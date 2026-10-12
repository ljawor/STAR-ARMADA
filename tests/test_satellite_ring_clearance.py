"""Independent #75 review: reserve whole rings, never just birth points."""
import math
import unittest
from helpers import make_game
from game.core.entity import Entity
from game.core.vectors import Vec3
from game.systems.satellite_orbits import orbit_geometry, ring_distance, orbit_position


class SatelliteRingClearanceTests(unittest.TestCase):
    def crossing_fixture(self):
        gm = make_game(ai=False)
        gm.state.entities.clear()
        gm.state.map_info.bounds = 20000
        planets = []
        for eid, xyz in ((1, (0, 0, 0)), (2, (2165.0635094610966, 0, 1249.9999999999998))):
            p = Entity(eid, 'planet', -1, 'temperate', pos=Vec3(*xyz), radius=500,
                       is_planet=True, colonized_by=0)
            gm.state.add_entity(p)
            p.satellite_locks = {slot: 180 for slot in range(5)}
            planets.append(p)
        player = gm.state.players[0]
        player.command_capacity = 1000
        player.credits = player.materials = player.energy = player.crew = 100000
        return gm, planets

    def test_paid_cross_planet_rings_reject_future_collision_without_spending(self):
        gm, (a, b) = self.crossing_fixture()
        self.assertTrue(gm.construction.start_satellite(a.id, 'defense_satellite', 0))
        # The current/birth point checks pass despite a 21u future approach.
        point = orbit_position(a, 45, 4.9043751981040655, 5, state=gm.state)
        self.assertLess(ring_distance(b.pos, *orbit_geometry(gm.state, b, 45, 5), point), 144)
        site = gm.construction.satellite_site(b, 'defense_satellite', 5)
        self.assertTrue(gm.construction._check_station_spacing('defense_satellite', site, 0)[0])
        player = gm.state.players[0]
        before = (player.credits, player.materials, player.energy, player.crew)
        self.assertFalse(gm.construction.start_satellite(b.id, 'defense_satellite', 0))
        self.assertFalse(b.build_queue)
        self.assertEqual(before, (player.credits, player.materials, player.energy, player.crew))

    def test_planetary_queue_preview_uses_control_and_paid_source_authority(self):
        from test_nebula_satellite_orbits import NebulaSatelliteOrbitTests
        for owner, source_owner, allied, expected in ((0, 0, False, False),
                (1, 1, True, False), (2, 2, False, True), (0, 2, False, True)):
            with self.subTest(owner=owner, source_owner=source_owner, allied=allied):
                gm, planet, old = NebulaSatelliteOrbitTests().fixture()
                del gm.state.entities[old.id]
                planet.colonized_by = owner
                for player in gm.state.players.values():
                    player.command_capacity = 1000
                    player.credits = player.materials = player.energy = player.crew = 100000
                if allied:
                    gm.state.players[0].team = gm.state.players[1].team = 99
                self.assertTrue(gm.construction.start_satellite(planet.id, 'defense_satellite', owner))
                work = planet.build_queue[0]
                opposite = orbit_position(planet, 45, work['slot'] * 2 * 3.141592653589793 / 6 +
                    3.141592653589793, work['slot'], state=gm.state)
                # Public/detected planet is NOT authority to disclose enemy intent.
                observer = gm.factory.spawn_ship('imperial_corvette', 0, opposite)
                gm.visibility.update(0)
                self.assertTrue(gm.state.can_see(0, planet.id))
                work['source_owner'] = source_owner
                self.assertFalse(gm.construction._check_station_spacing('mining_station', opposite, 0)[0])
                self.assertEqual(gm.construction._check_station_spacing(
                    'mining_station', opposite, 0, viewer=0)[0], expected)

    def mobile_fixture(self):
        from test_nebula_satellite_orbits import NebulaSatelliteOrbitTests
        gm, planet, old = NebulaSatelliteOrbitTests().fixture()
        del gm.state.entities[old.id]
        player = gm.state.players[0]
        player.command_capacity = 1000
        player.credits = player.materials = player.energy = player.crew = 100000
        planet.satellite_locks = {slot: 180 for slot in range(1, 6)}
        return gm, planet

    def test_mobile_birth_overlap_rejects_authoritative_purchase_without_spending(self):
        from game.core.commands import PlayerCommand
        gm, planet = self.mobile_fixture()
        site = gm.construction.satellite_site(planet, 'defense_satellite', 0)
        blocker = gm.factory.spawn_ship('imperial_constructor', 0, site)
        blocker.order_type = 'hold'
        player = gm.state.players[0]
        before = gm.state.stats.get('0', {}).get('credits_spent', 0)
        gm.state.queue_command(PlayerCommand('build_satellite', 0,
            target_id=planet.id, station_kind='defense_satellite'))
        gm.step(1 / 30)
        self.assertFalse(planet.build_queue)
        self.assertEqual(gm.state.stats.get('0', {}).get('credits_spent', 0), before)
        self.assertFalse(any(e.satellite_slot is not None for e in gm.state.entities.values()))

    def test_mobile_birth_overlap_defers_paid_completion_and_restores_exactly(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        gm, planet = self.mobile_fixture()
        self.assertTrue(gm.construction.start_satellite(planet.id, 'defense_satellite', 0))
        work = planet.build_queue[0]
        work['time_left'] = 0
        blocker = gm.factory.spawn_ship('imperial_constructor', 0, Vec3(*work['pos']))
        blocker.order_type = 'hold'
        before = gm.state.players[0].credits
        def snapshot(manager):
            return json.loads(json.dumps(manager.state.to_dict(precise=True)))
        restored = GameManager(GameState.from_dict(snapshot(gm)))
        income_control = GameManager(GameState.from_dict(snapshot(gm)))
        income_control.state.entity(planet.id).build_queue.clear()
        for tick in range(3):
            gm.step(1 / 30); restored.step(1 / 30); income_control.step(1 / 30)
            self.assertEqual(snapshot(gm), snapshot(restored), f'deferred tick {tick}')
            self.assertEqual(len(planet.build_queue), 1)
            self.assertEqual(planet.build_queue[0]['status'], 'paid')
            self.assertFalse(any(e.satellite_slot is not None for e in gm.state.entities.values()))
            self.assertEqual(gm.state.players[0].credits, income_control.state.players[0].credits)
        for manager in (gm, restored, income_control):
            manager.state.entity(blocker.id).pos = planet.pos + Vec3(6000, 0, 0)
            manager.step(1 / 30)
        self.assertEqual(snapshot(gm), snapshot(restored))
        self.assertFalse(planet.build_queue)
        satellites = [e for e in gm.state.entities.values() if e.satellite_slot is not None]
        self.assertEqual(len(satellites), 1)
        self.assertGreaterEqual(satellites[0].pos.dist(blocker.pos), (satellites[0].radius + blocker.radius) * 1.6)
        self.assertEqual(gm.state.players[0].credits, income_control.state.players[0].credits)

    def test_unsafe_mod_constellation_fails_closed_without_payment(self):
        for override, hull in (({'orbit_shell_spacing': 100}, None), ({}, 100),
                               ({'orbit_shell_spacing': float('nan')}, None),
                               ({'orbit_inclination': 1e100}, None)):
            with self.subTest(override=override, hull=hull):
                gm, planet = self.mobile_fixture()
                gm.construction.ds.rules.setdefault('colonies', {}).update(override)
                if hull is not None:
                    gm.construction.ds.stations['attack_satellite'].radius = hull
                self.assertIsNone(orbit_geometry(gm.state, planet, 45, 0))
                before = gm.state.players[0].credits
                self.assertFalse(gm.construction.start_satellite(planet.id, 'defense_satellite', 0))
                self.assertEqual(gm.state.players[0].credits, before)
                self.assertFalse(planet.build_queue)

    def test_mod_parent_clearance_certifies_the_swept_inner_chord(self):
        from game.core import detmath
        gm, (planet, other) = self.crossing_fixture()
        del gm.state.entities[other.id]
        gm.construction.ds.rules['colonies']['orbit_clearance'] = 10
        plan = orbit_geometry(gm.state, planet, 45, 0)
        self.assertIsNotNone(plan)
        self.assertGreaterEqual(plan[0] * detmath.cos(.01), planet.radius + 45 + 40)

    def test_ring_certificate_safe_unsafe_and_near_boundary_controls(self):
        from game.systems.satellite_orbits import rings_clear
        origin = Vec3()
        plan = (1000, .37, .61)
        self.assertTrue(rings_clear(origin, plan, origin, (1160, 1.1, .9), 144))
        self.assertFalse(rings_clear(origin, plan, origin, (1143.99, 1.1, .9), 144))
        self.assertTrue(rings_clear(origin, (1000, 0, 0), Vec3(0, 160, 0), (1000, 0, 0), 144))
        self.assertFalse(rings_clear(origin, (1000, 0, 0), Vec3(0, 144, 0), (1000, 0, 0), 144))
        self.assertFalse(rings_clear(origin, (1000, 0, 0), Vec3(1900, 0, 0), (1000, 0, 0), 1))
        self.assertFalse(rings_clear(origin, (float('nan'), 0, 0), origin, plan, 144))
        # Narrow tangencies/crossings at several non-grid orientations must
        # never be accepted merely because the evaluated midpoints miss them.
        # The runtime helper's analytic lower bounds, not these samples, certify
        # every admitted pair. Controls exercise both exact and subdivided paths.
        for node in (.013, .417, 1.013, 2.517):
            delta = Vec3(1900 * math.cos(node), 0, 1900 * math.sin(node))
            self.assertFalse(rings_clear(origin, (1000, 0, 0), delta, (1000, 0, 0), 1))

    def test_live_cross_planet_ring_rejects_future_collision(self):
        gm, (a, b) = self.crossing_fixture()
        sat = gm.factory.spawn_station('defense_satellite', 0,
            gm.construction.satellite_site(a, 'defense_satellite', 5))
        sat.planet_id, sat.satellite_slot = a.id, 5
        self.assertTrue(gm.construction._check_station_spacing('defense_satellite',
            gm.construction.satellite_site(b, 'defense_satellite', 5), 0)[0])
        self.assertFalse(gm.construction.start_satellite(b.id, 'defense_satellite', 0))
