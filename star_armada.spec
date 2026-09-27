# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for STAR ARMADA.

Build (repo root):
    ./.venv/bin/pyinstaller star_armada.spec --noconfirm

Produces dist/STAR ARMADA.app (macOS) or dist/STAR ARMADA/STAR ARMADA.exe
(Windows / one-dir). Assets are bundled as data so DataStore finds them at
sys._MEIPASS/assets.
"""
import os

block_cipher = None
ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ("assets", "assets"),          # game data + fonts
    ],
    hiddenimports=[
        "pygame.pkg_properties",
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.GLU",
        "numpy",
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
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "0.2.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)