import unittest
from helpers import make_game
from game.core.vectors import Vec3
from game.systems import stats


class StaffingTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.e = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())

    def test_half_complement_scales_speed_turn_damage_and_live_sensor_cache_once(self):
        e = self.e
        functions = [lambda: stats.effective_speed(self.st, e),
                     lambda: stats.effective_turn_rate(self.st, e),
                     lambda: stats.effective_weapon_damage(self.st, e, 100),
                     lambda: stats.effective_sensor_range(self.st, e)]
        full = [f() for f in functions]
        observer = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(full[-1] * .75, 0, 0))
        self.assertTrue(self.st.can_see(0, observer.id))
        e.crew = e.max_crew // 2
        e.crew_cargo = 240
        for before, fn in zip(full, functions):
            self.assertAlmostEqual(fn(), before * .5)
        self.assertFalse(self.st.can_see(0, observer.id))
        self.assertEqual(e.subsystem_fraction('life_support'), 1)
        e.crew = 0
        self.assertTrue(all(f() == 0 for f in functions))

    def test_half_staffed_producers_research_and_external_repairs_run_half_rate(self):
        base = self.gm.factory.spawn_station('command_station', 0, Vec3(5000, 0, 0))
        base.crew //= 2
        for e in list(self.st.entities.values()):
            if e is not base and e.is_station and e.owner == 0:
                e.crew = 0
        self.gm.economy.update(1)
        for resource, rate in self.gm.ds.stations['command_station'].income.items():
            self.assertEqual(self.st.players[0].income_frame[resource], rate * .5)
        yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(5000, 0, 2000))
        yard.crew //= 2
        self.assertTrue(self.gm.construction.start_ship(yard.id, 'imperial_crew_transport', 0))
        before = yard.build_queue[0]['time_left']
        self.gm.construction.update(1)
        self.assertEqual(before - yard.build_queue[0]['time_left'], .5)
        lab = self.gm.factory.spawn_station('research_station', 0, Vec3())
        lab.crew //= 2
        tid = self.gm.research.available_techs(0)[0]
        self.assertTrue(self.gm.research.start_research(0, lab.id, tid))
        info = self.st.players[0].researching[tid]
        before = info['time_left']
        self.gm.research.update(1)
        self.assertEqual(before - info['time_left'], .5)
        dock = self.gm.factory.spawn_station('repair_dock', 0, Vec3(3000, 0, 0))
        dock.crew //= 2
        self.e.pos = Vec3(3100, 0, 0)
        self.e.hull -= 500
        self.e.systems['life_support'].hp = 0
        self.st.grid.rebuild(self.st.entities)
        before = self.e.hull
        self.gm.economy.update(1)
        self.assertEqual(self.e.hull - before, self.gm.ds.stations['repair_dock'].repair_rate * .5)
        self.assertEqual(self.e.subsystem_hp('life_support'), self.gm.ds.stations['repair_dock'].repair_rate * .5)
        dock.crew = 0
        helper = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(3000, 0, 0))
        helper.crew //= 2
        before = self.e.hull
        self.gm.abilities._tick_active(helper, 'repair_drones', 1)
        self.assertEqual(self.e.hull - before, self.gm.ds.abilities['repair_drones'].effects['repair_hps'] * .5)

    def test_hangar_repairs_and_reinforcement_scale_provider_complement(self):
        carrier = self.gm.factory.spawn_ship('imperial_supercapital', 0, Vec3(3000, 0, 0))
        squad = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3(3100, 0, 0))
        squad.hangar_id = carrier.id
        squad.hull = squad.max_hull / 2
        squad.fighter_count = 1
        self.gm.squadrons._reinforce_and_repair(squad, 1)
        full_repair, full_reinforce = squad.hull - squad.max_hull / 2, squad.fighter_count - 1
        squad.hull = squad.max_hull / 2
        squad.fighter_count = 1
        carrier.crew //= 2
        self.gm.squadrons._reinforce_and_repair(squad, 1)
        self.assertAlmostEqual(squad.hull - squad.max_hull / 2, full_repair * .5)
        self.assertAlmostEqual(squad.fighter_count - 1, full_reinforce * .5)

    def test_auxiliary_hull_movement_uses_same_staffing_stat(self):
        from game.core.entity import Entity
        for data_id, full in [('trade_convoy', self.gm.ds.rules['economy']['trading']['speed']),
                              ('boarding_craft', self.gm.ds.rules['boarding']['craft_speed'])]:
            e = Entity(999, 'ship', 0, data_id, is_ship=True, crew=5, max_crew=10)
            self.assertAlmostEqual(stats.effective_speed(self.st, e), full * .5)


if __name__ == '__main__':
    unittest.main()
