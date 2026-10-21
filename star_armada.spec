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

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[
        # The native window (W11). A frozen build that ships the rings but not the viewer would
        # fall back to legacy on every launch and the migration would exist only in a checkout.
        ("render_cpp/build-w02/armada_viewer", "cpp"),
    ],
    datas=[
        ("assets", "assets"),          # game data + fonts
        # The compiled bgfx shaders. The viewer defaults to the directory baked in at build time
        # (the build tree), which does not exist inside a bundle, so `cpp_window.spawn` passes
        # `--shaders cpp/shaders` when the binary it found sits in a bundle.
        ("render_cpp/build-w02/shaders", "cpp/shaders"),
        # The approved Blender prototypes are the shipped default model selection, and the mesh
        # catalogue the window loads names their files. A bundle without them cannot build its
        # catalogue at all, which is what the first frozen attempt reported.
        ("visual_packs", "visual_packs"),
    ],
    hiddenimports=[
        "pygame.pkg_properties",
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
        "LSMinimumSystemVersion": "11.0",
    },
)