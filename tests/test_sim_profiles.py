"""Each scene profile must cover the subsystems it is used to prove (issue #56).

The single canonical scene was the whole cross-platform evidence, and it flies the
two fleets 22000 units apart: no ship is ever inside separation range, so the
collision maths — the heaviest per-tick floating-point work in the simulation, and
the module whose import a platform swap had just broken — never ran in it. Windows
CI stayed green while 86 local tests failed. These tests pin the coverage of each
profile, so a scene that measures nothing cannot pass for evidence again.
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

from game.net import diag

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('compare_netdiag', ROOT/'tools/compare_netdiag.py')
compare_netdiag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_netdiag)


class _CountingSqrt:
    """Stands in for the module's `math` and counts separation distance solves."""

    def __init__(self):
        self.calls = 0

    def sqrt(self, value):
        self.calls += 1
        return _real_sqrt(value)


from game.core.detmath import sqrt as _real_sqrt  # noqa: E402  (import order: after the stub)


def _separation_solves(profile, ticks):
    from game.systems import separation
    counter = _CountingSqrt()
    with mock.patch.object(separation, 'math', counter):
        fingerprint = diag.sim_fingerprint(ticks, profile=profile)
    return fingerprint, counter.calls


class SceneCoverageTests(unittest.TestCase):
    def test_every_profile_builds_and_hashes(self):
        for profile in diag.LAN_PROFILES:
            with self.subTest(profile=profile):
                fingerprint = diag.sim_fingerprint(5, profile=profile)
                self.assertIsNone(fingerprint.get('error'))
                self.assertEqual(fingerprint['profile'], profile)
                self.assertRegex(fingerprint['checksum'], r'^[0-9a-f]{64}$')

    def test_profile_ticks_cover_every_profile(self):
        self.assertEqual(sorted(diag.PROFILE_TICKS), sorted(diag.LAN_PROFILES))
        self.assertGreaterEqual(diag.PROFILE_TICKS['contact'], 300,
                                'the contact scene must outlast the fly-in, or it only '
                                'measures the approach')

    def test_unknown_profile_is_rejected_rather_than_silently_using_the_default(self):
        with self.assertRaises(ValueError):
            diag.lan_scene(0, profile='nonsense')

    def test_contact_scene_reaches_the_collision_maths_that_canonical_never_touches(self):
        """The gap this profile exists to close, asserted rather than assumed."""
        _, canonical_solves = _separation_solves('canonical', 30)
        _, contact_solves = _separation_solves('contact', 30)
        self.assertEqual(canonical_solves, 0,
                         'canonical is expected to be a strategic scene: if it now '
                         'engages, this test is the one to revisit')
        self.assertGreater(contact_solves, 0,
                           'the contact scene must push ships apart, or it proves no '
                           'more than the canonical one')
        self.assertGreater(contact_solves, 30,
                           'contact must keep interacting tick after tick, not collide '
                           'once and drift apart')

    def test_contact_scene_keeps_engaging_for_the_whole_fingerprint(self):
        _, solves = _separation_solves('contact', diag.PROFILE_TICKS['contact'])
        self.assertGreater(solves, diag.PROFILE_TICKS['contact'],
                           'ships must still be colliding in the last third of the run')

    def test_every_profile_is_reproducible_and_distinct(self):
        first = {name: diag.sim_fingerprint(30, profile=name)['checksum']
                 for name in diag.LAN_PROFILES}
        second = {name: diag.sim_fingerprint(30, profile=name)['checksum']
                  for name in diag.LAN_PROFILES}
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), len(first),
                         'two profiles that hash the same scene measure nothing extra')


class ReportContractTests(unittest.TestCase):
    def test_the_report_carries_every_profile_and_the_legacy_key_still_works(self):
        report = diag._base_report('info')
        report['sim_fingerprints'] = diag.sim_fingerprints(ticks=5)
        self.assertEqual(sorted(report['sim_fingerprints']), sorted(diag.LAN_PROFILES))
        report['sim_fingerprint'] = report['sim_fingerprints'][diag.DEFAULT_PROFILE]
        self.assertEqual(report['sim_fingerprint']['profile'], diag.DEFAULT_PROFILE)


