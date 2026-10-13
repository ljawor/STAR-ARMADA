"""#90 acceptance: measure the RENDERED footprint of each weapon family.

The unit tests pin the shape maths; this renders real frames and measures each
projectile's bounding box in pixels, so "lasers look like laser bolts and
torpedoes like squares" is checked against actual GL output rather than the
intent of the code.

It measures the same scene twice: once through the shipped path, once with the
shape classification forced back to the old single round treatment, so the
before/after numbers are visible side by side.

Run from the repo root with a real video driver (a dummy driver cannot create a
GL context):

    .venv/bin/python tools/diag_weapon_fire_look.py --out ~/.hermes/cache/scratch/fire90
"""
import argparse
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
# one projectile per family, all at the same camera depth so px-per-world is
# identical for every measurement
# (weapon id, label, heading as (screen-right, screen-up), family)
SPECIMENS = [
    ("laser_cannon", "laser_cannon", (1.0, 0.0), "bolt"),
    ("heavy_turbolaser", "heavy_turbolaser", (1.0, 0.0), "bolt"),
    ("proton_torpedo", "proton_torpedo", (1.0, 0.0), "square"),
    ("missile_battery", "missile_battery", (1.0, 0.0), "square"),
    ("planet_pulsar_beam", "planet_pulsar_beam", (1.0, 0.0),
     "legacy (super weapon: unchanged)"),
    # Diagonal headings: a square oriented by its heading would be a diamond
    # here (fill ~0.5 instead of 1.0), which the axis-aligned row cannot show.
    ("laser_cannon", "laser (diagonal)", (1.0, 1.0), "bolt"),
    ("proton_torpedo", "torpedo (diagonal)", (1.0, -1.0), "square"),
]
SPACING_PX = 150.0
# Specimens sit in empty space in FRONT of, and clear of, the player's own hull.
# Projectiles are drawn with depth WRITES off, so a ship drawn afterwards paints
# over a projectile sitting on the same pixels — the centre specimen measured
# 0 px until the row was lifted above the silhouette.
DEPTH = 700.0
ROW_LIFT_PX = 240.0


