"""Asteroid fields must reach the native window: they are the only mining sites.

The collector used to skip them ("not spheres, stay out until they have their own
pass"), so every map drew without its fields and a player had nothing to anchor a
mining station to. These tests pin the binding, the scale and the visible result.
"""
import json
import os
import unittest
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game.core.skirmish import build_skirmish_map, default_skirmish_options
from game.core.manager import GameManager
from game.data.store import DataStore
from render.asset_selection import ship_binding
from render.ship_sizes import ship_size
from render_bridge import collect, packed


ROOT = Path(__file__).resolve().parents[1]


class AsteroidFieldCollectionTests(unittest.TestCase):
    def setUp(self):
        self.ds = DataStore()
        self.map_def = build_skirmish_map(self.ds, default_skirmish_options(self.ds))
        self.manager = GameManager.start_skirmish(self.map_def)
        self.state = self.manager.state
        self.asteroids = [e for e in self.state.entities.values()
                          if e.is_planet and e.data_id == 'asteroid_field']
        self.assertTrue(self.asteroids, 'fixture map has no asteroid fields')

    def tables(self, state=None):
        bindings, weapons = collect.required_names(
            state or self.state, self.ds, ship_size=ship_size,
            ship_binding=ship_binding, all_visible=True)
        return packed.Tables.build(bindings, list(weapons))

    def collector(self, tables):
        return collect.FrameCollector(self.ds, tables, asset_selection=None,
                                      ship_size=ship_size,
                                      ship_binding=ship_binding,
                                      all_visible=True)

    def test_the_scale_matches_the_prop_it_draws(self):
        # The scale is only right while the prop still spans +-ASTEROID_EXTENT: a re-authored
        # mesh that grows or shrinks would silently change how big a field looks (and where
        # the rocks sit relative to the mining radius). Read the asset, do not trust the constant.
        mesh = json.loads((ROOT / 'assets/models/shared_asteroid_field.mesh.json').read_text())
        (x0, _y0, z0), (x1, _y1, z1) = mesh['bounds']
        self.assertAlmostEqual(collect.ASTEROID_EXTENT, (x1 - x0) / 2, places=6)
        self.assertAlmostEqual(collect.ASTEROID_EXTENT, (z1 - z0) / 2, places=6)

    def test_session_table_reserves_the_asteroid_binding(self):
        bindings, _ = collect.required_names(
            self.state, self.ds, ship_size=ship_size,
            ship_binding=ship_binding, all_visible=True)
        self.assertIn(collect.ASTEROID_BINDING, bindings,
                      'a session table without the binding can never draw a field')

    def test_every_asteroid_field_is_emitted_with_the_environment_binding(self):
        tables = self.tables()
        collector = self.collector(tables)
        instances, _effects, stats = collector.collect(self.state)
        index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
        drawn = [i for i in instances if i[1] == index]
        self.assertEqual(len(drawn), len(self.asteroids),
                         'an asteroid field was dropped from the frame')
        self.assertEqual(stats['omitted_planets'], 0,
                         'asteroid fields are still counted as omitted planets')
        self.assertIn(collect.ASTEROID_BINDING, tables.bindings)

    def test_field_is_scaled_to_its_mining_radius(self):
        tables = self.tables()
        index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
        instances, _e, _s = self.collector(tables).collect(self.state)
        by_entity = {record[0]: record for record in instances}
        for asteroid in self.asteroids:
            record = by_entity[asteroid.id]
            self.assertEqual(record[1], index)
            # The model spans +-ASTEROID_EXTENT, so scaling it to fill the field's radius
            # keeps the picture inside the radius the simulation mines within. Matrix columns
            # start at index 7; the x column is (c*s, 0, -s*s) and the y column is (0, s, 0).
            scale = record[11]
            self.assertAlmostEqual(scale, asteroid.radius / collect.ASTEROID_EXTENT, places=3)

    def test_a_map_without_fields_emits_none_and_still_renders(self):
        for entity in self.asteroids:
            entity.alive = False
        tables = self.tables()
        instances, _e, stats = self.collector(tables).collect(self.state)
        index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
        self.assertEqual([i for i in instances if i[1] == index], [])
        self.assertGreater(stats['instances'], 0)

    def test_every_shipped_skirmish_map_draws_its_fields(self):
        for map_id in sorted(self.ds.maps):
            if not map_id.startswith('skirmish'):
                continue
            options = dict(default_skirmish_options(self.ds), map_id=map_id)
            manager = GameManager.start_skirmish(build_skirmish_map(self.ds, options))
            state = manager.state
            fields = [e for e in state.entities.values()
                      if e.is_planet and e.data_id == 'asteroid_field']
            self.assertTrue(fields, f'{map_id} defines no asteroid fields')
            tables = self.tables(state)
            instances, _e, _s = self.collector(tables).collect(state)
            index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
            drawn = [i for i in instances if i[1] == index]
            self.assertEqual(len(drawn), len(fields), f'{map_id} hides its asteroid fields')


if __name__ == '__main__':
    unittest.main()
