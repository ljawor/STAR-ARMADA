"""Recovery policy regressions through the authoritative manager pipeline."""
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class RecoveryAIManagerRegressions(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.st.players[0].is_ai = True
        self.gm.ds.rules['ai']['strategic_interval'] = 10000
        self.base = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.gm.factory.spawn_station('command_station', 1, Vec3(10000, 0, 10000))
        self.st.players[0].crew = 1000
        self.st.players[0].credits = 10000
        self.observed_commands = []

    def ticks(self, count):
        before = self.st.tick
        for _ in range(count):
            self.observed_commands.extend(self.st.command_queue)
            self.gm.step(1 / 30)
        self.assertEqual(self.st.tick, before + count)
        self.assertFalse(self.st.game_over)

    def order(self, kind, ship, target=None):
        self.st.queue_command(PlayerCommand(kind, 0, unit_ids=(ship.id,),
                                            target_id=target.id if target else None))
        self.ticks(1)
        self.assertTrue(ship.crew_mission)

    def continue_exactly(self, count):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import state_checksum
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot))
        restored.ds.rules['ai']['strategic_interval'] = self.gm.ds.rules['ai']['strategic_interval']
        self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))), snapshot)
        for tick in range(count):
            self.observed_commands.extend(self.st.command_queue)
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(json.loads(json.dumps(self.st.to_dict(precise=True))),
                             json.loads(json.dumps(restored.state.to_dict(precise=True))), tick)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), tick)
        self.assertEqual(self.st.tick, snapshot['tick'] + count)
        self.assertFalse(self.st.game_over)

    def test_idle_understaffed_transport_without_field_target_returns_to_recruit(self):
        transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, -2000))
        transport.crew = 1
        distance = transport.pos.dist(self.base.pos)
        self.ticks(600)
        self.assertEqual(transport.crew_mission.get('phase'), 'recover')
        self.assertEqual(transport.crew_mission.get('target'), self.base.id)
        self.assertLess(transport.pos.dist(self.base.pos), distance)
        self.assertTrue(any(c.type == 'crew_recover' and transport.id in c.unit_ids
                            for c in self.observed_commands))
        self.continue_exactly(600)
        self.assertEqual(transport.crew_mission.get('target'), self.base.id)
        self.assertLess(transport.pos.dist(self.base.pos), distance)

    def test_abandoned_remote_transport_does_not_block_logistics_replacement(self):
        self.gm.ds.rules['ai']['strategic_interval'] = 1.0
        yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(0, 0, 600))
        self.st.players[0].materials = 10000
        self.st.players[0].energy = 10000
        target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(4000, 0, 0))
        target.crew = 0
        abandoned = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, -4000))
        abandoned.crew = 0
        self.ticks(60)
        self.assertTrue(any(c.type == 'build_ship' and c.ship_id == 'imperial_crew_transport'
                            and c.unit_ids == (yard.id,) for c in self.observed_commands))
        self.assertTrue(any(q.get('item') == 'imperial_crew_transport' for q in yard.build_queue))
        self.continue_exactly(840)
        replacements = [e for e in self.st.entities.values()
                        if e.owner == 0 and e.data_id == 'imperial_crew_transport'
                        and e.id != abandoned.id]
        self.assertEqual(len(replacements), 1)
        self.assertTrue(replacements[0].operational)
        self.assertEqual(abandoned.crew, 0)
        self.assertEqual(sum(c.type == 'build_ship' and c.ship_id == 'imperial_crew_transport'
                             for c in self.observed_commands), 1)

    def test_idle_understaffed_transport_completes_recruitment_after_restore(self):
        transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, -2000))
        transport.crew = transport.max_crew // 2
        self.ticks(60)
        self.assertEqual(transport.crew_mission.get('phase'), 'recover')
        self.continue_exactly(1800)
        self.assertEqual(transport.crew, transport.max_crew)
        self.assertEqual(transport.crew_mission, {})
        self.assertEqual(transport.order_type, 'idle')
        self.assertFalse(any(c.type in ('attack', 'attack_move', 'crew_load', 'crew_deliver')
                             and transport.id in c.unit_ids for c in self.observed_commands))

    def test_safe_active_understaffed_transport_missions_are_preserved(self):
        target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(4000, 0, 0))
        target.crew = 0
        for phase in ('load', 'deliver'):
            with self.subTest(phase=phase):
                transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 300))
                transport.crew_cargo = 20
                self.order('crew_' + phase, transport, target if phase == 'deliver' else None)
                transport.crew = 1
                if phase == 'deliver':
                    transport.pos = Vec3(2000, 0, 0)
                self.ticks(12)
                self.assertEqual(transport.crew_mission.get('phase'), phase)
                self.assertGreaterEqual(transport.crew_cargo, 20)
                self.assertFalse(any(c.type == 'crew_recover' and transport.id in c.unit_ids
                                     for c in self.observed_commands))

    def test_available_transports_prevent_duplicate_logistics_production(self):
        from game.core.state import PlayerState
        for variant in ('absent', 'operational_remote', 'abandoned_own_base', 'abandoned_allied_base'):
            with self.subTest(variant=variant):
                self.setUp()
                self.gm.ds.rules['ai']['strategic_interval'] = 1.0
                self.gm.factory.spawn_station('shipyard', 0, Vec3(0, 0, 600))
                self.st.players[0].materials = 10000
                self.st.players[0].energy = 10000
                target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(4000, 0, 0))
                target.crew = 0
                if variant != 'absent':
                    pos = Vec3(0, 0, -4000) if variant == 'operational_remote' else Vec3(0, 0, -300)
                    transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, pos)
                    if variant != 'operational_remote':
                        transport.crew = 0
                    if variant == 'abandoned_allied_base':
                        self.st.players[2] = PlayerState(2, 'imperial', team=self.st.players[0].team)
                        self.gm.factory.spawn_station('command_station', 2, Vec3(0, 0, -4000))
                        transport.pos = Vec3(0, 0, -3700)
                self.ticks(900)
                builds = [c for c in self.observed_commands
                          if c.type == 'build_ship' and c.ship_id == 'imperial_crew_transport']
                self.assertEqual(len(builds), 1 if variant == 'absent' else 0)
                transports = [e for e in self.st.entities.values()
                              if e.owner == 0 and e.data_id == 'imperial_crew_transport']
                self.assertEqual(len(transports), 1)
                self.assertTrue(transports[0].operational)

    def test_emergency_support_preempts_active_transport_missions_without_unloading(self):
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(0, 0, -600))
        target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(4000, 0, 0))
        target.crew = 0
        for phase in ('load', 'deliver'):
            with self.subTest(phase=phase):
                transport = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 300))
                transport.crew_cargo = 20
                self.order('crew_' + phase, transport, target if phase == 'deliver' else None)
                transport.pos = Vec3(1200, 0, 0)
                transport.systems['life_support'].hp = 0
                cargo = transport.crew_cargo
                self.ticks(12)
                self.assertEqual(transport.crew_mission.get('phase'), 'recover')
                self.assertEqual(transport.crew_mission.get('target'), dock.id)
                self.assertEqual(transport.order_target_id, dock.id)
                self.assertEqual(transport.crew_cargo, cargo)
                self.assertEqual(target.crew, 0)
                # Recovery is serialized AI intent consumed by the manager.
                self.assertTrue(any(cmd.type == 'crew_recover' and
                                    transport.id in cmd.unit_ids and cmd.target_id == dock.id
                                    for cmd in self.observed_commands))
                distance = transport.pos.dist(dock.pos)
                personnel = self.st.players[0].crew + sum(
                    e.crew + e.crew_cargo for e in self.st.entities.values() if e.owner == 0)
                self.ticks(180)
                self.assertEqual(transport.crew_mission.get('target'), dock.id)
                self.assertLess(transport.pos.dist(dock.pos), distance)
                self.assertGreater(transport.crew_cargo, 0)
                self.assertLessEqual(transport.crew_cargo, cargo)
                self.assertEqual(target.crew, 0)
                self.assertLessEqual(self.st.players[0].crew + sum(
                    e.crew + e.crew_cargo for e in self.st.entities.values() if e.owner == 0), personnel)

    def test_replenishment_only_finishes_with_safe_partially_damaged_support(self):
        ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(300, 0, 0))
        ship.crew = ship.max_crew // 2
        ship.systems['life_support'].hp *= .8
        self.gm.factory.spawn_station('repair_dock', 0, Vec3(5000, 0, 0))
        self.ticks(12)
        self.assertEqual(ship.crew_mission.get('target'), self.base.id)
        self.ticks(2400)
        self.assertEqual(ship.crew, ship.max_crew)
        self.assertAlmostEqual(ship.subsystem_fraction('life_support'), .8)
        self.assertEqual(ship.crew_mission, {})
        self.assertIn(ship, self.gm.ai.ais[0].my_units())

    def test_fallback_recovery_retargets_new_usable_repair_infrastructure(self):
        from game.core.state import PlayerState
        self.st.players[2] = PlayerState(2, 'imperial', team=0)
        ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(300, 0, 0))
        ship.systems['life_support'].hp *= .6
        self.ticks(12)
        self.assertEqual(ship.crew_mission.get('target'), self.base.id)
        # Allied docks recruit but EconomySystem cannot repair this owner's hull.
        self.gm.factory.spawn_station('repair_dock', 2, Vec3(0, 0, 300))
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(1500, 0, 0))
        self.ticks(12)
        self.assertEqual(ship.crew_mission.get('target'), dock.id)
        self.assertEqual(ship.order_target_id, dock.id)
        self.assertTrue(any(cmd.type == 'crew_recover' and cmd.target_id == dock.id
                            and ship.id in cmd.unit_ids for cmd in self.observed_commands))
        self.ticks(900)
        self.assertGreaterEqual(ship.subsystem_fraction('life_support'), .99)
        self.assertEqual(ship.crew_mission, {})
        self.assertIn(ship, self.gm.ai.ais[0].my_units())

    def test_hidden_competing_party_target_does_not_change_ai_boarding(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState, PlayerState
        self.st.players[2] = PlayerState(2, 'imperial', team=2)
        attacker = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(200, 0, 0))
        attacker.systems['weapons'].hp = 0
        target = self.gm.factory.spawn_ship('imperial_frigate', 1, Vec3(450, 0, 0))
        target.crew = 0
        target.shields = {q: 0 for q in target.shields}
        target.systems['shield_gen'].hp = 0
        competitor = self.gm.factory.spawn_ship('imperial_cruiser', 2, Vec3(450, 0, 400))
        competitor.systems['weapons'].hp = 0
        self.st.queue_command(PlayerCommand('board', 2, unit_ids=(competitor.id,), target_id=target.id))
        self.ticks(1)
        assert competitor.boarding_party_id is not None
        craft = self.st.entity(competitor.boarding_party_id)
        assert craft is not None
        craft.pos = Vec3(9000, 0, 9000)
        self.gm.visibility.update()
        self.assertFalse(self.st.can_see(0, craft.id))
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        choices = []
        distant = next(e for e in self.st.entities.values() if e.owner == 1 and e.is_station)
        for hidden_target in (distant.id, target.id):
            gm = GameManager(GameState.from_dict(snapshot))
            hidden_craft = gm.state.entity(craft.id)
            assert hidden_craft is not None
            hidden_craft.boarding['target'] = hidden_target
            commands = []
            for _ in range(3):
                commands.extend(c.to_dict() for c in gm.state.command_queue
                                if c.type == 'board' and attacker.id in c.unit_ids)
                gm.step(1 / 30)
                self.assertFalse(gm.state.can_see(0, craft.id))
            self.assertEqual(gm.state.tick, snapshot['tick'] + 3)
            live_attacker = gm.state.entity(attacker.id)
            assert live_attacker is not None
            self.assertIsNotNone(live_attacker.boarding_party_id)
            choices.append(commands)
        self.assertTrue(choices[0])
        self.assertEqual(choices[1], choices[0])
        # Still reserve own/allied parties and currently detected competitors.
        for reservation in ('own', 'allied', 'detected_hostile'):
            with self.subTest(reservation=reservation):
                gm = GameManager(GameState.from_dict(snapshot))
                party = gm.state.entity(craft.id)
                source = gm.state.entity(competitor.id)
                assert party is not None and source is not None
                if reservation == 'own':
                    party.owner = source.owner = 0
                elif reservation == 'allied':
                    gm.state.players[2].team = gm.state.players[0].team
                else:
                    party.pos = Vec3(250, 0, 250)
                for _ in range(3):
                    self.assertFalse(any(c.type == 'board' and attacker.id in c.unit_ids
                                         for c in gm.state.command_queue))
                    gm.step(1 / 30)
                live_attacker = gm.state.entity(attacker.id)
                assert live_attacker is not None
                self.assertIsNone(live_attacker.boarding_party_id)

    def test_new_dock_retarget_and_repair_completion_restore_exactly_every_tick(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import state_checksum
        ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(300, 0, 0))
        ship.systems['life_support'].hp *= .6
        self.ticks(12)
        self.assertEqual(ship.crew_mission.get('target'), self.base.id)
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot))
        # Rule overrides are fixture configuration, not serialized game state.
        restored.ds.rules['ai']['strategic_interval'] = self.gm.ds.rules['ai']['strategic_interval']
        self.assertEqual(json.loads(json.dumps(restored.state.to_dict(precise=True))), snapshot)
        for gm in (self.gm, restored):
            gm.factory.spawn_station('repair_dock', 0, Vec3(1500, 0, 0))
        for tick in range(900):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(json.loads(json.dumps(self.st.to_dict(precise=True))),
                             json.loads(json.dumps(restored.state.to_dict(precise=True))), tick)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), tick)
        self.assertEqual(self.st.tick, snapshot['tick'] + 900)
        self.assertEqual(ship.crew_mission, {})
        self.assertGreaterEqual(ship.subsystem_fraction('life_support'), .99)


if __name__ == '__main__':
    unittest.main()
