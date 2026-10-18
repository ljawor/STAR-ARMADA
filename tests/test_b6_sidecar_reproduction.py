"""Behavioural reproduction of the review-only B6 sidecars; no Blender needed."""
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class B6SidecarReproductionTests(unittest.TestCase):
    def test_b6_sidecars_reproduce_from_the_real_batch_check(self):
        result = subprocess.run(
            [sys.executable, 'tools/art/write_pending_sidecars.py',
             '--batch', 's06-b6-imperial-ships', '--check'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, '0 stale sidecar(s)\n')


    def test_successful_check_does_not_write_pending_records(self):
        pending = ROOT / 'art/manifests/pending'
        paths = list(pending.glob('*.json'))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        result = subprocess.run(
            [sys.executable, 'tools/art/write_pending_sidecars.py',
             '--batch', 's06-b6-imperial-ships', '--check'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(set(paths), set(pending.glob('*.json')))
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})

    def test_stale_check_reports_without_repairing_or_creating_files(self):
        pending = ROOT / 'art/manifests/pending'
        batch = json.loads((pending / 'S06-BATCH-B6-IMPERIAL-SHIPS.json').read_text())
        # Keep the scratch directory inside ROOT so the real CLI can report relative paths.
        with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts') as directory:
            out = Path(directory)
            for asset in batch['assets']:
                name = 'S06-' + asset['identifier'].upper().replace('_', '-') + '.json'
                (out / name).write_bytes((pending / name).read_bytes())
            victim = out / 'S06-IMPERIAL-CORVETTE.json'
            victim.write_bytes(b'stale\n')
            missing = out / 'S06-IMPERIAL-CONVOY.json'
            missing.unlink()
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()}
            result = subprocess.run(
                [sys.executable, 'tools/art/write_pending_sidecars.py',
                 '--batch', batch['batch'], '--check', '--out-dir', str(out)],
                cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count('STALE '), 2)
            self.assertTrue(result.stdout.endswith('2 stale sidecar(s)\n'), result.stdout)
            self.assertEqual(before, {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.iterdir()})

    def test_declared_seed_arguments_reach_real_existing_master_refusal(self):
        pending = ROOT / 'art/manifests/pending'
        batch = json.loads((pending / 'S06-BATCH-B6-IMPERIAL-SHIPS.json').read_text())
        self.assertEqual(len(batch['assets']), 8)
        for asset in batch['assets']:
            with self.subTest(binding=asset['binding']):
                seed = ROOT / asset['seed']
                sidecar = json.loads((pending / (
                    'S06-' + asset['identifier'].upper().replace('_', '-') + '.json')).read_text())
                self.assertEqual(sidecar['initial_seed']['sha256'],
                                 hashlib.sha256(seed.read_bytes()).hexdigest())
                self.assertEqual(sidecar['initial_seed']['selects'], asset['seed_arg'])
                # This is deliberately a refusal, before importing bpy or doing any work.
                # It validates the seed's actual ROWS lookup, not its historical prose.
                result = subprocess.run(
                    [sys.executable, str(seed), '--', *shlex.split(asset['seed_arg'])],
                    cwd=ROOT, capture_output=True, text=True, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(asset['identifier'] + '.blend is the editable master.', result.stderr)
                self.assertNotIn('unknown target', result.stderr)
                self.assertNotIn('No module named', result.stderr)
                self.assertIn('export_' + asset['identifier'] + '.py', result.stderr)


if __name__ == '__main__':
    unittest.main()
