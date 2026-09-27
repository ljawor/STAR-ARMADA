#!/usr/bin/env bash
# Build the STAR ARMADA .app bundle and wrap it in a DMG (macOS).
# Usage: scripts/build_mac.sh [output.dmg]
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""

# prefer the project venv, fall back to python3
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python3"; fi

# ensure build tooling in the venv (PEP 668: never system pip)
if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
  if [ "$PY" = ".venv/bin/python" ]; then
    ./.venv/bin/pip install pyinstaller
  else
    python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt pyinstaller
    PY=".venv/bin/python"
  fi
fi

"$PY" -m PyInstaller star_armada.spec --noconfirm

APP="dist/STAR ARMADA.app"
[ -d "$APP" ] || { echo "app bundle missing: $APP" >&2; exit 1; }

# ad-hoc codesign so Gatekeeper doesn't hard-fail local runs
codesign --force --deep --sign - "$APP" 2>/dev/null || true

OUT="${1:-dist/STAR-ARMADA-0.2.0-mac.dmg}"
mkdir -p dist/dmg_staging
rm -rf dist/dmg_staging/*
cp -R "$APP" dist/dmg_staging/
ln -s /Applications dist/dmg_staging/Applications
hdiutil create -volname "STAR ARMADA" -srcfolder dist/dmg_staging \
  -ov -format UDZO "$OUT"
rm -rf dist/dmg_staging
echo "DMG written: $OUT"