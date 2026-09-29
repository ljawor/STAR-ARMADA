"""Visual: are trade convoys actually visible in flight?

Reproduces the reported play — build 2 trade stations, then look for convoys.
Renders the real renderer from a tactical camera between the two stations
after letting convoys build up, and probes pixels for convoy presence.

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_convoy_visible.py [out.png]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                     # noqa: E402
import pygame                                          # noqa: E402
from OpenGL.GL import (glFinish, glReadPixels,         # noqa: E402
                       GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves",
                                                         "diag_convoy.png")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.manager import GameManager                  # noqa: E402
from game.core.vectors import Vec3                         # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.camera import Camera                           # noqa: E402
from render.hud import HUD                                 # noqa: E402
from render.renderer import Renderer                       # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

# two markets 4500u apart — a realistic player layout near their start
A = Vec3(-2250, 0, -6000)
B = Vec3(2250, 0, -6000)
gm.factory.spawn_station("trade_station", 0, A)
gm.factory.spawn_station("trade_station", 0, B)

DT = 1 / 30.0
print(f"leg = {A.dist(B):,.0f}u   spawn_interval = "
      f"{gm.trading.cfg['spawn_interval']}s")

# run just past the first spawn so convoys are on the leg
for _ in range(int(75 / DT)):
    gm.step(DT)

convs = [e for e in st.entities.values()
         if e.alive and e.data_id == "trade_convoy"]
print(f"convoys alive at t={st.time:.0f}s: {len(convs)}")
for c in convs:
    dest = st.entity(c.convoy_dest)
    print(f"  id={c.id} pos=({c.pos.x:+,.0f},{c.pos.z:+,.0f}) "
          f"-> {c.pos.dist(dest.pos):,.0f}u to go")

mid = Vec3((A.x + B.x) / 2, 0, (A.z + B.z) / 2)
cam = Camera(W, H)
cam.target = [mid.x, 0.0, mid.z]
renderer = Renderer(st, cam)
renderer.time = 6.0
hud = HUD(W, H, st)

sel = {convs[0].id} if convs else set()

for name, dist in (("tactical", 2600.0), ("far", 6000.0)):
    cam.yaw, cam.pitch, cam.distance = 0.0, 24.0, dist
    renderer.draw(DT, sel)
    hud.render(sel, None, 0, False, "", 0.0, 0.0)
    hud.draw_gl()
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    arr = (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
           .reshape(H, W, 3).astype(np.float32) / 255.0)
    lit = int((arr.max(axis=2) > 0.12).sum())
    bright = int((arr.max(axis=2) > 0.45).sum())
    print(f"[{name:8s} dist={dist:,.0f}] lit={lit:6d} bright={bright:5d}")
    p = out.replace(".png", f"_{name}.png")
    surf = pygame.image.frombuffer(
        (arr[::-1] * 255).astype(np.uint8).tobytes(), (W, H), "RGB")
    pygame.image.save(surf, p)
    print(f"  saved {p}")

print("PROBE_DONE")
