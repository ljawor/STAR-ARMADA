"""Diag: the trade readout in the left panel must be fully readable.

Reported: selecting a trade station showed the INCOME line cut in half — the
line was drawn at panel.y+70 while the HULL bar began at panel.y+78, so the
bar painted over the bottom of the text.

Renders the REAL HUD with a trade station and a convoy selected, then probes
the text row's pixels directly:

  1. TRADE-coloured text pixels exist in the trade row
  2. no bar/background pixel covers the glyph band (text not clipped)
  3. the line fits inside the panel's inner width
  4. same for a convoy's CARGO line

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_trade_readout.py [out.png]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                     # noqa: E402
import pygame                                          # noqa: E402

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves",
                                                         "diag_trade_readout.png")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.manager import GameManager                  # noqa: E402
from game.core.vectors import Vec3                         # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.hud import HUD, TRADE                          # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

gm.factory.spawn_station("trade_station", 0, Vec3(-3000, 0, -6000))
gm.factory.spawn_station("trade_station", 0, Vec3(3000, 0, -6000))
gm.trading.cfg.update(spawn_interval=0.5, speed=40.0)   # spawn quickly
for _ in range(int(4 / (1 / 30.0))):
    gm.step(1 / 30.0)

station = next(e for e in st.entities.values()
               if e.alive and e.data_id == "trade_station" and e.owner == 0)
conv = next(e for e in st.entities.values()
            if e.alive and e.data_id == "trade_convoy")

hud = HUD(W, H, st)
_fail: list[str] = []

# the panel geometry must match _left_panel
PANEL = pygame.Rect(10, 44, 320, 430)


def check(name, ok, detail=""):
    print(f"[{'ok ' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail.append(name)


def row_pixels(sel, kind, y_off, height=18):
    """Render with `sel` selected and return the overlay region of the row."""
    hud.render(sel, None, 0, False, "", 0.0, 0.0)
    reg = hud.overlay.subsurface(
        pygame.Rect(PANEL.x, PANEL.y + y_off, PANEL.width, height))
    arr = pygame.surfarray.array3d(reg).transpose(1, 0, 2).astype(np.int16)
    return arr


def near(px, col, tol=40):
    return (np.abs(px - np.array(col, dtype=np.int16)).max(axis=-1) <= tol)


for kind, sel, y_off in (("trade station", {station.id}, 70),
                         ("convoy", {conv.id}, 70)):
    print(f"\n--- {kind} selected, trade row at panel.y+{y_off} ---")
    line = hud._trade_line(station if kind == "trade station" else conv)
    print(f"    text: {line!r}")
    arr = row_pixels(sel, kind, y_off)

    trade_px = int(near(arr, TRADE).sum())
    check(f"1. TRADE text pixels visible ({kind})", trade_px > 30,
          f"{trade_px} px of {TRADE}")

    # glyph band must not be painted over by the HULL bar colour.
    # BAR_HULL is the hull bar fill; sample the hull bar row for its colour.
    hud.render({station.id}, None, 0, False, "", 0.0, 0.0)
    hull_row = pygame.surfarray.array3d(hud.overlay.subsurface(
        pygame.Rect(PANEL.x, PANEL.y + 88, PANEL.width, 6))).transpose(1, 0, 2)
    hull_col = tuple(int(v) for v in np.median(
        hull_row.reshape(-1, 3), axis=0))
    print(f"    hull bar colour at +88 = {hull_col}")
    # the glyph rows (top 15px of the row) must contain no hull-bar fill
    glyph = arr[:15]
    overlap = int(near(glyph, hull_col, tol=25).sum())
    check(f"2. text row NOT covered by the hull bar ({kind})",
          overlap < 12, f"{overlap} hull-colour px in the glyph band")

# 3. width fit for the worst-case string at the render font size
f = hud.font_small
for s in ("INCOME 2.5cr/s · NEEDS A SECOND MARKET",
          "INCOME 2.5cr/s · 12 CONVOYS OUT",
          "CARGO 150cr  → AI Warlord"):
    wpx = f.size(s)[0]
    check(f"3. fits inner width ({s[:26]}...)", wpx <= 296,
          f"{wpx}px of 296")

# save an enlarged crop of the panel for the visual check
hud.render({station.id}, None, 0, False, "", 0.0, 0.0)
crop = hud.overlay.subsurface(
    pygame.Rect(PANEL.x, PANEL.y, PANEL.width, 200)).copy()
big = pygame.transform.scale(crop, (PANEL.width * 2, 400))
pygame.image.save(big, out)
print(f"\nsaved {out}")
print("READOUT_OK" if not _fail else f"READOUT_FAIL {_fail}")
sys.exit(1 if _fail else 0)
