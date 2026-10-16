#!/usr/bin/env python3
"""D5 evidence — capture the approved trio in the game as it stands today.

Reuses the S00 evidence harness's own scene recipe and camera specs
(artifacts/alliance_blender_trio/evidence/capture_slice.py: PLACEMENTS, VIEWS,
build_scene, configure) so the framing is identical to the approved
trio-in-game.png. Differences from the harness:

  * single source (today's main) instead of a sealed two-source before/after,
    because D5 asks one question: what does the trio look like NOW;
  * no 180-tick battle (appearance only) — every frame is the frozen view_time
    the approved captures used (renderer.time = 3.0, dt = 0);
  * production default materials (no STAR_ARMADA_FIXED_MATERIALS), recorded.

This is one frame per view, not art acceptance. It cannot approve anything.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import subprocess
import sys

TREE = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
VIEWS_WANTED = ("common-scale", "tactical", "capital-close", "capital-detail", "capital-keel", "escort-close", "yard-close")
LABEL = sys.argv[3] if len(sys.argv) > 3 else "today"
OUT.mkdir(parents=True, exist_ok=True)
os.chdir(TREE)
sys.path.insert(0, str(TREE / "artifacts" / "alliance_blender_trio" / "evidence"))
sys.path.insert(0, str(TREE))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=TREE, capture_output=True, text=True).stdout.strip()


import capture_slice as cs  # noqa: E402  (the harness lives in the tree)

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from OpenGL import GL  # noqa: E402

import game  # noqa: E402
import render  # noqa: E402

for module in (game, render):
    assert str(pathlib.Path(module.__file__).resolve()).startswith(str(TREE)), module.__file__
assert not os.environ.get("STAR_ARMADA_FIXED_MATERIALS"), "production default only"

from game.benchmark import state_hash  # noqa: E402
from render.camera import Camera  # noqa: E402
from render.hud import HUD  # noqa: E402
from render.renderer import Renderer  # noqa: E402

W, H = cs.W, cs.H
report = {
    "purpose": "D5 negative visual check: the approved trio must look exactly as approved",
    "source_tree": str(TREE),
    "source_revision": git("rev-parse", "HEAD"),
    "source_describe": git("log", "--oneline", "-1"),
    "source_clean": git("status", "--porcelain") == "",
    "assets": {p.name: sha(p) for p in sorted((TREE / "assets" / "models").glob("alliance_*.mesh.json"))},
    "view_time": 3.0,
    "mode": "single-source frozen-frame capture (no ticks, no HUD except tactical)",
    "captures": [],
}

gm, ids, recipe = cs.build_scene()
st = gm.state
report["scene"] = {"entities": {k: v for k, v in ids.items()}, "recipe_sha256": cs.digest(recipe),
                   "initial_state_sha256": state_hash(st)}

pygame.display.init()
pygame.font.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
pygame.event.pump()
GL.glEnable(GL.GL_DEPTH_TEST)
GL.glEnable(GL.GL_MULTISAMPLE)
GL.glClearColor(.008, .012, .025, 1.)
viewport = tuple(int(x) for x in GL.glGetIntegerv(GL.GL_VIEWPORT))
samples = int(GL.glGetIntegerv(GL.GL_SAMPLES))
buffers = int(GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS))
report["display"] = dict(viewport=viewport, samples=samples, sample_buffers=buffers, driver=pygame.display.get_driver(),
                         gl={k: GL.glGetString(v).decode() for k, v in
                             [("vendor", GL.GL_VENDOR), ("renderer", GL.GL_RENDERER), ("version", GL.GL_VERSION)]})
assert viewport == (0, 0, W, H) and samples == 4 and buffers == 1, report["display"]

cam = Camera(W, H)
renderer = Renderer(st, cam)
assert not renderer.skip, "renderer reported skip passes"
report["materials_available"] = renderer.materials.available
report["materials_error"] = renderer.materials.error
assert renderer.materials.available, "production default is the shader path; a fallback here is a finding"
renderer.diff_render = True
renderer.time = 3.0
hud = HUD.__new__(HUD)
hud.tex = None
HUD.__init__(hud, W, H, st)
selection = {ids["capital"]}


def frame(spec, with_hud):
    """Four draws, then a repeat read: the frame must not depend on draw order or mutate sim state."""
    for _ in range(3):
        _draw(spec, with_hud)
    before = state_hash(st)
    _draw(spec, with_hud)
    GL.glFinish()
    first = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)[::-1].copy()
    _draw(spec, with_hud)
    GL.glFinish()
    again = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)[::-1].copy()
    assert np.array_equal(first, again), "frozen repeat differs: not a deterministic frame"
    assert before == state_hash(st), "draw mutated the simulation digest"
    assert GL.glGetError() == GL.GL_NO_ERROR
    return first


def _draw(spec, with_hud):
    pygame.event.pump()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            raise RuntimeError("window closed by operator")
    cs.configure(cam, spec)
    renderer.time = 3.0
    renderer.draw(0., selection)
    if with_hud:
        hud.render(selection, None, 0, False)
        hud.draw_gl()


for name in VIEWS_WANTED:
    spec = cs.VIEWS[name]
    with_hud = name == "tactical"
    pixels = frame(spec, with_hud)
    path = OUT / f"{LABEL}-{name}.png"
    pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (W, H), "RGB"), str(path))
    report["captures"].append(dict(
        name=name, image=path.name, image_sha256=sha(path),
        spec=spec, with_hud=with_hud, view_time=3.0,
        lit_pixels=int((pixels.max(axis=2) > 12).sum()),
        pixels_sha256=hashlib.sha256(pixels.tobytes()).hexdigest()))

report["status"] = "captured-frozen-frames-for-owner-visual-check"
(OUT / "d5-report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
print(json.dumps({k: report[k] for k in ("status", "source_revision", "source_describe", "source_clean",
                                        "materials_available", "display")}, indent=1))
for c in report["captures"]:
    print(f"  {c['name']:14s} {c['image']:26s} {c['image_sha256'][:12]} lit={c['lit_pixels']:7d} hud={c['with_hud']}")
print("report:", OUT / "d5-report.json")
pygame.quit()
