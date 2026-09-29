"""Diag: box-select rectangle is drawn, and Ctrl+1..9 assigns control groups.

Two reported bugs:
  1. left-drag box-selects but no rectangle is ever drawn
  2. Ctrl+1..9 does not work (every number key assigned, so it never recalled)

Part 1 renders the REAL HUD mid-drag and probes the pixels between the two
drag corners for the rectangle's fill/edge colour.
Part 2 drives the REAL InputController event path with synthetic pygame events
and asserts assign-vs-recall semantics.

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_drag_groups.py [out.png]
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
                                                         "diag_drag_box.png")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.manager import GameManager                  # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.camera import Camera                           # noqa: E402
from render.hud import HUD, DRAG_EDGE                      # noqa: E402
from render.input import InputController                   # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
cam = Camera(W, H)
hud = HUD(W, H, st)

_fail: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'ok ' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail.append(name)


# ============================================================ 1. the drag box
print("=== 1. box-select rectangle ===")
X0, Y0, X1, Y1 = 300, 200, 700, 520


def arr_of(surface):
    return pygame.surfarray.array3d(surface).transpose(1, 0, 2).astype(np.int16)


def near(px, col, tol=40):
    return (np.abs(px - np.array(col[:3], dtype=np.int16)).max(axis=-1) <= tol)


# DRAG_EDGE (150,195,255) is within 30 of the top bar's energy colour
# (150,220,240), so the NEGATIVE checks need a tight tolerance or they
# false-positive on the HUD itself. tol=12 is clean (verified separately).
TOL = 12


# no drag -> no rectangle
hud.set_drag_box(None, None)
hud.render(set(), None, 0, False, "", 0.0, 0.0)
base = arr_of(hud.overlay)
edge_none = int(near(base, DRAG_EDGE, tol=TOL).sum())
check("1a. no rectangle when not dragging", edge_none == 0,
      f"{edge_none} edge px")

# mid-drag -> rectangle drawn
hud.set_drag_box((X0, Y0), (X1, Y1))
hud.render(set(), None, 0, False, "", 0.0, 0.0)
img = arr_of(hud.overlay)
edge_px = int(near(img, DRAG_EDGE, tol=TOL).sum())

# the top edge row must contain edge-colour pixels spanning the box width
top = img[Y0 - 1:Y0 + 2, X0:X1]
top_hits = int(near(top, DRAG_EDGE, tol=TOL).sum())
check("1b. rectangle EDGE drawn while dragging", edge_px > 200,
      f"{edge_px} edge px")
check("1c. edge spans the dragged width", top_hits >= (X1 - X0) * 0.8,
      f"{top_hits} of {X1 - X0} px on the top edge")

# interior must be tinted (fill). The overlay is an SRCALPHA surface, so
# subtlety lives in its ALPHA channel — array3d/array_alpha give RGB and A
# separately, and RGB alone reads as the raw fill colour regardless of alpha.
hud.set_drag_box((X0, Y0), (X1, Y1))
hud.render(set(), None, 0, False, "", 0.0, 0.0)
alpha = pygame.surfarray.array_alpha(hud.overlay).T.astype(np.int16)
interior_a = alpha[Y0 + 40:Y1 - 40, X0 + 40:X1 - 40].mean()
outside_a = alpha[Y1 + 60:Y1 + 120, X0 + 40:X1 - 40].mean()
check("1d. interior tinted (alpha up) but SUBTLE",
      interior_a > 8.0 and interior_a < 70.0 and interior_a > outside_a + 8.0,
      f"interior alpha {interior_a:.1f} vs outside {outside_a:.1f}")

# degenerate drag must not draw a giant box
hud.set_drag_box((X0, Y0), (X0 + 1, Y0 + 1))
hud.render(set(), None, 0, False, "", 0.0, 0.0)
tiny = int(near(arr_of(hud.overlay), DRAG_EDGE, tol=TOL).sum())
check("1e. no rectangle for a 1px (click-like) drag", tiny == 0, f"{tiny} px")

# save a crop for the visual check
hud.set_drag_box((X0, Y0), (X1, Y1))
hud.render(set(), None, 0, False, "", 0.0, 0.0)
crop = hud.overlay.subsurface(
    pygame.Rect(X0 - 40, Y0 - 40, (X1 - X0) + 80, (Y1 - Y0) + 80)).copy()
pygame.image.save(crop, out)
print(f"saved {out}")


# ======================================================= 2. control groups
print("\n=== 2. Ctrl+1..9 control groups ===")


class _App:
    local_player = 0

    def __init__(self):
        self.flashes = []

    def flash(self, msg):
        self.flashes.append(msg)

    def request_exit(self):
        pass

    def toggle_pause(self):
        pass


def make_ic():
    app = _App()
    ic = InputController(st, cam, hud, app)
    ic.local_player = 0
    return ic, app


def key(ic, k, ctrl=False, shift=False, down=True):
    """Drive the REAL handler (not _control_group directly)."""
    mod = 0
    if ctrl:
        mod |= pygame.KMOD_CTRL | pygame.KMOD_LCTRL
    if shift:
        mod |= pygame.KMOD_SHIFT
    ev = pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP,
                            key=k, mod=mod, scancode=0, unicode="")
    ic.handle_event(ev)
    # mirror what SDL does for the tracked key set
    if ctrl:
        (ic.keys.add if down else ic.keys.discard)(pygame.K_LCTRL)


ic, app = make_ic()
units = [e.id for e in st.entities.values() if e.alive and e.owner == 0][:3]
assert len(units) >= 2, f"need 2+ player units, got {units}"

# assign: select units, Ctrl+1
ic.selection = set(units[:2])
key(ic, pygame.K_1, ctrl=True, down=True)
key(ic, pygame.K_1, ctrl=True, down=False)
check("2a. Ctrl+1 assigns the selection",
      ic.groups.get(1) == set(units[:2]), f"group1={ic.groups.get(1)}")

# Ctrl+1 must NOT have changed the selection
check("2b. Ctrl+1 leaves the selection alone",
      ic.selection == set(units[:2]), f"sel={ic.selection}")

# now clear the selection and press 1 alone -> recall the group
ic.selection = set()
key(ic, pygame.K_1, down=True)
key(ic, pygame.K_1, down=False)
check("2c. plain 1 RECALLS the group",
      ic.selection == set(units[:2]), f"sel={ic.selection}")

# reassigning with Ctrl+2 to a different set, then plain 2 recalls it
ic.selection = {units[2]}
key(ic, pygame.K_2, ctrl=True, down=True)
key(ic, pygame.K_2, ctrl=True, down=False)
ic.selection = set()
key(ic, pygame.K_2, down=True)
key(ic, pygame.K_2, down=False)
check("2d. Ctrl+2 then plain 2 round-trips",
      ic.selection == {units[2]}, f"sel={ic.selection}")

# shift+number ADDS to the selection (documented union behaviour)
ic.selection = set(units[:1])
key(ic, pygame.K_1, shift=True, down=True)
key(ic, pygame.K_1, shift=True, down=False)
check("2e. Shift+1 unions with the group",
      ic.selection == set(units[:2]), f"sel={ic.selection}")

# recalling an EMPTY group must clear, not crash
ic.selection = set(units[:1])
key(ic, pygame.K_7, down=True)
key(ic, pygame.K_7, down=False)
check("2f. unassigned group clears the selection",
      ic.selection == set(), f"sel={ic.selection}")

print(f"\nflash messages seen: {app.flashes[:4]}")
print("DRAG_GROUPS_OK" if not _fail else f"DRAG_GROUPS_FAIL {_fail}")
sys.exit(1 if _fail else 0)
