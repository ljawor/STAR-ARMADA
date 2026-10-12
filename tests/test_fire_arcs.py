"""#58 regression: capital batteries cover every bearing; nose-only mounts still aim.

The ship catalogue declares per-mount `arcs`, but until #58 nothing read them:
every weapon fell back to the weapon catalogue's single `hardpoint`, which is
`"front"` for turbolasers, heavy turbolasers, ion cannons, mass drivers,
plasma lances and beam lances. So a capital's main battery could only fire
inside ±72° of its nose and had to stop and turn to shoot at all.

These tests drive the real WeaponSystem launches at four bearings, and the
real DataStore catalogue, so they fail both if the arcs are ignored again and
if arcs stop constraining a genuinely nose-only mount.
"""
import unittest

from helpers import make_game
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.weapons import mount_arcs, mount_needs_nose

CAPITAL_CATEGORIES = ('cruiser', 'battleship', 'supercapital')
SECTORS = ('front', 'rear', 'left', 'right')


def all_round(arcs):
    """True when the sector list leaves no bearing uncovered."""
    if 'all' in arcs:
        return True
    return all(any(arc == 'all' or arc == sector for arc in arcs) for sector in SECTORS)


class FireArcDataTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.ds = DataStore.get()

    def capital_ships(self):
        return {sid: ship for sid, ship in self.ds.ships.items()
                if ship.category in CAPITAL_CATEGORIES}

    def test_every_capital_mount_covers_every_bearing(self):
        capitals = self.capital_ships()
        self.assertTrue(capitals, 'no capital ships registered')
        factions = {ship.faction for ship in capitals.values()}
        for sid, ship in capitals.items():
            for wref in ship.weapons:
                with self.subTest(ship=sid, weapon=wref['weapon']):
                    self.assertTrue(
                        all_round(wref.get('arcs', [])),
                        f'{sid} {wref["weapon"]} mounts {wref.get("arcs")} and '
                        f'cannot fire at every bearing')

    def test_every_registered_faction_has_a_full_coverage_capital(self):
        covered = {}
        for sid, ship in self.capital_ships().items():
            if all(all_round(w.get('arcs', [])) for w in ship.weapons):
                covered.setdefault(ship.faction, []).append(sid)
        for faction in sorted({s.faction for s in self.ds.ships.values()}):
            if not any(s.category in CAPITAL_CATEGORIES for s in self.ds.ships.values()
                       if s.faction == faction):
                continue
            with self.subTest(faction=faction):
                self.assertTrue(covered.get(faction), f'{faction} has no all-round capital')

    def test_smaller_hulls_keep_the_arcs_their_design_declares(self):
        """Arcs must stay meaningful: only the ordered capital scope widened."""
        nose_only = [sid for sid, ship in self.ds.ships.items()
                     if ship.category not in CAPITAL_CATEGORIES
                     and any(not all_round(w.get('arcs', [])) for w in ship.weapons)]
        self.assertTrue(nose_only, 'no ship declares a limited arc any more')


class MountArcUnitTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.ds = DataStore.get()

    def test_mount_spec_wins_over_the_catalogue_hardpoint(self):
        turbolaser = self.ds.resolve_weapon('turbolaser')
        self.assertEqual(turbolaser.hardpoint, 'front', 'catalogue default changed')
        self.assertEqual(mount_arcs({'weapon': 'turbolaser', 'count': 3,
                                     'arcs': ['all']}, turbolaser), ('all',))
        self.assertEqual(mount_arcs({'weapon': 'turbolaser', 'count': 3,
                                     'arcs': ['front', 'left']}, turbolaser),
                         ('front', 'left'))

    def test_mounts_without_arcs_fall_back_to_the_weapon_hardpoint(self):
        turbolaser = self.ds.resolve_weapon('turbolaser')
        laser = self.ds.resolve_weapon('laser_cannon')
        self.assertEqual(mount_arcs({'weapon': 'turbolaser', 'count': 1}, turbolaser),
                         ('front',))
        self.assertEqual(mount_arcs({'weapon': 'laser_cannon', 'count': 1}, laser),
                         ('all',))
        self.assertEqual(mount_arcs('turbolaser', turbolaser), ('front',))

    def test_only_a_forward_only_mount_demands_the_nose(self):
        turbolaser = self.ds.resolve_weapon('turbolaser')
        self.assertTrue(mount_needs_nose({'weapon': 'turbolaser', 'count': 1,
                                          'arcs': ['front']}, turbolaser))
        self.assertFalse(mount_needs_nose({'weapon': 'turbolaser', 'count': 1,
                                           'arcs': ['all']}, turbolaser))
        self.assertFalse(mount_needs_nose({'weapon': 'turbolaser', 'count': 1,
                                           'arcs': ['front', 'rear']}, turbolaser))


