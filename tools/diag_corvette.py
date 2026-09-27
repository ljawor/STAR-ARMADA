"""Diag: corvette close-ups from 3 yaw angles — judge rounding + texture.

Injects ONE imperial corvette far from the skirmish starting base, renders
it from three camera yaws (real window server), probes lit/color counts,
saves a vertical strip for visual review.
"""
import os
os.environ["STAR_ARMADA_SKIP"] = "starfield,nebulas,star,planets,jumppoints,rings,sites"
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import pygame
from OpenGL.GL import (glGetError, glReadPixels, glClearColor, glClear,
                       GL_RGB, GL_UNSIGNED_BYTE, GL_NO_ERROR,
                       GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT)

import numpy as np
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.entity import Entity
from game.core.vectors import Vec3
from render.camera import Camera
from render.renderer import Renderer

W, H = 640, 400
os.makedirs("saves", exist_ok=True)
pygame.init()
pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
pygame.display.set_caption("diag corvette")
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

# one corvette at a realistic in-battle position (lighting from the star
# matches gameplay; the 200000 isolation spot has starlight from one side only)
e = Entity(id=901, kind="ship", owner=0, data_id="imperial_corvette",
           pos=Vec3(8000.0, 0.0, 3000.0), radius=40)
e.yaw = 2.4
e.vel = Vec3(0, 0, 0)
e.is_ship, e.is_station, e.is_squadron, e.is_construction = \
    True, False, False, False
st.entities[e.id] = e

cam = Camera(W, H)
renderer = Renderer(st, cam)
renderer.camera = cam
renderer.time = 3.0

tiles = []
for yaw in (0.6, 1.6, 2.6):
    glClearColor(0.02, 0.02, 0.05, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    cam.target = [e.pos.x, 0.0, e.pos.z]
    cam.yaw = yaw
    cam.pitch = 26.0
    # hull full length ~70 units (50 half * 0.7 scale): close-up at ~120 units
    cam.distance = 35.0 * 3.5
    cam.apply(W, H)
    renderer.draw(1 / 30, set())
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    arr = np.frombuffer(data, dtype=np.uint8).reshape(H, W, 3)[:, ::-1, :]
    lit = int(((arr[:, :, 0] > 40) | (arr[:, :, 1] > 40)
               | (arr[:, :, 2] > 40)).sum())
    uniq = len(np.unique(arr.reshape(-1, 3), axis=0))
    err = glGetError()
    print(f"yaw={yaw:.1f} lit={lit} colors={uniq} GLerr=0x{err:x}")
    if lit <= 800:
        print("WARN: dim view, continuing anyway")
    assert err == GL_NO_ERROR
    tiles.append(arr.copy())

out = pygame.image.frombuffer(np.concatenate(tiles, axis=0).tobytes(),
                              (W, H * len(tiles)), "RGB")
pygame.image.save(out, "saves/diag_corvette.png")
print("saved saves/diag_corvette.png")
print("CORVETTE_DIAG_OK")