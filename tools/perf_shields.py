"""Perf: cost of the shield bubble pass (draw-time, not just build)."""
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
pygame.init()
pygame.display.set_mode((1280, 800), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from OpenGL.GL import glClear, glClearColor, glFinish, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT  # noqa: E402
from game.core.entity import Entity, QUADRANTS      # noqa: E402
from game.core.manager import GameManager           # noqa: E402
from game.core.vectors import Vec3                  # noqa: E402
from game.data.store import DataStore               # noqa: E402
from render.camera import Camera                    # noqa: E402
from render.renderer import Renderer                # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

W, H = 1280, 800
cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 35.0, 20.0, 2600.0
r = Renderer(st, cam)
r.time = 2.0


def mk(i, x, z, shields):
    e = Entity(id=i, kind="ship", owner=i % 2, data_id="imperial_frigate",
               pos=Vec3(x, 0, z), radius=55.0)
    e.yaw, e.vel = math.radians(20 + i * 7), Vec3(0, 0, 0)
    e.is_ship, e.is_station = True, False
    e.max_shield_quad = 900.0
    e.shield_regen = 0.0
    for q in QUADRANTS:
        e.shields[q] = 900.0 if shields else 0.0
    return e


def bench(n, shields, frames=40):
    st.entities.clear()
    for i in range(n):
        a = i / max(1, n) * 2 * math.pi
        e = mk(i, math.cos(a) * 1800, math.sin(a) * 1800, shields)
        st.entities[e.id] = e
    for _ in range(5):                       # warm up (builds display lists)
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        r.draw(1 / 30, set())
    glFinish()
    t0 = time.perf_counter()
    for _ in range(frames):
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        r.draw(1 / 30, set())
    glFinish()
    return (time.perf_counter() - t0) / frames * 1000.0


for n in (20, 60, 150):
    off = bench(n, False)
    on = bench(n, True)
    print(f"n={n:4d}  shields off {off:6.2f} ms/frame   on {on:6.2f} ms/frame   "
          f"delta {on - off:+6.2f} ms")
