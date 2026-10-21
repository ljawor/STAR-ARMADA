"""W02 packed-frame profile: round-trip, fail-closed rejection, producer equivalence."""
from __future__ import annotations

import struct
import unittest

from render_bridge import collect, packed


def tables():
    return packed.Tables.build(
        ['imperial:dagger', 'imperial:needle', 'rebel:fighter'], ['beam', 'muzzle', 'laser'])


def frame(instances=2, effects=2, *, tab=None):
    tab = tab or tables()
    rows = [packed.instance_record(entity_id=index + 1, binding_id=index,
                                   matrix=packed.matrix_from_pose((index * 10.0, 0.0, 5.0), 0.5, 2.0),
                                   tint=(1.0, 0.5, 0.25, 1.0), flags=index, hp=0.75, shield=0.5)
            for index in range(instances)]
    fx = [packed.effect_record(cls=packed.EFFECT_CLASS, kind_id=index,
                               position=(1.0, 2.0, 3.0), end_position=(4.0, 5.0, 6.0),
                               life=0.5, size=2.0, color=(0.1, 0.2, 0.3, 1.0))
          for index in range(effects)]
    buffer = bytearray(packed.frame_size(len(rows), len(fx)))
    raw = bytes(packed.pack_frame(buffer, tick=17, frame_index=3, tables=tab,
                                  instances=rows, effects=fx, flags=packed.FLAG_SELECTED))
    return tab, raw


class InstanceHealthTest(unittest.TestCase):
    """hp/shield on the wire must be the entity's real condition.

    Entity carries `hull`/`max_hull`; an earlier reader asked for `hp`/`max_hp` (which only
    subsystems have), so every instance in every frame carried hp = 0 and the disabled flag.
    Nothing in the picture showed it, so only an assertion on the decoded values catches it.
    """

    def setUp(self):
        import game.core  # noqa: F401
        from game.graphics_benchmark import make_fixture
        import pathlib
        from render import asset_selection
        from render.ship_sizes import ship_size
        from tools.render.dump_snapshot import _default_selection
        root = pathlib.Path(__file__).resolve().parents[1]
        asset_selection.configure(_default_selection(), asset_root=root,
                                  pack_root=root / 'visual_packs')
        self.fixture = make_fixture('four-player-combat-v1')
        self.state, self.ds = self.fixture.manager.state, self.fixture.manager.ds
        _, _, seeded = collect.collect(
            self.state, self.ds, None, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.collector = collect.FrameCollector(
            self.ds, seeded['tables'], asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))

    def decode(self):
        raw, _ = self.collector.collect_into(self.state, self.buffer,
                                             tick=self.state.tick, frame_index=0)
        return {record['entity_id']: record
                for record in packed.unpack_frame(bytes(raw), self.collector.tables)['instances']}

    def test_intact_hull_is_one_not_zero(self):
        decoded = self.decode()
        fractions = [record['hp'] for record in decoded.values()]
        self.assertTrue(fractions, 'the fixture produced no instances')
        self.assertGreater(min(fractions), 0.9, 'every instance reported a destroyed hull')

    def test_damage_and_disabled_flags_follow_the_hull(self):
        entity = next(e for e in self.state.entities.values()
                      if e.alive and e.is_ship and e.max_hull)
        original = entity.hull
        try:
            entity.hull = entity.max_hull * 0.4
            damaged = self.decode()[entity.id]
            self.assertAlmostEqual(damaged['hp'], 0.4, places=5)
            self.assertEqual(damaged['flags'], packed.FLAG_DAMAGED)
            entity.hull = entity.max_hull * 0.01
            disabled = self.decode()[entity.id]
            self.assertAlmostEqual(disabled['hp'], 0.01, places=5)
            self.assertEqual(disabled['flags'], packed.FLAG_DISABLED)
        finally:
            entity.hull = original


