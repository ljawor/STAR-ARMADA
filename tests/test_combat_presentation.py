"""Native combat presentation: world dimensions, real flight direction, no simulation writes."""
import copy
import types
import unittest
from game.core.vectors import Vec3
from render import emissive_batch
from render_bridge import emissive as codec


class ProjectilePresentationTests(unittest.TestCase):
    def shot(self, weapon='laser', size=1.0, velocity=(900., 40., -300.)):
        return types.SimpleNamespace(weapon_id=weapon, size=size,
            pos=Vec3(10., 20., 30.), vel=Vec3(*velocity), color=(.2, .7, 1., 1.))

    def records(self, shots, lead=0.):
        return emissive_batch.projectiles(shots, lambda w: w,
            lambda *args: self.fail('Native flight must not consult screen-pixel extents'), lead=lead)

    def test_all_three_weapon_families_leave_the_pixel_billboard_path(self):
        # Fail on a value, not a missing new codec symbol, against the old producer.
        for weapon in ('laser', 'turbolaser', 'point_defense', 'missile', 'torpedo'):
            with self.subTest(weapon=weapon):
                records, stats = self.records([self.shot(weapon)])
                self.assertEqual(len(records), 1)
                self.assertNotEqual(records[0]['kind'], codec.BOLT)
                self.assertEqual(records[0]['flags'], codec.FLAG_ADDITIVE | codec.FLAG_DEPTH)

    def test_length_is_not_derived_from_viewport_or_zoom(self):
        records, _ = self.records([self.shot(size=1.), self.shot(size=2.)])
        self.assertEqual(records[1]['radius'], records[0]['radius'] * 2.)
        self.assertEqual(records[1]['width'], records[0]['width'] * 2.)

    def test_head_is_real_position_direction_is_full_world_velocity(self):
        shot = self.shot()
        records, _ = self.records([shot], lead=1/60)
        record = records[0]
        self.assertEqual(record['a'], tuple(a + b/60 for a,b in zip((10.,20.,30.), (900.,40.,-300.))))
        self.assertEqual(record['b'], (900.,40.,-300.))

    def test_guided_and_unguided_have_distinct_silhouettes(self):
        records, stats = self.records([self.shot(w) for w in ('laser','missile','torpedo')])
        self.assertEqual(len({p['shape'] for p in records}), 3)
        self.assertEqual(stats['drawn'], 3)
        self.assertEqual(stats['squares'], 0)

    def test_codec_roundtrip_carries_world_units_and_subtype(self):
        records, _ = self.records([self.shot(w) for w in ('laser','missile','torpedo')])
        decoded = codec.decode(codec.encode(records))
        self.assertEqual([p['shape'] for p in decoded], [p['shape'] for p in records])
        self.assertEqual([p['radius'] for p in decoded], [p['radius'] for p in records])

    def test_presentation_never_moves_or_reaims_the_simulated_shot(self):
        shots = [self.shot(w) for w in ('laser','missile','torpedo')]
        before = copy.deepcopy([vars(p) for p in shots])
        self.records(shots, lead=.02)
        self.assertEqual([vars(p) for p in shots], before)

    def test_codec_refuses_malformed_flights_on_both_sides(self):
        import math
        import zlib
        record = codec.flight((1.,2.,3.), (900.,0.,0.), 12., .4, (1.,.5,.2,1.))
        bad_records = []
        for key, value in [('shape', 3), ('flags', 2), ('segments', 1), ('radius', 0.),
                           ('width', math.inf), ('a', (math.nan,0.,0.)),
                           ('b', (0.,0.,0.)), ('b', (1e9,0.,0.))]:
            bad_records.append(dict(record, **{key:value}))
        for bad in bad_records:
            with self.subTest(record=bad):
                with self.assertRaises(codec.EmissiveError):
                    codec.encode([bad])
                body = codec.RECORD.pack(bad['kind'], bad['shape'], bad['flags'],
                    *bad['colour'], *bad['a'], *bad['b'], bad['radius'], bad['width'],
                    bad['segments'], 0)
                data = codec.HEADER.pack(codec.MAGIC, codec.VERSION, 1, 0, zlib.crc32(body)) + body
                with self.assertRaises(codec.EmissiveError):
                    codec.decode(data)

    def test_stationary_malformed_direction_is_safe_not_an_invented_world_shot(self):
        records, stats = self.records([self.shot(velocity=(0.,0.,0.))])
        self.assertEqual(records, [])
        self.assertEqual(stats['legacy'], 1)


if __name__ == '__main__':
    unittest.main()
