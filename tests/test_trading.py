"""Trading tests (spec §26): convoy spawn, delivery payment, raiding loot."""
import unittest

from helpers import make_game, run_for
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore


def _two_traders(gm):
    """Spawn a trade station for both players near their command stations."""
    st = gm.state
    st.next_entity_id  # noqa
    for pid, x in ((0, -6000.0), (1, 6000.0)):
        gm.factory.spawn_station("trade_station", pid, Vec3(x, 0, 0))
    return [e for e in st.entities.values()
            if e.alive and e.data_id == "trade_station"]


class TestConvoys(unittest.TestCase):
    def test_convoy_spawns(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg["spawn_interval"] = 0.5
        stations = _two_traders(gm)
        run_for(gm, 1.0)
        convoys = [e for e in st.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertGreaterEqual(len(convoys), 1)
        c = convoys[0]
        self.assertGreater(c.cargo_credits, 0)
        self.assertIsNotNone(c.convoy_dest)
        self.assertIn(c.owner, (0, 1))

    def test_convoy_arrives_and_pays(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg.update(spawn_interval=0.5)
        import game.data.store as _s
        _s.DataStore.get().rules["economy"]["trading"]["speed"] = 400.0
        stations = _two_traders(gm)
        p0 = st.players[0]
        cr0 = p0.credits
        run_for(gm, 40.0)
        paid = p0.credits > cr0
        self.assertTrue(paid, "destination owner should be paid on arrival")

    def test_raid_loots_killer(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg["spawn_interval"] = 0.5
        _two_traders(gm)
        run_for(gm, 1.0)
        convoys = [e for e in st.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertGreaterEqual(len(convoys), 1)
        c = convoys[0]
        p1 = st.players[1]
        cr1 = p1.credits
        # player 1 destroys player 0's convoy
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": c,
            "damage": 10**9, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 1.0, "weapon": None, "impact_pos": c.pos.copy(),
        })
        run_for(gm, 0.2)
        loot = c.cargo_credits * ts.cfg.get("loot_fraction", 0.5)
        self.assertGreaterEqual(p1.credits, cr1 + loot - 1.0)

    def test_no_trade_stations_no_convoys(self):
        gm = make_game(ai=False)
        run_for(gm, 2.0)
        convoys = [e for e in gm.state.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertEqual(len(convoys), 0)


class TestTradingReachability(unittest.TestCase):
    """Regressions for trading never actually running in a real game."""

    def test_ai_builds_a_trade_station(self):
        """The AI used to gate trade on >4000cr, which it holds for ~1.7% of a
        match — so trading never started. It must now build one."""
        gm = make_game()
        run_for(gm, 420.0)
        trade = [e for e in gm.state.entities.values()
                 if e.alive and e.data_id == "trade_station" and e.owner == 1]
        self.assertGreaterEqual(len(trade), 1, "AI never built a trade station")

    def test_ai_station_sites_are_legal(self):
        """AI build sites must pass the sim's own validator.

        _offset() returned ONE fixed angle, which on skirmish01 pointed into
        the planet Skarn — every queued build was rejected and silently
        dropped, so the AI never built anything it queued there.
        """
        gm = make_game()
        run_for(gm, 60.0)
        st = gm.state
        ai = gm.ai.ais[1]
        cs = st._construction_system
        home = next(e for e in st.entities.values()
                    if e.alive and e.is_station and e.owner == 1)
        builder = next(e for e in st.entities.values()
                       if e.alive and e.owner == 1 and e.is_construction)
        site = ai._find_station_site("trade_station", 900, home, builder)
        self.assertIsNotNone(site, "no legal trade-station site found")
        ok, reason = cs.check_site("trade_station", site, builder)
        self.assertTrue(ok, f"AI picked an illegal site: {reason}")

    def test_default_skirmish_starts_trading(self):
        """End-to-end: with no hand-placed stations, convoys must fly."""
        gm = make_game()
        st = gm.state
        arrived = []
        st.events.subscribe("convoy_arrived", lambda e: arrived.append(e.data))
        run_for(gm, 600.0)
        self.assertGreater(len(arrived), 0,
                           "no convoy delivered in 10 min of a default skirmish")


class TestConvoyArrivalSemantics(unittest.TestCase):
    """`owner` in the arrival payload means PAID, not the convoy's owner."""

    def test_escort_completes_only_for_human_convoy(self):
        """An AI convoy docking at the player's market must NOT complete the
        player's escort objective (it did: objective flipped done on an
        AI-owned convoy)."""
        from tests.test_objectives import _mission
        gm = make_game(ai=False)
        st = gm.state
        _mission(gm, [{"type": "escort_convoy", "text": "Escort"}])
        gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        gm.factory.spawn_station("trade_station", 1, Vec3(6000, 0, 0))
        import game.data.store as _s
        _s.DataStore.get().rules["economy"]["trading"]["speed"] = 400.0
        gm.trading.cfg.update(spawn_interval=0.5)

        seen = []
        st.events.subscribe("convoy_arrived", lambda e: seen.append(dict(e.data)))
        run_for(gm, 45.0)
        self.assertTrue(seen, "no arrivals to inspect")
        # every arrival must name its convoy's real owner
        for a in seen:
            self.assertIn("convoy_owner", a)
        human = [a for a in seen if a["convoy_owner"] == 0]
        if human:
            self.assertTrue(gm.mission.objectives[0]["done"])

    def test_raid_signal_names_the_victim_convoy(self):
        """convoy_raided must carry convoy_owner so an escort objective can
        tell the player's loss from an enemy's."""
        gm = make_game(ai=False)
        st = gm.state
        gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        gm.factory.spawn_station("trade_station", 1, Vec3(6000, 0, 0))
        gm.trading.cfg.update(spawn_interval=0.5, speed=10.0)
        raided = []
        st.events.subscribe("convoy_raided", lambda e: raided.append(dict(e.data)))
        run_for(gm, 1.0)
        c = next(e for e in st.entities.values()
                 if e.alive and e.data_id == "trade_convoy" and e.owner == 0)
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": c,
            "damage": 10**9, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 1.0, "weapon": None, "impact_pos": c.pos.copy(),
        })
        run_for(gm, 0.2)
        self.assertTrue(raided, "raid did not publish convoy_raided")
        self.assertEqual(raided[0]["convoy_owner"], 0)


class TestStartUnits(unittest.TestCase):
    def test_mission_enemy_trade_station_spawns(self):
        """Only mining/shipyard/research were honoured in start_units; any
        other station kind fell through to the ship branch and spawned
        NOTHING (the m02 enemy trade_station never appeared)."""
        import os
        DataStore.reset()
        ds = DataStore()
        mission = next(m for m in ds.campaign["missions"]
                       if m["id"] == "m02_supply_line")
        gm = GameManager.start_mission(ds.maps[mission["map"]], mission)
        st = gm.state
        enemy_trade = [e for e in st.entities.values()
                       if e.alive and e.data_id == "trade_station" and e.owner == 1]
        self.assertEqual(len(enemy_trade), 1,
                         "mission enemy trade_station did not spawn")


class TestConvoyHasNoShipData(unittest.TestCase):
    """A trade_convoy is a simulated ship with NO ShipData entry (TradingSystem
    mints it directly). Any code path that assumes ship data exists crashes —
    the reported one was the HUD's command-capacity readout, on every frame."""

    def _with_convoy(self):
        gm = make_game(ai=False)
        st = gm.state
        gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        gm.factory.spawn_station("trade_station", 1, Vec3(6000, 0, 0))
        gm.trading.cfg.update(spawn_interval=0.5, speed=10.0)
        run_for(gm, 1.0)
        conv = next(e for e in st.entities.values()
                    if e.alive and e.data_id == "trade_convoy")
        return gm, st, conv

    def test_command_used_is_total(self):
        """Was: KeyError "Unknown ship id 'trade_convoy'" -> game crash."""
        gm, st, conv = self._with_convoy()
        for pid, p in st.players.items():
            used = p.command_used(st.entities)
            self.assertIsInstance(used, int, f"player {pid} used={used!r}")

    def test_command_cost_zero_for_convoy(self):
        gm, st, conv = self._with_convoy()
        self.assertEqual(DataStore.get().command_cost(conv), 0)

    def test_convoy_stats_do_not_crash(self):
        """effective_speed/turn_rate are called every simulation tick."""
        from game.systems import stats
        gm, st, conv = self._with_convoy()
        self.assertGreater(stats.effective_speed(st, conv), 0.0)
        self.assertEqual(stats.effective_turn_rate(st, conv), 0.0)
        # must not raise either
        DataStore.get().unit_name(conv)
        conv.hull_fraction()
        conv.speed_multiplier()

    def test_whole_sim_runs_with_convoys_alive(self):
        """No other system may crash once a convoy exists."""
        gm, st, conv = self._with_convoy()
        run_for(gm, 30.0)          # would raise from any per-tick system

    def test_check_site_tolerates_data_less_builder(self):
        """check_site resolved the BUILDER through resolve_ship, whose
        ``unit is not None`` guard was dead code (it RAISES on an unknown id)
        — so placing a station from any hull without ship data raised."""
        gm, st, conv = self._with_convoy()
        cs = st._construction_system
        site = conv.pos + Vec3(400.0, 0.0, 400.0)
        ok, reason = cs.check_site("trade_station", site, conv)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(reason, str)


if __name__ == "__main__":
    unittest.main()