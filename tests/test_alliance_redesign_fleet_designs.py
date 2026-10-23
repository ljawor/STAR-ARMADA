"""CPU geometry contract tests; never import Blender or the export driver."""
import importlib.util
import ast
import json
import math
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('fleet_designs', ROOT/'tools/art/alliance_redesign_fleet_designs.py')
assert SPEC is not None and SPEC.loader is not None
fleet=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fleet)
ROLES={'base','dark','trim','accent','lit','cool'}
COVERAGE=json.loads((ROOT/'artifacts/alliance-redesign/coverage.json').read_text())
BUDGET=json.loads((ROOT/'artifacts/alliance-redesign/triangle-budget-plan.json').read_text())
ROWS={r['binding'].split(':')[1]:r for r in COVERAGE['rows'] if r['group']=='ship_or_logistics'}
SIGNATURES={'fighter':'fighter twinboom','bomber':'heavy torpedo magazine',
            'corvette':'blockade runner engine transom','cruiser':'liberty broad shoulder',
            'battleship':'command cruiser armor bank','supercapital':'empty sidehangar',
            'constructor':'engineering crane armature','colonizer':'colony habitat pressure module',
            'convoy':'convoy cargo module'}


class FakeGeometry:
    def __init__(self):
        self.parts=[]

    def mesh(self,name,role,verts,faces,bevel=0):
        assert bevel==0, 'CPU count must not miss evaluated bevel geometry'
        assert role in ROLES
        assert verts and faces
        assert all(len(f)>=3 and all(0<=i<len(verts) for i in f) for f in faces)
        assert all(all(math.isfinite(c) for c in p) for p in verts)
        self.parts.append({'name':name,'role':role,'verts':verts,'faces':faces,
                           'triangles':sum(len(f)-2 for f in faces),
                           'bounds':[[fn(p[i] for p in verts) for i in range(3)] for fn in (min,max)]})


def frame_for(kind):
    lo,hi=ROWS[kind]['bounds']
    return {'lo':lo,'hi':hi,'span':[hi[i]-lo[i] for i in range(3)],
            'center':[(hi[i]+lo[i])/2 for i in range(3)]}


def make(kind):
    g=FakeGeometry(); fleet.build(kind,g,frame_for(kind)); return g


def report(kind,g):
    return {'kind':kind,'triangles':sum(p['triangles'] for p in g.parts),
            'roles':{r:sum(p['triangles'] for p in g.parts if p['role']==r) for r in sorted(ROLES)},
            'bounds':[[fn(p['bounds'][j][i] for p in g.parts) for i in range(3)]
                      for j,fn in enumerate((min,max))], 'parts':len(g.parts)}


class FleetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models={kind:make(kind) for kind in fleet.KINDS}

    def test_manifest_coverage_exactly_nine(self):
        self.assertEqual(len(ROWS),10)
        self.assertEqual(set(fleet.KINDS),set(ROWS)-{'frigate'})
        self.assertEqual(len(fleet.KINDS),9)

    def test_budgets_materials_and_native_envelopes(self):
        for kind,g in self.models.items():
            with self.subTest(kind=kind):
                result=report(kind,g)
                self.assertGreater(result['triangles'],1800)
                self.assertLessEqual(result['triangles'],BUDGET['per_binding_alliance_allocations'][kind])
                self.assertEqual({p['role'] for p in g.parts},ROLES)
                lo,hi=ROWS[kind]['bounds']
                for axis in range(3):
                    a,b=result['bounds'][0][axis],result['bounds'][1][axis]
                    self.assertGreaterEqual(a,lo[axis])
                    self.assertLessEqual(b,hi[axis])
                    self.assertLess(abs((b-a)/(hi[axis]-lo[axis])-1),.01)
                self.assertEqual(len({p['name'] for p in g.parts}),len(g.parts))

    def test_all_parts_have_connected_host_bounding_boxes(self):
        # Necessary contact condition (not a claim of a full solid intersection test).
        for kind,g in self.models.items():
            with self.subTest(kind=kind):
                seen={0}; remaining=set(range(1,len(g.parts)))
                while remaining:
                    added=set()
                    for i in remaining:
                        a=g.parts[i]['bounds']
                        if any(all(a[0][k]<=g.parts[j]['bounds'][1][k]+1e-8 and
                                   a[1][k]>=g.parts[j]['bounds'][0][k]-1e-8 for k in range(3)) for j in seen):
                            added.add(i)
                    if not added: break
                    seen.update(added); remaining-=added
                self.assertFalse(remaining,[g.parts[i]['name'] for i in remaining])

    def test_signature_parts_and_distinct_structural_silhouettes(self):
        signatures=[]
        for kind,g in self.models.items():
            self.assertTrue(any(SIGNATURES[kind] in p['name'] for p in g.parts),kind)
            frame=frame_for(kind)
            # Top/side occupancy grid of structural geometry, excluding equipment.
            cells=set()
            for p in g.parts:
                if p['role']!='base': continue
                for v in p['verts']:
                    q=tuple(round((v[i]-frame['center'][i])/frame['span'][i]*20) for i in range(3))
                    cells.add(q)
            signatures.append(frozenset(cells))
        self.assertEqual(len(set(signatures)),9)
        self.assertEqual(sum('fighter twinboom' in p['name'] for p in self.models['fighter'].parts),2)
        self.assertEqual(sum('open exhaust throat' in p['name'] for p in self.models['corvette'].parts),5)

    def test_hangars_remain_visibly_empty(self):
        g=self.models['supercapital']; f=frame_for('supercapital')
        # Side-facing view rays through each hangar: no opaque object may cover
        # the aperture center, between inner wall and exterior mouth.
        for side in (-1,1):
            x0,x1=sorted((side*.31,side*.99))
            for z in (-.4,0,.4):
                for p in g.parts:
                    if p['role'] in ('cool','lit'): continue
                    vv=[[(v[i]-f['center'][i])/(f['span'][i]*.4995)
                         for i in range(3)] for v in p['verts']]
                    for face in p['faces']:
                        for j in range(1,len(face)-1):
                            a,b,c=(vv[k] for k in (face[0],face[j],face[j+1]))
                            # Barycentric intersection in the YZ projection.
                            det=(b[2]-c[2])*(a[1]-c[1])+(c[1]-b[1])*(a[2]-c[2])
                            if abs(det)<1e-12: continue
                            u=((b[2]-c[2])*(-.1-c[1])+(c[1]-b[1])*(z-c[2]))/det
                            v=((c[2]-a[2])*(-.1-c[1])+(a[1]-c[1])*(z-c[2]))/det
                            if min(u,v,1-u-v)<-1e-9: continue
                            x=u*a[0]+v*b[0]+(1-u-v)*c[0]
                            self.assertFalse(x0<x<x1,p['name'])

    def test_open_nozzle_topology_and_emitter_visibility(self):
        for kind,g in self.models.items():
            f=frame_for(kind)
            for throat in (p for p in g.parts if p['name'].startswith('open exhaust throat')):
                self.assertTrue(all(len(face)==4 for face in throat['faces']))
                index=throat['name'].split()[-1]
                emitter=next(p for p in g.parts if p['name']=='visible recessed drive emitter '+index)
                machinery=next(p for p in g.parts if p['name']=='drive machinery '+index)
                self.assertLess(throat['bounds'][0][2],emitter['bounds'][0][2])
                self.assertLess(emitter['bounds'][1][2],machinery['bounds'][0][2])
                self.assertEqual(emitter['role'],'cool')
                # Bore caps would produce n-gons; all ring end faces are annular quads.
                self.assertEqual(len(throat['faces']),72)

    def test_deterministic_and_no_degenerate_triangles(self):
        for kind,g in self.models.items():
            self.assertEqual(g.parts,make(kind).parts)
            for p in g.parts:
                for face in p['faces']:
                    # All faces convex; fan area is an independent nonzero check.
                    a=p['verts'][face[0]]
                    for j in range(1,len(face)-1):
                        b=p['verts'][face[j]]; c=p['verts'][face[j+1]]
                        u=[b[k]-a[k] for k in range(3)]; v=[c[k]-a[k] for k in range(3)]
                        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                        self.assertGreater(sum(q*q for q in cross),1e-18,(kind,p['name']))

    def test_broad_functional_panels_cover_capital_decks(self):
        for kind,minimum in (('cruiser',8),('battleship',12),('supercapital',16)):
            f=frame_for(kind)
            panels=[p for p in self.models[kind].parts if 'broad functional panel' in p['name']]
            self.assertGreaterEqual(len(panels),minimum,kind)
            area=0
            for p in panels:
                extent=[(p['bounds'][1][i]-p['bounds'][0][i])/(f['span'][i]*.4995)
                        for i in range(3)]
                self.assertGreater(extent[0],.19,p['name'])
                self.assertGreater(extent[1],.09,p['name'])
                self.assertGreater(extent[2],.16,p['name'])
                self.assertGreaterEqual(len(p['verts']),32,p['name'])
                area+=extent[0]*extent[2]
            self.assertGreater(area,{'cruiser':.49,'battleship':.65,'supercapital':1.1}[kind])

    def test_large_hulls_have_exposed_functional_assemblies(self):
        for kind,prefixes in {
            'cruiser':('liberty flank','liberty raised gun platform','liberty forecastle'),
            'battleship':('command flank machinery','command gun platform tier','command forward armor'),
            'supercapital':('carrier gantry','carrier aft service plant','carrier service alley machinery'),
        }.items():
            for prefix in prefixes:
                self.assertTrue(any(p['name'].startswith(prefix) for p in self.models[kind].parts),prefix)
        # Side radiators must project out of the narrowed armor bank, not hide inside it.
        for kind,prefix in (('cruiser','liberty flank'),('battleship','command flank machinery')):
            f=frame_for(kind)
            for p in self.models[kind].parts:
                if p['name'].startswith(prefix) and 'radiator rib' in p['name']:
                    xs=[abs((v[0]-f['center'][0])/(f['span'][0]*.4995)) for v in p['verts']]
                    self.assertGreater(min(xs),.96,p['name'])
        # Roof work cannot intrude into the hangar interior, even off sampled rays.
        f=frame_for('supercapital')
        for p in self.models['supercapital'].parts:
            if p['name'].startswith(('carrier roof armor','carrier gantry','carrier aft service plant',
                                     'carrier service alley machinery')):
                self.assertGreaterEqual((p['bounds'][0][1]-f['center'][1])/(f['span'][1]*.4995),.389)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):fleet.build('frigate',FakeGeometry(),frame_for('fighter'))

    def test_future_aggregate_ceiling_and_cpu_only_imports(self):
        allocation=dict(BUDGET['per_binding_alliance_allocations'])
        allocation.update({k:report(k,g)['triangles'] for k,g in self.models.items()})
        self.assertLessEqual(sum(allocation.values())+BUDGET['current_accepted_imperium_triangles'],
                             BUDGET['global_ceiling_unchanged'])
        tree=ast.parse((ROOT/'tools/art/alliance_redesign_fleet_designs.py').read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
            if isinstance(node,ast.ImportFrom):imports.append(node.module)
        self.assertEqual(imports,['math'])


if __name__=='__main__':
    import sys
    if '--report' in sys.argv:
        print(json.dumps([report(k,make(k)) for k in fleet.KINDS],indent=2))
    else:
        unittest.main()
