#!/usr/bin/env python3
"""Prove a built STAR ARMADA .app actually contains the code we just wrote.

Why this exists: a plain grep inside a .app proves nothing. PyInstaller stores
Python modules marshalled inside PYZ.pyz, which lives inside the PKG CArchive
appended to the executable. Worse, marker-string checks give FALSE PASSES —
"impact_pos" already existed in projectiles.py before the fix, so looking for
the string tells you nothing about whether the fix is in the bundle. That is
exactly the class of mistake this repo has already paid for twice (a probe that
measured a silhouette could not see a blown-out interior).

So this does not guess at markers. It compiles the working-tree source and
compares a structural signature of the resulting code object against the code
object actually stored in the bundle. Equal signature => the shipped bytecode
IS this source. Any mismatch on any module => the artifact is stale.

Structure-only: co_filename and line-number tables are excluded on purpose,
because PyInstaller rewrites file paths and that must not count as a difference.

Usage:
    ./.venv/bin/python tools/appcheck.py ["dist/STAR ARMADA.app"]
Exit: 0 = APPCHECK_OK, 1 = APPCHECK_FAIL (stale or incomplete artifact)
"""
import hashlib
import marshal
import os
import re
import sys
import tempfile
import types

try:
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
except ImportError:
    print("APPCHECK_FAIL: PyInstaller not importable (run with ./.venv/bin/python)")
    sys.exit(1)

APP = sys.argv[1] if len(sys.argv) > 1 else "dist/STAR ARMADA.app"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Modules whose shipped bytecode must equal the working-tree source. These are
# the files the audio pass / crash fix touched, plus the entry point.
WATCHED = [
    "main",
    "render.audio",
    "game.systems.projectiles",
    "game.systems.damage",
]


def structure_signature(obj, h=None):
    """Hash a code object's structure, ignoring paths and line tables."""
    if h is None:
        h = hashlib.sha256()
    if isinstance(obj, types.CodeType):
        h.update(b"C" + obj.co_code)
        h.update(repr((obj.co_argcount, obj.co_posonlyargcount,
                       obj.co_kwonlyargcount, obj.co_flags & 0x0F,
                       tuple(obj.co_names), tuple(obj.co_varnames))).encode())
        for c in obj.co_consts:
            structure_signature(c, h)
    else:
        h.update(b"S" + repr(obj).encode())
    return h.hexdigest()


def find_exe(app):
    exe = os.path.join(app, "Contents", "MacOS", "STAR ARMADA")
    if os.path.exists(exe):
        return exe
    for root, _d, files in os.walk(app):
        for f in files:
            if f == "STAR ARMADA":
                return os.path.join(root, f)
    return None


EXE = find_exe(APP)
if EXE is None:
    print("APPCHECK_FAIL: no executable found in", APP)
    sys.exit(1)
print("executable:", EXE, os.path.getsize(EXE), "bytes")

# --- open the CArchive and pull out both the PYZ and the entry scripts ------
car = CArchiveReader(EXE)
pyz_name = next((n for n in car.toc if n.endswith(".pyz")), None)
if pyz_name is None:
    print("APPCHECK_FAIL: no PYZ in CArchive")
    sys.exit(1)

tmpdir = tempfile.mkdtemp(prefix="appcheck_")
pyz_file = os.path.join(tmpdir, "PYZ-00.pyz")
with open(pyz_file, "wb") as f:
    f.write(car.extract(pyz_name))
pyz = ZlibArchiveReader(pyz_file)

bundled = {}


def load_bundled(name):
    """Get the code object for a module, from the PYZ or the CArchive."""
    if name in bundled:
        return bundled[name]
    code = None
    if name in pyz.toc:
        code = pyz.extract(name)
    elif name in car.toc:
        try:
            code = marshal.loads(car.extract(name))
        except Exception:
            code = None
    bundled[name] = code
    return code


# --- version from the bundle ------------------------------------------------
plist = os.path.join(APP, "Contents", "Info.plist")
txt = open(plist, "rb").read().decode("utf-8", "replace") if os.path.exists(plist) else ""
m = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", txt)
ver = m.group(1) if m else "?"

# --- compare every watched module ------------------------------------------
print()
print("watching %d modules; bundle version %s" % (len(WATCHED), ver))
print()
fails = []
for name in WATCHED:
    rel = name.replace(".", "/") + ".py"
    src_path = os.path.join(ROOT, rel)
    if not os.path.exists(src_path):
        print("  SKIP  %-28s (no local %s)" % (name, rel))
        continue
    code = load_bundled(name)
    if code is None:
        print("  FAIL  %-28s not present in bundle" % name)
        fails.append(name)
        continue
    with open(src_path) as f:
        local = compile(f.read(), rel, "exec")
    s_bundled = structure_signature(code)
    s_local = structure_signature(local)
    if s_bundled == s_local:
        print("  OK    %-28s bytecode matches working tree" % name)
    else:
        print("  FAIL  %-28s STALE — bundled bytecode differs from %s" % (name, rel))
        print("          bundled %s" % s_bundled[:16])
        print("          local   %s" % s_local[:16])
        fails.append(name)

# --- the version must match the source of truth ----------------------------
init_path = os.path.join(ROOT, "game", "__init__.py")
with open(init_path) as f:
    m2 = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
expected = m2.group(1) if m2 else None
print()
print("source version: %s | bundle version: %s" % (expected, ver))
if expected is None or ver != expected:
    print("  FAIL bundle version does not match game/__init__.py")
    fails.append("version")

print()
if fails:
    print("APPCHECK_FAIL: %s" % "; ".join(fails))
    sys.exit(1)
print("APPCHECK_OK — bundle bytecode matches the working tree and version %s" % ver)
