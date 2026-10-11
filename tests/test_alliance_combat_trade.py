"""Allied nonaggression and authoritative own/allied commercial routes."""
import unittest

from helpers import make_game
from game.core.commands import AttackCommand, PlayerCommand
from game.core.state import GameState, PlayerState
from game.core.manager import GameManager
from game.core.vectors import Vec3


class AllianceCombatTradeTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.st.players[0].team = self.st.players[1].team = 0
        self.st.players[2] = PlayerState(2, team=1)
        # Keep victory active without combat near the commerce fixtures.
        for pid, x in ((0, -10000), (1, -8000), (2, 10000)):
            self.gm.factory.spawn_station('command_station', pid, Vec3(x, 0, 10000))
        self.gm.trading.cfg['spawn_interval'] = 100000

    def market(self, owner, x, z=0):
        return self.gm.factory.spawn_station('trade_station', owner, Vec3(x, 0, z))

    def test_auto_route_ignores_closest_enemy_market(self):
        src = self.market(0, 0)
        self.market(2, 100)
        ally = self.market(1, 1000)
        self.gm.trading._spawn_convoys()
        convoy = next(e for e in self.st.entities.values()
                      if e.data_id == 'trade_convoy' and e.owner == 0)
        self.assertEqual(convoy.convoy_dest, ally.id)


    def test_nearest_market_tie_uses_lowest_id(self):
        src = self.market(0, 0)
        low = self.market(1, 1000)
        high = self.market(0, -1000)
        # Dictionary insertion order is not the route tie-breaker.
        self.st.entities.pop(low.id)
        self.st.entities[low.id] = low
        self.gm.trading._spawn_convoys()
        convoy = next(e for e in self.st.entities.values()
                      if e.data_id == 'trade_convoy' and e.owner == src.owner)
        self.assertEqual(convoy.convoy_dest, low.id)

    def test_only_enemy_market_has_no_fallback_convoy(self):
        self.market(0, 0)
        self.market(2, 1000)
        self.gm.trading._spawn_convoys()
        self.assertFalse([e for e in self.st.entities.values()
                          if e.data_id == 'trade_convoy'])


    def test_persisted_hostile_route_is_cancelled_before_first_movement(self):
        src = self.market(0, 0)
        hostile = self.market(2, 1000)
        convoy = self.gm.trading._make_convoy(src, hostile, 150, 250)
        convoy.pos = Vec3(1000, 0, -500)
        convoy.vel = Vec3(0, 0, 40)
        del self.st.entities[src.id]
        restored = GameManager(GameState.from_dict(self.st.to_dict(precise=True)))
        restored.trading.cfg['spawn_interval'] = 100000
        c = restored.state.entity(convoy.id)
        assert c is not None
        before = c.pos.to_dict(precise=True)
        arrived = []
        restored.state.events.subscribe('convoy_arrived', lambda e: arrived.append(e.data))
        restored.step(1 / 30)
        self.assertEqual(c.pos.to_dict(precise=True), before)
        self.assertIsNone(c.convoy_dest)
        self.assertIsNone(c.order_target_id)
        self.assertEqual(c.order_type, 'idle')
        self.assertEqual(c.vel.length(), 0)
        self.assertFalse(arrived)


    def test_saved_legal_destination_repairs_hidden_movement_endpoint(self):
        for endpoint_kind in ('hostile_market', 'nonmarket'):
            with self.subTest(endpoint_kind=endpoint_kind):
                self.setUp()
                src = self.market(0, 0)
                ally = self.market(1, 0, -2000)
                enemy = (self.market(2, 0, 2000) if endpoint_kind == 'hostile_market'
                         else self.gm.factory.spawn_ship('imperial_corvette', 2, Vec3(0, 0, 2000)))
                c = self.gm.trading._make_convoy(src, ally, 150, 250)
                c.order_target_id = enemy.id
                c.order_target_pos = enemy.pos.copy()
                c.vel = Vec3(0, 0, 50)
                for e in self.st.entities.values():
                    e.sensor_range = 0
                gm = GameManager(GameState.from_dict(self.st.to_dict(precise=True)))
                gm.trading.cfg['spawn_interval'] = 100000
                restored = gm.state.entity(c.id)
                assert restored is not None
                self.assertFalse(gm.state.can_see(0, enemy.id))
                gm.step(1 / 30)
                self.assertEqual(restored.order_target_id, ally.id)
                self.assertIsNone(restored.order_target_pos)
                self.assertLess(restored.pos.z, 0)
                self.assertLessEqual(restored.vel.z, 0)

    def test_visibility_does_not_exempt_unvalidated_convoy_market_order(self):
        from game.systems.weapons import clear_unseen_targets
        src = self.market(0, 0)
        ally = self.market(1, -2000)
        enemy = self.market(2, 2000)
        c = self.gm.trading._make_convoy(src, ally, 150, 250)
        c.order_target_id = enemy.id
        c.order_target_pos = enemy.pos.copy()
        for e in self.st.entities.values():
            e.sensor_range = 0
        clear_unseen_targets(self.st, c)
        self.assertIsNone(c.order_target_id)
        self.assertIsNone(c.order_target_pos)
        self.assertEqual(c.order_type, 'idle')

    def test_manual_route_cannot_deliver_back_to_source_at_spawn(self):
        src = self.market(0, 0)
        ally = self.market(1, 0, 1800)
        c = self.gm.trading._make_convoy(src, ally, 150, 250)
        arrivals = []
        self.st.events.subscribe('convoy_arrived', lambda ev: arrivals.append(dict(ev.data)))
        credits = {pid: p.credits for pid, p in self.st.players.items()}
        self.st.command_queue.append(PlayerCommand('trade_route', 0, unit_ids=(c.id,), target_id=src.id))
        self.gm.commands.consume()
        self.gm.trading.update(0)
        self.assertEqual({pid: p.credits for pid, p in self.st.players.items()}, credits)
        self.assertFalse(arrivals)
        self.assertTrue(c.alive)
        self.assertEqual(c.convoy_dest, ally.id)

    def test_source_identity_precise_snapshot_and_lan_checksum(self):
        import json
        from dataclasses import fields
        from game.core.entity import Entity
        from game.net.lan import precise_checksum
        src = self.market(0, 0)
        ally = self.market(1, 0, 1800)
        c = self.gm.trading._make_convoy(src, ally, 150.123456789, 250)
        self.assertIn('convoy_source', {f.name for f in fields(Entity)})
        self.assertEqual(c.convoy_source, src.id)
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        self.assertIsNone(ship.convoy_source)
        self.gm.visibility.update()
        snapshot = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored_state = GameState.from_dict(snapshot)
        self.assertEqual(json.loads(json.dumps(restored_state.to_dict(precise=True))), snapshot)
        restored = GameManager(restored_state)
        restored_convoy = restored.state.entity(c.id)
        assert restored_convoy is not None
        self.assertEqual(restored_convoy.convoy_source, src.id)
        checksum = precise_checksum(self.gm)
        c.convoy_source = ally.id
        self.assertNotEqual(checksum, precise_checksum(self.gm))
        c.convoy_source = src.id
        self.assertEqual(checksum, precise_checksum(self.gm))

    def test_auto_fallback_excludes_source_market_without_payment(self):
        for route_kind in ('captured_destination', 'saved_source_destination'):
            with self.subTest(route_kind=route_kind):
                self.setUp()
                src = self.market(0, 0)
                ally = self.market(1, 0, 1800)
                c = self.gm.trading._make_convoy(src, ally, 150, 250)
                ally.owner = 2
                if route_kind == 'saved_source_destination':
                    c.convoy_dest = c.order_target_id = src.id
                credits = {pid: p.credits for pid, p in self.st.players.items()}
                arrivals = []
                self.st.events.subscribe('convoy_arrived', lambda ev: arrivals.append(dict(ev.data)))
                self.gm.commands.consume()
                self.gm.trading.update(0)
                self.assertIsNone(c.convoy_dest)
                self.assertIsNone(c.order_target_id)
                self.assertEqual(c.order_type, 'idle')
                self.assertEqual({pid: p.credits for pid, p in self.st.players.items()}, credits)
                self.assertFalse(arrivals)
                # A new distinct allied endpoint may resume known-source cargo.
                other = self.market(1, 0, -1800)
                self.gm.step(1 / 30)
                self.assertEqual(c.convoy_dest, other.id)
                self.assertLess(c.pos.z, 0)

    def test_legacy_unknown_source_restores_but_cannot_create_payment_route(self):
        src = self.market(0, 0)
        ally = self.market(1, 0, 1800)
        c = self.gm.trading._make_convoy(src, ally, 150, 250)
        c.pos = ally.pos.copy()
        snapshot = self.st.to_dict(precise=True)
        # Real pre-source saves also predate the authoritative runtime graph.
        snapshot.pop('runtime_state')
        for saved in snapshot['entities'].values():
            saved.pop('convoy_source', None)
        gm = GameManager(GameState.from_dict(snapshot))
        gm.trading.cfg['spawn_interval'] = 100000
        convoy = gm.state.entity(c.id)
        assert convoy is not None
        self.assertIsNone(convoy.convoy_source)
        arrivals = []
        gm.state.events.subscribe('convoy_arrived', lambda ev: arrivals.append(dict(ev.data)))
        credits = {pid: p.credits for pid, p in gm.state.players.items()}
        gm.state.command_queue.append(PlayerCommand('trade_route', 0, unit_ids=(c.id,), target_id=src.id))
        gm.commands.consume()
        gm.trading.update(0)
        self.assertEqual({pid: p.credits for pid, p in gm.state.players.items()}, credits)
        self.assertFalse(arrivals)
        self.assertIsNone(convoy.convoy_dest)
        self.assertIsNone(convoy.order_target_id)
        self.assertIsNone(convoy.convoy_source)
        self.assertTrue(convoy.alive)
        self.assertEqual(convoy.order_type, 'idle')

    def test_manual_reroute_travels_new_heading_and_pays_exact_payer_once(self):
        for reward_owner in ('source', 'destination'):
            with self.subTest(reward_owner=reward_owner):
                self.setUp()
                src = self.market(0, 0)
                original = self.market(1, 0, 2000)
                dest = self.market(1, 0, -1800)
                c = self.gm.trading._make_convoy(src, original, 150, 250)
                c.vel = Vec3(0, 0, 50)
                self.gm.trading.cfg['reward_owner'] = reward_owner
                arrivals = []
                banks = []
                self.st.events.subscribe('convoy_arrived', lambda ev: arrivals.append(dict(ev.data)))
                # Observe banks after economy, immediately before real trading.
                trading_update = self.gm.trading.update
                def capture_banks(dt):
                    banks.append({pid: p.credits for pid, p in self.st.players.items()})
                    trading_update(dt)
                self.gm.trading.update = capture_banks
                self.st.command_queue.append(PlayerCommand('trade_route', 0, unit_ids=(c.id,), target_id=dest.id))
                self.gm.step(1 / 30)
                self.assertLess(c.pos.z, 0, 'reroute must clear old momentum before movement')
                self.assertFalse(arrivals)
                for _ in range(1800):
                    self.gm.step(1 / 30)
                    if arrivals:
                        break
                self.assertEqual(len(arrivals), 1)
                paid = 0 if reward_owner == 'source' else 1
                self.assertEqual(arrivals[0], dict(entity_id=c.id, owner=paid,
                                                 convoy_owner=0, dest=dest.id, cargo=150))
                for pid, p in self.st.players.items():
                    self.assertEqual(p.credits - banks[-1][pid], 150 if pid == paid else 0)
                self.assertFalse(c.alive)
                self.assertEqual(c.convoy_source, src.id)
                self.gm.step(1 / 30)
                self.assertEqual(len(arrivals), 1)

    def test_hostile_arrival_cannot_pay_even_without_command_tick(self):
        src = self.market(0, 0)
        hostile = self.market(2, 1000)
        c = self.gm.trading._make_convoy(src, hostile, 150, 250)
        c.pos = hostile.pos.copy()
        del self.st.entities[src.id]
        credits = self.st.players[2].credits
        arrived = []
        self.st.events.subscribe('convoy_arrived', lambda e: arrived.append(e.data))
        self.gm.trading.update(1 / 30)
        self.assertEqual(self.st.players[2].credits, credits)
        self.assertFalse(arrived)
        self.assertTrue(c.alive)
        self.assertIsNone(c.convoy_dest)


    def test_explicit_route_accepts_only_owned_convoy_and_live_friendly_market(self):
        src = self.market(0, 0)
        own = self.market(0, 1500)
        ally = self.market(1, 2500)
        hostile = self.market(2, 500)
        foreign = self.gm.trading._make_convoy(ally, src, 150, 250)
        c = self.gm.trading._make_convoy(src, own, 150, 250)
        self.gm.commands._apply(PlayerCommand('trade_route', 0, unit_ids=(c.id,), target_id=ally.id))
        self.assertEqual(c.convoy_dest, ally.id)
        self.assertEqual(c.order_target_id, ally.id)
        self.assertEqual(c.order_type, 'move')
        nonmarket = next(e for e in self.st.entities.values() if e.data_id == 'command_station')
        dead = self.market(1, 3000)
        dead.alive = False
        for invalid in (hostile.id, nonmarket.id, dead.id, 999999):
            self.gm.commands._apply(PlayerCommand('trade_route', 0, unit_ids=(c.id,), target_id=invalid))
            self.assertEqual(c.convoy_dest, ally.id)
        self.gm.commands._apply(PlayerCommand('trade_route', 0, unit_ids=(foreign.id,), target_id=own.id))
        self.assertEqual(foreign.convoy_dest, src.id)
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        self.gm.commands._apply(PlayerCommand('trade_route', 0, unit_ids=(ship.id,), target_id=ally.id))
        self.assertIsNone(ship.convoy_dest)
        self.assertEqual(ship.order_type, 'idle')


    def test_only_enemy_raid_produces_loot_and_event(self):
        seen = []
        self.st.events.subscribe('convoy_raided', lambda e: seen.append(e.data))
        for killer in (0, 1, -1):
            with self.subTest(killer=killer):
                credits = {pid: p.credits for pid, p in self.st.players.items()}
                self.st.events.publish('unit_destroyed', data_id='trade_convoy',
                                       entity_id=999, owner=0, killer_owner=killer,
                                       cargo_credits=150, pos=[0, 0, 0])
                self.assertEqual({pid: p.credits for pid, p in self.st.players.items()}, credits)
                self.assertFalse(seen)
        credits = self.st.players[2].credits
        self.st.events.publish('unit_destroyed', data_id='trade_convoy',
                               entity_id=999, owner=0, killer_owner=2,
                               cargo_credits=150, pos=[0, 0, 0])
        self.assertEqual(self.st.players[2].credits, credits + 75)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]['convoy_owner'], 0)


    def test_stale_allied_attack_lock_is_cleared_before_movement(self):
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(500, 0, 500))
        ship.order_type = 'attack'
        ship.current_target = ship.order_target_id = ally.id
        ship.order_target_pos = ally.pos.copy()
        self.st.grid.rebuild(self.st.entities)
        self.gm.movement.update(1 / 30)
        self.assertIsNone(ship.current_target)
        self.assertIsNone(ship.order_target_id)
        self.assertIsNone(ship.order_target_pos)
        self.assertEqual(ship.order_type, 'idle')
        self.assertEqual(ship.yaw, 0)


    def test_damage_queue_cannot_harm_friendly_even_if_queued_before_alliance(self):
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 500))
        snapshot = (ally.hull, dict(ally.shields), {k: v.hp for k, v in ally.systems.items()})
        for attacker, owner in ((ship, 2), (None, 0), (None, 1)):
            self.st.damage_queue.append(dict(target=ally, damage=10000,
                                            shield_mult=1, armor_mult=1, system_mult=1,
                                            attacker_entity=attacker, attacker_id=owner))
        self.gm.damage.update(0)
        self.assertEqual((ally.hull, dict(ally.shields), {k: v.hp for k, v in ally.systems.items()}), snapshot)
        self.assertTrue(ally.alive)
        self.assertEqual(ship.xp, 0)
        # Environmental/neutral damage remains physical, not a diplomatic attack.
        self.st.damage_queue.append(dict(target=ally, damage=10000,
                                        shield_mult=1, armor_mult=1, system_mult=1,
                                        attacker_entity=None, attacker_id=-2))
        self.gm.damage.update(0)
        self.assertFalse(ally.alive)


    def test_queued_beam_retains_source_for_nonaggression(self):
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 500))
        self.st.damage_queue.append(dict(target=ally, damage=10000, attacker=ship,
                                        shield_mult=1, armor_mult=1, system_mult=1))
        hull, shields = ally.hull, dict(ally.shields)
        self.gm.damage.update(0)
        self.assertEqual(ally.hull, hull)
        self.assertEqual(ally.shields, shields)
        self.assertTrue(ally.alive)


    def test_ai_does_not_select_known_allied_planet_without_colonized_by(self):
        from game.ai.ai import AIPlayer
        home = self.gm.factory.spawn_station('command_station', 0, Vec3())
        planet = self.gm.factory.spawn_planet(dict(id='ally', type='temperate',
                                                pos=[500, 0, 0], radius=100))
        planet.owner = 1
        planet.colonized_by = None
        self.assertTrue(self.st.can_see(0, planet.id))
        self.assertIsNone(AIPlayer(self.st, 0)._pick_colony_target(home))


    def test_real_manager_friendly_routes_spawn_travel_arrive_and_pay(self):
        for destination_owner in (0, 1):
            with self.subTest(destination_owner=destination_owner):
                self.setUp()
                src = self.market(0, 0)
                dest = self.market(destination_owner, 0, 1800)
                enemy = self.market(2, 100, 0)
                self.gm.trading.cfg['spawn_interval'] = .01
                arrivals = []
                self.st.events.subscribe('convoy_arrived', lambda e: arrivals.append(dict(e.data)))
                self.gm.step(1 / 30)
                self.gm.trading.cfg['spawn_interval'] = 100000
                c = next(e for e in self.st.entities.values()
                         if e.data_id == 'trade_convoy' and e.owner == 0
                         and e.order_target_id == dest.id)
                start = c.pos.to_dict(precise=True)
                credits = self.st.players[destination_owner].credits
                for _ in range(60):
                    self.gm.step(1 / 30)
                self.assertNotEqual(c.pos.to_dict(precise=True), start)
                for _ in range(1500):
                    self.gm.step(1 / 30)
                self.assertFalse(c.alive)
                delivered = [a for a in arrivals if a['entity_id'] == c.id]
                self.assertEqual(len(delivered), 1)
                self.assertEqual(delivered[0]['dest'], dest.id)
                self.assertEqual(delivered[0]['owner'], destination_owner)
                self.assertGreaterEqual(self.st.players[destination_owner].credits,
                                        credits + c.cargo_credits)
                self.assertFalse(any(a['dest'] == enemy.id for a in arrivals))

    def test_legacy_hostile_route_reroutes_before_movement(self):
        src = self.market(0, -3000)
        enemy = self.market(2, 0, 1000)
        ally = self.market(1, 0, -1000)
        c = self.gm.trading._make_convoy(src, enemy, 150, 250)
        c.pos = Vec3()
        c.yaw = 0
        c.vel = Vec3(0, 0, 50)
        self.gm.step(1 / 30)
        self.assertEqual(c.convoy_dest, ally.id)
        self.assertEqual(c.order_target_id, ally.id)
        self.assertLess(c.pos.z, 0, 'must not integrate even one hostile-bound tick')

    def test_nonmarket_endpoint_is_invalidated(self):
        src = self.market(0, 0)
        invalid = next(e for e in self.st.entities.values() if e.owner == 0)
        c = self.gm.trading._make_convoy(src, invalid, 150, 250)
        self.gm.commands.consume()
        self.assertIsNone(c.convoy_dest)
        self.assertIsNone(c.order_target_id)
        self.assertEqual(c.order_type, 'idle')

    def test_explicit_friendly_attack_is_rejected_without_replacing_orders(self):
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 500))
        ship.order_type = 'move'
        ship.order_target_pos = Vec3(1000, 0, 0)
        self.gm.commands._apply(AttackCommand(0, [ship.id], ally.id))
        self.assertEqual(ship.order_type, 'move')
        self.assertEqual(ship.order_target_pos.to_dict(), [1000, 0, 0])
        self.assertIsNone(ship.current_target)
        self.assertIsNone(ship.order_target_id)
        self.gm.commands._apply(AttackCommand(0, [ally.id], ship.id))
        self.assertEqual(ally.order_type, 'idle')

    def test_auto_weapons_and_ai_select_enemy_not_nearer_ally(self):
        from game.ai.ai import AIPlayer
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 200))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 2, Vec3(0, 0, 500))
        self.st.grid.rebuild(self.st.entities)
        self.assertIs(self.gm.weapons.find_target(ship, 1000), enemy)
        self.st.tick = 3
        AIPlayer(self.st, 0).tactical_tick(.2)
        self.assertEqual(ship.current_target, enemy.id)
        self.gm.weapons._ship_weapons(ship, 1 / 30)
        self.assertTrue(self.st.projectiles)
        self.assertTrue(all(p.target_id != ally.id for p in self.st.projectiles.values()))

    def test_squadron_clears_allied_lock_between_tactical_ticks(self):
        sq = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, Vec3(0, 0, 200))
        sq.order_type = 'attack'
        sq.order_target_id = sq.current_target = ally.id
        self.st.grid.rebuild(self.st.entities)
        self.gm.squadrons.update(.01)
        self.assertEqual(sq.order_type, 'idle')
        self.assertIsNone(sq.current_target)
        self.assertIsNone(sq.order_target_id)
        self.gm.squadrons.update(.2)
        self.assertIsNone(sq.current_target)

    def test_physical_projectile_passes_ally_and_hits_hidden_enemy(self):
        from game.core.world import Projectile
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3())
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 2, Vec3(1000, 0, 0))
        for e in self.st.entities.values():
            e.sensor_range = 0
        p = Projectile(1, 0, 'laser_cannon', Vec3(), Vec3(), ally.id,
                       100, 1, 1, 1, 100)
        self.st.projectiles[p.id] = p
        self.st.grid.rebuild(self.st.entities)
        self.gm.projectiles.update(1 / 30)
        self.assertFalse(self.st.damage_queue)
        self.assertIn(p.id, self.st.projectiles)
        self.assertFalse(self.st.can_see(0, enemy.id))
        p.pos = enemy.pos.copy()
        self.gm.projectiles.update(1 / 30)
        self.assertEqual(self.st.damage_queue[0]['target'].id, enemy.id)
        self.assertNotIn(p.id, self.st.projectiles)

    def test_emp_jam_and_tractor_respect_nonaggression(self):
        caster = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        ally = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 200))
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 2, Vec3(0, 0, 300))
        self.st.grid.rebuild(self.st.entities)
        before = (dict(ally.shields), {k: v.hp for k, v in ally.systems.items()})
        energy = caster.energy
        self.assertFalse(self.gm.abilities.activate(caster, 'tractor_beam', ally.id))
        self.assertEqual(caster.energy, energy)
        self.assertFalse(caster.ability_cooldowns)
        self.assertTrue(self.gm.abilities.activate(caster, 'emp_burst'))
        self.assertEqual((dict(ally.shields), {k: v.hp for k, v in ally.systems.items()}), before)
        self.assertLess(enemy.shields['front'], enemy.max_shield_quad)
        caster.energy = caster.max_energy
        self.assertTrue(self.gm.abilities.activate(caster, 'sensor_jam'))
        self.assertNotIn('sensor_jammed', ally.ability_active)
        self.assertIn('sensor_jammed', enemy.ability_active)


    def test_long_ai_allied_trade_is_deterministic_after_restore(self):
        import json
        from game.net.replay import state_checksum
        self.market(0, 0)
        self.market(1, 0, 1800)
        for pid in (0, 1, 2):
            self.st.players[pid].is_ai = True
            self.gm.factory.spawn_ship('imperial_corvette', pid,
                                       Vec3(-3000 + pid * 3000, 0, -6000))
            self.gm.factory.spawn_ship('imperial_constructor', pid,
                                       Vec3(-10000 + pid * 4000, 0, 9000))
        self.gm.trading.cfg['spawn_interval'] = 5
        restored = GameManager(GameState.from_dict(json.loads(json.dumps(self.st.to_dict(precise=True)))))
        restored.trading.cfg.update(self.gm.trading.cfg)
        arrivals = []
        fired = []
        self.st.events.subscribe('convoy_arrived', lambda e: arrivals.append(e.data))
        self.st.events.subscribe('weapon_fired', lambda e: fired.append(e.data))
        for tick in range(6000):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(self.st.tick, tick + 1, 'check must not silently time game-over no-op steps')
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state), f'tick {tick + 1}')
            for e in self.st.entities.values():
                if e.current_target is not None:
                    target = self.st.entity(e.current_target)
                    # Damage can purge a killed target later in the same tick;
                    # next pre-movement contact validation clears that dead ID.
                    if target is not None:
                        self.assertTrue(self.st.is_enemy(e.owner, target.owner))
                if e.data_id == 'trade_convoy' and e.convoy_dest is not None:
                    dest = self.st.entity(e.convoy_dest)
                    self.assertTrue(dest is not None and dest.owner in self.st.allied_player_ids(e.owner))
        self.assertTrue(arrivals, 'exercise real AI and commerce, not an empty deterministic simulation')


if __name__ == '__main__':
    unittest.main()
