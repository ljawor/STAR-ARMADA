"""Full gameplay loop test: BUILD → GATHER → RESEARCH → FLEET → ATTACK → WIN (spec §47)."""
import unittest

from helpers import make_game, run_for, order_build
from game.core.vectors import Vec3
from game.core.commands import (
    BuildStationCommand, BuildShipCommand, ResearchCommand,
    FleetCreateCommand, AttackCommand, AttackMoveCommand, MoveCommand,
)


class TestConstruction(unittest.TestCase):
    def _prep(self):
        gm = make_game(ai=False)
        st = gm.state
        builder = next(e for e in st.entities.values()
                       if e.alive and e.owner == 0 and e.is_construction)
        home = next(e for e in st.entities.values()
                    if e.is_station and e.owner == 0)
        ast = next(e for e in st.entities.values()
                   if e.data_id == "asteroid_field" and e.pos.x < 0)
        return gm, st, builder, home, ast

    def test_build_mining_station(self):
        gm, st, builder, home, ast = self._prep()
        ok = order_build(gm, builder, "mining_station", ast.pos.copy(), 0)
        self.assertTrue(ok)
        run_for(gm, 30)
        mines = [e for e in st.entities.values()
                 if e.is_station and e.data_id == "mining_station"]
        self.assertEqual(len(mines), 1)

    def test_build_shipyard_and_ships(self):
        gm, st, builder, home, ast = self._prep()
        pos = home.pos + Vec3(600, 0, 0)
        self.assertTrue(order_build(gm, builder, "shipyard", pos, 0))
        run_for(gm, 45)
        yard = next((e for e in st.entities.values()
                     if e.is_station and e.data_id == "shipyard"), None)
        self.assertIsNotNone(yard)
        # build corvettes
        queued = gm.construction.start_ship(yard.id, "imperial_corvette", 0, 2)
        self.assertEqual(queued, 2)
        run_for(gm, 60)
        corvettes = [e for e in st.entities.values()
                     if e.alive and e.is_ship and e.data_id == "imperial_corvette"]
        self.assertGreaterEqual(len(corvettes), 4)   # 2 start + 2 built

    def test_resources_gate_construction(self):
        gm, st, builder, home, ast = self._prep()
        st.players[0].credits = 0
        st.players[0].materials = 0
        ok = order_build(gm, builder, "mining_station", ast.pos.copy(), 0)
        self.assertFalse(ok)

    def test_colonize_planet(self):
        gm, st, builder, home, ast = self._prep()
        col = gm.factory.spawn_ship("imperial_colonizer", 0, Vec3(0, 0, 0))
        planet = next(e for e in st.entities.values()
                      if e.is_planet and e.data_id == "temperate")
        ok = gm.construction.start_colonize(col.id, planet.id, 0)
        self.assertTrue(ok)
        run_for(gm, 120)
        self.assertEqual(planet.colonized_by, 0)
        self.assertFalse(col.alive)   # colonizer consumed


class TestResearch(unittest.TestCase):
    def _prep(self):
        gm = make_game(ai=False)
        st = gm.state
        builder = next(e for e in st.entities.values()
                       if e.alive and e.owner == 0 and e.is_construction)
        home = next(e for e in st.entities.values()
                    if e.is_station and e.owner == 0)
        return gm, st, builder, home

    def test_research_flow(self):
        gm, st, builder, home = self._prep()
        # build research station
        self.assertTrue(order_build(gm, builder, "research_station", home.pos + Vec3(-600, 0, 0), 0))
        run_for(gm, 40)
        lab = next((e for e in st.entities.values()
                    if e.is_station and e.data_id == "research_station"), None)
        self.assertIsNotNone(lab)
        ok = gm.research.start_research(0, lab.id, "imp_weapons_1")
        self.assertTrue(ok)
        run_for(gm, 50)
        self.assertIn("imp_weapons_1", st.players[0].researched)
        # effect applies
        from game.systems.stats import tech_mult
        self.assertAlmostEqual(tech_mult(st, 0, "weapon_damage_mult"), 1.15)
        # tier 2 unlocks
        self.assertIn("imp_weapons_2", gm.research.available_techs(0))

    def test_prerequisites_block(self):
        gm = make_game(ai=False)
        self.assertNotIn("imp_weapons_2", gm.research.available_techs(0))


