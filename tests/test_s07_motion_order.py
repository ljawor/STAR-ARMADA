"""CPU production-AST motion order; no context or native GL calls.

Authored mixed scenes phase every visible ship's motion around independent
per-entity uncached hulls; legacy-only scenes retain per-entity submission.
Cached legacy role suppression is intentionally unchanged.
"""
import ast
from types import SimpleNamespace as NS
import unittest
from test_s07_lod_environment import (
    SOURCE, production_namespace, renderer_fixture, entity, fake_imports, noop,
)


def trace(cached, authored=(True, True), speeds=(36., 36.), visible=True,
          apparent=60.):
    ns = production_namespace()
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    helpers = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name in ('_draw_ship_trail', '_draw_ship_glow')]
    for node in helpers:
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                if child.id.startswith('gl'):
                    ns[child.id] = noop
                elif child.id.startswith('GL_'):
                    ns[child.id] = 1
    exec(compile(ast.Module(body=helpers, type_ignores=[]), str(SOURCE), 'exec'), ns)
    renderer, size, _ = renderer_fixture(ns, 'rebel:frigate')
    ships = [entity('rebel:frigate') for _ in speeds]
    for i, (ship, speed, selected) in enumerate(zip(ships, speeds, authored)):
        ship.id = i + 1
        ship.yaw = 0.
        ship.selected = selected
        ship.vel = NS(length=lambda speed=speed: speed)
    renderer._ship_size = lambda e: NS(**{**vars(size), 'shape':
        'rebel:frigate' if e.selected else 'needle'})
    ns['is_authored'] = lambda binding: binding == 'rebel:frigate'
    ns['segment_visible'] = lambda *a: visible
    ns['position'] = lambda p: p
    renderer._in_front = lambda *a: visible
    renderer.state = NS(entities={e.id: e for e in ships},
                        can_see=lambda *a: True,
                        is_position_visible=lambda *a: visible)
    events = []
    ns['glBegin'] = lambda *a: events.append('trail')
    ns['glCallList'] = lambda key: events.append('hull:' + key)
    renderer._draw_glow = lambda *a, **k: events.append('glow')
    for name in ('_draw_ship_trail', '_draw_ship_glow'):
        setattr(renderer, name, lambda *a, _name=name: ns[_name](renderer, *a))
    # Recorders are installed in the actual live namespace used by each function,
    # not a copied globals dict containing stale native GL entry points.
    for name in ('_draw_ships', '_draw_ship', '_draw_ship_trail', '_draw_ship_glow'):
        assert ns[name].__globals__ is ns
        assert ns[name].__globals__['glCallList'] is ns['glCallList']
    cache = {'visible': [(e, None) for e in ships], 'relation': {0: 'own'},
             'owner_color': {0: (.3, .6, .9)}}
    cache.update({e.id: {'apparent': apparent, 'size': renderer._ship_size(e)}
                  for e in ships})
    with fake_imports():
        ns['_draw_ships'](renderer, set(), cache if cached else None)
    return events


def phases(events):
    return ['hull' if event.startswith('hull:') else event for event in events]


class MotionOrderTests(unittest.TestCase):
    def test_authored_overlapping_moving_ships_match_cached_motion_phases(self):
        expected = ['trail'] * 2 + ['hull'] * 12 + ['glow'] * 2
        self.assertEqual(phases(trace(True)), expected)
        self.assertEqual(phases(trace(False)), expected)

    def test_legacy_only_keeps_per_entity_order(self):
        self.assertEqual(phases(trace(False, (False, False))),
                         (['trail'] + ['hull'] * 6 + ['glow']) * 2)

    def test_mixed_keeps_vfx_counts_and_cached_legacy_role_suppression(self):
        for cached in (False, True):
            events = trace(cached, (True, False), apparent=8.)
            hulls = 7 if cached else 12
            self.assertEqual(phases(events),
                             ['trail'] * 2 + ['hull'] * hulls + ['glow'] * 2)
            self.assertEqual(sum(e.startswith('hull:rebel:frigate') for e in events), 6)

    def test_motion_thresholds_and_visibility_are_unchanged(self):
        for speed, trails, glows in ((0., 0, 0), (2., 0, 0),
                                     (8., 2, 0), (36., 2, 2)):
            for cached in (False, True):
                with self.subTest(speed=speed, cached=cached):
                    events = trace(cached, speeds=(speed, speed))
                    self.assertEqual(events.count('trail'), trails)
                    self.assertEqual(events.count('glow'), glows)
                    hidden = trace(cached, speeds=(speed, speed), visible=False)
                    self.assertEqual(hidden.count('trail'), 0)
                    self.assertEqual(hidden.count('glow'), 0)


if __name__ == '__main__':
    unittest.main()
