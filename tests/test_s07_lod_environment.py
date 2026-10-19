"""CPU acceptance of production role suppression and asteroid branch RNG.

AST extraction executes unchanged production bodies without importing/constructing
Renderer or opening GL. GL entry points and display-list lookup are recording
seams, not rasterization. Authored ships keep all roles; legacy ships retain
cached role suppression. This is neither pixel parity nor mesh LOD acceptance.
"""
import ast
from contextlib import nullcontext
import copy
import hashlib
import json
import math
from pathlib import Path
import random
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'render/renderer.py'
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
EPS = 1e-6
PIXELS = (16.0 - EPS, 16.0, 16.0 + EPS, 34.0 - EPS, 34.0, 34.0 + EPS)
SHIP_BINDINGS = ('rebel:battleship', 'rebel:frigate', 'imperial:fighter',
                 'syndicate:convoy', 'confederacy:constructor')
STATION_BINDINGS = tuple(f'{f}:shipyard' for f in
                         ('rebel', 'imperial', 'syndicate', 'confederacy'))


def noop(*args, **kwargs):
    return None


class FakeGL(ModuleType):
    def __getattr__(self, name):
        return 1 if name.startswith('GL_') else noop


def production_namespace(mutation=None):
    """Compile selected actual AST nodes; mutations are in-memory controls only."""
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    wanted = {'_draw_ship_role_batch', '_draw_ship', '_draw_ships',
              '_draw_asteroid_field', '_draw_rock', 'field_placement', 'rock_params'}
    nodes = [copy.deepcopy(n) for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in wanted]
    nodes += [copy.deepcopy(n) for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'ASTEROID_ROLE_TINTS'
                      for t in n.targets)]
    if mutation:
        nodes = mutation(nodes)
    ns = {'math': math, 'random': random, 'Entity': object,
          'mk': NS(hull_shade=lambda color, relation: color),
          'is_authored': lambda binding: True,
          'Vec3': lambda x, y, z: NS(x=x, y=y, z=z)}
    for n in nodes:
        for child in ast.walk(n):
            if isinstance(child, ast.Name):
                if child.id.startswith('gl'):
                    ns[child.id] = noop
                elif child.id.startswith('GL_'):
                    ns[child.id] = 1
    ns['_gl'] = FakeGL('OpenGL.GL')
    mod = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), str(SOURCE), 'exec',
                 flags=__import__('__future__').annotations.compiler_flag), ns)
    return ns


def entity(binding, station=False):
    faction, key = binding.split(':')
    return NS(id=1, owner=0, data_id=key, radius=50., pos=NS(x=17., y=3., z=-9.),
              yaw=.2, vel=NS(length=lambda: 0.), is_ship=not station,
              is_squadron=False, is_station=station, is_planet=False,
              alive=True, jump_travelling=False)


def renderer_fixture(ns, binding):
    size = NS(shape=binding, scale=1., length=100., stern=-50., half_width=20.)
    calls = []
    ns['glCallList'] = calls.append
    materials = NS(available=True, hull_pass=noop, use=lambda *a, **k: nullcontext())
    renderer = NS(materials=materials, time=3., ds=None, _hull_tex=1,
                  local_player=0, skip=set(), _material_metal=noop,
                  _material_matte=noop, _ship_size=lambda e: size,
                  _hull_color=lambda e: (.3, .6, .9),
                  _owner_color=lambda owner: (.3, .6, .9),
                  _ship_display_list=lambda key: key,
                  _station_detail_list=lambda key, role, faction: f'{faction}:{key}:{role}')
    for name in ('_draw_ship', '_draw_ship_role_batch'):
        setattr(renderer, name, lambda *a, _name=name, **k: ns[_name](renderer, *a, **k))
    return renderer, size, calls


def fake_imports(faction='rebel'):
    gl = FakeGL('OpenGL.GL')
    package = ModuleType('OpenGL')
    package.GL = gl
    frame = ModuleType('render.planet_building_geometry')
    frame.station_frame = lambda *a: ((0., 0., 0.),
                                      ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)), None)
    visual = ModuleType('render.faction_visuals')
    visual.owner_faction = lambda *a: faction
    return patch.dict('sys.modules', {'OpenGL': package, 'OpenGL.GL': gl,
                      'render.planet_building_geometry': frame,
                      'render.faction_visuals': visual})


