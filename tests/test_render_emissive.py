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


if __name__ == '__main__':
    unittest.main()
