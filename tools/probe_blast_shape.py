"""Probe: measure the blast's SHAPE, not just its pixel count.

The user reports the explosion "still looks very simple". A pixel count cannot
tell a turbulent fireball from a stack of flat discs, so measure the geometry:

  sat%      fraction of blast px clipped at >=0.99 -> a flat white plate
  plateau%  fraction sitting within 1% of the modal brightness
  edge      brightness at the rim / brightness at the core. A hard-edged disc
            holds core brightness out to the rim (~1.0); a real fireball falls
            off smoothly (<< 1).
  fill      blast px / area of the bounding circle. A flat disc = ~1.0; a
            lumpy cloud sits well below.
  rough     std/mean of the boundary radius over 72 angles. A perfect circle
            = 0.0.
  radial    mean brightness per concentric band, core -> rim.

Two probe bugs fixed here, both of which made earlier runs meaningless:
  1. frames were saved as raw 0..1 floats via image.frombuffer -> every PNG
     came out black (the array must be scaled by 255 first);
  2. renderer.time advances every frame and drives planet spin / starfield
     drift, so EVERY background pixel differed between the two frames and the
     baseline-subtraction mask covered the whole screen. Fixed by the
     renderer's `diff_render` flag, which freezes the animation clock.

Run: PYTHONPATH=. ./.venv/bin/python tools/probe_blast_shape.py [outdir]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import math                                          # noqa: E402
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
# planets spin with time; even frozen, the star at the scene origin would sit
# under the blast, so clear the scenery and keep a clean starfield backdrop.
st.entities = {}

cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 0.0, 26.0, 1200.0
renderer = Renderer(st, cam)
renderer.time = 5.0
renderer.diff_render = True          # freeze the animation clock


def grab():
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def save(img, path):
    """Scale to 0..255 before writing — raw floats in frombuffer = black PNG."""
    pygame.image.save(
        pygame.image.frombuffer((img * 255.0).astype(np.uint8).tobytes(),
                                (W, H), "RGB"), path)


st.effects = []
renderer.draw(1 / 30.0, set())
BASE = grab()


def analyse(t, size=40.0, seed=7, save_shot=True, thresh=0.03):
    st.effects = [{"kind": "explosion", "pos": [0.0, 0.0, 0.0],
                   "t": t, "size": size, "seed": seed}]
    renderer.draw(1 / 30.0, set())
    img = grab()
    diff = np.abs(img - BASE).max(axis=2)
    mask = diff > thresh
    n = int(mask.sum())
    if n < 30:
        return None
    ys, xs = np.nonzero(mask)
    # robust centre/radius: a few stray embers would otherwise blow up rmax
    # and drag the centre off, making every shape metric meaningless
    cx, cy = np.median(xs), np.median(ys)
    r = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    rmax = float(np.percentile(r, 99.0))
    keep = r <= rmax
    cx, cy = float(np.median(xs[keep])), float(np.median(ys[keep]))
    r = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    keep = r <= rmax
    r_core = r[keep]
    lum = img[ys[keep], xs[keep]].max(axis=1)
    lum_all = img[ys, xs].max(axis=1)

    sat = float((lum >= 0.99).mean())

    hist, edges = np.histogram(lum, bins=40, range=(0, 1))
    modal = edges[int(np.argmax(hist))]
    plateau = float(((lum >= modal - 0.01) & (lum <= modal + 0.01)).mean())

    nb = 12
    prof = []
    for i in range(nb):
        lo, hi = rmax * i / nb, rmax * (i + 1) / nb
        band = (r_core >= lo) & (r_core < hi) if i < nb - 1 else (r_core >= lo)
        prof.append(float(lum[band].mean()) if band.any() else 0.0)

    inner = lum[r_core < rmax * 0.35]
    outer = lum[r_core > rmax * 0.75]
    edge = (float(outer.mean()) / float(inner.mean())
            if inner.size and outer.size and inner.mean() > 0 else 0.0)

    area = math.pi * rmax * rmax
    fill = int(keep.sum()) / area if area > 0 else 0.0

    ang = np.arctan2(ys[keep] - cy, xs[keep] - cx)
    bins = np.linspace(-math.pi, math.pi, 73)
    idx = np.digitize(ang, bins)
    radii = np.array([r_core[idx == b].max() for b in range(1, 73)
                      if (idx == b).any()], dtype=np.float32)
    rough = float(radii.std() / radii.mean()) if radii.size and radii.mean() else 0.0

    if save_shot:
        save(img, os.path.join(outdir, f"blast_t{t:.2f}.png"))

    return {"px": n, "sat": sat, "plateau": plateau, "edge": edge,
            "fill": float(fill), "rough": rough, "rmax": rmax, "prof": prof,
            "lum": lum_all}


print(f"{'t':>5} {'px':>7} {'sat%':>6} {'plateau%':>9} {'edge':>6} "
      f"{'fill':>6} {'rough':>6} {'rmax':>6}  brightness(max/median)")
rows = {}
for t in (0.02, 0.08, 0.16, 0.30, 0.45, 0.65, 0.90, 1.20, 1.45):
    a = analyse(t)
    if a is None:
        print(f"{t:5.2f}  (nothing drawn)")
        continue
    rows[t] = a
    print(f"{t:5.2f} {a['px']:7d} {a['sat'] * 100:6.1f} {a['plateau'] * 100:9.1f} "
          f"{a['edge']:6.2f} {a['fill']:6.2f} {a['rough']:6.2f} {a['rmax']:6.0f}  "
          f"{a['lum'].max():.2f}/{np.median(a['lum']):.2f}")

mid = rows.get(0.16) or rows.get(sorted(rows)[len(rows) // 2])
if mid:
    print(f"\nradial profile (core -> rim): "
          + " ".join(f"{v:.2f}" for v in mid["prof"]))
    print("\nVERDICT:")
    print(f"  flat white plate? {'YES' if mid['sat'] > 0.2 else 'no'}"
          f"  ({mid['sat'] * 100:.0f}% of blast px clipped at max)")
    print(f"  holds to the rim? {'YES - hard disc' if mid['edge'] > 0.75 else 'no'}"
          f"  (rim/core {mid['edge']:.2f})")
    print(f"  a filled circle?  {'YES' if mid['fill'] > 0.80 else 'no'}"
          f"  (fill {mid['fill']:.2f} of bounding circle)")
    print(f"  silhouette rough? {'YES - lumpy' if mid['rough'] > 0.18 else 'NO - a clean circle'}"
          f"  ({mid['rough']:.2f})")
print(f"\nshots -> {outdir}/blast_t*.png")
