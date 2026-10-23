"""CPU-only hardware contract; geometry facade matches the Blender API exactly."""
import importlib.util
import inspect
import json
import math
from collections import Counter
from pathlib import Path
import unittest

from test_alliance_redesign_ship_designs import Geometry

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'tools/art/alliance_redesign_hardware_designs.py'
KINDS = ('defense_satellite', 'attack_satellite', 'planet_extractor',
         'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon')


def specimens():
    assert SOURCE.exists(), 'Dedicated hardware recipes must exist'
    spec = importlib.util.spec_from_file_location('hardware_designs', SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    coverage = json.loads((ROOT/'artifacts/alliance-redesign/coverage.json').read_text())
    rows = {r['binding'].split(':')[1]: r for r in coverage['rows']}
    result = []
    for kind in KINDS:
        lo, hi = rows[kind]['bounds']
        frame = dict(lo=lo, hi=hi, span=[b-a for a,b in zip(lo,hi)],
                     center=[(a+b)/2 for a,b in zip(lo,hi)])
        g = Geometry()
        module.build(kind, g, frame)
        result.append((kind,g,frame))
    return module,result


class HardwareTests(unittest.TestCase):
    def test_all_six_geometry_contracts(self):
        module, models = specimens()
        self.assertEqual(tuple(inspect.signature(module.build).parameters), ('kind','g','frame'))
        caps = json.loads((ROOT/'artifacts/alliance-redesign/triangle-budget-plan.json').read_text())['per_binding_alliance_allocations']
        for kind,g,frame in models:
            with self.subTest(kind=kind):
                triangles = sum(len(f)-2 for _,_,_,faces in g.parts for f in faces)
                self.assertGreater(triangles,1800)
                self.assertLessEqual(triangles,caps[kind])
                self.assertEqual({p[1] for p in g.parts},set(('base','dark','trim','accent','lit','cool')))
                self.assertEqual(len({p[0] for p in g.parts}),len(g.parts))
                vertices = [v for p in g.parts for v in p[2]]
                bounds = [[fn(v[i] for v in vertices) for i in range(3)] for fn in (min,max)]
                for i in range(3):
                    self.assertGreaterEqual(bounds[0][i],frame['lo'][i])
                    self.assertLessEqual(bounds[1][i],frame['hi'][i])
                    self.assertAlmostEqual((bounds[1][i]-bounds[0][i])/frame['span'][i],.998,places=6)
                    self.assertAlmostEqual(sum(b[i] for b in bounds)/2,frame['center'][i],places=6)
                for name,role,vs,faces in g.parts:
                    self.assertTrue(all(math.isfinite(c) for v in vs for c in v),name)
                    edges = Counter()
                    for face in faces:
                        for a,b in zip(face,face[1:]+face[:1]):
                            edges[tuple(sorted((a,b)))] += 1
                        for j in range(1,len(face)-1):
                            a,b,c = (vs[k] for k in (face[0],face[j],face[j+1]))
                            u = [b[i]-a[i] for i in range(3)]
                            v = [c[i]-a[i] for i in range(3)]
                            cross = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                            self.assertGreater(sum(x*x for x in cross),1e-16,name)
                    self.assertEqual(set(edges.values()),{2},name)
                    # Every high-vertex primitive is an annular tube, not a
                    # capped cylinder masquerading as an open energy collar.
                    if len(vs) > 16:
                        self.assertEqual(len(vs)-len(edges)+len(faces),0,name)
                print(kind,triangles,'triangles',len(g.parts),'parts; bounds',bounds)

    def test_parts_connected_and_functional_landmarks_distinct(self):
        _,models = specimens()
        words = dict(defense_satellite=('shield','interceptor'), attack_satellite=('spine','barrel'),
                     planet_extractor=('drill','ore'), planet_trade_hub=('crane','apron'),
                     planet_shield_generator=('coil','pylon'), planet_pulsar_cannon=('barrel','breech'))
        for kind,g,_ in models:
            names = ' '.join(p[0] for p in g.parts)
            for word in words[kind]:
                self.assertIn(word,names)
            bounds = [[(min(v[i] for v in p[2]),max(v[i] for v in p[2])) for i in range(3)] for p in g.parts]
            connected = {0}
            while True:
                added = {j for j,b in enumerate(bounds) if j not in connected and any(
                    all(b[k][0] <= bounds[i][k][1]+1e-6 and bounds[i][k][0] <= b[k][1]+1e-6 for k in range(3)) for i in connected)}
                if not added:
                    break
                connected.update(added)
            self.assertEqual(len(connected),len(g.parts),(kind,[g.parts[i][0] for i in range(len(g.parts)) if i not in connected]))

    def test_body_budget_is_functional_panels_not_service_repeats(self):
        _,models = specimens()
        features = {
            'defense_satellite': ('segmented pressure armor','stepped shoulder armor','targeting module'),
            'attack_satellite': ('segmented pressure armor','broad flank vent','targeting module'),
            'planet_extractor': ('ore sorter pressure armor','compressor pump','ore hopper'),
            'planet_trade_hub': ('customs stepped armor','crane diagonal truss','drive motor','loading door'),
            'planet_shield_generator': ('shield base conduit','capacitor vent bank','pylon pressure armor'),
            'planet_pulsar_cannon': ('breech bolted armor','pedestal stepped armor','targeting module'),
        }
        for kind,g,frame in models:
            with self.subTest(kind=kind):
                self.assertEqual(sum('service cassette' in p[0] for p in g.parts),6)
                self.assertLessEqual(sum(len(f)-2 for n,_,_,fs in g.parts
                                         if 'cassette' in n or 'cooler rib' in n
                                         for f in fs),456)
                for feature in features[kind]:
                    parts = [p for p in g.parts if feature in p[0]]
                    self.assertTrue(parts,feature)
                    # A functional body detail must span a substantial axis;
                    # renamed tiny greebles cannot satisfy the feature contract.
                    self.assertTrue(any(max((max(v[i] for v in p[2])-min(v[i] for v in p[2]))
                                            /frame['span'][i] for i in range(3)) > .09
                                        for p in parts),feature)
                armor = [p for p in g.parts if any(w in p[0] for w in ('pressure armor','stepped armor','bolted armor'))]
                self.assertTrue(armor)
                self.assertTrue(all(len(p[2]) == 16 for p in armor))

    def test_unknown_kind_rejected_before_emission(self):
        module,models = specimens()
        g = Geometry()
        with self.assertRaises(ValueError):
            module.build('shipyard',g,models[0][2])
        self.assertFalse(g.parts)

    def test_service_highlights_have_unobstructed_upward_sightlines(self):
        _,models = specimens()
        for kind,g,_ in models:
            triangles = [(name,vs[f[0]],vs[f[j]],vs[f[j+1]])
                         for name,role,vs,faces in g.parts if role not in ('lit','cool')
                         for f in faces for j in range(1,len(f)-1)]
            for name,role,vs,_ in g.parts:
                if 'task beacon' not in name and 'coolant indicator' not in name:
                    continue
                px = sum(v[0] for v in vs)/len(vs)
                pz = sum(v[2] for v in vs)/len(vs)
                py = max(v[1] for v in vs)
                for obstacle,a,b,c in triangles:
                    den = (b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
                    if abs(den) < 1e-10:
                        continue
                    u = ((b[2]-c[2])*(px-c[0])+(c[0]-b[0])*(pz-c[2]))/den
                    v = ((c[2]-a[2])*(px-c[0])+(a[0]-c[0])*(pz-c[2]))/den
                    w = 1-u-v
                    if min(u,v,w) >= -1e-8:
                        self.assertLessEqual(u*a[1]+v*b[1]+w*c[1],py+1e-6,(kind,name,obstacle))


if __name__ == '__main__':
    unittest.main()
