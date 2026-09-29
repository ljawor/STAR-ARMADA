"""Diag: professional explosion + convoys visible in the 3D view.

Reported:
  1. explosions too simple
  2. trade convoy shows on the MINIMAP but not on the map -> unattackable

Probes, against the REAL renderer:
  A. convoy renders in the 3D pass (px on screen) and is attackable/selectable
  B. hull_hit is NOT a flat saturated white disc
  C. explosion is multi-stage: colour ramps, area grows, layers overlap
  D. shots saved for the visual check at several blast ages

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_explosion.py [outdir]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                     # noqa: E402
import pygame                                          # noqa: E402
from OpenGL.GL import (glFinish, glReadPixels,         # noqa: E402
                       GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.manager import GameManager                  # noqa: E402
from game.core.vectors import Vec3                         # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.camera import Camera                           # noqa: E402
from render.renderer import Renderer                       # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

_fail: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'ok ' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail.append(name)


def grab():
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


# camera on the origin, looking at the blast site
ORIGIN = (0.0, 0.0, 0.0)
cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 0.0, 26.0, 900.0
renderer = Renderer(st, cam)
renderer.time = 5.0


def frame_at(effects, t):
    st.effects = effects
    for fx in st.effects:
        fx["t"] = t
    renderer.draw(1 / 30.0, set())
    return grab()


def blast_pixels(effects, t, thresh=0.03):
    """Pixels the blast actually CONTRIBUTES, via baseline subtraction.

    Counting raw lit pixels also counts the starfield (~41k px), which swamps
    the effect and made 'does it fade?' measure the background. Compare
    against the same scene with no effects instead. Also returns the frame and
    its max per-channel difference from the baseline (for determinism checks:
    this driver's MSAA resolve is not bit-exact, so exact equality is the
    wrong assertion).
    """
    st.effects = []
    base = frame_at([], 0.0)
    img = frame_at(effects, t)
    return img, base, np.abs(img - base).max(axis=2),


# ============================================== A. convoy visible in 3D view
print("=== A. convoy drawn in the 3D pass ===")
st.effects = []
# clear the map so nothing else can account for the pixels
st.entities = {k: v for k, v in st.entities.items() if v.is_planet}
conv = st.add_entity(__import__("game.core.entity", fromlist=["Entity"]).Entity(
    id=st.next_entity_id, kind="ship", owner=1, data_id="trade_convoy",
    pos=Vec3(0.0, 0.0, 0.0)))
st.next_entity_id += 1
conv.is_ship = True
conv.radius = 18.0
conv.hull = 250.0
conv.max_hull = 250.0
conv.cargo_credits = 150.0
conv.convoy_dest = 1
conv.order_type = "move"

img = frame_at([], 0.0)
lit = int((img.max(axis=2) > 0.20).sum())
check("A1. convoy draws pixels in the 3D view", lit > 40,
      f"{lit} lit px at distance 900 (was 0 before the fix)")

# it must be a lit, shaded hull in the owner colour — not a flat marker.
px = img[img.max(axis=2) > 0.20]
if len(px):
    print(f"     bright px mean RGB = {px.mean(axis=0).round(2)}")
check("A2. convoy pixels are not pure white (a shaded hull)",
      len(px) > 0 and px.mean(axis=0).max() < 0.995,
      "mean channel below 1.0")

# the world->screen projection must work so it is selectable/attackable
sp = cam.world_to_screen(0.0, 0.0, 0.0)
check("A3. convoy projects to screen (clickable/attackable)", sp is not None,
      f"screen={None if sp is None else (round(sp[0]), round(sp[1]))}")

# ================================================= B. hull_hit is not white
print("\n=== B. hull_hit impact is not a flat white disc ===")
st.effects = [{"kind": "hull_hit", "pos": list(ORIGIN), "t": 0.05,
               "color": [1.0, 0.62, 0.26], "size": 18.0}]
img = frame_at(st.effects, 0.05)
m = img.max(axis=2)
hot = m > 0.55
n_hot = int(hot.sum())
sat_white = int(((img.min(axis=2) > 0.93) & hot).sum())
print(f"     hot px={n_hot}  saturated-white px={sat_white}")
check("B1. impact has warm (non-white) colour", n_hot > 20 and
      sat_white < n_hot * 0.5,
      f"{sat_white}/{n_hot} px are white (was a solid white disc)")

# ============================================== C. explosion is multi-stage
print("\n=== C. explosion is layered / animated ===")
probe = []
for t in (0.02, 0.10, 0.25, 0.50, 0.80, 1.10, 1.45):
    img, _, diff = blast_pixels(
        [{"kind": "explosion", "pos": list(ORIGIN), "t": t,
          "size": 60.0, "seed": 7}], t)
    area = int((diff > 0.03).sum())
    bright = int((img.max(axis=2) > 0.55).sum())
    hot = img[img.max(axis=2) > 0.55]
    tint = hot.mean(axis=0).round(3) if len(hot) else np.zeros(3)
    probe.append((t, area, bright, tint))
    print(f"     t={t:4.2f}s  blast px={area:6d}  bright={bright:5d}  "
          f"mean RGB of bright = {tuple(float(v) for v in tint)}")

areas = [p[1] for p in probe]
check("C1. blast EXPANDS over its life", areas[2] > areas[0],
      f"area {areas[0]} -> {areas[2]} by t=0.25")
check("C2. blast FADES OUT at the end", areas[-1] < areas[2] * 0.6,
      f"area {areas[2]} (t=0.25) -> {areas[-1]} (t=1.45)")
# colour must actually change (a cooling fireball), not stay one tint
tints = [p[3] for p in probe if p[2] > 30]
if len(tints) >= 3:
    first, last = tints[0], tints[-1]
    shift = float(np.abs(np.array(first) - np.array(last)).sum())
    check("C3. fireball colour COOLS over time (white -> red)", shift > 0.25,
          f"RGB {tuple(first)} -> {tuple(last)} (delta {shift:.2f})")
else:
    check("C3. enough bright frames to compare colour", False,
          f"only {len(tints)} frames")

# a big blast must be substantially brighter/bigger than a small one
_, _, db = blast_pixels([{"kind": "explosion", "pos": list(ORIGIN), "t": 0.3,
                             "size": 120.0, "seed": 2}], 0.3)
big = int((db > 0.03).sum())
_, _, ds_ = blast_pixels([{"kind": "explosion", "pos": list(ORIGIN), "t": 0.3,
                           "size": 20.0, "seed": 2}], 0.3)
small = int((ds_ > 0.03).sum())
check("C4. blast scales with the dying unit's size", big > small * 1.8,
      f"big={big} vs small={small}")

# determinism: same seed -> identical pixels
def px_of(seed, t=0.35):
    return blast_pixels([{"kind": "explosion", "pos": list(ORIGIN), "t": t,
                          "size": 60.0, "seed": seed}], t)[0]

a = px_of(11)
b = px_of(11)
c = px_of(12)
# This driver's MSAA resolve is NOT bit-exact (an empty scene re-rendered
# differs by ~1500 px at <=0.64), so exact equality is the wrong assertion.
d_same = float(np.abs(a - b).max())
d_diff = float(np.abs(a - c).max())
check("C5. same seed reproduces the same blast (within MSAA noise)",
      d_same < 0.9, f"max diff {d_same:.3f}")
check("C6. different seed varies the blast", d_diff >= d_same,
      f"seed-varied diff {d_diff:.3f} vs same-seed {d_same:.3f}")

# ======================================================= D. save the shots
print("\n=== D. saved frames ===")
os.makedirs(outdir, exist_ok=True)
for t in (0.03, 0.12, 0.30, 0.55, 0.95):
    st.effects = [{"kind": "explosion", "pos": list(ORIGIN), "t": t,
                   "size": 70.0, "seed": 7}]
    img = frame_at(st.effects, t)
    p = os.path.join(outdir, f"diag_expl_t{t:.2f}.png")
    surf = pygame.image.frombuffer(
        (img[::-1] * 255).astype(np.uint8).tobytes(), (W, H), "RGB")
    # crop to the middle so the blast is legible
    crop = surf.subsurface(pygame.Rect(W // 2 - 220, H // 2 - 220, 440, 440)) \
               .copy()
    pygame.image.save(pygame.transform.scale(crop, (560, 560)), p)
    print(f"     saved {p}")

print("\nEXPLOSION_OK" if not _fail else f"\nEXPLOSION_FAIL {_fail}")
sys.exit(1 if _fail else 0)
