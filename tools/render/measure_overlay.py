"""Measure what it costs to get a pygame UI surface onto the GPU each frame.

W03's premise in docs/CPP_RENDERER_MIGRATION.md is that Python's `gl*` calls in the UI have to be
replaced by a draw list and the text re-rasterized from an atlas inside C++. Before accepting that,
this measures the alternative the code already uses: `render/hud.py::_upload` turns the whole HUD
surface into RGBA bytes with `pygame.image.tostring` and hands it to `glTexImage2D` once per frame.

Numbers reported, per frame, on a 1280x800 surface with a realistic amount of HUD content drawn:

  full_teximage     tostring + glTexImage2D (what hud.py does today)
  full_subimage     tostring + glTexSubImage2D into an already-allocated texture
  dirty_subimage    tostring of one dirty rect + glTexSubImage2D

Synthetic by construction: the surface content is drawn here, not by a running match, so the
comparison is about transfer cost, not about whether the HUD is cheap to *draw*.

Run: .venv/bin/python tools/render/measure_overlay.py --width 1280 --height 800 --frames 240
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time

# No SDL_VIDEODRIVER=offscreen here: that driver cannot create a GL context on macOS
# ("Could not initialize OpenGL / GLES library"), and the transfer cost is what is measured.
import pygame
from OpenGL.GL import (
    GL_LINEAR,
    GL_RGBA,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_UNSIGNED_BYTE,
    glBindTexture,
    glFinish,
    glGenTextures,
    glTexImage2D,
    glTexParameteri,
    glTexSubImage2D,
    glViewport,
)


def build_surface(width: int, height: int) -> pygame.Surface:
    """A surface with enough content that the pixels are not all identical."""
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    font = pygame.font.SysFont("helvetica,arial", 18)
    # Panels and bars: the HUD is mostly filled rects with rounded corners.
    for i in range(14):
        rect = pygame.Rect(16, 16 + i * 54, 300, 46)
        pygame.draw.rect(surface, (17, 28, 38, 235), rect, border_radius=8)
        pygame.draw.rect(surface, (43, 57, 69, 255), rect, 1, border_radius=8)
        pygame.draw.rect(surface, (184, 220, 215, 255),
                         pygame.Rect(rect.x + 8, rect.y + 8, 120 + i * 9, 8), border_radius=3)
        label = font.render(f"FLEET COMMAND {i:02d}  ·  1,2{i}0/2,000", True, (229, 235, 236))
        surface.blit(label, (rect.x + 10, rect.y + 22))
    banner = font.render("STAR ARMADA  ·  OUTER ARMADA  ·  SECTOR 7", True, (229, 235, 236))
    surface.blit(banner, banner.get_rect(midtop=(width // 2, 8)))
    return surface


def ms(samples: list[float]) -> dict:
    return {
        "samples": len(samples),
        "median_ms": round(statistics.median(samples), 4),
        "p95_ms": round(sorted(samples)[max(0, int(len(samples) * 0.95) - 1)], 4),
        "max_ms": round(max(samples), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--out", default="")
    parser.add_argument("--driver", default=os.environ.get("SDL_VIDEODRIVER", ""),
                        help="SDL video driver; empty means the platform default")
    args = parser.parse_args()

    if args.driver:
        os.environ["SDL_VIDEODRIVER"] = args.driver
    pygame.init()
    pygame.display.set_mode((args.width, args.height), pygame.OPENGL | pygame.DOUBLEBUF)
    glViewport(0, 0, args.width, args.height)
    surface = build_surface(args.width, args.height)

    texture = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, args.width, args.height, 0,
                    GL_RGBA, GL_UNSIGNED_BYTE, None)
    glFinish()

    full, sub, dirty, encode = [], [], [], []
    dirty_rect = pygame.Rect(args.width // 3, args.height // 3, 320, 180)

    for frame in range(args.frames):
        # Change something each frame so no path can cheat by caching bytes.
        pygame.draw.rect(surface, (184, 220, 215, 255),
                         pygame.Rect(20, 20, 40 + (frame % 200), 10), border_radius=3)

        t0 = time.perf_counter()
        data = pygame.image.tostring(surface, "RGBA", False)
        t1 = time.perf_counter()
        encode.append((t1 - t0) * 1000.0)

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, args.width, args.height, 0,
                        GL_RGBA, GL_UNSIGNED_BYTE, data)
        glFinish()
        t2 = time.perf_counter()
        full.append((t2 - t0) * 1000.0)

        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, args.width, args.height,
                           GL_RGBA, GL_UNSIGNED_BYTE, data)
        glFinish()
        t3 = time.perf_counter()
        sub.append((t3 - t0) * 1000.0)

        part = surface.subsurface(dirty_rect)
        part_data = pygame.image.tostring(part, "RGBA", False)
        glTexSubImage2D(GL_TEXTURE_2D, 0, dirty_rect.x, args.height - dirty_rect.bottom,
                           dirty_rect.width, dirty_rect.height, GL_RGBA,
                           GL_UNSIGNED_BYTE, part_data)
        glFinish()
        t4 = time.perf_counter()
        dirty.append((t4 - t3) * 1000.0)

    receipt = {
        "tool": "measure_overlay",
        "synthetic": True,
        "surface": [args.width, args.height],
        "megapixels": round(args.width * args.height / 1e6, 3),
        "bytes_per_frame": args.width * args.height * 4,
        "encode_tostring": ms(encode),
        "full_teximage": ms(full),
        "full_subimage": ms(sub),
        "dirty_subimage": ms(dirty),
        "note": (
            "full_teximage is what render/hud.py::_upload does today; full_subimage reuses the "
            "allocation; dirty_subimage is one 320x180 rect. Timings include glFinish so the "
            "transfer is complete, which a real frame would overlap with the world pass."
        ),
    }
    print(json.dumps(receipt, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2) + "\n")
            print(f"wrote {args.out}")
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
