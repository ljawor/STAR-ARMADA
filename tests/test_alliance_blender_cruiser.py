"""Focused contracts for the pending, blend-authoritative Liberty specimen."""
import ast
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MESH = ROOT / 'assets/models/alliance_cruiser.mesh.json'


class ReviewMetadata(unittest.TestCase):
    def test_recipe_declares_actual_empty_commands_and_selection(self):
        import importlib.util
        from types import SimpleNamespace
        from unittest.mock import Mock
        spec=importlib.util.spec_from_file_location('cruiser_review',ROOT/'tools/diag_alliance_cruiser_review.py')
        review=importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
        inherited=dict(command_schedule='inherited attack schedule',selection=[42],seed=12345)
        gm=object(); ids={'capital':42}
        helper=SimpleNamespace(build_scene=Mock(return_value=(gm,ids,inherited)),issue=Mock())
        self.assertTrue(callable(getattr(review,'build_review_scene',None)), 'review needs an explicit truthful scene recipe')
        actual_gm,actual_ids,recipe=review.build_review_scene(helper)
        self.assertIs(actual_gm,gm); self.assertIs(actual_ids,ids)
        self.assertEqual(recipe['command_schedule'],[])
        self.assertEqual(recipe['selection'],[])
        self.assertEqual(recipe['seed'],12345)
        helper.issue.assert_not_called()
        self.assertEqual(inherited['selection'],[42], 'do not mutate shared helper recipe')
        tree=ast.parse((ROOT/'tools/diag_alliance_cruiser_review.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(n.func,ast.Attribute) and n.func.attr=='issue' for n in calls))
        selections=[n.args[1 if n.func.attr=='draw' else 0] for n in calls
                    if isinstance(n.func,ast.Attribute) and n.func.attr in ('draw','render')
                    and isinstance(n.func.value,ast.Name) and n.func.value.id in ('renderer','hud')]
        self.assertEqual(len(selections),2)
        self.assertTrue(all(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='set' and not n.args for n in selections))
        self.assertFalse(any(isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
                             and n.func.value.id=='helper' and n.func.attr=='build_scene'
                             for n in calls if getattr(n,'lineno',0)>40))


class ExportSafety(unittest.TestCase):
    def assert_master_refused(self, alias):
        import importlib.util
        import sys
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); master=root/'master.blend'; master.write_bytes(b'protected master')
            output=master
            if alias=='relative':
                (root/'child').mkdir(); output=root/'child/../master.blend'
            elif alias=='symlink':
                output=root/'alias.blend'; output.symlink_to(master)
            elif alias=='hardlink':
                import os
                output=root/'alias.blend'; os.link(master,output)
            opened=Mock(side_effect=RuntimeError('master opened before refusal'))
            stub=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(open_mainfile=opened)))
            spec=importlib.util.spec_from_file_location('cruiser_export',ROOT/'tools/art/export_alliance_cruiser.py')
            exporter=importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules,{'bpy':stub}), patch.object(sys,'argv',['exporter','--','--blend',str(master),'--output',str(output)]):
                spec.loader.exec_module(exporter)
                with self.assertRaisesRegex(ValueError,'master|source|input'):
                    exporter.main()
            opened.assert_not_called()
            self.assertEqual(master.read_bytes(),b'protected master')
            self.assertEqual(output.read_bytes(),b'protected master')

    def test_export_refuses_master_before_open(self):
        self.assert_master_refused('same')

    def test_export_refuses_relative_master_alias_before_open(self):
        self.assert_master_refused('relative')

    def test_export_refuses_symlink_master_alias_before_open(self):
        self.assert_master_refused('symlink')

    def test_export_refuses_hardlink_master_alias_before_open(self):
        self.assert_master_refused('hardlink')


