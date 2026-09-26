"""Probe: does the new ship display list rasterize in a clean context?

Renders ONE lit_box and ONE needle list at a known screen position and
probes the pixel rows — isolates display-list/culling/lighting issues
from the full draw() path.

Run: ./.venv/bin/python tools/probe_hull.py
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# NOTE: no dummy driver — SDL dummy has no OpenGL on macOS; use the real
# window server like diag_models.py does.

import pygame
pygame.init()
W, H = 800, 600
pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

import OpenGL.GL as GL
from render.camera import Camera
from render.renderer import Renderer

cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw = 35.0
cam.pitch = 30.0
cam.distance = 400.0
r = Renderer.__new__(Renderer)

# minimal renderer init: only what _ship_display_list/_lit_box need
r.skip = set()
r.ship_lists = {}
r.state = None
r.camera = cam
r.ds = None
r.time = 0.0

GL.glClearColor(0.02, 0.02, 0.05, 1.0)
GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)

# mimic draw-loop light setup: enable light0 + color material (star key light)
GL.glEnable(GL.GL_LIGHTING)
GL.glEnable(GL.GL_LIGHT0)
GL.glEnable(GL.GL_COLOR_MATERIAL)
GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)

lst = r._ship_display_list("needle")
GL.glPushMatrix()
GL.glColor3f(0.38, 0.53, 0.86)
GL.glCallList(lst)
GL.glPopMatrix()
GL.glFinish()

err = GL.glGetError()
data = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
import numpy as np
arr = np.frombuffer(pygame.image.tobytes(img, "RGB"),
                    dtype=np.uint8).reshape(H, W, 3)
ys, xs = np.where(arr.max(axis=2) > 30)
print("lit pixels:", len(ys), "bbox:",
      (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None)
print("GLerr=0x%x" % err)

out = os.path.join(ROOT, "saves", "probe_hull.png")
pygame.image.save(img, out)
print("saved", out)