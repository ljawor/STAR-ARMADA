"""W05 slice 3: the emissive batch (ARMEMIT01) — weapon fire, beams, glows, jump rings."""
from __future__ import annotations

import types
import unittest

from render import emissive_batch
from render_bridge import emissive as codec


class CodecTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        records = [codec.ribbon((0, 0, 0), (10, 0, 0), 1.5, (1.0, 0.4, 0.2, 0.8)),
                   codec.disc((1, 2, 3), 14.0, (0.2, 0.6, 1.0, 0.8)),
                   codec.ring((0, 0, 0), 160.0, 2.5, (0.5, 0.7, 1.0, 0.5)),
                   codec.bolt((5, 0, 0), (0, 0, 1), 9.0, 1.5, (1.0, 0.9, 0.4, 0.95))]
        encoded = codec.encode(records)
        self.assertEqual(len(encoded), codec.HEADER.size + 4 * codec.RECORD_BYTES)
        self.assertEqual(codec.encode(codec.decode(encoded)), encoded)

    def test_kinds_and_flags_survive(self):
        decoded = codec.decode(codec.encode([
            codec.ring((0, 0, 0), 10.0, 1.0, (1, 1, 1, 0.5), depth=True),
            codec.bolt((1, 1, 1), (0, 1, 0), 3.0, 2.0, (1, 1, 1, 1.0), square=True)]))
        self.assertEqual(decoded[0]['kind'], codec.RING)
        self.assertTrue(decoded[0]['flags'] & codec.FLAG_DEPTH)
        self.assertTrue(decoded[0]['flags'] & codec.FLAG_ADDITIVE)
        self.assertEqual(decoded[1]['shape'], codec.SHAPE_SQUARE)

    def test_refuses_damaged_batches(self):
        good = codec.encode([codec.disc((0, 0, 0), 5.0, (1, 1, 1, 1))])
        flipped = bytearray(good)
        flipped[-2] ^= 0xFF
        cases = {'crc': bytes(flipped), 'magic': b'ARMEMIT0' + good[8:],
                 'truncated': good[:-1], 'short': good[:9], 'trailing': good + b'\x00'}
        for name, payload in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(codec.EmissiveError):
                    codec.decode(payload)

    def test_ceiling(self):
        with self.assertRaises(codec.EmissiveError):
            codec.encode([codec.disc((0, 0, 0), 1.0, (1, 1, 1, 1))] * (codec.MAX_RECORDS + 1))


class BeamTests(unittest.TestCase):
    def effect(self, **kwargs):
        base = {'kind': 'beam', 't': 0.0, 'pos': (0, 0, 0), 'target_pos': (100, 0, 0),
                'color': [1.0, 0.5, 0.2]}
        base.update(kwargs)
        return base

    def test_a_beam_is_three_ribbons_and_two_glows(self):
        primitives, skipped = emissive_batch.beams([self.effect()])
        self.assertEqual(skipped, 0)
        ribbons = [p for p in primitives if p['kind'] == codec.RIBBON]
        discs = [p for p in primitives if p['kind'] == codec.DISC]
        self.assertEqual(len(ribbons), 3)
        self.assertEqual(len(discs), 2)              # muzzle and impact
        self.assertAlmostEqual(ribbons[0]['width'], 4.5)     # 9.0 / 2 sheath
        self.assertAlmostEqual(ribbons[1]['width'], 1.5)     # 3.0 / 2
        self.assertAlmostEqual(ribbons[2]['width'], 0.6)     # 1.2 / 2
        self.assertGreater(ribbons[1]['colour'][0], ribbons[0]['colour'][0])

    def test_alpha_fades_with_age_and_expires(self):
        fresh, _ = emissive_batch.beams([self.effect(t=0.0)])
        old, _ = emissive_batch.beams([self.effect(t=0.20)])
        self.assertGreater(fresh[0]['colour'][3], old[0]['colour'][3])
        expired, skipped = emissive_batch.beams([self.effect(t=0.30)])
        self.assertEqual(expired, [])
        self.assertEqual(skipped, 1)

    def test_resolved_contact_drops_the_impact_glow(self):
        primitives, _ = emissive_batch.beams([self.effect(resolved_contact=True)])
        self.assertEqual(len([p for p in primitives if p['kind'] == codec.DISC]), 1)


class RingTests(unittest.TestCase):
    def test_jump_ring_grows_as_it_fades(self):
        early = emissive_batch.rings([{'kind': 'jump_charge', 't': 0.0, 'pos': (0, 0, 0)}])[0]
        late = emissive_batch.rings([{'kind': 'jump_charge', 't': 0.8, 'pos': (0, 0, 0)}])[0]
        self.assertAlmostEqual(early['radius'], 60.0)       # 60 + 160 * (1 - 1)
        self.assertAlmostEqual(late['radius'], 188.0)       # 60 + 160 * (1 - 0.2)
        self.assertGreater(early['colour'][3], late['colour'][3])

    def test_expired_jump_ring_is_dropped(self):
        self.assertEqual(emissive_batch.rings([{'kind': 'jump_charge', 't': 1.4,
                                                'pos': (0, 0, 0)}]), [])


