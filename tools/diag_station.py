"""Diagnostic: draw ONE command station, screenshot, report GL errors.

Variants via argv: 'cull' = enable backface culling; 'nocull' = disable.
Run: ./.venv/bin/python tools/diag_station.py cull saves/diag_cull.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame

from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR)

mode = sys.argv[1] if len(sys.argv) > 1 else "cull"
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "saves", "diag.png")

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
stn = next(e for e in st.entities.values() if e.owner == 0 and e.is_station)

cam = Camera(W, H)
cam.target = [stn.pos.x, 0.0, stn.pos.z]
cam.zoom(0.55)
renderer = Renderer(st, cam)

glClearColor(0.02, 0.02, 0.05, 1.0)
from OpenGL.GL import GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, glClear
cam.apply(W, H)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

# draw ONLY the station
import OpenGL.GL as GL
if mode == "nocull":
    GL.glDisable(GL.GL_CULL_FACE)
renderer._draw_station(stn)
err = glGetError()
print(f"mode={mode} station={stn.data_id} pos=({stn.pos.x:0.0f},{stn.pos.z:0.0f}) "
      f"r={stn.radius} GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")

data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(data, (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
print("saved", out)

# count non-background pixels (did anything draw at all?)
import numpy as np
arr = np.frombuffer(data, dtype=np.uint8).reshape(H, W, 3)
nonbg = int((arr.sum(axis=2) > 30).sum())
print("non-background pixels:", nonbg)