class TestFormations(unittest.TestCase):
    def test_fleet_create_and_formation_move(self):
        gm = make_game(ai=False)
        st = gm.state
        ships = [e.id for e in st.entities.values()
                 if e.alive and e.owner == 0 and (e.is_ship or e.is_squadron)]
        st.queue_command(FleetCreateCommand(0, ships, "Alpha", commander="aggressive",
                                            formation="wedge"))
        run_for(gm, 0.5)
        self.assertEqual(len(st.fleets), 1)
        fleet = next(iter(st.fleets.values()))
        self.assertEqual(fleet.commander, "aggressive")
        self.assertEqual(fleet.formation, "wedge")
        # formation move
        target = fleet_flag = next(e for e in st.entities.values()
                                   if e.is_station and e.owner == 0).pos + Vec3(3000, 0, 0)
        from game.core.commands import PlayerCommand
        st.queue_command(PlayerCommand("move", 0, unit_ids=tuple(fleet.member_ids),
                                       target_pos=(target.x, target.y, target.z)))
        run_for(gm, 60)   # fleet includes a 60 u/s constructor + planet detour
        avg_dist = sum(e.pos.dist(target) for e in st.entities.values()
                       if e.id in fleet.member_ids and e.alive) / max(1, len(fleet.member_ids))
        self.assertLess(avg_dist, 900)

    def test_commander_bonus(self):
        gm = make_game(ai=False)
        st = gm.state
        ships = [e.id for e in st.entities.values()
                 if e.alive and e.owner == 0 and e.is_ship and not e.is_construction]
        st.queue_command(FleetCreateCommand(0, ships, "Alpha", commander="recon"))
        run_for(gm, 0.5)
        ship = next(e for e in st.entities.values()
                    if e.alive and e.owner == 0 and e.is_ship and e.fleet_id is not None)
        from game.systems.stats import effective_sensor_range
        sd = gm.ds.resolve_ship(ship.data_id)
        # recon commander gives +25%; veteran 0
        expected = sd.sensor_range * 1.25
        self.assertAlmostEqual(effective_sensor_range(st, ship), expected, delta=expected * 0.02)


class TestSquadrons(unittest.TestCase):
    def test_reinforce_at_station(self):
        gm = make_game(ai=False)
        st = gm.state
        sq = next(e for e in st.entities.values()
                  if e.alive and e.is_squadron and e.owner == 0)
        station = next(e for e in st.entities.values()
                       if e.is_station and e.owner == 0)
        sq.fighter_count = 2
        sq.pos.set(station.pos + Vec3(100, 0, 0))
        sq.hangar_id = station.id
        run_for(gm, 25)
        self.assertGreater(sq.fighter_count, 2)
        self.assertLessEqual(sq.fighter_count, sq.max_fighters)

    def test_squadron_auto_engages(self):
        gm = make_game(ai=False)
        st = gm.state
        sq = gm.factory.spawn_ship("imperial_tie_squadron", 0, Vec3(-2000, 0, 0))
        enemy = gm.factory.spawn_ship("imperial_corvette", 1, Vec3(-1500, 0, 0))
        run_for(gm, 3)
        self.assertEqual(sq.order_type, "attack")
        self.assertEqual(sq.current_target, enemy.id)


class TestAI(unittest.TestCase):
    def test_ai_builds_economy_and_fleet(self):
        gm = make_game()   # AI on for player 1
        run_for(gm, 240)
        st = gm.state
        ai_stations = [e.data_id for e in st.entities.values()
                       if e.is_station and e.owner == 1]
        self.assertIn("mining_station", ai_stations)
        ai_ships = [e for e in st.entities.values()
                    if e.alive and e.owner == 1 and (e.is_ship or e.is_squadron)]
        self.assertGreater(len(ai_ships), 5)

    def test_ai_researches(self):
        gm = make_game()
        # 15 min, not 10: a constructor now has to TRAVEL to each site
        # (`economy.station_build_range`), so the AI's build order runs longer —
        # it takes its first tech at ~680s.
        run_for(gm, 900)
        p1 = gm.state.players[1]
        # AI should have research station + at least started research
        self.assertTrue(p1.researched or p1.researching)


