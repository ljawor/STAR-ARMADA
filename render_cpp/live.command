#!/bin/bash
# Double-click launcher for the W02/W03 window: the Python simulation publishes frames and a
# composed HUD into shared rings, the C++ viewer draws them. Camera only for now (W04 adds
# commands back into the simulation); Esc quits and stops the producer.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${STAR_ARMADA_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  printf 'Set STAR_ARMADA_PYTHON to a Python interpreter with the game dependencies.\n' >&2
  exit 1
fi
# The prebuilt-deps build dir is the one that can be configured without network access.
BUILD="${STAR_ARMADA_VIEWER_BUILD:-$ROOT/render_cpp/build-w02}"
[[ -d "$BUILD" ]] || BUILD="$ROOT/render_cpp/build"
if [[ ! -x "$BUILD/armada_viewer" ]]; then
  printf 'No viewer at %s/armada_viewer — build it first (cmake -S render_cpp -B %s).\n' \
    "$BUILD" "$BUILD" >&2
  exit 1
fi
BASE="${STAR_ARMADA_DEMO_DIR:-$BUILD/live-demo}"
mkdir -p "$BASE"
SNAP="$BASE/live.snap"
[[ -f "$SNAP" ]] || "$PYTHON" tools/render/dump_snapshot.py --units 600 --out "$SNAP"
# A fresh ring directory per launch: the producer truncates its rings when it starts, and a
# window that opens onto a half-created ring aborts with a short read.
DIR="$BASE/run-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$DIR"

producer=0
cleanup() {
  if [[ "$producer" != 0 ]]; then
    kill "$producer" 2>/dev/null || true
    wait "$producer" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$PYTHON" tools/render/stream_ring.py \
  --ring "$DIR/frames.bin" --seconds 7200 --hz 60 \
  --overlay-ring "$DIR/hud.bin" --overlay-slots 48 --overlay-keyframe 1.0 \
  --report "$DIR/producer.json" &
producer=$!

# Wait for the rings to carry a published frame, so the window opens on a complete HUD.
for _ in $(seq 1 160); do
  if [[ -s "$DIR/frames.bin" && -s "$DIR/hud.bin" && -s "$DIR/frames.bin.tables" ]]; then
    sleep 1.0   # let at least one slot finish being written before the reader maps it
    break
  fi
  if ! kill -0 "$producer" 2>/dev/null; then
    printf 'The producer exited before publishing; see %s.\n' "$DIR/producer.json" >&2
    exit 1
  fi
  sleep 0.25
done

"$BUILD/armada_viewer" --snapshot "$SNAP" --assets "$ROOT" \
  --ring "$DIR/frames.bin" --overlay-ring "$DIR/hud.bin" \
  --report "$DIR/viewer.json" "$@"
