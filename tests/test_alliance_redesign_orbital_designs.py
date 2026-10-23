"""CPU geometry contract tests; use the real facade's pure mesh constructors."""
import ast
import collections
import importlib.util
import json
import math
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('command_station', 'mining_station', 'research_station', 'defense_platform',
         'sensor_station', 'trade_station', 'fighter_platform', 'repair_dock', 'energy_relay')
SIGNATURES = ('inhabited tier', 'ore crusher', 'laboratory', 'gun arm', 'sensor dish',
              'transfer gantry', 'launch bay', 'open cradle', 'power stack')


class Geometry:
    def __init__(self):
        self.parts = []
        source = ast.parse((ROOT/'tools/art/alliance_redesign_geometry.py').read_text())
        funcs: list[ast.stmt] = [n for n in source.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('box', 'loft', 'ring', 'disc')]
        ns = {'math': math, 'mesh': self.mesh}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), '<real facade>', 'exec'), ns)
        for name in ('box', 'loft', 'ring', 'disc'):
            setattr(self, name, ns[name])

    def mesh(self, name, role, verts, faces, bevel=0):
        assert bevel == 0, 'CPU triangle counts must equal exported counts'
        self.parts.append((name, role, list(verts), list(faces)))


def load_design():
    path = ROOT/'tools/art/alliance_redesign_orbital_designs.py'
    assert path.exists(), 'Orbital design implementation is missing'
    spec = importlib.util.spec_from_file_location('orbital_designs', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def specimens():
    module = load_design()
    rows = json.loads((ROOT/'artifacts/alliance-redesign/coverage.json').read_text())['rows']
    for row in rows:
        kind = row['binding'].split(':')[1]
        if kind not in KINDS:
            continue
        lo, hi = row['bounds']
        frame = dict(lo=lo, hi=hi, span=[b-a for a,b in zip(lo,hi)],
                     center=[(a+b)/2 for a,b in zip(lo,hi)])
        g = Geometry()
        module.build(kind, g, frame)
        yield kind, frame, g


class OrbitalDesignTests(unittest.TestCase):
    def test_all_orbital_contracts(self):
        caps = json.loads((ROOT/'artifacts/alliance-redesign/triangle-budget-plan.json').read_text())['per_binding_alliance_allocations']
        built = list(specimens())
        self.assertEqual(set(KINDS), {k for k, _, _ in built})
        fingerprints = set()
        for kind, frame, g in built:
            with self.subTest(kind=kind):
                verts = [v for _, _, vv, _ in g.parts for v in vv]
                triangles = sum(len(f)-2 for _, _, _, ff in g.parts for f in ff)
                self.assertGreater(triangles, 1800)
                self.assertLessEqual(triangles, caps[kind])
                self.assertLessEqual(len(verts), 9500)
                self.assertEqual({r for _,r,_,_ in g.parts}, {'base','dark','trim','accent','lit','cool'})
                self.assertEqual(len({n for n,_,_,_ in g.parts}), len(g.parts))
                self.assertTrue(any(SIGNATURES[KINDS.index(kind)] in n for n,_,_,_ in g.parts))
                for axis in range(3):
                    low, high = min(v[axis] for v in verts), max(v[axis] for v in verts)
                    self.assertGreaterEqual(low, frame['lo'][axis])
                    self.assertLessEqual(high, frame['hi'][axis])
                    self.assertAlmostEqual((high-low)/frame['span'][axis], .999, places=6)
                fingerprint = tuple(sorted((r,len(v),len(f)) for _,r,v,f in g.parts))
                self.assertNotIn(fingerprint, fingerprints)
                fingerprints.add(fingerprint)
                for name, _, vv, ff in g.parts:
                    edges = collections.Counter()
                    for face in ff:
                        self.assertGreaterEqual(len(face), 3, name)
                        for a,b in zip(face, face[1:]+face[:1]):
                            edges[tuple(sorted((a,b)))] += 1
                        for j in range(1,len(face)-1):
                            a,b,c = (vv[face[q]] for q in (0,j,j+1))
                            u,v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
                            cross = [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                            self.assertGreater(sum(c*c for c in cross), 1e-16, name)
                    self.assertEqual(set(edges.values()), {2}, name)
                print(f'{kind}: triangles={triangles} vertices={len(verts)} parts={len(g.parts)}')

    def test_attached_parts_and_open_working_clearances(self):
        for kind, frame, g in specimens():
            with self.subTest(kind=kind):
                bounds = [([min(v[i] for v in vv) for i in range(3)],
                           [max(v[i] for v in vv) for i in range(3)])
                          for _,_,vv,_ in g.parts]
                # Necessary attachment condition. Closed-part topology is tested
                # above; this guards obvious disconnected masts and equipment.
                reached = {0}
                while True:
                    additions = {j for j,(lo,hi) in enumerate(bounds) if j not in reached
                                 and any(all(lo[i] <= bounds[k][1][i]+1e-7 and
                                             hi[i] >= bounds[k][0][i]-1e-7 for i in range(3))
                                         for k in reached)}
                    if not additions:
                        break
                    reached.update(additions)
                self.assertEqual(len(reached), len(bounds),
                                 [g.parts[j][0] for j in range(len(bounds)) if j not in reached])
                samples = []
                if kind == 'fighter_platform':
                    samples = [(x,y,z) for x in (-.30,.30) for y in (-.20,0,.15)
                               for z in (-.40,0,.40)]
                elif kind == 'repair_dock':
                    samples = [(x,y,z) for x in (-.20,0,.20) for y in (-.10,.10,.30)
                               for z in (-.20,.10,.40)]
                for sample in samples:
                    p = [frame['center'][i]+sample[i]*frame['span'][i]*.999 for i in range(3)]
                    self.assertFalse(any(all(lo[i] < p[i] < hi[i] for i in range(3))
                                         for lo,hi in bounds), (kind,sample,'filled clearance'))

    def test_functional_architecture_has_visible_scale(self):
        # A window grid cannot satisfy this: require raised machinery/armor with
        # useful footprint and height, as well as a genuinely changing hull section.
        features = {
            'command_station': ('command terrace armor', 'command cooling plant', 'command service bridge', 'command logistics bay'),
            'mining_station': ('ore separator', 'ore conveyor drive'),
            'research_station': ('laboratory sample lock', 'laboratory thermal hood'),
            'defense_platform': ('fire control armored director', 'gun arm ammunition'),
            'sensor_station': ('sensor receiver cabinet', 'sensor waveguide'),
            'trade_station': ('customs inspection lock', 'transfer gantry drive'),
            'fighter_platform': ('launch bay ventilation', 'flight control roof armor'),
            'repair_dock': ('repair dock machine shop', 'open cradle travel drive'),
            'energy_relay': ('power stack switchgear', 'power stack bus cover'),
        }
        for kind, frame, g in specimens():
            with self.subTest(kind=kind):
                for prefix in features[kind]:
                    selected = [vv for n, _, vv, _ in g.parts if n.startswith(prefix)]
                    self.assertTrue(selected, (kind, prefix))
                    dimensions = [[(max(v[i] for v in vv)-min(v[i] for v in vv)) /
                                   (frame['span'][i]*.999) for i in range(3)] for vv in selected]
                    self.assertTrue(any(d[0] >= .065 and d[1] >= .025 and d[2] >= .06
                                        for d in dimensions), (kind, prefix, 'only tiny surface noise'))
                shaped = []
                for _, _, vv, _ in g.parts:
                    if len(vv) < 24 or len(vv) % 8:
                        continue
                    sections = [vv[j:j+8] for j in range(0,len(vv),8)]
                    if all(len({round(v[2],7) for v in section}) == 1 for section in sections):
                        widths = [max(v[0] for v in s)-min(v[0] for v in s) for s in sections]
                        if max(widths)-min(widths) > frame['span'][0]*.025:
                            shaped.append(vv)
                self.assertTrue(shaped, (kind, 'uniform slab bodies'))

    def test_rejects_invalid_requests(self):
        module = load_design()
        with self.assertRaises(ValueError):
            module.build('shipyard', Geometry(), {})
        for bounds in (([0,0,0],[1,0,1]), ([0,0,0],[1,float('nan'),1])):
            with self.assertRaises(ValueError):
                module.build('command_station', Geometry(), dict(zip(('lo','hi'),bounds)))


if __name__ == '__main__':
    unittest.main()
