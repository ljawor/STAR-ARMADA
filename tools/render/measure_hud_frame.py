"""Price the HUD frame: full-surface upload (what it did before) versus dirty-rect upload.

Both modes paint the same HUD from the same state; only the transfer differs. The paint is timed
with the transfer so the number is the whole per-frame cost of getting the overlay to the GPU,
which is the thing that changed.

  full   painter.recorder = None and a forced full upload every frame  (the old behaviour)
  dirty  the recorder decides which rects changed                       (the new behaviour)

Alternating runs in one process, so thermal or scheduler drift cannot favour one mode.

Run: PYTHONPATH=.:tests .venv/bin/python tools/render/measure_hud_frame.py --out artifacts/cpp-renderer/w03
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
import sys

import pygame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.manager import GameManager
from game.data.store import DataStore
from render.hud import HUD
from render.overlay_upload import painter

WIDTH, HEIGHT = 1280, 800


def timed(hud, frames, fps_values, mode):
    samples = []
    pixels = []
    selection = set()
    for index, fps in enumerate(fps_values):
        if mode == "full":
            painter.recorder = None
            hud.uploader.full_pending = True
        else:
            painter.recorder = hud.recorder
        start = time.perf_counter()
        hud.render(selection, None, 0, False, "", 0.0, fps)
        samples.append((time.perf_counter() - start) * 1000.0)
        pixels.append(hud.uploader.pixels)
        hud.uploader.pixels = 0
        if index % 8 == 0:
            selection = set() if selection else {
                e.id for e in hud.state.entities.values() if e.owner == 0 and e.is_ship}
    return samples, pixels


def stats(values):
    return {
        "samples": len(values),
        "median": round(statistics.median(values), 4),
        "p95": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", default="artifacts/cpp-renderer/w03")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()
    DataStore.reset()
    gm = GameManager.start_skirmish(DataStore().maps["skirmish01"])
    hud = HUD(WIDTH, HEIGHT, gm.state)

    # fps text that changes every frame is the realistic worst case for a HUD: it guarantees that at
    # least one label differs, so the dirty path cannot win by doing nothing at all.
    fps_values = [float(i % 6) for i in range(args.frames)]

    results = {"full": [], "dirty": []}
    pixels = {"full": [], "dirty": []}
    for _ in range(args.rounds):
        for mode in ("full", "dirty"):
            samples, sent = timed(hud, args.frames, fps_values, mode)
            results[mode].extend(samples)
            pixels[mode].extend(sent)

    painter.recorder = hud.recorder
    receipt = {
        "tool": "measure_hud_frame",
        "window": [WIDTH, HEIGHT],
        "frames_per_round": args.frames,
        "rounds": args.rounds,
        "full_surface_pixels": WIDTH * HEIGHT,
        "modes": {
            mode: dict(stats(results[mode]),
                       median_pixels_uploaded=pixels[mode][len(pixels[mode]) // 2],
                       pixels_per_frame_median=int(statistics.median(
                           [p for p in pixels[mode] if p <= WIDTH * HEIGHT])))
            for mode in ("full", "dirty")
        },
        "note": (
            "Timing is hud.render() as a whole: paint into the surface, upload, rebind. It includes "
            "the recorder's per-op bookkeeping, which is why this is the number that matters and the "
            "transfer table in the W03 document is not. The HUD state is a real skirmish; the fps "
            "label changes every frame, so the dirty path still has work to do."
        ),
    }
    full = receipt["modes"]["full"]["median"]
    dirty = receipt["modes"]["dirty"]["median"]
    receipt["saved_ms"] = round(full - dirty, 4)
    receipt["saved_ratio"] = round(1.0 - dirty / full, 4)
    print(json.dumps(receipt, indent=2))
    (out / "hud-frame-cost.json").write_text(json.dumps(receipt, indent=2) + "\n")
    hud.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
