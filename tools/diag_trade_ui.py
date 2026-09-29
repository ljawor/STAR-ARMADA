"""Diag: a trade convoy must not crash the render/HUD path.

Reproduces the reported crash: build a trade station, a convoy spawns, then
select it. The traceback was

    hud.render -> _top_bar -> p.command_used -> command_cost -> resolve_ship
    KeyError: "Unknown ship id 'trade_convoy'"

A trade_convoy is a simulated ship minted by TradingSystem with deliberately
NO ShipData entry, so every code path that assumes ship data exists raises.
This drives the REAL renderer + HUD (the same calls main.py makes) with a
convoy alive and selected, and probes that:

  1. HUD top bar renders with a convoy in play (command capacity readout)
  2. HUD left panel renders with the convoy selected (cargo/destination line)
  3. HUD left panel renders with a trade station selected (income line)
  4. renderer.draw() renders a frame containing convoys
  5. selecting a convoy draws it without GL errors
  6. command_used() is total for every player

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_trade_ui.py [out.png]
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                    # noqa: E402
import pygame                                         # noqa: E402
from OpenGL.GL import (glFinish, glGetError, glReadPixels,  # noqa: E402
                       GL_NO_ERROR, GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves",
                                                         "diag_trade_ui.png")

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
_fail: list[str] = []


def grab() -> np.ndarray:
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok ' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail.append(name)


def attempt(name: str, fn) -> bool:
    """Run fn(), report a crash as a FAIL rather than letting it escape."""
    try:
        fn()
        check(name, True)
        return True
    except Exception as exc:
        check(name, False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------- scene setup
# Two markets so convoys actually spawn, close together so a few fly quickly.
gm.factory.spawn_station("trade_station", 0, Vec3(-3000, 0, 0))
gm.factory.spawn_station("trade_station", 1, Vec3(3000, 0, 0))
gm.trading.cfg.update(spawn_interval=0.5, speed=40.0)
DT = 1 / 30.0
for _ in range(int(6 / DT)):
    gm.step(DT)

convoys = [e for e in st.entities.values()
           if e.alive and e.data_id == "trade_convoy"]
trade = next(e for e in st.entities.values()
             if e.alive and e.data_id == "trade_station" and e.owner == 0)
print(f"subject: {len(convoys)} convoys alive, trade_station id={trade.id}")
print()

conv = convoys[0]
cam = Camera(W, H)
cam.target = [0.0, 0.0, 0.0]
cam.yaw, cam.pitch, cam.distance = 0.0, 22.0, 2600.0
renderer = Renderer(st, cam)
renderer.time = 3.0
hud = HUD(W, H, st)

# (1) the exact reported crash: HUD top bar with a convoy in play
attempt("1. HUD top bar with convoy in play (command capacity)",
        lambda: hud.render(set(), None, 0, False, "", 0.0, 0.0))

# (6) command_used must be total for every player
def _used_total():
    for pid, p in st.players.items():
        n = p.command_used(st.entities)
        assert isinstance(n, (int, float)), f"player {pid}: non-numeric {n}"
attempt("6. command_used() total for every player", _used_total)

# (2) HUD with the convoy selected — must not raise
attempt("2. HUD left panel, convoy selected",
        lambda: hud.render({conv.id}, None, 0, False, "", 0.0, 0.0))

# (3) HUD with a trade station selected
attempt("3. HUD left panel, trade station selected",
        lambda: hud.render({trade.id}, None, 0, False, "", 0.0, 0.0))

# the trade readout text itself
def _lines():
    print(f"        convoy       -> {hud._trade_line(conv)!r}")
    print(f"        trade stn    -> {hud._trade_line(trade)!r}")
attempt("3b. _trade_line for both unit kinds", _lines)

# (4) a full renderer frame with convoys on screen
attempt("4. renderer.draw() with convoys alive",
        lambda: renderer.draw(DT, {conv.id}))

# (5) selection of a convoy draws clean, no GL errors
glGetError()
attempt("5. renderer.draw() with convoy SELECTED (no GL error)",
        lambda: renderer.draw(DT, {conv.id}))
err = glGetError()
check("5b. GL error code clean after drawing selection", err == GL_NO_ERROR,
      f"glGetError()={err}")

# composite the HUD overlay into the framebuffer so the capture SHOWS the
# panel (hud.render only draws into its own surface; draw_gl uploads it)
attempt("5c. HUD overlay composites to GL (draw_gl)",
        lambda: (hud.render({conv.id}, None, 0, False, "", 0.0, 0.0),
                 hud.draw_gl()))
err2 = glGetError()
check("5d. GL error code clean after HUD draw_gl", err2 == GL_NO_ERROR,
      f"glGetError()={err2}")

# pixels: the convoy hull must actually be on screen in the captured frame
img = grab()
lit = int((img.max(axis=2) > 0.12).sum())
check("7. frame has visible content", lit > 2000, f"{lit} lit px")

os.makedirs(os.path.dirname(out), exist_ok=True)
surf = pygame.image.frombuffer(
    (img[::-1] * 255).astype(np.uint8).tobytes(), (W, H), "RGB")
pygame.image.save(surf, out)
print(f"\nsaved {out}")
print("TRADE_UI_OK" if not _fail else f"TRADE_UI_FAIL {_fail}")
sys.exit(1 if _fail else 0)
