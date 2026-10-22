"""What the ownership cues are, decided once, for both renderers.

`render/renderer.py` draws three cheap overlays: selection rings (`_draw_selection_rings`), ownership
markers (`_draw_ownership_markers`) and planet owner rings (inside `_draw_planets`). Their *rules*
are what a player reads — a shielded unit hides its ring behind the bubble, a damaged hull turns its
ring orange and then red, a hostile gets a diamond and a fixed threat colour — so the rules are not
duplicated here as a second opinion. This module turns state into the primitives
`render_bridge/markers.py` carries, mirroring those three functions line for line and citing them.

Two things are deliberately left to the window:

  * marker pixel size. Python's is `markers.marker_px(apparent_px)` with a camera-derived apparent
    size; in live mode the window owns the camera, so it applies the same formula to its own view.
  * nothing else. Selection, relation, colour, severity and shape are all decided here.
"""
from __future__ import annotations

from render import markers as mk
from render_bridge import markers as codec

SELECTION_ALPHA = 0.9           # render/renderer.py::_draw_selection_rings
# render/renderer.py::_draw_collection_points draws the destination in this teal, at a world radius
# of at least 45 units, as a diamond in the ecliptic with a cross through it. The window draws the
# destination only while its owning station is selected. Deselecting hides the cue without
# clearing the saved destination used by future production.
COLLECTION_COLOUR = (0.35, 0.95, 0.8)
COLLECTION_ALPHA = 0.95
COLLECTION_RADIUS = 45.0
COLLECTION_WIDTH = 2.0
COLLECTION_SEGMENTS = 4         # a four-segment flat ring is the legacy diamond, corner for corner
SELECTION_WIDTH = 2.0
SELECTION_SEGMENTS = 28
SHIELDED_RING_FACTOR = 1.1      # tucked inside the bubble at radius * 1.35
PLAIN_RING_FACTOR = 1.35
PLANET_RING_FACTOR = 1.1
PLANET_OWNER_CLEARANCE = 120.0  # _draw_planets: r = e.radius + 120
PLANET_OWNER_WIDTH = 3.0
PLANET_OWNER_SEGMENTS = 40


def _colour(player):
    if player is None:
        return (1.0, 1.0, 1.0)
    return tuple(player.color[:3])


def _severity_colour(entity, owner_colour):
    """Owner colour, overridden by hull severity — the same thresholds as the renderer."""
    fraction = entity.hull_fraction()
    if fraction < 0.35:
        return (1.0, 0.25, 0.2)
    if fraction < 0.7:
        return (1.0, 0.8, 0.25)
    return owner_colour


def is_shielded(entity) -> bool:
    """A shielded unit draws no ring: the bubble already shows the shield at 1.35x."""
    if entity.is_planet:
        return False
    try:
        return entity.max_shield_total() > 0 and entity.total_shield() > 0
    except AttributeError:
        return False


def selection_rings(state, selection_ids, radius_of) -> list:
    """One circle per selected unit, coloured by owner and hull severity."""
    out = []
    for entity_id in sorted(selection_ids):
        entity = state.entities.get(entity_id)
        if entity is None or not entity.alive:
            continue
        if getattr(entity, 'planet_building_slot', None) is not None:
            continue                     # surface hardware selects its planet, not itself
        if getattr(entity, 'jump_travelling', False):
            continue                     # no hull in the world view, so no ring around it (#162)
        if is_shielded(entity):
            continue
        hull = float(radius_of(entity))
        if hull <= 0.0:
            continue                     # not drawn by the frame, so it gets no ring
        player = state.players.get(entity.owner)
        colour = _severity_colour(entity, _colour(player))
        # The hull's world radius, not the instance scale: `scale` is a multiplier on a mesh
        # authored at catalogue size, so a ring sized from it is a hairline beside the hull.
        radius = hull * (PLAIN_RING_FACTOR if not entity.is_planet else PLANET_RING_FACTOR)
        vertical = entity.is_station or not (entity.is_ship or entity.is_squadron)
        out.append(codec.circle((entity.pos.x, entity.pos.y, entity.pos.z), radius, colour,
                                vertical=vertical, width=SELECTION_WIDTH,
                                segments=SELECTION_SEGMENTS, alpha=SELECTION_ALPHA,
                                depth=False))
    return out


