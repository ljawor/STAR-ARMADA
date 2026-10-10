"""Physical, deterministic fighter exploration regressions (headless)."""
import unittest
import helpers
from game.core.vectors import Vec3


class TestFighterExploration(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        from game.core.state import GameState, PlayerState
        from game.data.store import DataStore
        from game.systems.unit_factory import UnitFactory
        from game.systems.squadrons import SquadronSystem
        from game.systems.weapons import WeaponSystem
        DataStore.reset()
        self.st = GameState()
        self.st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}
        self.gm = SimpleNamespace(state=self.st, factory=UnitFactory(self.st),
                                  squadrons=SquadronSystem(self.st), weapons=WeaponSystem(self.st))
        self.st.entities.clear()
        self.st.explored_cells.clear()
        self.st.discovered_planets.clear()
        self.st.map_info.bounds = 6000
        self.st.map_info.victory_mode = 'elimination'
        self.fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())

    def system(self):
        from game.systems import exploration
        self.assertTrue(hasattr(exploration, 'ExplorationSystem'), 'exploration API missing')
        return exploration.ExplorationSystem(self.st)

    def test_start_persists_exploration_intent_without_revealing_cells(self):
        system = self.system()
        before = self.st.to_dict(precise=True)['explored_cells']
        self.assertTrue(system.start(self.fighter, 0))
        self.assertEqual(self.fighter.order_type, 'explore')
        self.assertIsNotNone(self.fighter.order_target_pos)
        self.assertIsNone(self.fighter.current_target)
        self.assertEqual(before, self.st.to_dict(precise=True)['explored_cells'])
        target = self.fighter.order_target_pos.copy()
        system.update(1 / 30)
        self.assertEqual(target.to_dict(), self.fighter.order_target_pos.to_dict())

    def test_detected_contact_never_fires_or_overrides_exploration(self):
        system = self.system()
        enemy = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, Vec3(0, 0, 300))
        self.st.grid.rebuild(self.st.entities)
        self.assertTrue(self.st.can_see(0, enemy.id))
        self.assertTrue(system.start(self.fighter, 0))
        self.gm.squadrons.update(.3)
        self.gm.weapons.update(.3)
        self.assertEqual(self.fighter.order_type, 'explore')
        self.assertIsNone(self.fighter.current_target)
        self.assertFalse(any(p.attacker_entity_id == self.fighter.id
                             for p in self.st.projectiles.values()))
        self.assertFalse(any(d.get('attacker') is self.fighter for d in self.st.damage_queue))

    def test_detected_enemy_on_route_reroutes_away_from_weapon_threat(self):
        system = self.system()
        self.assertTrue(system.start(self.fighter, 0))
        old = self.fighter.order_target_pos.copy()
        enemy = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, old)
        self.assertTrue(self.st.can_see(0, enemy.id))
        system.update(1 / 30)
        target = self.fighter.order_target_pos
        self.assertIsNotNone(target)
        self.assertNotEqual(old.to_dict(), target.to_dict())
        self.assertGreater(target.dist(enemy.pos), 1200)
        self.assertGreater((self.fighter.pos - enemy.pos).dot(target - self.fighter.pos), 0)

    def test_only_unsafe_frontier_retreats_to_safe_owned_area(self):
        system = self.system()
        home = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(-2000, 0, 0))
        self.fighter.sensor_range = 2500
        self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(1500, 0, 0))
        cells = {(x, z) for x in range(-6, 6) for z in range(-6, 6)}
        cells.remove((3, 0))
        self.st.explored_cells[0] = cells
        self.assertTrue(system.start(self.fighter, 0))
        self.assertIsNotNone(self.fighter.order_target_pos)
        self.assertEqual(self.fighter.order_target_pos.to_dict(), home.pos.to_dict())
        self.assertEqual(self.fighter.order_type, 'explore')

    def test_capability_rejects_constructor_and_boarding_roles(self):
        from game.systems.exploration import exploration_capable
        self.assertTrue(exploration_capable(self.fighter))
        bomber = self.gm.factory.spawn_ship('imperial_tie_bomber_squadron', 0, Vec3())
        self.assertTrue(exploration_capable(bomber))
        self.fighter.is_construction = True
        self.assertFalse(exploration_capable(self.fighter))
        self.fighter.is_construction = False
        self.fighter.boarding = {'phase': 'approach'}
        self.assertFalse(exploration_capable(self.fighter))

    def test_config_validation_rejects_nonfinite_or_nonpositive_values(self):
        from game.systems import exploration
        self.assertTrue(hasattr(exploration, 'validate_exploration_rules'))
        exploration.validate_exploration_rules({})
        for value in (True, 0, -1, float('inf'), float('nan'), '350'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exploration.validate_exploration_rules({'exploration': {'threat_margin': value}})
        with self.assertRaises(ValueError):
            exploration.validate_exploration_rules({'exploration': []})
        exploration.validate_exploration_rules({'exploration': {'threat_margin': 500}})

    def test_reinforcement_completion_preserves_exploration(self):
        system = self.system()
        hangar = self.gm.factory.spawn_ship('imperial_battleship', 0, Vec3())
        self.fighter.hangar_id = hangar.id
        self.fighter.fighter_count = self.fighter.max_fighters - .001
        self.assertTrue(system.start(self.fighter, 0))
        self.gm.squadrons.update(1)
        self.assertEqual(self.fighter.fighter_count, self.fighter.max_fighters)
        self.assertEqual(self.fighter.order_type, 'explore')

    def test_actual_manager_movement_reveals_new_cells_within_speed_limit(self):
        import math
        from game.core.entity import Entity
        from game.systems import stats
        gm = helpers.make_game(ai=False)
        st = gm.state
        st.entities.clear()
        st.explored_cells.clear()
        st.discovered_planets.clear()
        st.map_info.bounds = 6000
        fighter = gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        sentinel = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(2800, 0, 2800))
        sentinel.order_type = 'hold'
        planet = Entity(st.next_entity_id, 'planet', -1, 'rocky',
                        pos=Vec3(-1200, 0, -600), radius=250, is_planet=True)
        st.add_entity(planet)
        gm.visibility.update(0)
        initial_cells = set(st.explored_cells[0])
        initial_pos = fighter.pos.copy()
        self.assertTrue(gm.exploration.start(fighter, 0))
        visited = set()
        for _ in range(1800):
            previous = fighter.pos.copy()
            gm.step(1 / 30)
            self.assertFalse(st.game_over)
            self.assertTrue(all(e.alive for e in st.entities.values()))
            self.assertLessEqual(previous.dist(fighter.pos), stats.effective_speed(st, fighter) / 30 + 1e-6)
            self.assertTrue(all(math.isfinite(v) for v in (fighter.pos.x, fighter.pos.y, fighter.pos.z)))
            self.assertGreater(fighter.pos.dist(planet.pos), planet.radius * 1.2 + fighter.radius)
            self.assertEqual(fighter.order_type, 'explore')
            self.assertIsNone(fighter.current_target)
            visited.add(st.visibility_cell(fighter.pos))
        self.assertEqual(st.tick, 1800)
        self.assertGreater(initial_pos.dist(fighter.pos), 500)
        self.assertGreater(len(visited - initial_cells), 2)
        self.assertGreater(len(st.explored_cells[0] - initial_cells), 10)

    def test_hidden_enemy_mutation_cannot_change_exploration_route(self):
        import json
        from game.core.state import GameState
        from game.systems.exploration import ExplorationSystem
        from game.systems.movement import MovementSystem
        from game.systems.visibility import VisibilitySystem
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(2500, 0, 2500))
        self.fighter.sensor_range = 100
        self.assertTrue(self.system().start(self.fighter, 0))
        clone = GameState.from_dict(json.loads(json.dumps(self.st.to_dict(precise=True))))
        clone.entities[enemy.id].pos = Vec3(-2500, 0, -2500)
        clone.entities[enemy.id].data_id = 'imperial_supercapital'
        clone.entities[enemy.id].radius = 5000
        systems = [(state, ExplorationSystem(state), MovementSystem(state), VisibilitySystem(state))
                   for state in (self.st, clone)]
        for _ in range(90):
            for state, exploration, movement, visibility in systems:
                self.assertFalse(state.can_see(0, enemy.id))
                exploration.update(1 / 30)
                movement.update(1 / 30)
                visibility.update(1 / 30)
            first, second = self.st.entities[self.fighter.id], clone.entities[self.fighter.id]
            self.assertEqual(first.pos.to_dict(), second.pos.to_dict())
            self.assertEqual(first.order_target_pos.to_dict(), second.order_target_pos.to_dict())
            self.assertEqual(self.st.explored_cells.get(0), clone.explored_cells.get(0))

    def test_exact_json_restore_continues_same_manager_exploration(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        sentinel = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(2800, 0, 2800))
        sentinel.order_type = 'hold'
        gm = GameManager(self.st)
        self.assertTrue(gm.exploration.start(self.fighter, 0))
        for _ in range(77):
            gm.step(1 / 30)
        normalize = lambda state: json.loads(json.dumps(state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(normalize(self.st)))
        self.assertEqual(normalize(self.st), normalize(restored.state))
        initial = self.fighter.pos.copy()
        for _ in range(450):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertFalse(self.st.game_over)
            self.assertTrue(all(e.alive for e in self.st.entities.values()))
            self.assertEqual(normalize(self.st), normalize(restored.state))
        self.assertEqual(self.st.tick, 527)
        self.assertGreater(self.fighter.pos.dist(initial), 300)

    def test_allied_history_idles_persistently_then_resumes(self):
        from game.core.state import PlayerState
        self.st.players[2] = PlayerState(2, team=0)
        self.st.explored_cells[2] = {(x, z) for x in range(-6, 6) for z in range(-6, 6)}
        system = self.system()
        self.assertTrue(system.start(self.fighter, 0))
        self.assertEqual(self.fighter.order_type, 'explore')
        self.assertIsNone(self.fighter.order_target_pos)
        self.assertEqual(self.fighter.vel.length(), 0)
        system.update(1 / 30)
        self.assertEqual(self.fighter.order_type, 'explore')
        self.assertIsNone(self.fighter.order_target_pos)
        self.st.explored_cells[2].remove((3, 3))
        system.update(1 / 30)
        self.assertEqual(self.st.visibility_cell(self.fighter.order_target_pos), (3, 3))
        system.cancel(self.fighter)
        self.assertEqual(self.fighter.order_type, 'idle')
        self.assertIsNone(self.fighter.order_target_pos)
        system.update(1 / 30)
        self.assertEqual(self.fighter.order_type, 'idle')

    def test_authority_and_operational_checks_reject_without_mutation(self):
        system = self.system()
        for player in (1, -1, 99):
            before = self.st.to_dict(precise=True)
            self.assertFalse(system.start(self.fighter, player))
            self.assertEqual(before, self.st.to_dict(precise=True))
        self.fighter.crew = 0
        before = self.st.to_dict(precise=True)
        self.assertFalse(system.start(self.fighter, 0))
        self.assertEqual(before, self.st.to_dict(precise=True))
        self.fighter.crew = self.fighter.max_crew
        self.assertTrue(system.start(self.fighter, 0))
        self.fighter.crew = 0
        system.update(1 / 30)
        self.assertEqual(self.fighter.order_type, 'idle')
        self.assertIsNone(self.fighter.order_target_pos)

    def test_accepted_explorer_detaches_fleet_and_cancels_jump(self):
        from game.core.world import Fleet
        system = self.system()
        mate = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(-1000, 0, 0))
        self.st.fleets[1] = Fleet(id=1, owner=0, name='Patrol',
                                 member_ids={self.fighter.id, mate.id}, flagship_id=self.fighter.id)
        self.fighter.fleet_id = mate.fleet_id = 1
        mate.order_type = 'move'
        mate.order_target_pos = Vec3(3000, 0, 0)
        self.fighter.jump_charge = 2
        self.fighter.jump_target = Vec3(1000, 0, 0)
        self.assertTrue(system.start(self.fighter, 0))
        self.assertIsNone(self.fighter.fleet_id)
        self.assertEqual(self.st.fleets[1].member_ids, {mate.id})
        self.assertEqual(self.st.fleets[1].flagship_id, mate.id)
        self.assertEqual(mate.order_type, 'move')
        self.assertEqual(self.fighter.jump_charge, 0)
        self.assertIsNone(self.fighter.jump_target)
        self.fighter.order_type = 'move'
        self.fighter.order_target_pos = Vec3(123, 0, 456)
        system.update(1 / 30)
        self.assertEqual(self.fighter.order_target_pos.to_dict(), [123, 0, 456])

    def test_manager_ticks_physically_avoid_detected_weapon_keepout(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        gm = GameManager(self.st)
        self.fighter.sensor_range = 2000
        self.assertTrue(gm.exploration.start(self.fighter, 0))
        initial_target = self.fighter.order_target_pos.copy()
        enemy = gm.factory.spawn_ship('imperial_corvette', 1, initial_target)
        enemy.order_type = 'hold'
        self.assertTrue(self.st.can_see(0, enemy.id))
        start = self.fighter.pos.copy()
        normalize = lambda state: json.loads(json.dumps(state.to_dict(precise=True)))
        restored = None
        for tick in range(300):
            if tick == 77:
                restored = GameManager(GameState.from_dict(normalize(self.st)))
                self.assertEqual(normalize(self.st), normalize(restored.state))
            gm.step(1 / 30)
            if restored is not None:
                restored.step(1 / 30)
                self.assertEqual(normalize(self.st), normalize(restored.state))
            self.assertFalse(self.st.game_over)
            self.assertTrue(all(e.alive for e in self.st.entities.values()))
            self.assertGreater(self.fighter.pos.dist(enemy.pos), 1250)
            self.assertEqual(self.fighter.order_type, 'explore')
            self.assertIsNone(self.fighter.current_target)
            self.assertIsNone(self.fighter.order_target_id)
        self.assertEqual(self.st.tick, 300)
        self.assertGreater(self.fighter.pos.dist(start), 500)
        fired = [event for event in self.st.events.log
                 if event.type == 'weapon_fired' and event.data.get('attacker_id') == self.fighter.id]
        self.assertEqual(fired, [])

    def test_sensor_discovery_does_not_abort_safe_waypoint(self):
        system = self.system()
        self.assertTrue(system.start(self.fighter, 0))
        target = self.fighter.order_target_pos.copy()
        self.assertGreater(self.fighter.pos.dist(target), 80)
        self.st.explored_cells[0] = {(x, z) for x in range(-6, 6) for z in range(-6, 6)}
        system.update(1 / 30)
        self.assertIsNotNone(self.fighter.order_target_pos)
        self.assertEqual(self.fighter.order_target_pos.to_dict(), target.to_dict())
        self.fighter.pos = target.copy()
        system.update(1 / 30)
        self.assertIsNone(self.fighter.order_target_pos)
        self.assertEqual(self.fighter.order_type, 'explore')
        self.assertEqual(self.fighter.vel.length(), 0)

    def test_exact_manager_restore_finishes_planet_detour_then_replacement(self):
        import json
        from game.core.commands import MoveCommand
        from game.core.entity import Entity
        from game.core.manager import GameManager
        from game.core.state import GameState
        self.fighter.pos = Vec3(250, 0, 250)
        self.fighter.sensor_range = 100
        sentinel = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(-2800, 0, 2800))
        sentinel.order_type = 'hold'
        planet = Entity(self.st.next_entity_id, 'planet', -1, 'rocky',
                        pos=Vec3(1250, 0, 250), radius=400, is_planet=True)
        self.st.add_entity(planet)
        self.st.explored_cells[0] = {(x, z) for x in range(-6, 6) for z in range(-6, 6)} - {(4, 0)}
        gm = GameManager(self.st)
        self.assertTrue(gm.exploration.start(self.fighter, 0))
        for _ in range(150):
            gm.step(1 / 30)
        self.assertIsNotNone(self.fighter.order_target_pos)
        normalize = lambda state: json.loads(json.dumps(state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(normalize(self.st)))
        self.assertEqual(normalize(self.st), normalize(restored.state))
        targets = set()
        for _ in range(1350):
            if self.fighter.order_target_pos is not None:
                targets.add(tuple(self.fighter.order_target_pos.to_dict()))
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(normalize(self.st), normalize(restored.state))
            self.assertFalse(self.st.game_over)
            self.assertTrue(all(e.alive for e in self.st.entities.values()))
            self.assertGreater(self.fighter.pos.dist(planet.pos), planet.radius * 1.2 + self.fighter.radius)
            self.assertEqual(self.fighter.order_type, 'explore')
            self.assertIsNone(self.fighter.current_target)
        self.assertEqual(self.st.tick, 1500)
        self.assertGreater(len(targets), 1)
        self.assertIn((4, 0), self.st.explored_cells[0])
        self.assertEqual(self.st.visibility_cell(self.fighter.pos), (4, 0))
        self.assertGreater(self.fighter.pos.x, 2000)
        self.assertIsNone(self.fighter.order_target_pos)
        self.assertEqual(self.fighter.vel.length(), 0)
        destination = Vec3(2600, 0, 250)
        for manager in (gm, restored):
            manager.state.queue_command(MoveCommand(0, (self.fighter.id,), destination))
        for _ in range(30):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(normalize(self.st), normalize(restored.state))
            self.assertEqual(self.fighter.order_type, 'move')
            self.assertEqual(self.fighter.order_target_pos.to_dict(), destination.to_dict())
        self.assertEqual(self.st.tick, 1530)

    def test_public_planet_detour_reaches_remaining_cell(self):
        from game.core.entity import Entity
        from game.systems.movement import MovementSystem
        from game.systems.visibility import VisibilitySystem
        self.fighter.pos = Vec3(250, 0, 250)
        self.fighter.sensor_range = 100
        planet = Entity(self.st.next_entity_id, 'planet', -1, 'rocky',
                        pos=Vec3(1250, 0, 250), radius=400, is_planet=True)
        self.st.add_entity(planet)
        self.st.explored_cells[0] = {(x, z) for x in range(-6, 6) for z in range(-6, 6)} - {(4, 0)}
        system = self.system()
        self.assertTrue(system.start(self.fighter, 0))
        self.assertIsNotNone(self.fighter.order_target_pos)
        movement, visibility = MovementSystem(self.st), VisibilitySystem(self.st)
        for _ in range(1500):
            system.update(1 / 30)
            movement.update(1 / 30)
            visibility.update(1 / 30)
            self.assertGreater(self.fighter.pos.dist(planet.pos), planet.radius * 1.2 + self.fighter.radius)
            # Sensor/rectangle intersection records discovery before physical
            # entry; keep exercising movement until the fighter reaches the cell.
            if self.st.visibility_cell(self.fighter.pos) == (4, 0):
                break
        self.assertIn((4, 0), self.st.explored_cells[0])
        self.assertGreater(self.fighter.pos.x, 2000)


if __name__ == '__main__':
    unittest.main()
