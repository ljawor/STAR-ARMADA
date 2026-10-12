"""#75: exact matching-replay gas obstruction, not an engagement pause."""
import json
import math
import unittest
from pathlib import Path
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.satellite_orbits import orbit_position


class NebulaSatelliteOrbitTests(unittest.TestCase):
    def fixture(self):
        DataStore.reset()
        map_def = json.loads(json.dumps(DataStore.get().maps['skirmish04']))
        for player in map_def['players']:
            player['is_ai'] = False
        gm = GameManager.start_skirmish(map_def)
        planet = gm.state.entity(13)
        planet.colonized_by = 0
        # Extracted from replay tick 25401, satellite 203. Isolate the
        # permanent obstruction without inventing a combat or economy cause.
        sat = gm.factory.spawn_station('defense_satellite', 0,
            Vec3(3754.4079389884923, 144.76543841687462, 6959.819988639355))
        sat.planet_id, sat.satellite_slot = planet.id, 2
        sat.satellite_orbit_phase = 5.000395102392876
        return gm, planet, sat

    def test_all_map_planets_every_slot_have_safe_complete_rings(self):
        from game.systems.colonies import eligible_planet, colony_rules
        from game.systems.satellite_orbits import orbit_geometry, ring_distance
        DataStore.reset()
        maps = json.loads(json.dumps(DataStore.get().maps))
        count = 0
        for map_id, definition in sorted(maps.items()):
            if not map_id.startswith('skirmish'):
                continue
            for player in definition['players']:
                player['is_ai'] = False
            gm = GameManager.start_skirmish(definition)
            for planet in list(gm.state.entities.values()):
                if not eligible_planet(planet):
                    continue
                owner = min((e for e in gm.state.entities.values() if e.data_id == 'command_station'),
                            key=lambda e: (e.pos.dist_sq(planet.pos), e.id)).owner
                plans = []
                for slot in range(colony_rules()['satellite_cap']):
                    with self.subTest(map=map_id, planet=planet.id, slot=slot):
                        plan = orbit_geometry(gm.state, planet, 45., slot)
                        self.assertIsNotNone(plan)
                        plans.append(plan)
                        for body in gm.state.entities.values():
                            if body.alive and body.is_planet and body is not planet and body.data_id != 'asteroid_field':
                                self.assertGreaterEqual(ring_distance(planet.pos, *plan, body.pos), (45. + body.radius) * 1.6)
                        self.assertTrue(gm.construction.satellite_ring_available(planet, 'attack_satellite', slot, owner))
                        count += 1
                for a, b in zip(plans, plans[1:]):
                    self.assertGreaterEqual(b[0] - a[0], 144.)
        self.assertGreater(count, 24)

    def test_paid_constellation_restore_continues_through_complete_orbit(self):
        from game.core.commands import PlayerCommand
        gm, planet, old = self.fixture()
        del gm.state.entities[old.id]
        player = gm.state.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        for _ in range(32):
            gm.step(1 / 30)
        balance = {k: getattr(player, k) for k in ('credits', 'materials', 'energy', 'crew')}
        costs = {k: 0. for k in balance}
        for slot in range(6):
            kind = ('defense_satellite', 'attack_satellite')[slot % 2]
            cost = gm.factory.station_build_cost(kind)
            self.assertTrue(gm.construction.start_satellite(planet.id, kind, 0))
            self.assertEqual(planet.build_queue[-1]['slot'], slot)
            for key in costs:
                costs[key] += cost.get(key, 0.)
                self.assertEqual(getattr(player, key), balance[key] - costs[key])
        def snapshot(manager):
            return json.loads(json.dumps(manager.state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot(gm)))
        self.assertEqual(snapshot(gm), snapshot(restored))
        # Exact save continuation includes sequential paid completions and
        # one complete revolution after the last satellite finishes.
        phases = {}; travel = {}
        for tick in range(7800):
            gm.step(1 / 30); restored.step(1 / 30)
            self.assertEqual(snapshot(gm), snapshot(restored), f'tick {tick}')
            for sat in gm.state.entities.values():
                if sat.satellite_slot is None:
                    continue
                last = phases.get(sat.id, sat.satellite_orbit_phase)
                step = (sat.satellite_orbit_phase - last) % (2 * math.pi)
                if step < .1:
                    travel[sat.id] = travel.get(sat.id, 0.) + step
                phases[sat.id] = sat.satellite_orbit_phase
        sats = [e for e in gm.state.entities.values() if e.planet_id == planet.id and e.satellite_slot is not None]
        self.assertEqual(sorted(e.satellite_slot for e in sats), list(range(6)))
        self.assertFalse(planet.build_queue)
        for sat in sats:
            self.assertGreater(travel[sat.id], 2 * math.pi)

    def test_paid_and_completed_orbits_reserve_the_far_side(self):
        from game.systems.colonies import colony_rules
        from game.systems.satellite_orbits import orbit_position
        gm, planet, old = self.fixture()
        del gm.state.entities[old.id]
        player = gm.state.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        for _ in range(32):
            gm.step(1 / 30)
        self.assertTrue(gm.construction.start_satellite(planet.id, 'defense_satellite', 0))
        work = planet.build_queue[0]
        opposite = orbit_position(planet, 45., math.pi, work['slot'], state=gm.state)
        self.assertGreater(opposite.dist(Vec3(*work['pos'])), 1000.)
        self.assertFalse(gm.construction._check_station_spacing('mining_station', opposite, 0)[0])
        for _ in range(24 * 30):
            gm.step(1 / 30)
        self.assertFalse(planet.build_queue)
        self.assertFalse(gm.construction._check_station_spacing('mining_station', opposite, 0)[0])

    def test_blocked_complete_ring_rejects_purchase_without_payment(self):
        from game.systems.satellite_orbits import orbit_position
        gm, planet, old = self.fixture()
        del gm.state.entities[old.id]
        player = gm.state.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        for _ in range(32):
            gm.step(1 / 30)
        planet.satellite_locks = {slot: gm.state.time + 180 for slot in range(1, 6)}
        site = gm.construction.satellite_site(planet, 'defense_satellite', 0)
        obstacle = orbit_position(planet, 45., math.pi, 0, state=gm.state)
        gm.factory.spawn_station('mining_station', 0, obstacle)
        self.assertTrue(gm.construction._check_station_spacing('defense_satellite', site, 0)[0])
        before = (player.credits, player.materials, player.energy, player.crew)
        self.assertFalse(gm.construction.start_satellite(planet.id, 'defense_satellite', 0))
        self.assertFalse(planet.build_queue)
        self.assertEqual(before, (player.credits, player.materials, player.energy, player.crew))

    def test_replay_derived_blocked_satellite_completes_safe_orbit(self):
        gm, planet, sat = self.fixture()
        self.assertFalse(gm.satellite_orbits.engaged(sat))
        start_phase = sat.satellite_orbit_phase
        travel = 0.0
        previous = sat.pos.copy()
        last_phase = start_phase
        for _ in range(4800):
            gm.satellite_orbits.update(1 / 30)
            # Migration and the orbit must retain the exact giant clearance.
            for other in gm.state.entities.values():
                if other.alive and other.is_planet and other is not planet and other.data_id != 'asteroid_field':
                    self.assertGreaterEqual(sat.pos.dist(other.pos), (sat.radius + other.radius) * 1.6 - 1e-8)
            self.assertLessEqual(sat.pos.dist(previous), 5.0, 'teleported to new plane')
            step = (sat.satellite_orbit_phase - last_phase) % (2 * math.pi)
            if step < .1:
                travel += step
            last_phase, previous = sat.satellite_orbit_phase, sat.pos.copy()
        self.assertGreater(travel, 2 * math.pi, 'orbit still wedged at gas giant')