class TestFullLoop(unittest.TestCase):
    def test_destroy_enemy_base_wins(self):
        """The §47 acceptance loop, driven through commands like a player."""
        gm = make_game(ai=False)
        st = gm.state
        # cheat resources like a campaign grant
        p0 = st.players[0]
        p0.credits += 50000
        p0.materials += 30000
        p0.energy += 10000
        p0.crew += 20000
        builder = next(e for e in st.entities.values()
                       if e.alive and e.owner == 0 and e.is_construction)
        home = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
        # 1. BUILD shipyard
        self.assertTrue(order_build(gm, builder, "shipyard", home.pos + Vec3(800, 0, 0), 0))
        run_for(gm, 45)
        yard = next(e for e in st.entities.values()
                    if e.is_station and e.data_id == "shipyard" and e.owner == 0)
        self.assertIsNotNone(yard)
        # 2. RESEARCH a weapons tech (grant a research station instantly for speed)
        lab = gm.factory.spawn_station("research_station", 0, home.pos + Vec3(-800, 0, 0))
        self.assertTrue(gm.research.start_research(0, lab.id, "imp_weapons_1"))
        run_for(gm, 50)
        self.assertIn("imp_weapons_1", p0.researched)
        # 3. BUILD FLEET
        queued = gm.construction.start_ship(yard.id, "imperial_cruiser", 0, 2)
        self.assertEqual(queued, 2)
        queued += gm.construction.start_ship(yard.id, "imperial_corvette", 0, 4)
        run_for(gm, 90)
        combat = [e for e in st.entities.values()
                  if e.alive and e.owner == 0 and e.is_ship
                  and not e.is_construction]
        self.assertGreaterEqual(len(combat), 6)
        # 4. group into fleet
        st.queue_command(FleetCreateCommand(0, [e.id for e in combat], "Hammer",
                                            commander="aggressive", formation="wedge"))
        run_for(gm, 0.5)
        fleet = next(iter(st.fleets.values()))
        # 5. Scout toward the scenario's fixed opposing spawn, not a hidden
        # entity lock. Exploration alone cannot authorize an attack command.
        enemy_home = next(e for e in st.entities.values()
                          if e.is_station and e.owner == 1)
        self.assertFalse(st.can_see(0, enemy_home.id))
        opposing_start = next(p['start'] for p in gm.ds.maps['skirmish01']['players']
                              if p['slot'] == 1)
        st.queue_command(AttackMoveCommand(0, list(fleet.member_ids), Vec3(*opposing_start)))
        for _ in range(30 * 900):
            gm.step(1 / 30)
            if st.can_see(0, enemy_home.id) or st.game_over:
                break
        self.assertTrue(st.can_see(0, enemy_home.id), "fleet never discovered enemy base")
        st.queue_command(AttackCommand(0, list(fleet.member_ids), enemy_home.id))
        won = False
        for _ in range(60 * 900):    # up to 15 minutes sim (travel + siege)
            gm.step(1 / 30)
            if st.game_over:
                won = st.winner == 0
                break
        self.assertTrue(st.game_over, "game did not end after fleet assault")
        self.assertTrue(won, "player did not win")

    def test_victory_requires_command_station(self):
        gm = make_game(ai=False)
        st = gm.state
        # kill both command stations -> game over
        for e in [e for e in st.entities.values() if e.data_id == "command_station"]:
            e.hull = 1
            st.damage_queue.append({
                "attacker_id": -2, "attacker_entity": None, "target": e,
                "damage": 10 ** 9, "shield_mult": 1, "armor_mult": 1,
                "system_mult": 1, "weapon": None, "impact_pos": e.pos.copy(),
            })
        gm.step(1 / 30)
        gm.step(1.0)
        self.assertTrue(st.game_over)


if __name__ == "__main__":
    unittest.main()