"""`tools/compare_netdiag.py` decides whether two machines can play together.

The clauses are the two that decide a mixed-platform LAN match: the handshake
identity (version/protocol/content hash — issue #56) and the deterministic scene
fingerprint (a matching handshake still desyncs when the ticks checksum differs).
Fixtures here are report shapes, not live probes; the real reports are compared
by hand with the tool itself.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('compare_netdiag', ROOT/'tools/compare_netdiag.py')
compare_netdiag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_netdiag)


def report(platform_, *, content_hash='a' * 64, checksum='b' * 64, ticks=3,
           timeline_offsets=0, components=None, game_version='0.11.0',
           protocol_version=1, addresses=None):
    """A minimal `--netdiag info` report.

    `timeline_offsets` shifts the per-tick checksums so two reports can be made to
    agree or disagree at a chosen tick (0 = identical).
    """
    timeline = [dict(tick=tick, checksum=f'{tick + timeline_offsets:064x}')
                for tick in range(ticks + 1)]
    return dict(
        tool='netdiag', mode='info',
        environment=dict(os_name=platform_, os_release='1', machine='x86_64',
                         python='3.11.9', game_version=game_version,
                         protocol_version=protocol_version, content_hash=content_hash),
        addresses=addresses if addresses is not None else
        dict(route_preferred='192.168.1.5', all=['127.0.0.1', '192.168.1.5'],
             detail=[], dialable=['192.168.1.5']),
        sim_fingerprint=dict(ticks=ticks, checksum=checksum, timeline=timeline,
                             components=components or {'entities': 'e' * 16, 'players': 'p' * 16}),
    )


class CompareTests(unittest.TestCase):
    def test_agreeing_machines_pass_every_clause(self):
        ok, lines = compare_netdiag.compare(report('macOS'), report('Windows'))
        self.assertTrue(ok, lines)
        joined = '\n'.join(lines)
        self.assertIn(f'OK   content_hash {"a" * 16}…', joined)
        self.assertIn(f'OK   simulation fingerprint {"b" * 16}…', joined)
        self.assertNotIn('FAIL', joined)

    def test_content_hash_mismatch_is_named_as_the_handshake_clause(self):
        ok, lines = compare_netdiag.compare(report('macOS'), report('Windows', content_hash='c' * 64))
        self.assertFalse(ok)
        joined = '\n'.join(lines)
        self.assertIn('FAIL content_hash', joined)
        self.assertIn('content mismatch', joined)
        self.assertIn('a' * 16, joined)
        self.assertIn('c' * 16, joined)

    def test_version_and_protocol_mismatches_are_separate_clauses(self):
        ok, lines = compare_netdiag.compare(
            report('macOS'), report('Windows', game_version='0.10.0', protocol_version=2))
        self.assertFalse(ok)
        joined = '\n'.join(lines)
        self.assertIn("FAIL game_version", joined)
        self.assertIn("FAIL protocol_version", joined)

    def test_simulation_mismatch_reports_the_first_divergent_tick_and_components(self):
        left = report('macOS', timeline_offsets=0, components={'players': 'a' * 16, 'entities': 'b' * 16})
        right = report('Windows', timeline_offsets=2,
                       components={'players': 'a' * 16, 'entities': 'c' * 16})
        ok, lines = compare_netdiag.compare(left, right)
        self.assertFalse(ok)
        joined = '\n'.join(lines)
        self.assertIn('FAIL simulation fingerprint', joined)
        self.assertIn('desync', joined)
        self.assertIn('first divergent tick: 0', joined)
        self.assertIn('differing state components: entities', joined)
        self.assertNotIn('players,', joined)

    def test_reports_predating_the_timeline_still_compare_without_crashing(self):
        left = report('macOS'); right = report('Windows', checksum='d' * 64)
        for report_ in (left, right):
            report_['sim_fingerprint'].pop('timeline')
            report_['sim_fingerprint'].pop('components')
        ok, lines = compare_netdiag.compare(left, right)
        self.assertFalse(ok)
        joined = '\n'.join(lines)
        self.assertIn('no per-tick timeline', joined)
        self.assertIn('no per-component digests', joined)

    def test_fingerprint_that_failed_to_run_is_a_clause_not_a_pass(self):
        left = report('macOS')
        right = report('Windows')
        right['sim_fingerprint'] = dict(ticks=0, checksum=None, error='KeyError: boom')
        ok, lines = compare_netdiag.compare(left, right)
        self.assertFalse(ok)
        self.assertIn('FAIL simulation fingerprint on machine-b', '\n'.join(lines))

    def test_dialable_addresses_are_listed_per_machine(self):
        _, lines = compare_netdiag.compare(report('macOS'), report('Windows'))
        joined = '\n'.join(lines)
        self.assertIn('machine-a dialable at: 192.168.1.5', joined)
        self.assertIn('machine-b dialable at: 192.168.1.5', joined)

    def test_cli_exit_codes_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            same = Path(tmp)/'same.json'
            other = Path(tmp)/'other.json'
            same.write_text(json.dumps(report('macOS')), encoding='utf-8')
            other.write_text(json.dumps(report('Windows')), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT/'tools/compare_netdiag.py'),
                                     str(same), str(other), '--labels', 'mac', 'pc'],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('COMPARE_OK', result.stdout)
            self.assertIn('note mac:', result.stdout)
            self.assertIn('note pc:', result.stdout)

            other.write_text(json.dumps(report('Windows', content_hash='e' * 64)), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT/'tools/compare_netdiag.py'),
                                     str(same), str(other)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('COMPARE_FAIL', result.stdout)

    def test_unreadable_or_foreign_files_exit_two_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp)/'nope.json')
            foreign = Path(tmp)/'foreign.json'
            foreign.write_text(json.dumps({'tool': 'other'}), encoding='utf-8')
            for bad in (missing, str(foreign)):
                result = subprocess.run([sys.executable, str(ROOT/'tools/compare_netdiag.py'),
                                         bad, bad], cwd=ROOT, capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertIn('compare_netdiag:', result.stderr)

    def test_real_reports_from_two_platforms_compare(self):
        """The reports CI and the reporter actually produce load and compare."""
        with tempfile.TemporaryDirectory() as tmp:
            mac = Path(tmp)/'mac.json'
            mac.write_text(json.dumps(report('macOS')), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT/'tools/compare_netdiag.py'),
                                     str(mac), str(mac)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':                       # pragma: no cover - manual entry
    unittest.main()
