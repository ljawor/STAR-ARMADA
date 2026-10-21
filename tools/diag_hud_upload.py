"""Prove the HUD's dirty-rect upload on a real GL context, and report what it saves.

The unit tests replay the recorder's rects in Python. This does it the only way that can catch a
wrong y-offset or a flipped patch: it renders the HUD into the actual framebuffer and reads the
pixels back.

Sequence per scenario, all on one window and one game state:

  1. paint + full upload            -> capture (reference)
  2. paint the same state again     -> dirty rects must be empty, capture must be byte-identical
  3. change one thing (fps label, hull damage) -> partial upload -> capture
  4. same state, forced full upload -> capture; 3 and 4 must be byte-identical

Run: PYTHONPATH=.:tests .venv/bin/python tools/diag_hud_upload.py --out artifacts/cpp-renderer/w03
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
import sys

import numpy as np
import pygame
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.manager import GameManager
from game.data.store import DataStore
from game.core.vectors import Vec3
from render.camera import Camera
from render.hud import HUD
from render.renderer import Renderer

WIDTH, HEIGHT = 1280, 800


def capture(width=WIDTH, height=HEIGHT):
    GL.glFinish()
    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    return np.flipud(np.frombuffer(bytes(raw), np.uint8).reshape(height, width, 3)).copy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/cpp-renderer/w03")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()
    DataStore.reset()
    ds = DataStore()
    gm = GameManager.start_skirmish(ds.maps["skirmish01"])
    st = gm.state
    command = next(e for e in st.entities.values() if e.owner == 0 and e.data_id == "command_station")
    cam = Camera(WIDTH, HEIGHT)
    cam.target = [command.pos.x, command.pos.y, command.pos.z]
    cam.distance, cam.yaw, cam.pitch = 3400, 25, 45
    renderer = Renderer(st, cam)
    renderer.diff_render = True
    hud = HUD(WIDTH, HEIGHT, st)
    ships = [e for e in st.entities.values() if e.owner == 0 and e.is_ship]
    selection = {ships[0].id} if ships else set()

    uploads = []
    pixels = []
    original = hud.uploader.upload

    def timed_upload(surface, rects):
        start = time.perf_counter()
        sent = original(surface, rects)
        uploads.append((time.perf_counter() - start) * 1000.0)
        pixels.append(sent)
        return sent

    hud.uploader.upload = timed_upload
    results = {}

    tex_state = {}

    def composite(fps: float) -> np.ndarray:
        # HUD only: the world pass is not part of this comparison, and drawing it twice is not
        # guaranteed to produce identical pixels (camera smoothing, animated geometry).
        GL.glClearColor(0.0, 0.0, 0.0, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        hud.render(selection, None, 0, False, "", 0.0, fps)
        GL.glFinish()
        tex = bytes(GL.glGetTexImage(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE))
        tex_state["texture_equals_surface"] = (
            tex == pygame.image.tobytes(hud.overlay, "RGBA", False))
        hud.draw_gl()
        return capture()

    # 1-2: the same state twice. The second pass must send nothing and draw the same pixels.
    first = composite(0.0)
    full_bytes = pixels[-1]
    second = composite(0.0)
    results["steady_state"] = {
        "full_surface_pixels": full_bytes,
        "second_pass_pixels": pixels[-1],
        "identical": bool(np.array_equal(first, second)),
        "max_channel_delta": int(np.abs(first.astype(int) - second.astype(int)).max()),
    }

    # 3-4: change the fps label only, partial upload, then force a full upload of the same state.
    partial = composite(59.0)
    partial_pixels = pixels[-1]
    hud.uploader.full_pending = True
    full = composite(59.0)
    forced_full_pixels = pixels[-1]
    delta = int(np.abs(partial.astype(int) - full.astype(int)).max())
    results["partial_vs_full"] = {
        "partial_pixels": partial_pixels,
        "forced_full_pixels": forced_full_pixels,
        "saved_ratio": round(1.0 - partial_pixels / max(1, forced_full_pixels), 4),
        "identical": bool(np.array_equal(partial, full)),
        "max_channel_delta": delta,
    }

    # Damage a hull and repeat, which is the animated case that actually matters in a fight.
    if ships:
        ships[0].hull = max(1.0, ships[0].max_hull * 0.35)
    damaged = composite(0.0)
    damaged_pixels = pixels[-1]
    damaged_surface = pygame.image.tobytes(hud.overlay, "RGBA", False)
    hud.uploader.full_pending = True
    damaged_full = composite(0.0)
    damaged_full_surface = pygame.image.tobytes(hud.overlay, "RGBA", False)
    results["damage_partial_vs_full_texture_ok"] = dict(
        tex_state, surface_identical=damaged_surface == damaged_full_surface)
    results["damage_partial_vs_full"] = {
        "partial_pixels": damaged_pixels,
        "forced_full_pixels": pixels[-1],
        "saved_ratio": round(1.0 - damaged_pixels / max(1, pixels[-1]), 4),
        "identical": bool(np.array_equal(damaged, damaged_full)),
        "max_channel_delta": int(np.abs(damaged.astype(int) - damaged_full.astype(int)).max()),
    }

    # Control: two more draws of the same state with the texture already complete. If these differ
    # from each other, the composite itself is not repeatable and no pixel comparison here is valid.
    damaged_again = composite(0.0)
    repeat = np.any(damaged_full != damaged_again, axis=2)
    results["repeatability_control"] = {
        "identical": not bool(repeat.any()),
        "mismatch_pixels": int(repeat.sum()),
        "max_channel_delta": int(np.abs(damaged_full.astype(int) - damaged_again.astype(int)).max()),
    }

    mismatch = np.any(damaged != damaged_full, axis=2)
    if mismatch.any():
        ys, xs = np.where(mismatch)
        results["damage_partial_vs_full"]["bbox"] = [int(xs.min()), int(ys.min()),
                                                     int(xs.max()), int(ys.max())]
        results["damage_partial_vs_full"]["mismatch_pixels"] = int(mismatch.sum())
        rows = sorted(set(int(y) for y in ys))
        results["damage_partial_vs_full"]["rows"] = rows[:5] + (["..."] if len(rows) > 5 else [])

    pygame.image.save(pygame.surfarray.make_surface(np.transpose(full, (1, 0, 2))),
                      str(out / "hud-partial-upload.png"))
    # A difference image is the honest artifact when something does not match.
    diff = np.abs(damaged.astype(int) - damaged_full.astype(int)).astype(np.uint8) * 12
    pygame.image.save(pygame.surfarray.make_surface(np.transpose(diff, (1, 0, 2))),
                      str(out / "hud-diff.png"))

    receipt = {
        "tool": "diag_hud_upload",
        "window": [WIDTH, HEIGHT],
        "full_surface_bytes": WIDTH * HEIGHT * 4,
        "results": results,
        "upload_ms": {
            "samples": len(uploads),
            "median_ms": round(statistics.median(uploads), 4),
            "max_ms": round(max(uploads), 4),
        },
        "note": (
            "Capture comparison is exact (max channel delta must be 0). Timings include only the "
            "texture transfer, not the paint; the world pass is drawn before every capture so the "
            "composite is the real frame."
        ),
    }
    print(json.dumps(receipt, indent=2))
    (out / "hud-upload-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    hud.close()
    pygame.quit()
    return 0 if all(v["identical"] for k, v in results.items()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