class BearingLaunchTests(unittest.TestCase):
    """Real launches through WeaponSystem._ship_weapons at four bearings."""

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.target = self.gm.factory.spawn_station('command_station', 1, Vec3())
        self.target.sensor_range = 10000

    def spawn_attacker(self, ship_id, offset):
        # Start from a clean field: only the station target and this attacker.
        for eid in [eid for eid, e in self.st.entities.items() if eid != self.target.id]:
            del self.st.entities[eid]
        ship = self.gm.factory.spawn_ship(ship_id, 0, self.target.pos + offset)
        ship.sensor_range = 10000
        ship.order_type = 'attack'
        ship.order_target_id = self.target.id
        ship.current_target = self.target.id
        ship.yaw = 0.0                      # nose on +Z, target offsets vary
        return ship

    def launches_at(self, ship_id, offset, ticks=180):
        """Count launches (damage queue entries) while the hull keeps its yaw."""
        ship = self.spawn_attacker(ship_id, offset)
        shots = 0
        for _ in range(ticks):
            self.st.tick += 1
            self.st.time += 1 / 30
            ship.energy = ship.max_energy
            self.st.grid.rebuild(self.st.entities)
            self.gm.weapons._ship_weapons(ship, 1 / 30)
            shots += len(self.st.damage_queue) + len(self.st.projectiles)
            self.st.damage_queue.clear()
            self.st.projectiles.clear()
        return shots

    def bearings(self, distance):
        """Attacker offsets for a hull whose nose is +Z: target ahead/astern/port/starboard.

        Offsets are the attacker's position relative to the station, so 'astern'
        puts the nose away from the target. `left`/`right` follow the arc test in
        WeaponSystem._in_arc, whose left sector is +X for a +Z nose.
        """
        return (('ahead', Vec3(0, 0, -distance)),
                ('astern', Vec3(0, 0, distance)),
                ('port', Vec3(distance, 0, 0)),
                ('starboard', Vec3(-distance, 0, 0)))

    def test_capital_cruiser_fires_at_a_target_on_every_bearing(self):
        for name, offset in self.bearings(1200):
            with self.subTest(bearing=name):
                shots = self.launches_at('imperial_cruiser', offset)
                self.assertGreater(shots, 0,
                                   f'cruiser battery silent with the target {name}')

    def test_supercapital_fires_at_a_target_on_every_bearing(self):
        for name, offset in self.bearings(1500):        # inside turbolaser reach
            with self.subTest(bearing=name):
                shots = self.launches_at('rebel_supercapital', offset)
                self.assertGreater(shots, 0,
                                   f'supercapital battery silent with the target {name}')

    def test_battleship_heavy_battery_fires_at_a_target_on_every_bearing(self):
        for name, offset in self.bearings(2000):        # inside heavy turbolaser reach
            with self.subTest(bearing=name):
                shots = self.launches_at('imperial_battleship', offset)
                self.assertGreater(shots, 0,
                                   f'battleship battery silent with the target {name}')

    def test_nose_only_fighter_still_cannot_shoot_astern(self):
        """The invariant behind the arcs: front-only mounts still need the nose."""
        behind = self.launches_at('imperial_tie_squadron', Vec3(0, 0, 700))
        self.assertEqual(behind, 0, 'a rear target must stay outside a front-only arc')
        ahead = self.launches_at('imperial_tie_squadron', Vec3(0, 0, -700))
        self.assertGreater(ahead, 0, 'the same fighter must still fire ahead')

    def test_capital_keeps_firing_while_it_orbits(self):
        """No stopped, target-facing fire windows are needed once coverage is full."""
        from game.systems.movement import MovementSystem
        import math
        ship = self.spawn_attacker('confed_supercapital', Vec3(0, 0, -1872))
        movement = MovementSystem(self.st)
        shots, travelled = 0, 0.0
        previous = None
        for _ in range(3600):
            self.st.tick += 1
            self.st.time += 1 / 30
            movement.update(1 / 30)
            self.st.grid.rebuild(self.st.entities)
            ship.energy = ship.max_energy
            self.gm.weapons._ship_weapons(ship, 1 / 30)
            shots += len(self.st.damage_queue) + len(self.st.projectiles)
            self.st.damage_queue.clear()
            self.st.projectiles.clear()
            angle = math.atan2(ship.pos.x - self.target.pos.x, ship.pos.z - self.target.pos.z)
            if previous is not None:
                travelled += abs((angle - previous + math.pi) % (2 * math.pi) - math.pi)
            previous = angle
        self.assertGreater(shots, 40, 'a fully covered capital must keep shooting')
        self.assertGreater(travelled, 0.5, 'and keep manoeuvring while it does')


if __name__ == '__main__':
    unittest.main()
