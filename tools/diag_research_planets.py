"""Diag: research-station selection (HUD crash repro) + planet/star visuals.

Exercises the exact crash path from the user report: select research_station
-> _right_panel -> _scrollable(key='techs') -> payload lookup. Previously
KeyError: 'techs' crashed the game on click.

Run: ./.venv/bin/python tools/diag_research_planets.py [out.png]
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "saves", "diag_research_planets.png")

pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.entity import Entity
from game.core.vectors import Vec3
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

# find/force a research station owned by player 0
rs = next((e for e in st.entities.values()
           if e.data_id == "research_station" and e.owner == 0), None)
if rs is None:
    rs = Entity(id=9001, kind="station", owner=0, data_id="research_station",
                pos=Vec3(-11000, 0, 800), radius=140)
    rs.yaw = 0.0
    rs.vel = Vec3(0, 0, 0)
    rs.is_station = True
    rs.is_ship = False
    rs.is_squadron = False
    st.entities[rs.id] = rs

cam = Camera(W, H)
cam.target = [rs.pos.x, 0.0, rs.pos.z]
cam.yaw = 30.0
cam.pitch = 38.0
cam.distance = 1500.0

renderer = Renderer(st, cam)
hud = HUD(W, H, st)
hud.set_camera_ref(cam)
renderer.time = 7.0

# --- THE CRASH REPRO: render HUD with the research station selected
try:
    hud.render({rs.id}, None, 0, False, "diag", 1.0, 30.0)
    hud.draw_gl()
    print("RESEARCH_HUD_OK (techs payload lookup passed)")
except Exception as ex:
    print("RESEARCH_HUD_FAIL:", type(ex).__name__, ex)
    raise

# --- render world (planets + star visible from this angle)
glClearColor(0.02, 0.02, 0.05, 1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.draw(1 / 30, set())
hud.render({rs.id}, None, 0, False, "", 0.0, 30.0)
hud.draw_gl()
err = glGetError()
from OpenGL.GL import glFinish
glFinish()
data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
print("saved", out, f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")

# planet/star texture sanity: polar cap must not be a flat uniform block,
# star alpha must reach 0 at the edges (round billboard)
from render import textures as tex
cap = tex.planet_texture("temperate", size=256, seed=5)
import numpy as np
arr = np.dstack(pygame.surfarray.pixels3d(cap))
row_mid = arr[128, :, :]
print("temperate row128 unique colors:", len(np.unique(row_mid.reshape(-1, 3), axis=0)))
star = tex.star_texture(size=256, seed=3)
sa = pygame.surfarray.pixels_alpha(star)
print("star alpha corners (must be ~0):", sa[0, 0], sa[0, -1], sa[-1, 0], sa[-1, -1])
print("star alpha center (must be 255):", sa[128, 128])