def _elongation(xs, ys):
    """How elongated a lit mask is, independent of its angle.

    Bounding-box aspect only works while a bolt happens to travel along a screen
    axis: a 45-degree bolt has a SQUARE box however thin it is, so the box metric
    reported a perfect diagonal bolt as round. The ratio of the second moments
    (covariance eigenvalues) measures the same thing at any heading.
    """
    if len(xs) < 4:
        return 0.0
    pts = np.stack([xs.astype(float), ys.astype(float)])
    values = np.linalg.eigvalsh(np.cov(pts))
    return float(np.sqrt(max(values[1], 1e-9) / max(values[0], 1e-9)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "saves", "weapon_fire_look"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)

    from game.core.entity import Entity                    # noqa: E402
    from game.core.manager import GameManager              # noqa: E402
    from game.core.vectors import Vec3                     # noqa: E402
    from game.core.world import Projectile                 # noqa: E402
    from game.data.store import DataStore                  # noqa: E402
    from render.camera import Camera                       # noqa: E402
    from render.renderer import Renderer                   # noqa: E402
    import render.renderer as renderer_mod                 # noqa: E402

    DataStore.reset()
    ds = DataStore()
    gm = GameManager.start_skirmish(ds.maps["skirmish01"])
    st = gm.state

    own = next(e for e in st.entities.values()
               if e.owner == 0 and e.is_ship and not e.is_planet)
    anchor = own.pos

    cam = Camera(W, H)
    cam.target = [anchor.x, anchor.y, anchor.z]
    cam.yaw, cam.pitch, cam.distance = 35.0, 24.0, 900.0
    r = Renderer(st, cam)
    r.time = 2.0

    # world units per pixel at the specimens' depth (same maths the renderer uses)
    half_fov_tan = math.tan(math.radians(cam.fov / 2))
    px_per_world = cam.height / (2.0 * DEPTH * half_fov_tan)
    spacing = SPACING_PX / px_per_world
    right, up, _fwd = cam.basis()
    eye = cam.eye_position()
    lift = ROW_LIFT_PX / px_per_world      # lift the whole row off the hull

    def at(depth, right_u=0.0, up_u=0.0):
        return Vec3(eye[0] + _fwd[0] * depth + right[0] * right_u + up[0] * up_u,
                    eye[1] + _fwd[1] * depth + right[1] * right_u + up[1] * up_u,
                    eye[2] + _fwd[2] * depth + right[2] * right_u + up[2] * up_u)

    st.projectiles.clear()
    slots = []
    made = {}
    for i, (weapon_id, label, (heading_u, heading_v), _family) in enumerate(SPECIMENS):
        wd = ds.weapons[weapon_id]
        u = (i - (len(SPECIMENS) - 1) / 2.0) * spacing
        pos = at(DEPTH, right_u=u, up_u=lift)
        vx = right[0] * heading_u + up[0] * heading_v
        vy = right[1] * heading_u + up[1] * heading_v
        vz = right[2] * heading_u + up[2] * heading_v
        pid = 9000 + i
        st.projectiles[pid] = Projectile(
            id=pid, owner=0, weapon_id=weapon_id, pos=pos,
            vel=Vec3(vx * 1200.0, vy * 1200.0, vz * 1200.0),
            target_id=-1, damage=10.0, shield_mult=1.0, armor_mult=1.0,
            system_mult=1.0, life=9.0, color=tuple(wd.color), size=float(wd.size))
        made[pid] = st.projectiles[pid]
        slots.append((pid, label, u))

    # one bolt fired straight at the camera: no screen-space heading at all
    head_pos = at(DEPTH, up_u=-lift)
    head_on = Projectile(
        id=9999, owner=0, weapon_id="laser_cannon",
        pos=head_pos,
        vel=Vec3(-_fwd[0] * 1200.0, -_fwd[1] * 1200.0, -_fwd[2] * 1200.0),
        target_id=-1, damage=10.0, shield_mult=1.0, armor_mult=1.0,
        system_mult=1.0, life=9.0, color=tuple(ds.weapons["laser_cannon"].color),
        size=float(ds.weapons["laser_cannon"].size))
    st.projectiles[head_on.id] = head_on
    made[head_on.id] = head_on

    def screen_xy(pos):
        # pinhole projection relative to the EYE: a lateral offset is
        # perpendicular to the view axis and so carries no depth itself
        d = (pos.x - eye[0], pos.y - eye[1], pos.z - eye[2])
        along = sum(d[i] * _fwd[i] for i in range(3))
        if along <= 1.0:
            return None
        sx = W / 2.0 + (sum(d[i] * right[i] for i in range(3)) / along) * (H / 2.0) / half_fov_tan
        sy = H / 2.0 - (sum(d[i] * up[i] for i in range(3)) / along) * (H / 2.0) / half_fov_tan
        return sx, sy

    centre = screen_xy(anchor)
    print(f"projection check: anchor projects to {centre} (expect ~{W / 2:.0f}, {H / 2:.0f})")

    def frame():
        for _ in range(3):
            glClearColor(0.0, 0.0, 0.0, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            r.draw(1 / 30, set())
        glFinish()
        raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
        img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
        arr = np.frombuffer(pygame.image.tobytes(img, "RGB"),
                            dtype=np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
        # GL reads bottom-up; flip so row 0 is the top of the screen
        return np.flipud(arr)

    def save(arr, name):
        # `arr` is already top-row-first (frame() flips the bottom-up GL read),
        # and pygame treats the first row as the top: flipping again here would
        # export a mirrored image.
        path = os.path.join(args.out, name)
        pygame.image.save(pygame.image.frombuffer(
            (arr * 255.0).astype(np.uint8).tobytes(), (W, H), "RGB"), path)
        return path

    for pid in list(st.projectiles):
        del st.projectiles[pid]
    background = frame()
    st.projectiles = dict(made)

    def measure(base, label):
        arr = frame()
        diff = np.clip(arr - base, 0.0, None).max(axis=2)
        rows = []
        # NB: the specimen's own name, not `label` — that is measure()'s pass
        # name, and shadowing it mislabelled both report tables (found by reading
        # the output, which printed "torpedo (diagonal)" over the shipped table).
        for pid, spec_label, u in slots:
            xy = screen_xy(st.projectiles[pid].pos)
            if xy is None:
                rows.append((spec_label, None, None, None, 0, 0.0))
                continue
            cx, cy = int(round(xy[0])), int(round(xy[1]))
            half = int(SPACING_PX / 2.0) - 2
            x0, x1 = max(0, cx - half), min(W, cx + half)
            y0, y1 = max(0, cy - half), min(H, cy + half)
            ys, xs = np.nonzero(diff[y0:y1, x0:x1] > 0.05)
            if not len(xs):
                rows.append((spec_label, 0, 0, None, 0, 0.0))
                continue
            bw = int(xs.max() - xs.min()) + 1
            bh = int(ys.max() - ys.min()) + 1
            # fill: a flat quad lights its whole bounding box, a radial glow only
            # the disc inside it (~pi/4). This is what separates a square
            # torpedo from a round blob, which the bbox aspect alone cannot.
            # paleness: an additive halo over a brightened core sums past 1.0 and
            # bleaches the bolt white, throwing away the per-weapon colour. Count
            # lit pixels whose darkest channel is still near-saturated.
            lit = arr[y0:y1, x0:x1][ys, xs]      # RGB of the lit pixels
            pale = float((lit.min(axis=1) > 0.8).mean())
            rows.append((spec_label, bw, bh, bw / float(bh), int(len(xs)),
                         len(xs) / float(bw * bh), _elongation(xs, ys), pale))
            print(f"    [at] {spec_label:<20} screen=({cx},{cy}) lit-centre="
                  f"({x0 + int(xs.mean())},{y0 + int(ys.mean())})")
        hx = screen_xy(head_on.pos)
        head_row = None
        if hx is not None:
            cx, cy = int(round(hx[0])), int(round(hx[1]))
            x0, x1 = max(0, cx - 70), min(W, cx + 70)
            y0, y1 = max(0, cy - 70), min(H, cy + 70)
            ys, xs = np.nonzero(diff[y0:y1, x0:x1] > 0.05)
            if len(xs):
                bw = int(xs.max() - xs.min()) + 1
                bh = int(ys.max() - ys.min()) + 1
                head_row = (bw, bh, bw / float(bh), int(len(xs)),
                            _elongation(xs, ys))
        print(f"\n--- {label} ---")
        print(f"{'weapon':<20}{'bbox w':>8}{'bbox h':>8}{'aspect':>8}{'fill':>7}"
              f"{'elong':>7}{'pale':>7}{'px':>7}  family")
        for (label, bw, bh, aspect, n, fill, elong, pale), (_wid, _lbl, _h, family) \
                in zip(rows, SPECIMENS):
            w_txt = "-" if bw is None else str(bw)
            h_txt = "-" if bh is None else str(bh)
            a_txt = f"{aspect:.2f}" if aspect else "-"
            f_txt = f"{fill:.2f}" if fill else "-"
            e_txt = f"{elong:.2f}" if elong else "-"
            p_txt = f"{pale:.2f}" if pale is not None else "-"
            print(f"{label:<20}{w_txt:>8}{h_txt:>8}{a_txt:>8}{f_txt:>7}{e_txt:>7}"
                  f"{p_txt:>7}{n:>7}  {family}")
        if head_row:
            print(f"{'laser (head-on)':<20}{head_row[0]:>8}{head_row[1]:>8}"
                  f"{head_row[2]:>8.2f}{'':>7}{head_row[4]:>7.2f}{head_row[3]:>7}"
                  f"  streak, not a dot")
        return rows, head_row, arr

    shipped_rows, shipped_head, shipped_arr = measure(background, "shipped path")
    shipped_png = save(shipped_arr, "fire_look_after.png")

    # same scene, shape classification forced back to the old round treatment
    shipped_shape = renderer_mod.projectile_shape
    renderer_mod.projectile_shape = lambda weapon_type: "legacy"
    legacy_rows, legacy_head, legacy_arr = measure(background, "pre-fix behaviour (shapes disabled)")
    legacy_png = save(legacy_arr, "fire_look_before.png")
    renderer_mod.projectile_shape = shipped_shape

    # A close-up pass purely for eyeballing: at tactical zoom a bolt is a few
    # pixels, so the shapes are only legible when the camera is near. 420 units
    # is a realistic close-combat zoom; the specimens were briefly measured at
    # 150, where a size-4.5 turbolaser bolt is larger than a fighter and the
    # frame stops representing anything a player sees.
    cam.distance, cam.pitch = 420.0, 14.0
    close_right, close_up, close_fwd = cam.basis()
    close_eye = cam.eye_position()
    close_depth = 260.0
    close_px = cam.height / (2.0 * close_depth * half_fov_tan)
    close_lift = 120.0 / close_px
    st.projectiles.clear()
    headings = [("laser_cannon", 1.0, 1.0), ("heavy_turbolaser", 1.0, 0.0),
                ("proton_torpedo", 1.0, -1.0), ("interceptor_cannon", 0.0, 1.0),
                ("missile_battery", 1.0, 0.35), ("planet_pulsar_beam", 1.0, 0.0)]
    for i, (weapon_id, ru, uu) in enumerate(headings):
        wd = ds.weapons[weapon_id]
        u = (i - (len(headings) - 1) / 2.0) * (75.0 / close_px)
        pos = Vec3(close_eye[0] + close_fwd[0] * close_depth + close_right[0] * u
                   + close_up[0] * close_lift,
                   close_eye[1] + close_fwd[1] * close_depth + close_right[1] * u
                   + close_up[1] * close_lift,
                   close_eye[2] + close_fwd[2] * close_depth + close_right[2] * u
                   + close_up[2] * close_lift)
        vx = close_right[0] * ru + close_up[0] * uu
        vy = close_right[1] * ru + close_up[1] * uu
        vz = close_right[2] * ru + close_up[2] * uu
        st.projectiles[9500 + i] = Projectile(
            id=9500 + i, owner=0, weapon_id=weapon_id, pos=pos,
            vel=Vec3(vx * 900.0, vy * 900.0, vz * 900.0), target_id=-1,
            damage=10.0, shield_mult=1.0, armor_mult=1.0, system_mult=1.0,
            life=9.0, color=tuple(wd.color), size=float(wd.size))
    close_png = save(frame(), "fire_look_close.png")

    failures = []
    for (wid, bw, bh, aspect, _n, fill, elong, pale), (_w, _lbl, _h, family) \
            in zip(shipped_rows, SPECIMENS):
        if aspect is None:
            failures.append(f"{wid}: nothing rendered")
            continue
        # Elongation, not bbox aspect: a bolt at 45 degrees has a square box.
        if family == "bolt" and elong < 2.5:
            failures.append(f"{wid}: bolt elongation {elong:.2f} < 2.5")
        if family == "square" and not (0.6 <= aspect <= 1.67):
            failures.append(f"{wid}: square aspect {aspect:.2f} outside 0.6-1.67")
        if family == "square" and fill < 0.95:
            # A square oriented by its heading fills ~0.5 of its box: a diamond.
            failures.append(f"{wid}: shaped quad only fills {fill:.2f} of its box")
        if family in ("bolt", "square") and pale > 0.45:
            failures.append(f"{wid}: {pale:.2f} of the bolt renders as white "
                            f"(weapon colour lost)")
        if family.startswith("legacy") and (fill > 0.86 or elong > 1.35):
            failures.append(f"{wid}: super weapon stopped being a round glow "
                            f"(fill {fill:.2f}, elong {elong:.2f})")
    if shipped_head is None:
        failures.append("head-on laser rendered nothing")
    elif shipped_head[4] < 2.5:
        failures.append(f"head-on laser collapsed to {shipped_head[0]}x{shipped_head[1]} px "
                        f"(elong {shipped_head[4]:.2f})")
    # the old path must NOT have satisfied the new bars, or this proves nothing
    legacy_lasers = [r for r, s in zip(legacy_rows, SPECIMENS) if s[3].startswith("bolt")]
    for (wid, bw, bh, aspect, _n, fill, elong, _p) in legacy_lasers:
        if aspect is not None and elong >= 2.5:
            failures.append(f"pre-fix path already elongated for {wid} ({elong:.2f})")
    legacy_glows = [r for r, s in zip(legacy_rows, SPECIMENS)
                    if s[3].startswith("legacy") or s[3] == "square"]
    for (wid, bw, bh, aspect, _n, fill, elong, _p) in legacy_glows:
        if fill is not None and fill >= 0.95:
            failures.append(f"pre-fix path already filled its box for {wid} ({fill:.2f})")
    if legacy_head is not None and legacy_head[4] >= 2.5:
        failures.append(f"pre-fix path already drew a head-on streak "
                        f"(elong {legacy_head[4]:.2f})")

    print(f"\nsaved {shipped_png}\nsaved {legacy_png}")
    if failures:
        print("\nFAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nOK: bolts render elongated, torpedoes square, super weapons unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
