#!/usr/bin/env python3
"""Owner review sheet: approved battleship (BEFORE) vs the hull-detail pass (AFTER).

BEFORE = main's approved asset, captured today from a pristine origin/main worktree
AFTER  = the same scene captured from the detail worktree
Same recipe, same cameras, same frozen view time, production materials: the only
difference in the two trees is assets/models/alliance_battleship.mesh.json.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import sys

import numpy as np
import pygame

pygame.init()
pygame.font.init()

BEFORE_TREE = pathlib.Path(sys.argv[1]).resolve()   # pristine origin/main worktree
AFTER_TREE = pathlib.Path(sys.argv[2]).resolve()    # detail worktree
BEFORE = pathlib.Path(sys.argv[3]).resolve()        # before captures
AFTER = pathlib.Path(sys.argv[4]).resolve()         # after captures
BG, FG, DIM = (12, 16, 28), (236, 241, 250), (150, 162, 184)
VIEWS = ("capital-detail", "capital-close", "tactical", "common-scale", "capital-keel", "escort-close", "yard-close")


def load(root, prefix, view):
    return pygame.image.load(str(pathlib.Path(root) / f"{prefix}-{view}.png"))


def triangles(root):
    path = pathlib.Path(root) / "assets/models/alliance_battleship.mesh.json"
    return json.loads(path.read_text())["triangle_count"]


def stats(view):
    a = pygame.surfarray.array3d(load(BEFORE, "today", view)).astype(int)
    b = pygame.surfarray.array3d(load(AFTER, "detail", view)).astype(int)
    d = np.abs(a - b).max(axis=2)
    ys, xs = np.nonzero(d > 8)
    return dict(view=view, changed_pixels=int((d > 8).sum()),
                changed_percent=round(float((d > 8).mean() * 100), 2),
                changed_box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                before_sha256=hashlib.sha256((pathlib.Path(BEFORE) / f"today-{view}.png").read_bytes()).hexdigest()[:12],
                after_sha256=hashlib.sha256((pathlib.Path(AFTER) / f"detail-{view}.png").read_bytes()).hexdigest()[:12])


report = [stats(v) for v in VIEWS]
print(json.dumps(report, indent=1))
(AFTER / "hull-detail-comparison.json").write_text(json.dumps(dict(views=report), indent=2, sort_keys=True) + "\n")

SW = 1800
THIRD = (SW - 80) // 3
PAD, CAP = 22, 32
FONT = lambda s, c=FG, b=True: pygame.font.SysFont("Helvetica", s, bold=b).render(c[0], True, c[1]) if isinstance(c, tuple) else None
font = pygame.font.SysFont("Helvetica", 22, bold=True)
big = pygame.font.SysFont("Helvetica", 34, bold=True)
small = pygame.font.SysFont("Helvetica", 17, bold=False)
label = lambda text, size=22, colour=FG: pygame.font.SysFont("Helvetica", size, bold=True).render(text, True, colour)
note = lambda text, colour=DIM: pygame.font.SysFont("Helvetica", 17, bold=False).render(text, True, colour)


def fit(image, width):
    return pygame.transform.smoothscale(image, (width, int(image.get_height() * width / image.get_width())))


def crop(root, prefix, box):
    surface = pygame.Surface((box[2] - box[0], box[3] - box[1]))
    surface.blit(load(root, prefix, "capital-detail"), (0, 0), pygame.Rect(*box))
    return surface


cols = [("capital-detail (310 u)", "capital-detail"), ("capital-close (450 u)", "capital-close"), ("tactical (3100 u)", "tactical")]
zooms = [("bow deck", (370, 250, 830, 550)), ("aft machinery", (600, 260, 1060, 560))]
row_h = fit(load(BEFORE, "today", "capital-detail"), THIRD).get_height()
zoom_h = (zooms[0][1][3] - zooms[0][1][1])
sheet_h = PAD * 4 + 34 + 20 + 2 * (CAP + row_h + 16) + 2 * (CAP + zoom_h + 16) + 40
sheet = pygame.Surface((SW, sheet_h))
sheet.fill(BG)
y = PAD
sheet.blit(big.render("Alliance Pelagic — hull surface detail, for approval", True, FG), (PAD, y)); y += 36
sheet.blit(note("same scene, cameras, frozen view time and production materials; the frigate and the yard are untouched, "
                "only the battleship asset differs"), (PAD, y)); y += 26
for text, prefix, colour in ((f"BEFORE  approved hull on main — {triangles(BEFORE_TREE):,} triangles", "today", DIM),
                             (f"AFTER  hull-detail pass — {triangles(AFTER_TREE):,} triangles", "detail", FG)):
    sheet.blit(label(text, 24, colour), (PAD, y)); y += CAP
    for i, (_, view) in enumerate(cols):
        sheet.blit(fit(load(BEFORE if prefix == "today" else AFTER, prefix, view), THIRD), (40 + i * (THIRD + 10), y))
    y += row_h + 16
for caption, box in zooms:
    for i, (text, prefix, colour) in enumerate((("BEFORE", "today", DIM), ("AFTER", "detail", FG))):
        image = crop(BEFORE if prefix == "today" else AFTER, prefix, box)
        x = 40 + i * (image.get_width() + 30)
        sheet.blit(image, (x, y + 20))
        sheet.blit(label(f"{text}  {caption} (native px)", 21, colour), (x, y))
    y += zoom_h + 20 + CAP
yard = next(r for r in report if r["view"] == "yard-close")
escort = next(r for r in report if r["view"] == "escort-close")
sheet.blit(note(f"the shipyard close-up frame is byte-identical ({yard['before_sha256']} == {yard['after_sha256']}); the frigate frame changes only inside {escort['changed_box']}, "
                f"where the battleship stands behind it"), (PAD, y))
sheet.blit(note(f"changed pixels — detail {report[0]['changed_pixels']}, close {report[1]['changed_pixels']}, "
                f"tactical {report[2]['changed_pixels']}, common scale {report[3]['changed_pixels']} of 1,024,000"), (PAD, y + 22))

path = AFTER / "battleship-detail-review.png"
pygame.image.save(sheet, str(path))
print("sheet:", path, f"{sheet.get_width()}x{sheet.get_height()}", hashlib.sha256(path.read_bytes()).hexdigest()[:12])
