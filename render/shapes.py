"""Weapon-bolt and shield-shape rules that outlived the legacy renderer.

These are pure functions and constants: they decide a bolt's proportions and a bubble's colour,
which the live window and the HUD both need, and which the tests can check without a GL context.
They used to live in `render/renderer.py`; they moved here so deleting that module (#160) does not
delete the rules the window still uses.
"""
from __future__ import annotations
import math

from render.camera import normalize3

# Shield bubbles never render smaller than this across, in screen pixels. The hull pass applies the
# same idea to ship scale (spec §35 readability): without it a distant bubble resolves to nothing but
# its rim and collapses back into the flat outline circle the additive shell replaced.
SHIELD_MIN_PX = 74.0

# --- weapon fire look (#90) -------------------------------------------------
# Laser-family projectiles are thin rectangles elongated along their heading and torpedoes/missiles
# are squares, instead of every bolt being the same round glow-and-speck. Ion, plasma, kinetic and
# beam weapons keep that treatment: the brief is explicit that super weapons like the biggest ships
# and the pulsar cannon stay as they are.
BOLT_WEAPON_TYPES = ("laser", "point_defense", "turbolaser")
SQUARE_WEAPON_TYPES = ("torpedo", "missile")
BOLT_LENGTH_PER_SIZE = 5.5      # bolt length, in weapon data sizes
BOLT_WIDTH_PER_SIZE = 0.85      # bolt width: long and thin, never a dot
BOLT_MIN_PX = (3.6, 1.8)        # SCREEN-space floor (length, width) in pixels
SQUARE_SIDE_PER_SIZE = 2.1
SQUARE_MIN_PX = 3.0


def projectile_shape(weapon_type: str | None) -> str:
    """'bolt', 'square' or 'legacy' for a weapon family (#90)."""
    if weapon_type in BOLT_WEAPON_TYPES:
        return "bolt"
    if weapon_type in SQUARE_WEAPON_TYPES:
        return "square"
    return "legacy"


def projectile_extents(shape: str, size: float, px_per_world: float) -> tuple[float, float]:
    """(length, width) of one projectile's core quad, in world units.

    Pure, so the proportions are testable without a GL context. Both extents carry a SCREEN-space
    floor: a world-only size is ~1 px at overview range, which is exactly the readability failure
    the old point sprites had.
    """
    if shape == "square":
        side = max(size * SQUARE_SIDE_PER_SIZE, SQUARE_MIN_PX * px_per_world)
        return side, side
    return (max(size * BOLT_LENGTH_PER_SIZE, BOLT_MIN_PX[0] * px_per_world),
            max(size * BOLT_WIDTH_PER_SIZE, BOLT_MIN_PX[1] * px_per_world))


def square_quad_offsets(side: float):
    """Axis-aligned corners for a square projectile.

    Squares are deliberately NOT oriented by their heading: a square rotated to follow a diagonal
    heading reads as a diamond, which is not what "torpedoes look like squares" means.
    """
    half = side / 2.0
    return ((half, half), (half, -half), (-half, -half), (-half, half))


def projectile_quad_offsets(vel, right, up, length: float, width: float):
    """Four corners, in the camera plane, of a projectile quad.

    Offsets are (u, v) along `right`/`up`; the caller maps them to world space. The long axis
    follows the projectile's heading projected into the view plane. A shot fired straight at or
    away from the camera has no screen-space heading at all - falling back to a fixed axis keeps it
    a visible streak instead of collapsing to a dot.
    """
    v = normalize3((vel[0], vel[1], vel[2])) if any(vel) else (0.0, 0.0, 0.0)
    dr = v[0] * right[0] + v[1] * right[1] + v[2] * right[2]
    du = v[0] * up[0] + v[1] * up[1] + v[2] * up[2]
    proj = math.hypot(dr, du)
    if proj < 0.15:
        ux, uy = 0.0, 1.0
    else:
        ux, uy = dr / proj, du / proj
    px_, py_ = -uy, ux
    hl, hw = length / 2.0, width / 2.0
    return ((ux * hl + px_ * hw, uy * hl + py_ * hw),
            (ux * hl - px_ * hw, uy * hl - py_ * hw),
            (-ux * hl - px_ * hw, -uy * hl - py_ * hw),
            (-ux * hl + px_ * hw, -uy * hl + py_ * hw))


def shield_color(s: float) -> tuple[float, float, float]:
    """Bubble colour for a shield-strength fraction.

    Blue at full strength, shifting through yellow and orange to red as the field weakens, so a
    glance at the 3D view says how much shield is left without reading the side panel. The bubble
    vanishes entirely at zero, so the ramp's last readable state is the red warning.
    """
    stops = ((0.12, (1.00, 0.18, 0.12)),     # red    — about to fail
             (0.30, (1.00, 0.48, 0.06)),     # orange
             (0.62, (1.00, 0.86, 0.06)),     # yellow — long, saturated band so
                                             # "damaged but holding" is its own
                                             # readable state, not a brief
                                             # transition
             (0.85, (1.00, 0.97, 0.90)),     # warm white — see below
             (1.00, (0.30, 0.55, 1.00)))     # blue   — nominal
    # The warm-white stop is not decoration. A straight yellow->blue blend passes through
    # (0.65, 0.69, 0.58), where green outweighs both red and blue — the bubble turns olive at ~75%
    # shields, exactly when it should still read as healthy, and olive is nowhere on the requested
    # ramp. Routing through a white with R >= G keeps red the dominant channel on the yellow half
    # and blue the dominant one on the blue half, so green never leads at any strength.
    if s <= stops[0][0]:
        return stops[0][1]
    for (s0, c0), (s1, c1) in zip(stops, stops[1:]):
        if s <= s1:
            k = (s - s0) / max(1e-6, s1 - s0)
            return (c0[0] + (c1[0] - c0[0]) * k,
                    c0[1] + (c1[1] - c0[1]) * k,
                    c0[2] + (c1[2] - c0[2]) * k)
    return stops[-1][1]
