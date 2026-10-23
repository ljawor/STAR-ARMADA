"""The window is presented faster than the simulation steps; the world is carried forward to match.

`main.py` paces the loop at RENDER_RATE and the simulation at TICK_RATE. Between two ticks nothing
in the world has moved in the simulation, so a frame published `lead` seconds into the tick must
show the same hull a little further along its own velocity, or the extra frames are duplicates and
the picture still moves at TICK_RATE. These tests pin that arithmetic and pin the two rates apart.
"""
from __future__ import annotations

import pathlib
import unittest

from render_bridge import collect, packed

ROOT = pathlib.Path(__file__).resolve().parents[1]
TICK_DT = 1.0 / 30.0


class RenderLeadTests(unittest.TestCase):
    """Runs on the shared four-player fixture: real hulls with real bindings, no window."""

    def setUp(self):
        import game.core  # noqa: F401
        from game.graphics_benchmark import make_fixture
        from render import asset_selection
        from render.ship_sizes import ship_size
        from tools.render.dump_snapshot import _default_selection
        asset_selection.configure(_default_selection(), asset_root=ROOT,
                                  pack_root=ROOT / 'visual_packs')
        self.fixture = make_fixture('four-player-combat-v1')
        self.state, self.ds = self.fixture.manager.state, self.fixture.manager.ds
        _, _, seeded = collect.collect(
            self.state, self.ds, None, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.collector = collect.FrameCollector(
            self.ds, seeded['tables'], asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))
        # A hull that is drawn by this frame, with a known velocity: the subject of every test.
        from game.core.vectors import Vec3
        self.ship = next(e for e in self.state.entities.values()
                         if e.alive and e.is_ship and not e.jump_travelling)
        self.ship.pos = Vec3(120.0, 0.0, -80.0)
        self.ship.vel = Vec3(300.0, 0.0, -600.0)
        self.ship.yaw = 0.0

    def translation(self, lead):
        data, _ = self.collector.collect_into(self.state, self.buffer, tick=self.state.tick,
                                              frame_index=0, lead=lead)
        frame = packed.unpack_frame(data, self.collector.tables)
        row, = [r for r in frame['instances'] if r['entity_id'] == self.ship.id]
        self.assertFalse(row['flags'] & packed.FLAG_SURFACE_FRAME)
        return row['matrix'][9:12]

    # ------------------------------------------------------------------ hulls
    def test_no_lead_is_the_simulated_pose(self):
        self.assertEqual(self.translation(0.0), [120.0, 0.0, -80.0])

    def test_lead_carries_the_hull_along_its_velocity(self):
        lead = TICK_DT / 2
        x, y, z = self.translation(lead)
        self.assertAlmostEqual(x, 120.0 + 300.0 * lead, places=3)
        self.assertAlmostEqual(y, 0.0, places=3)
        self.assertAlmostEqual(z, -80.0 - 600.0 * lead, places=3)

    def test_lead_never_touches_the_simulation(self):
        before = self.state.to_dict(precise=True)
        self.translation(TICK_DT)
        self.assertEqual(before, self.state.to_dict(precise=True))

    def test_half_a_tick_is_half_the_distance(self):
        """Two frames inside one tick must not jump: the lead is linear in elapsed time."""
        rest = self.translation(0.0)
        quarter, half = self.translation(TICK_DT / 4), self.translation(TICK_DT / 2)
        for axis in range(3):
            self.assertAlmostEqual(half[axis] - rest[axis], 2.0 * (quarter[axis] - rest[axis]),
                                   places=3)

    # ------------------------------------------------------- things riding hulls
    def test_selection_ring_travels_with_the_hull(self):
        """A ring drawn at the tick pose while the hull is drawn ahead would visibly trail."""
        from render import primitive_batch
        lead = TICK_DT / 2
        lead_ring, = primitive_batch.selection_rings(
            self.state, {self.ship.id}, lambda e: 40.0, lead=lead)
        still_ring, = primitive_batch.selection_rings(self.state, {self.ship.id}, lambda e: 40.0)
        self.assertNotEqual(lead_ring, still_ring)
        self.assertAlmostEqual(lead_ring['centre'][0], 120.0 + 300.0 * lead, places=3)
        self.assertAlmostEqual(still_ring['centre'][0], 120.0, places=3)

    def test_bolt_travels_by_its_own_velocity(self):
        from types import SimpleNamespace
        from game.core.vectors import Vec3
        from render.emissive_batch import projectiles
        weapon = next(iter(__import__('render.shapes', fromlist=['BOLT_WEAPON_TYPES'])
                           .BOLT_WEAPON_TYPES))
        shot = SimpleNamespace(pos=Vec3(0.0, 0.0, 0.0), vel=Vec3(900.0, 0.0, 0.0),
                               size=1.0, color=(1.0, 0.6, 0.2, 1.0), weapon_id=weapon)
        extents = lambda _shape, _size, _ppw: (6.0, 2.0)  # noqa: E731
        lead = TICK_DT / 2
        with_lead, _ = projectiles([shot], lambda _w: weapon, extents, lead=lead)
        without, _ = projectiles([shot], lambda _w: weapon, extents)
        self.assertAlmostEqual(with_lead[0]['a'][0], 900.0 * lead, places=3)
        self.assertEqual(without[0]['a'][0], 0.0)

    # ------------------------------------------------------------------ rates
    def test_the_loop_paces_the_window_faster_than_the_simulation(self):
        """Both rates are constants in main.py; this fails if someone re-couples them."""
        source = (ROOT / 'main.py').read_text()
        self.assertIn('RENDER_RATE = 60', source)
        self.assertIn('TICK_DT = 1.0 / TICK_RATE', source)
        self.assertIn('pacer(RENDER_RATE)', source)
        self.assertNotIn('clock.tick(TICK_RATE)', source)


if __name__ == '__main__':
    unittest.main()
