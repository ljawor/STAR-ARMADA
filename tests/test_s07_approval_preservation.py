"""S07 may touch unrelated renderer methods, never silently re-approve B5 art."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE='e264230fd0eeb5522e86d5527d7fa7c2ff9eddbd2d2eba05a1ab0cccbef0d378'

def ast_signature(node):
    # Python 3.14 omits empty fields by default; canonicalize across CI versions.
    def project(value):
        if isinstance(value, ast.AST):
            return [type(value).__name__, {key:project(item) for key,item in ast.iter_fields(value)
                                          if item is not None and item != []}]
        if isinstance(value,list):
            return [project(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(project(node),sort_keys=True).encode()).hexdigest()

class ApprovalPreservation(unittest.TestCase):
    def test_renderer_pin_correction_retains_approved_bytes_and_asteroid_methods(self):
        approvals=json.loads((ROOT/'art/manifests/approvals.json').read_text())
        decision=next(d for d in approvals['decision_log'] if d['id']=='s06-b5-environment-2026-10-17')
        self.assertIn('s07_renderer_pin_correction',decision)
        correction=decision['s07_renderer_pin_correction']
        self.assertEqual(correction['previous_renderer_sha256'],BASE)
        self.assertEqual(correction['authority'],'s07-opt-in-continuation-2026-10-18')
        self.assertTrue(correction['appearance_approval_unchanged'])
        row=decision['revision']['assets'][0]
        before=correction['previous_runtime']
        self.assertEqual(before['render/renderer.py'],BASE)
        self.assertEqual({k:v for k,v in row['runtime'].items() if k!='render/renderer.py'},
                         {k:v for k,v in before.items() if k!='render/renderer.py'})
        self.assertEqual(row['source'],correction['previous_source'])
        self.assertEqual(row['exporter'],correction['previous_exporter'])
        for group in ('source','exporter','runtime'):
            for path,expected in row[group].items():
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected,path)
        tree=ast.parse((ROOT/'render/renderer.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Renderer')
        methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(set(correction['unchanged_method_ast_sha256']),
                         {'_draw_asteroid_field','_asteroid_prop_lists','_emit_detail_mesh'})
        for name,expected in correction['unchanged_method_ast_sha256'].items():
            actual=ast_signature(methods[name])
            self.assertEqual(actual,expected,name)

if __name__=='__main__': unittest.main()
