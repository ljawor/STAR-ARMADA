"""Exact camera bounds with shared model geometry, live world transforms."""
import itertools
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from game.core.vectors import Vec3
from render import fleet_geometry
from render import planet_building_geometry as geometry


def entity(kind='defense_satellite', **changes):
    values = dict(data_id=kind, owner=0, pos=Vec3(100, 200, 300), radius=50.,
                  yaw=.7, satellite_slot=0, planet_building_slot=None, planet_id=None)
    values.update(changes)
    return SimpleNamespace(**values)


def state(faction='imperial', planet=None):
    return SimpleNamespace(players={0: SimpleNamespace(faction=faction)},
                           entity=lambda eid: planet if planet is not None and eid == planet.id else None)


def legacy_box(st, e, angle=0.):
    from render.faction_visuals import owner_faction
    mesh = fleet_geometry.station_mesh(e.data_id, owner_faction(st, e.owner))
    points = [p for role in mesh.values() for _, tri in role for p in tri]
    lo = tuple(min(p[i] for p in points) for i in range(3))
    hi = tuple(max(p[i] for p in points) for i in range(3))
    frame = geometry.station_frame(st, e, angle)
    points = [geometry.transform_point(p, frame) for p in itertools.product(*zip(lo, hi))]
    origin = frame[0]
    low = tuple(min(p[i] for p in points) - origin[i] for i in range(3))
    high = tuple(max(p[i] for p in points) - origin[i] for i in range(3))
    return origin, 0., low, high


class StationBoundsTests(unittest.TestCase):
    def clear_cache(self):
        cache = getattr(geometry, '_station_local_bounds', None)
        if cache is not None:
            cache.cache_clear()

    def test_unchanged_mesh_is_scanned_once_while_transform_stays_live(self):
        self.clear_cache()
        st, e = state(), entity()
        expected = legacy_box(st, e)
        moved = entity(pos=Vec3(-71, 83, 95), radius=77., yaw=1.2)
        expected_moved = legacy_box(st, moved)
        with patch.object(fleet_geometry, 'station_mesh', wraps=fleet_geometry.station_mesh) as mesh:
            self.assertEqual(geometry.station_camera_box(st, e), expected)
            self.assertEqual(geometry.station_camera_box(st, moved), expected_moved)
            self.assertEqual(mesh.call_count, 1, 'model-space extrema must not rescan triangles per entity/frame')
    def test_all_station_families_match_legacy_extrema_exactly(self):
        from game.systems.planet_buildings import BUILDING_TYPES
        kinds = (*fleet_geometry.STATION_TYPES, 'defense_satellite', 'attack_satellite', *BUILDING_TYPES)
        planet = SimpleNamespace(id=7, radius=430., pos=Vec3(37., -21., 65.))
        for faction, kind in itertools.product(('imperial', 'rebel', 'confederacy', 'syndicate'), kinds):
            surface = kind in BUILDING_TYPES
            satellite = kind in ('defense_satellite', 'attack_satellite')
            st = state(faction, planet)
            for angle in (0., .31, 2.7):
                e = entity(kind, satellite_slot=2 if satellite else None,
                           planet_id=7 if surface else None,
                           planet_building_slot=3 if surface else None,
                           radius=83., yaw=angle)
                with self.subTest(faction=faction, kind=kind, angle=angle):
                    self.assertEqual(geometry.station_camera_box(st, e, angle), legacy_box(st, e, angle))

    def test_unknown_identifiers_canonicalize_before_bounded_cache(self):
        self.clear_cache()
        st = state('unrecognized faction')
        for index in range(100):
            e = entity('mod-station-' + str(index))
            self.assertEqual(geometry.station_camera_box(st, e), legacy_box(st, e))
        info = geometry._station_local_bounds.cache_info()
        self.assertEqual((info.misses, info.currsize, info.maxsize), (1, 1, 64))

    def test_faction_changes_select_current_geometry(self):
        st, e = state(), entity()
        for faction in ('imperial', 'rebel', 'syndicate', 'confederacy', 'imperial'):
            st.players[0].faction = faction
            self.assertEqual(geometry.station_camera_box(st, e), legacy_box(st, e))


if __name__ == '__main__':
    unittest.main()
