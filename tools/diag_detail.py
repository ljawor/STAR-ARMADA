"""Diag: detail close-ups — render each subject in its own camera pass.

Ten subjects (5 ship hull classes, 5 station types), each rendered alone
with a close camera; tiles composited into a 5x2 grid. Per-tile pixel
assertions: lit geometry + unique colors prove multi-part detail.

Run: ./.venv/bin/python tools/diag_detail.py [out.png]
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["STAR_ARMADA_SKIP"] = "starfield,nebulas,star,planets,jumppoints,rings,sites"

import pygame
from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear, glFinish)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "saves", "diag_detail.png")

pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

import numpy as np
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.entity import Entity
from game.core.vectors import Vec3
from render.camera import Camera
from render.renderer import Renderer

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
renderer = Renderer(st, None)

subjects = []   # (kind, data_id, radius)
for did, r in (("imperial_tie_squadron", 30), ("imperial_corvette", 40),
               ("imperial_cruiser", 70), ("imperial_battleship", 95),
               ("imperial_constructor", 40)):
    subjects.append(("ship", did, r))
for did, r in (("command_station", 130), ("shipyard", 110),
               ("fighter_platform", 75), ("mining_station", 70),
               ("defense_platform", 60)):
    subjects.append(("station", did, r))

# spread subjects far apart so neighbors never leak into a close-up
for idx, (kind, did, radius) in enumerate(subjects):
    e = Entity(id=700 + idx, kind=kind, owner=idx % 2, data_id=did,
               pos=Vec3(idx * 40000.0 - 200000.0, 0.0, 0.0), radius=radius)
    e.yaw = math.pi * 0.75
    e.vel = Vec3(0, 0, 0)
    if kind == "ship":
        e.is_ship, e.is_station = True, False
        e.is_squadron, e.is_construction = False, (did == "imperial_constructor")
    else:
        e.is_ship, e.is_station, e.is_squadron, e.is_construction = \
            False, True, False, False
    st.entities[e.id] = e

cam = Camera(W, H)
renderer.camera = cam
renderer.time = 3.0

TILE_W, TILE_H = 256, 160
COLS, ROWS = 5, 2
grid = pygame.Surface((COLS * TILE_W, ROWS * TILE_H))
fails = []

for idx, (kind, did, radius) in enumerate(subjects):
    e = st.entities[700 + idx]
    glClearColor(0.02, 0.02, 0.05, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    cam.target = [e.pos.x, 0.0, e.pos.z]
    cam.yaw = 0.55
    cam.pitch = 28.0
    # framing: display-list hulls have TRUE half-lengths (wedge 22, needle 50,
    # cruiser 80, dagger 95, utility 20 units at scale 1); the draw scale is
    # vis_scale * max(1, radius/40) — size the camera from the real extent
    ext = {"imperial_tie_squadron": 22, "imperial_corvette": 50,
           "imperial_cruiser": 80, "imperial_battleship": 95,
           "imperial_constructor": 20}.get(did, 40.0)
    if kind == "ship":
        vis_scale = {"imperial_tie_squadron": 0.45, "imperial_corvette": 0.7,
                     "imperial_cruiser": 1.6, "imperial_battleship": 2.4,
                     "imperial_constructor": 0.8}.get(did, 1.0)
        half = ext * vis_scale * max(1.0, radius / 40.0)
        cam.distance = half * 11.0
    else:
        cam.distance = radius * 6.0
    cam.apply(W, H)
    renderer.draw(1 / 30, set())
    err = glGetError()
    glFinish()
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    frame = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
    frame = pygame.transform.flip(frame, False, True)
    # center crop -> tile
    tile = pygame.Surface((TILE_W, TILE_H))
    tile.blit(frame, (-((W - TILE_W) // 2), -((H - TILE_H) // 2)))
    grid.blit(tile, ((idx % COLS) * TILE_W, (idx // COLS) * TILE_H))
    arr = np.frombuffer(pygame.image.tobytes(tile, "RGB"), dtype=np.uint8)
    arr = arr.reshape(TILE_H, TILE_W, 3)
    lit = int(((arr[:, :, 0] > 40) | (arr[:, :, 1] > 40)
               | (arr[:, :, 2] > 40)).sum())
    uniq = len(np.unique(arr.reshape(-1, 3), axis=0))
    ok = lit > 800 and uniq > 8   # flat single-tone boxes measure ~3-7 colors;
                                  # three tone passes + lighting give 9-14+
    print(f"  {did:26s} lit={lit:7d} colors={uniq:5d} "
          f"{'OK' if ok else 'FAIL'} GLerr=0x{err:x}")
    if not ok:
        fails.append(f"{did}: lit={lit} colors={uniq} — too sparse/flat")

pygame.image.save(grid, out)
print("saved", out)
if fails:
    print("DETAIL_DIAG_FAIL:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("DETAIL_DIAG_OK")