class BoltTests(unittest.TestCase):
    def shot(self, **kwargs):
        base = types.SimpleNamespace(pos=types.SimpleNamespace(x=10, y=0, z=0), size=1.0,
                                     vel=types.SimpleNamespace(to_tuple=lambda: (0.0, 0.0, 1.0)),
                                     color=(1.0, 0.9, 0.4), weapon_id='laser')
        for key, value in kwargs.items():
            setattr(base, key, value)
        return base

    def extents(self, shape, size, px_per_world):
        self.assertEqual(px_per_world, 1.0)      # pixels, by construction
        return (12.0, 2.0) if shape == 'bolt' else (8.0, 8.0)

    def test_bolt_carries_pixel_extents_and_heading(self):
        primitives, stats = emissive_batch.projectiles([self.shot()], lambda s: 'laser',
                                                        self.extents)
        self.assertEqual(len(primitives), 2)               # halo + core
        self.assertEqual(primitives[0]['kind'], codec.BOLT)
        self.assertEqual(primitives[0]['b'], (0.0, 0.0, 1.0))
        self.assertAlmostEqual(primitives[1]['radius'], 6.0)     # 12 px half-length
        self.assertAlmostEqual(primitives[1]['width'], 1.0)
        self.assertEqual(stats['drawn'], 1)

    def test_square_bolts_and_legacy_shots(self):
        primitives, stats = emissive_batch.projectiles(
            [self.shot(weapon_id='laser'), self.shot(weapon_id='torpedo'),
             self.shot(weapon_id='missile')],
            lambda s: 'legacy' if s == 'missile' else s, self.extents)
        self.assertEqual(stats['legacy'], 1)               # the legacy point sprite is not carried
        self.assertEqual(stats['squares'], 1)
        squares = [p for p in primitives if p['shape'] == codec.SHAPE_SQUARE]
        self.assertEqual(len(squares), 2)                  # halo + core for the torpedo only


class ExplosionTests(unittest.TestCase):
    """A blast crosses as parameters - position, size, age, seed - and the window rebuilds it.

    Sending the geometry would be ~950 triangles per blast per frame; the parameters are 44 bytes
    and the rebuild is the renderer's own formulas (`render_cpp/include/explosion.hpp`).
    """

    def blast(self, kind='explosion', t=0.35, size=120.0, seed=7):
        return {'kind': kind, 'pos': (10.0, 20.0, 30.0), 't': t, 'size': size, 'seed': seed}

    def test_a_live_blast_is_one_parameter_record(self):
        primitives, skipped = emissive_batch.explosions([self.blast()])
        self.assertEqual(len(primitives), 1)
        self.assertEqual(skipped, 0)
        record = primitives[0]
        self.assertEqual(record['kind'], codec.EXPLOSION)
        self.assertEqual(record['a'], (10.0, 20.0, 30.0))
        self.assertAlmostEqual(record['radius'], 120.0)      # the size the renderer derives from
        self.assertAlmostEqual(record['width'], 0.35)        # seconds, not a 0..1 fraction
        self.assertEqual(record['segments'], 7)              # the seed the shape comes from

    def test_the_same_seed_and_age_rebuild_the_same_blast(self):
        first, _ = emissive_batch.explosions([self.blast()])
        second, _ = emissive_batch.explosions([self.blast()])
        self.assertEqual(codec.encode(first), codec.encode(second))

    def test_a_blast_past_its_life_is_dropped(self):
        primitives, skipped = emissive_batch.explosions([self.blast(t=1.5)])
        self.assertEqual(primitives, [])
        self.assertEqual(skipped, 1)

    def test_small_blasts_are_half_size_on_their_own_clock(self):
        # renderer.py draws explosion_small as the same phenomenon at half size, 0.55x the clock,
        # with its own fade - not as a different orange blob.
        primitives, skipped = emissive_batch.explosions([self.blast('explosion_small', t=0.40)])
        self.assertEqual(skipped, 0)
        self.assertEqual(len(primitives), 1)
        record = primitives[0]
        self.assertAlmostEqual(record['radius'], 60.0)        # max(10, 120) * 0.5
        self.assertAlmostEqual(record['width'], 0.40 * 0.55)
        self.assertEqual(record['segments'], emissive_batch.EXPLOSION_SMALL_SEED)

    def test_a_faded_small_blast_is_dropped_before_the_big_lifetime(self):
        primitives, skipped = emissive_batch.explosions(
            [self.blast('explosion_small', t=emissive_batch.EXPLOSION_SMALL_LIFETIME)])
        self.assertEqual(primitives, [])
        self.assertEqual(skipped, 1)

    def test_blasts_ride_alongside_beams_and_bolts(self):
        primitives, stats = emissive_batch.build([self.blast()], [], lambda _w: None, None)
        self.assertEqual(stats['explosions'], 1)
        self.assertTrue(primitives)
        decoded = codec.decode(codec.encode(primitives))
        self.assertEqual(decoded[0]['kind'], codec.EXPLOSION)