class PackedProfileTests(unittest.TestCase):
    def test_roundtrip_preserves_every_field(self):
        tab, raw = frame()
        decoded = packed.unpack_frame(raw, tab)
        self.assertEqual((decoded['tick'], decoded['frame_index'], decoded['flags']), (17, 3, 1))
        self.assertEqual(len(decoded['instances']), 2)
        first = decoded['instances'][0]
        self.assertEqual(first['entity_id'], 1)
        self.assertEqual(first['binding'], tab.bindings[0])
        self.assertAlmostEqual(first['hp'], 0.75, places=5)
        self.assertAlmostEqual(first['shield'], 0.5, places=5)
        self.assertAlmostEqual(first['matrix'][9], 0.0)      # translation x for index 0
        self.assertEqual(decoded['effects'][0]['kind'], tab.kinds[0])
        self.assertAlmostEqual(decoded['effects'][0]['position'][2], 3.0)

    def test_header_is_fixed_stride_and_little_endian(self):
        self.assertEqual(packed.FRAME.size, 48)
        self.assertEqual(packed.INSTANCE.size, 68)
        self.assertEqual(packed.EFFECT.size, 52)
        _, raw = frame()
        self.assertEqual(raw[:8], packed.MAGIC)
        self.assertEqual(struct.unpack_from('<H', raw, 8)[0], packed.VERSION)
        self.assertEqual(len(raw), packed.FRAME.size + 2 * packed.INSTANCE.size
                         + 2 * packed.EFFECT.size)

    def test_rejects_foreign_table_crc(self):
        tab, raw = frame()
        other = packed.Tables.build(['imperial:dagger'], ['beam'])
        with self.assertRaises(packed.FrameError):
            packed.unpack_frame(raw, other)

    def test_rejects_corrupted_payload(self):
        tab, raw = frame()
        corrupt = bytearray(raw)
        corrupt[-1] ^= 0xFF
        with self.assertRaises(packed.FrameError):
            packed.unpack_frame(bytes(corrupt), tab)

    def test_rejects_binding_outside_table(self):
        tab, raw = frame()
        corrupt = bytearray(raw)
        corrupt[packed.FRAME.size + 4] = 0xFF          # binding_id of instance 0
        corrupt[packed.FRAME.size + 5] = 0xFF
        with self.assertRaises(packed.FrameError):
            packed.unpack_frame(bytes(corrupt), tab)

    def test_rejects_trailing_bytes_and_truncation(self):
        tab, raw = frame()
        for candidate in (raw + b'\x00', raw[:-4]):
            with self.assertRaises(packed.FrameError):
                packed.unpack_frame(candidate, tab)

    def test_rejects_non_finite_input(self):
        with self.assertRaises(packed.FrameError):
            packed.instance_record(entity_id=1, binding_id=0,
                                   matrix=(0.0,) * 11 + (float('nan'),), tint=(1.0, 1.0, 1.0))
        with self.assertRaises(packed.FrameError):
            packed.effect_record(cls=packed.EFFECT_CLASS, kind_id=0,
                                 position=(float('inf'), 0.0, 0.0))

    def test_instance_matrix_is_a_uniformly_scaled_yaw_rotation(self):
        """The 12 floats are (c,0,-t)(0,s,0)(t,0,c)+translation, as the W01 layout reads them.

        Asserted as invariants rather than against one expected tuple, because they hold for
        every entity and would have caught a transposed or column-swapped matrix: the middle
        column must be the vertical axis, and the two horizontal columns must stay
        orthogonal with equal lengths.
        """
        import game.core  # noqa: F401
        from game.graphics_benchmark import make_fixture
        from render import asset_selection
        from render.ship_sizes import ship_size
        from tools.render.dump_snapshot import _default_selection
        import pathlib

        asset_selection.configure(_default_selection(),
                                  asset_root=pathlib.Path(__file__).resolve().parents[1],
                                  pack_root=pathlib.Path(__file__).resolve().parents[1] / 'visual_packs')
        fixture = make_fixture('four-player-combat-v1')
        state, ds = fixture.manager.state, fixture.manager.ds
        _, _, stats = collect.collect(
            state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        collector = collect.FrameCollector(
            ds, stats['tables'], asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        buffer = bytearray(packed.frame_size(1024, 0))
        raw, counts = collector.collect_into(state, buffer, tick=state.tick, frame_index=0)
        decoded = packed.unpack_frame(bytes(raw), collector.tables)
        entities = {entity.id: entity for entity in state.entities.values()}
        turned = 0
        for instance in decoded['instances']:
            m = instance['matrix']
            left, up, right = m[0:3], m[3:6], m[6:9]
            self.assertEqual((up[0], up[2]), (0.0, 0.0), 'middle column is not the vertical axis')
            self.assertGreater(up[1], 0.0, 'vertical axis collapsed')
            self.assertAlmostEqual(left[0], right[2], places=5)     # c == c
            self.assertAlmostEqual(left[2], -right[0], places=5)    # -t == -(t)
            entity = entities[instance['entity_id']]
            self.assertAlmostEqual(m[9], entity.pos.x, places=2)
            self.assertAlmostEqual(m[10], entity.pos.y, places=2)
            self.assertAlmostEqual(m[11], entity.pos.z, places=2)
            if abs(entity.yaw) > 0.3:
                turned += 1
        self.assertGreater(turned, 0, 'fixture carries no rotated entity; the check proved nothing')

    def test_tables_are_sorted_and_crc_is_stable(self):
        flipped = packed.Tables.build(['b', 'a'], ['y', 'x'])
        sorted_same = packed.Tables.build(['a', 'b'], ['x', 'y'])
        self.assertEqual(flipped.bindings, sorted_same.bindings)
        self.assertEqual(flipped.crc32, sorted_same.crc32)

    def test_producer_path_matches_validated_builder(self):
        """`collect_into` (frame-rate path) must agree with the validating builder."""
        import game.core  # noqa: F401  core/systems import cycle, per the project skill
        from game.benchmark import state_hash
        from game.graphics_benchmark import make_fixture
        from render import asset_selection
        from render.ship_sizes import ship_size
        from tools.render.dump_snapshot import _default_selection

        asset_selection.configure(_default_selection(), asset_root=__import__('pathlib').Path(
            __file__).resolve().parents[1], pack_root=__import__('pathlib').Path(
            __file__).resolve().parents[1] / 'visual_packs')
        fixture = make_fixture('four-player-combat-v1')
        state, ds = fixture.manager.state, fixture.manager.ds
        before = state_hash(state)

        _, _, stats = collect.collect(
            state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        collector = collect.FrameCollector(
            ds, stats['tables'], asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)

        records, effects, _ = collector.collect(state)
        buffer = bytearray(packed.frame_size(len(records), len(effects)))
        raw, counts = collector.collect_into(state, buffer, tick=state.tick, frame_index=0)
        decoded = packed.unpack_frame(bytes(raw), collector.tables)

        self.assertEqual(counts['instances'], len(records))
        self.assertEqual(counts['effects'], len(effects))
        self.assertEqual(len(decoded['instances']), len(records))
        for expected, actual in zip(records, decoded['instances']):
            self.assertEqual(expected[0], actual['entity_id'])
            self.assertEqual(collector.tables.bindings[expected[1]], actual['binding'])
            self.assertAlmostEqual(expected[3] / 255, actual['tint'][0], places=2)
            for left, right in zip(expected[7:19], actual['matrix']):
                # The wire profile stores float32, so compare as it is transmitted.
                self.assertLessEqual(abs(left - right), max(1.0, abs(left)) * 2.0 ** -20)
        self.assertEqual(state_hash(state), before, 'producer mutated simulation state')


if __name__ == '__main__':
    unittest.main()
