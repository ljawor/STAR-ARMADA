"""Planet economy + energy: a colonized world must pay, and EN must be earnable.

Reported in play: "How do I get EN? At some point my EN is 10 and I can't build
anymore." Investigation found THREE independent barriers, each of which alone
made energy income unreachable — the resource could only ever be spent:

1. Planet income was dead for EVERY planet type. The income gate read
   ``e.owner``, but a planet is spawned with ``owner == -1`` and colonising sets
   only ``colonized_by``. So ``if e.owner < 0: continue`` skipped every planet
   before the (also wrong) ``colonized_by == e.owner`` test could even run.
   No gas giant ever paid EN, and no world paid credits or crew either.

2. energy_relay could not be legally placed anywhere. Its ``requires_range``
   (<=1100u of a gas giant's CENTRE) sat entirely inside check_site's
   planet-spacing exclusion zone (gas giants are r2200, so the nearest legal
   spot was ~2355u). Swept exhaustively: zero legal positions on skirmish01.

3. No constructor could build an energy_relay at all — the id was missing from
   every faction's ``can_build_stations``.

Any one of these makes EN inert, so the tests below pin each one separately.
"""
from __future__ import annotations

import math
import unittest

from helpers import make_game
from game.core.vectors import Vec3
from game.data.store import DataStore


def _step(gm, seconds):
    for _ in range(int(seconds * 30)):
        gm.step(1 / 30)


def _first(st, **kw):
    """First live entity matching every attribute in kw (takes a GameState)."""
    for e in st.entities.values():
        if not e.alive:
            continue
        if all(getattr(e, k) == v for k, v in kw.items()):
            return e
    return None


def _colonize(gm, planet, player=0, fac="imperial"):
    """Colonize `planet` for `player` and run until it completes."""
    st = gm.state
    col = gm.factory.spawn_ship(
        f"{fac}_colonizer", player,
        Vec3(planet.pos.x, 0, planet.pos.z + planet.radius + 400), 0)
    ok = st._construction_system.start_colonize(col.id, planet.id, player)
    _step(gm, 30)
    return ok


# faction -> (constructor id, colonizer id). Note confederacy's ids are
# abbreviated ("confed_"), so they cannot be derived from the faction name.
FACTIONS = {
    "imperial": ("imperial_constructor", "imperial_colonizer"),
    "rebel": ("rebel_constructor", "rebel_colonizer"),
    "confederacy": ("confed_constructor", "confed_colonizer"),
    "syndicate": ("syndicate_constructor", None),
}


class TestPlanetIncome(unittest.TestCase):
    """Barrier 1: colonized planets must actually produce."""

    def test_colonized_temperate_planet_pays_credits_and_crew(self):
        gm = make_game(ai=False)
        p = gm.state.players[0]
        planet = _first(gm.state, data_id="temperate")
        self.assertIsNotNone(planet, "skirmish01 should have a temperate world")
        self.assertTrue(_colonize(gm, planet))
        self.assertEqual(planet.colonized_by, 0)
        # planets stay neutral terrain, so owner remains -1 — that is exactly
        # what made the old gate dead
        self.assertEqual(planet.owner, -1)

        rates = DataStore.get().rules["economy"]["planet_income"]["temperate"]
        self.assertGreaterEqual(p.income_frame.get("credits", 0.0),
                                rates["credits"] - 1e-6)
        crew_bonus = DataStore.get().rules["economy"]["planet_crew_bonus"]["temperate"]
        self.assertGreaterEqual(p.income_frame.get("crew", 0.0),
                                rates.get("crew", 0.0) + crew_bonus - 1e-6)

    def test_gas_giant_rejects_colonization_and_legacy_colony_income(self):
        gm = make_game(ai=False)
        p = gm.state.players[0]
        gas = _first(gm.state, data_id="gas_giant")
        self.assertIsNotNone(gas)
        self.assertFalse(_colonize(gm, gas))
        self.assertIsNone(gas.colonized_by)
        self.assertEqual(p.income_frame.get('energy', 0), 0)
        # Legacy ownership is not a loophole into forbidden gas income.
        gas.colonized_by = 0
        e0 = p.energy
        _step(gm, 10)
        self.assertEqual(p.energy, e0)
        self.assertEqual(p.income_frame.get('energy', 0), 0)

    def test_uncolonized_planet_pays_nothing(self):
        gm = make_game(ai=False)
        p = gm.state.players[0]
        _step(gm, 5)
        self.assertEqual(p.income_frame.get("energy", 0.0), 0.0)
        self.assertEqual(p.income_frame.get("materials", 0.0), 0.0)

    def test_enemy_colony_does_not_pay_me(self):
        """Income must go to the colonizer, not to whoever happens to be P0."""
        gm = make_game(ai=False)
        p0 = gm.state.players[0]
        _step(gm, 1)
        own_rate = p0.income_frame.get('credits', 0)
        planet = _first(gm.state, data_id="temperate")
        self.assertTrue(_colonize(gm, planet, player=1, fac="imperial"))
        self.assertEqual(planet.colonized_by, 1)
        self.assertAlmostEqual(p0.income_frame.get('credits', 0), own_rate)
        p1 = gm.state.players[1]
        rates = DataStore.get().rules['economy']['planet_income']['temperate']
        self.assertGreaterEqual(p1.income_frame.get('credits', 0), rates['credits'])
        before0, before1 = p0.credits, p1.credits
        _step(gm, 10)
        self.assertAlmostEqual(p0.credits - before0, own_rate * 10, places=5)
        self.assertGreaterEqual(p1.credits - before1, rates['credits'] * 10)


