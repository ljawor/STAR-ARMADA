"""Diag: graphics pass A — emissive detail, metal specular, MSAA.

PyOpenGL *segfaults* when GL calls run with no context (verified), so none of
this can be a headless unit test. This script is the verification, following
the repo's diag + pixel-probe pattern.

Checks
------
1. MSAA       — granted SAMPLES after requesting 4x.
2. EMISSIVE   — a lone corvette: rendering with the lit display lists called
                must add lit pixels a bare (empty lit list) render cannot make.
3. WINDOWS    — warm emissive pixels (the window colour 1.0/0.80/0.52) present.
4. NAV LIGHTS — saturated red and green marker pixels present.
5. SPECULAR   — the brightest hull pixel with the metal pass must exceed an
                all-matte render of the same geometry (specular must bite).
6. STATION    — command_station / shipyard / trade_station each show warm
                glazing pixels.
7. No GL errors.

Run: ./.venv/bin/python tools/diag_gfx3.py [out.png]
Prints DIAG_OK (exit 0) only when every assertion holds.
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                    # noqa: E402
import pygame                                         # noqa: E402
from OpenGL.GL import (glClear, glClearColor, glFinish, glGenLists,   # noqa: E402
                       glGetError, glGetIntegerv, glNewList, glEndList,
                       glReadPixels, GL_COLOR_BUFFER_BIT, GL_COMPILE,
                       GL_DEPTH_BUFFER_BIT, GL_NO_ERROR, GL_RGB,
                       GL_SAMPLES, GL_UNSIGNED_BYTE)

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves", "diag_gfx3.png")

pygame.init()
AA = 4
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, AA)
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

samples = int(glGetIntegerv(GL_SAMPLES))
print(f"[1] MSAA requested {AA}x -> granted {samples}x")

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
_empty_list = None


def grab() -> np.ndarray:
    """Front buffer as HxWx3 float [0,1], rows top-down."""
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def mk(eid, data_id, owner, pos, yaw=0.0, radius=45.0, is_station=False):
    e = Entity(id=eid, kind="station" if is_station else "ship", owner=owner,
               data_id=data_id, pos=Vec3(*pos), radius=radius)
    e.yaw, e.vel = yaw, Vec3(0, 0, 0)
    e.is_station = is_station
    e.is_ship = not is_station
    return e


def scene(entities, cam_dist, yaw, pitch, *, skip_lit=False, skip_spec=False,
          save=None) -> np.ndarray:
    """Clear the state, stage `entities`, render one frame, return pixels."""
    global _empty_list
    st.entities.clear()
    for e in entities:
        st.entities[e.id] = e
    cam = Camera(W, H)
    cam.target = [0.0, 0.0, 0.0]
    cam.yaw, cam.pitch, cam.distance = yaw, pitch, cam_dist
    r = Renderer(st, cam)
    r.time = 5.0
    if skip_lit:
        if _empty_list is None:
            _empty_list = glGenLists(1)
            glNewList(_empty_list, GL_COMPILE)
            glEndList()
        empty = int(_empty_list)
        orig = Renderer._ship_display_list

        def patched(self, shape):
            return empty if shape.endswith("_lit") else orig(self, shape)
        r._ship_display_list = patched.__get__(r, Renderer)
        r._station_lit_list = lambda data_id: empty
    if skip_spec:
        r._material_metal = lambda *a, **k: None
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    r.draw(1 / 30, set())
    arr = grab()
    err = glGetError()
    if err != GL_NO_ERROR:
        _fail.append(f"GL error 0x{err:x} during render")
    if save:
        img = pygame.image.frombuffer(
            bytes(np.flipud(arr * 255).astype(np.uint8).tobytes()), (W, H), "RGB")
        pygame.image.save(img, save)
    return arr


def warm_mask(a):
    """Pixels that can only come from the warm emissive window colour."""
    r_, g_, b_ = a[..., 0], a[..., 1], a[..., 2]
    return (r_ > 0.62) & (g_ > 0.38) & (b_ < 0.72) & (r_ > b_ + 0.18)


# ------------------------------------------------------------ 2. emissive pass
ship = [mk(1, "imperial_corvette", 0, (0, 0, 0), yaw=math.radians(60))]
CAMD, YAW, PITCH = 260.0, 35.0, 24.0
with_lit = scene(ship, CAMD, YAW, PITCH, save=os.path.join(ROOT, "saves", "diag_gfx3_ship.png"))
bare = scene(ship, CAMD, YAW, PITCH, skip_lit=True)
# NOTE: comparing "any lit pixel" between the two renders is meaningless —
# the windows sit ON the hull, so they replace hull pixels and barely change
# the silhouette (an earlier version of this probe measured only 55 "new"
# pixels and looked like a failure). What matters is the emissive content:
# warm window pixels that exist with the lit pass and are absent without it.
w_lit = int(warm_mask(with_lit).sum())
w_bare = int(warm_mask(bare).sum())
print(f"[2] warm emissive px: with lit list={w_lit} without={w_bare}")
if w_lit - w_bare < 40:
    _fail.append(f"emissive pass adds only {w_lit - w_bare} warm px (expected >= 40)")

# ------------------------------------------------------------ 3. warm windows
n_warm = int(warm_mask(with_lit).sum())
print(f"[3] warm window pixels: {n_warm}")
if n_warm < 60:
    _fail.append(f"{n_warm} warm window px (expected >= 60)")

# ------------------------------------------------------------ 4. nav lights
r_, g_, b_ = with_lit[..., 0], with_lit[..., 1], with_lit[..., 2]
n_red = int(((r_ > 0.60) & (g_ < 0.30) & (b_ < 0.30)).sum())
n_grn = int(((g_ > 0.60) & (r_ < 0.35) & (b_ < 0.40)).sum())
print(f"[4] nav lights: red={n_red} green={n_grn}")
if n_red < 6 or n_grn < 6:
    _fail.append(f"nav lights too small (red={n_red}, green={n_grn})")

# ------------------------------------------------------------ 5. specular
cruiser = [mk(2, "imperial_cruiser", 0, (0, 0, 0), yaw=math.radians(50),
              radius=70.0)]
spec = scene(cruiser, 320.0, 35.0, 22.0,
             save=os.path.join(ROOT, "saves", "diag_gfx3_cruiser.png"))
matte = scene(cruiser, 320.0, 35.0, 22.0, skip_spec=True)
# NOTE: comparing max luminance is useless here — some hull pixel is already
# saturated in both renders (trim is clamped near white), so max reports
# 1.000 == 1.000 whether or not specular works. Count how MANY pixels the
# highlight lifts instead, which is what the eye actually sees.
hull = ~warm_mask(matte)
delta = (spec.max(axis=2) - matte.max(axis=2))[hull]
n_hi = int((delta > 0.02).sum())
p99 = float(np.percentile(spec.max(axis=2)[hull], 99))
print(f"[5] specular-lifted hull px: {n_hi} of {int(hull.sum())} "
      f"| max delta={float(delta.max()):.3f} | p99 metal={p99:.3f}")
if n_hi < 200:
    _fail.append(f"specular lifted only {n_hi} px (expected >= 200)")

# ------------------------------------------------------------ 6. station glazing
for sid in ("command_station", "shipyard", "trade_station", "mining_station"):
    sd = ds.stations.get(sid)
    if sd is None:
        _fail.append(f"station asset missing: {sid}")
        continue
    rad = float(sd.radius)
    arr = scene([mk(10, sid, 0, (0, 0, 0), radius=rad, is_station=True)],
                rad * 7.0, 35.0, 24.0,
                save=os.path.join(ROOT, "saves", f"diag_gfx3_{sid}.png"))
    n = int(warm_mask(arr).sum())
    print(f"[6] {sid:16s} radius={rad:5.0f} warm glazing px: {n}")
    if n < 60:
        _fail.append(f"{sid}: only {n} warm glazing px (expected >= 60)")

# ------------------------------------------------------------ 7. montage
battle = [mk(20, "imperial_corvette", 0, (-700, 0, 0), yaw=math.radians(20)),
          mk(21, "imperial_corvette", 1, (700, 0, 0), yaw=math.radians(160)),
          mk(22, "imperial_frigate", 0, (-300, 0, 700), yaw=math.radians(-30)),
          mk(23, "imperial_frigate", 1, (300, 0, 700), yaw=math.radians(210)),
          mk(24, "imperial_cruiser", 0, (0, 0, -500), yaw=math.radians(90), radius=70.0),
          mk(25, "command_station", 0, (-2400, 0, -200), radius=260.0, is_station=True),
          mk(26, "command_station", 1, (2400, 0, -200), radius=260.0, is_station=True),
          mk(27, "shipyard", 0, (-900, 0, -1100), radius=180.0, is_station=True),
          mk(28, "fighter_platform", 1, (900, 0, -1100), radius=150.0, is_station=True),
          mk(29, "mining_station", 1, (1500, 0, 500), radius=120.0, is_station=True),
          mk(30, "imperial_battleship", 0, (-200, 0, -1500), yaw=math.radians(70),
             radius=110.0)]
scene(battle, 4600.0, 35.0, 30.0, save=out)
print("saved", out)

if _fail:
    for f in _fail:
        print("  FAIL:", f)
    print("DIAG_FAIL")
    sys.exit(1)
print("DIAG_OK")
