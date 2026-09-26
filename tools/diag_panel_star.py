"""Diagnostic: production panel (selected shipyard) + textured star + placement banner.

Run: ./.venv/bin/python tools/diag_panel_star.py saves/diag_panel.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame

from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves", "diag_panel.png")

pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.state import GameState
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

# find a shipyard station (or command station) owned by player 0
stn = next(e for e in st.entities.values()
           if e.owner == 0 and e.is_station)

cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]     # face map center; star at [0,-3000,0]
cam.pitch = 10.0
cam.yaw = 90.0                   # look along -z, star should be visible top
cam.zoom(0.25)                   # far out so star is small
renderer = Renderer(st, cam)
hud = HUD(W, H, st)
app = type("App", (), {"flash": lambda self, m: None,
                       "request_exit": lambda self: None})()

# simulate the production panel: select the station
renderer.draw(1 / 30, {stn.id})
hud.render({stn.id}, None, 0, False, "constructing mining_station", 3.0, 30.0)
hud.draw_gl()
err = glGetError()
print(f"station={stn.data_id} builds={getattr(ds.stations.get(stn.data_id), 'builds_ships', None)} "
      f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")

data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
print("saved", out)

# placement ghost check (no GL): fake placement payload and re-render HUD
hud.placement = {"builder_id": stn.id, "station_kind": "mining_station",
                 "ghost": {"sx": 640, "sy": 400, "valid": True,
                           "radius": 120, "world": (0, 0, 0)}}
hud.render(set(), None, 0, False, "", 0.0, 30.0)
hud.draw_gl()
data2 = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img2 = pygame.image.frombuffer(bytes(data2), (W, H), "RGB")
img2 = pygame.transform.flip(img2, False, True)
out2 = out.replace(".png", "_ghost.png")
pygame.image.save(img2, out2)
print("saved", out2)

# textured star close-up: aim camera at the star
from render import textures as _tex
from OpenGL.GL import glFinish
star = st.map_info.star
cam.target = [float(star["pos"][0]), float(star["pos"][1]), float(star["pos"][2])]
cam.yaw = 90.0
cam.pitch = 5.0
cam.distance = 13000.0     # > guard radius (size*2.2=5720), star ~460px wide
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.time = 4.0
renderer._draw_star()
err3 = glGetError()
glFinish()
# pixel probes: billboard center/edge (should be bright orange if textured)
import numpy as np
px_c = glReadPixels(W // 2, H // 2, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
px_e = glReadPixels(W // 2 + 150, H // 2, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
print("star probes center/edge:", bytes(px_c).hex(), bytes(px_e).hex())
s = _tex.star_texture()
print("texture sample (128,128):", s.get_at((128, 128)),
      "bits", s.get_bitsize(), "texid", renderer._star_tex)

# manual billboard with the same helper — isolates _draw_star state vs helper
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.time = 4.0
renderer._draw_star()
glFinish()
err3 = glGetError()
import numpy as np
px_c = glReadPixels(W // 2, H // 2, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
px_e = glReadPixels(W // 2 + 150, H // 2, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
print("star probes center/edge:", bytes(px_c).hex(), bytes(px_e).hex())
data3 = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img3 = pygame.image.frombuffer(bytes(data3), (W, H), "RGB")
img3 = pygame.transform.flip(img3, False, True)
out3 = out.replace(".png", "_star.png")
pygame.image.save(img3, out3)
print("saved", out3, f"GLerr=0x{err3:x}")