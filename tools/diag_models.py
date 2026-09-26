"""Diagnostic: render new ship + station geometry from a hero angle.

Run: ./.venv/bin/python tools/diag_models.py saves/diag_models.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame

from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves", "diag_models.png")

pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.data.store import DataStore
from game.core.manager import GameManager
from render.camera import Camera
from render.renderer import Renderer

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
print("player colors:", {pid: tuple(round(c, 2) for c in p.color)
                         for pid, p in st.players.items()})

# stage hero ships + both stations around origin with per-player colors
import math
st.entities.clear()
from game.core.entity import Entity
from game.core.vectors import Vec3


def mk(eid, data_id, owner, pos, yaw, radius=45.0, is_station=False,
       is_squadron=False):
    e = Entity(id=eid, kind="squadron" if is_squadron else
               ("station" if is_station else "ship"),
               owner=owner, data_id=data_id, pos=Vec3(*pos), radius=radius)
    e.yaw = yaw
    e.vel = Vec3(0, 0, 0)
    e.is_station = is_station
    e.is_squadron = is_squadron
    e.is_ship = not (is_station or is_squadron)
    st.entities[eid] = e
    return e


mk(1, "imperial_corvette", 0, (-600, 0, 0), math.radians(20))
mk(2, "imperial_corvette", 1, (600, 0, 0), math.radians(160))
mk(3, "imperial_frigate", 0, (-250, 0, 700), math.radians(-30))
mk(4, "imperial_frigate", 1, (250, 0, 700), math.radians(210))
mk(5, "imperial_cruiser", 0, (0, 0, -500), math.radians(90), radius=70)
mk(6, "imperial_colonizer", 0, (-900, 0, 500), math.radians(45))
mk(7, "command_station", 0, (-1600, 0, -200), 0.0, radius=260, is_station=True)
mk(8, "command_station", 1, (1600, 0, -200), 0.0, radius=260, is_station=True)
mk(9, "shipyard", 0, (-700, 0, -900), 0.0, radius=180, is_station=True)
mk(10, "fighter_platform", 0, (700, 0, -900), 0.0, radius=150, is_station=True)
mk(11, "mining_station", 1, (900, 0, 300), 0.0, radius=120, is_station=True)
mk(12, "imperial_tie_squadron", 0, (0, 0, 300), math.radians(0), radius=30,
   is_squadron=True)

cam = Camera(W, H)
# close-up on the P0 corvette at (-600,0,0), yaw 20°
cam.target = [0.0, 0.0, 0.0]
cam.yaw = 0.0
cam.pitch = 32.0
cam.distance = 3600.0
renderer = Renderer(st, cam)
renderer.time = 7.0

# project every entity so we can verify framing programmatically
for eid, e in st.entities.items():
    sp = cam.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
    print(f"  e{eid} {e.data_id:26s} pos=({e.pos.x:7.0f},{e.pos.z:6.0f})"
          f" screen={sp}")

glClearColor(0.02, 0.02, 0.05, 1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.draw(1 / 30, set())
err = glGetError()
from OpenGL.GL import glFinish
glFinish()
data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
# pixel probe: center strip max brightness — the corvette must be visible
import numpy as _np
arr = _np.frombuffer(pygame.image.tobytes(img, "RGB"),
                     dtype=_np.uint8).reshape(H, W, 3)
strip = arr[360:440, 560:720]
print("center strip max RGB:", strip.reshape(-1, 3).max(axis=0))
print("saved", out, f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")