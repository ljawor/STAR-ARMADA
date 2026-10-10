"""Every built-in race has command-only, faction-correct colony hardware."""
import unittest
from helpers import make_game, run_for
from game.core.vectors import Vec3
from render.faction_visuals import ship_visual_key


class ColonyFactionTests(unittest.TestCase):
    def test_every_registered_race_has_command_only_colony_ship(self):
        gm = make_game(ai=False)
        ds = gm.ds
        command = next(e for e in gm.state.entities.values()
                       if e.owner == 0 and e.data_id == 'command_station')
        yard = next(e for e in gm.state.entities.values()
                    if e.owner == 0 and e.data_id == 'shipyard')
        for faction in ds.factions:
            with self.subTest(faction=faction):
                colony_ships = [s for s in ds.ships.values()
                                if s.faction == faction and s.can_colonize]
                self.assertTrue(colony_ships, faction)
                gm.state.players[0].faction = faction
                for ship in colony_ships:
                    self.assertIn(ship.id, ds.stations['command_station'].builds_ships)
                    self.assertTrue(gm.construction.station_can_build_ship(command, ship.id))
                    self.assertFalse(gm.construction.station_can_build_ship(yard, ship.id))
                    self.assertFalse(ship.can_build_stations)
                    self.assertEqual(ship.max_rank, 5)

    def test_syndicate_colonizer_uses_its_existing_bespoke_mesh_and_settles(self):
        gm = make_game(ai=False)
        self.assertIn('syndicate_colonizer', gm.ds.ships)
        self.assertEqual(ship_visual_key(gm.ds, 'syndicate_colonizer'), 'syndicate:colonizer')
        gm.state.players[0].faction = 'syndicate'
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'temperate')
        ship = gm.factory.spawn_ship('syndicate_colonizer', 0,
            planet.pos + Vec3(0, 0, planet.radius + 300))
        self.assertTrue(gm.construction.start_colonize(ship.id, planet.id, 0))
        run_for(gm, 16)
        self.assertEqual(planet.colonized_by, 0)
        self.assertFalse(ship.alive)


if __name__ == '__main__':
    unittest.main()
