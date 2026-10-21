#!/bin/bash
# Optional local-tool launcher; never changes the game's renderer preference.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${STAR_ARMADA_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  COMMON="$(git rev-parse --path-format=absolute --git-common-dir)"
  PYTHON="$(dirname "$COMMON")/.venv/bin/python"
fi
if [[ ! -x "$PYTHON" ]]; then
  printf 'Set STAR_ARMADA_PYTHON to a Python interpreter with the game dependencies.\n' >&2
  exit 1
fi
BUILD="${STAR_ARMADA_VIEWER_BUILD:-$ROOT/render_cpp/build}"
if [[ ! -x "$BUILD/armada_viewer" ]]; then
  cmake -S "$ROOT/render_cpp" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD" --target armada_viewer --parallel 4
fi
"$PYTHON" tools/render/dump_snapshot.py --units 600 --out "$BUILD/fleet.snap"
exec "$BUILD/armada_viewer" --snapshot "$BUILD/fleet.snap" --assets "$ROOT/assets" "$@"
