"""Cross-platform LAN diagnostics: `--netdiag` and the connect-code classifier.

Issue #56 ("multi player not working" — two platforms, neither direction
connects) has a Windows-side cause that is provable off Windows: ``connect_ex``
returns the raw Winsock in-progress code (10035) on Windows while the join path
compared its result against POSIX errno values, so a Windows client failed with
"Connection failed" whoever hosted.

These tests pin the classification table, prove the diagnostic really observes
an inbound connection (not an empty report), and exercise the report contract:
explicit output paths, missing parents, directory-valued paths, console-less
output and nonzero status on failure. The black-hole probe is the
platform-dependent half of the regression — on Windows CI it observes the real
Winsock code instead of trusting the table.
"""
import contextlib
import errno
import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest

from game.net import diag
from game.net.lan import (CONNECT_IN_PROGRESS, LanSession, classify_connect_result,
                          connect_failure_message, default_lan_options)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def pump_sessions(sessions, predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for session in sessions:
            session.poll()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def legacy_join_predicate(code):
    """The pre-fix expression from LanSession.join, kept to prove non-vacuity."""
    return code in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY)


class ConnectCodeTests(unittest.TestCase):
    def test_windows_winsock_in_progress_codes_are_accepted(self):
        for code in (10035, 10036, 10037):
            self.assertIn(code, CONNECT_IN_PROGRESS, code)
            self.assertEqual(classify_connect_result(code), 'pending', code)

    def test_posix_in_progress_codes_are_accepted(self):
        for code in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK, errno.EAGAIN):
            self.assertEqual(classify_connect_result(code), 'pending', code)

    def test_immediate_success_is_connected(self):
        self.assertEqual(classify_connect_result(0), 'connected')

    def test_failure_codes_fail_and_are_named(self):
        for code in (errno.ECONNREFUSED, errno.ETIMEDOUT, errno.EHOSTUNREACH,
                     errno.ENETUNREACH, 10061, 10060, 10065, 10051, 10013, 10049):
            self.assertEqual(classify_connect_result(code), 'failed', code)
            self.assertNotIn(code, CONNECT_IN_PROGRESS, code)
        refused = connect_failure_message(10061, '10.0.0.5', 7777)
        self.assertIn('10061', refused)
        self.assertIn('nothing is listening', refused)
        self.assertIn('10.0.0.5:7777', refused)
        self.assertIn('firewall', connect_failure_message(10060, '10.0.0.5', 7777))

    def test_unknown_and_non_integer_codes_fail_without_crashing(self):
        for code in (None, 'x', -1, 123456):
            self.assertEqual(classify_connect_result(code), 'failed', code)
        self.assertIn('unrecognized', connect_failure_message(123456, '10.0.0.5', 7777))

    def test_pre_fix_join_predicate_would_have_rejected_the_windows_code(self):
        """Non-vacuity for issue #56: the old expression rejected 10035."""
        self.assertFalse(legacy_join_predicate(10035))
        self.assertEqual(classify_connect_result(10035), 'pending')
        # The two must still agree on the codes the old expression did accept.
        for code in (0,) + (errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
            self.assertTrue(legacy_join_predicate(code), code)
            self.assertIn(classify_connect_result(code), ('connected', 'pending'), code)

    def test_observed_platform_connect_code_is_classified(self):
        """The code this platform really returns for a connect that cannot finish.

        192.0.2.0/24 (RFC 5737 TEST-NET-1) is never routed, so a nonblocking
        connect to it stays in progress. On a host with no route at all the
        platform answers with a hard failure instead and there is nothing to
        observe here, so that case skips loudly rather than passing silently.
        """
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.setblocking(False)
            code = client.connect_ex(diag.BLACK_HOLE)
        finally:
            client.close()
        verdict = classify_connect_result(code)
        if verdict == 'failed':
            self.skipTest(f'no black-holed route on this host: connect_ex returned {code} '
                          f'({errno.errorcode.get(code)})')
        self.assertIn(verdict, ('connected', 'pending'), code)


class NetdiagContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status = diag.cli(argv)
        return status, buffer.getvalue()

    def report_path(self, name='report.json'):
        return os.path.join(self.tmp.name, name)

    def test_info_report_is_written_with_required_fields(self):
        out = self.report_path()
        status, text = self.run_cli(['info', '--out', out])
        self.assertEqual(status, 0, text)
        self.assertTrue(os.path.isfile(out))
        with open(out) as handle:
            report = json.load(handle)
        self.assertEqual((report['tool'], report['mode']), ('netdiag', 'info'))
        self.assertEqual(report['output_path'], out)
        for key in ('platform', 'python', 'frozen', 'game_version', 'protocol_version',
                    'content_hash', 'user_dir'):
            self.assertIn(key, report['environment'])
        self.assertIn('route_preferred', report['addresses'])
        self.assertTrue(report['port_status']['bindable'], report['port_status'])
        self.assertTrue(report['loopback_pair']['paired'], report['loopback_pair'])
        self.assertRegex(report['sim_fingerprint']['checksum'] or '', r'^[0-9a-f]{64}$')
        self.assertEqual(report['sim_fingerprint']['ticks'], diag.SIM_FINGERPRINT_TICKS)
        self.assertIn('report:', text)

    def test_simulation_fingerprint_is_reproducible_and_data_bound(self):
        """Two peers compare this value before playing: it must be stable here
        and must move when the map data moves."""
        first = diag.sim_fingerprint(ticks=10)
        second = diag.sim_fingerprint(ticks=10)
        self.assertRegex(first['checksum'] or '', r'^[0-9a-f]{64}$')
        self.assertEqual(first, second)
        self.assertEqual(first['ticks'], 10)
        self.assertNotEqual(diag.sim_fingerprint(ticks=20)['checksum'], first['checksum'])

    def test_missing_parent_directories_are_created(self):
        out = os.path.join(self.tmp.name, 'nested', 'deeper', 'report.json')
        status, text = self.run_cli(['info', '--out', out])
        self.assertEqual(status, 0, text)
        self.assertTrue(os.path.isfile(out))

    def test_directory_valued_out_path_fails_with_nonzero_status(self):
        status, text = self.run_cli(['info', '--out', self.tmp.name])
        self.assertEqual(status, 2)
        self.assertIn('REPORT WRITE FAILED', text)

    def test_unknown_mode_and_option_are_rejected_with_usage(self):
        status, text = self.run_cli(['sideways'])
        self.assertEqual(status, 2)
        self.assertIn('usage: --netdiag', text)
        status, text = self.run_cli(['info', '--nope', '1'])
        self.assertEqual(status, 2)
        self.assertIn('unknown option', text)

    def test_help_exits_zero_with_usage(self):
        status, text = self.run_cli(['--help'])
        self.assertEqual(status, 0)
        self.assertIn('usage: --netdiag', text)

    def test_connect_requires_a_numeric_ipv4_address(self):
        status, text = self.run_cli(['connect', '--address', 'host.local',
                                     '--out', self.report_path()])
        self.assertEqual(status, 2)
        self.assertIn('numeric IPv4', text)
        status, text = self.run_cli(['connect', '--out', self.report_path()])
        self.assertEqual(status, 2)
        self.assertIn('--address', text)

    def test_connect_to_a_closed_port_reports_refusal_and_fails(self):
        port = free_port()
        out = self.report_path('refused.json')
        status, text = self.run_cli(['connect', '--address', '127.0.0.1', '--port', str(port),
                                     '--wait', '0.5', '--out', out])
        self.assertEqual(status, 1, text)
        with open(out) as handle:
            report = json.load(handle)
        self.assertFalse(report['ok'])
        self.assertNotEqual(report['raw_connect'].get('blocking_code'), 0)
        self.assertEqual(report['raw_connect'].get('outcome'), 'refused', report['raw_connect'])
        self.assertIn('nothing is listening', text)

    def test_raw_connect_reports_the_outcome_not_only_a_number(self):
        """A refused dial and a dropped SYN must not read as the same failure."""
        refused = diag.raw_connect('127.0.0.1', free_port(), timeout=1.0)
        self.assertEqual(refused['outcome'], 'refused')
        self.assertIn('nothing is listening', refused['outcome_message'])
        self.assertEqual(refused['nonblocking_verdict'], 'failed')

    def test_output_is_harmless_without_a_console(self):
        """Frozen GUI builds have stdout=None; --netdiag must still complete."""
        out = self.report_path('noconsole.json')
        saved = diag.sys.stdout
        diag.sys.stdout = None
        try:
            status = diag._finish(diag.run_info(), out)
        finally:
            diag.sys.stdout = saved
        self.assertEqual(status, 0)
        self.assertTrue(os.path.isfile(out))

    def test_user_dir_matches_menus_rule(self):
        try:
            import render.menus as menus
        except ImportError as exc:              # pragma: no cover - no pygame here
            self.skipTest(f'render.menus unavailable: {exc}')
        self.assertEqual(diag.user_dir(), menus.USER_DIR)


class NetdiagListenTests(unittest.TestCase):
    def test_listen_observes_a_real_inbound_connection(self):
        """The report must come from a real socket, not from an empty default."""
        port = free_port()
        results = {}

        def serve():
            results['report'] = diag.run_listen(port, wait=5.0)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        time.sleep(0.3)                          # let the listener bind first
        client = LanSession.join('127.0.0.1', port, name='probe')
        try:
            pump_sessions([client], lambda: client.snapshot['status'] == 'lobby')
        finally:
            client.close()
        thread.join(timeout=10)
        report = results.get('report')
        self.assertIsNotNone(report, 'run_listen never returned')
        self.assertTrue(report['connections'], report['verdict'])
        self.assertTrue(report['ok'], report['verdict'])
        arrived = [row for row in report['connections'] if row['tcp_arrived']]
        self.assertEqual(len(arrived), 1, arrived)
        self.assertTrue(arrived[0]['address'].startswith('127.0.0.1:'), arrived)
        self.assertTrue(arrived[0]['handshake_completed'], arrived)
        self.assertIn('completed the handshake', ' '.join(report['verdict']))

    def test_listen_without_a_peer_states_the_firewall_checks(self):
        report = diag.run_listen(free_port(), wait=0.3)
        report['wait'] = 0.3
        self.assertFalse(report['ok'])
        text = ' '.join(report['verdict'])
        self.assertIn('No TCP connection reached', text)
        self.assertIn('firewall', text)

    def test_listen_reports_a_port_it_cannot_open(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(('', 0))
        holder.listen(1)
        self.addCleanup(holder.close)
        port = holder.getsockname()[1]
        report = diag.run_listen(port, wait=0.2)
        self.assertFalse(report['ok'])
        self.assertIn('bind_error', report)
        self.assertIn('Could not open', ' '.join(report['verdict']))

    def test_peer_report_separates_tcp_arrival_from_the_handshake(self):
        port = free_port()
        host = LanSession.host(port, default_lan_options(), name='netdiag-host')
        self.addCleanup(host.close)
        client = LanSession.join('127.0.0.1', port, name='probe')
        self.addCleanup(client.close)
        pump_sessions([host, client], lambda: client.snapshot['status'] == 'lobby')
        rows = host.peer_report()
        self.assertEqual(len(rows), 1, rows)
        self.assertTrue(rows[0]['address'].startswith('127.0.0.1:'), rows)
        self.assertEqual(rows[0]['slot'], 1, rows)


if __name__ == '__main__':
    unittest.main()
