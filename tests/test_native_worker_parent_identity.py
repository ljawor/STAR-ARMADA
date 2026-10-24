"""Portable Windows identity regression; mock only the kernel API boundary."""
import ctypes
import os
import time
import unittest
from unittest.mock import Mock, patch

from render_bridge import native_worker as worker


class ParentIdentityTests(unittest.TestCase):
    def kernel(self, creation=123, success=True):
        kernel = Mock()
        kernel.OpenProcess.return_value = 456
        kernel.GetCurrentProcess.return_value = -1
        def times(handle, created, exited, system, user):
            created._obj.dwLowDateTime = creation & 0xffffffff
            created._obj.dwHighDateTime = creation >> 32
            return success
        kernel.GetProcessTimes.side_effect = times
        def wait(handle, milliseconds):
            if milliseconds:
                time.sleep(.001)
            return 258
        kernel.WaitForSingleObject.side_effect = wait
        return kernel

    def test_reused_live_pid_with_stale_getppid_is_rejected_before_native(self):
        kernel = self.kernel(creation=124)
        config = dict(parent_pid=42, parent_creation_time=123, port=1234)
        with patch.object(os, 'name', 'nt'), patch.object(worker.sys, 'platform', 'win32'), \
                patch.object(os, 'getppid', return_value=42), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                patch.object(worker, 'configuration', return_value=config), \
                patch.object(worker.socket, 'create_connection', side_effect=AssertionError('guard yielded')), \
                patch.object(worker, 'load_library') as native:
            with self.assertRaisesRegex(RuntimeError, 'creation'):
                worker.run('unused')
        native.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(456)

    def test_matching_creation_allows_guard_and_closes_handle(self):
        kernel = self.kernel(creation=0xfedcba9876543210)
        with patch.object(os, 'name', 'nt'), patch.object(os, 'getppid', return_value=42), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            with worker.parent_guard(42, 0xfedcba9876543210):
                kernel.GetProcessTimes.assert_called_once()
                kernel.OpenProcess.assert_called_once_with(0x101000, False, 42)
        kernel.CloseHandle.assert_called_once_with(456)

    def test_query_failure_rejects_before_yield_and_closes_handle(self):
        kernel = self.kernel(success=False)
        with patch.object(os, 'name', 'nt'), patch.object(os, 'getppid', return_value=42), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            with self.assertRaisesRegex(RuntimeError, 'query.*creation'):
                with worker.parent_guard(42, 123):
                    self.fail('query failure allowed')
        kernel.CloseHandle.assert_called_once_with(456)

    def test_parent_captures_creation_before_spawning_each_worker(self):
        import json
        import tempfile
        from pathlib import Path
        from render_bridge import embedded
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            root = Path(temp)
            library = root / 'unused-library'
            library.touch()
            seen = []
            def spawn(command, **kwargs):
                seen.append(json.loads(Path(command[-1]).read_text()))
                raise RuntimeError('stop before spawning')
            with patch.object(embedded, 'find_library', return_value=str(library)), \
                    patch.object(worker, 'process_creation_time', side_effect=[123, 124]) as creation, \
                    patch.object(embedded.subprocess, 'Popen', side_effect=spawn):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, 'stop before spawning'):
                        embedded.EmbeddedWindow(['viewer', '--width', '320', '--height', '240'], root=root)
            self.assertEqual([config.get('parent_creation_time') for config in seen], [123, 124])
            self.assertEqual(creation.call_count, 2)

    def test_current_process_creation_uses_pseudo_handle_and_fixed_width_filetime(self):
        kernel = self.kernel(creation=0xfedcba9876543210)
        with patch.object(os, 'name', 'nt'), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            self.assertEqual(worker.process_creation_time(), 0xfedcba9876543210)
        self.assertEqual(kernel.GetProcessTimes.call_args.args[0], -1)
        self.assertEqual(ctypes.sizeof(kernel.GetProcessTimes.call_args.args[1]._obj), 8)
        kernel.OpenProcess.assert_not_called()
        kernel.CloseHandle.assert_not_called()  # GetCurrentProcess is a pseudo-handle.

    def test_posix_guard_rejects_non_null_creation(self):
        with patch.object(os, 'name', 'posix'), patch.object(os, 'getppid', return_value=42):
            with self.assertRaisesRegex(ValueError, 'parent_creation_time'):
                with worker.parent_guard(42, 123):
                    self.fail('non-null POSIX creation allowed')

    def test_creation_configuration_is_strict_on_both_platforms(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            base = Path(temp)
            frame = base / 'frame'
            frame.write_bytes(bytes(320 * 240 * 4))
            path = base / 'config.json'
            value = dict(port=1234, nonce='a'*64, library=str(frame), frame=str(frame),
                         parent_pid=42, parent_creation_time=None, width=320, height=240,
                         argv=['viewer', '--width', '320', '--height', '240'])
            for platform, valid, invalid in (
                    ('nt', (1, 2**64-1), (None, True, False, 0, -1, 2**64, '123', 1.0)),
                    ('posix', (None,), (1, True, '123'))):
                # Keep pathlib native; only the OS boundary used by validation changes.
                with patch.object(worker, 'Path', side_effect=type(base)), \
                        patch.object(os, 'name', platform):
                    for creation in valid:
                        path.write_text(json.dumps(dict(value, parent_creation_time=creation)))
                        self.assertEqual(worker.configuration(path)['parent_creation_time'], creation)
                    for creation in invalid:
                        with self.subTest(platform=platform, creation=creation):
                            path.write_text(json.dumps(dict(value, parent_creation_time=creation)))
                            with self.assertRaisesRegex(ValueError, 'parent_creation_time'):
                                worker.configuration(path)
                    old = dict(value)
                    del old['parent_creation_time']
                    path.write_text(json.dumps(old))
                    with self.assertRaisesRegex(ValueError, 'configuration fields'):
                        worker.configuration(path)
