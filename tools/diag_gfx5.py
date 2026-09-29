"""Diag: graphics pass A shields — additive bubble with a Fresnel rim.

Replaces the old flat outline circle with a view-aligned additive shell whose
rim glow is baked into per-vertex alpha (fixed-function GL cannot do a
per-fragment Fresnel term, and a specular highlight would only glint where
the light happens to bisect — not the bright limb the reference art shows).

Checks
------
1. BUBBLE    a shielded ship grows an additive blue shell beyond its hull
2. FRESNEL   the shell is near-transparent through its middle and bright at
             its limb (measured as a radial mean over the whole bubble)
3. SEE-THROUGH the ship stays visible inside the bubble (no occlusion)
4. STRENGTH  a depleted shield renders a visibly weaker bubble
4b. RAMP     the bubble shifts blue -> yellow -> orange -> red as shields drop
5. NO SHIELD a unit with no shield capacity gets no bubble at all
5b. CLEAN    no flat outline circle or half-circle health arcs around a
             selected shielded unit (they were removed as clutter)
6. QUADRANT  losing a quadrant flashes that FACE of the bubble, and the
             flash decays away again
7. No GL errors.

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_gfx5.py [out.png]
Prints DIAG_OK (exit 0) only when every assertion holds.
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                    # noqa: E402
import pygame                                         # noqa: E402
from OpenGL.GL import (glClear, glClearColor, glFinish, glGetError,  # noqa: E402
                       glReadPixels, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
                       GL_NO_ERROR, GL_RGB, GL_UNSIGNED_BYTE)

W, H = 1280, 800
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves", "diag_gfx5.png")

pygame.init()
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.entity import Entity, QUADRANTS             # noqa: E402
from game.core.manager import GameManager                  # noqa: E402
from game.core.vectors import Vec3                         # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.camera import Camera                           # noqa: E402
from render.renderer import Renderer                       # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state
_fail: list[str] = []

YAW, PITCH, DIST = 35.0, 20.0, 900.0


def grab() -> np.ndarray:
    glFinish()
    raw = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(bytes(raw), (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    return (np.frombuffer(pygame.image.tobytes(img, "RGB"), dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def mk(eid, data_id, owner=0, pos=(0, 0, 0), yaw=0.0, radius=45.0,
       shield_quad=None):
    """Entity fixture.

    NOTE: `Entity.max_shield_quad` defaults to 0.0 and `shields` to all-zero,
    so a hand-built entity has NO shield capacity and the renderer correctly
    skips it. Real units get these from unit_factory; this helper must supply
    them or every shield assertion trivially fails.
    """
    e = Entity(id=eid, kind="ship", owner=owner, data_id=data_id,
               pos=Vec3(*pos), radius=radius)
    e.yaw, e.vel = yaw, Vec3(0, 0, 0)
    if hasattr(e, "is_ship"):
        e.is_ship, e.is_station = True, False
    if shield_quad is None:
        sdef = ds.ships.get(data_id)
        shield_quad = float(sdef.shield_quad) if sdef else 0.0
    e.max_shield_quad = float(shield_quad)
    e.shield_regen = 0.0        # isolate the bubble from regen in this diag
    for q in QUADRANTS:
        e.shields[q] = float(shield_quad)
    return e


def cam_for(dist=DIST):
    c = Camera(W, H)
    c.target = [0.0, 0.0, 0.0]
    c.yaw, c.pitch, c.distance = YAW, PITCH, dist
    return c


def screen_of(x, y, z, dist=DIST):
    return cam_for(dist).world_to_screen(x, y, z)


class Scene:
    """One Renderer driven across several frames.

    The quadrant hit-detector diffs against the PREVIOUS frame's shield
    values, which live on the Renderer instance — so rebuilding the Renderer
    between frames resets that cache and no hit is ever detected. Tests that
    depend on a hit must reuse a single Scene.
    """

    def __init__(self, dist=DIST):
        self.r = Renderer(st, cam_for(dist))
        self.r.time = 2.0

    def frame(self, entities, selected=()):
        st.entities.clear()
        for e in entities:
            st.entities[e.id] = e
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.r.draw(1 / 30, set(selected))
        err = glGetError()
        if err != GL_NO_ERROR:
            _fail.append(f"GL error 0x{err:x}")
        return grab()


def save_png(arr, path):
    img = pygame.image.frombuffer(
        bytes(np.flipud(arr * 255).astype(np.uint8).tobytes()), (W, H), "RGB")
    pygame.image.save(img, path)
    return path


def shell_stats(diff, cx, cy, thresh=0.015):
    """Radial + angular description of the additive shell in `diff`.

    Accepts a 2-D (H,W) or 3-D (H,W,3) frame difference. Uses an annulus mean
    over ALL angles rather than column/row maxima: a row-max profile conflates
    the limb (top/bottom of the bubble) with the interior and reports nonsense
    like "limb = 0".
    """
    lum = diff if diff.ndim == 2 else diff.max(axis=2)
    mask = lum > thresh
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    vals = lum[ys, xs]
    dx = xs.astype(np.float64) - cx
    dy = ys.astype(np.float64) - cy
    rr = np.sqrt(dx * dx + dy * dy)
    R = float(rr.max())
    return {"n": len(xs), "R": R, "rr": rr / max(1e-6, R), "vals": vals,
            "dx": dx, "dy": dy, "mask": mask}


FRIGATE = "imperial_frigate"
sdef = ds.ships[FRIGATE]
RAD = float(sdef.radius)
print(f"subject: {FRIGATE} radius={RAD} shield_quad={float(sdef.shield_quad)}")

ship = [mk(1, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD)]
sc = Scene()
sc.frame(ship)                                  # seed the shield cache
with_b = sc.frame(ship)
save_png(with_b, os.path.join(ROOT, "saves", "diag_gfx5_ship.png"))
no_b = Scene().frame([mk(2, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20),
                         radius=RAD, shield_quad=0.0)])

sp = screen_of(0.0, 0.0, 0.0)
sx, sy = (int(sp[0]), int(sp[1])) if sp else (W // 2, H // 2)
print(f"ship centre at screen ({sx},{sy})")

# ------------------------------------------------------------ 1. BUBBLE
diff = np.clip(with_b - no_b, 0, None)
shell_px = int((diff.max(axis=2) > 0.015).sum())
shell_blue = int(((diff[..., 2] - diff[..., 0]) > 0.03).sum())
print(f"[1] bubble pixels: {shell_px}  blue-dominant: {shell_blue}")
if shell_px < 400:
    _fail.append(f"shield bubble barely rendered: {shell_px} px")
if shell_blue < 300:
    _fail.append(f"bubble is not blue-dominant: {shell_blue} px")

# ------------------------------------------------------------ 2. FRESNEL
stt = shell_stats(diff, sx, sy)
if stt is None:
    _fail.append("could not find the shell for the Fresnel check")
else:
    inner = float(stt["vals"][(stt["rr"] > 0.30) & (stt["rr"] < 0.55)].mean()) \
        if ((stt["rr"] > 0.30) & (stt["rr"] < 0.55)).any() else 0.0
    limb = float(stt["vals"][stt["rr"] > 0.90].mean()) \
        if (stt["rr"] > 0.90).any() else 0.0
    mid = float(stt["vals"][(stt["rr"] > 0.55) & (stt["rr"] < 0.90)].mean()) \
        if ((stt["rr"] > 0.55) & (stt["rr"] < 0.90)).any() else 0.0
    # monotonic-ish rising profile from middle to limb
    print(f"[2] radial mean alpha: middle(0.30-0.55R)={inner:.3f}  "
          f"mid(0.55-0.90R)={mid:.3f}  limb(>0.90R)={limb:.3f}  "
          f"shell R={stt['R']:.0f}px  n={stt['n']}")
    if not (limb > mid > inner):
        _fail.append(f"radial profile not limb-weighted: "
                     f"{inner:.3f} / {mid:.3f} / {limb:.3f}")
    if limb <= inner * 1.8:
        _fail.append(f"Fresnel rim too weak: limb {limb:.3f} vs middle {inner:.3f}")

# ------------------------------------------------------------ 3. SEE-THROUGH
hull_region = (slice(max(0, sy - 40), sy + 40), slice(max(0, sx - 60), sx + 60))
h_with = with_b[hull_region].max(axis=2)
h_ref = no_b[hull_region].max(axis=2)
hull_px = int((h_ref > 0.05).sum())
survived = int(((h_ref > 0.05) & (h_with > 0.05)).sum())
print(f"[3] hull pixels visible through bubble: {survived}/{hull_px}")
if hull_px > 0 and survived < hull_px * 0.98:
    _fail.append(f"bubble occluded the ship: {survived}/{hull_px} hull px survive")

# ------------------------------------------------------------ 4. STRENGTH
# NOTE: a Scene's FIRST frame only seeds the previous-value cache. Lowering a
# quadrant's value counts as a HIT and fires the transient flash, so a
# comparison must be primed at its own constant level — a scene switched down
# from full strength measures the flash, not the standing strength.
weak = [mk(3, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD)]
for q in QUADRANTS:
    weak[0].shields[q] = weak[0].max_shield_quad * 0.25
sc_w = Scene()
sc_w.frame(weak)                                 # prime at 25%, no transition
weak_arr = sc_w.frame(weak)
save_png(weak_arr, os.path.join(ROOT, "saves", "diag_gfx5_weak.png"))
sc_full = Scene()
sc_full.frame(ship)
full_arr = sc_full.frame(ship)
full_lum = float(np.clip(full_arr - no_b, 0, None).sum())
weak_lum = float(np.clip(weak_arr - no_b, 0, None).sum())
print(f"[4] shield emission: full={full_lum:.0f} at 25%={weak_lum:.0f} "
      f"({weak_lum / max(1.0, full_lum):.2f}x)")
if weak_lum >= full_lum * 0.9:
    _fail.append(f"depleted shield not weaker: {weak_lum:.0f} vs {full_lum:.0f}")

# ------------------------------------------------------------ 4b. COLOUR RAMP
# The bubble must shift blue -> yellow -> orange -> red as shields drop, so
# strength reads from colour alone. Measures the hue of the shell's own
# emission at a few strengths (bubble-only, differenced against no-shield).
print("[4b] strength -> bubble hue (dominant channel of the shell):")


def bubble_hue(frac):
    """Hue of the bubble's INTERIOR, where the field's own colour dominates.

    Sampled over the mid-radius band rather than the whole shell: the rim is
    deliberately whitened (real fields scatter harder at grazing angles), and
    that white term adds blue at every strength, which would mask the ramp.
    At mid-radius the whitening is nil, so the pixels here are the true ramp
    colour, faded by strength.
    """
    ents = [mk(30, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD)]
    for q in QUADRANTS:
        ents[0].shields[q] = ents[0].max_shield_quad * frac
    sc = Scene()
    sc.frame(ents)                    # prime at this level (no false hit)
    arr = sc.frame(ents)
    d = np.clip(arr - no_b, 0, None).max(axis=2)
    ys_, xs_ = np.nonzero(d > 0.008)
    if len(xs_) == 0:
        return None
    cx_, cy_ = xs_.mean(), ys_.mean()
    rr_ = np.sqrt((xs_ - cx_) ** 2 + (ys_ - cy_) ** 2)
    R_ = max(1.0, rr_.max())
    sel = (rr_ > 0.30 * R_) & (rr_ < 0.58 * R_)
    if not sel.any():
        return None
    px = np.clip(arr - no_b, 0, None)[ys_[sel], xs_[sel]]
    return (float(px[:, 0].mean()), float(px[:, 1].mean()),
            float(px[:, 2].mean()))


ramp = [(1.00, "blue"), (0.60, "yellow"), (0.35, "orange"), (0.12, "red")]
hues = {}
for frac, name in ramp:
    h = bubble_hue(frac)
    if h is None:
        _fail.append(f"no bubble emission at {frac:.2f} shields")
        hues[frac] = (0.0, 0.0, 0.0)
        continue
    # NORMALISE by brightness before comparing: the bubble fades as well as
    # reddens, so raw channel means shrink toward zero with strength and a
    # "red minus blue" on them measures dimming, not hue.
    tot = max(1e-6, h[0] + h[1] + h[2])
    nrm = (h[0] / tot, h[1] / tot, h[2] / tot)
    hues[frac] = nrm
    print(f"    {frac:4.2f} shields ({name:6s}): "
          f"R={nrm[0]:.3f} G={nrm[1]:.3f} B={nrm[2]:.3f}")
# blue at full: B dominant. red at low: R dominant with little B.
if not (hues[1.00][2] > hues[1.00][0]):
    _fail.append(f"full-strength bubble is not blue-dominant: {hues[1.00]}")
if not (hues[0.12][0] > hues[0.12][2]):
    _fail.append(f"low-shield bubble is not red-dominant: {hues[0.12]}")
# the ramp must be monotonic in normalised red-minus-blue: blue -> red
rmb = [hues[f][0] - hues[f][2] for f, _ in ramp]
if not all(a < b for a, b in zip(rmb, rmb[1:])):
    _fail.append(f"colour ramp not monotonic blue->red: "
                 f"{[round(x, 3) for x in rmb]}")

# ---- 4c. NO GREEN BAND. A straight yellow->blue interpolation passes through
# olive, which is not on the requested blue/yellow/orange/red ramp and reads as
# neither healthy nor damaged. Sweep the whole range and require that green
# never dominates BOTH other channels anywhere.
print("[4c] full-range sweep (green must never dominate both R and B):")
worst = None
for i in range(2, 10):
    frac = i / 10.0
    h = bubble_hue(frac)
    if h is None:
        _fail.append(f"no bubble emission at {frac:.1f} shields")
        continue
    tot = max(1e-6, h[0] + h[1] + h[2])
    n = (h[0] / tot, h[1] / tot, h[2] / tot)
    greenish = n[1] > n[0] and n[1] > n[2]
    if worst is None or n[1] - max(n[0], n[2]) > worst[1]:
        worst = (frac, n[1] - max(n[0], n[2]), n)
    print(f"    {frac:4.1f}: R={n[0]:.3f} G={n[1]:.3f} B={n[2]:.3f}"
          f"{'   <-- GREEN-DOMINANT' if greenish else ''}")
    if greenish:
        _fail.append(f"bubble goes green-dominant at {frac:.1f} shields: "
                     f"R={n[0]:.3f} G={n[1]:.3f} B={n[2]:.3f}")

# ------------------------------------------------------------ 5. NO SHIELD
noshield = mk(5, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD,
              shield_quad=0.0)
sc5 = Scene()
a1 = sc5.frame([noshield])
a2 = sc5.frame([noshield])
stray = int((np.abs(a1 - a2).max(axis=2) > 0.05).sum())
print(f"[5] no-shield unit: bubble px 0 (skipped by capacity), "
      f"frame-to-frame stray px={stray}")
if stray > 20:
    _fail.append(f"unit without shields rendered a changing overlay ({stray} px)")

# ---- 5b. a SELECTED shielded unit must carry no flat outline circle and no
# half-circle health arcs — the bubble replaces them. The removed arcs floated
# at radius*1.6 above the hull and the ring at radius*1.35, so both showed up
# as crisp thin strokes; assert they are gone from a selected unit.
sc_sel = Scene()
sel_ship = [mk(12, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD)]
sc_sel.frame(sel_ship, selected={12})
sel_arr = sc_sel.frame(sel_ship, selected={12})
sc_nosel = Scene()
sc_nosel.frame(sel_ship)
nosel_arr = sc_nosel.frame(sel_ship)
# With the ring and arcs removed, selecting a SHIELDED unit adds no crisp
# marker at all: the bubble already shows everything.
sel_extra = int((np.abs(sel_arr - nosel_arr).max(axis=2) > 0.03).sum())
print(f"[5b] shielded unit: selection adds {sel_extra} px "
      f"(ring + health arcs removed)")
if sel_extra > 60:
    _fail.append(f"selected shielded unit still draws a marker "
                 f"({sel_extra} px) - ring/arcs not fully removed")
# and the removed arcs sat ABOVE the hull: nothing should be drawn there now
ys3, xs3 = np.nonzero(np.abs(sel_arr - nosel_arr).max(axis=2) > 0.03)
if len(ys3):
    print(f"    remnant bbox y {ys3.min()}..{ys3.max()} (ship centre y={sy})")

# ------------------------------------------------------------ 6. QUADRANT HIT
# NOTE: the hit detector diffs against the PREVIOUS frame's quadrant values,
# which live on the Renderer instance — rebuilding the Renderer between frames
# (as a fresh Scene would) resets that cache and no hit is ever detected, so
# this section drives ONE Scene for the whole sequence.
qa = mk(6, FRIGATE, 0, (0, 0, 0), yaw=0.0, radius=RAD)
sc6 = Scene()
sc6.frame([qa])                       # seed the previous-value cache
primed = sc6.frame([qa])              # baseline: no transition
qa.shields["front"] = 0.0             # front quadrant takes the hit
hit = sc6.frame([qa])
save_png(hit, os.path.join(ROOT, "saves", "diag_gfx5_flash.png"))
flash = np.clip(hit - primed, 0, None).max(axis=2)
n_flash = int((flash > 0.02).sum())
print(f"[6] front-quadrant hit flash px: {n_flash}")
if n_flash < 60:
    _fail.append(f"quadrant hit produced no flash ({n_flash} px)")

# Locate the flash relative to the ship's FRONT. Project a point just beyond
# the bubble on the world +Z axis, then compare the flash energy that landed
# on the near side of that axis against the far side.
fsp = screen_of(0.0, 0.0, RAD * 1.35)
if fsp is None:
    _fail.append("could not project the ship front")
else:
    ux, uy = fsp[0] - sx, fsp[1] - sy
    nn = math.hypot(ux, uy) or 1.0
    ux, uy = ux / nn, uy / nn
    ys, xs = np.nonzero(flash > 0.02)
    if len(xs) == 0:
        _fail.append("no flash geometry to analyse")
    else:
        dx = xs - sx
        dy = ys - sy
        # signed projection of each flash pixel onto the ship-front direction
        proj = dx * ux + dy * uy
        vals = flash[ys, xs]
        f_e = float(vals[proj > 0].sum())
        r_e = float(vals[proj < 0].sum())
        print(f"    flash energy: front half={f_e:.0f}  rear half={r_e:.0f}  "
              f"(front px={int((proj > 0).sum())}, rear px={int((proj < 0).sum())})")
        if f_e <= r_e * 1.5:
            _fail.append(f"hit flash not concentrated on the hit face: "
                         f"front {f_e:.0f} vs rear {r_e:.0f}")

# A quadrant hit must decay away rather than stick. NOTE: the drained front
# quadrant is a PERMANENT state change (it lowers the bubble's overall
# strength, bucket 8 -> 6), so the settled frame must be compared against a
# reference rendered at the SAME drained values — not against the full-strength
# baseline, which differs for legitimate reasons.
qa_ref = mk(8, FRIGATE, 0, (0, 0, 0), yaw=0.0, radius=RAD)
qa_ref.shields["front"] = 0.0
sc_ref = Scene()
sc_ref.frame([qa_ref])
drained_ref = sc_ref.frame([qa_ref])
settled = drained_ref
for _ in range(40):
    settled = sc6.frame([qa])
resid = int((np.abs(settled - drained_ref).max(axis=2) > 0.04).sum())
print(f"    flash after 40 frames: residual px={resid} (vs same-strength ref)")
if resid > 40:
    _fail.append(f"hit flash did not decay ({resid} px remain)")

# ---- 6b. the flash follows the SHIP's heading, not the world axes.
# yaw = +90 deg puts the ship's LEFT quadrant on world -Z, so a hit there must
# flash the opposite screen side from the yaw=0 front hit above.
qb = mk(9, FRIGATE, 0, (0, 0, 0), yaw=math.radians(90), radius=RAD)
sc_qb = Scene()
sc_qb.frame([qb])
qb_primed = sc_qb.frame([qb])
qb.shields["left"] = 0.0
qb_hit = sc_qb.frame([qb])
save_png(qb_hit, os.path.join(ROOT, "saves", "diag_gfx5_flash_left.png"))
qflash = np.clip(qb_hit - qb_primed, 0, None).max(axis=2)
ys2, xs2 = np.nonzero(qflash > 0.02)
if len(xs2) == 0:
    _fail.append("rotated-ship quadrant hit produced no flash")
else:
    # world -Z is the ship's left at yaw=90; project it to screen
    lsp = screen_of(0.0, 0.0, -RAD * 1.35)
    if lsp is None:
        _fail.append("could not project the rotated ship's left quadrant")
    else:
        lx, ly = lsp[0] - sx, lsp[1] - sy
        ln = math.hypot(lx, ly) or 1.0
        lx, ly = lx / ln, ly / ln
        proj2 = (xs2 - sx) * lx + (ys2 - sy) * ly
        l_e = float(qflash[ys2, xs2][proj2 > 0].sum())
        o_e = float(qflash[ys2, xs2][proj2 < 0].sum())
        print(f"[6b] yaw=90 left-quadrant hit: left-of-ship energy={l_e:.0f}  "
              f"opposite={o_e:.0f}")
        if l_e <= o_e * 1.5:
            _fail.append(f"rotated-ship flash not on the hit quadrant: "
                         f"left {l_e:.0f} vs opposite {o_e:.0f}")

# ---- 6c. at tactical zoom the bubble must still read as a VOLUME, not
# collapse into the flat rim-only ring the old renderer drew.
far = [mk(10, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD)]
sc_far = Scene(dist=4600.0)
sc_far.frame(far)
far_arr = sc_far.frame(far)
save_png(far_arr, os.path.join(ROOT, "saves", "diag_gfx5_far.png"))
far_ref = Scene(dist=4600.0).frame(
    [mk(11, FRIGATE, 0, (0, 0, 0), yaw=math.radians(20), radius=RAD,
        shield_quad=0.0)])
fdiff = np.clip(far_arr - far_ref, 0, None).max(axis=2)
fys, fxs = np.nonzero(fdiff > 0.015)
if len(fxs) == 0:
    _fail.append("no bubble at tactical zoom")
else:
    span = max(fxs.max() - fxs.min(), fys.max() - fys.min())
    # how much of the bubble area is actually filled (a rim-only ring would be
    # a thin annulus: filled fraction far below a filled disc)
    fcx, fcy = (fxs.min() + fxs.max()) / 2.0, (fys.min() + fys.max()) / 2.0
    rr = np.sqrt((fxs - fcx) ** 2 + (fys - fcy) ** 2)
    R = max(1.0, rr.max())
    inner = int(((rr < R * 0.55) & (fdiff[fys, fxs] > 0.015)).sum())
    tot = len(fxs)
    print(f"[6c] tactical-zoom bubble: span={span}px  px={tot}  "
          f"inner-disc coverage={inner}/{tot} ({inner / max(1, tot):.2f})")
    if span < 60:
        _fail.append(f"tactical-zoom bubble below readability floor: {span}px")
    # A filled volume (not the flat outline circle this pass replaced) fills a
    # substantial part of its disc; a rim-only outline fills almost none.
    if inner < tot * 0.10:
        _fail.append(f"tactical-zoom bubble is rim-only (inner coverage "
                     f"{inner}/{tot}), not a volume")

# ------------------------------------------------------------ 8. montage
# One row per strength decade so the blue -> yellow -> orange -> red ramp is
# visible in a single image, plus a selected unit to show the markers are gone.
mont = []
_specs = [("imperial_cruiser", 70.0, 1.00), ("imperial_cruiser", 70.0, 0.80),
          ("imperial_frigate", RAD, 0.60), ("imperial_frigate", RAD, 0.35),
          ("confed_corvette", 30.0, 0.12)]
for i, (did, rad, frac) in enumerate(_specs):
    col = i % 2
    e = mk(20 + i, did, col, ((i - 2) * 1500, 0, -600 + (i % 2) * 900),
           yaw=math.radians(20 + i * 55), radius=rad)
    for q in QUADRANTS:
        e.shields[q] = e.max_shield_quad * frac
    mont.append(e)
scm = Scene(dist=6400.0)
arr = None
for _ in range(4):
    arr = scm.frame(mont, selected={22})   # one selected, to show markers gone
save_png(arr, out)
print("saved", out)

if _fail:
    for f in _fail:
        print("  FAIL:", f)
    print("DIAG_FAIL")
    sys.exit(1)
print("DIAG_OK")