def planet_owner_rings(state) -> list:
    """A colonist's colour ring around every owned world."""
    out = []
    for entity in state.entities.values():
        if not entity.alive or not entity.is_planet:
            continue
        owner = getattr(entity, 'colonized_by', None)
        if owner is None or owner < 0:
            continue
        player = state.players.get(owner)
        if player is None:
            continue
        out.append(codec.circle((entity.pos.x, entity.pos.y, entity.pos.z),
                                float(entity.radius) + PLANET_OWNER_CLEARANCE,
                                _colour(player), width=PLANET_OWNER_WIDTH,
                                segments=PLANET_OWNER_SEGMENTS, alpha=1.0, depth=True))
    return out


def collection_point_cues(state, local_player, selection_ids=()) -> list:
    """A diamond on each selected owned station's saved destination.

    The rule (which station, which point, which colour) is `render/renderer.py::_draw_collection_points`
    and `game/systems/collection_points.py`; only the shape crosses. Four segments of a flat ring put
    a vertex on each axis, which is the same diamond the Python renderer builds by hand.
    """
    from game.systems.collection_points import collection_capable
    out = []
    for entity_id in sorted(selection_ids):
        entity = state.entities.get(entity_id)
        if entity is None or not entity.alive or entity.owner != local_player:
            continue
        point = getattr(entity, 'collection_point', None)
        if point is None or not collection_capable(entity):
            continue
        out.append(codec.circle((point.x, point.y, point.z), COLLECTION_RADIUS, COLLECTION_COLOUR,
                                vertical=False, width=COLLECTION_WIDTH,
                                segments=COLLECTION_SEGMENTS, alpha=COLLECTION_ALPHA,
                                depth=False))
    return out


def ownership_markers(state, local_player, visible_ids, mode='all', allies=None,
                      radius_of=None) -> list:
    """A chevron (own/ally/neutral) or diamond (hostile) on every detected unit."""
    mode = mk.marker_mode(mode)
    if mode == 'off':
        return []
    if allies is None:
        allies = {local_player}
    out = []
    for entity_id in sorted(visible_ids or ()):
        entity = state.entities.get(entity_id)
        if entity is None or not entity.alive or entity.is_planet:
            continue
        if getattr(entity, 'jump_travelling', False):
            continue                     # a chevron over empty space is a marker for nothing (#162)
        relationship = mk.relation_of(local_player, entity.owner, allies)
        if not mk.shows_marker(relationship, mode):
            continue
        player = state.players.get(entity.owner)
        owner_colour = _colour(player) if relationship in ('own', 'ally') else None
        colour = mk.marker_color(relationship, owner_colour)
        # `size` is the hull's own world radius, not the icon's pixels: the window applies
        # markers.marker_px to its own camera's apparent size, which is the only way the icon
        # stays screen-clamped when the window owns the camera.
        hull_radius = float(radius_of(entity)) if radius_of is not None else 0.0
        # The shape comes from render/markers.py, not from a second opinion about what a hostile
        # is: shape and colour both encode ownership, so both are the game's call.
        shape = mk.shape_for(relationship)
        out.append(codec.marker((entity.pos.x, entity.pos.y, entity.pos.z), hull_radius, colour,
                                hostile=(shape == mk.DIAMOND)))
    return out


def build(state, local_player, selection_ids, visible_ids, *, radius_of, mode='all',
          allies=None, planet_rings=True, with_markers=True, collection_points=True) -> list:
    """Everything the window draws on top of the world, as one batch."""
    primitives = selection_rings(state, selection_ids, radius_of)
    if planet_rings:
        primitives += planet_owner_rings(state)
    if collection_points:
        primitives += collection_point_cues(state, local_player, selection_ids)
    if with_markers:
        primitives += ownership_markers(state, local_player, visible_ids, mode, allies, radius_of)
    return primitives