class TestEnergyRelayPlacement(unittest.TestCase):
    """Barrier 2: a legal relay site must exist around a gas giant."""

    def _site_sweep(self, gm, gas, station_id="energy_relay"):
        cs = gm.state._construction_system
        c = _first(gm.state, owner=0, is_construction=True)
        legal = []
        for d in range(400, 9000, 50):
            for ang in range(0, 360, 30):
                pos = Vec3(gas.pos.x + d * math.cos(math.radians(ang)), 0,
                           gas.pos.z + d * math.sin(math.radians(ang)))
                ok, _reason = cs.check_site(station_id, pos, c)
                if ok:
                    legal.append(d)
        return legal

    def test_energy_relay_has_legal_sites_around_a_gas_giant(self):
        gm = make_game(ai=False)
        gas = _first(gm.state, data_id="gas_giant")
        legal = self._site_sweep(gm, gas)
        self.assertTrue(
            legal,
            "energy_relay had ZERO legal positions — the requires_range window "
            "does not overlap the planet-spacing exclusion zone")

    def test_relay_window_is_outside_the_spacing_exclusion_zone(self):
        """The two rules must be consistent, not merely both satisfiable."""
        from game.systems.construction import _body_clearance

        gm = make_game(ai=False)
        sd = DataStore.get().resolve_station("energy_relay")
        gas = _first(gm.state, data_id="gas_giant")
        clearance = _body_clearance(gas, sd.radius)
        rng = sd.requires_range["gas_giant"]
        self.assertGreater(
            clearance + rng, clearance,
            "requires_range must reach past the exclusion zone")
        # a point just inside the window must be accepted
        cs = gm.state._construction_system
        c = _first(gm.state, owner=0, is_construction=True)
        pos = Vec3(gas.pos.x, 0, gas.pos.z + clearance + 5)
        ok, reason = cs.check_site("energy_relay", pos, c)
        self.assertTrue(ok, f"just outside the exclusion zone rejected: {reason}")

    def test_mining_station_placement_still_works(self):
        """The asteroid-field path had an explicit spacing skip — keep it working."""
        gm = make_game(ai=False)
        cs = gm.state._construction_system
        c = _first(gm.state, owner=0, is_construction=True)
        ast = _first(gm.state, data_id="asteroid_field")
        ok, reason = cs.check_site("mining_station", ast.pos.copy(), c)
        self.assertTrue(ok, f"mining station at asteroid centre rejected: {reason}")