def expected_roles(px):
    return ('base',) if px < 16. else ('base', 'lit') if px < 34. else ROLES


def observed_roles(ns, binding, px, station=False, uncached=False):
    renderer, size, calls = renderer_fixture(ns, binding)
    e = entity(binding, station)
    renderer.state = NS(entities={e.id: e}, can_see=lambda *a: True)
    cache = {'relation': {0: 'own'}, 'owner_color': {0: (.3, .6, .9)},
             e.id: {'apparent': px, 'size': size}}
    with fake_imports(binding.split(':')[0]):
        if uncached:
            # Drive actual production uncached dispatch, then actual _draw_ship.
            ns['_draw_ships'](renderer, set(), None)
        else:
            for index, role in enumerate(ROLES):
                ns['_draw_ship_role_batch'](renderer, role, [] if station else [e],
                                           [e] if station else [], cache,
                                           material_pass=float(index) if index < 3 else None)
    if station:
        return tuple(call.rsplit(':', 1)[1] for call in calls)
    return tuple('base' if call == binding else call.removeprefix(binding + '_')
                 for call in calls)


def field_trace(ns, selected, x=122.5):
    """Record actual field translations/tumbles, actual rock branch and RNG state."""
    placements, translations, rotations, scales, lists, facets, rngs = [], [], [], [], [], [], []
    original_placement = ns['field_placement']
    def placement(radius, rng):
        value = original_placement(radius, rng)
        placements.append(value)
        return value
    def make_rng(seed):
        rng = random.Random(seed)
        rngs.append(rng)
        return rng
    ns['field_placement'] = placement
    ns['random'] = NS(Random=make_rng)
    ns.update(glTranslatef=lambda *a: translations.append(a),
              glRotatef=lambda *a: rotations.append(a),
              glScalef=lambda *a: scales.append(a), glCallList=lists.append)
    prop = {role: 'prop:' + role for role in ROLES} if selected else None
    r = NS(time=11., _asteroid_prop_lists=lambda: prop,
           _rock_facets=lambda *a: facets.append(a))
    r._draw_rock = lambda *a: ns['_draw_rock'](r, *a)
    ns['_draw_asteroid_field'](r, NS(pos=NS(x=x, y=6., z=-90.), radius=360.))
    return NS(placements=placements, translations=translations, rotations=rotations,
              scales=scales, lists=lists, facets=facets, rng_state=rngs[0].getstate())


def remove_rock_rng_before_selected(nodes):
    """De-fix: selected prop returns before consuming rock_params RNG."""
    rock = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == '_draw_rock')
    assignment = next(n for n in rock.body if isinstance(n, ast.Assign))
    branch = next(n for n in rock.body if isinstance(n, ast.If))
    rock.body.remove(assignment)
    branch.body.insert(0, ast.Assign(targets=copy.deepcopy(assignment.targets),
                                   value=ast.parse('((0.5, 0.5, 0.5), [])', mode='eval').body))
    rock.body.insert(rock.body.index(branch) + 1, assignment)
    return nodes


