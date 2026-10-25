"""A mining station's placement window must match the field a player can see.

`requires_range` asks for a site "within 900u of asteroid field", and building *inside* a
field is deliberate (the rocks are the resource). The window used to be measured from the
field's centre while every other body is measured from its edge, so on a field of radius
1400-1800 only the inner 900u core was legal - a spot well inside the visible rocks was
rejected with "must be within 900u of asteroid field".
"""
import unittest

from game.core.manager import GameManager
from game.core.skirmish import build_skirmish_map, default_skirmish_options
from game.core.vectors import Vec3
from game.data.store import DataStore


class MiningStationSiteTests(unittest.TestCase):
    def setUp(self):
        self.ds = DataStore()
        self.state = GameManager.start_skirmish(
            build_skirmish_map(self.ds, default_skirmish_options(self.ds))).state
        self.system = self.state._construction_system
        self.builder = next(e for e in self.state.entities.values()
                            if e.alive and e.owner == 0 and self.ds.ships.get(e.data_id)
                            and self.ds.ships[e.data_id].is_construction)
        self.field = max((e for e in self.state.entities.values()
                          if e.alive and e.data_id == 'asteroid_field'),
                         key=lambda e: e.radius)

    def site(self, distance):
        return Vec3(self.field.pos.x + distance, 0, self.field.pos.z)

    def test_the_window_starts_at_the_edge_of_the_field_not_its_centre(self):
        self.assertEqual(self.ds.stations['mining_station'].requires_range,
                         {'asteroid_field': 900})
        for distance in (self.field.radius * 0.5, self.field.radius * 0.95,
                         self.field.radius - 50, self.field.radius + 400):
            ok, why = self.system.check_site('mining_station', self.site(distance), self.builder)
            self.assertTrue(ok, f'{distance:.0f}u from the centre was rejected: {why}')

    def test_the_window_still_ends_900u_beyond_the_rocks(self):
        ok, why = self.system.check_site(
            'mining_station', self.site(self.field.radius + 2000), self.builder)
        self.assertFalse(ok, 'a site two thousand units past the field was accepted')
        self.assertIn('within 900u of asteroid field', why)

    def test_a_station_in_the_rocks_is_not_pushed_off_by_the_planet_rule(self):
        # The planet-spacing rule deliberately exempts asteroid fields; if it ever stops
        # doing so, this fails with "too close to planet" instead of a range complaint.
        ok, why = self.system.check_site(
            'mining_station', self.site(self.field.radius * 0.5), self.builder)
        self.assertTrue(ok, why)


if __name__ == '__main__':
    unittest.main()
