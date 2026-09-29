"""Probe: does the blast read as FIRE, or as a flat drawn shape?

The earlier silhouette probe (tools/probe_blast_shape.py) measured the RIM of
the bright region and reported "fixed" while the part the eye lands on — a
saturated flat white core — was untouched. An outline test cannot see a flat
interior. This probe measures the INTERIOR instead:

  sat%     fraction of bright pixels pinned at >=0.99 in every channel.
           A blown-out additive stack sits near 85%; real fire is well under.
  colours  distinct colours in the bright region. A flat billboard has ~1
           (the user's screenshot: 3214 px of exactly (253,250,217)).
  orange%  saturated warm fire pixels.
  flat%    share of the single most common colour.

Usage: PYTHONPATH=. ./.venv/bin/python tools/probe_blast_fill.py [outdir]
"""
from __future__ import annotations

import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                   # noqa: E402
import pygame                                        # noqa: E402
from OpenGL.GL import (glFinish, glReadPixels,       # noqa: E402
                       GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves")
os.makedirs(outdir, exist_ok=True)

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.manager import GameManager            # noqa: E402
from game.data.store import DataStore                # noqa: E402
from render.camera import Camera                     # noqa: E402
from render.renderer import Renderer                 # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
st.entities = {}
cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 0.0, 26.0, 1600.0
renderer = Renderer(st, cam)
renderer.time = 5.0
if hasattr(renderer, "diff_render"):
    renderer.diff_render = True


def grab():
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    im = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    im = pygame.transform.flip(im, False, True)
    return (np.frombuffer(pygame.image.tobytes(im, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def save(img, path):
    pygame.image.save(pygame.image.frombuffer(
        (img * 255).astype(np.uint8).tobytes(), (W, H), "RGB"), path)


st.effects = []
renderer.draw(1 / 30.0, set())

print(f"{'t':>5} | {'bright':>7} {'colours':>7} {'sat%':>6} {'orange%':>8} "
      f"{'flat%':>6}")
worst_sat = 0.0
for t in (0.04, 0.08, 0.12, 0.18, 0.28, 0.45, 0.70, 1.00):
    st.effects = [{"kind": "explosion", "pos": [0.0, 0.0, 0.0], "t": t,
                   "size": 85.0, "seed": 3}]
    renderer.draw(1 / 30.0, set())
    img = grab()
    save(img, os.path.join(outdir, f"fill_t{t:.2f}.png"))
    a = (img * 255).astype(np.uint8)
    lum = img.max(axis=2)
    bright = lum > 0.45
    n = int(bright.sum())
    if n < 40:
        print(f"{t:5.2f} | {n:7d}        -      -        -       -")
        continue
    cnt = collections.Counter(map(tuple, a[bright].tolist()))
    top_share = cnt.most_common(1)[0][1] / n
    rr, gg, bb = img[..., 0], img[..., 1], img[..., 2]
    orange = ((rr > 0.55) & (rr - gg > 0.22) & (gg - bb > 0.10) & bright)
    sat = float((lum[bright] > 0.99).mean()) * 100
    print(f"{t:5.2f} | {n:7d} {len(cnt):7d} {sat:5.1f}% "
          f"{orange.sum() / n * 100:7.1f}% {top_share * 100:5.1f}%")
    if t < 0.20:
        worst_sat = max(worst_sat, sat)

print(f"\nVERDICT: peak saturated-flat share while the flash is on screen "
      f"= {worst_sat:.1f}%")
print("  a blown-out additive stack sits near 85%; the user's screenshot "
      "showed 88% and 3214 px of ONE colour.")
print("  real fire: sat% well under 60, hundreds of distinct colours, "
      "flat% under 20.")
print(f"shots -> {outdir}/fill_t*.png")
