"""Inclined orbital motion and engagement suspension via real manager ticks."""
import json
import unittest
from helpers import make_game, run_for
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class SatelliteOrbitTests(unittest.TestCase):
    def test_precise_manager_continuation_through_active_orbital_combat(self):
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.core.world import Projectile
        satellite = self.satellite()
        defender = self.satellite('defense_satellite')
        defender = next(e for e in self.st.entities.values() if e.data_id == 'defense_satellite')
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, satellite.pos + Vec3(400, 0, 0))
        enemy.order_type = 'hold'
        run_for(self.gm, .2)
        self.assertTrue(any(p.attacker_entity_id == satellite.id for p in self.st.projectiles.values()))
        defender.crew = defender.max_crew // 2
        defender.systems['weapons'].hp *= .73456789
        defender.ability_cooldowns['_intercept'] = .123456789
        source = self.gm.factory.spawn_ship('imperial_corvette', 1, defender.pos + Vec3(300, 0, 0))
        source.order_type = 'hold'
        pid = self.st.next_projectile_id
        self.st.next_projectile_id += 1
        self.st.projectiles[pid] = Projectile(id=pid, owner=1, weapon_id='missile_battery',
            pos=defender.pos + Vec3(200, 0, 0), vel=Vec3(), target_id=defender.id,
            damage=55.123456789, shield_mult=1.0, armor_mult=1.0, system_mult=0.0,
            life=10.0, attacker_entity_id=source.id)
        def snapshot(gm):
            return json.loads(json.dumps(gm.state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot(self.gm)))
        self.assertEqual(snapshot(self.gm), snapshot(restored))
        phase = satellite.satellite_orbit_phase
        for _ in range(20):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.gm), snapshot(restored))
        self.assertNotIn(pid, self.st.projectiles)
        self.assertEqual(satellite.satellite_orbit_phase, phase)
        for gm in (self.gm, restored):
            for eid in (enemy.id, source.id):
                gm.state.entities[eid].pos = self.planet.pos + Vec3(7000, 0, 7000)
        for _ in range(12):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(snapshot(self.gm), snapshot(restored))
        self.assertNotEqual(satellite.satellite_orbit_phase, phase)
        self.assertFalse(self.st.game_over)

    def test_satellite_catalogue_uses_lower_cost_medium_durability(self):
        for kind in ('defense_satellite', 'attack_satellite'):
            sd = self.gm.ds.stations[kind]
            self.assertLess(sd.cost_credits, 900)
            self.assertLess(sd.cost_materials, 1100)
            self.assertLess(sd.hull, 11000)
            self.assertGreaterEqual(sd.hull, 4000)
            self.assertLess(sd.shield_quad, 3000)
            self.assertGreater(sd.shield_quad, 0)

    def test_hidden_missile_source_cannot_pause_or_trigger_interception(self):
        from game.core.world import Projectile
        satellite = self.satellite('defense_satellite')
        source = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(12000, 0, 12000))
        p = Projectile(id=self.st.next_projectile_id, owner=1, weapon_id='missile_battery',
            pos=satellite.pos + Vec3(100, 0, 0), vel=Vec3(), target_id=satellite.id,
            damage=55, shield_mult=1, armor_mult=1, system_mult=0, life=10,
            attacker_entity_id=source.id)
        self.st.projectiles[p.id] = p
        self.st.next_projectile_id += 1
        self.assertFalse(self.st.can_see(0, source.id))
        before = satellite.pos.copy()
        self.gm.step(1 / 30)
        self.assertIn(p.id, self.st.projectiles)
        self.assertGreater(satellite.pos.dist(before), 0)
        source.pos = satellite.pos + Vec3(200, 0, 0)
        before = satellite.pos.copy()
        self.gm.step(1 / 30)
        self.assertNotIn(p.id, self.st.projectiles)
        self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
        self.gm.step(1 / 30)
        self.assertGreater(satellite.pos.dist(before), 0)

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000

    def satellite(self, kind='attack_satellite'):
        self.st.queue_command(PlayerCommand('build_satellite', 0,
            target_id=self.planet.id, station_kind=kind))
        run_for(self.gm, 24)
        return next(e for e in self.st.entities.values() if e.planet_id == self.planet.id)

    def test_inclined_motion_pauses_for_valid_in_range_detected_engagement_and_resumes(self):
        satellite = self.satellite()
        before = satellite.pos.copy()
        run_for(self.gm, 1)
        self.assertGreater(satellite.pos.dist(before), 1)
        self.assertNotEqual(satellite.pos.y, self.planet.pos.y)
        enemy = self.gm.factory.spawn_ship('imperial_corvette', 1, satellite.pos + Vec3(300, 0, 0))
        enemy.order_type = 'hold'
        before = satellite.pos.copy()
        run_for(self.gm, .2)
        self.assertEqual(satellite.pos.to_dict(True), before.to_dict(True))
        self.assertEqual(satellite.current_target, enemy.id)
        self.assertTrue(any(p.attacker_entity_id == satellite.id for p in self.st.projectiles.values()))
        enemy.pos = self.planet.pos + Vec3(7000, 0, 7000)
        satellite.current_target = enemy.id  # stale lock cannot freeze orbit
        run_for(self.gm, .2)
        self.assertGreater(satellite.pos.dist(before), 1)
        self.assertFalse(self.st.game_over)
