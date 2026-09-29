"""A station may only be sited near the constructor that builds it.

Reported in play: an engineer corvette could be ordered to build a station
anywhere on the map and would then fly over and build it. There was no
proximity rule at all — `check_site` validated map bounds, spacing from planets
and other stations, `requires_range`, and the builder's build list, but never
the distance from the builder.

The rule is enforced at ORDER time (`start_station`) rather than inside
`check_site`, because the AI's site finders use `check_site` to pick a site
before the constructor has travelled there — folding proximity in would make
the energy relay (which lives out by a gas giant, ~7200u from home) unfindable.
"""
import unittest

from helpers import make_game
from game.core.vectors import Vec3


def _builder(st):
    """One construction hull owned by P0 that is allowed to build stations."""
    for e in st.entities.values():
        if not (e.alive and e.owner == 0 and e.is_construction):
            continue
        sd = st._construction_system.ds.ships.get(e.data_id)
        if sd is not None and sd.can_build_stations:
            return e
    raise AssertionError("no station-capable builder in the fixture")


class TestStationBuildRange(unittest.TestCase):

    def test_default_range_is_configured(self):
        gm = make_game(ai=False)
        cs = gm.state._construction_system
        self.assertGreater(cs.build_range(), 0.0)
        # and it is the value from game_rules.json, not a code default
        self.assertEqual(cs.build_range(),
                         gm.ds.rules["economy"]["station_build_range"])

    def test_build_refused_beyond_range(self):
        gm = make_game(ai=False)
        st = gm.state
        b = _builder(st)
        p = st.players[0]
        p.credits = 999999
        p.materials = 999999
        far = Vec3(b.pos.x + gm.state._construction_system.build_range() * 4,
                   0.0, b.pos.z)
        far, d, lim = gm.state._construction_system.too_far_to_build(far, b)
        self.assertTrue(far, "a site 4x the range away must be out of range")
        ok = gm.construction.start_station(
            b.id, "shipyard", Vec3(b.pos.x + lim * 4, 0.0, b.pos.z), 0)
        self.assertFalse(ok, "the sim accepted a build far outside range")
        self.assertFalse(b.build_queue, "a refused build must not enter the queue")

    def test_build_allowed_within_range(self):
        gm = make_game(ai=False)
        st = gm.state
        b = _builder(st)
        p = st.players[0]
        p.credits = 999999
        p.materials = 999999
        lim = gm.state._construction_system.build_range()
        pos = Vec3(b.pos.x + lim * 0.5, 0.0, b.pos.z)
        far, _d, _l = gm.state._construction_system.too_far_to_build(pos, b)
        self.assertFalse(far)
        self.assertTrue(gm.construction.start_station(b.id, "shipyard", pos, 0))

    def test_boundary_is_inclusive_at_the_limit(self):
        """Exactly at the limit is legal; a hair beyond is not."""
        gm = make_game(ai=False)
        st = gm.state
        b = _builder(st)
        cs = st._construction_system
        lim = cs.build_range()
        at = Vec3(b.pos.x + lim, 0.0, b.pos.z)
        over = Vec3(b.pos.x + lim + 1.0, 0.0, b.pos.z)
        self.assertFalse(cs.too_far_to_build(at, b)[0])
        self.assertTrue(cs.too_far_to_build(over, b)[0])

    def test_range_is_measured_from_the_builder_not_the_map_centre(self):
        """The verdict follows the builder, not a global constant.

        The fixture ships one station-capable constructor, so the second
        "builder" is simulated by moving the same ship: the identical site is
        legal from one position and illegal from another.
        """
        gm = make_game(ai=False)
        st = gm.state
        cs = st._construction_system
        lim = cs.build_range()
        a = _builder(st)
        home_pos = a.pos.copy()
        site = Vec3(home_pos.x + lim * 0.5, 0.0, home_pos.z)
        self.assertFalse(cs.too_far_to_build(site, a)[0])
        # same site, builder now far away
        a.pos = Vec3(site.x + lim * 3, 0.0, site.z)
        self.assertTrue(cs.too_far_to_build(site, a)[0],
                        "range must follow the builder, not be a global constant")
        # and back again
        a.pos = home_pos
        self.assertFalse(cs.too_far_to_build(site, a)[0])

    def test_moving_the_builder_into_range_unblocks_the_build(self):
        """The intended play: fly the constructor over, then place it."""
        gm = make_game(ai=False)
        st = gm.state
        b = _builder(st)
        p = st.players[0]
        p.credits = 999999
        p.materials = 999999
        cs = st._construction_system
        site = Vec3(b.pos.x + cs.build_range() * 4, 0.0, b.pos.z)
        self.assertFalse(gm.construction.start_station(b.id, "shipyard", site, 0))
        # walk there
        b.pos = site.copy()
        self.assertTrue(gm.construction.start_station(b.id, "shipyard", site, 0),
                        "arriving at the site must make the build legal")


