"""Frozen-app path rules: a shipped .app must never write into its own bundle.

This is the regression test for a real release blocker. main.py/menus.py used
ROOT = dirname(__file__) for saves, so:

  * running the app straight off a mounted DMG (read-only) CRASHED on the
    autosave/screenshot write, and
  * installed in /Applications it wrote settings, campaign progress and
    autosaves INSIDE the .app, so every update silently wiped the player's
    settings and campaign progress.

render.menus decides its paths at import time from sys.frozen / sys._MEIPASS,
so we re-execute the module with those attributes faked and SNAPSHOT the
results while the fake is still in place. (Returning the module object would be
a trap: reload() mutates it in place, so restoring the real environment
afterwards would silently reset the values the caller is about to assert on.)
"""
from __future__ import annotations

import importlib
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIELDS = ("ROOT", "ASSET_ROOT", "USER_DIR", "SAVES_DIR",
          "SETTINGS_PATH", "CAMPAIGN_PATH", "BALANCE_PATH")


def paths_as_frozen(frozen, platform, meipass=None):
    """Re-import render.menus with a faked environment; return a value snapshot."""
    import render.menus as menus

    saved = {
        "frozen": getattr(sys, "frozen", None),
        "meipass": getattr(sys, "_MEIPASS", None),
        "platform": sys.platform,
    }
    try:
        if frozen:
            sys.frozen = True
            sys._MEIPASS = meipass or "/tmp/fake_bundle"
        else:
            for attr in ("frozen", "_MEIPASS"):
                if hasattr(sys, attr):
                    delattr(sys, attr)
        sys.platform = platform
        importlib.reload(menus)
        # snapshot WHILE the fake environment is active
        return types.SimpleNamespace(**{f: getattr(menus, f) for f in FIELDS})
    finally:
        for attr, val in (("frozen", saved["frozen"]), ("_MEIPASS", saved["meipass"])):
            if val is None:
                if hasattr(sys, attr):
                    delattr(sys, attr)
            else:
                setattr(sys, attr, val)
        sys.platform = saved["platform"]
        importlib.reload(menus)   # leave the module as we found it


class TestFrozenPaths(unittest.TestCase):
    def test_unfrozen_keeps_data_next_to_the_repo(self):
        m = paths_as_frozen(False, "darwin")
        self.assertEqual(m.ASSET_ROOT, m.ROOT)
        self.assertEqual(m.USER_DIR, m.ROOT)
        self.assertEqual(m.SAVES_DIR, os.path.join(m.ROOT, "saves"))

    def test_frozen_macos_never_writes_inside_the_bundle(self):
        bundle = "/Applications/STAR ARMADA.app/Contents/Frameworks"
        m = paths_as_frozen(True, "darwin", bundle)
        # assets come from the bundle ...
        self.assertEqual(m.ASSET_ROOT, bundle)
        # ... but nothing writable may live there
        for field in ("SAVES_DIR", "SETTINGS_PATH", "CAMPAIGN_PATH", "BALANCE_PATH"):
            self.assertFalse(getattr(m, field).startswith(bundle),
                             f"{field} must not be inside the app bundle")
        self.assertIn("Application Support", m.USER_DIR)

    def test_frozen_windows_uses_appdata(self):
        m = paths_as_frozen(True, "win32", r"C:\bundle")
        self.assertFalse(m.SAVES_DIR.startswith(r"C:\bundle"))
        self.assertIn("STAR ARMADA", m.USER_DIR)

    def test_frozen_linux_uses_xdg_data_home(self):
        m = paths_as_frozen(True, "linux", "/opt/bundle")
        self.assertFalse(m.SAVES_DIR.startswith("/opt/bundle"))
        self.assertIn("STAR ARMADA", m.USER_DIR)

    def test_campaign_briefing_reads_from_the_bundle(self):
        """The campaign asset is read-only and must resolve from _MEIPASS."""
        bundle = "/Applications/STAR ARMADA.app/Contents/Frameworks"
        m = paths_as_frozen(True, "darwin", bundle)
        self.assertEqual(
            os.path.join(m.ASSET_ROOT, "assets", "data", "campaign", "campaign.json"),
            os.path.join(bundle, "assets", "data", "campaign", "campaign.json"))

    def test_main_and_menus_agree_on_the_saves_dir(self):
        """main.py imports USER_DIR from menus — they must not diverge."""
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
        with open(src) as f:
            text = f.read()
        self.assertIn("USER_DIR", text)
        self.assertIn('SAVES_DIR = os.path.join(USER_DIR, "saves")', text)
        # the old, bundle-relative form must be gone
        self.assertNotIn('SAVES_DIR = os.path.join(ROOT, "saves")', text)

    def test_restores_the_real_environment(self):
        """The helper must not leak faked attributes into the rest of the suite."""
        paths_as_frozen(True, "darwin", "/tmp/whatever")
        self.assertFalse(getattr(sys, "frozen", False))
        import render.menus as menus
        self.assertEqual(menus.ASSET_ROOT, menus.ROOT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
