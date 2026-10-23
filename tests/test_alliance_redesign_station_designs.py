"""CPU-only geometry contract for the original Alliance twin-slip shipyard."""
import ast
import importlib.util
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/art/alliance_redesign_station_designs.py'
ROLES = {'base', 'dark', 'trim', 'accent', 'lit', 'cool'}


class Geometry:
    """Run the production primitive mathematics, replacing only Blender mesh IO."""
    def __init__(self):
        self.parts = []
        source = ast.parse((ROOT / 'tools/art/imperium_fleet_geometry.py').read_text())
        source.body = [n for n in source.body if isinstance(n, ast.FunctionDef)
                       and n.name in {'box', 'loft', 'ring', 'disc'}]
        scope = {'math': math, 'mesh': self.mesh}
        exec(compile(source, '<production geometry primitives>', 'exec'), scope)
        for name in ('box', 'loft', 'ring', 'disc'):
            setattr(self, name, scope[name])

    def mesh(self, name, role, verts, faces, bevel=0):
        self.parts.append((name, role, verts, faces, bevel))


def load():
    spec = importlib.util.spec_from_file_location('alliance_station_designs', SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame():
    bounds = json.loads((ROOT / 'assets/models/manifests/alliance_shipyard.json').read_text())['bounds']
    lo, hi = bounds['min'], bounds['max']
    return dict(lo=lo, hi=hi, span=[b-a for a, b in zip(lo, hi)],
                center=[(a+b)/2 for a, b in zip(lo, hi)])


def specimen(f=None):
    g = Geometry()
    load().build('shipyard', g, f or frame())
    return g


class AllianceStationTests(unittest.TestCase):
    def test_complete_cpu_contract(self):
        self.assertTrue(SOURCE.exists(), 'dedicated Alliance station design must exist')
        g, f = specimen(), frame()
        self.assertEqual({p[1] for p in g.parts}, ROLES)
        self.assertEqual(len({p[0] for p in g.parts}), len(g.parts))
        vertices = [v for p in g.parts for v in p[2]]
        triangles = sum(len(face)-2 for p in g.parts for face in p[3])
        self.assertGreaterEqual(triangles, 7000)
        self.assertLessEqual(triangles, 11000)
        self.assertLess(triangles, 11888)
        self.assertLess(len(vertices), 9500)
        self.assertTrue(all(math.isfinite(c) for v in vertices for c in v))
        for axis in range(3):
            low, high = min(v[axis] for v in vertices), max(v[axis] for v in vertices)
            self.assertGreaterEqual(low, f['lo'][axis])
            self.assertLessEqual(high, f['hi'][axis])
            self.assertGreaterEqual((high-low)/f['span'][axis], .997)
            self.assertLessEqual((high-low)/f['span'][axis], .999)
        for name, _, verts, faces, bevel in g.parts:
            self.assertEqual(bevel, 0, name)
            edges = {}
            for face in faces:
                self.assertEqual(len(face), len(set(face)), name)
                self.assertTrue(all(0 <= i < len(verts) for i in face), name)
                for a, b in zip(face, face[1:]+face[:1]):
                    key = tuple(sorted((a, b)))
                    edges[key] = edges.get(key, 0)+1
                for i in range(1, len(face)-1):
                    a, b, c = [verts[face[j]] for j in (0, i, i+1)]
                    u, v = [[p[k]-a[k] for k in range(3)] for p in (b, c)]
                    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                    self.assertGreater(sum(x*x for x in cross), 1e-12, name)
            self.assertTrue(all(count == 2 for count in edges.values()), name)
    def test_shipyard_parts_and_two_unobstructed_slips(self):
        g, f = specimen(), frame()
        names = [p[0] for p in g.parts]
        for feature, count in (('outer slipway rail', 2), ('inner slipway rail', 2),
                               ('lower tie', 16), ('rail bogie', 8),
                               ('attached habitat pod', 12), ('fabrication module', 16)):
            self.assertEqual(sum(feature in name for name in names), count, feature)
        self.assertTrue(any('hub pressure habitat' in name for name in names))
        self.assertTrue(any('cab warm glazing' in p[0] and p[1] == 'lit' for p in g.parts))
        self.assertTrue(any('guide beacon' in p[0] and p[1] == 'cool' for p in g.parts))
        # AABB exclusion is stronger than a few sight-line samples: the complete
        # rectangular vessel-clearance volumes stay empty from mouth to mouth.
        for side in (-1, 1):
            clear_lo = [min(side*.205, side*.385), -.065, -.5]
            clear_hi = [max(side*.205, side*.385), .255, .5]
            for name, _, verts, _, _ in g.parts:
                nv = [[(v[i]-f['center'][i])/(f['span'][i]*.998)
                       for i in range(3)] for v in verts]
                low = [min(v[i] for v in nv) for i in range(3)]
                high = [max(v[i] for v in nv) for i in range(3)]
                self.assertFalse(all(low[i] < clear_hi[i] and high[i] > clear_lo[i]
                                     for i in range(3)), (side, name, 'sealed slip'))

    def test_every_part_attaches_to_the_assembly(self):
        g = specimen()
        bounds = [([min(v[i] for v in p[2]) for i in range(3)],
                   [max(v[i] for v in p[2]) for i in range(3)]) for p in g.parts]
        reached = {0}
        while True:
            added = {j for j, (lo, hi) in enumerate(bounds) if j not in reached
                     and any(all(lo[k] <= bounds[i][1][k]+1e-8 and
                                 hi[k] >= bounds[i][0][k]-1e-8 for k in range(3))
                             for i in reached)}
            if not added:
                break
            reached.update(added)
        self.assertEqual(len(reached), len(bounds),
                         [g.parts[i][0] for i in range(len(bounds)) if i not in reached])

    def test_positions_follow_translated_anisotropic_frame(self):
        original, f = specimen(), frame()
        other = dict(lo=[11, -90, 8], hi=[99, 12, 240])
        shifted = specimen(other)
        self.assertEqual(len(original.parts), len(shifted.parts))
        for a, b in zip(original.parts, shifted.parts):
            self.assertEqual(a[0:2], b[0:2])
            self.assertEqual(a[3], b[3])
            # Native loft chamfers are physical-size dependent. Centers and
            # envelopes, rather than chamfer offsets, must transform affinely.
            for i in range(3):
                for extremum in (min, max):
                    u = extremum(v[i] for v in a[2])
                    v = extremum(v[i] for v in b[2])
                    expected = other['lo'][i]+(u-f['lo'][i])/f['span'][i]*(other['hi'][i]-other['lo'][i])
                    self.assertAlmostEqual(expected, v)

    def test_invalid_input_emits_nothing_and_module_is_math_only(self):
        g, design = Geometry(), load()
        for kind, f in (('fortress', frame()), ('shipyard', dict(lo=[0,0,0], hi=[0,1,1])),
                        ('shipyard', dict(lo=[0,0,0], hi=[1,float('nan'),1]))):
            with self.assertRaises(ValueError):
                design.build(kind, g, f)
        self.assertEqual(g.parts, [])
        tree = ast.parse(SOURCE.read_text())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertTrue(all(isinstance(n, ast.Import) and
                            all(a.name == 'math' for a in n.names) for n in imports))


if __name__ == '__main__':
    unittest.main()
