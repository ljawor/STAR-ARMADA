"""Probe: is the FLASH (t<0.21s) a smooth disc, and is the shock a clean ring?

The main shape probe samples t>=0.02 but its "at t=0.16" verdict is dominated by
the big fireball, and it reported roughness ~0.16 for the whole composite. That
hid the fact that the FLASH layer alone was still a perfectly smooth _draw_glow
disc — the brightest thing on screen, and what the user actually saw.

So measure each layer in isolation, by brightness band:
  - flash:  the saturated core, lum > 0.85
  - mid:    lum 0.5..0.85
  - shock:  the faint outer ring, lum 0.03..0.5 (beyond the fire)

Run: PYTHONPATH=. ./.venv/bin/python tools/probe_blast_layers.py [outdir]
"""
from __future__ import annotations

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
cam.yaw, cam.pitch, cam.distance = 0.0, 26.0, 1200.0
renderer = Renderer(st, cam)
renderer.time = 5.0
renderer.diff_render = True


def grab():
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def save(img, path):
    pygame.image.save(
        pygame.image.frombuffer((img * 255.0).astype(np.uint8).tobytes(),
                                (W, H), "RGB"), path)


st.effects = []
renderer.draw(1 / 30.0, set())
BASE = grab()


def band_shape(img, lo, hi):
    """Roughness + fill of the pixels whose brightness is in [lo, hi)."""
    lum = img.max(axis=2)
    m = (lum >= lo) & (lum < hi)
    n = int(m.sum())
    if n < 60:
        return None
    ys, xs = np.nonzero(m)
    cy, cx = np.median(ys), np.median(xs)
    rad = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    rmax = float(np.percentile(rad, 99.0))
    k = rad <= rmax
    cy, cx = np.median(ys[k]), np.median(xs[k])
    rad = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    k = rad <= rmax
    rr, xx, yy = rad[k], xs[k], ys[k]
    ang = np.arctan2(yy - cy, xx - cx)
    bins = np.linspace(-np.pi, np.pi, 73)
    idx = np.digitize(ang, bins)
    outer = np.array([rr[idx == b].max() for b in range(1, 73)
                      if (idx == b).any()])
    rough = float(outer.std() / outer.mean()) if outer.size else 0.0
    area = np.pi * rmax * rmax
    return {"px": n, "rmax": rmax, "rough": rough,
            "fill": int(k.sum()) / area if area else 0.0,
            "sat": float((lum[m] >= 0.99).mean())}


print(f"{'t':>5} | {'FLASH (lum>0.85)':>34} | {'SHOCK outer (0.03-0.5)':>34}")
print(f"{'':>5} | {'px':>6} {'rmax':>5} {'rough':>6} {'sat%':>5} | "
      f"{'px':>6} {'rmax':>5} {'rough':>6} {'fill':>5}")
worst_flash = 0.0
for t in (0.02, 0.06, 0.10, 0.14, 0.18, 0.20, 0.30, 0.45, 0.65, 0.90):
    st.effects = [{"kind": "explosion", "pos": [0.0, 0.0, 0.0], "t": t,
                   "size": 85.0, "seed": 3}]
    renderer.draw(1 / 30.0, set())
    img = grab()
    save(img, os.path.join(outdir, f"layers_t{t:.2f}.png"))
    f = band_shape(img, 0.85, 1.01)
    s = band_shape(img, 0.03, 0.50)
    fs = (f"{f['px']:6d} {f['rmax']:5.0f} {f['rough']:6.3f} {f['sat'] * 100:5.1f}"
          if f else f"{'-':>6} {'-':>5} {'-':>6} {'-':>5}")
    ss = (f"{s['px']:6d} {s['rmax']:5.0f} {s['rough']:6.3f} {s['fill']:5.2f}"
          if s else f"{'-':>6} {'-':>5} {'-':>6} {'-':>5}")
    print(f"{t:5.2f} | {fs} | {ss}")
    if f and t < 0.21:
        worst_flash = max(worst_flash, f["rough"])

print(f"\nVERDICT: flash silhouette roughness while it is on screen "
      f"= {worst_flash:.3f}")
print("  a smooth _draw_glow disc gives ~0.01; irregular geometry gives >0.10")
print(f"shots -> {outdir}/layers_t*.png")
