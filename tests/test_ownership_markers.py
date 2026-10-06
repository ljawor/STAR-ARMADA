"""Ownership legibility: marker shape/colour/size and hull-shade rules."""
from __future__ import annotations

import unittest

from render import markers as mk


class TestRelation(unittest.TestCase):
    def test_own_allies_enemies_and_neutral_are_distinguished(self):
        allies = {0, 2}
        self.assertEqual(mk.relation_of(0, 0, allies), "own")
        self.assertEqual(mk.relation_of(0, 2, allies), "ally")
        self.assertEqual(mk.relation_of(0, 1, allies), "enemy")
        self.assertEqual(mk.relation_of(0, -1, allies), "neutral")

    def test_alliance_is_symmetric_for_any_local_player(self):
        # Player 2 sees the same coalition as player 0.
        allies = {0, 2}
        self.assertEqual(mk.relation_of(2, 0, allies), "ally")
        self.assertEqual(mk.relation_of(2, 2, allies), "own")
        self.assertEqual(mk.relation_of(2, 3, allies), "enemy")

    def test_local_player_outside_the_alliance_never_reports_ally(self):
        # A third player is not in {0,2}: nobody in that set is their ally.
        self.assertEqual(mk.relation_of(5, 0, {0, 2}), "enemy")
        self.assertEqual(mk.relation_of(5, 5, {0, 2}), "own")

    def test_empty_and_none_inputs_do_not_crash(self):
        self.assertEqual(mk.relation_of(0, 1, ()), "enemy")
        self.assertEqual(mk.relation_of(0, None, {0}), "neutral")
        self.assertEqual(mk.relation_of(0, 0, None), "own")


class TestShapeIsThePrimaryCue(unittest.TestCase):
    def test_own_ally_and_hostile_use_different_shapes(self):
        self.assertEqual(mk.shape_for("own"), mk.CHEVRON)
        self.assertEqual(mk.shape_for("ally"), mk.CHEVRON)
        self.assertEqual(mk.shape_for("enemy"), mk.DIAMOND)

    def test_shapes_are_valid_polygons_with_negative_y_apex(self):
        for poly in (mk.CHEVRON, mk.DIAMOND):
            self.assertGreaterEqual(len(poly), 3)
            ys = [p[1] for p in poly]
            # Apex points "down" in screen space toward the labelled hull.
            self.assertAlmostEqual(min(ys), -1.0, places=6)
            self.assertTrue(all(abs(x) <= 1.0 for x, _ in poly))

    def test_hostile_colour_is_a_single_fixed_threat_colour(self):
        # Not the enemy player's own colour: two enemies must look alike.
        a = mk.marker_color("enemy", (0.1, 0.9, 0.2))
        b = mk.marker_color("enemy", (0.9, 0.1, 0.9))
        self.assertEqual(a, b)
        self.assertEqual(a, mk.HOSTILE_COLOR)

    def test_own_colour_is_lifted_above_the_hull_tint(self):
        col = (0.15, 0.35, 0.95)
        lifted = mk.marker_color("own", col)
        self.assertTrue(all(l >= h for l, h in zip(lifted, col)))
        self.assertTrue(all(0.0 <= v <= 1.0 for v in lifted))

    def test_marker_colour_tolerates_bad_input(self):
        self.assertEqual(mk.marker_color("own", None), mk.NEUTRAL_COLOR)
        self.assertEqual(mk.marker_color("own", (1, 2)), mk.NEUTRAL_COLOR)


class TestScreenClamp(unittest.TestCase):
    def test_marker_never_shrinks_below_the_readable_floor(self):
        # The distant hull this exists for: a small corvette never drops under
        # the readable floor, and a zero/unknown footprint sits exactly on it.
        self.assertGreaterEqual(mk.marker_px(2.0), mk.MARKER_MIN_PX)
        self.assertLess(mk.marker_px(2.0), mk.MARKER_MIN_PX + 0.5)
        self.assertAlmostEqual(mk.marker_px(0.0), mk.MARKER_MIN_PX, places=6)
        self.assertAlmostEqual(mk.marker_px(None), mk.MARKER_MIN_PX, places=6)

    def test_marker_never_grows_past_the_cap(self):
        self.assertAlmostEqual(mk.marker_px(200.0), mk.MARKER_MAX_PX, places=6)

    def test_world_radius_matches_the_pixel_footprint(self):
        # 9px at 3 px/world => 1.5 world units half-extent.
        self.assertAlmostEqual(mk.world_radius(9.0, 3.0), 1.5, places=6)
        self.assertEqual(mk.world_radius(9.0, 0.0), 0.0)


class TestMode(unittest.TestCase):
    def test_default_and_invalid_values_fall_back_to_all(self):
        self.assertEqual(mk.marker_mode("all"), "all")
        self.assertEqual(mk.marker_mode("HOSTILES "), "hostiles")
        self.assertEqual(mk.marker_mode("off"), "off")
        self.assertEqual(mk.marker_mode(None), "all")
        self.assertEqual(mk.marker_mode("banana"), "all")
        self.assertEqual(mk.marker_mode(7), "all")

    def test_mode_cycles_through_all_three_states(self):
        self.assertEqual(mk.next_mode("all"), "hostiles")
        self.assertEqual(mk.next_mode("hostiles"), "off")
        self.assertEqual(mk.next_mode("off"), "all")

    def test_off_hides_everything_and_hostiles_hides_own(self):
        # The point of the mode: no enemy is ever invisible in any mode.
        self.assertFalse(mk.shows_marker("own", "off"))
        self.assertFalse(mk.shows_marker("enemy", "off"))
        self.assertTrue(mk.shows_marker("enemy", "hostiles"))
        # ...while friendly markers drop out so the own fleet stays uncluttered
        self.assertFalse(mk.shows_marker("ally", "hostiles"))
        self.assertTrue(mk.shows_marker("ally", "all"))

    def test_all_shows_own_and_enemy(self):
        for rel in ("own", "ally", "enemy"):
            self.assertTrue(mk.shows_marker(rel, "all"))


class TestHullShade(unittest.TestCase):
    def test_own_hulls_are_lifted_and_enemy_hulls_darkened(self):
        col = (0.30, 0.45, 0.90)
        own = mk.hull_shade(col, "own")
        foe = mk.hull_shade(col, "enemy")
        self.assertTrue(all(o > c for o, c in zip(own, col)))
        self.assertTrue(all(f < c for f, c in zip(foe, col)))

    def test_shades_stay_in_range_and_keep_hue_opposition(self):
        for rel in ("own", "ally", "enemy"):
            out = mk.hull_shade((0.30, 0.45, 0.90), rel)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in out))
        # own remains blue-dominant, enemy remains recognisable but dimmer
        own = mk.hull_shade((0.30, 0.45, 0.90), "own")
        self.assertGreater(own[2], own[0])

    def test_neutral_and_unknown_owners_are_left_alone(self):
        col = (0.30, 0.45, 0.90)
        self.assertEqual(mk.hull_shade(col, "neutral"), col)
        self.assertEqual(mk.hull_shade(None, "own"), None)


if __name__ == "__main__":
    unittest.main()