class TestRelayBuildableAndGenerates(unittest.TestCase):
    """Barrier 3 + end-to-end: a constructor must be able to build it, and the
    station must then actually produce EN."""

    def test_every_faction_constructor_can_build_an_energy_relay(self):
        ds = DataStore.get()
        for fac, (ctor_id, _col) in FACTIONS.items():
            with self.subTest(faction=fac):
                sd = ds.ships.get(ctor_id)
                self.assertIsNotNone(sd, f"{fac} has no constructor")
                self.assertIn(
                    "energy_relay", sd.can_build_stations,
                    f"{fac} constructor cannot build an energy_relay, so that "
                    f"faction can never produce EN")

    def test_building_a_relay_produces_energy(self):
        gm = make_game(ai=False)
        st = gm.state
        p = st.players[0]
        cs = st._construction_system
        gas = _first(st, data_id="gas_giant")
        c = _first(st, owner=0, is_construction=True)

        # a site the validator accepts
        from game.systems.construction import _body_clearance
        sd = DataStore.get().resolve_station("energy_relay")
        target = Vec3(gas.pos.x, 0, gas.pos.z + _body_clearance(gas, sd.radius) + 300)
        c.pos.set(target)
        self.assertTrue(cs.start_station(c.id, "energy_relay", target, 0),
                        "constructor refused to build an energy_relay at a legal site")

        _step(gm, 60)
        relays = [e for e in st.entities.values()
                  if e.alive and e.data_id == "energy_relay" and e.owner == 0]
        self.assertEqual(len(relays), 1, "the energy relay never finished building")

        rate = DataStore.get().stations["energy_relay"].income["energy"]
        self.assertAlmostEqual(p.income_frame.get("energy", 0.0), rate, places=6)

        e0 = p.energy
        _step(gm, 10)
        self.assertAlmostEqual(p.energy - e0, rate * 10, places=1,
                               msg="energy did not accrue over time")

    def test_cancelling_a_relay_refunds_half(self):
        """Sanity: the existing 50% refund contract still holds."""
        gm = make_game(ai=False)
        st = gm.state
        p = st.players[0]
        cs = st._construction_system
        cost = gm.factory.station_build_cost("energy_relay")
        before = p.credits
        cs.refund(0, cost, 0.5)
        self.assertAlmostEqual(p.credits - before, cost["credits"] * 0.5, places=6)


class TestAIEnergyEconomy(unittest.TestCase):
    """The AI must not run its fleet into the EN floor either.

    It previously never built an energy_relay (no build-order entry, and the
    relay sits out by a gas giant, not on the ring around home), and it
    explicitly skipped gas giants when colonising. So an AI player's EN only
    ever fell.
    """

    def test_ai_builds_an_energy_relay_and_earns_energy(self):
        gm = make_game(ai=True)
        st = gm.state
        ai_id = next(pid for pid, p in st.players.items() if p.is_ai)

        min_en = None
        got_relay_at = None
        # 20 min: the relay sits ~7200u out by a gas giant and the constructor
        # must WALK there now that build range is enforced, so it lands late in
        # the AI's build order (~830s).
        for _ in range(30 * 60 * 20):          # 20 sim-minutes
            gm.step(1 / 30)
            en = st.players[ai_id].energy
            min_en = en if min_en is None else min(min_en, en)
            if got_relay_at is None and any(
                    e.alive and e.data_id == "energy_relay" and e.owner == ai_id
                    for e in st.entities.values()):
                got_relay_at = st.time

        relays = [e for e in st.entities.values()
                  if e.alive and e.data_id == "energy_relay" and e.owner == ai_id]
        self.assertTrue(relays, "the AI never built an energy_relay in 8 minutes")
        self.assertGreater(st.players[ai_id].income_frame.get("energy", 0.0), 0.0,
                           "the AI's energy relay produced no EN")

    def test_ai_can_reach_a_gas_giant_site_for_a_relay(self):
        """The site finder must actually return a legal position."""
        gm = make_game(ai=True)
        st = gm.state
        ai_id = next(pid for pid, p in st.players.items() if p.is_ai)
        gm.ai.ensure()
        ai = gm.ai.ais[ai_id]
        home = ai.home_station()
        builder = next((e for e in ai.my_units()
                        if e.is_construction and not e.is_planet), None)
        if home is None or builder is None:
            self.skipTest("AI has no home/builder in this fixture")
        site = ai._find_energy_relay_site(home, builder)
        self.assertIsNotNone(site, "AI could not find a legal energy_relay site")
        ok, reason = st._construction_system.check_site("energy_relay", site, builder)
        self.assertTrue(ok, f"finder returned a site the sim rejects: {reason}")

    def test_colony_target_selection_rejects_gas_and_accepts_barren(self):
        gm = make_game(ai=True)
        st = gm.state
        gm.ai.ensure()
        ai = gm.ai.ais[1]
        home = ai.home_station()
        gas = _first(st, data_id="gas_giant")
        barren = _first(st, data_id="barren")
        self.assertIsNotNone(gas)
        self.assertIsNotNone(barren)
        for e in st.entities.values():
            if e.is_planet:
                e.alive = e is gas
        gas.pos = home.pos + Vec3(400, 0, 400)
        self.assertIsNone(ai._pick_colony_target(home), 'gas giants cannot be colonies')
        barren.alive = True
        barren.colonized_by = None
        barren.pos = home.pos + Vec3(800, 0, 800)
        self.assertIs(ai._pick_colony_target(home), barren)



if __name__ == "__main__":
    unittest.main(verbosity=2)