class LibertyGeometry(unittest.TestCase):
    def test_evaluated_mesh_contract(self):
        self.assertTrue(MESH.is_file(), 'Liberty evaluated export has not been authored')
        from render.authored_mesh import _load_profile
        mesh = _load_profile(MESH, 'alliance_cruiser', ((-66,66),(-11.265,19.3),(-99.925,97.5)),197.4)
        a = json.loads(MESH.read_text())
        self.assertEqual(set(mesh), {'base','dark','trim','accent','lit','cool'})
        self.assertLessEqual(a['triangle_count'], 7800)
        self.assertLessEqual(len(a['vertices']),9500)
        self.assertLess(MESH.stat().st_size,2_000_000)
        self.assertEqual(a['bounds'][0][2],-99.925)
        self.assertEqual(a['bounds'][1][2],97.5)
        for feature in ('bridge','keel','machinery','vent','armor','window','emitter','recognition'):
            self.assertTrue(any(feature in p['name'].lower() for p in a['parts']),feature)
        self.assertEqual(sum(p['triangles'] for p in a['parts']),a['triangle_count'])
        self.assertEqual(a['features']['authority'],'blend')
        self.assertEqual(a['features']['approval'],'pending_owner_approval')

    def test_source_is_blend_authoritative_and_export_only(self):
        exporter=(ROOT/'tools/art/export_alliance_cruiser.py').read_text()
        tree=ast.parse(exporter)
        self.assertIn('open_mainfile',exporter)
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr in ('save_as_mainfile','save_mainfile') for n in ast.walk(tree)))
        self.assertTrue((ROOT/'art/blender/alliance_cruiser.blend').is_file())

    def assert_emitter_centers_match_export(self, asset):
        centers=asset['features']['emitter_centers']
        self.assertEqual(len(centers),4, 'exactly four engine centers required')
        self.assertEqual(len({tuple(c) for c in centers}),4)
        offsets={role:0 for role in asset['batches']}; emitters=[]
        for part in asset['parts']:
            role=part['role']; start=offsets[role]; end=start+part['triangles']; offsets[role]=end
            if 'Recessed cyan emitter' not in part['name']:continue
            self.assertEqual(role,'cool')
            self.assertGreater(part['triangles'],0)
            triangles=asset['batches'][role][start:end]
            self.assertEqual(len(triangles),part['triangles'])
            points=[asset['vertices'][i] for tri in triangles for i in tri[3:]]
            lo=[min(p[i] for p in points) for i in range(3)]
            hi=[max(p[i] for p in points) for i in range(3)]
            emitters.append([(a+b)/2 for a,b in zip(lo,hi)])
        self.assertEqual(len(emitters),4, 'exactly four exported emitter parts required')
        for declared,actual in zip(sorted(centers),sorted(emitters)):
            for a,b in zip(declared,actual):self.assertAlmostEqual(a,b,places=5)

    def test_four_engine_centers_correspond_to_exported_emitter_geometry(self):
        self.assert_emitter_centers_match_export(json.loads(MESH.read_text()))

    def test_emitter_contract_rejects_vacuous_or_unlinked_metadata(self):
        import copy
        asset=json.loads(MESH.read_text())
        for defect in ('empty','duplicate','moved','missing_part','empty_geometry'):
            bad=copy.deepcopy(asset)
            if defect=='empty':bad['features']['emitter_centers']=[]
            if defect=='duplicate':bad['features']['emitter_centers'][0]=bad['features']['emitter_centers'][1]
            if defect=='moved':bad['features']['emitter_centers'][0][0]+=10
            emitter=next(p for p in bad['parts'] if 'Recessed cyan emitter' in p['name'])
            if defect=='missing_part':bad['parts'].remove(emitter)
            if defect=='empty_geometry':emitter['triangles']=0
            with self.subTest(defect=defect),self.assertRaises(AssertionError):
                self.assert_emitter_centers_match_export(bad)

    def test_each_recessed_emitter_has_five_clear_aft_rays(self):
        import numpy as np
        from render.authored_mesh import _load_profile
        mesh=_load_profile(MESH,'alliance_cruiser',((-66,66),(-11.265,19.3),(-99.925,97.5)),197.4)
        triangles=np.array([tri for role in ('base','dark','trim','accent') for _,tri in mesh[role]])
        a=triangles[:,0]; e1=triangles[:,1]-a; e2=triangles[:,2]-a
        direction=np.array([0.,0.,-1.]); p=np.cross(direction,e2); det=np.einsum('ij,ij->i',e1,p)
        inv=np.divide(1.,det,out=np.zeros_like(det),where=abs(det)>1e-9)
        def obstructed(origin):
            t=np.array(origin)-a; u=np.einsum('ij,ij->i',t,p)*inv
            q=np.cross(t,e1); v=np.einsum('j,ij->i',direction,q)*inv
            distance=np.einsum('ij,ij->i',e2,q)*inv
            return bool(np.any((abs(det)>1e-9)&(u>=0)&(v>=0)&(u+v<=1)&(distance>1e-5)))
        asset=json.loads(MESH.read_text())
        self.assert_emitter_centers_match_export(asset)
        for x,y,z in asset['features']['emitter_centers']:
            for dx,dy in ((0,0),(-1.5,0),(1.5,0),(0,-1.5),(0,1.5)):
                self.assertFalse(obstructed((x+dx,y+dy,z-.13)),(x,dx,dy))
            # Discriminating buried control: aft pressure casing lies in front.
            self.assertTrue(obstructed((x,y,-88.)),x)

    def test_corruption_is_rejected_by_production_loader(self):
        import copy
        import tempfile
        from render.authored_mesh import _load_profile
        original=json.loads(MESH.read_text())
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/s06_alliance_cruiser_review') as tmp:
            for defect in ('normal','index','winding','bounds','count'):
                data=copy.deepcopy(original)
                if defect=='normal':data['batches']['base'][0][0]=9
                if defect=='index':data['batches']['base'][0][3]=999999
                if defect=='winding':data['batches']['base'][0][3:]=list(reversed(data['batches']['base'][0][3:]))
                if defect=='bounds':data['vertices'][0][0]=66.1
                if defect=='count':data['triangle_count']+=1
                target=Path(tmp)/'bad.mesh.json'; target.write_text(json.dumps(data))
                with self.subTest(defect=defect),self.assertRaises(ValueError):
                    _load_profile(target,'alliance_cruiser',((-66,66),(-11.265,19.3),(-99.925,97.5)),197.4)


if __name__ == '__main__':
    unittest.main()