class TestAIBuildsWithinRange(unittest.TestCase):
    """The AI must respect the same rule, by walking its constructors over."""

    def test_ai_reaches_a_site_far_beyond_its_build_range(self):
        """End-to-end proof of the walk-into-range: the AI's energy relay sits
        ~7200u from home, far outside station_build_range, so it can only exist
        if a constructor genuinely travelled there first."""
        gm = make_game(ai=True)
        st = gm.state
        ai_id = next(pid for pid, p in st.players.items() if p.is_ai)
        cs = st._construction_system

        for _ in range(30 * 60 * 20):
            gm.step(1 / 30)

        relays = [e for e in st.entities.values()
                  if e.alive and e.is_station and e.data_id == "energy_relay"
                  and e.owner == ai_id]
        self.assertTrue(relays, "the AI never reached its far relay site")
        relay = relays[0]
        gas = min((e for e in st.entities.values()
                   if e.alive and e.is_planet and e.data_id == "gas_giant"),
                  key=lambda g: g.pos.dist(relay.pos), default=None)
        self.assertIsNotNone(gas, "no gas giant near the AI relay")
        # the relay really is far outside a single build range, so it can only
        # have been built by a constructor that walked to it
        self.assertGreater(
            relay.pos.dist(gas.pos),
            cs.build_range(),
            "relay is within build range — this test is not proving the walk")
        # it is a legal relay site: within the gas giant's relay band
        from game.systems.construction import _body_clearance
        band = cs.ds.resolve_station("energy_relay").requires_range["gas_giant"]
        self.assertLessEqual(
            relay.pos.dist(gas.pos),
            _body_clearance(gas, relay.radius) + band,
            "the built relay sits outside the gas giant's relay band")

        # no walk left stuck
        ai = gm.ai.ais[ai_id]
        self.assertFalse(ai._pending_site,
                         f"AI left a constructor stuck walking: {ai._pending_site}")

    def test_every_ai_build_was_ordered_from_within_range(self):
        """Over a full AI game, every ACCEPTED build must have been ordered with
        the constructor inside station_build_range.

        Wraps `start_station` so each accepted order records the real
        builder-to-site distance. This is the end-to-end version of the rule:
        with the proximity check removed, the recorded distances blow past the
        limit (see tools/reverse_planet_economy.py D6).
        """
        gm = make_game(ai=True)
        st = gm.state
        cs = st._construction_system
        lim = cs.build_range()

        accepted = []
        real = cs.start_station

        def spy(builder_id, station_id, pos, player_id):
            b = st.entity(builder_id)
            ok = real(builder_id, station_id, pos, player_id)
            if ok and b is not None:
                accepted.append(b.pos.dist(pos))
            return ok

        cs.start_station = spy
        try:
            for _ in range(30 * 60 * 14):
                gm.step(1 / 30)
        finally:
            cs.start_station = real

        self.assertGreater(len(accepted), 0, "the AI accepted no builds at all")
        self.assertLessEqual(
            max(accepted), lim + 1e-6,
            f"a build was ordered from {max(accepted):.0f}u away (limit {lim:.0f}u)")

    def test_ai_site_finders_validate_against_check_site(self):
        """Site finders must keep returning check_site-legal ground.

        check_site intentionally does NOT include the range rule — the finder
        picks the site before the constructor travels. If a finder ever returned
        illegal ground, the AI would walk over and still be refused.
        """
        gm = make_game(ai=True)
        st = gm.state
        ai_id = next(pid for pid, p in st.players.items() if p.is_ai)
        gm.ai.ensure()
        ai = gm.ai.ais[ai_id]
        home = ai.home_station()
        builder = next((e for e in ai.my_units()
                        if e.is_construction and not e.is_planet), None)
        if home is None or builder is None:
            self.skipTest("fixture has no AI home/builder")
        cs = st._construction_system
        for kind, dist in (("shipyard", 700), ("trade_station", 900)):
            site = ai._find_station_site(kind, dist, home, builder)
            if site is None:
                continue
            ok, reason = cs.check_site(kind, site, builder)
            self.assertTrue(ok, f"{kind} site rejected: {reason}")

    def test_ai_walks_the_constructor_into_range(self):
        """A far site must become a MOVE order, not a dropped build."""
        gm = make_game(ai=True)
        st = gm.state
        ai_id = next(pid for pid, p in st.players.items() if p.is_ai)
        gm.ai.ensure()
        ai = gm.ai.ais[ai_id]
        builder = next((e for e in ai.my_units()
                        if e.is_construction and not e.is_planet), None)
        if builder is None:
            self.skipTest("fixture has no AI constructor")
        cs = st._construction_system
        far_site = Vec3(builder.pos.x + cs.build_range() * 6, 0.0,
                        builder.pos.z)
        ai._pending_site.clear()
        ai._queue_build(builder, "shipyard", far_site)
        self.assertIn(builder.id, ai._pending_site,
                      "a far site must be remembered as pending")
        self.assertFalse(builder.build_queue, "nothing may build yet")

        # it is heading there (queue_command is deferred, so run one tick)
        gm.step(1 / 30)
        self.assertEqual(builder.order_type, "move")
        self.assertIsNotNone(builder.order_target_pos)
        self.assertAlmostEqual(builder.order_target_pos.x, far_site.x, places=3)

        # and once it arrives (within range), the build is issued
        builder.pos = Vec3(far_site.x - cs.build_range() * 0.5, 0.0, far_site.z)
        builder.order_type = "idle"
        ai._flush_pending_sites()
        gm.step(1 / 30)
        self.assertNotIn(builder.id, ai._pending_site,
                         "arriving in range must release the pending site")
        self.assertTrue(builder.build_queue,
                        "the station must be queued once the builder is in range")


if __name__ == "__main__":
    unittest.main(verbosity=2)
