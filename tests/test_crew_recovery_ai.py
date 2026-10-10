import unittest
from helpers import make_game
from game.ai.ai import AIPlayer
from game.core.vectors import Vec3


class RecoveryAITests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ai = AIPlayer(self.st, 0)
        self.base = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(300, 0, 0))
        self.e = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(2000, 0, 0))
        self.st.tick = 3

    def test_failing_support_queues_authoritative_recovery_to_repair_dock(self):
        self.e.systems['life_support'].hp *= .3
        before = self.e.pos.to_dict()
        self.ai.tactical_tick(.2)
        cmds = [c for c in self.st.command_queue if c.type == 'crew_recover' and self.e.id in c.unit_ids]
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].target_id, self.dock.id)
        self.assertEqual(self.e.order_type, 'idle')
        self.gm.commands.consume()
        self.assertEqual(self.e.crew_mission['phase'], 'recover')
        self.assertEqual(self.e.pos.to_dict(), before)
        self.assertNotIn(self.e, self.ai.my_units())

    def test_boarding_only_favourable_detected_disabled_enemies(self):
        enemy = self.gm.factory.spawn_ship('imperial_frigate', 1, Vec3(2100, 0, 0))
        enemy.crew = 0
        enemy.shields = {q: 0 for q in enemy.shields}
        self.gm.visibility.update()
        self.ai.tactical_tick(.2)
        cmds = [c for c in self.st.command_queue if c.type == 'board' and self.e.id in c.unit_ids]
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].target_id, enemy.id)
        self.st.command_queue.clear()
        enemy.pos = Vec3(12000, 0, 12000)
        self.e.order_type = 'idle'
        self.ai.tactical_tick(.2)
        self.assertFalse(any(c.type == 'board' for c in self.st.command_queue))
        enemy.pos = Vec3(2100, 0, 0)
        enemy.crew = enemy.max_crew
        enemy.systems['engines'].hp = 0
        self.ai.tactical_tick(.2)
        self.assertFalse(any(c.type == 'board' and self.e.id in c.unit_ids for c in self.st.command_queue))

    def test_transport_ai_loads_then_delivers_to_safe_owned_stranded_hull(self):
        t = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 250))
        self.e.crew = 0
        self.ai.tactical_tick(.2)
        self.assertTrue(any(c.type == 'crew_load' and t.id in c.unit_ids for c in self.st.command_queue))
        self.gm.commands.consume()
        self.gm.recovery.update(1)
        self.assertEqual(t.crew_cargo, 4)
        self.gm.recovery.cancel(t)
        self.st.command_queue.clear()
        self.ai.tactical_tick(.2)
        self.assertTrue(any(c.type == 'crew_deliver' and c.target_id == self.e.id for c in self.st.command_queue))

    def test_strategic_logistics_produces_missing_transport_for_safe_derelict(self):
        self.e.crew = 0
        yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(800, 0, 0))
        self.ai._ensure_crew_logistics(self.base)
        cmds = [c for c in self.st.command_queue if c.type == 'build_ship' and c.ship_id == 'imperial_crew_transport']
        self.assertEqual(len(cmds), 1)
        chosen = self.st.entity(cmds[0].unit_ids[0])
        self.assertEqual(chosen.data_id, 'shipyard')
        self.assertEqual(chosen.owner, 0)
        self.gm.commands.consume()
        self.st.command_queue.clear()
        self.ai._ensure_crew_logistics(self.base)
        self.assertFalse(any(c.ship_id == 'imperial_crew_transport' for c in self.st.command_queue))

    def test_failing_support_requests_existing_constructor_repair_infrastructure(self):
        self.dock.alive = False
        for e in self.st.entities.values():
            if e.owner == 0 and e.data_id == 'repair_dock':
                e.alive = False
        self.e.systems['life_support'].hp = 40
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3(400, 0, 0))
        self.ai._ensure_crew_logistics(self.base)
        self.assertTrue(any(c.type == 'build_station' and c.station_kind == 'repair_dock'
                            for c in self.st.command_queue))

    def test_logistics_and_deployed_boarders_are_not_retasked_as_combat_fleet(self):
        t = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3())
        self.e.boarding_party_id = 999
        self.assertNotIn(t, self.ai.my_units())
        self.assertNotIn(self.e, self.ai.my_units())


if __name__ == '__main__':
    unittest.main()
