"""CPU execution of real Renderer construction methods; never opens a GL context.

Real resolver, GameState, factory, station dispatch, outlines and triangle emitter.
Only GL entry points/material context are recording seams. Raw approval-pinned
payloads are the independent mesh oracle. This is not native visual acceptance,
input-placement validation, queue advancement, or a simulation buildability test.
"""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import textwrap
from types import FunctionType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

import game.core.manager  # Preserve the application's import order.
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.unit_factory import UnitFactory
from game.benchmark import state_hash
from render import renderer as module, asset_selection as selection
from render.authored_mesh import _load_profile
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[1]
FACTIONS = ('imperial', 'rebel', 'confederacy', 'syndicate')
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


class RecordingGL:
    """Small mask-aware recorder, not an implementation of a GL driver."""
    GROUPS = {'enabled': GL.GL_ENABLE_BIT, 'depth_mask': GL.GL_DEPTH_BUFFER_BIT,
              'color': GL.GL_CURRENT_BIT, 'blend': GL.GL_COLOR_BUFFER_BIT,
              'polygon': GL.GL_POLYGON_BIT, 'width': GL.GL_LINE_BIT}

    def __init__(self, depth=True):
        self.state = dict(enabled={int(GL.GL_DEPTH_TEST): depth,
                                   int(GL.GL_LIGHTING): True,
                                   int(GL.GL_TEXTURE_2D): True,
                                   int(GL.GL_CULL_FACE): True,
                                   int(GL.GL_BLEND): False}, depth_mask=True,
                          color=(.17, .23, .31, .43), blend=('caller', 'blend'),
                          polygon=('caller', 'polygon'), width=7.)
        self.initial = deepcopy(self.state)
        self.attribs, self.matrices, self.transforms = [], [], []
        self.calls, self.batches, self.active = [], [], None

    def call(self, name, *args):
        self.calls.append((name, args))
        if name == 'glPushAttrib':
            self.attribs.append((int(args[0]), deepcopy(self.state)))
        elif name == 'glPopAttrib':
            mask, saved = self.attribs.pop()
            for key, group in self.GROUPS.items():
                if mask & int(group):
                    self.state[key] = saved[key]
        elif name == 'glPushMatrix':
            self.matrices.append(list(self.transforms))
        elif name == 'glPopMatrix':
            self.transforms = self.matrices.pop()
        elif name in ('glTranslatef', 'glRotatef', 'glScalef'):
            self.transforms.append((name, args))
        elif name in ('glDisable', 'glEnable'):
            self.state['enabled'][int(args[0])] = name == 'glEnable'
        elif name == 'glDepthMask':
            self.state['depth_mask'] = args[0]
        elif name in ('glColor3f', 'glColor4f'):
            self.state['color'] = tuple(args) + ((1.,) if len(args) == 3 else ())
        elif name == 'glBlendFunc':
            self.state['blend'] = args
        elif name == 'glPolygonMode':
            self.state['polygon'] = args
        elif name == 'glLineWidth':
            self.state['width'] = args[0]
        elif name == 'glBegin':
            assert self.active is None, 'nested glBegin'
            self.active = dict(mode=int(args[0]), vertices=[], transforms=list(self.transforms))
        elif name == 'glVertex3f':
            assert self.active is not None
            self.active['vertices'].append(tuple(args))
        elif name == 'glEnd':
            self.batches.append(self.active)
            self.active = None

    def install(self, stack):
        # Every imported GL entry point is intercepted: no real GL calls occur.
        names = {n for n, value in vars(module).items()
                 if n.startswith('gl') and callable(value)}
        names |= {'glPushAttrib', 'glPopAttrib', 'glDisable', 'glEnable',
                  'glDepthMask', 'glPolygonMode', 'glMaterialfv', 'glMaterialf'}
        for name in names:
            fn = lambda *args, _name=name: self.call(_name, *args)
            if hasattr(module, name):
                stack.enter_context(patch.object(module, name, fn))
            if hasattr(GL, name):
                stack.enter_context(patch.object(GL, name, fn))


class ConstructionRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous_store = DataStore._instance
        cls.addClassCleanup(setattr, DataStore, '_instance', previous_store)
        previous = selection._selection, selection._resolver, selection._generation
        def restore_selection():
            selection._selection, selection._resolver, selection._generation = previous
            selection.invalidate_geometry_helpers()
        cls.addClassCleanup(restore_selection)
        cls.ds = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=[], balance={})
        selection.configure({'model_preview': True, 'visual_packs': []}, asset_root=ROOT)
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
        cls.rows = sorted((r for r in registry['bindings']
                           if r['status'] == 'core' and r['category'] == 'station'),
                          key=lambda r: r['binding'])
        manifests = {m['asset']: m for p in (ROOT / 'assets/models/manifests').glob('*.json')
                     if (m := json.loads(p.read_text())).get('contract') == 'star-armada/model-manifest'}
        cls.raw = {}
        for row in cls.rows:
            manifest = manifests[row['manifest']]
            data = (ROOT / manifest['files']['mesh']['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != manifest['files']['mesh']['sha256']:
                raise AssertionError('raw oracle payload differs from selected manifest pin')
            payload = json.loads(data)
            cls.raw[row['binding']] = {
                role: tuple((tuple(face[:3]), tuple(tuple(payload['vertices'][i])
                                                    for i in face[3:]))
                            for face in payload['batches'][role]) for role in ROLES}

    def fixture(self, faction, kind='shipyard', progress=.5, pos=(137., 19., 307.)):
        state = GameState(players={0: PlayerState(0, faction=faction),
                                   1: PlayerState(1, faction=faction)})
        constructor = next(d.id for d in self.ds.ships.values()
                           if d.faction == faction and d.category == 'construction'
                           and d.id.endswith('_constructor'))
        builder = UnitFactory(state).spawn_ship(constructor, 0, Vec3())
        builder.build_queue = [dict(kind='station', item=kind, pos=pos,
                                   time_left=100. * (1. - progress), total=100.)]
        r = module.Renderer.__new__(module.Renderer)
        r.state, r.ds, r.local_player, r.time = state, self.ds, 0, 7.
        r._owner_color = lambda owner: (.2, .4, .8)
        # _in_front itself remains the actual production method.
        r._draw_view_geometry = lambda: ((0., 0., -2000.),
                                         ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)))
        r.materials = NS(use=lambda *a, **k: nullcontext(), hull_pass=lambda *a: None,
                         available=False)
        r.placement = dict(builder_id=builder.id, station_kind=kind,
                           ghost=dict(world=pos, valid=True))
        return state, builder, r

    def draw(self, r, method, *, depth=True):
        trace, emitted = RecordingGL(depth), []
        actual_emit = r._emit_detail_mesh
        def emit(mesh):
            emitted.append(mesh)
            actual_emit(mesh)
        before, digest = deepcopy(r.state.to_dict(precise=True)), state_hash(r.state)
        queue_refs = [(e.build_queue, tuple(e.build_queue)) for e in r.state.entities.values()]
        placement = deepcopy(r.placement)
        with ExitStack() as stack:
            trace.install(stack)
            stack.enter_context(patch.object(r, '_emit_detail_mesh', emit))
            draw_method = getattr(r, method)
            # A source-mutated function must use the same patched GL globals.
            # Fail before execution: native GL without a context can crash/hang.
            for name in draw_method.__code__.co_names:
                if name.startswith('gl') and hasattr(module, name):
                    self.assertIs(draw_method.__globals__.get(name), getattr(module, name),
                                  f'{name} bypasses CPU recording seam')
            draw_method()
        self.assertEqual(r.state.to_dict(precise=True), before)
        self.assertEqual(state_hash(r.state), digest)
        self.assertEqual(r.placement, placement)
        for e, (queue, items) in zip(r.state.entities.values(), queue_refs):
            self.assertIs(e.build_queue, queue)
            self.assertEqual(len(queue), len(items))
            for actual, original in zip(queue, items):
                self.assertIs(actual, original)
        self.assertEqual(trace.attribs, [])
        self.assertEqual(trace.matrices, [])
        self.assertEqual(trace.transforms, [])
        self.assertIsNone(trace.active)
        return trace, emitted

    def assert_station(self, binding, trace, emitted):
        selected = selection.mesh_for(binding)
        self.assertIsNotNone(selected)
        self.assertEqual(tuple(selected), ROLES)
        self.assertEqual(len(emitted), len(ROLES))
        triangles = [b for b in trace.batches if b['mode'] == int(GL.GL_TRIANGLES)]
        self.assertEqual(len(triangles), len(ROLES))
        for role, mesh, batch in zip(ROLES, emitted, triangles):
            self.assertIs(mesh, selected[role], f'{binding}:{role} bypassed selected geometry')
            self.assertEqual(mesh, self.raw[binding][role], f'{binding}:{role} raw mismatch')
            self.assertEqual(batch['vertices'], [v for _, triangle in self.raw[binding][role]
                                                for v in triangle])
        return triangles

    def test_four_faction_selected_scaffold_emits_approved_roles_and_progress_height(self):
        binding = 'shared:construction_scaffold'
        selected = selection.mesh_for(binding)
        self.assertIsNotNone(selected)
        manifest = json.loads((ROOT / 'assets/models/manifests/shared_construction_scaffold.json').read_bytes())
        payload_bytes = (ROOT / manifest['files']['mesh']['path']).read_bytes()
        self.assertEqual(hashlib.sha256(payload_bytes).hexdigest(), manifest['files']['mesh']['sha256'])
        payload = json.loads(payload_bytes)
        raw = {role: tuple((tuple(face[:3]), tuple(tuple(payload['vertices'][i]) for i in face[3:]))
                           for face in payload['batches'][role]) for role in ROLES}
        for faction in FACTIONS:
            for progress in (.1, .5, .9):
                for dict_pos in (False, True):
                    with self.subTest(faction=faction, progress=progress, dict_pos=dict_pos):
                        _, builder, r = self.fixture(faction, progress=progress)
                        if dict_pos:
                            builder.build_queue[0]['pos'] = dict(x=137., y=19., z=307.)
                        trace, emitted = self.draw(r, '_draw_construction_sites')
                        self.assertEqual(len(emitted), 12)
                        triangles = [b for b in trace.batches if b['mode'] == int(GL.GL_TRIANGLES)]
                        self.assertEqual(len(triangles), 12)
                        for role, mesh, batch in zip(ROLES, emitted[6:], triangles[6:]):
                            self.assertIs(mesh, selected[role])
                            self.assertEqual(mesh, raw[role])
                            self.assertEqual(batch['vertices'], [v for _, tri in raw[role] for v in tri])
                            scale = self.ds.stations['shipyard'].radius / 50.
                            self.assertEqual(batch['transforms'][0], ('glTranslatef', (137., 0., 307.)))
                            transform, values = batch['transforms'][1]
                            self.assertEqual(transform, 'glScalef')
                            for actual, expected in zip(values, (scale, scale * (.4 + .6 * progress), scale)):
                                self.assertAlmostEqual(actual, expected)
                        self.assertEqual([b['mode'] for b in trace.batches if b['mode'] != int(GL.GL_TRIANGLES)],
                                         [int(GL.GL_LINE_STRIP)])

    def assert_lattice(self, trace, radius, progress):
        batches = [b for b in trace.batches if b['mode'] != int(GL.GL_TRIANGLES)]
        self.assertEqual([b['mode'] for b in batches],
                         [int(GL.GL_LINE_LOOP), int(GL.GL_LINES),
                          int(GL.GL_LINE_LOOP), int(GL.GL_LINE_STRIP)])
        self.assertEqual([len(b['vertices']) for b in batches[:3]], [24, 16, 24])
        h = radius * (.4 + .6 * progress)
        for v in batches[0]['vertices']:
            self.assertEqual(v[1], 0.)
        for index, v in enumerate(batches[1]['vertices']):
            self.assertAlmostEqual(v[1], h if index % 2 else 0.)
        for v in batches[2]['vertices']:
            self.assertAlmostEqual(v[1], h)
        # Production computes fraction from queue timers; avoid imposing exact float rounding.
        self.assertIn(len(batches[3]['vertices']), (int(40 * progress), int(40 * progress) + 1))
        return batches

    def test_all_40_selected_station_placement_outlines_emit_raw_all_role_geometry(self):
        self.assertEqual(len(self.rows), 40)
        self.assertEqual({r['binding'].split(':')[0] for r in self.rows}, set(FACTIONS))
        for row in self.rows:
            binding = row['binding']
            faction, kind = binding.split(':')
            with self.subTest(binding=binding):
                _, _, r = self.fixture(faction, kind)
                for valid in (True, False):
                    r.placement['ghost']['valid'] = valid
                    trace, emitted = self.draw(r, '_draw_placement_preview', depth=False)
                    triangles = self.assert_station(binding, trace, emitted)
                    radius = self.ds.stations[kind].radius
                    self.assertEqual(triangles[0]['transforms'], [
                        ('glTranslatef', (137., 19., 307.)),
                        ('glRotatef', (21., 0, 1, 0)),
                        ('glScalef', (radius / 50.,) * 3)])
                    color = (.30, .90, .55) if valid else (1., .25, .20)
                    self.assertIn(('glColor4f', (*color, .55)), trace.calls)
                    self.assertEqual(trace.state, trace.initial)
        print('CONSTRUCTION_ACTUAL placement: 40 station bindings x valid/invalid = 80; raw six-role identity, actual emitter, transforms, exact simulation/queue preservation')

    def test_four_faction_queue_progress_uses_legacy_scaffold_and_preserves_timers(self):
        # Explicit mixed-mode fallback fixture: selected station meshes, no
        # scaffold mesh. Publication no longer implies the scaffold is absent.
        original_mesh_for = selection.mesh_for
        fallback = patch.object(selection, 'mesh_for', side_effect=lambda binding:
                                None if binding == 'shared:construction_scaffold'
                                else original_mesh_for(binding))
        fallback.start()
        self.addCleanup(fallback.stop)
        self.assertIsNone(selection.mesh_for('shared:construction_scaffold'))
        for faction in FACTIONS:
            for progress in (.1, .5, .9):
                for position_dict in (False, True):
                    with self.subTest(faction=faction, progress=progress, dict_pos=position_dict):
                        _, builder, r = self.fixture(faction, progress=progress)
                        if position_dict:
                            builder.build_queue[0]['pos'] = dict(x=137., y=19., z=307.)
                        trace, emitted = self.draw(r, '_draw_construction_sites')
                        self.assert_station(faction + ':shipyard', trace, emitted)
                        self.assert_lattice(trace, self.ds.stations['shipyard'].radius, progress)
                        # The production queue helper does NOT scope line width.
                        expected = deepcopy(trace.initial)
                        expected['width'] = 3.
                        self.assertEqual(trace.state, expected)
        print('CONSTRUCTION_ACTUAL queue: 4 factions x 3 progress x tuple/dict = 24; selected shipyard outlines, unregistered legacy lattice, unchanged precise state/hash/queue object/timers')

    def test_queue_state_restoration_limit_is_explicit(self):
        _, _, r = self.fixture('imperial')
        trace, _ = self.draw(r, '_draw_construction_sites', depth=False)
        expected = deepcopy(trace.initial)
        expected['width'] = 3.
        expected['enabled'][int(GL.GL_DEPTH_TEST)] = True
        self.assertEqual(trace.state, expected)
        print('CONSTRUCTION_STATE_LIMIT actual queue method leaves line width 3 and forces depth test enabled; outline itself restores recorded scoped state')

    def test_outline_exception_restores_recorded_state_and_matrix(self):
        _, _, r = self.fixture('imperial')
        trace = RecordingGL(depth=False)
        with ExitStack() as stack:
            trace.install(stack)
            stack.enter_context(patch.object(r, '_emit_detail_mesh', side_effect=RuntimeError('injected emitter failure')))
            with self.assertRaisesRegex(RuntimeError, 'injected emitter failure'):
                r._draw_station_outline('shipyard', 'imperial', (137.,19.,307.), 90., (.2,.4,.8))
        self.assertEqual(trace.state, trace.initial)
        self.assertEqual((trace.attribs, trace.matrices, trace.transforms), ([], [], []))

    def test_actual_preview_and_queue_reject_nonlocal_dead_and_behind_eye(self):
        for faction in FACTIONS:
            for method in ('_draw_placement_preview', '_draw_construction_sites'):
                for reason in ('nonlocal', 'dead', 'not_constructor', 'behind_eye'):
                    with self.subTest(faction=faction, method=method, reason=reason):
                        _, builder, r = self.fixture(faction)
                        if reason == 'nonlocal':
                            builder.owner = 1
                        elif reason == 'dead':
                            builder.hull = 0.
                            builder.alive = False  # Factory stores liveness explicitly.
                        elif reason == 'not_constructor':
                            builder.data_id = next(d.id for d in self.ds.ships.values()
                                                   if d.faction == faction and d.category == 'corvette')
                            # Entity flags are stored; do not infer mutable flags from data_id.
                            builder.is_construction = False
                        else:
                            builder.build_queue[0]['pos'] = (137., 19., -3000.)
                            r.placement['ghost']['world'] = (137., 19., -3000.)
                        trace, emitted = self.draw(r, method)
                        self.assertEqual(emitted, [])
                        self.assertEqual(trace.calls, [])

    def test_negative_control_wrong_geometry_is_rejected_by_raw_identity_guard(self):
        _, _, r = self.fixture('imperial')
        with patch.object(module, 'station_mesh', return_value=selection.mesh_for('rebel:shipyard')):
            trace, emitted = self.draw(r, '_draw_placement_preview')
        with self.assertRaises(AssertionError):
            self.assert_station('imperial:shipyard', trace, emitted)
        print('NEGATIVE_CONTROL_CAUGHT actual station dispatch replaced with wrong faction geometry')

    def test_negative_control_nonlocal_queue_gate_removal_is_caught(self):
        source = textwrap.dedent(inspect.getsource(module.Renderer._draw_construction_sites))
        old = ' or e.owner != self.local_player'
        self.assertEqual(source.count(old), 1)
        namespace = dict(vars(module))
        exec(compile(source.replace(old, ''), str(ROOT / 'render/renderer.py'), 'exec'), namespace)
        _, builder, r = self.fixture('imperial')
        builder.owner = 1
        # Keep the mutated bytecode, but share the renderer's patchable globals.
        mutant = FunctionType(namespace['_draw_construction_sites'].__code__, vars(module))
        r._draw_construction_sites = mutant.__get__(r)
        trace, emitted = self.draw(r, '_draw_construction_sites')
        with self.assertRaises(AssertionError):
            self.assertEqual(emitted, [])
        self.assertGreater(len(trace.calls), 0)
        print('NEGATIVE_CONTROL_CAUGHT in-memory production nonlocal queue filter removal')

    def test_negative_control_missing_selected_scaffold_is_caught(self):
        original = selection.mesh_for
        self.assertIsNotNone(original('shared:construction_scaffold'))
        with patch.object(selection, 'mesh_for', lambda binding:
                          None if binding == 'shared:construction_scaffold' else original(binding)):
            _, _, r = self.fixture('imperial')
            trace, emitted = self.draw(r, '_draw_construction_sites')
            with self.assertRaises(AssertionError):
                self.assertEqual(len(emitted), 12, 'Selected station + selected scaffold must emit all roles')
            self.assert_lattice(trace, self.ds.stations['shipyard'].radius, .5)
            self.assertEqual(len(emitted), 6)
        self.assertIsNotNone(selection.mesh_for('shared:construction_scaffold'))
        print('NEGATIVE_CONTROL_CAUGHT missing registered scaffold; production fallback remains intact but cannot pass selected acceptance')


if __name__ == '__main__':
    unittest.main()
