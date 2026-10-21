"""W11: the window is the default, and a build that has no window still shows a game.

Three things can go wrong when a renderer becomes a setting, and each has a test here:

- a saved or hand-edited file names a renderer that does not exist;
- the frozen bundle carries the viewer somewhere the source tree does not;
- the settings screen grows a row that no key is behind.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RendererSettingTest(unittest.TestCase):
    def test_the_shipped_default_is_the_native_window(self):
        from render import menus
        self.assertEqual(menus.DEFAULT_SETTINGS["renderer"], "cpp")

    def test_a_hand_edited_file_naming_nothing_reads_as_the_default(self):
        from render import menus
        directory = tempfile.mkdtemp(prefix="w11-settings-")
        path = os.path.join(directory, "settings.json")
        original = menus.SETTINGS_PATH
        menus.SETTINGS_PATH = path
        try:
            Path(path).write_text(json.dumps({"renderer": "vulkan", "music_volume": 0.25}))
            loaded = menus.load_settings()
            self.assertEqual(loaded["renderer"], "cpp")
            # An unreadable renderer must not take the rest of the file with it.
            self.assertAlmostEqual(loaded["music_volume"], 0.25)

            Path(path).write_text(json.dumps({"renderer": "legacy"}))
            self.assertEqual(menus.load_settings()["renderer"], "legacy")
        finally:
            menus.SETTINGS_PATH = original

    def test_the_settings_screen_has_a_row_for_it(self):
        source = (ROOT / "render" / "classic_screens.py").read_text()
        self.assertIn("('Renderer (next session)', 'renderer', 'cycle_renderer')", source)
        menu_source = (ROOT / "render" / "menus.py").read_text()
        self.assertIn('elif act == "cycle_renderer":', menu_source)


class FindBinaryTest(unittest.TestCase):
    def _executable(self, directory: str) -> str:
        path = os.path.join(directory, "armada_viewer")
        Path(path).write_text("#!/bin/sh\nexit 0\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def test_a_frozen_bundle_finds_its_own_viewer(self):
        from render_bridge import cpp_window
        bundle = tempfile.mkdtemp(prefix="w11-bundle-")
        os.makedirs(os.path.join(bundle, "cpp"), exist_ok=True)
        shipped = self._executable(os.path.join(bundle, "cpp"))
        empty_root = tempfile.mkdtemp(prefix="w11-root-")
        setattr(sys, "_MEIPASS", bundle)
        try:
            self.assertEqual(cpp_window.find_binary(empty_root), shipped)
        finally:
            delattr(sys, "_MEIPASS")

    def test_a_source_checkout_still_uses_its_build_directory(self):
        from render_bridge import cpp_window
        root = tempfile.mkdtemp(prefix="w11-src-")
        os.makedirs(os.path.join(root, "render_cpp", "build-w02"), exist_ok=True)
        built = self._executable(os.path.join(root, "render_cpp", "build-w02"))
        self.assertEqual(cpp_window.find_binary(root), built)

    def test_no_viewer_is_not_an_error(self):
        from render_bridge import cpp_window
        self.assertIsNone(cpp_window.find_binary(tempfile.mkdtemp(prefix="w11-none-")))


if __name__ == "__main__":
    unittest.main()
