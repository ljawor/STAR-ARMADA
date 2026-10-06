"""Ownership legibility cues for the 3D view.

In a close-range scrum a hull is a handful of pixels and the additive shield
bubble sits over every unit in the same blue, so the only ownership channel —
hull tint — is the one the player cannot read. This module owns the two
redundant cues that fix it, as pure data so they can be tested without a GL
context:

  * **marker** — a screen-clamped chevron (own/ally) or diamond (hostile) that
    keeps a constant pixel size at any zoom, so ownership survives the smallest
    readable hull.
  * **hull shade** — the base tint is pushed up for own/ally hulls and down for
    hostiles, so the tint channel still reads after the bubble wash.

Shape carries the meaning, colour reinforces it: any single cue being unclear
still leaves the other, which is what makes it survive a busy battle.
"""
from __future__ import annotations

# Marker footprint in screen pixels. Clamped rather than scaled: a marker that
# shrinks with distance is the problem it exists to solve. 9 px is the smallest
# footprint that still resolves two distinct silhouette shapes; 15 px keeps a
# capital ship's icon from covering its own bubbles.
MARKER_MIN_PX = 9.0
MARKER_MAX_PX = 15.0

MODES = ("all", "hostiles", "off")


def marker_mode(value) -> str:
    """Normalise a settings value to one of MODES (default 'all')."""
    if isinstance(value, str) and value.strip().lower() in MODES:
        return value.strip().lower()
    return "all"


def next_mode(value) -> str:
    """Cycle the setting: all -> hostiles -> off -> all."""
    mode = marker_mode(value)
    return MODES[(MODES.index(mode) + 1) % len(MODES)]


def relation_of(local_player: int, owner: "int | None", allied_owners) -> str:
    """Classify `owner` from `local_player`'s point of view.

    `allied_owners` is the owner-id collection the local player is allied to
    (normally including the local player itself). A neutral/environmental
    owner (owner < 0, e.g. terrain) is neither.
    """
    if owner is None or owner < 0:
        return "neutral"
    if owner == local_player:
        return "own"
    try:
        allies = set(allied_owners)
    except TypeError:
        return "enemy"
    if local_player in allies and owner in allies:
        return "ally"
    if owner == local_player:
        return "own"
    return "enemy"


def is_hostile(rel: str) -> bool:
    return rel == "enemy"


def shows_marker(rel: str, mode) -> bool:
    """Whether a unit with this relation draws a marker in this mode.

    'hostiles' is the decluttered mode: every HOSTILE unit still gets a shape
    (so no enemy is ever invisible), while the player's own fleet falls back to
    plain hull tint and the selection ring.
    """
    mode = marker_mode(mode)
    if mode == "off":
        return False
    if mode == "hostiles":
        return rel in ("enemy", "neutral")
    return rel in ("own", "ally", "enemy", "neutral")


def marker_px(apparent_px: "float | None") -> float:
    """Marker footprint for a hull whose apparent size is `apparent_px`.

    Larger hulls get a slightly larger icon so the marker stays proportionate,
    but it never drops below MARKER_MIN_PX (the whole point) nor grows past
    MARKER_MAX_PX (so it cannot blanket a capital ship's own shields).
    """
    size = MARKER_MIN_PX + max(0.0, float(apparent_px or 0.0)) * 0.12
    return max(MARKER_MIN_PX, min(MARKER_MAX_PX, size))


def world_radius(px: float, px_per_world: float) -> float:
    """World-space half-extent that renders `px` pixels wide at this depth."""
    if px_per_world <= 0.0:
        return 0.0
    return (float(px) * 0.5) / float(px_per_world)


# Marker outlines in the camera-aligned (right, up) plane, normalised to a
# half-extent of 1.0. Screen-space +y is up, so a downward-pointing chevron
# aims at the hull it labels; the diamond is orientation-free.
CHEVRON = ((-1.00, 0.62), (-0.46, 0.62), (0.00, -0.18),
           (0.46, 0.62), (1.00, 0.62), (0.00, -1.00))
DIAMOND = ((0.00, 1.00), (0.72, 0.20), (0.72, -0.20),
           (0.00, -1.00), (-0.72, -0.20), (-0.72, 0.20))

OWN_SHAPE = "chevron"
HOSTILE_SHAPE = "diamond"


def shape_for(rel: str):
    """Polygon for a relation — shape, not just colour, encodes ownership."""
    return DIAMOND if is_hostile(rel) else CHEVRON


# The hostile cue is a single fixed threat colour rather than the enemy's own
# player colour: in a 2-4 player match a per-player diamond would just move the
# "which one is that" question onto the marker. One colour means one meaning.
HOSTILE_COLOR = (1.00, 0.34, 0.12)
NEUTRAL_COLOR = (0.72, 0.72, 0.72)
OUTLINE_COLOR = (0.02, 0.03, 0.05)


def marker_color(rel: str, owner_color) -> tuple:
    """Fill colour for a marker of this relation."""
    if is_hostile(rel):
        return HOSTILE_COLOR
    if rel == "neutral":
        return NEUTRAL_COLOR
    try:
        c = tuple(float(x) for x in owner_color)[:3]
    except (TypeError, ValueError):
        return NEUTRAL_COLOR
    if len(c) != 3:
        return NEUTRAL_COLOR
    # Own/ally markers must clear the bubble wash, so lift them toward white.
    return tuple(min(1.0, v * 0.65 + 0.42) for v in c)


def hull_shade(color, rel: str) -> tuple:
    """Base hull tint pushed apart by relation.

    Own/ally hulls are lifted so they still show the player colour through an
    additive bubble; hostile hulls are pushed darker and slightly desaturated
    so they read as the opposite end of the same channel. Stations, terrains
    and unknown owners are returned unchanged.
    """
    try:
        c = tuple(float(x) for x in color)[:3]
    except (TypeError, ValueError):
        return color
    if len(c) != 3:
        return color
    if rel in ("own", "ally"):
        return tuple(min(1.0, v * 0.82 + 0.26) for v in c)
    if rel == "enemy":
        mean = (c[0] + c[1] + c[2]) / 3.0
        return tuple(max(0.0, (v * 0.55 + mean * 0.10)) for v in c)
    return c
