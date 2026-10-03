"""Pure model-space acceptance; no SDL or GL context needed."""
import importlib
import math
import unittest

class FleetDetailTests(unittest.TestCase):
    def test_common_ship_shapes_have_cached_beveled_hardware(self):
        g = importlib.import_module('render.fleet_geometry')
        self.assertTrue(hasattr(g, 'ship_mesh'), 'pure detailed ship geometry missing')
        signatures = set()
        for shape in ('wedge','needle','cruiser','dagger','box'):
            mesh = g.ship_mesh(shape)
            self.assertIs(mesh, g.ship_mesh(shape))
            self.assertEqual(set(mesh), {'base','dark','trim','accent','lit','cool'})
            self.assertGreater(len(mesh['base']), 40)
            self.assertGreater(len(mesh['dark']), 20)
            self.assertGreater(len(mesh['accent']), 10)
            self.assertGreater(len(mesh['lit']), 10)
            self.assertGreater(len(mesh['cool']), 10)
            self.assertLess(sum(map(len,mesh.values())), 4500)
            points = [v for tris in mesh.values() for n,tri in tris for v in tri]
            signatures.add(tuple((min(v[i] for v in points),max(v[i] for v in points)) for i in range(3)))
            for tris in mesh.values():
                for n,tri in tris:
                    self.assertAlmostEqual(sum(x*x for x in n), 1., places=6)
                    u=[tri[1][i]-tri[0][i] for i in range(3)]
                    v=[tri[2][i]-tri[0][i] for i in range(3)]
                    cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    self.assertGreater(sum(a*b for a,b in zip(n,cross)),1e-8)
                    self.assertTrue(all(math.isfinite(x) for p in tri for x in p))
        self.assertEqual(len(signatures),5,'ship silhouettes collapsed')

    def test_station_types_are_distinct_alloy_hardware_not_generic_boxes(self):
        g = importlib.import_module('render.fleet_geometry')
        self.assertTrue(hasattr(g, 'station_mesh'), 'pure detailed station geometry missing')
        ids = ('command_station','shipyard','research_station','defense_platform',
               'mining_station','sensor_station','trade_station','fighter_platform',
               'repair_dock','energy_relay')
        signatures = set()
        for did in ids:
            mesh = g.station_mesh(did)
            self.assertIs(mesh, g.station_mesh(did))
            self.assertEqual(set(mesh), {'base','dark','trim','accent','lit','cool'})
            for role in mesh:
                self.assertGreater(len(mesh[role]),10,(did,role))
            self.assertLess(sum(map(len,mesh.values())),6500,did)
            points=[v for tris in mesh.values() for n,tri in tris for v in tri]
            self.assertLess(max(abs(x) for v in points for x in v),110)
            self.assertGreater(max(abs(x) for v in points for x in v),30)
            signatures.add(tuple((min(v[i] for v in points),max(v[i] for v in points)) for i in range(3)))
            for tris in mesh.values():
                for n,tri in tris:
                    self.assertAlmostEqual(sum(x*x for x in n),1.,places=6)
                    self.assertTrue(all(math.isfinite(x) for v in tri for x in v))
        self.assertEqual(len(signatures),len(ids))

if __name__=='__main__': unittest.main()