class ComparatorTests(unittest.TestCase):
    def _report(self, checksums):
        return dict(tool='netdiag',
                    environment=dict(game_version='1.0.0', protocol_version=1,
                                     content_hash='a' * 64, os_name='x', os_release='1',
                                     machine='m', python='3.11'),
                    sim_fingerprint=dict(profile='canonical', checksum='a' * 64, ticks=60,
                                         timeline=[dict(tick=0, checksum='a' * 64)]),
                    sim_fingerprints={name: dict(profile=name, checksum=value, ticks=60,
                                                 timeline=[dict(tick=0, checksum=value)])
                                      for name, value in checksums.items()})

    def test_identical_reports_pass_and_name_every_profile(self):
        report = self._report({'canonical': 'a' * 64, 'contact': 'b' * 64})
        ok, lines = compare_netdiag.compare(report, report)
        self.assertTrue(ok)
        self.assertTrue(any('[canonical scene]' in line for line in lines))
        self.assertTrue(any('[contact scene]' in line for line in lines))

    def test_one_divergent_profile_fails_even_when_the_other_agrees(self):
        left = self._report({'canonical': 'a' * 64, 'contact': 'b' * 64})
        right = self._report({'canonical': 'a' * 64, 'contact': 'c' * 64})
        ok, lines = compare_netdiag.compare(left, right)
        self.assertFalse(ok)
        failures = [line for line in lines if line.startswith('FAIL')]
        self.assertTrue(failures)
        self.assertTrue(all('contact' in line for line in failures), failures)

    def test_a_machine_that_never_ran_a_profile_fails(self):
        left = self._report({'canonical': 'a' * 64, 'contact': 'b' * 64})
        right = self._report({'canonical': 'a' * 64})
        ok, lines = compare_netdiag.compare(left, right)
        self.assertFalse(ok)
        self.assertTrue(any('[contact scene]' in line and line.startswith('FAIL')
                            for line in lines), lines)

    def test_a_report_from_before_the_profiles_still_compares(self):
        """The single-profile shape the first Windows artifacts carry."""
        legacy = self._report({'canonical': 'a' * 64})
        for key in ('sim_fingerprints',):
            legacy.pop(key)
        self.assertEqual(compare_netdiag.fingerprint_profiles(legacy), {'canonical':
                        legacy['sim_fingerprint']})
        ok, lines = compare_netdiag.compare(legacy, legacy)
        self.assertTrue(ok)
        self.assertTrue(any('simulation fingerprint' in line for line in lines))


class StateDumpTests(unittest.TestCase):
    def test_a_dump_records_its_scene_so_a_mismatched_pair_is_visible(self):
        import tempfile
        from pathlib import Path
        _dump_spec = importlib.util.spec_from_file_location('lan_state_diff',
                                                           ROOT/'tools/lan_state_diff.py')
        lan_state_diff = importlib.util.module_from_spec(_dump_spec)
        _dump_spec.loader.exec_module(lan_state_diff)
        with tempfile.TemporaryDirectory() as folder:
            canonical = Path(folder)/'canonical.json'
            contact = Path(folder)/'contact.json'
            lan_state_diff.dump(0, canonical, scene='canonical')
            lan_state_diff.dump(0, contact, scene='contact')
            self.assertEqual(json.loads(canonical.read_text())['scene'], 'canonical')
            self.assertEqual(json.loads(contact.read_text())['scene'], 'contact')
            self.assertNotEqual(json.loads(canonical.read_text())['checksum'],
                                json.loads(contact.read_text())['checksum'])


if __name__ == '__main__':                       # pragma: no cover - manual entry
    unittest.main()
