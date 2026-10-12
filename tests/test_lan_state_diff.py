"""`tools/lan_state_diff.py` must name the value a checksum difference hides.

The tool exists because a mixed-platform pair reported different lockstep
checksums from the very first tick: 'checksums differ' is not a diagnosis. These
tests pin that the dump is exactly what `precise_checksum` hashes (so the tool
can never drift from the checksum it explains) and that the differ reports a JSON
path with both values.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('lan_state_diff', ROOT/'tools/lan_state_diff.py')
lan_state_diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lan_state_diff)

from game.net import diag, lan  # noqa: E402  (path set by the tool import above)


class DumpTests(unittest.TestCase):
    def test_the_dumped_structure_is_exactly_what_the_checksum_hashes(self):
        """Non-vacuity: hashing the dumped structure must reproduce the ticksum.

        Without this, the tool could explain a difference that the checksum does
        not actually see (or miss the one it does).
        """
        manager = diag.lan_scene(0)
        round_tripped = json.loads(json.dumps(lan.canonical_state(manager)))
        self.assertEqual(hashlib.sha256(lan._json(round_tripped)).hexdigest(),
                         lan.precise_checksum(manager))

    def test_dump_writes_the_checksum_and_the_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'state.json'
            payload = lan_state_diff.dump(0, out)
            written = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(written['checksum'], payload['checksum'])
            self.assertEqual(written['ticks'], 0)
            # canonical_state() mirrors precise_checksum's own nesting.
            self.assertIn('entities', written['state']['state'])
            self.assertIn('ai', written['state'])
            self.assertIn('systems', written['state'])

    def test_a_simulated_step_changes_the_dumped_state(self):
        """The tick argument must really step the scene, or the diff is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            as_built = lan_state_diff.dump(0, Path(tmp)/'a.json')
            after_one = lan_state_diff.dump(1, Path(tmp)/'b.json')
            self.assertNotEqual(as_built['checksum'], after_one['checksum'])
            self.assertTrue(lan_state_diff.differences(as_built['state'], after_one['state']))

    def test_two_dumps_of_the_same_scene_are_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = lan_state_diff.dump(2, Path(tmp)/'a.json')
            second = lan_state_diff.dump(2, Path(tmp)/'b.json')
            self.assertEqual(first['checksum'], second['checksum'])
            self.assertEqual(first['state'], second['state'])


class DifferencesTests(unittest.TestCase):
    def test_a_single_leaf_difference_is_named_with_both_values(self):
        left = dict(state=dict(entities={0: dict(x=1.0, yaw=0.0)},
                               tick=0))
        right = dict(state=dict(entities={0: dict(x=1.0000000000000002, yaw=0.0)},
                                tick=0))
        found = lan_state_diff.differences(left['state'], right['state'])
        self.assertEqual([path for path, _, _ in found], ['$.entities.0.x'])
        self.assertEqual(found[0][1], 1.0)
        self.assertEqual(found[0][2], 1.0000000000000002)

    def test_boolean_and_integer_type_changes_are_not_silently_equal(self):
        found = lan_state_diff.differences(dict(flag=True), dict(flag=1))
        self.assertEqual([path for path, _, _ in found], ['$.flag'])

    def test_missing_keys_and_length_changes_are_reported(self):
        found = lan_state_diff.differences(dict(a=[1, 2], b=1), dict(a=[1], c=1))
        paths = {path for path, _, _ in found}
        self.assertIn('$.b', paths)
        self.assertIn('$.c', paths)
        self.assertIn('$.a (length)', paths)

    def test_limit_stops_the_walk(self):
        left = {str(i): i for i in range(50)}
        right = {str(i): i + 1 for i in range(50)}
        self.assertEqual(len(lan_state_diff.differences(left, right, limit=3)), 3)

    def test_equal_states_have_no_differences(self):
        state = dict(tick=0, entities={0: dict(x=1.5)})
        self.assertEqual(lan_state_diff.differences(state, state), [])


class CliTests(unittest.TestCase):
    def _dump(self, path, ticks=0):
        payload = lan_state_diff.dump(ticks, path)
        return payload

    def test_identical_dumps_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            left, right = Path(tmp)/'a.json', Path(tmp)/'b.json'
            self._dump(left)
            self._dump(right)
            result = subprocess.run([sys.executable, str(ROOT/'tools/lan_state_diff.py'),
                                     'diff', str(left), str(right)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('IDENTICAL', result.stdout)

    def test_a_doctored_dump_exits_one_and_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            left, right = Path(tmp)/'a.json', Path(tmp)/'b.json'
            payload = self._dump(left)
            payload['state']['state']['tick'] = 7          # pretend the other machine
            payload['checksum'] = 'f' * 64
            right.write_text(json.dumps(payload), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT/'tools/lan_state_diff.py'),
                                     'diff', str(left), str(right)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('$.state.tick', result.stdout)
            self.assertIn('left : 0', result.stdout)
            self.assertIn('right: 7', result.stdout)

    def test_non_dump_and_missing_files_exit_two_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            not_a_dump = Path(tmp)/'other.json'
            not_a_dump.write_text(json.dumps({'nope': 1}), encoding='utf-8')
            for bad in (str(not_a_dump), str(Path(tmp)/'absent.json')):
                result = subprocess.run([sys.executable, str(ROOT/'tools/lan_state_diff.py'),
                                         'diff', bad, bad],
                                        cwd=ROOT, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertIn('lan_state_diff:', result.stderr)


if __name__ == '__main__':                       # pragma: no cover - manual entry
    unittest.main()
