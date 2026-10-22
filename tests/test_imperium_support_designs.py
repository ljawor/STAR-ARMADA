"""CPU contract checks; no bpy, renderer, or approved builders imported."""
import importlib.util
from pathlib import Path
import math
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/art/imperium_support_designs.py'
BOUNDS = {
    'bomber': ([-31.25, -3.24, -28.996], [31.25, 14, 35]),
    'colonizer': ([-20, -7, -24.6975], [20, 26.5, 24.35825]),
    'convoy': ([-19.5, -6.8, -24.6975], [19.5, 25.73641, 24.35825]),
}

class Geometry:
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces, bevel=0):
        self.parts.append((name, role, verts, faces, bevel))


def load():
    spec = importlib.util.spec_from_file_location('support_designs', SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SupportDesignTests(unittest.TestCase):
    def test_complete_geometry_contract(self):
        self.assertTrue(SOURCE.exists(), 'new support design module must exist')
        module = load()
        for kind, (lo, hi) in BOUNDS.items():
            with self.subTest(kind=kind):
                g = Geometry()
                frame = dict(lo=lo, hi=hi, span=[b-a for a,b in zip(lo,hi)],
                             center=[(a+b)/2 for a,b in zip(lo,hi)])
                module.build(kind, g, frame)
                self.assertGreater(len(g.parts), 40)
                self.assertEqual({p[1] for p in g.parts},
                                 {'base','dark','trim','accent','lit','cool'})
                self.assertEqual(len({p[0] for p in g.parts}), len(g.parts))
                vertices = [v for p in g.parts for v in p[2]]
                self.assertTrue(all(math.isfinite(x) for v in vertices for x in v))
                triangles = sum(len(f)-2 for p in g.parts for f in p[3])
                self.assertLess(triangles, 6000 if kind == 'bomber' else 10000)
                self.assertLess(len(vertices), 10000)
                for axis in range(3):
                    low = min(v[axis] for v in vertices)
                    high = max(v[axis] for v in vertices)
                    self.assertGreaterEqual(low, lo[axis]+.003-1e-9)
                    self.assertLessEqual(high, hi[axis]-.003+1e-9)
                    self.assertLess(low-lo[axis], frame['span'][axis]*.01)
                    self.assertLess(hi[axis]-high, frame['span'][axis]*.01)
                for name, role, verts, faces, bevel in g.parts:
                    self.assertEqual(bevel, 0, name)
                    for face in faces:
                        self.assertGreaterEqual(len(face), 3)
                        self.assertEqual(len(face), len(set(face)))
                        self.assertTrue(all(0 <= i < len(verts) for i in face))
                # Every kit part overlaps the connected assembly by its AABB.
                boxes = [([min(v[i] for v in p[2]) for i in range(3)],
                          [max(v[i] for v in p[2]) for i in range(3)]) for p in g.parts]
                reached = {0}
                while True:
                    added = {j for j, (a,b) in enumerate(boxes) if j not in reached
                             and any(all(a[k] <= boxes[i][1][k]+1e-8 and
                                         b[k] >= boxes[i][0][k]-1e-8 for k in range(3))
                                     for i in reached)}
                    if not added:
                        break
                    reached.update(added)
                self.assertEqual(len(reached), len(boxes),
                                 [g.parts[i][0] for i in range(len(boxes)) if i not in reached])

    def test_engine_faces_are_first_hits_from_stern(self):
        module = load()
        for kind, (lo, hi) in BOUNDS.items():
            g = Geometry()
            module.build(kind, g, dict(lo=lo, hi=hi))
            emitters = [p for p in g.parts if 'connected cyan emitter' in p[0]]
            self.assertEqual(len(emitters), 2)
            triangles = [(p[0], p[1], [p[2][face[j]] for j in (0,i,i+1)])
                         for p in g.parts for face in p[3] for i in range(1,len(face)-1)]
            for emitter in emitters:
                vs = emitter[2]
                cx,cy = [sum(v[i] for v in vs)/len(vs) for i in (0,1)]
                rx,ry = [max(v[i] for v in vs)-[cx,cy][i] for i in (0,1)]
                for dx,dy in ((0,0),(.4,0),(-.4,0),(0,.4),(0,-.4),(.3,.3),(-.3,-.3)):
                    px,py = cx+rx*dx,cy+ry*dy
                    hits = []
                    for name,role,(a,b,c) in triangles:
                        det = (b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1])
                        if abs(det) < 1e-12:
                            continue
                        u = ((px-a[0])*(c[1]-a[1])-(c[0]-a[0])*(py-a[1]))/det
                        v = ((b[0]-a[0])*(py-a[1])-(px-a[0])*(b[1]-a[1]))/det
                        if u >= -1e-9 and v >= -1e-9 and u+v <= 1+1e-9:
                            hits.append((a[2]+u*(b[2]-a[2])+v*(c[2]-a[2]), name, role))
                    self.assertTrue(hits)
                    self.assertEqual(min(hits)[1], emitter[0], (kind,dx,dy,min(hits)))

    def test_faces_are_nondegenerate_and_closed_per_part(self):
        module = load()
        for kind, (lo,hi) in BOUNDS.items():
            g = Geometry()
            module.build(kind,g,dict(lo=lo,hi=hi))
            for name,_,verts,faces,_ in g.parts:
                edges = {}
                for f in faces:
                    for a,b in zip(f, f[1:]+f[:1]):
                        edge = tuple(sorted((a,b)))
                        edges[edge] = edges.get(edge,0)+1
                    for i in range(1,len(f)-1):
                        a,b,c = [verts[f[j]] for j in (0,i,i+1)]
                        u,v = [[p[k]-a[k] for k in range(3)] for p in (b,c)]
                        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2],
                                 u[0]*v[1]-u[1]*v[0]]
                        self.assertGreater(sum(x*x for x in cross), 1e-12, name)
                self.assertTrue(all(count == 2 for count in edges.values()), name)

    def test_invalid_inputs_emit_nothing(self):
        module = load()
        g = Geometry()
        with self.assertRaises(ValueError):
            module.build('fighter',g,dict(lo=[0,0,0],hi=[1,1,1]))
        with self.assertRaises(ValueError):
            module.build('bomber',g,dict(lo=[0,0,0],hi=[0,1,1]))
        self.assertEqual(g.parts, [])

if __name__ == '__main__':
    unittest.main()
