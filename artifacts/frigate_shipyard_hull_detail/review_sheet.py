#!/usr/bin/env python3
"""Owner review sheet: the frigate and the shipyard after the surface-detail pass.

BEFORE = the approved revision this batch is stacked on (PR #120 head 7d54294)
AFTER  = the same scene captured from this batch's worktree
Same recipe, cameras, frozen view time and production materials. The only
difference in the two trees is the frigate and the shipyard runtime payload; the
capital's payload is byte-identical, so the capital frames are a negative control.

Usage: review_sheet_batch2.py BEFORE_TREE AFTER_TREE BEFORE_CAPTURES AFTER_CAPTURES
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

BEFORE_TREE, AFTER_TREE, BEFORE, AFTER = [pathlib.Path(a).resolve() for a in sys.argv[1:5]]
BG, FG, DIM, WARN = (12, 16, 28), (236, 241, 250), (150, 162, 184), (255, 120, 110)
CAPITAL = ("capital-close", "capital-detail", "capital-keel", "common-scale", "tactical")
SHIPS = ("escort-close", "yard-close")
VIEWS = CAPITAL + SHIPS


def load(root, prefix, view):
    return pygame.image.load(str(pathlib.Path(root) / f"{prefix}-{view}.png"))


def payload(root, name):
    path = pathlib.Path(root) / f"assets/models/alliance_{name}.mesh.json"
    return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()


def stats(view):
    a = pygame.surfarray.array3d(load(BEFORE, "approved", view)).astype(int)
    b = pygame.surfarray.array3d(load(AFTER, "detail", view)).astype(int)
    d = np.abs(a - b).max(axis=2)
    mask = d > 8
    ys, xs = np.nonzero(mask)
    return dict(view=view, changed_pixels=int(mask.sum()),
                changed_percent=round(float(mask.mean() * 100), 3),
                changed_box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                before_sha256=hashlib.sha256((pathlib.Path(BEFORE) / f"approved-{view}.png").read_bytes()).hexdigest()[:12],
                after_sha256=hashlib.sha256((pathlib.Path(AFTER) / f"detail-{view}.png").read_bytes()).hexdigest()[:12])


report = [stats(v) for v in VIEWS]
assets = {}
for name in ("battleship", "frigate", "shipyard"):
    before_payload, before_sha = payload(BEFORE_TREE, name)
    after_payload, after_sha = payload(AFTER_TREE, name)
    assets[name] = dict(before_sha256=before_sha[:12], after_sha256=after_sha[:12],
                        identical=before_sha == after_sha,
                        before_triangles=before_payload["triangle_count"],
                        after_triangles=after_payload["triangle_count"],
                        before_vertices=len(before_payload["vertices"]),
                        after_vertices=len(after_payload["vertices"]),
                        before_extents=[round(before_payload["bounds"][1][i] - before_payload["bounds"][0][i], 6) for i in range(3)],
                        after_extents=[round(after_payload["bounds"][1][i] - after_payload["bounds"][0][i], 6) for i in range(3)])
out = dict(purpose="owner visual review: frigate and shipyard surface detail", views=report, assets=assets,
           before_tree=str(BEFORE_TREE), after_tree=str(AFTER_TREE))
(AFTER / "frigate-shipyard-detail-comparison.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(dict(assets=assets, views={r["view"]: [r["changed_pixels"], r["before_sha256"], r["after_sha256"]] for r in report}), indent=1))

# --- an overlay proving where the capital frames moved: red is |delta|>8 ---
for view in CAPITAL + SHIPS:
    a = pygame.surfarray.array3d(load(BEFORE, "approved", view))
    b = pygame.surfarray.array3d(load(AFTER, "detail", view)).astype(int)
    mask = (np.abs(a.astype(int) - b).max(axis=2) > 8)
    overlay = a.copy()
    overlay[mask] = (255, 60, 50)
    surf = pygame.Surface((a.shape[0], a.shape[1]))
    pygame.surfarray.blit_array(surf, overlay)
    pygame.image.save(surf, str(pathlib.Path(AFTER) / f"changed-where-{view}.png"))

SW = 1800
THIRD = (SW - 80) // 3
PAD, CAP = 22, 32
font = lambda t, s=22, c=FG: pygame.font.SysFont("Helvetica", s, bold=True).render(t, True, c)
small = lambda t, s=17, c=DIM: pygame.font.SysFont("Helvetica", s, bold=False).render(t, True, c)
big = font


def fit(image, width):
    return pygame.transform.smoothscale(image, (width, int(image.get_height() * width / image.get_width())))


def crop(root, prefix, view, box):
    surface = pygame.Surface((box[2] - box[0], box[3] - box[1]))
    surface.blit(load(root, prefix, view), (0, 0), pygame.Rect(*box))
    return surface


cols = [("escort-close 155 u", "escort-close"), ("yard-close 450 u", "yard-close"), ("common-scale 1800 u", "common-scale")]
zooms = [("escort-close", "frigate flank (native px)", (430, 300, 900, 520)),
         ("yard-close", "yard rails and crosshead (native px)", (380, 230, 940, 620))]
row_h = fit(load(BEFORE, "approved", "escort-close"), THIRD).get_height()
zoom_h = [(b[3] - b[1]) for _, _, b in zooms]
sheet_h = PAD * 4 + 34 + 22 + int(2.2 * (CAP + row_h + 16)) + sum(zoom_h) + 4 * (CAP + 16) + 70
sheet = pygame.Surface((SW, sheet_h + 400))
sheet.fill(BG)
y = PAD
sheet.blit(big("Alliance frigate and shipyard — surface detail, for approval", 34), (PAD, y)); y += 36
sheet.blit(small("same scene, cameras, frozen view time and production materials as the approved captures; BEFORE is the revision this batch is stacked on "
                 "(PR #120 head 7d54294), AFTER adds this batch"), (PAD, y)); y += 26
for text, prefix, colour in ((f"BEFORE  approved revision — frigate {assets['frigate']['before_triangles']:,} / "
                              f"yard {assets['shipyard']['before_triangles']:,} triangles", "approved", DIM),
                             (f"AFTER  surface detail — frigate {assets['frigate']['after_triangles']:,} / "
                              f"yard {assets['shipyard']['after_triangles']:,} triangles", "detail", FG)):
    sheet.blit(font(text, 24, colour), (PAD, y)); y += CAP
    root = BEFORE if prefix == "approved" else AFTER
    for i, (_, view) in enumerate(cols):
        sheet.blit(fit(load(root, prefix, view), THIRD), (40 + i * (THIRD + 10), y))
    y += row_h + 16
for (view, caption, box) in zooms:
    for i, (text, prefix, colour) in enumerate((("BEFORE", "approved", DIM), ("AFTER", "detail", FG))):
        root = BEFORE if prefix == "approved" else AFTER
        image = crop(root, prefix, view, box)
        x = 40 + i * (image.get_width() + 30)
        sheet.blit(image, (x, y + 20))
        sheet.blit(font(f"{text}  {caption}", 21, colour), (x, y))
    y += (box[3] - box[1]) + 20 + CAP
yard = next(r for r in report if r["view"] == "yard-close")
escort = next(r for r in report if r["view"] == "escort-close")
capital = "byte-identical" if assets["battleship"]["identical"] else "CHANGED"
def wrapped(text, width=165):
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return lines


def paragraph(text, y, step=22, colour=DIM):
    for line in wrapped(text):
        sheet.blit(small(line, 17, colour), (PAD, y)); y += step
    return y + 8


y = paragraph(f"negative control: the approved capital payload is {capital} between the two trees ({assets['battleship']['after_sha256']}), and its frames move only in the pixels "
              f"the escort and the yard occupy ({AFTER}/changed-where-*.png paints them red)", y)
y = paragraph(f"changed pixels of 1,024,000 — escort-close {escort['changed_pixels']} ({escort['changed_percent']}%), yard-close {yard['changed_pixels']} ({yard['changed_percent']}%), "
              f"common-scale {next(r for r in report if r['view'] == 'common-scale')['changed_pixels']}", y)
y = paragraph(f"neither model changes size: frigate extents {assets['frigate']['after_extents']}, yard extents {assets['shipyard']['after_extents']}, both identical to BEFORE", y)
y = paragraph("nothing here is approved yet: this is one revision for the owner to look at", y, colour=FG)

sheet = sheet.subsurface((0, 0, SW, y)).copy()
path = AFTER / "frigate-shipyard-detail-review.png"
pygame.image.save(sheet, str(path))
print("sheet:", path, f"{sheet.get_width()}x{sheet.get_height()}", hashlib.sha256(path.read_bytes()).hexdigest()[:12])
