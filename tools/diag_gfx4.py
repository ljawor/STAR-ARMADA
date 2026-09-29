"""Diag: graphics pass A combat effects — beams, bolts, explosions.

Probes that the effect upgrades actually render:
  BEAM       a beam has real thickness (not a 1px GL_LINES scratch)
  PROJECTILE a bolt renders a bright additive core + halo
  EXPLOSION  a detonation produces a hot core, ring and ember sparks
  SPARKS     ember pixels exist away from the blast centre
  No GL errors.

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_gfx4.py [out.png]
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                    # noqa: E402
import pygame                                         # noqa: E402
from OpenGL.GL import (glClear, glClearColor, glFinish, glGetError,  # noqa: E402
                       glReadPixels, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
                       GL_NO_ERROR, GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves", "diag_gfx4.png")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.entity import Entity                        # noqa: E402
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


def grab() -> np.ndarray:
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def render(effects, projectiles=(), dist=1400.0, yaw=0.0, pitch=18.0,
           save=None):
    st.entities.clear()
    st.effects = list(effects)
    st.projectiles.clear()
    for i, p in enumerate(projectiles):
        st.projectiles[i] = p
    cam = Camera(W, H)
    cam.target = [0.0, 0.0, 0.0]
    cam.yaw, cam.pitch, cam.distance = yaw, pitch, dist
    r = Renderer(st, cam)
    r.time = 3.0
    glClearColor(0, 0, 0, 1)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    r.draw(1 / 30, set())
    err = glGetError()
    if err != GL_NO_ERROR:
        _fail.append(f"GL error 0x{err:x}")
    arr = grab()
    if save:
        img = pygame.image.frombuffer(
            bytes(np.flipud(arr * 255).astype(np.uint8).tobytes()), (W, H), "RGB")
        pygame.image.save(img, save)
    return arr


class Proj:
    def __init__(self, x, y, z, color):
        self.pos = Vec3(x, y, z)
        self.color = color


# --------------------------------------------------------------- 1. BEAM
# a beam across the view; measure its on-screen thickness
beam_fx = [{"kind": "beam", "t": 0.02, "pos": (-600.0, 0.0, 0.0),
            "target_pos": (600.0, 0.0, 0.0), "color": [0.5, 0.85, 1.0]}]
arr = render(beam_fx, dist=1500.0, save=os.path.join(ROOT, "saves", "diag_gfx4_beam.png"))
col = arr.max(axis=2).max(axis=1)             # brightest per screen row
rows_hot = int((col > 0.25).sum())
print(f"[1] beam rows with signal: {rows_hot} (a 1px GL_LINES would be ~1-3)")
if rows_hot < 6:
    _fail.append(f"beam too thin: {rows_hot} rows (expected >= 6)")
peak_row = int(np.argmax(col))
row_profile = arr.max(axis=2)[max(0, peak_row - 6):peak_row + 7].max(axis=1)
print(f"    vertical profile at beam row: "
      f"{[round(float(v), 2) for v in row_profile]}")

# --------------------------------------------------------------- 2. PROJECTILE
cols = [(0.55, 0.85, 1.0), (1.0, 0.55, 0.35)]
projs = [Proj(-300 + i * 150, 0, 0, cols[i % 2]) for i in range(6)]
arr = render([], projectiles=projs, dist=1200.0,
             save=os.path.join(ROOT, "saves", "diag_gfx4_bolts.png"))
hot = arr.max(axis=2) > 0.55
print(f"[2] bolt hot pixels: {int(hot.sum())} (6 bolts => expect >= 40)")
if int(hot.sum()) < 40:
    _fail.append(f"bolts too faint: {int(hot.sum())} hot px")
# halo: a bolt should light pixels beyond its hot core
mid = arr.max(axis=2) > 0.12
print(f"    bolt halo pixels: {int(mid.sum())} (halo must exceed core)")
if int(mid.sum()) <= int(hot.sum()):
    _fail.append("projectile halo did not render")

# --------------------------------------------------------------- 3. EXPLOSION
expl = [{"kind": "explosion", "t": 0.35, "pos": (0.0, 0.0, 0.0),
         "size": 90, "color": [1, 0.6, 0.3], "seed": 7}]
arr = render(expl, dist=1600.0, save=os.path.join(ROOT, "saves", "diag_gfx4_explosion.png"))
# locate the blast by DIFFING against an empty frame — the starfield has
# bright points of its own, and argmax picks a star, not the explosion
empty = render([], dist=1600.0)
diff = np.clip(arr - empty, 0, None).max(axis=2)
lum = arr.max(axis=2)
n_blast = int((diff > 0.25).sum())
print(f"[3] explosion blast pixels: {n_blast}")
if n_blast < 1500:
    _fail.append(f"explosion too small: {n_blast} px (expected >= 1500)")
cy, cx = np.unravel_index(int(np.argmax(diff)), diff.shape)
print(f"    blast centre at screen ({cx},{cy})")
# a real hot core is a few px wide — a 50x50 mean just averages the gradient
# away and reports the falloff, not the core
core = arr[max(0, cy - 5):cy + 5, max(0, cx - 5):cx + 5]
core_mean = [round(float(core[..., i].mean()), 3) for i in range(3)]
peak = float(diff.max())
print(f"    core mean RGB: {core_mean} | peak delta: {peak:.3f}")
if peak < 0.85:
    _fail.append(f"explosion core not white-hot: peak {peak:.3f} (want >= 0.85)")
if core_mean[0] < 0.45:
    _fail.append(f"explosion core not bright: {core_mean}")

# --------------------------------------------------------------- 4. SPARKS
# embers are thrown clear of the fireball: warm pixels in an annulus
# measured from the BLAST centre (not the frame centre)
yy, xx = np.mgrid[0:H, 0:W]
rad = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
annulus = (rad > 60) & (rad < 700)
warm = (arr[..., 0] > 0.16) & (arr[..., 0] > arr[..., 2] + 0.05)
n_spark = int((warm & annulus).sum())
print(f"[4] ember pixels in annulus around blast: {n_spark}")
if n_spark < 40:
    _fail.append(f"no ember sparks outside the fireball: {n_spark} px")

# --------------------------------------------------------------- 5. montage
battle_fx = [
    {"kind": "beam", "t": 0.01, "pos": (-900.0, 40.0, -300.0),
     "target_pos": (900.0, -20.0, 300.0), "color": [0.55, 0.9, 1.0]},
    {"kind": "beam", "t": 0.06, "pos": (1100.0, 0.0, 200.0),
     "target_pos": (-500.0, 30.0, -600.0), "color": [1.0, 0.45, 0.5]},
    {"kind": "explosion", "t": 0.4, "pos": (400.0, 0.0, -200.0),
     "size": 110, "color": [1, 0.6, 0.3], "seed": 3},
    {"kind": "explosion_small", "t": 0.15, "pos": (-700.0, 0.0, 250.0),
     "size": 40, "color": [1, 0.6, 0.3]},
    {"kind": "muzzle", "t": 0.02, "pos": (-950.0, 40.0, -300.0),
     "color": [0.6, 0.9, 1.0]},
]
bat = [Entity(id=50, kind="ship", owner=0, data_id="imperial_cruiser",
              pos=Vec3(-1200, 0, -400), radius=70.0),
       Entity(id=51, kind="ship", owner=1, data_id="imperial_cruiser",
              pos=Vec3(1300, 0, 400), radius=70.0),
       Entity(id=52, kind="ship", owner=0, data_id="imperial_frigate",
              pos=Vec3(-1100, 0, -800), radius=45.0)]
for s in bat:
    s.yaw, s.vel = math.radians(0), Vec3(0, 0, 0)
    s.is_ship, s.is_station = True, False
st.entities.clear()
for s in bat:
    st.entities[s.id] = s
extra = [Proj(-1000 + i * 260, 20 * math.sin(i), -300 + i * 120,
              cols[i % 2]) for i in range(7)]
render(battle_fx, projectiles=extra, dist=4200.0,
       save=out)
print("saved", out)

if _fail:
    for f in _fail:
        print("  FAIL:", f)
    print("DIAG_FAIL")
    sys.exit(1)
print("DIAG_OK")
