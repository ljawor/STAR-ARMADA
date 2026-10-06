"""Real SDL/GL ownership-legibility probe.

PYTHONPATH=. .venv/bin/python tools/diag_ownership_markers.py [scratch-output-dir]

Ownership in a scrum is carried by hull tint, and the additive shield bubble
sits over every unit in the same blue — so the one channel the player could read
is the one the bubble washes out. This probe renders a fixed own-vs-hostile
scrum through the production Renderer and asserts, from the framebuffer, that:

  * an own unit gets a CHEVRON and a hostile unit a DIAMOND, distinguished by
    the icon's pixel shape (wide top vs widest mid-height), not by colour —
    measured with the other passes skipped so the bubble cannot distort it;
  * the pre-change renderer draws NOTHING in that pass (the check is not
    vacuous — a probe that fires on an unchanged build proves nothing);
  * the hull-tint channel itself moves: own hulls brighter, hostile darker;
  * the marker footprint is screen-clamped, not proportional to distance;
  * the three settings modes change markers only, never the simulation.

Two measurement notes that cost a debugging session each:

  * The marker pass must be measured with the other passes SKIPPED. The bubble
    is additive, so the hull-shade change shows through it; diffing a full new
    frame against a full control frame covers the whole bubble, not the icon.
  * The hull-tint assertion must be measured with shields DRAINED, because the
    bubble vanishes at zero by design and would otherwise dominate the patch.

The board (before_after_markers.png) is the real scene with shields up, which is
what the player actually sees.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pygame
from OpenGL import GL
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 800
LIT = 96                       # "something is drawn here" brightness floor
MIN_BLOB = 12                  # pixels; below this it is a star or edge noise

# Everything except the marker pass: markers are then measured against black.
ONLY_MARKERS = frozenset({
    "starfield", "nebulas", "star", "jumppoints", "planets", "ships",
    "shields", "effects", "projectiles", "sites", "rings",
})


def load_committed_renderer(tag: str):
    """Import renderer.py as committed at `tag`, without touching the tree.

    The control must be the PRE-CHANGE renderer; loading only the new one would
    make the comparison vacuous.
    """
    try:
        src = subprocess.run(["git", "show", f"{tag}:render/renderer.py"],
                             cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout
    except Exception as exc:
        return None, f"git show {tag}:render/renderer.py failed: {exc}"
    name = f"_ctrl_renderer_{hashlib.sha1(src.encode()).hexdigest()[:8]}"
    path = Path(tempfile.mkdtemp(prefix="armada-ctrl-")) / f"{name}.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, name


def build_scene():
    """Deterministic scrum: an own wing and a hostile wing.

    Ships come from the real unit factory rather than hand-built Entities: the
    complaint is about reading ownership THROUGH the additive shield bubble, and
    a bare Entity has no shields at all, so a hand-built scene would test an
    easier picture than the game actually shows.
    """
    from game.core.manager import GameManager
    from game.core.vectors import Vec3
    from game.data.store import DataStore

    DataStore.reset()
    ds = DataStore.get()
    game = GameManager.start_skirmish(ds.maps["skirmish01"])
    st = game.state
    st.entities.clear()
    spawn = game.factory.spawn_ship
    origin = Vec3(0, 0, 0)
    own = [spawn("imperial_corvette", 0, origin, 0.35),
           spawn("imperial_frigate", 0, origin, -0.2)]
    foe = [spawn("rebel_corvette", 1, origin, 3.3),
           spawn("rebel_frigate", 1, origin, 2.9)]
    for e, (x, z) in zip(own + foe,
                         ((-260, 0), (-120, 210), (300, 60), (620, -120))):
        e.pos.set(Vec3(x, 0, z))
        e.vel = Vec3(0, 0, 0)
        e.sensor_range = 6000.0     # a zero-range enemy is correctly unseen
    for e in own + foe:
        assert e.max_shield_total() > 0, f"{e.data_id} has no shields"
        for q in e.shields:
            e.shields[q] = e.max_shield_quad
    return game, st, own, foe


def render_frame(renderer, camera, width, height, mode=None, only_markers=False):
    if mode is not None:
        renderer.marker_mode = mode
    renderer.skip = set(ONLY_MARKERS) if only_markers else set()
    camera.width, camera.height = width, height
    GL.glViewport(0, 0, width, height)
    GL.glClearColor(0.0, 0.0, 0.0, 1.0)
    renderer.diff_render = True     # freeze the clock so frames are comparable
    renderer.draw(1.0 / 30.0, set())
    GL.glFinish()
    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    px = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
    assert GL.glGetError() == GL.GL_NO_ERROR, "GL error while rendering"
    return px


def _largest_blob(mask):
    if not mask.any():
        return []
    seen = np.zeros_like(mask, dtype=bool)
    ys, xs = np.nonzero(mask)
    best = []
    for yy, xx in zip(ys, xs):
        if seen[yy, xx]:
            continue
        q, blob = deque([(yy, xx)]), []
        seen[yy, xx] = True
        while q:
            ay, ax = q.popleft()
            blob.append((ay, ax))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                by, bx = ay + dy, ax + dx
                if 0 <= by < mask.shape[0] and 0 <= bx < mask.shape[1] \
                        and mask[by, bx] and not seen[by, bx]:
                    seen[by, bx] = True
                    q.append((by, bx))
        if len(blob) > len(best):
            best = blob
    return best


def marker_probe(frame, camera, entity, width=W, height=H):
    """Measure the icon above `entity` in a markers-only frame.

    The discriminator is the WIDTH PROFILE down the icon: a chevron's widest row
    is the solid bar at the TOP, a diamond's is the MIDDLE. Corner-cell
    occupancy was tried first and proved fragile, and diffing two full frames is
    worse still (see the module docstring).
    """
    pos = camera.world_to_screen(entity.pos.x, entity.pos.y, entity.pos.z)
    assert pos is not None, f"unit {entity.id} is off screen"
    cx, cy = int(round(pos[0])), int(round(pos[1]))
    x0, x1 = max(0, cx - 46), min(width, cx + 46)
    y0, y1 = max(0, cy - 44), max(0, min(height, cy - 1))
    if x1 <= x0 or y1 <= y0:
        return dict(px=0)
    win = frame[y0:y1, x0:x1].astype(int)
    blob = _largest_blob(win.max(axis=2) > LIT)
    if len(blob) < MIN_BLOB:
        return dict(px=len(blob))
    by = [b[0] for b in blob]
    bx = [b[1] for b in blob]
    bbox = (min(bx), min(by), max(bx), max(by))
    w_ = bbox[2] - bbox[0] + 1
    h_ = bbox[3] - bbox[1] + 1
    rows = (win.max(axis=2) > LIT)[bbox[1]:bbox[3] + 1, bbox[0]:bbox[2] + 1]
    widths = rows.sum(axis=1).astype(float)
    top = widths[:max(1, h_ // 4)].max()
    mid = widths[h_ // 4:max(h_ // 4 + 1, (3 * h_) // 4)].max()
    return dict(px=len(blob), bbox=bbox, size=(int(w_), int(h_)),
                top_ratio=float(top / w_), mid_ratio=float(mid / w_))


def hull_patch(frame, camera, entity):
    """Mean brightness of a patch on the hull body, below the marker band."""
    pos = camera.world_to_screen(entity.pos.x, entity.pos.y, entity.pos.z)
    cx, cy = int(round(pos[0])), int(round(pos[1]))
    win = frame[max(0, cy + 1):cy + 16, max(0, cx - 14):cx + 14].astype(int)
    return float(win.mean()) if win.size else 0.0


def main():
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        raise RuntimeError("This diagnostic requires a real SDL/GL window")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        os.environ.get("TMPDIR", "/tmp")) / "ownership-markers"
    out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()

    from render.camera import Camera
    import render.renderer as R
    from render import markers as mk

    game, st, own, foe = build_scene()
    camera = Camera(W, H)
    camera.target = [0.0, 0.0, 30.0]
    camera.distance = 1900.0
    camera.pitch = 52.0
    camera.yaw = 0.0

    new = R.Renderer(st, camera)
    new.local_player = 0
    new.marker_mode = "all"
    ctrl_mod, ctrl_note = load_committed_renderer("main^")
    assert ctrl_mod is not None, f"control renderer unavailable: {ctrl_note}"
    ctrl = ctrl_mod.Renderer(st, camera)
    ctrl.local_player = 0

    before = st.to_dict(precise=True)
    try:
        # ---- 1) icon shape, measured against black ------------------------
        iso = render_frame(new, camera, W, H, mode="all", only_markers=True)
        assert st.to_dict(precise=True) == before, "renderer mutated the sim"
        for e in own:
            p = marker_probe(iso, camera, e)
            assert p["px"] >= MIN_BLOB, f"own unit {e.id} has no marker ({p})"
            assert p["top_ratio"] > 0.85, \
                f"own marker {e.id} is not a chevron (top={p['top_ratio']:.2f})"
        for e in foe:
            p = marker_probe(iso, camera, e)
            assert p["px"] >= MIN_BLOB, f"hostile unit {e.id} has no marker ({p})"
            assert p["top_ratio"] < 0.70, \
                f"hostile marker {e.id} has a chevron's wide top " \
                f"({p['top_ratio']:.2f})"
            assert p["mid_ratio"] > p["top_ratio"] + 0.10, \
                f"hostile marker {e.id} is not widest mid-height ({p})"
        print("MARKER_SHAPES_OK: chevron on own, diamond on hostile")

        # ---- 2) the control draws nothing in this pass (non-vacuous) ------
        ctrl_iso = render_frame(ctrl, camera, W, H, only_markers=True)
        for e in own + foe:
            c = marker_probe(ctrl_iso, camera, e)
            assert c["px"] < MIN_BLOB, \
                f"pre-change build already drew a marker on {e.id} ({c['px']} px)"
        print("CONTROL_EMPTY_OK: pre-change renderer draws no marker")

        # ---- 3) icons are screen-clamped, not distance-proportional -------
        near = marker_probe(iso, camera, own[0])["size"][0]
        assert abs(near - mk.marker_px(0)) <= 4.0, \
            f"marker not screen-clamped: {near} px wide"
        print(f"CLAMP_OK: near marker {near} px wide "
              f"(clamped floor {mk.marker_px(0):.0f} px)")

        # ---- 4) the hull-tint channel itself moved ------------------------
        # Shields drained: the bubble vanishes at zero by design (the
        # frac <= 0.001 guard), so this reads the tint without the additive
        # wash. The board below shows the full-shield case the player sees.
        for e in own + foe:
            for q in e.shields:
                e.shields[q] = 0.0
        tint_new = render_frame(new, camera, W, H, mode="off")
        tint_old = render_frame(ctrl, camera, W, H)
        own_new = np.mean([hull_patch(tint_new, camera, e) for e in own])
        foe_new = np.mean([hull_patch(tint_new, camera, e) for e in foe])
        own_old = np.mean([hull_patch(tint_old, camera, e) for e in own])
        foe_old = np.mean([hull_patch(tint_old, camera, e) for e in foe])
        assert own_new > own_old + 1.0, \
            f"own hull not lifted ({own_new:.2f} vs {own_old:.2f})"
        assert foe_new < foe_old - 1.0, \
            f"hostile hull not darkened ({foe_new:.2f} vs {foe_old:.2f})"
        assert own_new > foe_new, \
            f"own hull not brighter than hostile ({own_new:.2f} vs {foe_new:.2f})"
        print(f"HULL_TINT_OK: own {own_old:.1f}->{own_new:.1f}, "
              f"hostile {foe_old:.1f}->{foe_new:.1f} (shields drained)")

        # ---- 5) modes gate markers only, never the simulation -------------
        counts = {}
        for mode, expect_own, expect_foe in (("hostiles", False, True),
                                             ("off", False, False)):
            f = render_frame(new, camera, W, H, mode=mode, only_markers=True)
            o = max(marker_probe(f, camera, e)["px"] for e in own)
            h = max(marker_probe(f, camera, e)["px"] for e in foe)
            counts[mode] = (o, h)
            assert (o >= MIN_BLOB) == expect_own, f"own marker, mode={mode}: {o}"
            assert (h >= MIN_BLOB) == expect_foe, f"hostile marker, mode={mode}: {h}"
        print(f"MODES_OK: {counts}")

        # ---- 6) the board the eye judges: real scene, shields restored ----
        for e in own + foe:
            for q in e.shields:
                e.shields[q] = e.max_shield_quad
        scene_old = render_frame(ctrl, camera, W, H)
        scene_new = render_frame(new, camera, W, H, mode="all")
        assert st.to_dict(precise=True) == before, "board render mutated the sim"
        board = Image.new("RGB", (W, H * 2))
        board.paste(Image.fromarray(scene_old), (0, 0))
        board.paste(Image.fromarray(scene_new), (0, H))
        board.save(out / "before_after_markers.png")
        Image.fromarray(scene_new).save(out / "all_markers.png")
        print(f"OWNERSHIP_DIAG_OK: {out / 'before_after_markers.png'}")
    finally:
        new.close()
        pygame.quit()


if __name__ == "__main__":
    main()
