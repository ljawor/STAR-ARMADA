"""Probe: rasterize the same _lit_box/_out_pyr calls INLINE (no display
list) to separate list-compilation from geometry emission.

Run: ./.venv/bin/python tools/probe_inline.py
"""
import os
import sys
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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
r.skip = set()
r.ship_lists = {}
r.state = None
r.camera = cam
r.ds = None
r.time = 0.0

GL.glClearColor(0.02, 0.02, 0.05, 1.0)
GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
GL.glEnable(GL.GL_LIGHTING)
GL.glEnable(GL.GL_LIGHT0)
GL.glEnable(GL.GL_COLOR_MATERIAL)
GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)

GL.glColor3f(0.38, 0.53, 0.86)
# inline call — no display list
r._lit_box(24, 10, 44, cz=-8)
GL.glFinish()

err = GL.glGetError()
data = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
import numpy as np
arr = np.frombuffer(pygame.image.tobytes(img, "RGB"),
                    dtype=np.uint8).reshape(H, W, 3)
ys, xs = np.where(arr.max(axis=2) > 30)
print("INLINE lit pixels:", len(ys), "bbox:",
      (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
      if len(xs) else None)
print("GLerr=0x%x" % err)

out = os.path.join(ROOT, "saves", "probe_inline.png")
pygame.image.save(img, out)
print("saved", out)