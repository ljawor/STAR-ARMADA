"""Diag: placement-restriction UX — ghost validator == sim validator.

Proves the exact fix for "ghost green but station not built":
1. mining_station ghost at a spot FAR from the asteroid field must be RED
   with reason "must be within ... of asteroid field" (old code showed green).
2. the same validator accepts a spot near the asteroid field.
3. start_station() through the real command path accepts that near spot and
   queues the build (returns True).
4. ghost far spot: start_station() refuses with a floating text (visible to
   the player).
5. HUD ghost draw path renders with reason text without crashing.

Run: ./.venv/bin/python tools/diag_placement.py [out.png]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
from OpenGL.GL import (glGetError, glReadPixels, glClearColor, GL_RGB,
                       GL_UNSIGNED_BYTE, GL_NO_ERROR, GL_COLOR_BUFFER_BIT,
                       GL_DEPTH_BUFFER_BIT, glClear, glFinish)

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "saves", "diag_placement.png")

pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.vectors import Vec3
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
cs = gm.construction
assert st._construction_system is cs, "state._construction_system wired"

builder = next(e for e in st.entities.values()
               if e.is_construction and e.owner == 0)
print("builder:", builder.data_id, "at", (builder.pos.x, builder.pos.z))

# find the asteroid field (the only legal mining-station neighborhood)
field = next(e for e in st.entities.values() if e.data_id == "asteroid_field")
fx, fz = field.pos.x, field.pos.z
print("asteroid field at", (fx, fz), "radius", field.radius)

# mining station requires_range
msd = ds.stations.get("mining_station")
print("mining_station requires_range:", msd.requires_range)

fails = []

# --- 1. far spot: ghost must be RED with a reason
far = (fx + 8000.0, 0.0, fz + 8000.0)
ok_far, reason_far = cs.check_site("mining_station", far, builder)
print(f"far spot ok={ok_far} reason={reason_far!r}")
if ok_far or "asteroid" not in reason_far:
    fails.append("far spot should be RED with asteroid reason")

# --- 2. near spot: INSIDE the field (requires_range measures from the
#        field CENTER, so legal mining spots are within the field itself)
near = (fx + field.radius * 0.5, 0.0, fz - field.radius * 0.3)
ok_near, reason_near = cs.check_site("mining_station", near, builder)
print(f"near spot ok={ok_near} reason={reason_near!r}")
if not ok_near:
    fails.append(f"near spot should be GREEN, got {reason_near!r}")

# --- 3. sim accepts the near spot through the real command path
cmd_ok = cs.start_station(builder.id, "mining_station", Vec3(*near), 0)
print("start_station(near) ->", cmd_ok)
if not cmd_ok:
    fails.append("sim refused the green spot — the original bug")
q = builder.build_queue
print("builder queue:", [(i.get("kind"), i.get("item")) for i in q])
if not any(i.get("item") == "mining_station" for i in q):
    fails.append("mining_station not in builder queue")

# --- 4. sim refuses the far spot with a player-visible floating text
st.floating_texts.clear()
ok2 = cs.start_station(builder.id, "mining_station", Vec3(*far), 0)
fts = [t["text"] for t in st.floating_texts]
print("start_station(far) ->", ok2, "| floating texts:", fts)
if ok2:
    fails.append("sim accepted the red spot")
if not any("asteroid" in t for t in fts):
    fails.append("no player-visible rejection text for far spot")

# --- 5. HUD ghost render with reason (draw path must not crash)
cam = Camera(W, H)
cam.target = [near[0], 0.0, near[2]]
cam.yaw = 30.0
cam.pitch = 38.0
cam.distance = 1400.0
renderer = Renderer(st, cam)
hud = HUD(W, H, st)
hud.set_camera_ref(cam)
renderer.time = 3.0

hud.placement = {"builder_id": builder.id, "station_kind": "mining_station",
                 "ghost": {"sx": 640, "sy": 200, "valid": False,
                           "reason": reason_far or "must be within 2500u of asteroid field",
                           "radius": msd.radius if msd else 120, "world": near}}
hud.render({builder.id}, None, 0, False, "diag placement", 1.0, 30.0)
hud.draw_gl()

# floating texts projected through the renderer -> HUD labels
hud.set_floating_texts(renderer.floating_texts_screen())
print("floating_texts_screen:", [(t[2], t[0], t[1]) for t in hud.floating_texts])

glClearColor(0.02, 0.02, 0.05, 1.0)
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
cam.apply(W, H)
renderer.draw(1 / 30, set())
hud.render({builder.id}, None, 0, False, "", 0.0, 30.0)
hud.draw_gl()
err = glGetError()
glFinish()
data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
img = pygame.image.frombuffer(bytes(data), (W, H), "RGB")
img = pygame.transform.flip(img, False, True)
pygame.image.save(img, out)
print("saved", out, f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")

if fails:
    print("PLACEMENT_DIAG_FAIL:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PLACEMENT_DIAG_OK")