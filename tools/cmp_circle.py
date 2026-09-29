"""Render a frigate on the CURRENT branch vs main's renderer, selected and
unselected, to establish what actually draws the flat circle in the
'before' screenshot: the selection ring, or shield rendering?

main has NO shield drawing at all (grep "def _draw_shields" -> 0), so if the
circle appears on main it is the selection ring.

Usage: PYTHONPATH=. ./.venv/bin/python tools/cmp_circle.py
"""
import importlib.util
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                    # noqa: E402
import pygame                                         # noqa: E402
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

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state


def load_renderer(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod.Renderer


Renderer = load_renderer(os.path.join(ROOT, "render", "renderer.py"), "cur_rend")

# main's renderer (no shield code) — saved by the caller
MAIN_PATH = os.environ.get("MAIN_RENDERER", "/tmp/main_renderer.py")
RendererMain = None
if os.path.exists(MAIN_PATH):
    RendererMain = load_renderer(MAIN_PATH, "main_rend")


def mk(i, x, z, owner, yaw, radius=55.0, frac=1.0):
    e = Entity(id=i, kind="ship", owner=owner, data_id="imperial_frigate",
               pos=Vec3(x, 0, z), radius=radius)
    e.yaw, e.vel = yaw, Vec3(0, 0, 0)
    e.is_ship, e.is_station = True, False
    if hasattr(e, "max_shield_quad"):
        e.max_shield_quad = 900.0
        e.shield_regen = 0.0
        for q in QUADRANTS:
            e.shields[q] = 900.0 * frac
    return e


cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 35.0, 20.0, 900.0


def shot(rend_cls, selected, path):
    r = rend_cls(st, cam)
    r.time = 2.0
    st.entities.clear()
    st.entities[1] = mk(1, 0, 0, 0, math.radians(20))
    for _ in range(3):
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        r.draw(1 / 30, set(selected))
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    arr = (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
           .reshape(H, W, 3).astype(np.float32) / 255.0)
    pygame.image.save(img, path)
    return arr


# current branch: unselected vs unselected-without-shields -> bubble
cur_ns = shot(Renderer, set(), os.path.join(ROOT, "saves", "cmp_cur_unsel.png"))
cur_sel = shot(Renderer, {1}, os.path.join(ROOT, "saves", "cmp_cur_sel.png"))
print("current branch: bubble+ring written")


def ring_px(arr):
    """Pixels lit by a thin crisp outline: bright, but no soft fill behind."""
    lum = arr.max(axis=2)
    return int((lum > 0.06).sum())


if RendererMain is not None:
    main_ns = shot(RendererMain, set(), os.path.join(ROOT, "saves", "cmp_main_unsel.png"))
    main_sel = shot(RendererMain, {1}, os.path.join(ROOT, "saves", "cmp_main_sel.png"))
    print(f"main  unselected lit px: {ring_px(main_ns)}")
    print(f"main  SELECTED   lit px: {ring_px(main_sel)}")
else:
    print("main renderer not available; set MAIN_RENDERER")

lit_ns = ring_px(cur_ns)
lit_sel = ring_px(cur_sel)
print(f"branch unselected lit px: {lit_ns}")
print(f"branch SELECTED   lit px: {lit_sel}")
print("saved saves/cmp_*.png")
