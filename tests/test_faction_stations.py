"""Headless contracts for faction station hardware, not renderer mocks."""
import importlib.util
import math
import unittest

FACTIONS = ('rebel', 'confederacy', 'syndicate')
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


class FactionStationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('render.faction_stations'),
                             'non-Imperial station hardware is missing')
        from render import faction_stations
        return faction_stations

    def test_command_and_yard_are_immutable_solid_six_role_meshes(self):
        module = self.module()
        for faction in FACTIONS:
            for kind in ('command_station', 'shipyard'):
                with self.subTest(faction=faction, kind=kind):
                    mesh = module.station_mesh(faction, kind)
                    self.assertEqual(tuple(mesh), ROLES)
                    self.assertTrue(all(mesh[role] for role in ROLES))
                    self.assertIs(mesh, module.station_mesh(faction, kind))
                    with self.assertRaises(TypeError):
                        mesh['base'] = ()
                    self.assertIsInstance(mesh['base'], tuple)
                    self.check_triangles(mesh)

    def test_all_thirty_station_layouts_have_distinct_solid_silhouettes(self):
        from render.fleet_geometry import STATION_TYPES
        module = self.module()
        silhouettes = set()
        for faction in FACTIONS:
            for kind in STATION_TYPES:
                with self.subTest(faction=faction, kind=kind):
                    mesh = module.station_mesh(faction, kind)
                    self.assertTrue(all(mesh[r] for r in ROLES))
                    self.check_triangles(mesh)
                    vertices = [v for triangles in mesh.values() for _,tri in triangles for v in tri]
                    radius = max(math.sqrt(sum(x*x for x in v)) for v in vertices)
                    self.assertGreater(radius, 25)
                    self.assertLess(radius, 82)
                    # Rasterized TOP hull footprint, rather than triangle-count or
                    # emissive/paint differences, establishes tactical uniqueness.
                    mask = set()
                    for _, tri in mesh['base']:
                        for a in range(11):
                            for b in range(11-a):
                                p = tuple((tri[0][i]*a + tri[1][i]*b + tri[2][i]*(10-a-b))/10 for i in (0,2))
                                mask.add(tuple(round(x/3) for x in p))
                    signature = frozenset(mask)
                    self.assertNotIn(signature, silhouettes)
                    silhouettes.add(signature)
        self.assertEqual(len(silhouettes), 30)

    def test_cache_canonicalizes_mod_ids_before_lookup(self):
        from render.fleet_geometry import _station_mesh as imperial, STATION_TYPES
        module = self.module()
        module._station_mesh.cache_clear()
        for faction in FACTIONS:
            for kind in STATION_TYPES:
                module.station_mesh(faction,kind)
        self.assertEqual(module._station_mesh.cache_info().currsize, 30)
        before = module._station_mesh.cache_info().misses
        for index in range(100):
            for faction in FACTIONS:
                expected = module.station_mesh(faction,'research_station')
                self.assertIs(module.station_mesh(faction,f'mod_{index}'),expected)
                self.assertIs(module.station_mesh(faction,[]),expected)
            self.assertIs(module.station_mesh(f'mod_{index}','command_station'),imperial('command_station'))
            self.assertIs(module.station_mesh({},{}),imperial('research_station'))
        self.assertEqual(module._station_mesh.cache_info().misses,before)
        self.assertEqual(module._station_mesh.cache_info().currsize,30)
        self.assertEqual(module._station_mesh.cache_info().maxsize,30)
        for kind in STATION_TYPES:
            self.assertIs(module.station_mesh('imperial',kind),imperial(kind))

    def test_every_emissive_role_has_an_exterior_visible_surface(self):
        import numpy as np
        module = self.module()
        for faction in FACTIONS:
            for kind in module.STATION_TYPES:
                mesh = module.station_mesh(faction,kind)
                opaque = np.array([tri for r in ('base','dark','trim','accent') for _,tri in mesh[r]])
                origin = opaque[:,0]
                edge1 = opaque[:,1]-origin
                edge2 = opaque[:,2]-origin
                for role in ('lit','cool'):
                    visible = False
                    for normal,tri in mesh[role]:
                        direction = np.array(normal)
                        ray_start = np.mean(tri,axis=0)+direction*1e-5
                        p = np.cross(direction,edge2)
                        determinant = np.sum(edge1*p,axis=1)
                        valid = np.abs(determinant)>1e-9
                        inv = np.divide(1.,determinant,out=np.zeros_like(determinant),where=valid)
                        delta = ray_start-origin
                        u = np.sum(delta*p,axis=1)*inv
                        q = np.cross(delta,edge1)
                        v = np.sum(q*direction,axis=1)*inv
                        distance = np.sum(edge2*q,axis=1)*inv
                        blocked = valid & (u>=0) & (v>=0) & (u+v<=1) & (distance>1e-5)
                        if not blocked.any():
                            visible = True
                            break
                    with self.subTest(faction=faction,kind=kind,role=role):
                        self.assertTrue(visible,'emissive geometry buried inside opaque hardware')

    def test_render_bounds_stay_close_to_existing_nominal_station_sizes(self):
        from render.fleet_geometry import _station_mesh as imperial
        module = self.module()
        def radius(mesh):
            return max(math.sqrt(sum(x*x for x in v)) for tris in mesh.values() for _,tri in tris for v in tri)
        for kind in module.STATION_TYPES:
            baseline = radius(imperial(kind))
            for faction in FACTIONS:
                with self.subTest(faction=faction,kind=kind):
                    self.assertLessEqual(radius(module.station_mesh(faction,kind)),baseline*1.1)

    def test_material_triangle_containers_are_deeply_immutable_for_all_layouts(self):
        module = self.module()
        for faction in FACTIONS:
            for kind in module.STATION_TYPES:
                mesh = module.station_mesh(faction,kind)
                with self.subTest(faction=faction,kind=kind):
                    for triangles in mesh.values():
                        self.assertIsInstance(triangles,tuple)
                        normal,tri = triangles[0]
                        self.assertIsInstance(normal,tuple)
                        self.assertIsInstance(tri,tuple)
                        self.assertTrue(all(isinstance(v,tuple) for v in tri))
                    with self.assertRaises(TypeError):
                        mesh['base'][0][1][0][0] = 999

    def test_functional_geometry_has_service_voids_and_machine_verticality(self):
        module = self.module()
        # Clear passage samples specified in *final* model coordinates.
        for faction,kind,point in (
            ('rebel','shipyard',(0,4,0)),
            ('confederacy','shipyard',(0,9.6,41.6)),
            ('syndicate','shipyard',(15,12,20)),
            *((f,'repair_dock',(0,0,0)) for f in FACTIONS),
        ):
            mesh = module.station_mesh(faction,kind)
            # No opaque triangle's tight AABB may invade these small service volumes.
            for role in ('base','dark','trim','accent'):
                for _,tri in mesh[role]:
                    overlaps = all(min(v[i] for v in tri)-.8 <= point[i] <= max(v[i] for v in tri)+.8 for i in range(3))
                    self.assertFalse(overlaps,(faction,kind,role,'filled docking void'))
        for faction in FACTIONS:
            def axis(kind,index,fn):
                return fn(v[index] for tris in module.station_mesh(faction,kind).values() for _,tri in tris for v in tri)
            self.assertGreater(axis('sensor_station',1,max),30)
            self.assertLess(axis('mining_station',1,min),-14)
            self.assertGreater(axis('energy_relay',0,max)-axis('energy_relay',0,min),75)

    def test_lazy_imports_work_in_both_module_orders_without_opengl(self):
        import subprocess
        import sys
        for first in ('faction_stations','fleet_geometry'):
            script = f'''import sys
from render import {first}
from render import faction_stations as f
assert 'OpenGL' not in sys.modules
assert len(f.station_mesh('rebel','shipyard')) == 6
assert 'OpenGL' not in sys.modules
'''
            result = subprocess.run([sys.executable,'-c',script],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def check_triangles(self, mesh):
        for triangles in mesh.values():
            for normal, tri in triangles:
                self.assertEqual(len(tri), 3)
                self.assertTrue(all(math.isfinite(x) for v in (normal, *tri) for x in v))
                self.assertAlmostEqual(sum(x*x for x in normal), 1, places=9)
                u = tuple(tri[1][i]-tri[0][i] for i in range(3))
                v = tuple(tri[2][i]-tri[0][i] for i in range(3))
                cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                self.assertGreater(sum(x*x for x in cross), 1e-12)
                length = math.sqrt(sum(x*x for x in cross))
                self.assertGreater(sum(a*b for a,b in zip(normal,cross))/length, .999999)


if __name__ == '__main__':
    unittest.main()
