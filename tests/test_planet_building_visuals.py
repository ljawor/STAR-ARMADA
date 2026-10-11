"""Pure surface geometry and shared world-space rendering/picking contract."""
import importlib
import math
import unittest
from game.core.entity import Entity
from game.core.vectors import Vec3
from game.systems.planet_buildings import BUILDING_TYPES, planet_building_site


class SurfaceGeometryTests(unittest.TestCase):
    def test_solid_distinct_buildings_have_foundations_and_material_roles(self):
        from render.fleet_geometry import station_mesh
        signatures = []
        for kind in BUILDING_TYPES:
            mesh = station_mesh(kind)
            pts = [p for role in mesh.values() for _, tri in role for p in tri]
            self.assertGreater(len(pts), 100)
            self.assertGreaterEqual(min(p[1] for p in pts), 0)
            self.assertEqual(min(p[1] for p in pts), 0)
            self.assertGreater(max(p[1] for p in pts), 25)
            self.assertTrue(all(mesh[r] for r in ('base','dark','trim','accent','cool')))
            for role in mesh.values():
                for n, tri in role:
                    self.assertAlmostEqual(sum(v*v for v in n), 1.)
                    a,b,c = tri
                    u = tuple(b[i]-a[i] for i in range(3))
                    v = tuple(c[i]-a[i] for i in range(3))
                    cross = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    self.assertGreater(sum(cross[i]*n[i] for i in range(3)), 0)
            signatures.append(tuple(pts))
        self.assertEqual(len(set(signatures)), 4)

    def test_world_vertices_clear_actual_sphere_at_all_six_factory_anchors(self):
        module = importlib.import_module('render.planet_building_geometry')
        self.assertTrue(hasattr(module, 'station_world_mesh'), 'missing shared world mesh')
        from types import SimpleNamespace
        planet = Entity(id=1, kind='planet', owner=-1, data_id='temperate', pos=Vec3(13,77,-91), radius=650)
        state = SimpleNamespace(entity=lambda i: planet if i == 1 else None,
                                players={})
        for slot in range(6):
            foundation, normal = planet_building_site(planet, slot)
            e = Entity(id=2, kind='station', data_id='planet_pulsar_cannon',
                       owner=0, radius=85, pos=foundation,
                       planet_id=1, planet_building_slot=slot)
            points = [p for role in module.station_world_mesh(state,e,0).values()
                      for _, tri in role for p in tri]
            self.assertGreaterEqual(min(math.dist(p, (13,77,-91)) for p in points), planet.radius)
            # No camera/time-dependent floating/magnification of surface sites.
            self.assertEqual(module.station_world_mesh(state,e,0),module.station_world_mesh(state,e,2))
            heights = [sum((p[i]-foundation.to_tuple()[i])*normal.to_tuple()[i] for i in range(3)) for p in points]
            self.assertAlmostEqual(min(heights), 1.)

    def test_slots_are_owned_selected_only_and_show_paid_progress(self):
        from types import SimpleNamespace
        module = importlib.import_module('render.planet_building_geometry')
        self.assertTrue(hasattr(module,'visible_surface_slots'), 'missing slot affordances')
        planet = Entity(id=1,kind='planet',owner=-1,data_id='temperate',radius=650)
        planet.is_planet = True
        planet.colonized_by = 0
        planet.build_queue = [dict(kind='planet_building',slot=1,item='planet_trade_hub',time_left=5,total=20)]
        building = Entity(id=2,kind='station',owner=0,data_id='planet_extractor',planet_id=1,planet_building_slot=0)
        state = SimpleNamespace(entities={1:planet,2:building},can_see=lambda owner,eid: True)
        slots = module.visible_surface_slots(state,0,{1})
        self.assertEqual(len(slots),6)
        self.assertEqual([s['status'] for s in slots],['occupied','building','empty','empty','empty','empty'])
        self.assertEqual(slots[1]['progress'],.75)
        self.assertEqual(module.visible_surface_slots(state,1,{1}),())
        self.assertEqual(module.visible_surface_slots(state,0,set()),())
        planet.colonized_by=1
        self.assertEqual(module.visible_surface_slots(state,0,{1}),())

    def test_picking_uses_outward_hardware_not_foundation_or_camera_spin(self):
        module=importlib.import_module('render.planet_building_geometry')
        self.assertTrue(hasattr(module,'station_pick_distance'),'missing mesh picking API')
        from types import SimpleNamespace
        planet=Entity(id=1,kind='planet',owner=-1,data_id='temperate',radius=650)
        pos,_=planet_building_site(planet,4)
        e=Entity(id=2,kind='station',owner=0,data_id='planet_pulsar_cannon',radius=85,
                 pos=pos,planet_id=1,planet_building_slot=4)
        state=SimpleNamespace(entity=lambda i:planet,players={})
        camera=SimpleNamespace(world_to_screen=lambda x,y,z:(x,y),_station_angle=lambda:1.)
        pts=[p for m in module.station_world_mesh(state,e).values() for _,tri in m for p in tri]
        point=max(pts,key=lambda p:p[1])
        self.assertLess(module.station_pick_distance(state,e,camera,(point[0],point[1]),28),28)
        self.assertGreater(module.station_pick_distance(state,e,camera,(1000,1000),28),28)
        box=module.station_camera_box(state,e)
        for p in pts:
            self.assertTrue(all(box[2][i]<=p[i]-box[0][i]<=box[3][i] for i in range(3)))
