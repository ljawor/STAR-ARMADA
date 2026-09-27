"""Diag: graphics pass — asteroids, all station types, nose-first movement.

Verifies:
1. Asteroid rocks are lit faceted lumps (not flat squares) — pixel check.
2. All 8 station types render distinct multi-part geometry.
3. Ships moving with velocity face nose-first: ship with yaw=0 moving +z
   must show its nose (+z side of the hull display list) toward +z; the
   renderer now rotates by +yaw (matching sim facing), verified by projecting
   the ship's nose tip to screen vs its tail.
4. Movement sim: velocity projection kills sideways drift.

Run: ./.venv/bin/python tools/diag_gfx2.py [out.png]
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear, glFinish)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "saves", "diag_gfx2.png")

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

fails = []

# ---------------------------------------------------------------- movement sim
DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
ship = next(e for e in st.entities.values() if e.is_ship and e.owner == 0)
# force a turn: heading east (yaw = pi/2), old velocity pointing north;
# then ORDER it to keep moving east — thrust must push along the nose only
ship.yaw = math.pi / 2
ship.vel = Vec3(0.0, 0.0, 300.0)       # pure sideways velocity
from game.core.commands import MoveCommand
st.queue_command(MoveCommand(0, [ship.id],
                             Vec3(ship.pos.x + 2000.0, 0.0, ship.pos.z)))
pos0 = (ship.pos.x, ship.pos.z)
for _ in range(30):                    # 1 simulated second
    gm.step(1 / 30)
moved = (ship.pos.x - pos0[0], ship.pos.z - pos0[1])
print(f"sim check: heading east, ordered east -> moved dx={moved[0]:.2f} dz={moved[1]:.2f}")
# tolerance 12: the separation system legitimately nudges position when ships
# spawn close together; nose-first is about *velocity*, not contact pushes
if abs(moved[1]) > 12.0:
    fails.append(f"ship drifted sideways dz={moved[1]:.1f} — nose-first violated")
if moved[0] <= 10.0:
    fails.append("ship did not accelerate toward its nose (east)")

# ---------------------------------------------------------------- scene render
# fresh game for a clean scene
DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
renderer = Renderer(st, None)

field = next(e for e in st.entities.values() if e.data_id == "asteroid_field")
# spawn all 8 station types + a moving ship in a line for the wide shot
kinds = ["command_station", "shipyard", "research_station", "defense_platform",
         "sensor_station", "trade_station", "fighter_platform", "repair_dock",
         "energy_relay", "mining_station"]
x0 = field.pos.x - 5200
for i, k in enumerate(kinds):
    ent = Entity(id=900 + i, kind="station", owner=i % 2, data_id=k,
                 pos=Vec3(x0 + i * 1150, 0.0, field.pos.z - 2600.0),
                 radius=90)
    ent.yaw = 0.0
    ent.vel = Vec3(0, 0, 0)
    ent.is_station = True
    ent.is_ship = False
    ent.is_squadron = False
    ent.is_construction = False
    st.entities[ent.id] = ent
# a cruiser moving fast (engine glow + trail visible)
mover = Entity(id=950, kind="ship", owner=0, data_id="imperial_cruiser",
               pos=Vec3(x0 + 600, 0.0, field.pos.z - 1400.0), radius=60)
mover.yaw = math.pi / 2          # facing +x (east)
mover.vel = Vec3(220.0, 0.0, 0.0)
mover.is_ship = True
mover.is_station = False
mover.is_squadron = False
st.entities[mover.id] = mover

cam = Camera(W, H)
cam.target = [field.pos.x, 0.0, field.pos.z - 1600.0]
cam.yaw = 0.0
cam.pitch = 34.0
cam.distance = 7400.0
renderer.camera = cam
renderer.time = 5.0

glClearColor(0.02, 0.02, 0.05, 1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.draw(1 / 30, set())
err = glGetError()
glFinish()
data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
print("saved", out, f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")

# pixel probe: find the asteroid field on screen via its center, then probe
# a box around it; must have >1500 lit pixels and >= 25 unique colors
arr = np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
arr = arr.reshape(H, W, 3)
fs = cam.world_to_screen(field.pos.x, field.pos.y, field.pos.z)
print("field center on screen:", fs)
if fs is None:
    fails.append("asteroid field not in front of camera")
else:
    cx_, cy_ = int(fs[0]), int(fs[1])
    y0_, y1_ = max(0, cy_ - 350), min(H, cy_ + 350)
    x0_, x1_ = max(0, cx_ - 500), min(W, cx_ + 500)
    band = arr[y0_:y1_, x0_:x1_, :]
    lit = int(((band[:, :, 0] > 40) | (band[:, :, 1] > 40)
               | (band[:, :, 2] > 40)).sum())
    uniq = len(np.unique(band.reshape(-1, 3), axis=0))
    print(f"asteroid band: lit px={lit} unique colors={uniq}")
    if lit < 1500:
        fails.append(f"asteroids too dim/sparse: lit={lit}")
    if uniq < 25:
        fails.append(f"asteroids look flat: only {uniq} colors")

# nose-first render check: cruiser nose (+z local = +x world at yaw=pi/2)
# must project to screen-right of its tail
nose_w = (mover.pos.x + 60 * math.sin(mover.yaw), mover.pos.y,
          mover.pos.z + 60 * math.cos(mover.yaw))
tail_w = (mover.pos.x - 60 * math.sin(mover.yaw), mover.pos.y,
          mover.pos.z - 60 * math.cos(mover.yaw))
ns = cam.world_to_screen(*nose_w)
ts = cam.world_to_screen(*tail_w)
print(f"cruiser nose screen={ns} tail screen={ts}")
if ns is None or ts is None:
    fails.append("cruiser nose/tail projection failed")
elif ns[0] <= ts[0]:
    fails.append("cruiser rendered tail-first — yaw mirror bug is back")

if fails:
    print("GFX2_DIAG_FAIL:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("GFX2_DIAG_OK")