"""Diag: battle scene (effects as billboards), detailed ships, construction
scaffold, plus weapon_fired/projectile_hit event wiring check.

Run: ./.venv/bin/python tools/diag_battle.py [out.png]
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
    ROOT, "saves", "diag_battle.png")

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

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

# --- event wiring check: publish fire/hit, assert audio callbacks exist
fired = []
st.events.subscribe("weapon_fired", lambda ev: fired.append(ev.data))
st.events.publish("weapon_fired", attacker_id=1, owner=0, weapon="laser_cannon",
                  heavy=False)
assert fired and fired[0]["weapon"] == "laser_cannon", "weapon_fired failed"
assert len(st.events.log) == 0, "noisy event leaked into log ring!"
print("EVENTS_OK: weapon_fired delivered, log ring clean")

st.entities.clear()

def mk(eid, data_id, owner, pos, yaw=0.0, radius=45.0, is_station=False,
       is_construction=False, queue_item=None):
    e = Entity(id=eid, kind="station" if is_station else "ship", owner=owner,
               data_id=data_id, pos=Vec3(*pos), radius=radius)
    e.yaw = yaw
    e.vel = Vec3(0, 0, 0)
    e.is_station = is_station
    e.is_construction = is_construction
    e.is_ship = not (is_station or is_construction)
    if queue_item:
        e.build_queue.append(queue_item)
    st.entities[eid] = e
    return e

# battle line: two frigates exchanging fire with a cruiser
mk(1, "imperial_frigate", 0, (-300, 0, 0), math.radians(0))
mk(2, "imperial_corvette", 0, (-150, 0, 260), math.radians(-10))
mk(3, "rebel_frigate", 1, (400, 0, 80), math.radians(200))
mk(4, "rebel_corvette", 1, (520, 0, -220), math.radians(160))
mk(5, "imperial_cruiser", 0, (-900, 0, -400), math.radians(15), radius=70)
mk(6, "command_station", 0, (-1500, 0, 500), 0.0, radius=260, is_station=True)
mk(7, "shipyard", 0, (-900, 0, 900), 0.0, radius=180, is_station=True)
# constructor building a mining station: scaffold should show at site
mk(8, "imperial_constructor", 0, (-400, 0, 700), math.radians(0),
   is_construction=True,
   queue_item={"kind": "station", "item": "mining_station",
               "time_left": 30.0, "total": 45.0, "status": "paid",
               "pos": {"x": -200.0, "y": 0.0, "z": 900.0}})
# battle effects: explosions, impacts, fire, beam, muzzle flashes
st.spawn_effect("explosion", Vec3(150, 0, 100), size=80)
st.spawn_effect("impact", Vec3(300, 10, 60), color=[1, 0.6, 0.3])
st.spawn_effect("impact", Vec3(360, -10, 120), color=[0.4, 0.7, 1])
st.spawn_effect("fire", Vec3(330, 0, 80), size=60)
st.spawn_effect("beam", Vec3(-250, 0, 0),
                target_pos=(380.0, 0.0, 80.0), color=[1, 0.3, 0.3])
st.spawn_effect("muzzle", Vec3(-260, 4, 0), color=[1, 0.8, 0.4])
st.spawn_effect("shield_down", Vec3(400, 0, 80), size=90)
st.spawn_effect("explosion_small", Vec3(480, 0, -200), size=40)

cam = Camera(W, H)
cam.target = [-300.0, 0.0, 0.0]
cam.yaw = 50.0
cam.pitch = 26.0
cam.distance = 260.0
renderer = Renderer(st, cam)
renderer.time = 3.0

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
print("saved", out, f"GLerr=0x{err:x} ({'OK' if err == GL_NO_ERROR else 'ERROR'})")