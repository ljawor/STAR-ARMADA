"""CPU-only measurement contracts for the real-driver S05 harness."""
import importlib.util
from pathlib import Path
import unittest
import json
import argparse
import os
import subprocess
import tempfile
from unittest.mock import patch


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.module = harness()
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'S05 Test')
        self.git('config', 'user.email', 's05@example.invalid')
        self.manifest = self.repo / 'art/manifests/approved-trio-source-hashes.json'
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({'assets/models/sample.json': 'sealed'}))
        asset = self.repo/'assets/models/sample.json'
        asset.parent.mkdir(parents=True)
        asset.write_text('{}')
        self.payload = self.repo / 'payload.txt'
        self.payload.write_text('control')
        self.control = self.commit('control')
        self.payload.write_text('candidate')
        self.candidate = self.commit('candidate')
        self.payload.write_text('later harness commit')
        self.head = self.commit('later')
        self.module.CONTROL, self.module.CANDIDATE = self.control, self.candidate

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True).strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def test_orchestrator_uses_sealed_pins_and_forwards_scratch_without_gl(self):
        m = self.module
        self.manifest.write_text('{"assets/models/sample.json": "dirty-live"}')
        output = self.base/'selected-scratch/run'
        args = argparse.Namespace(output=output, scratch_root=output.parent, user_root=[self.repo])
        real_run = subprocess.run
        launched = []

        def run(command, **kwargs):
            if len(command) > 2 and command[2] == 'capture':
                launched.append(command)
                raise RuntimeError('CPU test stops before GL capture')
            return real_run(command, **kwargs)

        with patch.object(m, '__file__', str(self.repo/'tools/harness.py')), \
             patch.object(m.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'CPU test stops'):
                m.orchestrate(args)
        receipt = json.loads((output/'source-receipts.json').read_text())
        self.assertEqual(receipt['approved_pins'], {'assets/models/sample.json': 'sealed'})
        self.assertTrue(json.loads((output/'user-preservation.json').read_text())['equal'])
        self.assertEqual(len(launched), 1)
        self.assertIn('--scratch-root', launched[0])
        index = launched[0].index('--scratch-root')
        self.assertEqual(Path(launched[0][index+1]), output.parent)

    def test_manifest_pins_come_from_sealed_candidate_not_live_checkout(self):
        self.assertTrue(callable(getattr(self.module, 'approved_pins', None)),
                        'sealed candidate manifest helper is missing')
        self.manifest.write_text(json.dumps({'assets/models/sample.json': 'unapproved-live-edit'}))
        receipts = self.module.archive_sources(self.repo, self.base / 'sources')
        self.assertEqual(self.module.approved_pins(receipts),
                         {'assets/models/sample.json': 'sealed'})

    def test_missing_pinned_revision_fails_before_any_archive(self):
        self.module.CANDIDATE = '0' * 40
        output = self.base / 'sources'
        with self.assertRaisesRegex(RuntimeError, 'missing pinned candidate revision '+ '0' * 40):
            self.module.archive_sources(self.repo, output)
        self.assertFalse(output.exists())

    def test_archives_pinned_objects_when_head_is_later_and_tree_is_dirty(self):
        self.assertTrue(callable(getattr(self.module, 'archive_sources', None)),
                        'immutable archive preflight helper is missing')
        self.payload.write_text('dirty owner work')
        output = self.base / 'sources'
        receipts = self.module.archive_sources(self.repo, output)
        self.assertNotEqual(self.head, self.candidate)
        for variant, revision, content in [('control', self.control, 'control'),
                                           ('candidate', self.candidate, 'candidate')]:
            self.assertEqual(receipts[variant]['revision'], revision)
            self.assertEqual((Path(receipts[variant]['source']) / 'payload.txt').read_text(), content)
        self.assertEqual(self.payload.read_text(), 'dirty owner work')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.head)
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def harness():
    path = ROOT / 'tools/diag_trio_generic_equivalence.py'
    if not path.exists():
        raise AssertionError('S05 measurement harness not implemented')
    spec = importlib.util.spec_from_file_location('s05_measure', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PathTests(unittest.TestCase):
    def test_preservation_roots_follow_current_home_and_include_explicit_user_roots(self):
        m = harness()
        self.assertTrue(callable(getattr(m, 'preservation_roots', None)),
                        'portable user inventory helper is missing')
        with tempfile.TemporaryDirectory(dir=Path.home()/'.hermes/cache/scratch') as directory:
            home = Path(directory)
            repo = home/'checkout'
            owner = home/'Downloads/Project/STAR-ARMADA'
            owner.mkdir(parents=True)
            extra = home/'custom-user-data'
            extra.mkdir()
            with patch.object(m.Path, 'home', return_value=home):
                self.assertEqual(m.preservation_roots(repo, [extra, repo]),
                                 [repo.resolve(), owner.resolve(), extra.resolve()])
                owner.rmdir()
                self.assertEqual(m.preservation_roots(repo), [repo.resolve()])

    def test_output_guard_uses_current_home_or_explicit_scratch_and_rejects_escapes(self):
        m = harness()
        self.assertTrue(callable(getattr(m, 'guard_output', None)),
                        'portable scratch guard helper is missing')
        with tempfile.TemporaryDirectory(dir=Path.home()/'.hermes/cache/scratch') as directory:
            home = Path(directory)/'another-user'
            scratch = home/'.hermes/cache/scratch'
            scratch.mkdir(parents=True)
            outside = home/'outside'
            outside.mkdir()
            (scratch/'escape').symlink_to(outside, target_is_directory=True)
            with patch.object(m.Path, 'home', return_value=home), patch.dict(os.environ, {'TMPDIR': '/tmp'}):
                self.assertEqual(m.guard_output(scratch/'run'), (scratch/'run').resolve())
                for invalid in (outside/'run', scratch/'escape/run', scratch):
                    with self.assertRaisesRegex(ValueError, 'scratch'):
                        m.guard_output(invalid)
            explicit = home/'selected-workspace'
            self.assertEqual(m.guard_output(explicit/'run', explicit), (explicit/'run').resolve())
            with self.assertRaises(ValueError):
                m.guard_output(scratch/'run', explicit)


class RepeatPolicyTests(unittest.TestCase):
    def test_unusable_runtime_projection_protects_every_pixel(self):
        from types import SimpleNamespace
        m = harness()
        self.assertTrue(callable(getattr(m, 'conservative_model_mask', None)), 'fail-closed runtime wrapper missing')
        cam = SimpleNamespace(width=20,height=20,near=2.,fov=55.,eye_position=lambda:(0,0,0),basis=lambda:np.eye(3))
        mask,proof = m.conservative_model_mask(cam,[dict(name='near',vertices=[[-1,-1,1],[1,1,3]],frame=((0,0,0),np.eye(3),1))])
        self.assertTrue(mask.all()); self.assertTrue(proof['fail_closed'])
        a=np.zeros((20,20,3),np.uint8); b=a.copy(); b[0,0,0]=1
        with self.assertRaises(AssertionError): m.enforce_repeat(a,b,mask)

    def test_runtime_gates_reject_mutated_real_pair_without_relaxing_cross_source(self):
        m = harness()
        self.assertTrue(callable(getattr(m, 'enforce_repeat', None)), 'runtime gate missing')
        a = np.zeros((20,20,3), np.uint8); mask = np.zeros((20,20), bool); mask[10:,10:] = True
        for position, amplitude in (((0,0),2), ((10,10),1)):
            b = a.copy(); b[position[0],position[1],0] = amplitude
            with self.assertRaises(AssertionError): m.enforce_repeat(a,b,mask)
        b = a.copy(); b[:9,:15,0] = 1
        with self.assertRaises(AssertionError): m.enforce_repeat(a,b,mask)
        b = a.copy(); b[0,0,0] = 1
        self.assertTrue(m.enforce_repeat(a,b,mask)['passed'])
        with self.assertRaises(AssertionError): m.enforce_exact(a,b)
        self.assertTrue(m.enforce_exact(a,a)['changed_pixels'] == 0)

    def test_projected_geometry_rotations_clipping_and_fail_closed(self):
        import math
        from types import SimpleNamespace
        m = harness()
        self.assertTrue(callable(getattr(m, 'projected_model_mask', None)), 'geometry mask missing')
        cam = SimpleNamespace(width=200, height=120, near=2., fov=55.,
                              eye_position=lambda:(0.,0.,0.), basis=lambda:((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)))
        points = [[x,y,z] for x in (-5,5) for y in (-3,3) for z in (-4,4)]
        for angle in (0., .7, 2.2):
            c,s = math.cos(angle), math.sin(angle)
            basis = ((c,0.,-s),(0.,1.,0.),(s,0.,c))
            for distance in (30., 100., 1000.):
                models = [dict(name=str(i), vertices=points, frame=((x,0.,distance),basis,1.)) for i,x in enumerate((-20.,0.,20.))]
                mask, proof = m.projected_model_mask(cam, models)
                self.assertEqual(len(proof['models']), 3)
                for model in models:
                    for p in points:
                        world = np.array(model['frame'][0]) + np.array(p) @ np.array(basis)
                        sx = 100 + world[0]/world[2]*60/math.tan(math.radians(55)/2)
                        sy = 60 - world[1]/world[2]*60/math.tan(math.radians(55)/2)
                        if 0 <= sx < 200 and 0 <= sy < 120: self.assertTrue(mask[int(sy),int(sx)])
                self.assertEqual(proof['mask_sha256'], __import__('hashlib').sha256(mask.tobytes()).hexdigest())
        for bad in (float('nan'), float('inf'), 10**1000):
            with self.assertRaises(ValueError): m.projected_model_mask(cam, [dict(name='bad',vertices=points,frame=((bad,0,30),np.eye(3),1))])
        with self.assertRaises(ValueError): m.projected_model_mask(cam, [dict(name='near',vertices=points,frame=((0,0,3),np.eye(3),1))])
        with self.assertRaises(ValueError): m.projected_model_mask(cam, [])

    def test_background_allowance_is_narrow_and_cross_source_stays_exact(self):
        m = harness()
        self.assertTrue(callable(getattr(m, 'repeat_metrics', None)), 'repeat policy missing')
        a = np.zeros((20, 20, 3), np.uint8)
        mask = np.zeros((20, 20), bool); mask[10:, 10:] = True
        b = a.copy(); b[:8, :16, 0] = 1
        self.assertTrue(m.repeat_metrics(a, b, mask)['passed'])
        self.assertEqual(m.pixel_metrics(a, b)['changed_pixels'], 128)
        b[8, 0, 0] = 1
        self.assertFalse(m.repeat_metrics(a, b, mask)['passed'])
        b = a.copy(); b[0, 0, 0] = 2
        self.assertFalse(m.repeat_metrics(a, b, mask)['passed'])
        b = a.copy(); b[10, 10, 0] = 1
        self.assertFalse(m.repeat_metrics(a, b, mask)['passed'])
        for bad in (a.astype(float), a[:0], np.zeros((20,20,4), np.uint8), [[1]], np.full((20,20,3), np.nan)):
            with self.assertRaises(ValueError): m.repeat_metrics(bad, bad, mask)
        for bad in (mask.astype(int), mask[:0], None):
            with self.assertRaises(ValueError): m.repeat_metrics(a, a, bad)


class MeasurementTests(unittest.TestCase):
    def test_exact_comparison_catches_single_channel_and_shape(self):
        m = harness()
        a = np.zeros((8, 9, 3), np.uint8)
        self.assertEqual(m.pixel_metrics(a, a)['changed_pixels'], 0)
        b = a.copy(); b[2, 3, 1] = 1
        self.assertEqual(m.pixel_metrics(a, b)['changed_pixels'], 1)
        with self.assertRaises(ValueError):
            m.pixel_metrics(a, b[:2])

    def test_feature_span_is_role_local_and_rejects_incomplete_metadata(self):
        m = harness()
        d = {'batches': {'lit': [0, 1, 2], 'cool': [0]}, 'parts': [
            {'name': 'other', 'role': 'lit', 'triangles': 1},
            {'name': 'emitter', 'role': 'cool', 'triangles': 1},
            {'name': 'lamp', 'role': 'lit', 'triangles': 2}]}
        self.assertEqual(m.part_spans(d)['lamp'], ('lit', 1, 3))
        d['parts'][-1]['triangles'] = 1
        with self.assertRaises(ValueError): m.part_spans(d)

    def test_feature_gate_requires_local_broad_emission_not_global_light(self):
        m = harness()
        absent = np.zeros((80, 80, 3), np.uint8)
        full = absent.copy(); full[35:40, 35:42] = (240, 200, 90)
        self.assertTrue(m.feature_metrics(full, absent, (38, 38), 'warm')['passed'])
        self.assertFalse(m.feature_metrics(full, full, (38, 38), 'warm')['passed'])
        self.assertFalse(m.feature_metrics(full, absent, (4, 4), 'warm')['passed'])
        sliver = absent.copy(); sliver[38, 35:42] = (240, 200, 90)
        self.assertFalse(m.feature_metrics(sliver, absent, (38, 38), 'warm')['passed'])
        cyan = absent.copy(); cyan[35:40, 35:42] = (70, 210, 255)
        self.assertTrue(m.feature_metrics(cyan, absent, (38, 38), 'cool')['passed'])

    def test_tick_comparison_rejects_missing_or_shifted_tick(self):
        m = harness()
        a = [{'tick': 0, 'sha256': 'a'}, {'tick': 1, 'sha256': 'b'}]
        self.assertTrue(m.same_ticks(a, a))
        self.assertFalse(m.same_ticks(a, a[:1]))
        self.assertFalse(m.same_ticks(a, [{'tick': 2, 'sha256': 'a'}, a[1]]))

if __name__ == '__main__':
    unittest.main()
