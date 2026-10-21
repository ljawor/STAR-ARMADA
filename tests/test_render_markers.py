"""W05 slice 2: the ownership cue batch (ARMARK01) and the rules behind it.

Two things are worth testing and they are different:

  * the codec round-trips byte for byte and refuses anything it cannot trust whole;
  * the *rules* match the Python renderer — a shielded unit hides its ring, a wounded hull turns
    the ring orange then red, a hostile gets a diamond. Those rules are what a player reads, so a
    silent drift here is a gameplay bug, not a cosmetic one.
"""
from __future__ import annotations

import types
import unittest

from render import primitive_batch
from render_bridge import markers as codec


class Entity:
    def __init__(self, entity_id, **kwargs):
        self.id = entity_id
        self.alive = kwargs.get('alive', True)
        self.pos = types.SimpleNamespace(x=kwargs.get('x', 0.0), y=kwargs.get('y', 0.0),
                                         z=kwargs.get('z', 0.0))
        self.owner = kwargs.get('owner', 0)
        self.radius = kwargs.get('radius', 40.0)
        self.is_ship = kwargs.get('is_ship', True)
        self.is_station = kwargs.get('is_station', False)
        self.is_squadron = kwargs.get('is_squadron', False)
        self.is_planet = kwargs.get('is_planet', False)
        self.colonized_by = kwargs.get('colonized_by', None)
        self.hull = kwargs.get('hull', 100.0)
        self.max_hull = kwargs.get('max_hull', 100.0)
        self.max_shield_total = kwargs.get('max_shield_total', lambda: 0.0)
        self.total_shield = kwargs.get('total_shield', lambda: 0.0)

    def hull_fraction(self):
        return self.hull / self.max_hull if self.max_hull else 0.0


class State:
    def __init__(self, entities, players=None):
        self.entities = {entity.id: entity for entity in entities}
        self.players = players or {0: types.SimpleNamespace(color=(0.2, 0.8, 0.3))}


def fake_players(colours):
    return {key: types.SimpleNamespace(color=value) for key, value in colours.items()}


class CodecTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        records = [
            codec.circle((10.0, 0.0, -5.0), 120.0, (0.2, 0.8, 0.3)),
            codec.marker((1.0, 2.0, 3.0), 40.0, (1.0, 0.3, 0.25), hostile=True),
            codec.circle((0.0, 0.0, 0.0), 700.0, (1.0, 1.0, 1.0), vertical=True, width=3.0,
                         segments=40, alpha=1.0, depth=True),
        ]
        encoded = codec.encode(records)
        self.assertEqual(len(encoded), codec.HEADER.size + 3 * codec.RECORD_BYTES)
        self.assertEqual(codec.encode(codec.decode(encoded)), encoded)

    def test_alpha_and_flags_survive(self):
        decoded = codec.decode(codec.encode([codec.circle((0, 0, 0), 5.0, (1.0, 0.5, 0.25),
                                                          alpha=0.4, depth=True)]))[0]
        self.assertEqual(decoded['colour'][3], 102)
        self.assertTrue(decoded['flags'] & codec.FLAG_DEPTH)
        self.assertTrue(decoded['flags'] & codec.FLAG_BLEND)

    def test_refuses_untrustworthy_batches(self):
        good = codec.encode([codec.circle((0, 0, 0), 5.0, (1, 1, 1))])
        flipped = bytearray(good)
        flipped[-1] ^= 0xFF
        cases = {
            'crc': bytes(flipped),
            'magic': b'ARMARK02' + good[8:],
            'truncated': good[:-1],
            'short': good[:10],
            'trailing': good + b'\x00',
            'reserved': good[:12] + b'\x01\x00\x00\x00' + good[16:],
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(codec.MarkerError):
                    codec.decode(payload)

    def test_refuses_unknown_kind_and_reserved_record(self):
        bad = bytearray(codec.encode([codec.circle((0, 0, 0), 5.0, (1, 1, 1))]))
        bad[codec.HEADER.size] = 9
        with self.assertRaises(codec.MarkerError):
            codec.decode(bytes(bad))
        reserved = bytearray(codec.encode([codec.circle((0, 0, 0), 5.0, (1, 1, 1))]))
        reserved[codec.HEADER.size + 30] = 1
        with self.assertRaises(codec.MarkerError):
            codec.decode(bytes(reserved))

    def test_ceiling(self):
        with self.assertRaises(codec.MarkerError):
            codec.encode([codec.circle((0, 0, 0), 1.0, (1, 1, 1))] * (codec.MAX_RECORDS + 1))


class SelectionRuleTests(unittest.TestCase):
    def scale(self, entity):
        return 100.0

    def test_ring_radius_is_the_drawn_scale(self):
        entity = Entity(1, radius=40.0)
        rings = primitive_batch.selection_rings(State([entity]), {1}, self.scale)
        self.assertEqual(len(rings), 1)
        self.assertAlmostEqual(rings[0]['size'], 54.0)      # 1.35 x the entity's world radius
        self.assertEqual(rings[0]['segments'], 28)
        self.assertFalse(rings[0]['flags'] & codec.FLAG_DEPTH)

    def test_a_shielded_unit_draws_no_ring(self):
        shielded = Entity(2, max_shield_total=lambda: 50.0, total_shield=lambda: 50.0)
        self.assertEqual(primitive_batch.selection_rings(State([shielded]), {2}, self.scale), [])

    def test_hull_severity_overrides_the_owner_colour(self):
        hurt = Entity(3, hull=20.0, max_hull=100.0)
        ring = primitive_batch.selection_rings(State([hurt]), {3}, self.scale)[0]
        self.assertEqual(ring['colour'][:3], (255, 64, 51))
        wounded = Entity(4, hull=50.0, max_hull=100.0)
        ring = primitive_batch.selection_rings(State([wounded]), {4}, self.scale)[0]
        self.assertEqual(ring['colour'][:3], (255, 204, 64))
        healthy = Entity(5)
        ring = primitive_batch.selection_rings(State([healthy]), {5}, self.scale)[0]
        self.assertEqual(ring['colour'][:3], (51, 204, 76))

    def test_stations_and_planets_get_an_upright_ring(self):
        station = Entity(6, is_ship=False, is_station=True)
        ring = primitive_batch.selection_rings(State([station]), {6}, self.scale)[0]
        self.assertEqual(ring['shape'], codec.SHAPE_XY)
        planet = Entity(7, is_ship=False, is_station=False, is_planet=True, radius=600.0)
        ring = primitive_batch.selection_rings(State([planet]), {7}, self.scale)[0]
        self.assertEqual(ring['shape'], codec.SHAPE_XY)
        self.assertAlmostEqual(ring['size'], 660.0)          # 1.1 x radius for a world

    def test_dead_and_surface_hardware_are_skipped(self):
        dead = Entity(8, alive=False)
        building = Entity(9)
        building.planet_building_slot = 0      # surface hardware selects its planet, not itself
        rings = primitive_batch.selection_rings(State([dead, building]), {8, 9}, self.scale)
        self.assertEqual(rings, [])


class PlanetRingTests(unittest.TestCase):
    def test_owned_world_gets_its_colonists_colour_and_depth(self):
        planet = Entity(10, is_ship=False, is_planet=True, radius=600.0, colonized_by=1)
        state = State([planet], fake_players({0: (0.2, 0.8, 0.3), 1: (0.9, 0.2, 0.2)}))
        rings = primitive_batch.planet_owner_rings(state)
        self.assertEqual(len(rings), 1)
        self.assertAlmostEqual(rings[0]['size'], 720.0)      # radius + 120
        self.assertEqual(rings[0]['segments'], 40)
        self.assertTrue(rings[0]['flags'] & codec.FLAG_DEPTH)
        self.assertEqual(rings[0]['colour'][:3], (230, 51, 51))

    def test_unowned_world_gets_nothing(self):
        planet = Entity(11, is_ship=False, is_planet=True, radius=600.0)
        self.assertEqual(primitive_batch.planet_owner_rings(State([planet])), [])


class MarkerRuleTests(unittest.TestCase):
    def test_hostile_gets_a_diamond_and_neutral_a_chevron(self):
        hostile = Entity(20, owner=2)
        neutral = Entity(21, owner=0)
        state = State([hostile, neutral], fake_players({0: (0.2, 0.8, 0.3)}))
        state.players[2] = types.SimpleNamespace(color=(0.9, 0.2, 0.2))
        markers = primitive_batch.ownership_markers(state, 0, {20, 21}, 'all', {0})
        by_id = {marker_id: m for marker_id, m in zip(sorted({20, 21}), markers)}
        self.assertEqual(by_id[20]['shape'], codec.SHAPE_DIAMOND)     # owner 2, not allied
        self.assertEqual(by_id[21]['shape'], codec.SHAPE_CHEVRON)     # own

    def test_own_marker_uses_the_owner_colour_lifted(self):
        own = Entity(22, owner=0)
        state = State([own])
        marker = primitive_batch.ownership_markers(state, 0, {22}, 'all', {0})[0]
        self.assertEqual(marker['shape'], codec.SHAPE_CHEVRON)
        self.assertGreater(marker['colour'][1], 204)          # lifted, not the raw 0.8

    def test_mode_off_and_hostiles_only(self):
        own = Entity(23, owner=0)
        hostile = Entity(24, owner=1)
        state = State([own, hostile], fake_players({0: (0.2, 0.8, 0.3), 1: (1.0, 0.2, 0.2)}))
        self.assertEqual(primitive_batch.ownership_markers(state, 0, {23, 24}, 'off', {0}), [])
        only = primitive_batch.ownership_markers(state, 0, {23, 24}, 'hostiles', {0})
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]['shape'], codec.SHAPE_DIAMOND)

    def test_marker_carries_the_hull_radius_not_pixels(self):
        own = Entity(25, radius=60.0)
        marker = primitive_batch.ownership_markers(State([own]), 0, {25}, 'all', {0},
                                                  scale_of=lambda entity: 12.5)[0]
        self.assertAlmostEqual(marker['size'], 12.5)


if __name__ == '__main__':
    unittest.main()
