"""CPU-only contract probe: actual authored surfaces, no bpy or renderer."""
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/art/imperium_capital_designs.py'
FRAMES = {
    'frigate': ([-16,-5,-43.601], [16,24,48]),
    'cruiser': ([-29.45,-7,-62.94], [29.45,31.5,78]),
    'battleship': ([-38.45,-10,-80.183], [38.45,39.5,108]),
    'supercapital': ([-38.45,-10,-80.183], [38.45,39.5,108]),
}

class Geometry:
    def __init__(self): self.parts = []
    def mesh(self, name, role, verts, faces, bevel=0):
        assert bevel == 0, 'CPU budget probe requires explicit geometry, not unknown modifiers'
        self.parts.append((name, role, list(verts), list(faces)))
    def loft(self, name, role, stations, x=0, bevel=0):
        vv=[]
        for z,w,t,b in stations:
            c=min((t-b)*.24,w*.3)
            vv.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),(x+w,b+c,z),(x+w-c,b,z),(x-w+c,b,z),(x-w,b+c,z),(x-w,t-c,z)])
        ff=[tuple(reversed(range(8))),tuple(range(len(vv)-8,len(vv)))]
        ff.extend((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j) for k in range(len(stations)-1) for j in range(8))
        self.mesh(name,role,vv,ff,bevel)
    def box(self,name,role,loc,size,bevel=0):
        vv=[tuple(loc[i]+s[i]*size[i]/2 for i in range(3)) for s in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        self.mesh(name,role,vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)
    def ring(self,name,role,x,y,stations,n=12):
        vv=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z) for z,o,i in stations for r in (o,i) for j in range(n)]
        ff=[]
        for k in range(len(stations)-1):
            for wall in (0,1):
                a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
                ff.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
        for k in (0,len(stations)-1):
            a=k*2*n
            ff.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
        self.mesh(name,role,vv,ff)
    def disc(self,name,role,x,y,z,r,depth,n=12):
        vv=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+d*depth/2) for d in (-1,1) for j in range(n)]
        self.mesh(name,role,vv,[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)])

class CapitalDesignTests(unittest.TestCase):
    def test_dispatcher_creates_bounded_six_role_class_distinct_geometry(self):
        self.assertTrue(SOURCE.exists(), 'new capital geometry dispatcher is absent')
        spec=importlib.util.spec_from_file_location('capital_designs',SOURCE)
        assert spec is not None and spec.loader is not None
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        signatures=[]
        for kind,(lo,hi) in FRAMES.items():
            with self.subTest(kind=kind):
                frame={'lo':lo,'hi':hi,'span':[hi[i]-lo[i] for i in range(3)],'center':[(hi[i]+lo[i])/2 for i in range(3)]}
                g=Geometry(); module.build(kind,g,frame)
                vv=[v for _,_,vs,_ in g.parts for v in vs]
                tri=sum(len(f)-2 for _,_,_,fs in g.parts for f in fs)
                self.assertEqual({p[1] for p in g.parts},{'base','dark','trim','accent','lit','cool'})
                self.assertTrue(5000<=tri<=12000,(kind,tri))
                self.assertLessEqual(len(vv),10000)
                for axis in range(3):
                    low=min(v[axis] for v in vv); high=max(v[axis] for v in vv)
                    self.assertGreaterEqual(low,lo[axis]+.003-1e-8)
                    self.assertLessEqual(high,hi[axis]-.003+1e-8)
                    self.assertLess(low-lo[axis],frame['span'][axis]*.01)
                    self.assertLess(hi[axis]-high,frame['span'][axis]*.01)
                # Aft sight rays must leave each broad cyan disc unobstructed.
                # Fan triangulation is sufficient for the convex primitive faces.
                opaque=[]
                for part,role,vs,fs in g.parts:
                    if role=='cool': continue
                    for f in fs:
                        opaque.extend((part,vs[f[0]],vs[f[q]],vs[f[q+1]]) for q in range(1,len(f)-1))
                for part,role,vs,fs in g.parts:
                    if 'exposed cyan drive emitter' not in part: continue
                    xx=sum(v[0] for v in vs)/len(vs); yy=sum(v[1] for v in vs)/len(vs)
                    zz=min(v[2] for v in vs)
                    rr=max(v[0] for v in vs)-xx
                    for rad in (.35,.72):
                        for angle in range(8):
                            px=xx+rr*rad*math.cos(angle*math.pi/4)
                            py=yy+rr*rad*math.sin(angle*math.pi/4)
                            for obstacle,a,b,c in opaque:
                                den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                                if abs(den)<1e-10: continue
                                u=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/den
                                v=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/den
                                w=1-u-v
                                if min(u,v,w)>=-1e-8:
                                    hit=u*a[2]+v*b[2]+w*c[2]
                                    self.assertGreater(hit,zz-1e-7,(kind,part,'buried by',obstacle))
                signatures.append(tuple(p[0] for p in g.parts))
                print(kind, 'triangles',tri,'raw_vertices',len(vv),'parts',len(g.parts))
        self.assertEqual(len(set(signatures)),4)

if __name__=='__main__': unittest.main()
