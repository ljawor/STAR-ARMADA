"""Authoritative construction spacing, reservations and knowledge boundaries."""
import unittest

from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.construction import ConstructionSystem
from game.systems.unit_factory import UnitFactory


class ConstructionExclusionTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.st = GameState()
        self.st.players[0] = PlayerState(0, credits=100000, materials=100000,
                                         energy=100000, crew=100000, command_capacity=100)
        self.st.players[1] = PlayerState(1)
        self.factory = UnitFactory(self.st)
        self.builder = self.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.cs = ConstructionSystem(self.st)
        self.cs.factory = self.factory
        self.st._construction_system = self.cs

    def test_ai_boarding_accepts_favorable_shields_down_target_with_healthy_subsystems(self):
        from game.ai.ai import AIPlayer
        from game.core.manager import GameManager
        gm = GameManager(state=self.st)
        gm.factory.spawn_station('command_station', 0, Vec3(-10000, 0, 0))
        source = gm.factory.spawn_ship('imperial_frigate', 0, Vec3(5000, 0, 0))
        target = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(5200, 0, 0))
        target.crew = 1  # doctrine still needs a favorable party/defender ratio
        target.shields = {q: 0.0 for q in target.shields}
        self.assertEqual(target.subsystem_fraction('engines'), 1)
        self.assertEqual(target.subsystem_fraction('weapons'), 1)
        self.st.tick = 3
        ai = AIPlayer(self.st, 0)
        ai.tactical_tick(1 / 30)
        self.assertTrue(any(c.type == 'board' and c.unit_ids == (source.id,)
                            and c.target_id == target.id for c in self.st.command_queue))

    def test_real_commands_enforce_paid_spacing_and_restore_boundary_completion(self):
        import json
        from game.core.commands import PlayerCommand
        from game.core.manager import GameManager
        gm = GameManager(state=self.st)
        gm.factory.spawn_station('command_station', 0, Vec3(-10000, 0, 0))
        gm.factory.spawn_station('command_station', 1, Vec3(10000, 0, 0))
        near = gm.factory.spawn_ship('imperial_constructor', 0, Vec3(1000, 0, 0))
        edge = gm.factory.spawn_ship('imperial_constructor', 0, Vec3(1500, 0, 0))
        for source in (self.builder, near, edge):
            self.st.queue_command(PlayerCommand('build_station', 0, unit_ids=(source.id,),
                station_kind='trade_station', target_pos=(source.pos.x, source.pos.y, source.pos.z)))
        gm.step(1 / 30)
        self.assertEqual(len(self.builder.build_queue), 1)
        self.assertEqual(near.build_queue, [])
        self.assertEqual(len(edge.build_queue), 1)
        cost = gm.factory.station_build_cost('trade_station')['credits']
        self.assertEqual(self.st.stats['0']['credits_spent'], cost * 2)
        for source in (self.builder, edge):
            source.build_queue[0]['time_left'] = .001
        snapshot = lambda st: json.loads(json.dumps(st.to_dict(precise=True)))
        data = snapshot(self.st)
        restored = GameManager(state=GameState.from_dict(data))
        self.assertEqual(data, snapshot(restored.state))
        for _ in range(3):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.st), snapshot(restored.state))
        markets = [e for e in self.st.entities.values() if e.data_id == 'trade_station']
        self.assertEqual(len(markets), 2)
        self.assertEqual(markets[0].pos.dist(markets[1].pos), 1500)

    def test_real_command_revalidates_hidden_center_appearing_after_preview(self):
        from game.core.commands import PlayerCommand
        from game.core.manager import GameManager
        gm = GameManager(state=self.st)
        gm.factory.spawn_station('command_station', 0, Vec3(-10000, 0, 0))
        self.builder.pos = Vec3(2000, 0, 0)
        self.builder.sensor_range = 0
        self.assertTrue(gm.construction.check_site('shipyard', self.builder.pos, self.builder, viewer=0)[0])
        gm.factory.spawn_station('command_station', 1, Vec3())
        self.st.queue_command(PlayerCommand('build_station', 0, unit_ids=(self.builder.id,),
            station_kind='shipyard', target_pos=(2000, 0, 0)))
        gm.step(1 / 30)
        self.assertEqual(self.builder.build_queue, [])
        self.assertEqual(self.st.stats.get('0', {}).get('credits_spent', 0), 0)
        self.assertIn('Cannot build: site unavailable', [t['text'] for t in self.st.floating_texts])

    def test_enemy_private_queued_market_does_not_change_preview(self):
        self.builder.pos = Vec3(1000, 0, 0)
        enemy = self.factory.spawn_ship('imperial_constructor', 1, Vec3(1200, 0, 0))
        self.assertTrue(self.st.can_see(0, enemy.id))
        expected = self.cs.check_site('trade_station', self.builder.pos, self.builder, viewer=0)
        enemy.build_queue.append(dict(kind='station', item='trade_station', pos=[0, 0, 0], status='paid'))
        self.assertEqual(expected, self.cs.check_site('trade_station', self.builder.pos, self.builder, viewer=0))
        self.assertFalse(self.cs.check_site('trade_station', self.builder.pos, self.builder)[0])

    def test_configurable_minimums_and_live_only_hostile_center_exclusion(self):
        economy = DataStore.get().rules['economy']
        economy['trade_station_min_distance'] = 2000
        economy['enemy_command_build_min_distance'] = 4000
        market = self.factory.spawn_station('trade_station', 0, Vec3())
        self.assertFalse(self.cs.check_site('trade_station', Vec3(1999, 0, 0), self.builder)[0])
        self.assertTrue(self.cs.check_site('trade_station', Vec3(2000, 0, 0), self.builder)[0])
        market.alive = False
        center = self.factory.spawn_station('command_station', 1, Vec3())
        self.assertFalse(self.cs.check_site('shipyard', Vec3(3999, 0, 0), self.builder)[0])
        self.assertTrue(self.cs.check_site('shipyard', Vec3(4000, 0, 0), self.builder)[0])
        center.alive = False
        enemy = self.factory.spawn_ship('imperial_constructor', 1, Vec3())
        enemy.build_queue.append(dict(kind='station', item='command_station', pos=[0, 0, 0], status='paid'))
        self.assertTrue(self.cs.check_site('shipyard', Vec3(2000, 0, 0), self.builder)[0])

    def test_ai_arrival_keeps_market_accounted_for_before_command_consumption(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        self.builder.pos = Vec3(7000, 0, 0)
        ai._pending_site[self.builder.id] = ('trade_station', self.builder.pos.copy())
        self.assertEqual(ai._count_stations('trade_station'), 1)
        ai._flush_pending_sites()
        self.assertEqual(ai._pending_site, {})
        self.assertEqual(len(self.st.command_queue), 1)
        self.assertEqual(ai._count_stations('trade_station'), 1)

    def test_ai_never_reserves_illegal_far_site_and_releases_newly_blocked_pending(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        site = Vec3(7000, 0, 0)
        center = self.factory.spawn_station('command_station', 1, site + Vec3(2000, 0, 0))
        ai._queue_build(self.builder, 'trade_station', site)
        self.assertEqual(ai._pending_site, {})
        self.assertEqual(self.st.command_queue, [])
        center.alive = False
        ai._queue_build(self.builder, 'trade_station', site)
        self.assertIn(self.builder.id, ai._pending_site)
        center.alive = True
        self.st.command_queue.clear()
        ai._flush_pending_sites()
        self.assertEqual(ai._pending_site, {})
        self.assertEqual(self.st.command_queue, [])

    def test_ai_trade_sites_reserve_unpaid_travel_and_unconsumed_commands(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        home = self.factory.spawn_station('command_station', 0, Vec3())
        first = ai._find_station_site('trade_station', 900, home, self.builder)
        self.assertIsNotNone(first)
        other = self.factory.spawn_ship('imperial_constructor', 0, Vec3())
        for reservation in ('pending', 'command'):
            with self.subTest(reservation=reservation):
                ai._pending_site.clear()
                self.st.command_queue.clear()
                if reservation == 'pending':
                    ai._pending_site[self.builder.id] = ('trade_station', first)
                else:
                    from game.core.commands import PlayerCommand
                    self.st.queue_command(PlayerCommand('build_station', 0,
                        unit_ids=(self.builder.id,), station_kind='trade_station',
                        target_pos=(first.x, first.y, first.z)))
                second = ai._find_station_site('trade_station', 900, home, other)
                self.assertIsNotNone(second)
                self.assertGreaterEqual(first.dist(second), 1500)
                self.assertTrue(self.cs.check_site('trade_station', second, other)[0])

    def test_midbuild_hostile_center_cancels_completion_without_refund(self):
        for kind in ('station', 'satellite'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'station':
                    self.assertTrue(self.cs.start_station(self.builder.id, 'trade_station', Vec3(), 0))
                    source = self.builder
                else:
                    source = self.planet()
                    self.assertTrue(self.cs.start_satellite(source.id, 'attack_satellite', 0))
                bank = self.st.players[0].credits
                site = Vec3(*source.build_queue[0]['pos'])
                self.factory.spawn_station('command_station', 1, site + Vec3(2000, 0, 0))
                source.build_queue[0]['time_left'] = .001
                self.cs.update(.1)
                self.assertEqual(source.build_queue, [])
                self.assertEqual(bank, self.st.players[0].credits)
                self.assertFalse(any(e.data_id in ('trade_station', 'attack_satellite')
                                     for e in self.st.entities.values()))

    def test_existing_shipyard_production_survives_hostile_center_proximity(self):
        yard = self.factory.spawn_station('shipyard', 0, Vec3())
        self.factory.spawn_station('command_station', 1, Vec3(2000, 0, 0))
        self.assertEqual(self.cs.start_ship(yard.id, 'imperial_corvette', 0), 1)
        yard.build_queue[0]['time_left'] = .001
        self.cs.update(.1)
        self.assertTrue(yard.alive)
        self.assertTrue(any(e.data_id == 'imperial_corvette' for e in self.st.entities.values()))

    def planet(self):
        planet = self.factory.spawn_planet(dict(id='test', type='temperate', pos=[0, 0, 0], radius=600))
        planet.colonized_by = 0
        return planet

    def test_satellite_exact_hostile_boundary_and_paid_site_obstruction(self):
        planet = self.planet()
        site0 = self.cs.satellite_site(planet, 'defense_satellite', 0)
        center = self.factory.spawn_station('command_station', 1, site0 + Vec3(0, 0, 3000))
        self.assertEqual(site0.dist(center.pos), 3000)
        from game.systems.colonies import colony_rules
        legal = [slot for slot in range(1, colony_rules()['satellite_cap'])
                 if self.cs.satellite_site(planet, 'defense_satellite', slot).dist(center.pos) >= 3000]
        self.assertTrue(legal)
        # A paid ordinary site blocks slot 0 independently of the boundary.
        self.builder.build_queue.append(dict(kind='station', item='trade_station',
            pos=site0.to_dict(precise=True), status='paid', time_left=100, total=100))
        self.assertTrue(self.cs.start_satellite(planet.id, 'defense_satellite', 0))
        self.assertEqual(planet.build_queue[0]['slot'], legal[0])
        self.assertGreaterEqual(Vec3(*planet.build_queue[0]['pos']).dist(center.pos), 3000)
        planet.build_queue.clear()
        self.builder.build_queue.clear()
        self.assertTrue(self.cs.start_satellite(planet.id, 'defense_satellite', 0))
        self.assertEqual(planet.build_queue[0]['slot'], 0)

    def test_satellite_search_checks_hostile_exclusion_at_every_slot(self):
        from game.systems.colonies import colony_rules
        planet = self.planet()
        center = self.factory.spawn_station('command_station', 1, Vec3(0, 0, 2500))
        center.crew = 0
        cap = colony_rules()['satellite_cap']
        legal = [slot for slot in range(cap)
                 if self.cs.satellite_site(planet, 'attack_satellite', slot).dist(center.pos) >= 3000]
        self.assertTrue(legal)
        self.assertNotEqual(legal[0], 0)
        self.assertTrue(self.cs.start_satellite(planet.id, 'attack_satellite', 0))
        self.assertEqual(planet.build_queue[0]['slot'], legal[0])
        self.assertGreaterEqual(Vec3(*planet.build_queue[0]['pos']).dist(center.pos), 3000)

    def test_hostile_command_blocks_entire_satellite_ring_without_spending(self):
        planet = self.planet()
        self.factory.spawn_station('command_station', 1, planet.pos)
        bank = self.st.players[0].credits
        for kind in ('attack_satellite', 'defense_satellite'):
            self.assertFalse(self.cs.start_satellite(planet.id, kind, 0))
            self.assertEqual(bank, self.st.players[0].credits)
            self.assertEqual(planet.build_queue, [])

    def test_nonfinite_coordinates_never_preview_or_start(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            for axis in range(3):
                with self.subTest(value=value, axis=axis):
                    coords = [0, 0, 0]
                    coords[axis] = value
                    pos = Vec3(*coords)
                    self.assertFalse(self.cs.check_site('shipyard', pos, self.builder)[0])
                    self.assertFalse(self.cs.check_site('shipyard', pos, self.builder, viewer=0)[0])
                    bank = self.st.players[0].credits
                    self.assertFalse(self.cs.start_station(self.builder.id, 'shipyard', pos, 0))
                    self.assertEqual(bank, self.st.players[0].credits)
                    self.assertEqual(self.builder.build_queue, [])

    def test_hostile_command_excludes_all_new_stations_at_strict_boundary(self):
        center = self.factory.spawn_station('command_station', 1, Vec3())
        center.crew = 0
        for kind in DataStore.get().ships[self.builder.data_id].can_build_stations:
            with self.subTest(kind=kind):
                ok, reason = self.cs.check_site(kind, Vec3(2999.99, 0, 0), self.builder)
                self.assertFalse(ok)
                self.assertEqual(reason, 'too close to hostile command station')
        self.assertTrue(self.cs.check_site('shipyard', Vec3(3000, 0, 0), self.builder)[0])
        center.owner = 0
        self.assertTrue(self.cs.check_site('shipyard', Vec3(2000, 0, 0), self.builder)[0])
        center.owner = 1
        self.st.players[0].team = self.st.players[1].team = 5
        self.assertTrue(self.cs.check_site('shipyard', Vec3(2000, 0, 0), self.builder)[0])
        self.st.players[1].team = 6
        center.alive = False
        self.assertTrue(self.cs.check_site('shipyard', Vec3(2000, 0, 0), self.builder)[0])

    def test_hidden_command_preview_is_invariant_and_order_rejects_generically(self):
        self.builder.sensor_range = 0
        self.builder.pos = Vec3(2000, 0, 0)
        site = self.builder.pos.copy()
        expected = self.cs.check_site('shipyard', site, self.builder, viewer=0)
        self.factory.spawn_station('command_station', 1, Vec3())
        self.assertEqual(expected, (True, ''))
        self.assertEqual(expected, self.cs.check_site('shipyard', site, self.builder, viewer=0))
        bank = self.st.players[0].credits
        self.assertFalse(self.cs.start_station(self.builder.id, 'shipyard', site, 0))
        self.assertEqual(bank, self.st.players[0].credits)
        self.assertEqual(self.st.floating_texts[-1]['text'], 'Cannot build: site unavailable')

    def test_paid_trade_reservations_across_constructor_queues(self):
        for owner in (0, 1):
            with self.subTest(owner=owner):
                other = self.factory.spawn_ship('imperial_constructor', owner, Vec3(9000, 0, 0))
                other.build_queue.append(dict(kind='station', item='trade_station',
                    pos=[0, 0, 0], status='paid', time_left=100, total=100))
                self.assertFalse(self.cs.check_site('trade_station', Vec3(1499, 0, 0), self.builder)[0])
                self.assertTrue(self.cs.check_site('trade_station', Vec3(1500, 0, 0), self.builder)[0])
                other.build_queue[0]['status'] = 'unpaid'
                self.assertTrue(self.cs.check_site('trade_station', Vec3(1499, 0, 0), self.builder)[0])
                other.build_queue.clear()

    def test_second_trade_order_cannot_bypass_paid_reservation(self):
        self.assertTrue(self.cs.start_station(self.builder.id, 'trade_station', Vec3(), 0))
        other = self.factory.spawn_ship('imperial_constructor', 0, Vec3(1000, 0, 0))
        before = self.st.players[0].credits
        self.assertFalse(self.cs.start_station(other.id, 'trade_station', other.pos, 0))
        self.assertEqual(before, self.st.players[0].credits)
        self.assertEqual(other.build_queue, [])
        self.assertFalse(self.cs.start_station(self.builder.id, 'trade_station', Vec3(1600, 0, 0), 1))

    def test_trade_spacing_any_owner_live_derelict_and_exact_boundary(self):
        market = self.factory.spawn_station('trade_station', 0, Vec3())
        market.crew = 0  # alive physical hardware still occupies the site
        self.st.players[2] = PlayerState(2, team=0)
        for owner in (0, 1, 2):
            market.owner = owner
            with self.subTest(owner=owner):
                self.assertFalse(self.cs.check_site('trade_station', Vec3(1499.99, 0, 0), self.builder)[0])
                self.assertTrue(self.cs.check_site('trade_station', Vec3(1500, 0, 0), self.builder)[0])
                self.assertTrue(self.cs.check_site('trade_station', Vec3(0, 1500, 0), self.builder)[0])
        market.alive = False
        self.assertTrue(self.cs.check_site('trade_station', Vec3(1499, 0, 0), self.builder)[0])
