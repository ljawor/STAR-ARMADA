"""Bounded sanitized persistence and the real main failure boundary."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from test_lan_main import factories


class DiagnosticsTests(unittest.TestCase):
    def diagnostics(self):
        self.assertIsNotNone(importlib.util.find_spec('game.net.diagnostics'), 'Durable diagnostics missing')
        return importlib.import_module('game.net.diagnostics')

    def test_bounded_reports_never_include_arbitrary_error_text(self):
        diag = self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            for tick in range(30):
                self.assertTrue(diag.record_failure(root, phase='transport', tick=tick,
                    reason='Disconnected: 192.168.1.2 secret-token payload crew_load',
                    exception=RuntimeError('secret-token')))
            files = list((Path(root)/'diagnostics').glob('*.json'))
            self.assertLessEqual(len(files), 8)
            self.assertEqual(len(files), 8)
            for file in files:
                self.assertLess(file.stat().st_size, 1024)
                raw = file.read_text()
                for forbidden in ('192.168', 'secret-token', 'crew_load', 'payload'):
                    self.assertNotIn(forbidden, raw)
                row = json.loads(raw)
                self.assertEqual(row['phase'], 'transport')
                self.assertEqual(row['reason'], 'disconnect')
                self.assertTrue(row['build'])
                self.assertEqual(row['exception'], 'RuntimeError')
            blocker = Path(root)/'blocker'
            blocker.write_text('file')
            self.assertFalse(diag.record_failure(blocker, phase='input', tick=0, reason='x'))
            self.assertFalse(diag.record_failure(root, phase=object(), tick=object(), reason=object()))

    def test_report_write_fault_does_not_interrupt_main_teardown(self):
        diag = self.diagnostics()
        for operation in ('os.fsync', 'os.replace'):
            with tempfile.TemporaryDirectory() as root:
                ns = factories()
                session = SimpleNamespace(close=Mock())
                ns.update(USER_DIR=root, net_session=session,
                    state=SimpleNamespace(tick=4, _net_session=session))
                with patch('game.net.diagnostics.' + operation, side_effect=OSError('disk failure')):
                    ns['leave_game']('Disconnected', phase='transport')
                self.assertEqual(ns['mode'], 'menu')
                session.close.assert_called_once()
                self.assertFalse(list((Path(root)/'diagnostics').glob('*.json')))
                self.assertFalse(list((Path(root)/'diagnostics').glob('*.tmp')))

    def test_main_poll_failure_persists_before_graph_teardown(self):
        self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            session = SimpleNamespace(poll=Mock(), close=Mock(), snapshot={'error': 'Desync at tick 42'})
            ns.update(USER_DIR=root, net_session=session,
                state=SimpleNamespace(tick=42, _net_session=session))
            ns['poll_network']()
            rows = list((Path(root)/'diagnostics').glob('*.json'))
            self.assertEqual(len(rows), 1)
            row = json.loads(rows[0].read_text())
            self.assertEqual((row['phase'], row['tick'], row['reason']), ('transport', 42, 'desync'))
            self.assertEqual(ns['mode'], 'menu')

    def test_main_input_python_exception_is_sanitized(self):
        self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            session = SimpleNamespace(close=Mock())
            ns.update(USER_DIR=root, net_session=session, state=SimpleNamespace(tick=8, _net_session=session),
                inputc=SimpleNamespace(handle_event=Mock(side_effect=RuntimeError('token=private at 192.168.1.5'))))
            ns['handle_game_input'](object())
            files = list((Path(root)/'diagnostics').glob('*.json'))
            self.assertEqual(len(files), 1)
            row = json.loads(files[0].read_text())
            self.assertEqual((row['phase'], row['tick'], row['exception']), ('input', 8, 'RuntimeError'))
            self.assertNotIn('private', files[0].read_text())

    def test_empty_python_exception_still_records(self):
        self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            session = SimpleNamespace(close=Mock())
            ns.update(USER_DIR=root, net_session=session, state=SimpleNamespace(tick=8, _net_session=session),
                inputc=SimpleNamespace(handle_event=Mock(side_effect=RuntimeError())))
            ns['handle_game_input'](object())
            self.assertEqual(len(list((Path(root)/'diagnostics').glob('*.json'))), 1)

    def test_simulation_failure_real_main_boundary_records(self):
        self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            session = SimpleNamespace(close=Mock())
            ns.update(USER_DIR=root, net_session=session, state=SimpleNamespace(tick=19, _net_session=session),
                advance_simulation=Mock(side_effect=RuntimeError('private')))
            self.assertIn('step_game_frame', ns, 'Testable production simulation boundary missing')
            self.assertFalse(ns['step_game_frame'](.034))
            row = json.loads(next((Path(root)/'diagnostics').glob('*.json')).read_text())
            self.assertEqual((row['phase'], row['tick'], row['exception']), ('simulation', 19, 'RuntimeError'))
            self.assertEqual(ns['mode'], 'menu')

    def test_both_real_tcp_peers_persist_terminal_error(self):
        self.diagnostics()
        from test_lan_human_safety import setup_pair
        sessions, managers = setup_pair(self)
        with tempfile.TemporaryDirectory() as root:
            namespaces = []
            for i in (0, 1):
                ns = factories()
                ns.update(USER_DIR=str(Path(root)/str(i)), net_session=sessions[i], state=managers[i].state)
                namespaces.append(ns)
            sessions[0]._fail('Desync at tick 0')
            namespaces[0]['poll_network']()
            import time
            deadline = time.monotonic() + 3
            while namespaces[1]['mode'] == 'game':
                namespaces[1]['poll_network']()
                self.assertLess(time.monotonic(), deadline)
            for i, reason in ((0, 'desync'), (1, 'disconnect')):
                row = json.loads(next((Path(root)/str(i)/'diagnostics').glob('*.json')).read_text())
                self.assertEqual((row['reason'], row['phase'], row['tick']), (reason, 'transport', 0))

    def test_session_simulation_failure_retains_phase_at_main_poll(self):
        self.diagnostics()
        from test_lan_human_safety import setup_pair
        sessions, managers = setup_pair(self)
        managers[0].state.tick = 1
        self.assertFalse(sessions[0].advance(managers[0], 1/30))
        self.assertEqual(sessions[0].snapshot['status'], 'error')
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            ns.update(USER_DIR=root, state=managers[0].state, net_session=sessions[0])
            ns['poll_network']()
            row = json.loads(next((Path(root)/'diagnostics').glob('*.json')).read_text())
            self.assertEqual(row['phase'], 'simulation')

    def test_empty_advance_exception_tears_down_at_real_main_poll_with_report(self):
        self.diagnostics()
        from test_lan_human_safety import setup_pair, run_ticks
        sessions, managers = setup_pair(self)
        run_ticks(self, sessions, managers, 1)
        session, manager = sessions[0], managers[0]
        with patch.object(manager, 'step', side_effect=ValueError()) as step:
            self.assertFalse(session.advance(manager, 1/30))
        step.assert_called_once()
        self.assertEqual(session.snapshot['status'], 'error')
        self.assertEqual(session.snapshot['error'], '')
        with tempfile.TemporaryDirectory() as root:
            ns = factories()
            ns.update(USER_DIR=root, state=manager.state, net_session=session)
            original_close = session.close
            def close_after_report():
                rows = list((Path(root)/'diagnostics').glob('*.json'))
                self.assertEqual(len(rows), 1)
                self.assertIs(ns['net_session'], session)
                self.assertIs(manager.state._net_session, session)
                original_close()
            with patch.object(session, 'close', side_effect=close_after_report) as close:
                ns['poll_network']()
            self.assertEqual(ns['mode'], 'menu')
            close.assert_called_once()
            self.assertIsNone(ns['net_session'])
            self.assertIsNone(manager.state._net_session)
            self.assertEqual(session.snapshot['status'], 'closed')
            self.assertEqual(ns['menu'].lan_notice, 'LAN session failed.')
            rows = list((Path(root)/'diagnostics').glob('*.json'))
            self.assertEqual(len(rows), 1)
            row = json.loads(rows[0].read_text())
            self.assertEqual((row['phase'], row['tick'], row['reason']),
                             ('simulation', 1, 'controlled_termination'))

    def test_unhandled_hook_forwards_original_exception_when_diagnostics_fail(self):
        diag = self.diagnostics()
        import sys
        for provider_fails, operation in ((True, None), (False, 'os.fsync'),
                                          (False, 'os.replace'), (True, 'os.replace')):
            with self.subTest(provider_fails=provider_fails, operation=operation):
                with tempfile.TemporaryDirectory() as root, patch('sys.excepthook') as old:
                    tick_provider = Mock(side_effect=ValueError('tick failure')) if provider_fails else lambda: 77
                    diag.install_exception_hook(root, tick_provider)
                    try:
                        raise RuntimeError('original private payload')
                    except RuntimeError as exc:
                        original = sys.exc_info()
                    if operation:
                        with patch('game.net.diagnostics.' + operation, side_effect=OSError('write failure')):
                            sys.excepthook(*original)
                    else:
                        sys.excepthook(*original)
                    old.assert_called_once_with(*original)
                    self.assertIs(old.call_args.args[1], original[1])
                    self.assertIs(old.call_args.args[2], original[2])
                    rows = list((Path(root)/'diagnostics').glob('*.json'))
                    if operation:
                        self.assertEqual(rows, [])
                        self.assertFalse(list((Path(root)/'diagnostics').glob('*.tmp')))
                    else:
                        row = json.loads(rows[0].read_text())
                        self.assertIsNone(row['tick'])
                        self.assertEqual((row['reason'], row['exception']), ('python_exception', 'RuntimeError'))

    def test_unhandled_hook_records_and_preserves_previous_hook(self):
        diag = self.diagnostics()
        with tempfile.TemporaryDirectory() as root:
            old = Mock()
            with patch('sys.excepthook', old):
                diag.install_exception_hook(root, lambda: 77)
                import sys
                exc = RuntimeError('private payload')
                sys.excepthook(type(exc), exc, None)
                old.assert_called_once_with(type(exc), exc, None)
            rows = list((Path(root)/'diagnostics').glob('*.json'))
            self.assertEqual(len(rows), 1)
            row = json.loads(rows[0].read_text())
            self.assertEqual((row['phase'], row['tick'], row['reason']), ('unhandled', 77, 'python_exception'))
