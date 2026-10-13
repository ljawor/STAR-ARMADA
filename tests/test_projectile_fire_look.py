"""#90 — weapon fire reads as shaped bolts, not identical round specks.

The old `_draw_projectiles` gave every projectile the same treatment: an
additive radial glow plus a 3.2 px GL_POINTS core. A laser bolt, a turbolaser
bolt and a torpedo were therefore indistinguishable, which is what the issue
reports ("lasers should look like laser bolts, torpedoes like squares").

The shape choice and the quad proportions are pure functions precisely so they
can be pinned here without a GL context; the real rendered pixels are checked by
`tools/diag_weapon_fire_look.py`, which measures a per-family bounding box.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from render.renderer import (  # noqa: E402
    BOLT_WEAPON_TYPES, SQUARE_WEAPON_TYPES,
    projectile_extents, projectile_quad_offsets, projectile_shape,
    square_quad_offsets)

WEAPONS = os.path.join(ROOT, "assets", "data", "weapons", "weapons.json")
STATIONS = os.path.join(ROOT, "assets", "data", "stations", "stations.json")


def _weapons():
    with open(WEAPONS) as fh:
        data = json.load(fh)
    return data["weapons"] if "weapons" in data else data


def _bbox(offsets):
    us = [u for (u, _v) in offsets]
    vs = [v for (_u, v) in offsets]
    return max(us) - min(us), max(vs) - min(vs)


class WeaponFamilyClassificationTests(unittest.TestCase):
    """Every real weapon type must land in a deliberate family."""

    def test_laser_family_is_a_shaped_bolt(self):
        for name in ("laser", "point_defense", "turbolaser"):
            with self.subTest(weapon_type=name):
                self.assertEqual("bolt", projectile_shape(name))

    def test_torpedoes_and_missiles_are_squares(self):
        for name in ("torpedo", "missile"):
            with self.subTest(weapon_type=name):
                self.assertEqual("square", projectile_shape(name))

    def test_super_weapons_keep_the_old_treatment(self):
        # The brief: "super weapons like the biggest ships or the pulsar cannon
        # stay as they are", so beams (and ion/plasma/kinetic) are untouched.
        for name in ("beam", "ion", "plasma", "kinetic"):
            with self.subTest(weapon_type=name):
                self.assertEqual("legacy", projectile_shape(name))

    def test_unknown_or_missing_type_falls_back_to_legacy(self):
        for name in (None, "", "railgun"):
            with self.subTest(weapon_type=name):
                self.assertEqual("legacy", projectile_shape(name))

    def test_every_shipped_weapon_type_is_accounted_for(self):
        known = set(BOLT_WEAPON_TYPES) | set(SQUARE_WEAPON_TYPES)
        known |= {"ion", "plasma", "kinetic", "beam"}
        shipped = {w.get("type") for w in _weapons().values()}
        self.assertTrue(shipped, "weapons.json parsed empty")
        self.assertLessEqual(shipped - known, set(),
                             "new weapon type with no deliberate fire look")

    def test_shipped_families_pick_the_intended_shape(self):
        # Named weapons, not just "some weapon of each shape": with the type
        # lists narrowed, every family key still existed and a looser version of
        # this test stayed green (found by sabotage).
        weapons = _weapons()
        expected = {"laser_cannon": "bolt", "interceptor_cannon": "bolt",
                    "heavy_turbolaser": "bolt", "proton_torpedo": "square",
                    "missile_battery": "square", "planet_pulsar_beam": "legacy",
                    "beam_lance": "legacy"}
        for weapon_id, shape in expected.items():
            with self.subTest(weapon=weapon_id):
                self.assertIn(weapon_id, weapons, "catalogue renamed a weapon")
                self.assertEqual(shape, projectile_shape(weapons[weapon_id].get("type")))

    def test_every_shipped_family_has_at_least_one_member(self):
        seen = {}
        for wid, w in _weapons().items():
            seen.setdefault(projectile_shape(w.get("type")), []).append(wid)
        self.assertIn("bolt", seen, "no bolt weapon in the catalogue")
        self.assertIn("square", seen, "no square weapon in the catalogue")
        self.assertIn("legacy", seen, "no legacy weapon in the catalogue")


class ProjectileExtentTests(unittest.TestCase):
    """Bolts are long and thin; squares are square; neither stays a dot."""

    def test_bolt_is_elongated_in_world_units(self):
        length, width = projectile_extents("bolt", 1.6, 0.05)
        self.assertGreater(length, 3.0 * width,
                           "a bolt must read as a streak, not a blob")
        self.assertAlmostEqual(1.6 * 5.5, length)
        self.assertAlmostEqual(1.6 * 0.85, width)

    def test_square_has_equal_extents(self):
        length, width = projectile_extents("square", 2.4, 0.05)
        self.assertAlmostEqual(length, width)

    def test_screen_space_floor_keeps_distant_fire_visible(self):
        # 20 world units per pixel is roughly the far end of tactical zoom.
        #
        # Literal pixel floors, NOT the module constants they guard: a test that
        # reads the constant passes when the constant is gutted. Verified by
        # sabotage — lowering BOLT_MIN_PX/SQUARE_MIN_PX to zero left a
        # constant-based version of this test green.
        px_per_world = 20.0
        length, width = projectile_extents("bolt", 1.0, px_per_world)
        self.assertGreaterEqual(length / px_per_world, 3.0)
        self.assertGreaterEqual(width / px_per_world, 1.5)
        side, _other = projectile_extents("square", 1.0, px_per_world)
        self.assertGreaterEqual(side / px_per_world, 2.5)

    def test_distant_bolt_stays_elongated(self):
        length, width = projectile_extents("bolt", 1.0, 20.0)
        self.assertGreater(length, width, "distant bolts must not become dots")


class ProjectileQuadOrientationTests(unittest.TestCase):
    RIGHT = (1.0, 0.0, 0.0)
    UP = (0.0, 1.0, 0.0)

    def test_long_axis_follows_heading_along_screen_x(self):
        offsets = projectile_quad_offsets((100.0, 0.0, 0.0), self.RIGHT, self.UP,
                                          12.0, 3.0)
        du, dv = _bbox(offsets)
        self.assertAlmostEqual(12.0, du, places=5)
        self.assertAlmostEqual(3.0, dv, places=5)

    def test_long_axis_follows_heading_along_screen_y(self):
        # Deliberately tilted off the vertical: a straight (0, 1, 0) heading
        # projects to exactly the degenerate-heading fallback, so it cannot tell
        # "follows the heading" from "always uses the fallback". Sabotage found
        # that — forcing the fallback left the axis-aligned version of this test
        # green.
        offsets = projectile_quad_offsets((0.2, 1.0, 0.0), self.RIGHT, self.UP,
                                          12.0, 3.0)
        du, dv = _bbox(offsets)
        self.assertGreater(dv, 12.0)
        self.assertLess(dv, 13.5)
        self.assertGreater(du, 4.0)      # tilted, not the 3.0-wide fallback
        self.assertLess(du, 6.0)

    def test_diagonal_heading_rotates_the_quad_not_resizes_it(self):
        offsets = projectile_quad_offsets((100.0, 100.0, 0.0), self.RIGHT, self.UP,
                                          12.0, 3.0)
        du, dv = _bbox(offsets)
        self.assertGreater(du, 3.0)
        self.assertLess(du, 12.0)
        self.assertGreater(dv, 3.0)

    def test_heading_into_the_screen_falls_back_to_a_visible_streak(self):
        # No screen-space heading at all: collapsing here is what turns a
        # head-on volley into invisible dots.
        for vel in ((0.0, 0.0, 500.0), (0.0, 0.0, -500.0), (0.0, 0.0, 0.0)):
            with self.subTest(vel=vel):
                offsets = projectile_quad_offsets(vel, self.RIGHT, self.UP, 12.0, 3.0)
                du, dv = _bbox(offsets)
                self.assertAlmostEqual(12.0, dv, places=5)
                self.assertAlmostEqual(3.0, du, places=5)

    def test_quad_never_collapses_to_zero_area(self):
        for vel in ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0),
                    (0.3, 0.9, -0.2)):
            with self.subTest(vel=vel):
                offsets = projectile_quad_offsets(vel, self.RIGHT, self.UP, 9.0, 2.0)
                du, dv = _bbox(offsets)
                self.assertGreater(du * dv, 0.0)

    def test_orientation_is_independent_of_heading_magnitude(self):
        fast = projectile_quad_offsets((900.0, 0.0, 0.0), self.RIGHT, self.UP, 12.0, 3.0)
        slow = projectile_quad_offsets((0.9, 0.0, 0.0), self.RIGHT, self.UP, 12.0, 3.0)
        for a, b in zip(fast, slow):
            self.assertAlmostEqual(a[0], b[0], places=6)
            self.assertAlmostEqual(a[1], b[1], places=6)


class SquareProjectileTests(unittest.TestCase):
    """Torpedoes are squares — not diamonds (#90)."""

    def test_square_corners_are_axis_aligned(self):
        corners = square_quad_offsets(8.0)
        self.assertEqual(4, len(corners))
        for u, v in corners:
            self.assertAlmostEqual(abs(u), 4.0)
            self.assertAlmostEqual(abs(v), 4.0)

    def test_square_quad_fills_its_bounding_box(self):
        # A diamond would cover half of it; a square covers all of it.
        corners = square_quad_offsets(10.0)
        us = sorted({round(u, 6) for u, _v in corners})
        vs = sorted({round(v, 6) for _u, v in corners})
        self.assertEqual([-5.0, 5.0], us)
        self.assertEqual([-5.0, 5.0], vs)

    def test_heading_oriented_square_would_be_a_diamond(self):
        # Documents why the renderer must not orient squares by heading: the
        # same equal-sided quad rotated 45 degrees by a diagonal heading covers
        # only half its box, i.e. it reads as a diamond.
        oriented = projectile_quad_offsets((1.0, 1.0, 0.0), (1.0, 0.0, 0.0),
                                           (0.0, 1.0, 0.0), 10.0, 10.0)
        du, dv = _bbox(oriented)
        self.assertAlmostEqual(du, dv, places=5)
        self.assertGreater(du, 9.9)          # rotated: box grows
        self.assertLess(du, 14.5)
        axis_aligned = square_quad_offsets(10.0)
        self.assertNotAlmostEqual(_bbox(axis_aligned)[0], du, places=2)


class PulsarReachTests(unittest.TestCase):
    """#81 — the pulsar cannon out-ranged the map it defends."""

    OLD_RANGE = 8400.0

    def test_pulsar_beam_range_is_shortened(self):
        beam = _weapons()["planet_pulsar_beam"]
        self.assertAlmostEqual(6720.0, float(beam["range"]))
        self.assertLess(float(beam["range"]), self.OLD_RANGE)

    def test_pulsar_cannon_still_detects_what_it_can_shoot(self):
        # The 8400 pair was introduced together because detection gates every
        # launch; shortening one without the other would blind the cannon.
        with open(STATIONS) as fh:
            cannon = json.load(fh)["stations"]["planet_pulsar_cannon"]
        beam = float(_weapons()["planet_pulsar_beam"]["range"])
        self.assertGreaterEqual(float(cannon["sensor_range"]), beam)

    def test_pulsar_reach_is_now_below_the_kill_zone_it_used_to_cover(self):
        # Playable span on skirmish01 is ~24000 units, so the old 8400 reached a
        # third of the map from a single planetary battery.
        span = 24000.0
        self.assertLess(float(_weapons()["planet_pulsar_beam"]["range"]) / span, 0.30)


if __name__ == "__main__":
    unittest.main()
