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
from render_bridge import collect, packed, planets as planet_bindings


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
        # mesh that grows or shrinks would silently change how big a field looks (and where the
        # rocks sit relative to the mining radius). Measured from the vertices - the `bounds`
        # record is written by the exporter, so trusting it would miss a stale export.
        mesh = json.loads((ROOT / 'assets/models/shared_asteroid_field.mesh.json').read_text())
        xs = [vertex[0] for vertex in mesh['vertices']]
        zs = [vertex[2] for vertex in mesh['vertices']]
        self.assertAlmostEqual(collect.ASTEROID_EXTENT, (max(xs) - min(xs)) / 2, places=6)
        self.assertAlmostEqual(collect.ASTEROID_EXTENT, (max(zs) - min(zs)) / 2, places=6)
        # ... and the exporter's own record must agree with the geometry it describes.
        (bx0, _by0, bz0), (bx1, _by1, bz1) = mesh['bounds']
        self.assertAlmostEqual(bx1 - bx0, max(xs) - min(xs), places=6,
                               msg="the exporter's bounds record is stale for the vertices it wrote")
        self.assertAlmostEqual(bz1 - bz0, max(zs) - min(zs), places=6,
                               msg="the exporter's bounds record is stale for the vertices it wrote")

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
        self.assertEqual(len(drawn), len(self.asteroids) * collect.ASTEROID_ROCKS,
                         'an asteroid field was dropped from the frame')
        self.assertEqual(stats['omitted_planets'], 0,
                         'asteroid fields are still counted as omitted planets')

    def test_a_field_is_a_scatter_of_small_rocks_not_one_boulder(self):
        instances, _e, _s = self.collector(self.tables()).collect(self.state)
        index = {name: i for i, name in enumerate(self.tables().bindings)}[collect.ASTEROID_BINDING]
        by_field = {}
        for record in instances:
            if record[1] == index:
                by_field.setdefault(collect.rock_field_id(record[0]), []).append(record)
        self.assertEqual(len(by_field), len(self.asteroids))
        for asteroid in self.asteroids:
            rocks = by_field[asteroid.id & 0xFFFF]
            self.assertEqual(len(rocks), collect.ASTEROID_ROCKS)
            # The boulder regression: one instance scaled to the whole radius. Every rock must
            # be a small body, and the biggest must stay well under the field radius.
            sizes = sorted(record[11] * collect.ASTEROID_EXTENT for record in rocks)
            self.assertLess(sizes[-1], asteroid.radius * 0.10)
            self.assertGreater(sizes[0], asteroid.radius * 0.015)
            self.assertEqual(len({record[0] for record in rocks}), len(rocks),
                             'rock instance ids must be unique or the window glides them')

    def test_rocks_stay_inside_the_field_and_are_laid_out_deterministically(self):
        for asteroid in self.asteroids:
            first = collect.asteroid_rocks(asteroid)
            second = collect.asteroid_rocks(asteroid)
            self.assertEqual(first, second, 'the scatter must be stable across frames and reloads')
            for (x, _y, z), _yaw, scale, _shade in first:
                distance = ((x - asteroid.pos.x) ** 2 + (z - asteroid.pos.z) ** 2) ** 0.5
                self.assertLessEqual(distance + scale * collect.ASTEROID_EXTENT,
                                     asteroid.radius + 1e-6,
                                     'a rock reaches outside the radius the mining rule uses')

    def test_the_live_emitter_scatters_the_same_rocks_as_the_one_shot(self):
        # `collect()` is what tests and tools call; `collect_into()` is what every live session
        # calls (render_bridge/live.py) and it carries its own asteroid branch, so pinning only
        # the one-shot path would let the frame-rate emitter drift or drop the fields silently.
        tables = self.tables()
        collector = self.collector(tables)
        one_shot, _e, _s = collector.collect(self.state)
        buffer = bytearray(packed.frame_size(len(one_shot), 0))
        payload, stats = collector.collect_into(self.state, buffer, tick=0, frame_index=0)
        decoded = packed.unpack_frame(bytes(payload), tables)
        live = [record for record in decoded['instances']
                if record['binding'] == collect.ASTEROID_BINDING]
        index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
        one_shot_rocks = [record for record in one_shot if record[1] == index]
        # Byte for byte, not just the ids: the two branches pack their own matrix and tint, so an
        # id-only comparison would pass while the live frame drew the rocks in the wrong place,
        # the wrong colour or with the wrong flags.
        # Compare the bytes each rock actually occupies in the live payload, not a re-encode of
        # it: the two branches build their own matrix (column order, scale, translation) and tint,
        # so equal entity ids would survive a rock drawn somewhere else, in another colour, with
        # other flags. Doubles become float32 in the frame, which is why the comparison is over
        # the packed bytes rather than over the Python floats.
        raw = bytes(payload)
        start = packed.FRAME.size
        stride = packed.INSTANCE.size
        placed = [i for i, record in enumerate(decoded['instances'])
                  if record['binding'] == collect.ASTEROID_BINDING]
        live_bytes = b''.join(raw[start + i * stride:start + (i + 1) * stride] for i in placed)
        one_shot_bytes = b''.join(packed.INSTANCE.pack(*record) for record in one_shot_rocks)
        self.assertEqual(live_bytes, one_shot_bytes,
                         'the live emitter packs different instances than the one-shot collector')
        self.assertEqual(stats['instances'], len(one_shot))

    def test_the_scatter_is_worked_out_once_per_field_not_once_per_frame(self):
        # The layout depends only on the field, and a field is static, so a per-frame rebuild is
        # pure waste: 64 rocks per field over sixteen fields cost 2.76 ms of a 1.0 ms budget
        # before this cache existed. Misses prove every live field is laid out; hits prove the
        # frames after the first reuse it.
        tables = self.tables()
        collector = self.collector(tables)
        collect._scatter.cache_clear()
        buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, 0))
        for index in range(4):
            collector.collect_into(self.state, buffer, tick=index, frame_index=index)
        info = collect._scatter.cache_info()
        self.assertEqual(info.misses, len(self.asteroids),
                         'a field was laid out more than once, or not at all')
        self.assertGreaterEqual(info.hits, len(self.asteroids) * 3,
                                'later frames recomputed the scatter instead of reusing it')

    def test_the_densest_map_still_fits_a_frame(self):
        options = dict(default_skirmish_options(self.ds), map_id='skirmish05')
        state = GameManager.start_skirmish(build_skirmish_map(self.ds, options)).state
        tables = self.tables(state)
        instances, _e, _s = self.collector(tables).collect(state)
        fields = sum(1 for e in state.entities.values()
                     if e.alive and e.data_id == 'asteroid_field')
        self.assertEqual(fields, 16)
        self.assertLess(len(instances), packed.MAX_INSTANCES,
                        'the eight-player map must fit the frame budget')

    def test_a_map_without_fields_emits_none_and_still_draws_its_planets(self):
        # Disabling the fields must remove only the fields: the planet texture path they used
        # to be (wrongly) excluded from is what proves it. `stats['instances'] > 0` would pass
        # on the ships alone.
        planets = [e for e in self.state.entities.values()
                   if e.is_planet and e.data_id != 'asteroid_field' and e.alive]
        self.assertTrue(planets, 'fixture map has no ordinary planets to compare against')
        for entity in self.asteroids:
            entity.alive = False
        tables = self.tables()
        instances, _e, _stats = self.collector(tables).collect(self.state)
        index = {name: i for i, name in enumerate(tables.bindings)}[collect.ASTEROID_BINDING]
        self.assertEqual([i for i in instances if i[1] == index], [])
        drawn = {tables.bindings[record[1]] for record in instances}
        for planet in planets:
            expected = planet_bindings.binding_name(planet.data_id, planet.name_override or planet.data_id)
            self.assertIn(expected, drawn,
                          'an ordinary planet stopped resolving its texture binding')

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
            self.assertEqual(len(drawn), len(fields) * collect.ASTEROID_ROCKS,
                             f'{map_id} hides its asteroid fields')


if __name__ == '__main__':
    unittest.main()