class S07LodEnvironmentTests(unittest.TestCase):
    def test_registered_representatives_authored_parity_and_legacy_thresholds(self):
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
        rows = {row['binding']: row for row in registry['bindings']}
        ns = production_namespace()
        evidence = []
        for binding in SHIP_BINDINGS:
            self.assertEqual(rows[binding]['status'], 'core')
            for authored in (True, False):
                ns['is_authored'] = lambda key, selected=authored: selected
                for px in PIXELS:
                    with self.subTest(binding=binding, authored=authored, apparent=px):
                        cached = observed_roles(ns, binding, px)
                        uncached = observed_roles(ns, binding, px, uncached=True)
                        self.assertEqual(cached, ROLES if authored else expected_roles(px))
                        self.assertEqual(uncached, ROLES)
                        self.assertEqual(cached == uncached, authored or px >= 34.)
                        evidence.append({'binding': binding, 'authored': authored,
                                         'apparent': px, 'cached': cached,
                                         'uncached': uncached})
        print('LOD_ROLE_SUBMISSION_NOT_PIXEL_PARITY_OR_MESH_LOD ' + json.dumps(evidence))

    def test_registered_station_controls_keep_all_roles_at_every_threshold(self):
        rows = {r['binding']: r for r in json.loads(
            (ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))['bindings']}
        ns = production_namespace()
        for binding in STATION_BINDINGS:
            self.assertEqual(rows[binding]['status'], 'core')
            for px in PIXELS:
                with self.subTest(binding=binding, apparent=px):
                    self.assertEqual(observed_roles(ns, binding, px, station=True), ROLES)

    def assert_field_equivalent(self, selected, fallback):
        self.assertEqual(len(selected.placements), 40)
        self.assertEqual(len(fallback.placements), 40)
        self.assertEqual(selected.placements, fallback.placements)
        self.assertEqual(selected.translations, fallback.translations)
        self.assertEqual(selected.rotations, fallback.rotations)
        self.assertEqual(selected.rng_state, fallback.rng_state)

    def test_actual_field_and_rock_branches_preserve_all_40_placements_and_final_rng(self):
        for x in (122.5, -37.25, 0.):
            with self.subTest(field_x=x):
                selected = field_trace(production_namespace(), True, x)
                fallback = field_trace(production_namespace(), False, x)
                self.assert_field_equivalent(selected, fallback)
                self.assertEqual(selected.translations,
                                 [(x, 6., -90.)] + [p[:3] for p in selected.placements])
                self.assertEqual(selected.rotations,
                                 [(11. * .15 * p[4], .3, .7, .2)
                                  for p in selected.placements])
                self.assertEqual(selected.facets, [])
                self.assertEqual(selected.lists, ['prop:' + r for r in ROLES] * 40)
                self.assertEqual(selected.scales, [(p[3],) * 3 for p in selected.placements])
                self.assertEqual(fallback.lists, [])
                self.assertEqual(fallback.scales, [])
                self.assertGreaterEqual(len(fallback.facets), 80)
                self.assertLessEqual(len(fallback.facets), 160)
                self.assertTrue(all(len(args[4]) == 14 for args in fallback.facets))
                print('ASTEROID_ACTUAL_BRANCHES ' + json.dumps({
                    'field_x': x, 'placements': selected.placements,
                    'final_rng_sha256': hashlib.sha256(repr(selected.rng_state).encode()).hexdigest(),
                    'selected_prop_calls': len(selected.lists),
                    'fallback_facet_calls': len(fallback.facets)}))

    def test_negative_control_threshold_suppression_guard_bites(self):
        def defix(nodes):
            batch = next(n for n in nodes if isinstance(n, ast.FunctionDef)
                         and n.name == '_draw_ship_role_batch')
            loop = next(n for n in batch.body if isinstance(n, ast.For))
            # De-fix the actual production ship-role suppression, not the oracle.
            removed = [n for n in loop.body if isinstance(n, ast.If)
                       and any(isinstance(c, ast.Continue) for c in n.body)
                       and 'apparent' in ast.unparse(n.test)]
            if len(removed) != 2:
                raise AssertionError('threshold control target is no longer unique')
            loop.body = [n for n in loop.body if n not in removed]
            return nodes
        ns = production_namespace(defix)
        ns['is_authored'] = lambda binding: False
        observed = observed_roles(ns, SHIP_BINDINGS[0], 16. - EPS)
        with self.assertRaises(AssertionError):
            self.assertEqual(observed, expected_roles(16. - EPS))
        print('NEGATIVE_CONTROL_CAUGHT removed_actual_role_suppression')

    def test_negative_control_selected_rock_rng_skip_guard_bites(self):
        selected = field_trace(production_namespace(remove_rock_rng_before_selected), True)
        fallback = field_trace(production_namespace(), False)
        self.assertNotEqual(selected.placements[1:], fallback.placements[1:])
        self.assertNotEqual(selected.rng_state, fallback.rng_state)
        with self.assertRaises(AssertionError):
            self.assert_field_equivalent(selected, fallback)
        print('NEGATIVE_CONTROL_CAUGHT skipped_actual_selected_rock_rng_consumption')


if __name__ == '__main__':
    unittest.main()
