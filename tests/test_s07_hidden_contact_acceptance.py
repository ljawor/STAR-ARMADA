"""Selected, real-registry CPU contact guards; no GL or catalogue activation.

Historical memory here is the real transient ballistic contact, not a fabricated
ship/station last-seen entity (GameState only remembers static planets).
"""
from copy import deepcopy
import inspect
import math
import textwrap
import unittest
from unittest.mock import patch

import game.core.manager
from game.core.entity import Entity
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.unit_factory import UnitFactory
from render import asset_selection as selection
from render.fog import effect_visible
from render.renderer import Renderer
import render.renderer as renderer_module
from test_s07_selected_geometry_matrix import (
    ROOT, catalogue_rows, raw_geometry, rotate, frame_oracle, lies_on_triangle_mesh)
import json


class HiddenContactAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior_store = DataStore._instance
        cls.addClassCleanup(setattr, DataStore, '_instance', prior_store)
        prior = selection._selection, selection._resolver, selection._generation
        def restore():
            selection._selection, selection._resolver, selection._generation = prior
            selection.invalidate_geometry_helpers()
        cls.addClassCleanup(restore)
        cls.ds = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=[], balance={})
        selection.configure({'model_preview': True, 'visual_packs': []}, asset_root=ROOT)
        # Representative actual consumers, not a fake mesh/resolver candidate.
        cls.rows = [next(r for r in catalogue_rows(cls.ds)
                         if r['binding'].startswith('imperial:') and r['category'] == category)
                    for category in ('combat_hull', 'station', 'satellite', 'planet_installation')]
        manifests = [json.loads(p.read_text()) for p in (ROOT/'assets/models/manifests').glob('*.json')]
        cls.raw = {r['binding']: raw_geometry(next(m for m in manifests if m.get('asset') == r['manifest']))[2]
                   for r in cls.rows}

    def fixture(self, row):
        state = GameState(players={0: PlayerState(0, faction='rebel'),
                                   1: PlayerState(1, faction='imperial')})
        factory = UnitFactory(state)
        observer = factory.spawn_ship('rebel_corvette', 0, Vec3(0., 5000., 0.))
        observer.sensor_range = 2000.
        data_id = row['consumers'][0]['data_id']
        target = (factory.spawn_ship(data_id, 1, Vec3(100., 5000., 0.))
                  if row['category'] == 'combat_hull' else
                  factory.spawn_station(data_id, 1, Vec3(100., 5000., 0.)))
        target.yaw = .73
        planet = None
        if row['category'] in ('satellite', 'planet_installation'):
            planet = Entity(id=100, kind='planet', owner=-1, data_id='temperate',
                            is_planet=True, pos=Vec3(100., 4300., 0.), radius=650.)
            state.add_entity(planet)
            target.planet_id = planet.id
            if row['category'] == 'satellite':
                target.satellite_slot = 2
            else:
                target.planet_building_slot = 4
                target.pos = Vec3(100., 4951., 0.)
        renderer = Renderer.__new__(Renderer)
        renderer.ds, renderer.state, renderer.local_player, renderer.time = self.ds, state, 0, 0.
        renderer._station_angle = lambda: 0.51
        renderer._px_per_world = lambda *args, **kwargs: 1.
        resolved = selection._resolver.resolve(row['binding'])
        self.assertIsNotNone(resolved)
        self.assertIs(selection.mesh_for(row['binding']), resolved.mesh)
        raw = self.raw[row['binding']]
        if target.is_ship:
            self.assertEqual(renderer._ship_size(target).shape, row['binding'])
            world = rotate(raw * renderer._ship_size(target).scale, target.yaw) + target.pos.to_tuple()
            normal = (0., 1., 0.)
        else:
            origin, basis = frame_oracle(target, planet, renderer._station_angle())
            world = (raw * (target.radius/50.)) @ basis + origin
            normal = tuple(basis[1])
        effect = dict(kind='hull_hit', target_id=target.id, pos=tuple(world[0].mean(axis=0)),
                      normal=normal, center=target.pos.to_tuple(), radius=target.radius, size=5., t=0.)
        self.assertTrue(state.can_see(0, target.id))
        self.assertTrue(effect_visible(state, 0, effect))
        state.effects.append(effect)
        return state, target, planet, observer, renderer, world, effect

    def assert_draw(self, renderer, effect, expected):
        state = renderer.state
        before, effects = deepcopy(state.to_dict(precise=True)), deepcopy(state.effects)
        with patch('render.hit_effects.draw_hit') as draw:
            renderer._draw_hits()  # Real consumer; only GL endpoint replaced.
        self.assertEqual(draw.call_count, int(expected))
        if expected:
            self.assertEqual(draw.call_args.args[1], effect)
        self.assertEqual(state.to_dict(precise=True), before)
        self.assertEqual(state.effects, effects)

    def test_visible_selected_hulls_use_raw_mesh_and_copy_effects(self):
        for row in self.rows:
            with self.subTest(binding=row['binding']):
                state, target, planet, observer, renderer, world, effect = self.fixture(row)
                before, original = deepcopy(state.to_dict(precise=True)), deepcopy(effect)
                mapped = renderer._visual_hit(effect)
                self.assertIsNot(mapped, effect)
                self.assertTrue(mapped.get('visual_contact'))
                self.assertTrue(lies_on_triangle_mesh(mapped['pos'], world))
                self.assertEqual(effect, original)
                self.assert_draw(renderer, mapped, True)
                self.assertEqual(state.to_dict(precise=True), before)

    def test_hidden_historical_contacts_do_not_follow_current_transform(self):
        for row in self.rows:
            for kind in ('hull_hit', 'shield_hit', 'impact'):
                with self.subTest(binding=row['binding'], kind=kind):
                    state, target, planet, observer, renderer, world, effect = self.fixture(row)
                    effect['kind'] = kind
                    original = deepcopy(effect)
                    # Preserve legal observed ballistic coordinates; move live geometry
                    # and attached parent far outside the same unchanged sensor picture.
                    for x in (30000., 50000.):
                        target.pos = Vec3(x, 9000., -5000.)
                        target.yaw += 1.2
                        target.radius *= 1.4
                        if planet:
                            planet.pos = Vec3(x, 8300., -5000.)
                        self.assertFalse(state.can_see(0, target.id))
                        self.assertIsNone(state.known_entity(0, target.id))
                        self.assertTrue(effect_visible(state, 0, effect))
                        before = deepcopy(state.to_dict(precise=True))
                        self.assertIs(renderer._visual_hit(effect), effect,
                                      'hidden current geometry must not remap historical contact')
                        self.assert_draw(renderer, original, True)
                        self.assertEqual(state.to_dict(precise=True), before)

    def test_stale_removed_targets_and_unsensed_historical_positions(self):
        for row in self.rows:
            with self.subTest(binding=row['binding']):
                state, target, planet, observer, renderer, world, effect = self.fixture(row)
                state.entities.pop(target.id)
                self.assertFalse(state.can_see(0, target.id))
                self.assertIs(renderer._visual_hit(effect), effect)
                self.assert_draw(renderer, deepcopy(effect), True)
                # A remembered ballistic contact is not permission to draw after
                # its location itself falls outside current sensors.
                observer.pos = Vec3(-50000., 5000., 0.)
                self.assertFalse(effect_visible(state, 0, effect))
                self.assert_draw(renderer, effect, False)

    def test_visibility_gate_defixed_negative_control_fails_real_guard(self):
        source = textwrap.dedent(inspect.getsource(Renderer._visual_hit))
        gate = '    if not self.state.can_see(self.local_player, target_id):\n        return fx\n'
        self.assertEqual(source.count(gate), 1)
        namespace = dict(vars(renderer_module))
        exec(compile(source.replace(gate, '', 1), '<visibility-gate-defixed>', 'exec'), namespace)
        # Source rewritten only in memory; never mutate production files while
        # another acceptance owner may be importing them.
        with patch.object(Renderer, '_visual_hit', namespace['_visual_hit']):
            case = type(self)('test_hidden_historical_contacts_do_not_follow_current_transform')
            result = unittest.TestResult()
            case.run(result)
        self.assertFalse(result.wasSuccessful(), 'de-fixed visibility gate escaped the guard')
        self.assertFalse(result.errors, result.errors)
        self.assertEqual(len(result.failures), len(self.rows)*3)
        for test, traceback in result.failures:
            self.assertIn('hidden current geometry must not remap historical contact', traceback)


if __name__ == '__main__':
    unittest.main()
