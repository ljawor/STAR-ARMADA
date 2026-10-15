"""Keep deterministic terrain ordering without sorting unrelated fleet hulls."""
import builtins
import unittest
from unittest.mock import patch

from game.graphics_benchmark import make_fixture
from game.systems import satellite_orbits as orbits


class TerrainScanTests(unittest.TestCase):
    def test_orbit_plan_sorts_only_relevant_terrain(self):
        st = make_fixture('four-player-stock-distributed-v1').manager.state
        satellite = next(e for e in st.entities.values() if e.satellite_slot is not None)
        planet = st.entities[satellite.planet_id]
        expected_terrain = [e for e in st.entities.values()
                            if e.alive and e.is_planet and e is not planet
                            and e.data_id != 'asteroid_field']
        key_sizes = []
        def measured_sorted(values, *a, **kw):
            values = list(values)
            if kw.get('key') is not None:
                key_sizes.append(len(values))
            return builtins.sorted(values, *a, **kw)
        with patch.object(orbits, 'sorted', side_effect=measured_sorted, create=True):
            plan = orbits.orbit_geometry(st, planet, satellite.radius, 0)
        self.assertIsNotNone(plan)
        self.assertEqual(key_sizes, [len(expected_terrain)],
                         'orbit terrain keys must not sort unrelated combat hulls')

    def test_original_terrain_cache_key_survives_reordering_and_live_mutation(self):
        for fixture in ('four-player-stock-distributed-v1', 'four-player-combat-v1'):
            st = make_fixture(fixture).manager.state
            satellite = next(e for e in st.entities.values() if e.satellite_slot is not None)
            planet = st.entities[satellite.planet_id]
            st.entities = dict(reversed(tuple(st.entities.items())))
            others = [e for e in st.entities.values() if e.is_planet and e is not planet]
            for mutation in ('none', 'position', 'radius', 'death', 'asteroid'):
                e = others[0]
                if mutation == 'position':
                    e.pos.x += 15.
                elif mutation == 'radius':
                    e.radius += 10.
                elif mutation == 'death':
                    e.alive = False
                elif mutation == 'asteroid':
                    e.alive = True
                    e.data_id = 'asteroid_field'
                legacy = tuple((b.id, b.pos.x, b.pos.y, b.pos.z, b.radius)
                               for b in sorted(st.entities.values(), key=lambda b: b.id)
                               if b.alive and b.is_planet and b is not planet
                               and b.data_id != 'asteroid_field')
                with self.subTest(fixture=fixture, mutation=mutation):
                    with patch.object(orbits, '_terrain_plans', return_value=None) as cache:
                        orbits.orbit_geometry(st, planet, satellite.radius, 0)
                    self.assertEqual(cache.call_args.args[5], legacy)


if __name__ == '__main__':
    unittest.main()
