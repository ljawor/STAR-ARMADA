"""Does a SELECTED shielded ship look right, or does the selection ring draw a
flat circle back over the new bubble?

main had no shield rendering at all — the flat blue circle in the reference
screenshot is `_draw_selection_rings`, at radius e.radius * 1.35, which is the
SAME radius as the shield shell. So for a selected unit the two coincide.
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                   # noqa: E402
import pygame                                        # noqa: E402
from OpenGL.GL import (glClear, glClearColor, glFinish, glReadPixels,  # noqa: E402
                       GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_RGB,
                       GL_UNSIGNED_BYTE)

W, H = 1280, 800
pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.entity import Entity, QUADRANTS       # noqa: E402
from game.core.manager import GameManager            # noqa: E402
from game.core.vectors import Vec3                   # noqa: E402
from game.data.store import DataStore                # noqa: E402
from render.camera import Camera                     # noqa: E402
from render.renderer import Renderer                 # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state


def mk(i, x, z, owner, yaw, radius=55.0, frac=1.0, data_id="imperial_frigate"):
    e = Entity(id=i, kind="ship", owner=owner, data_id=data_id,
               pos=Vec3(x, 0, z), radius=radius)
    e.yaw, e.vel = yaw, Vec3(0, 0, 0)
    e.is_ship, e.is_station = True, False
    e.max_shield_quad = 900.0
    e.shield_regen = 0.0
    for q in QUADRANTS:
        e.shields[q] = 900.0 * frac
    return e


cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 35.0, 20.0, 900.0
r = Renderer(st, cam)
r.time = 2.0


def shot(ents, selected, path):
    st.entities.clear()
    for e in ents:
        st.entities[e.id] = e
    for _ in range(3):
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        r.draw(1 / 30, set(selected))
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    np_arr = np.frombuffer(
        pygame.image.tobytes(pygame.transform.flip(img, False, True), "RGB"),
        dtype=np.uint8).reshape(H, W, 3)
    arr = np_arr.astype(np.float32) / 255.0
    pygame.image.save(
        pygame.image.frombuffer(bytes(np.flipud(arr * 255).astype(np.uint8)
                                     .tobytes()), (W, H), "RGB"), path)
    return arr


ship = mk(1, 0, 0, 0, math.radians(20))
a_sel = shot([ship], {1}, os.path.join(ROOT, "saves", "chk_selected.png"))
a_unsel = shot([ship], set(), os.path.join(ROOT, "saves", "chk_unselected.png"))

# The selection ring is a thin crisp loop; the bubble is a soft volumetric
# shell. Check the selection ring did not simply replace the bubble: the bubble
# must still fill the disc well beyond a 2px ring.
diff = np.clip(a_unsel - shot(
    [mk(2, 0, 0, 0, math.radians(20), frac=0.0)], set(),
    os.path.join(ROOT, "saves", "chk_noshield.png")), 0, None).max(axis=2)
ys, xs = np.nonzero(diff > 0.015)
cx, cy = xs.mean(), ys.mean()
rr = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
R = max(1.0, rr.max())
inner = int((rr < R * 0.55).sum())
print(f"unselected: bubble px={len(xs)} inner-disc={inner} "
      f"({inner / max(1, len(xs)):.2f})")

# how much brighter is the selected frame? if the ring overwrote the bubble the
# shell would be replaced, not added to
sel_diff = np.abs(a_sel - a_unsel).max(axis=2)
n_ring = int((sel_diff > 0.03).sum())
print(f"selection ring px changed={n_ring} "
      f"({n_ring / max(1, len(xs)):.2f} of bubble px)")
print("saved saves/chk_selected.png / chk_unselected.png / chk_noshield.png")
