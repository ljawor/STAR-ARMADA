# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for STAR ARMADA.

Build (repo root):
    ./.venv/bin/pyinstaller star_armada.spec --noconfirm

Produces dist/STAR ARMADA.app (macOS) or dist/STAR ARMADA/STAR ARMADA.exe
(Windows / one-dir). Assets are bundled as data so DataStore finds them at
sys._MEIPASS/assets.
"""
import os
import re
import runpy
import sys
from pathlib import Path

block_cipher = None
ROOT = os.path.abspath(SPECPATH)


def _version() -> str:
    """Read the version from game/__init__.py — the single source of truth.

    It used to be written out by hand here too, and the two drifted: the
    package said 0.3.0 while the bundle and the DMG name still said 0.2.0.
    """
    with open(os.path.join(ROOT, "game", "__init__.py")) as f:
        m = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "0.0.0"


VERSION = _version()
# The native renderer is mandatory. Fail before Analysis if either product,
# any compiled shader, or any non-system runtime dependency is absent.
native = runpy.run_path(os.path.join(ROOT, "tools", "build_native_release.py"))
build_dir = os.path.join(ROOT, "render_cpp", "build-w02")
native_binaries, native_shaders = native["native_payload"](build_dir)
native_manifest = native["write_manifest"](
    build_dir, native_binaries, native_shaders, sys.platform)
# Bridge/controller dispatch imports are dynamic. Enumerate source modules
# without importing packages: collect_submodules('game') itself trips the
# game.systems cold-import cycle and otherwise silently omits that subtree.
runtime_imports = set()
for package in ('game', 'render', 'render_bridge'):
    for path in (Path(ROOT) / package).rglob('*.py'):
        parts = path.relative_to(ROOT).with_suffix('').parts
        if parts[-1] == '__init__':
            parts = parts[:-1]
        if all(part.isidentifier() for part in parts):
            runtime_imports.add('.'.join(parts))
runtime_imports = sorted(runtime_imports)

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=native_binaries,
    datas=[
        ("assets", "assets"),          # game data + fonts
        (str(native_manifest), "cpp"),
        # The approved Blender prototypes are the shipped default model selection, and the mesh
        # catalogue the window loads names their files. A bundle without them cannot build its
        # catalogue at all, which is what the first frozen attempt reported.
        ("visual_packs", "visual_packs"),
    ] + native_shaders,
    hiddenimports=runtime_imports + [
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.GLU",
        "numpy",
        # Imported lazily inside functions (menus, main --netdiag): name them
        # explicitly so the diagnostic exists in the frozen build that has to
        # report a connect failure.
        "game.net",
        "game.net.lan",
        "game.net.diag",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="STAR ARMADA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # GUI app: no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="STAR ARMADA",
)
app = BUNDLE(
    coll,
    name="STAR ARMADA.app",
    icon=None,
    bundle_identifier="com.ljawor.stararmada",
    info_plist={
        "CFBundleName": "STAR ARMADA",
        "CFBundleDisplayName": "STAR ARMADA",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        # CMake does not set a deployment floor; do not advertise macOS 11
        # compatibility from this plist. Native runner/OS acceptance is separate.
    },
)