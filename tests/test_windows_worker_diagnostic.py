"""Isolated watchdog tests: no native imports, builds, or real subprocesses."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'diag_windows_worker_cleanup.py'
spec = importlib.util.spec_from_file_location('windows_worker_diagnostic', SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class WindowsWorkerDiagnosticTests(unittest.TestCase):
    def invoke(self, child, taskkill):
        output = io.StringIO()
        with mock.patch.object(diag, 'os', types.SimpleNamespace(name='nt')), \
                mock.patch.object(diag.sys, 'argv', [str(SCRIPT), '--run']), \
                mock.patch.object(diag.subprocess, 'Popen', return_value=child), \
                mock.patch.object(diag.subprocess, 'run', side_effect=taskkill) as run, \
                contextlib.redirect_stdout(output):
            code = diag.main()
        events = [json.loads(line) for line in output.getvalue().splitlines()
                  if line.startswith('{')]
        return code, output.getvalue(), events, run

    def test_taskkill_timeout_retains_tool_and_diagnostic_output(self):
        child = self.child(subprocess.TimeoutExpired('diagnostic', 100, output=b'evidence\n'),
                           (b'', None))
        failure = subprocess.TimeoutExpired('taskkill', 10, output=b'tool partial',
                                            stderr=b'tool error')
        code, output, events, _ = self.invoke(child, failure)
        self.assertEqual(code, 125)
        child.kill.assert_called_once_with()
        self.assertIn('evidence\n', output)
        event = next(e for e in events if e['stage'] == 'watchdog_taskkill')
        self.assertIn('TimeoutExpired', event['exception'])
        self.assertEqual(event['stdout'], 'tool partial')
        self.assertEqual(event['stderr'], 'tool error')
        self.assertTrue(any(e['stage'] == 'watchdog_failed' for e in events))

    def test_successful_taskkill_timeout_does_not_claim_descendant_cleanup(self):
        child = self.child(subprocess.TimeoutExpired('diagnostic', 100, output=b'partial\n'),
                           (b'partial\n', None))
        completed = types.SimpleNamespace(returncode=0, stdout=b'killed', stderr=b'')
        code, output, events, _ = self.invoke(child, [completed])
        self.assertEqual(code, 124)
        self.assertIn('partial\n', output)
        end = next(e for e in events if e['stage'] == 'watchdog_end')
        self.assertTrue(end['timed_out'])
        self.assertFalse(end['descendants_verified_stopped'])
        self.assertIn('descendant', end['note'])

    def test_unreaped_child_still_prints_the_captured_evidence(self):
        child = self.child(subprocess.TimeoutExpired('diagnostic', 100, output=b'partial evidence\n'),
                           subprocess.TimeoutExpired('diagnostic', 5))
        completed = types.SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        code, output, events, _ = self.invoke(child, [completed])
        self.assertEqual(code, 125)
        self.assertIn('partial evidence\n', output)
        self.assertTrue(any(e['stage'] == 'watchdog_failed' for e in events))

    def test_unreapable_child_keeps_the_newer_and_longer_buffer(self):
        child = self.child(
            subprocess.TimeoutExpired('diagnostic', 100, output=b'early evidence\n'),
            subprocess.TimeoutExpired('diagnostic', 5, output=b'early evidence\nlate detail\n'))
        completed = types.SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        code, output, events, _ = self.invoke(child, [completed])
        self.assertEqual(code, 125)
        self.assertIn('late detail', output, 'the newer snapshot was discarded')
        self.assertTrue(any(e['stage'] == 'watchdog_failed' for e in events))

    def test_taskkill_returning_nonzero_runs_the_direct_child_fallback(self):
        child = self.child(subprocess.TimeoutExpired('diagnostic', 100, output=b'evidence\n'),
                           (b'evidence\n', None))
        failed = types.SimpleNamespace(returncode=128, stdout=b'not found', stderr=b'')
        code, output, events, _ = self.invoke(child, [failed])
        self.assertEqual(code, 125)
        child.kill.assert_called_once_with()
        failure = next(e for e in events if e['stage'] == 'watchdog_failed')
        self.assertFalse(failure['descendants_verified_stopped'])
        self.assertIn('evidence\n', output)

    def child(self, *results):
        child = mock.Mock(pid=1234, returncode=-9)
        child.communicate.side_effect = results
        child.wait.return_value = -9
        return child

    def test_taskkill_launch_error_reports_failure_and_reaps_direct_child(self):
        child = self.child(subprocess.TimeoutExpired('diagnostic', 100,
                                                    output=b'baseline evidence\n'),
                           (b'baseline evidence\nfinal evidence\n', None))
        code, output, events, run = self.invoke(child, OSError('taskkill unavailable'))
        self.assertEqual(code, 125)
        child.kill.assert_called_once_with()
        self.assertEqual(child.communicate.call_args.kwargs, {'timeout': 5})
        self.assertIn('baseline evidence\nfinal evidence\n', output)
        failure = next(e for e in events if e['stage'] == 'watchdog_failed')
        self.assertFalse(failure['descendants_verified_stopped'])
        self.assertTrue(failure['direct_child_reaped'])
        self.assertIn('taskkill unavailable', output)
        self.assertEqual(run.call_args.kwargs['timeout'], 10)


if __name__ == '__main__':
    unittest.main()
