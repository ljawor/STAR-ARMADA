"""CPU geometry contract for the original Alliance escort specimen; no bpy."""
import importlib.util
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/art/alliance_redesign_ship_designs.py'


class Geometry:
    """Faithful explicit-surface facade for imperium_fleet_geometry's API."""
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces, bevel=0):
        assert bevel == 0, 'Budgets must measure authored geometry, not modifiers'
        self.parts.append((name, role, list(verts), list(faces)))

    def loft(self, name, role, stations, x=0, bevel=0):
        vv = []
        for z, w, t, b in stations:
            c = min((t-b)*.24, w*.3)
            vv.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),
                       (x+w,b+c,z),(x+w-c,b,z),(x-w+c,b,z),
                       (x-w,b+c,z),(x-w,t-c,z)])
        ff = [tuple(reversed(range(8))), tuple(range(len(vv)-8,len(vv)))]
        ff.extend((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j)
                  for k in range(len(stations)-1) for j in range(8))
        self.mesh(name,role,vv,ff,bevel)

    def box(self,name,role,loc,size,bevel=0):
        vv = [tuple(loc[i]+s[i]*size[i]/2 for i in range(3))
              for s in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                        (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        self.mesh(name,role,vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),
                              (3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)

    def ring(self,name,role,x,y,stations,n=12):
        assert all(0 < inner < outer for _,outer,inner in stations)
        vv = [(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z)
              for z,o,i in stations for r in (o,i) for j in range(n)]
        ff = []
        for k in range(len(stations)-1):
            for wall in (0,1):
                a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
                ff.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
        for k in (0,len(stations)-1):
            a=k*2*n
            ff.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
        self.mesh(name,role,vv,ff)

    def disc(self,name,role,x,y,z,r,depth,n=12):
        vv=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+d*depth/2)
            for d in (-1,1) for j in range(n)]
        self.mesh(name,role,vv,[tuple(reversed(range(n))),tuple(range(n,2*n))]+
                  [(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)])


def specimen():
    assert SOURCE.exists(), 'New Alliance ship design module is absent'
    spec = importlib.util.spec_from_file_location('alliance_redesign_ship_designs', SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bounds = json.loads((ROOT/'assets/models/manifests/alliance_frigate.json').read_text())['bounds']
    lo, hi = bounds['min'], bounds['max']
    frame = {'lo':lo, 'hi':hi, 'span':[hi[i]-lo[i] for i in range(3)],
             'center':[(hi[i]+lo[i])/2 for i in range(3)]}
    g = Geometry()
    module.build('frigate',g,frame)
    return module,g,frame


class AllianceFrigateTests(unittest.TestCase):
    def test_specimen_fills_actual_manifest_with_six_roles_and_explicit_budget(self):
        _,g,frame = specimen()
        vv = [v for _,_,vs,_ in g.parts for v in vs]
        tri = sum(len(f)-2 for _,_,_,fs in g.parts for f in fs)
        self.assertEqual({p[1] for p in g.parts}, {'base','dark','trim','accent','lit','cool'})
        self.assertTrue(6000 <= tri <= 10000, tri)
        self.assertLess(tri,11888)
        self.assertLess(len(vv),9500)
        self.assertEqual(len({p[0] for p in g.parts}),len(g.parts))
        for axis in range(3):
            low,high = min(v[axis] for v in vv),max(v[axis] for v in vv)
            self.assertGreaterEqual(low,frame['lo'][axis])
            self.assertLessEqual(high,frame['hi'][axis])
            self.assertTrue(.997 <= (high-low)/frame['span'][axis] <= .999)
            self.assertAlmostEqual((low+high)/2,frame['center'][axis],places=6)
        for name,role,vs,fs in g.parts:
            self.assertTrue(all(math.isfinite(c) for v in vs for c in v),name)
            for face in fs:
                for j in range(1,len(face)-1):
                    a,b,c = (vs[k] for k in (face[0],face[j],face[j+1]))
                    u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
                    cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    self.assertGreater(sum(x*x for x in cross),1e-16,(name,face))
        print('Alliance frigate:',tri,'triangles;',len(vv),'raw vertices;',len(g.parts),'parts')

    def test_deck_fittings_are_horizontal_not_vertical_wheels(self):
        _,g,_ = specimen()
        fittings = [p for p in g.parts if 'armored bearing' in p[0] or 'captive fastener' in p[0]]
        self.assertEqual(len(fittings),32)
        for name,_,vs,_ in fittings:
            spans = [max(v[i] for v in vs)-min(v[i] for v in vs) for i in range(3)]
            self.assertLess(spans[1],min(spans[0],spans[2])*.5,name)

    def test_all_components_have_a_structural_broad_phase_connection(self):
        # Broad phase catches detached towers/plates, not a welded-manifold claim.
        _,g,_ = specimen()
        bounds = [[(min(v[i] for v in p[2]),max(v[i] for v in p[2]))
                   for i in range(3)] for p in g.parts]
        connected = {0}
        while True:
            added = {j for j,b in enumerate(bounds) if j not in connected and
                     any(all(b[k][0] <= bounds[i][k][1]+1e-6 and
                             bounds[i][k][0] <= b[k][1]+1e-6 for k in range(3))
                         for i in connected)}
            if not added:
                break
            connected.update(added)
        self.assertEqual(len(connected),len(g.parts),
                         [p[0] for i,p in enumerate(g.parts) if i not in connected])

    def test_other_classes_are_rejected_without_emitting_geometry(self):
        module,_,frame = specimen()
        g = Geometry()
        with self.assertRaises(ValueError):
            module.build('cruiser',g,frame)
        self.assertFalse(g.parts)

    def test_drive_bores_leave_aft_sight_rays_unobstructed(self):
        _,g,_ = specimen()
        emitters = [p for p in g.parts if 'exposed cyan drive emitter' in p[0]]
        self.assertEqual(len(emitters),2)
        opaque = []
        for name,role,vs,fs in g.parts:
            if role == 'cool':
                continue
            for face in fs:
                opaque.extend((name,vs[face[0]],vs[face[q]],vs[face[q+1]])
                              for q in range(1,len(face)-1))
        for name,_,vs,_ in emitters:
            xx=sum(v[0] for v in vs)/len(vs); yy=sum(v[1] for v in vs)/len(vs)
            zz=min(v[2] for v in vs); radius=max(v[0] for v in vs)-xx
            for radial in (0,.35,.72,.95):
                for angle in range(12):
                    px=xx+radius*radial*math.cos(angle*math.pi/6)
                    py=yy+radius*radial*math.sin(angle*math.pi/6)
                    for obstacle,a,b,c in opaque:
                        den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                        if abs(den)<1e-10:
                            continue
                        u=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/den
                        v=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/den
                        w=1-u-v
                        if min(u,v,w)>=-1e-8:
                            self.assertGreater(u*a[2]+v*b[2]+w*c[2],zz-1e-7,(name,obstacle))


if __name__ == '__main__':
    unittest.main()
