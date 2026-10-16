"""Runtime contracts for the authored escort and industrial open-cradle yard."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

ROOT = Path(__file__).resolve().parents[1]

class AuthoredTrioTests(unittest.TestCase):
    def cases(self):
        from render import authored_mesh as a
        from render.faction_ships import ship_mesh
        from render.faction_stations import station_mesh
        return [('frigate', a.load_frigate, a.frigate_mesh, lambda: ship_mesh('rebel','frigate')),
                ('shipyard', a.load_shipyard, a.shipyard_mesh, lambda: station_mesh('rebel','shipyard'))]

    def test_all_unselected_catalogue_entries_are_byte_identical(self):
        import hashlib
        from render.faction_ships import ship_mesh
        from render.faction_stations import station_mesh
        expected=json.loads((ROOT/'tests/fixtures/alliance_trio_unselected.sha256.json').read_text())
        from render.fleet_geometry import ship_mesh as legacy_ship_mesh, _station_mesh as legacy_station_mesh
        self.assertEqual(len(expected),73)
        for key,digest in expected.items():
            kind,faction,role=key.split('/')
            if kind=='legacy_ship':mesh=legacy_ship_mesh(role)
            elif faction=='imperial':mesh=legacy_station_mesh(role)
            else:mesh=(ship_mesh if kind=='ship' else station_mesh)(faction,role)
            with self.subTest(entry=key):
                self.assertEqual(hashlib.sha256(repr(dict(mesh)).encode()).hexdigest(),digest)

    def test_live_export_and_deep_immutability(self):
        for name, loader, cached, facade in self.cases():
            with self.subTest(asset=name):
                path=ROOT/f'assets/models/alliance_{name}.mesh.json'
                data=json.loads(path.read_text())
                mesh=loader(path)
                self.assertEqual(mesh,facade())
                self.assertEqual(mesh,cached())
                self.assertIs(cached(),cached())
                self.assertEqual(cached.cache_info().maxsize,1)
                # Ceiling raised from 9000 by s07-detail-budget-2026-10-16; the runtime
                # loader caps an authored mesh at 12000 triangles and 10000 vertices.
                self.assertLess(data['triangle_count'],11888)
                self.assertGreater(data['triangle_count'],1800)
                self.assertLess(len(data['vertices']),9500)
                self.assertEqual(set(mesh),{'base','dark','trim','accent','lit','cool'})
                for role,faces in data['batches'].items():
                    self.assertEqual(mesh[role],tuple((tuple(f[:3]),tuple(tuple(data['vertices'][i]) for i in f[3:])) for f in faces))
                with self.assertRaises(TypeError): mesh['base']=()
                with self.assertRaises(TypeError): mesh['base'][0][1][0][0]=0
                self.assertTrue((ROOT/f'art/blender/alliance_{name}.blend').is_file())
                self.assertTrue((ROOT/f'tools/art/build_alliance_{name}.py').is_file())

    def test_finite_bounds_normals_winding_indices_and_corruption(self):
        for name, loader, _, _ in self.cases():
            original=json.loads((ROOT/f'assets/models/alliance_{name}.mesh.json').read_text())
            mutations=[lambda d:d.update(schema=99),lambda d:d.update(asset='other'),
                lambda d:d.update(bounds=[[0]*3]*2),lambda d:d.update(triangle_count=-1),
                lambda d:d['batches'].pop('cool'),lambda d:d['vertices'][0].__setitem__(0,float('nan')),
                lambda d:d['vertices'][0].__setitem__(0,10000),
                lambda d:d['batches']['base'][0].__setitem__(3,len(d['vertices'])),
                lambda d:d['batches']['base'][0].__setitem__(3,True),
                lambda d:d['batches']['base'][0].__setitem__(0,5),
                lambda d:d['batches']['base'][0].__setitem__(slice(3,6),list(reversed(d['batches']['base'][0][3:]))),
                lambda d:d['batches']['base'][0].__setitem__(4,d['batches']['base'][0][3])]
            with tempfile.TemporaryDirectory() as root:
                p=Path(root)/'bad.json'
                for i,mutate in enumerate(mutations):
                    with self.subTest(asset=name,case=i):
                        d=copy.deepcopy(original);mutate(d);p.write_text(json.dumps(d))
                        with self.assertRaises(ValueError):loader(p)
                p.write_bytes(b' ' * 2000001)
                with self.assertRaises(ValueError):loader(p)
                p.write_text('{')
                with self.assertRaises(ValueError):loader(p)

    def test_missing_and_corrupt_assets_use_bounded_fallback(self):
        from render import authored_mesh as a, faction_ships as fs, faction_stations as ft
        for name,_,cached,facade in self.cases():
            facade_cache=fs._ship_mesh if name=='frigate' else ft._station_mesh
            expected=facade()
            try:
                for error in [OSError('missing'),ValueError('corrupt')]:
                    facade_cache.cache_clear()
                    with patch.object(a,name+'_mesh',side_effect=error):
                        with warnings.catch_warnings(record=True) as seen:
                            warnings.simplefilter('always');fallback=facade();self.assertIs(fallback,facade())
                        self.assertEqual(len(seen),1)
                        self.assertTrue(all(fallback.values()))
                        self.assertNotEqual(expected,fallback)
            finally:
                cached.cache_clear();facade_cache.cache_clear()

    def test_each_drive_emitter_has_unobstructed_aft_broad_face(self):
        # Shoot parallel aft rays through nine samples of each emitting disc.
        # This catches a shroud aperture backed by a solid pressure-hull cap.
        for name, _, cached, _ in self.cases():
            mesh=cached()
            data=json.loads((ROOT/f'assets/models/alliance_{name}.mesh.json').read_text())
            offset=0;centers=[]
            for part in data['parts']:
                if part['role']!='cool':continue
                end=offset+part['triangles']
                if 'emitter' in part['name']:
                    points=[p for _,tri in mesh['cool'][offset:end] for p in tri]
                    centers.append(tuple((min(p[i] for p in points)+max(p[i] for p in points))/2
                                         if i<2 else min(p[i] for p in points) for i in range(3)))
                offset=end
            self.assertEqual(len(centers),2)
            for center in centers:
                for dx in (-1.2,0,1.2):
                    for dy in (-1.2,0,1.2):
                        x,y,z=center[0]+dx,center[1]+dy,center[2]
                        for role in ('base','dark','trim','accent'):
                            for _,tri in mesh[role]:
                                a,b,c=tri
                                d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                                if abs(d)<1e-10:continue
                                u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d
                                v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d
                                if min(u,v,1-u-v)>=-1e-8:
                                    hit=u*a[2]+v*b[2]+(1-u-v)*c[2]
                                    self.assertGreaterEqual(hit,z-.01,(name,center,'buried emitting face',role,hit))

    def test_each_worklight_is_a_named_exposed_broad_face(self):
        d=json.loads((ROOT/'assets/models/alliance_shipyard.mesh.json').read_text())
        lights=[p for p in d['parts'] if p['name'].startswith('Worklight exposed lens')]
        self.assertEqual(len(lights),4)
        self.assertTrue(all(p['role']=='lit' and p['triangles']>=12 for p in lights))
        # Lights sit above rather than inside rails; final visibility is checked per
        # feature using real production GL difference images in the capture probe.
        self.assertEqual(len(d['features']['worklights']),4)
        self.assertTrue(all(f['center'][1]>5 for f in d['features']['worklights']))
