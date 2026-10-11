"""Trading tests (spec §26): convoy spawn, delivery payment, raiding loot."""
import unittest

from helpers import make_game, run_for
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore


def _two_traders(gm, distance=1800.0):
    """Two own markets safely away from player 1, who remains an enemy."""
    return [gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, z))
            for z in (0, distance)]


def _allied_traders(gm):
    """An AI ally's market, with a living third enemy to prevent auto-victory."""
    from game.core.state import PlayerState
    st = gm.state
    st.players[0].team = st.players[1].team = 0
    st.players[1].is_ai = True  # make_game(ai=False) leaves AI controllers disabled
    st.players[2] = PlayerState(2, team=1, is_ai=True)
    gm.factory.spawn_station("command_station", 2, Vec3(10000, 0, 10000))
    return [gm.factory.spawn_station("trade_station", pid, Vec3(-6000, 0, z))
            for pid, z in ((0, 0), (1, 1800))]


def _advance_until(test, gm, predicate, max_ticks=1800):
    """Bounded real-manager progress; never accept game-over no-op ticks."""
    for _ in range(max_ticks):
        if predicate():
            return
        tick = gm.state.tick
        gm.step(1 / 30)
        test.assertEqual(gm.state.tick, tick + 1)
        test.assertFalse(gm.state.game_over)
    test.fail("condition not reached during live simulation")


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
        self.assertEqual(c.owner, 0)
        self.assertIn(c.convoy_dest, [station.id for station in stations])

    def test_convoy_arrives_and_pays(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        from unittest.mock import patch
        ts.cfg.update(spawn_interval=100000, reward_owner="destination")
        source, destination = _allied_traders(gm)
        c = ts._make_convoy(source, destination, 150.0, 250.0)
        start = c.pos.copy()
        arrived = []
        balance = {}

        def observe_payment(ev):
            data = dict(ev.data)
            paid = st.players[data["owner"]]
            arrived.append((data, paid.credits - balance[data["owner"]]))

        update = ts.update

        def observed_update(dt):
            # Economy already ran this tick: isolate the actual delivery credit.
            balance.update({pid: p.credits for pid, p in st.players.items()})
            update(dt)

        st.events.subscribe("convoy_arrived", observe_payment)
        with patch.object(ts, "update", side_effect=observed_update):
            _advance_until(self, gm, lambda: bool(arrived))
        self.assertEqual(len(arrived), 1)
        data, reward = arrived[0]
        self.assertEqual(data, dict(entity_id=c.id, owner=1, convoy_owner=0,
                                    dest=destination.id, cargo=150.0))
        self.assertEqual(reward, data["cargo"])
        self.assertGreater(c.pos.dist_sq(start), 0)
        self.assertFalse(c.alive)

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
        self.assertEqual(c.owner, 0)
        self.assertTrue(st.is_enemy(1, c.owner))
        gm.damage.update(0)  # real damage/payment, without ordinary economy income
        loot = c.cargo_credits * ts.cfg.get("loot_fraction", 0.5)
        self.assertFalse(c.alive)
        self.assertEqual(p1.credits - cr1, loot)

    def test_no_trade_stations_no_convoys(self):
        gm = make_game(ai=False)
        run_for(gm, 2.0)
        convoys = [e for e in gm.state.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertEqual(len(convoys), 0)


def _surface_hub(gm, planet):
    """An operational planet Trade Hub on a colonised world (issue #53)."""
    planet.colonized_by = 0
    hub = gm.factory.spawn_station("planet_trade_hub", 0,
                                   planet.pos + Vec3(planet.radius, 0, 0))
    hub.planet_id = planet.id
    hub.planet_building_slot = 0
    return hub


def _temperate(gm):
    return next(e for e in gm.state.entities.values()
                if e.data_id == "temperate" and e.owner == -1)


class TestPlanetTradeHub(unittest.TestCase):
    """Reported (#53): "Planet trading hub does not trade with trading stations"."""

    def test_hub_is_a_market_end_for_convoys(self):
        gm = make_game(ai=False)
        st = gm.state
        gm.trading.cfg["spawn_interval"] = 0.5
        hub = _surface_hub(gm, _temperate(gm))
        self.assertIn(hub, gm.trading.markets(st))
        run_for(gm, 2.0)
        self.assertEqual([e for e in st.entities.values()
                          if e.alive and e.data_id == "trade_convoy"], [],
                         "a lone market has nowhere to ship")
        station = gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        run_for(gm, 2.0)
        convoys = [e for e in st.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertTrue(convoys, "hub opened no route to the station")
        self.assertTrue(all(c.convoy_dest in (hub.id, station.id) for c in convoys))
        self.assertIn(hub.id, {c.convoy_source for c in convoys} |
                      {c.convoy_dest for c in convoys})

    def test_hub_convoy_delivers_and_pays_the_reward(self):
        from unittest.mock import patch
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg.update(spawn_interval=100000, reward_owner="destination")
        hub = _surface_hub(gm, _temperate(gm))
        station = gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        self.assertTrue(ts.valid_market(st, 0, hub))
        c = ts._make_convoy(hub, station, 150.0, 250.0)
        self.assertTrue(ts.valid_market(st, 0, st.entity(c.convoy_dest)))
        arrived = []
        balance = {}

        def observe_payment(ev):
            data = dict(ev.data)
            arrived.append((data, st.players[data["owner"]].credits
                             - balance[data["owner"]]))

        update = ts.update

        def observed_update(dt):
            balance.update({pid: p.credits for pid, p in st.players.items()})
            update(dt)

        st.events.subscribe("convoy_arrived", observe_payment)
        with patch.object(ts, "update", side_effect=observed_update):
            _advance_until(self, gm, lambda: bool(arrived))
        data, reward = arrived[0]
        self.assertEqual(data["dest"], station.id)
        self.assertEqual(data["cargo"], 150.0)
        self.assertEqual(reward, data["cargo"])
        self.assertFalse(c.alive)

    def test_hub_stops_trading_when_its_world_is_lost(self):
        gm = make_game(ai=False)
        st = gm.state
        planet = _temperate(gm)
        hub = _surface_hub(gm, planet)
        station = gm.factory.spawn_station("trade_station", 0, Vec3(-6000, 0, 0))
        self.assertIn(hub, gm.trading.markets(st))
        planet.colonized_by = 1                       # captured by the enemy
        self.assertNotIn(hub, gm.trading.markets(st))
        self.assertFalse(gm.trading.valid_market(st, 0, hub))
        self.assertTrue(gm.trading.valid_market(st, 0, station))


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
        human_market, ally_market = _allied_traders(gm)
        gm.trading.cfg.update(spawn_interval=100000, reward_owner="destination")
        seen = []
        st.events.subscribe("convoy_arrived", lambda e: seen.append(dict(e.data)))
        # Install the mission's real event hooks before the first delivery.
        gm.step(1 / 30)
        ai_convoy = gm.trading._make_convoy(ally_market, human_market, 150, 250)
        ai_start = ai_convoy.pos.copy()
        _advance_until(self, gm, lambda: bool(seen))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["entity_id"], ai_convoy.id)
        self.assertEqual(seen[0]["convoy_owner"], 1)
        self.assertEqual(seen[0]["owner"], 0)
        self.assertGreater(ai_convoy.pos.dist_sq(ai_start), 0)
        self.assertFalse(gm.mission.objectives[0]["done"])
        self.assertFalse(gm.mission.completed)
        self.assertFalse(gm.mission.failed)

        human_convoy = gm.trading._make_convoy(human_market, ally_market, 150, 250)
        human_start = human_convoy.pos.copy()
        _advance_until(self, gm, lambda: len(seen) == 2)
        self.assertEqual(seen[1]["entity_id"], human_convoy.id)
        self.assertEqual(seen[1]["convoy_owner"], 0)
        self.assertEqual(seen[1]["owner"], 1)
        self.assertGreater(human_convoy.pos.dist_sq(human_start), 0)
        self.assertTrue(gm.mission.objectives[0]["done"])
        self.assertTrue(gm.mission.completed)
        self.assertEqual(gm.mission._escorted_id, human_convoy.id)

    def test_raid_signal_names_the_victim_convoy(self):
        """convoy_raided must carry convoy_owner so an escort objective can
        tell the player's loss from an enemy's."""
        gm = make_game(ai=False)
        st = gm.state
        _two_traders(gm, distance=6000.0)
        gm.trading.cfg.update(spawn_interval=0.5)
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
        _two_traders(gm, distance=6000.0)
        gm.trading.cfg.update(spawn_interval=0.5)
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
        tick = st.tick
        run_for(gm, 30.0)          # would raise from any per-tick system
        self.assertEqual(st.tick - tick, int(30.0 / (1 / 30)))
        self.assertFalse(st.game_over)
        self.assertTrue(conv.alive)
        self.assertGreater(conv.pos.dist_sq(Vec3(-6000, 0, 0)), 0)

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