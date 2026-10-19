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
import subprocess
import sys
import tempfile
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
        # A bundle path must not collide with a real install on this machine: an
        # /Applications/... fake silently resolved against the shipped app the first
        # time, so every frozen case here builds its own temporary bundle.
        with tempfile.TemporaryDirectory() as bundle:
            bundle = os.path.realpath(bundle)
            m = paths_as_frozen(True, "darwin", bundle)
            # with no assets tree in the bundle the root falls back to _MEIPASS
            self.assertEqual(m.ASSET_ROOT, bundle)
            # ... but nothing writable may live there
            for field in ("SAVES_DIR", "SETTINGS_PATH", "CAMPAIGN_PATH", "BALANCE_PATH"):
                self.assertFalse(getattr(m, field).startswith(bundle),
                                 f"{field} must not be inside the app bundle")
            self.assertIn("Application Support", m.USER_DIR)

    def test_frozen_macos_resolves_the_symlinked_assets_tree(self):
        """Real PyInstaller 6 layout: data lives in Resources, _MEIPASS is Frameworks.

        Frameworks/assets is a symlink to ../Resources/assets, and the asset resolver
        refuses any path whose realpath leaves its root — so a root of Frameworks made
        it reject the bundle's own assets (E_SYMLINK_ESCAPE) and the frozen app died in
        start_game. ASSET_ROOT must be the directory that really owns assets/.
        """
        with tempfile.TemporaryDirectory() as top:
            top = os.path.realpath(top)   # /var -> /private/var on macOS
            resources = os.path.join(top, "Contents", "Resources")
            frameworks = os.path.join(top, "Contents", "Frameworks")
            os.makedirs(os.path.join(resources, "assets", "models", "schemas"))
            os.makedirs(frameworks)
            with open(os.path.join(resources, "assets", "marker.txt"), "w") as f:
                f.write("data\n")
            os.symlink(os.path.join("..", "Resources", "assets"),
                       os.path.join(frameworks, "assets"))
            m = paths_as_frozen(True, "darwin", frameworks)
            self.assertEqual(m.ASSET_ROOT, os.path.realpath(resources))
            self.assertNotEqual(m.ASSET_ROOT, frameworks)
            # the root the resolver is handed must contain the real tree, not a link out
            self.assertEqual(os.path.realpath(os.path.join(m.ASSET_ROOT, "assets")),
                             os.path.realpath(os.path.join(resources, "assets")))
            self.assertTrue(os.path.isfile(os.path.join(m.ASSET_ROOT, "assets", "marker.txt")))

    def test_one_folder_layout_keeps_meipass_as_the_root(self):
        """Windows/unpacked builds put assets directly inside _MEIPASS: unchanged."""
        with tempfile.TemporaryDirectory() as top:
            top = os.path.realpath(top)   # /var -> /private/var on macOS
            os.makedirs(os.path.join(top, "assets", "models"))
            m = paths_as_frozen(True, "win32", top)
            self.assertEqual(m.ASSET_ROOT, os.path.realpath(top))

    def test_frozen_windows_uses_appdata(self):
        m = paths_as_frozen(True, "win32", r"C:\bundle")
        self.assertFalse(m.SAVES_DIR.startswith(r"C:\bundle"))
        self.assertIn("STAR ARMADA", m.USER_DIR)

    def test_frozen_linux_uses_xdg_data_home(self):
        m = paths_as_frozen(True, "linux", "/opt/bundle")
        self.assertFalse(m.SAVES_DIR.startswith("/opt/bundle"))
        self.assertIn("STAR ARMADA", m.USER_DIR)

    def test_campaign_briefing_reads_from_the_bundle(self):
        """The campaign asset is read-only and must resolve from inside the bundle."""
        with tempfile.TemporaryDirectory() as top:
            top = os.path.realpath(top)
            resources = os.path.join(top, "Contents", "Resources")
            frameworks = os.path.join(top, "Contents", "Frameworks")
            campaign = os.path.join(resources, "assets", "data", "campaign")
            os.makedirs(campaign)
            os.makedirs(frameworks)
            with open(os.path.join(campaign, "campaign.json"), "w") as f:
                f.write("{}\n")
            os.symlink(os.path.join("..", "Resources", "assets"),
                       os.path.join(frameworks, "assets"))
            m = paths_as_frozen(True, "darwin", frameworks)
            resolved = os.path.join(m.ASSET_ROOT, "assets", "data", "campaign", "campaign.json")
            self.assertEqual(resolved, os.path.join(resources, "assets", "data", "campaign", "campaign.json"))
            self.assertTrue(os.path.isfile(resolved))

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

    def test_every_folder_a_dev_run_writes_into_the_repo_is_ignored(self):
        """USER_DIR is the repo in an unfrozen run, so its runtime folders must not be committable.

        A dev run writes saves and replays into the working tree, and — after a crash —
        `install_exception_hook(USER_DIR)` leaves diagnostics/failure-N.json beside them. The
        first two were ignored and the third was not, so a crash dump from the suite was
        swept into a `git add -A` and merged. Pinned here rather than in a source grep: the
        rule is only worth anything if git itself agrees with it.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isdir(os.path.join(root, ".git")):
            self.skipTest("not a git checkout")
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("git is not available")
        for sample in ("saves/save.json", "replays/match.rep", "diagnostics/failure-0.json"):
            with self.subTest(sample=sample):
                result = subprocess.run(["git", "-C", root, "check-ignore", "-q", sample],
                                        capture_output=True)
                self.assertEqual(result.returncode, 0,
                                 f"{sample} would be committed: add its folder to .gitignore")


if __name__ == "__main__":
    unittest.main(verbosity=2)
