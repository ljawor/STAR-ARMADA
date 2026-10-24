"""Discover the mandatory renderer in source and frozen native builds."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from render_bridge.cpp_window import find_binary


class NativeBinaryDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-discovery-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.bundle = Path(self.temp.name) / 'bundle'
        self.root.mkdir()
        self.bundle.mkdir()
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('STAR_ARMADA_CPP_VIEWER', None)

    @staticmethod
    def executable(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'discovery fixture; never executed')
        path.chmod(0o755)
        return str(path)

    def test_windows_frozen_uses_exe_and_prefers_bundle(self):
        shipped = self.executable(self.bundle / 'cpp' / 'armada_viewer.exe')
        self.executable(self.root / 'render_cpp/build-w02/armada_viewer.exe')
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True):
            self.assertEqual(find_binary(str(self.root)), shipped)

    def test_windows_source_uses_exe_without_bundle(self):
        built = self.executable(self.root / 'render_cpp/build-w02/armada_viewer.exe')
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(sys, '_MEIPASS', None, create=True):
            self.assertEqual(find_binary(str(self.root)), built)

    def test_macos_frozen_preserves_extensionless_name(self):
        shipped = self.executable(self.bundle / 'cpp/armada_viewer')
        with patch.object(sys, 'platform', 'darwin'), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True):
            self.assertEqual(find_binary(str(self.root)), shipped)

    def test_explicit_override_is_literal_and_takes_priority(self):
        custom = self.executable(self.root / 'custom viewer.exe')
        self.executable(self.bundle / 'cpp/armada_viewer.exe')
        os.environ['STAR_ARMADA_CPP_VIEWER'] = custom
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True):
            self.assertEqual(find_binary(str(self.root)), custom)

    def test_missing_windows_renderer_is_not_reported_present(self):
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(sys, '_MEIPASS', str(self.bundle), create=True):
            self.assertIsNone(find_binary(str(self.root)))


if __name__ == '__main__':
    unittest.main()
