"""#60 regression: ships must be able to hit — and so destroy — surface hardware.

`_launch_projectiles` spawns each shot at the muzzle (`0.8 * radius` ahead of the
hull along its facing) but used to compute the velocity from the hull centre, so
the whole trajectory was displaced sideways by the muzzle offset whenever the
hull was not pointing at its target. A ship in a firing orbit points ~90 degrees
off it, which is the full offset: 72 units on a cruiser, wider than the 27-50
unit hit sphere of anything under ~120 radius. Surface hardware (radius 45) was
therefore unkillable by ships, which is what #60 reports.

The catalogue and the damage pipeline were already correct: `planet_buildings`
absorbs surface damage into an operational shield generator's quadrant pools and
DamageSystem is the single writer that kills the hull. Only the aim was wrong.
"""
import math
import unittest

from helpers import make_game, run_for, run_until, queue_detected_human_attack
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3

DT = 1 / 30


class MuzzleAimTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.victim = self.gm.factory.spawn_station('mining_station', 1, Vec3(0, 0, 0))
        # nose on +Z, target due +X: the broadside attitude of a firing orbit
        self.ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(1500, 0, 0))
        self.ship.yaw = 0.0
        self.ship.sensor_range = 20000
        self.wd = self.gm.ds.resolve_weapon('turbolaser')

    def launch_one(self, target=None):
        target = target or self.victim
        before = set(self.st.projectiles)
        self.gm.weapons._launch_projectiles(self.ship, target, self.wd, 1)
        created = [p for pid, p in self.st.projectiles.items() if pid not in before]
        self.assertEqual(len(created), 1)
        return created[0]

    def test_the_shot_starts_at_the_muzzle(self):
        shot = self.launch_one()
        expected = self.ship.pos + Vec3(math.sin(self.ship.yaw), 0,
                                        math.cos(self.ship.yaw)) * (self.ship.radius * 0.8)
        self.assertAlmostEqual(shot.pos.dist(expected), 0.0, places=6)
        self.assertGreater(shot.pos.dist(self.ship.pos), 70.0,
                           'the muzzle offset itself is part of the visual model')

    def test_a_broadside_shot_is_aimed_from_the_muzzle_not_the_hull(self):
        """Exact geometry: with the spread silenced the flight line must pass
        through the target centre, not 0.8*radius to one side of it."""
        radius, self.victim.radius = self.victim.radius, 0.0
        try:
            rel = self.victim.pos - self.ship.pos
            self.assertAlmostEqual(rel.normalized().length(), 1.0, places=9)
            offsets = []
            for _ in range(6):
                shot = self.launch_one()
                to_target = self.victim.pos - shot.pos
                offsets.append(to_target.cross(shot.vel).length() / to_target.length())
        finally:
            self.victim.radius = radius
        self.assertLess(max(offsets), 1e-6,
                        f'shots are aimed from the hull centre: offsets {offsets}')
        self.assertLess(1.0, radius, 'the fixture target must have a real radius')

    def test_a_broadside_cruiser_lands_shots_on_a_small_station(self):
        """End to end: launch, fly, hit, damage — with the hull held broadside."""
        attacker = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3(1500, 0, 0))
        attacker.sensor_range = 20000
        attacker.order_type = 'attack'
        attacker.order_target_id = attacker.current_target = self.victim.id
        before = self.victim.hull
        for _ in range(int(30 / DT)):
            self.st.tick += 1
            self.st.time += DT
            attacker.yaw = 0.0                    # never points at the target
            self.st.grid.rebuild(self.st.entities)
            self.gm.weapons._ship_weapons(attacker, DT)
            self.gm.projectiles.update(DT)
            self.gm.damage.update(DT)
        self.assertLess(self.victim.hull, before - 500,
                        'a broadside hull landed almost no damage on a radius-45 station')


class SurfaceHardwareKillPathTests(unittest.TestCase):
    """#60 through the real command, the real manager and the real pipeline."""

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000

    def build(self, kind='planet_extractor'):
        self.st.queue_command(PlayerCommand('build_planet_building', 0,
                                            target_id=self.planet.id, station_kind=kind))
        self.gm.step(DT)
        # Wait on the delivered hull, not a second count: surface build time is
        # derived from the building's cost (#95).
        run_until(self.gm, lambda: any(e.alive and e.planet_id == self.planet.id
                                       and e.planet_building_slot is not None
                                       for e in self.st.entities.values()))
        return next(e for e in self.st.entities.values()
                    if e.alive and e.planet_id == self.planet.id
                    and e.planet_building_slot is not None)

    def test_a_ship_destroying_surface_hardware_frees_its_slot(self):
        from game.systems.planet_buildings import building_slots
        building = self.build()
        slot = building.planet_building_slot
        self.assertIn(slot, building_slots(self.st, self.planet))
        attacker = self.gm.factory.spawn_ship('imperial_cruiser', 1,
                                              building.pos + Vec3(1500, 0, 0))
        attacker.sensor_range = 20000
        self.st.queue_command(PlayerCommand('attack', 1, unit_ids=(attacker.id,),
                                            target_id=building.id))
        elapsed = 0.0
        reattacked = False
        while building.alive and elapsed < 300.0:
            self.gm.step(DT)
            elapsed += DT
            if building.alive and not building.operational and not reattacked:
                self.assertIsNone(attacker.current_target)
                self.assertIn(slot, building_slots(self.st, self.planet))
                queue_detected_human_attack(self.gm, 1, [attacker.id], building.id)
                reattacked = True
        self.assertTrue(reattacked)
        self.assertFalse(building.alive,
                         f'surface hardware survived {elapsed:.0f}s of a cruiser; '
                         f'hull {building.hull:.0f}/{building.max_hull:.0f}')
        self.assertNotIn(building.id, self.st.entities)
        self.assertNotIn(slot, building_slots(self.st, self.planet))
        self.assertLess(elapsed, 240.0, 'the kill takes far longer than it should')
        self.assertEqual(self.st.stats['1']['kills'], 1)

    def test_a_satellite_is_destructible_before_any_lockout_exists(self):
        """#57's prerequisite: a destroyed satellite is a real, reachable event."""
        # Keep the anti-ship platform as #57's lockout fixture. Both moving
        # defense and engaged attack platforms are covered by #62's separate
        # position/velocity and real projectile-kill regressions.
        self.assertTrue(self.gm.construction.start_satellite(self.planet.id,
                                                              'attack_satellite', 0))
        run_for(self.gm, 200)
        satellite = next(e for e in self.st.entities.values()
                         if e.alive and e.satellite_slot is not None)
        attacker = self.gm.factory.spawn_ship('imperial_cruiser', 1,
                                              satellite.pos + Vec3(1500, 0, 0))
        attacker.sensor_range = 20000
        self.st.queue_command(PlayerCommand('attack', 1, unit_ids=(attacker.id,),
                                            target_id=satellite.id))
        elapsed = 0.0
        reattacked = False
        while satellite.alive and elapsed < 300.0:
            self.gm.step(DT)
            elapsed += DT
            if satellite.alive and not satellite.operational and not reattacked:
                self.assertIsNone(attacker.current_target)
                self.assertFalse(self.planet.satellite_locks)
                queue_detected_human_attack(self.gm, 1, [attacker.id], satellite.id)
                reattacked = True
        self.assertTrue(reattacked)
        self.assertFalse(satellite.alive,
                         f'a satellite survived {elapsed:.0f}s of a cruiser')
        self.assertNotIn(satellite.id, self.st.entities)


if __name__ == '__main__':
    unittest.main()
