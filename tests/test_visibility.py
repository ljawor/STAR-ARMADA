"""Live sensor queries and deterministic exploration memory."""
import json
import unittest

import helpers
from game.core.entity import Entity
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3


class TestVisibility(unittest.TestCase):
    def setUp(self):
        self.gm = helpers.make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.st.explored_cells.clear()
        self.st.discovered_planets.clear()
        self.st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}

    def unit(self, eid, owner, x: float = 0, sensor: float = 1000,
             kind="ship", y: float = 0, z: float = 0):
        e = Entity(eid, kind, owner, "test", pos=Vec3(x, y, z),
                   is_ship=kind == "ship", is_station=kind == "station",
                   is_squadron=kind == "squadron", is_planet=kind == "planet",
                   sensor_range=sensor)
        self.st.add_entity(e)
        return e

    def test_repeated_contact_queries_do_not_reaggregate_sources(self):
        from unittest.mock import patch
        from game.systems.stats import effective_sensor_range
        for eid in range(1, 101):
            self.unit(eid, 0)
        enemy = self.unit(101, 1, 500)
        with patch.object(GameState, "sensor_sources", wraps=self.st.sensor_sources) as sources, \
                patch("game.systems.stats.effective_sensor_range",
                      wraps=effective_sensor_range) as ranges:
            for _ in range(20):
                self.assertTrue(self.st.can_see(0, enemy.id))
            self.assertEqual(sources.call_count, 0)
            self.assertLessEqual(ranges.call_count, 1)

    def test_tick_limits_exploration_aggregation_to_three_phases(self):
        from unittest.mock import patch
        self.unit(1, 0)
        self.unit(2, 1, 500)
        with patch.object(GameState, "sensor_sources", wraps=self.st.sensor_sources) as sources:
            self.gm.step(1 / 30)
            self.assertLessEqual(sources.call_count, 6)

    def test_moved_observer_explores_before_dying_during_combat(self):
        from unittest.mock import patch
        source = self.unit(1, 0, sensor=100)
        destination = Vec3(5000, 0, 0)
        self.assertFalse(self.st.is_position_explored(0, destination))
        with patch.object(self.gm.movement, "update",
                          side_effect=lambda dt: setattr(source, "pos", destination.copy())), \
                patch.object(self.gm.damage, "update",
                             side_effect=lambda dt: setattr(source, "alive", False)):
            self.gm.step(1 / 30)
        self.assertTrue(self.st.is_position_explored(0, destination))
        self.assertFalse(self.st.is_position_visible(0, destination))

    def test_cached_witness_validates_all_same_tick_modifier_mutations(self):
        from game.core.world import Fleet
        from game.systems.stats import effective_sensor_range
        source = self.gm.factory.spawn_ship("imperial_corvette", 0, Vec3())
        enemy = self.unit(1000, 1, source.sensor_range)
        start_tick = self.st.tick

        def check():
            radius = effective_sensor_range(self.st, source)
            for x, y, z in ((radius, 0, 0), (radius + .01, 0, 0),
                            (0, radius * .6, radius * .8), (1000, 0, 0)):
                enemy.pos = Vec3(source.pos.x+x, source.pos.y+y, source.pos.z+z)
                expected = ((source.pos.x-enemy.pos.x)**2
                            + (source.pos.y-enemy.pos.y)**2
                            + (source.pos.z-enemy.pos.z)**2 <= radius**2 and radius > 0)
                self.assertEqual(self.st.can_see(0, enemy.id), expected)
            self.assertEqual(self.st.tick, start_tick)

        check()
        source.systems["sensors"].hp = 0
        check()
        source.systems["sensors"].max_hp = 0
        check()
        source.systems["sensors"].max_hp = 100
        source.systems["sensors"].hp = 100
        source.sensor_range = 1234
        check()
        source.ability_active["sensor_jammed"] = .1
        check()
        source.ability_active["sensor_jammed"] = 0
        check()
        tech = next(t for t in self.gm.ds.techs.values()
                    if t.effects.get("sensor_range_mult", 1) > 1)
        self.st.players[0].researched.add(tech.id)
        check()
        self.st.players[0].researched.clear()
        check()
        self.st.fleets[1] = Fleet(id=1, owner=0, name="Sensors", commander="scout")
        self.gm.ds.rules.setdefault("commanders", {})["scout"] = {"sensor_range": .5}
        source.fleet_id = 1
        check()
        self.st.fleets[1].commander = "tactical"
        check()
        source.fleet_id = None
        source.xp = 100000
        check()
        source.xp = 0
        check()
        nebula = {"pos": [0, 0, 0], "radius": 100}
        self.st.map_info.nebulas = [nebula]
        check()
        nebula["pos"][0] = 10000
        check()
        source.pos.x = 10000
        check()
        nebula["radius"] = 0
        source.pos.y = 1
        check()

    def test_witness_deletion_spawn_ownership_and_team_mutations_are_immediate(self):
        source = self.unit(1, 0)
        enemy = self.unit(2, 1, 500)
        self.assertTrue(self.st.can_see(0, enemy.id))
        del self.st.entities[source.id]
        self.assertFalse(self.st.can_see(0, enemy.id))
        # Direct insertion, including reuse of an id, must not require a hook.
        replacement = Entity(1, "ship", 0, "test", is_ship=True, sensor_range=1000)
        self.st.entities[1] = replacement
        self.assertTrue(self.st.can_see(0, enemy.id))
        replacement.owner = 1
        self.assertFalse(self.st.can_see(0, enemy.id))
        self.st.players[2] = PlayerState(2, team=0)
        replacement.owner = 2
        self.assertTrue(self.st.can_see(0, enemy.id))
        self.st.players[2].team = 9
        self.assertFalse(self.st.can_see(0, enemy.id))
        self.st.players[0].team = 9
        self.assertTrue(self.st.can_see(0, enemy.id))
        replacement.pos.y = 1001
        self.assertFalse(self.st.can_see(0, enemy.id))
        replacement.pos = Vec3()
        self.assertTrue(self.st.can_see(0, enemy.id))
        replacement.alive = False
        self.assertFalse(self.st.can_see(0, enemy.id))
        replacement.alive = True
        self.assertTrue(self.st.can_see(0, enemy.id))
        saved = self.st.to_dict(precise=True)
        self.assertNotIn("_sensor_queries", saved)
        restored = GameState.from_dict(saved)
        self.assertIsNone(restored._sensor_queries)
        self.assertTrue(restored.can_see(0, enemy.id))

    def test_live_3d_boundaries_and_no_observer_fallback(self):
        enemy = self.unit(2, 1, 1000)
        self.assertFalse(self.st.can_see(0, enemy.id))
        source = self.unit(1, 0)
        self.assertTrue(self.st.can_see(0, enemy.id))
        enemy.pos.y = 1
        self.assertFalse(self.st.can_see(0, enemy.id))
        enemy.pos = Vec3(0, 600, 800)
        self.assertTrue(self.st.is_position_visible(0, enemy.pos))
        source.alive = False
        self.assertFalse(self.st.can_see(0, enemy.id))
        self.assertFalse(self.st.can_see(999, enemy.id))
        self.assertFalse(self.st.is_position_visible(999, Vec3()))
        self.assertFalse(self.st.can_see(0, source.id))

    def test_allied_remote_sources_individual_ranges_and_solo_players(self):
        self.st.players[2] = PlayerState(2, team=0)
        ally = self.unit(1, 2, 10000, sensor=3000, kind="station")
        own = self.unit(2, 0, sensor=100)
        target = self.unit(3, 1, 13000)
        self.assertTrue(self.st.can_see(0, ally.id))
        self.assertTrue(self.st.can_see(0, target.id))
        target.pos.x += 0.01
        self.assertFalse(self.st.can_see(0, target.id))
        target.pos.x = 200
        self.assertFalse(self.st.can_see(0, target.id))
        self.assertEqual([e.id for e, _ in self.st.sensor_sources(0)], [1, 2])
        self.st.players[0].team = None
        self.st.players[2].team = None
        self.assertFalse(self.st.can_see(0, ally.id))
        self.st.players[0].team = -1
        self.st.players[2].team = -1
        self.assertFalse(self.st.can_see(0, ally.id))
        self.assertTrue(self.st.can_see(0, own.id))
        planet = self.unit(4, -1, 10000, sensor=999999, kind="planet")
        own.alive = False
        self.assertFalse(self.st.is_position_visible(0, planet.pos))

    def test_exploration_and_planet_memory_survive_loss_without_hidden_updates(self):
        self.st.players[2] = PlayerState(2, team=0)
        source = self.unit(1, 2)
        planet = self.unit(2, -1, 500, kind="planet")
        planet.name_override = "First name"
        enemy_station = self.unit(3, 1, 500, sensor=0, kind="station")
        self.gm.visibility.update()
        self.assertTrue(self.st.is_position_explored(0, planet.pos))
        self.assertIs(self.st.known_entity(0, planet.id), planet)
        source.pos.x = 10000
        planet.owner = 1
        planet.colonized_by = 1
        planet.name_override = "Secret new name"
        self.gm.visibility.update()
        self.assertFalse(self.st.can_see(0, planet.id))
        remembered = self.st.known_entity(0, planet.id)
        assert remembered is not None
        self.assertEqual(remembered.name_override, "First name")
        self.assertEqual(remembered.owner, -1)
        self.assertIsNone(remembered.colonized_by)
        self.assertIsNone(self.st.known_entity(0, enemy_station.id))
        source.alive = False
        self.gm.visibility.update()
        self.assertTrue(self.st.is_position_explored(2, planet.pos))
        self.assertFalse(self.st.is_position_visible(0, planet.pos))
        self.assertFalse(self.st.is_position_explored(1, planet.pos))
        self.assertFalse(self.st.is_position_explored(999, planet.pos))
        self.assertIsNone(self.st.known_entity(999, planet.id))
        half = self.st.map_info.bounds / 2
        self.assertFalse(self.st.is_position_explored(0, Vec3(half + 1, 0, 0)))
        self.assertEqual(self.st.visibility_cell_size, 500)

    def test_save_exact_roundtrip_and_legacy_sensor_defaults(self):
        source = self.unit(1, 0, sensor=1234.56789)
        planet = self.unit(2, -1, 500, kind="planet")
        self.gm.visibility.update()
        source.alive = False
        planet.name_override = "Hidden change"
        saved = self.st.to_dict(precise=True)
        restored = GameState.from_dict(json.loads(json.dumps(saved)))
        self.assertEqual(restored.to_dict(precise=True), saved)
        self.assertEqual(restored.entities[1].sensor_range, source.sensor_range)
        self.assertTrue(restored.is_position_explored(0, planet.pos))
        remembered = restored.known_entity(0, planet.id)
        assert remembered is not None
        self.assertNotEqual(remembered.name_override, planet.name_override)
        self.assertNotIn("_visibility_system", saved)
        self.assertEqual(saved["explored_cells"][0], sorted(saved["explored_cells"][0]))
        ship = self.gm.factory.spawn_ship("imperial_corvette", 0, Vec3())
        station = self.gm.factory.spawn_station("sensor_station", 0, Vec3())
        legacy = self.st.to_dict(precise=True)
        del legacy["entities"][ship.id]["sensor_range"]
        del legacy["entities"][station.id]["sensor_range"]
        old = GameState.from_dict(legacy)
        self.assertEqual(old.entities[ship.id].sensor_range, ship.sensor_range)
        self.assertEqual(old.entities[station.id].sensor_range, station.sensor_range)
        self.assertEqual(old.entities[1].sensor_range, source.sensor_range)

    def test_manager_setup_and_tick_explore_and_replay_checksums_match(self):
        from game.core.manager import GameManager
        from game.net.replay import state_checksum
        gm = helpers.make_game(ai=False)
        self.assertTrue(gm.state.explored_cells[0])
        restored = GameManager(GameState.from_dict(gm.state.to_dict(precise=True)))
        for _ in range(20):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(state_checksum(gm.state), state_checksum(restored.state))
        source = self.unit(1, 0, x=5000)
        self.assertFalse(self.st.is_position_explored(0, source.pos))
        self.gm.step(1 / 30)
        self.assertTrue(self.st.is_position_explored(0, source.pos))
        self.assertIs(self.st._visibility_system, self.gm.visibility)

    def test_dynamic_modifiers_station_range_and_fresh_squadron(self):
        from game.systems.stats import effective_sensor_range
        ship = self.gm.factory.spawn_ship("imperial_corvette", 0, Vec3())
        enemy = self.unit(100, 1, x=ship.sensor_range)
        self.assertTrue(self.st.can_see(0, enemy.id))
        ship.systems["sensors"].hp = 0
        self.assertFalse(self.st.can_see(0, enemy.id))
        ship.systems["sensors"].hp = ship.systems["sensors"].max_hp
        ship.ability_active["sensor_jammed"] = 0.1234567
        self.assertFalse(self.st.can_see(0, enemy.id))
        saved = self.st.to_dict(precise=True)
        self.assertEqual(GameState.from_dict(saved).entities[ship.id].ability_active,
                         ship.ability_active)
        ship.ability_active.clear()
        tech = next(t for t in self.gm.ds.techs.values()
                    if t.effects.get("sensor_range_mult", 1) > 1)
        self.st.players[0].researched.add(tech.id)
        enemy.pos.x = ship.sensor_range * 1.01
        self.assertTrue(self.st.can_see(0, enemy.id))
        self.st.map_info.nebulas = [{"pos": [0, 0, 0], "radius": 100}]
        self.assertFalse(self.st.can_see(0, enemy.id))
        self.st.map_info.nebulas = []
        station = self.gm.factory.spawn_station("sensor_station", 0, Vec3())
        self.assertGreater(station.sensor_range, ship.sensor_range)
        enemy.pos.x = effective_sensor_range(self.st, station)
        self.assertTrue(self.st.can_see(0, enemy.id))
        station.alive = False
        self.assertFalse(self.st.can_see(0, enemy.id))
        squadron = self.gm.factory.spawn_ship("imperial_tie_squadron", 0, Vec3(10000, 0, 0))
        enemy.pos = squadron.pos.copy()
        self.assertTrue(self.st.can_see(0, enemy.id))
        self.assertTrue(any(e is squadron for e, _ in self.st.sensor_sources(0)))

    def test_mission_loadout_does_not_explore_replaced_start_observers(self):
        from game.core.manager import GameManager
        map_def = {"bounds": 20000, "players": [
            {"slot": 0, "start": [0, 0, 0], "start_units": {"sensor_station": 1}}],
            "planets": [{"id": "near", "pos": [0, 0, 100], "radius": 50}]}
        gm = GameManager.start_mission(map_def, {"loadout": {"start_units": {}}})
        self.assertFalse(gm.state.is_position_explored(0, Vec3()))
        planet = next(e for e in gm.state.entities.values() if e.is_planet)
        self.assertIsNone(gm.state.known_entity(0, planet.id))

    def test_teamless_players_are_enemies_not_implicit_allies(self):
        self.st.players[0].team = None
        self.st.players[1].team = None
        self.assertTrue(self.st.is_enemy(0, 1))
        self.assertEqual([p.id for p in self.st.enemy_players(0)], [1])
        self.st.players[0].team = self.st.players[1].team = -1
        self.assertTrue(self.st.is_enemy(0, 1))
        self.st.players[0].team = self.st.players[1].team = 0
        self.assertFalse(self.st.is_enemy(0, 1))


if __name__ == "__main__":
    unittest.main()
