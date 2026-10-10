"""Authoritative safety, conservation, cancellation and restored real ticks."""
import json
import unittest
from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3
from game.core.state import GameState, PlayerState
from game.core.manager import GameManager
from game.net.replay import state_checksum


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.base = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.gm.factory.spawn_station('command_station', 1, Vec3(9000, 0, 9000))
        self.target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(300, 0, 0))
        self.target.crew = 0
        self.t = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 300))
        self.p = self.st.players[0]
        self.p.crew, self.p.credits = 1000, 1000
        self.st.players[0].team = 0
        self.st.players[2] = PlayerState(2, 'rebel', team=0, crew=100, credits=100)
        self.gm.visibility.update()

    def cmd(self, kind, target=None, player=0, ids=None):
        self.st.queue_command(PlayerCommand(kind, player, unit_ids=ids or (self.t.id,),
                                            target_id=target.id if target else None))
        self.gm.commands.consume()

    def snapshot(self, state):
        return json.loads(json.dumps(state.to_dict(precise=True)))

    def test_support_admission_below_at_above_threshold_and_external_repair(self):
        for fraction, expected in ((.499, 0), (.5, 4), (.501, 4)):
            self.target.crew = 0
            self.target.systems['life_support'].hp = fraction * self.target.systems['life_support'].max_hp
            self.gm.recovery.update(1)
            self.assertEqual(self.target.crew, expected)
        self.target.crew = 0
        self.target.systems['life_support'].hp = 0
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(150, 0, 0))
        self.st.grid.rebuild(self.st.entities)
        self.gm.economy.update(1)
        self.assertEqual(self.target.crew, 0)
        for _ in range(90):
            self.gm.step(1 / 30)
        self.assertGreater(self.target.crew, 0)
        self.assertTrue(self.target.alive)

    def test_owned_hulls_only_allied_base_services_owners_own_pool(self):
        self.target.owner = 2
        pool = self.p.crew
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 4)
        self.assertEqual(self.st.players[2].crew, 96)
        self.assertEqual(self.p.crew, pool)
        self.target.crew = 0
        self.target.owner = 1
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 0)
        self.target.owner = -1
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 0)

    def test_no_resource_debt_or_free_progress_while_resources_absent(self):
        for crew, credits in ((0, 100), (10, 1.99), (.99, 100)):
            self.p.crew, self.p.credits = crew, credits
            self.gm.recovery.update(100)
            self.assertEqual(self.target.crew, 0)
            self.assertEqual(self.target.recruitment_progress, 0)
            self.assertEqual((self.p.crew, self.p.credits), (crew, credits))
        self.p.crew, self.p.credits = 1, 2
        self.gm.recovery.update(.249)
        self.assertEqual(self.target.crew, 0)
        self.gm.recovery.update(.001)
        self.assertEqual(self.target.crew, 1)
        self.assertEqual((self.p.crew, self.p.credits), (0, 0))

    def test_simultaneous_consumers_stable_id_priority_and_finite_capacity(self):
        self.p.crew, self.p.credits = 5, 10
        self.cmd('crew_load', ids=(self.t.id, self.t.id))
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 4)
        self.assertEqual(self.t.crew_cargo, 1)
        self.assertEqual((self.p.crew, self.p.credits), (0, 0))
        self.p.crew, self.p.credits = 1000, 2000
        self.t.crew_cargo = 239
        self.gm.recovery.update(100)
        self.assertEqual(self.t.crew_cargo, 240)
        self.assertEqual(self.t.crew_mission, {})

    def test_load_rechecks_base_support_owner_and_operating_crew(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.cmd('crew_load')
        self.base.owner = 1
        self.gm.step(.25)
        self.assertEqual(self.t.crew_cargo, 0)
        self.base.owner = 0
        self.t.systems['life_support'].hp = 49
        self.gm.step(.25)
        self.assertEqual(self.t.crew_cargo, 0)
        self.t.systems['life_support'].hp = 100
        self.t.crew = 0
        self.gm.step(.25)
        self.assertEqual(self.t.crew_mission, {})
        # Base replenishes operating crew, never converts existing cargo.
        self.assertEqual(self.t.crew, 1)
        self.assertEqual(self.t.crew_cargo, 0)

    def test_delivery_needs_explicit_order_safe_owned_target_and_3d_range(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.t.pos = Vec3(2000, 1000, 0)
        self.t.crew_cargo = 12
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 0)
        for owner in (1, 2, -1):
            self.target.owner = owner
            self.cmd('crew_deliver', self.target)
            self.assertEqual(self.t.crew_mission, {})
        self.target.owner = 0
        self.target.systems['life_support'].hp = 49.999
        self.cmd('crew_deliver', self.target)
        self.assertEqual(self.t.crew_mission, {})
        self.target.systems['life_support'].hp = 50
        self.cmd('crew_deliver', self.target)
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 0)
        self.t.pos = Vec3(2000, 0, 100)
        self.gm.recovery.update(1)
        self.assertEqual(self.target.crew, 8)
        self.assertEqual(self.t.crew_cargo, 4)

    def test_delivery_pauses_and_resumes_when_support_fails_without_pool_refund(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.t.pos = Vec3(2000, 0, 100)
        self.t.crew_cargo = 4
        self.cmd('crew_deliver', self.target)
        self.target.systems['life_support'].hp = 49
        before = self.p.crew
        self.gm.recovery.update(10)
        self.assertEqual((self.target.crew, self.t.crew_cargo), (0, 4))
        self.assertIn('50%', self.t.crew_mission['reason'])
        self.target.systems['life_support'].hp = 50
        self.gm.recovery.update(.5)
        self.assertEqual((self.target.crew, self.t.crew_cargo), (4, 0))
        self.assertEqual(self.p.crew, before)

    def test_stop_move_and_cancel_preserve_passengers_and_remove_target_references(self):
        self.t.crew_cargo = 4
        self.target.pos = Vec3(2000, 0, 0)
        for kind in ('stop', 'crew_cancel'):
            self.cmd('crew_deliver', self.target)
            self.cmd(kind)
            self.assertEqual(self.t.crew_mission, {})
            self.assertIsNone(self.t.order_target_id)
            self.assertEqual(self.t.crew_cargo, 4)
        self.cmd('crew_deliver', self.target)
        self.st.queue_command(PlayerCommand('move', 0, unit_ids=(self.t.id,), target_pos=(4000, 0, 0)))
        self.gm.commands.consume()
        self.assertEqual(self.t.crew_mission, {})
        self.assertEqual(self.t.order_type, 'move')

    def test_authority_rejects_enemy_source_forged_normal_ship_and_stale_target(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.t.crew_cargo = 4
        self.cmd('crew_deliver', self.target, player=1)
        self.assertEqual(self.t.crew_mission, {})
        self.cmd('crew_load', ids=(self.target.id,))
        self.assertEqual(self.target.crew_mission, {})
        self.st.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(self.t.id,), target_id=self.target.id))
        self.target.owner = 1
        self.gm.commands.consume()
        self.assertEqual(self.t.crew_mission, {})

    def test_target_transfer_or_destruction_clears_before_movement(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.t.crew_cargo = 4
        self.cmd('crew_deliver', self.target)
        before = self.t.pos.to_dict()
        self.target.owner = 1
        self.gm.step(.25)
        self.assertEqual(self.t.pos.to_dict(), before)
        self.assertEqual(self.t.crew_mission, {})
        self.assertIsNone(self.t.order_target_id)
        self.target.owner = 0
        self.cmd('crew_deliver', self.target)
        self.gm.damage._kill(self.target, None, -1)
        self.assertEqual(self.t.crew_mission, {})
        self.assertIsNone(self.t.order_target_id)
        self.gm.step(.25)
        self.assertEqual(self.t.crew_mission, {})
        self.assertEqual(self.t.crew_cargo, 4)

    def test_exact_json_restore_during_loading_delivery_and_passenger_losses_every_tick(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.cmd('crew_load')
        self.gm.step(.123456789)
        self.t.cargo_loss_accumulator = .123456789123
        initial = self.snapshot(self.st)
        restored = GameManager(GameState.from_dict(initial))
        self.assertEqual(self.snapshot(restored.state), initial)
        for i in range(120):
            if i == 40:
                for gm in (self.gm, restored):
                    transport = gm.state.entity(self.t.id)
                    transport.pos = Vec3(2000, 0, 140)
                    gm.state.queue_command(PlayerCommand.from_dict(PlayerCommand('crew_deliver', 0, unit_ids=(self.t.id,), target_id=self.target.id).to_dict()))
            if i == 70:
                for gm in (self.gm, restored):
                    gm.state.entity(self.t.id).systems['life_support'].hp = 0
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(self.snapshot(self.st), self.snapshot(restored.state), i)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), i)
        self.assertEqual(self.st.tick, initial['tick'] + 120)

    def test_recovery_order_does_not_finish_full_staffed_transport_before_reaching_base(self):
        self.target.pos = Vec3(2000, 0, 0)
        self.t.pos = Vec3(2000, 0, 300)
        self.cmd('crew_recover', self.base)
        self.gm.recovery.update(1)
        self.assertEqual(self.t.crew_mission.get('phase'), 'recover')
        for _ in range(900):
            self.gm.step(1 / 30)
        self.assertLessEqual(self.t.pos.dist(self.base.pos), self.base.radius + 600)
        self.assertEqual(self.t.crew_mission, {})

    def test_recorded_human_loading_and_delivery_replay_matches_every_real_tick(self):
        from game.net.replay import ReplayRecorder, ReplayPlayer
        self.target.pos = Vec3(0, 0, 1500)
        recorder = ReplayRecorder(self.st)
        for tick, cmd in [(1, PlayerCommand('crew_load', 0, unit_ids=(self.t.id,))),
                          (91, PlayerCommand('crew_cancel', 0, unit_ids=(self.t.id,))),
                          (92, PlayerCommand('crew_deliver', 0, unit_ids=(self.t.id,), target_id=self.target.id))]:
            recorder.on_command(cmd, tick)
        data = json.loads(json.dumps(recorder.to_dict()))
        replay = ReplayPlayer(data)
        restored = GameManager(GameState.from_dict(data['initial_state']))
        for tick in range(1, 701):
            for gm in (self.gm, restored):
                for cmd in replay.commands_for_tick(tick):
                    gm.state.queue_command(PlayerCommand.from_dict(cmd.to_dict()))
                gm.step(1 / 30)
            self.assertEqual(self.snapshot(self.st), self.snapshot(restored.state), tick)
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), tick)
        self.assertGreater(self.target.crew, 0)
        self.assertEqual(self.st.tick, 700)

    def test_mid_recovery_ai_restore_keeps_cadence_and_recovery_orders_exact(self):
        self.st.players[0].is_ai = True
        self.gm.ds.rules['ai']['strategic_interval'] = 10000
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(200, 0, 0))
        self.t.systems['life_support'].hp = 30
        self.gm.step(.123456789)
        for _ in range(10): self.gm.step(1 / 30)
        snapshot = self.snapshot(self.st)
        restored = GameManager(GameState.from_dict(snapshot))
        restored.ds.rules['ai']['strategic_interval'] = 10000
        self.assertEqual(snapshot, self.snapshot(restored.state))
        for i in range(150):
            self.gm.step(1 / 30); restored.step(1 / 30)
            self.assertEqual(self.snapshot(self.st), self.snapshot(restored.state), i)


if __name__ == '__main__':
    unittest.main()