class FakeUnit:
    """The smallest thing `shields()` needs: identity, place, shields and what kind of hull it is."""

    def __init__(self, uid=7, fraction=1.0, capacity=4.0,
                 station=False, ship=True, alive=True, planet=False, slot=None, radius=30.0):
        quadrants = (capacity * fraction,) * 4
        maxima = (capacity,) * 4
        self.id = uid
        self.alive = alive
        self.is_ship = ship
        self.is_squadron = False
        self.is_station = station
        self.is_planet = planet
        self.planet_building_slot = slot
        self.radius = radius
        self.pos = types.SimpleNamespace(x=1200.0, y=0.0, z=-800.0)
        self.shields = dict(zip(emissive_batch.QUADRANTS, quadrants))
        self._maxima = dict(zip(emissive_batch.QUADRANTS, maxima))

    def max_shield_total(self):
        return sum(self._maxima.values())


class ShieldShellTests(unittest.TestCase):
    """A bubble exists because Python says so; its tint is the strength ramp, not a hue guess."""

    def radius_of(self, unit):
        return 40.0

    def test_a_full_field_is_the_blue_stop_of_the_ramp(self):
        shells = emissive_batch.shields([FakeUnit()], self.radius_of)
        self.assertEqual(len(shells), 1)
        record = shells[0]
        self.assertEqual(record['kind'], codec.SHIELD)
        self.assertAlmostEqual(record['radius'], 40.0 * emissive_batch.SHIELD_SHIP_FACTOR)
        self.assertAlmostEqual(record['width'], 1.0)
        # blue: the nominal stop, with the ceiling alpha for a full field (the record stores
        # colour as bytes, so the ramp's floats arrive quantised)
        self.assertEqual(record['colour'][0], 77)      # 0.30 * 255
        self.assertEqual(record['colour'][1], 140)     # 0.55 * 255
        self.assertEqual(record['colour'][2], 255)
        self.assertAlmostEqual(record['colour'][3], emissive_batch.SHIELD_FADE[1] * 255, delta=1)

    def test_a_failing_field_is_red_and_still_visible(self):
        unit = FakeUnit(fraction=0.2)
        record = emissive_batch.shields([unit], self.radius_of)[0]
        self.assertGreater(record['colour'][0], record['colour'][2])       # red leads blue
        # the alpha floor exists so the most urgent quarter is never below the visibility line
        self.assertGreaterEqual(record['colour'][3], emissive_batch.SHIELD_FADE[0] * 255 - 1)

    def test_strength_is_quantised_into_eight_shells(self):
        # The renderer caches one display list per strength octant; two fractions inside one octant
        # must produce the same tint, and neighbours must not.
        low = FakeUnit(fraction=0.62)
        high = FakeUnit(fraction=0.74)
        a = emissive_batch.shields([low], self.radius_of)[0]['colour']
        b = emissive_batch.shields([high], self.radius_of)[0]['colour']
        self.assertNotEqual(a[:3], b[:3])

    def test_an_empty_field_raises_no_shell(self):
        unit = FakeUnit(fraction=0.0)
        self.assertEqual(emissive_batch.shields([unit], self.radius_of), [])

    def test_units_without_shields_raise_no_shell(self):
        unit = FakeUnit(fraction=1.0, capacity=0.0)
        self.assertEqual(emissive_batch.shields([unit], self.radius_of), [])

    def test_surface_hardware_is_protected_by_its_generator_not_a_bubble(self):
        # renderer.py skips planet_building_slot entities: an exterior bubble would advertise
        # protection for orbiting ships that the generator does not actually give.
        unit = FakeUnit(slot=3)
        self.assertEqual(emissive_batch.shields([unit], self.radius_of), [])

    def test_planets_never_get_a_ship_bubble(self):
        self.assertEqual(emissive_batch.shields([FakeUnit(planet=True)], self.radius_of), [])

    def test_stations_use_their_own_radius_not_the_hull_lookup(self):
        unit = FakeUnit(station=True, ship=False, radius=120.0)
        record = emissive_batch.shields([unit], self.radius_of)[0]
        self.assertAlmostEqual(record['radius'], 120.0 * emissive_batch.SHIELD_STATION_FACTOR)

    def test_an_unresolved_hull_radius_raises_no_shell(self):
        unit = FakeUnit()
        self.assertEqual(emissive_batch.shields([unit], lambda _u: 0.0), [])

    def test_shells_round_trip_through_the_bridge(self):
        shells = emissive_batch.shields([FakeUnit()], self.radius_of)
        decoded = codec.decode(codec.encode(shells))
        self.assertEqual(decoded[0]['kind'], codec.SHIELD)
        # the record carries the radius as a float32, so compare to its precision
        self.assertAlmostEqual(decoded[0]['radius'], shells[0]['radius'], places=3)
        self.assertEqual(decoded[0]['colour'], shells[0]['colour'])


if __name__ == '__main__':
    unittest.main()
