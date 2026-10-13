"""Knowledge-limited hyperspace geometry shared by intent and simulation.

No live enemy queries: legality depends on map bounds, selected hulls and own
reserved exits only, never exploration or current sensing. Y uses the same
+/-bounds/2 safety limit as XZ.
"""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3


def clear_jump_orders(entity) -> None:
    """Jump owns locomotion: discard stale routes and contact locks."""
    entity.order_type = "idle"
    entity.order_target_pos = None
    entity.order_target_id = None
    entity.current_target = None
    entity.patrol_a = None
    entity.patrol_b = None
    entity.vel = Vec3()


def detach_jumpers(state, ships) -> None:
    """Accepted jumpers leave their old formation; regrouping is explicit.

    Call only after all exits have been reserved. Nonjumpers keep their orders,
    rally and fleet identity; removing a flagship elects the largest remaining
    live hull, with lowest id breaking ties. Empty fleets are removed.
    """
    affected = set()
    for entity in ships:
        fleet = state.fleets.get(entity.fleet_id)
        if fleet is not None:
            fleet.member_ids.discard(entity.id)
            affected.add(fleet.id)
        entity.fleet_id = None
    for fid in sorted(affected):
        fleet = state.fleets[fid]
        if not fleet.member_ids:
            del state.fleets[fid]
        elif fleet.flagship_id not in fleet.member_ids:
            remaining = [state.entity(mid) for mid in sorted(fleet.member_ids)]
            remaining = [e for e in remaining if e is not None]
            flagship = min(remaining, key=lambda e: (-e.max_hull, e.id), default=None)
            fleet.flagship_id = flagship.id if flagship is not None else None


def transit_seconds(rules, distance: float) -> float:
    """Deterministic transit duration (#92): distance over speed, clamped."""
    speed = rules.get("transit_units_per_second", 240.0)
    tmin = rules.get("min_transit_seconds", 3.0)
    tmax = rules.get("max_transit_seconds", 120.0)
    if (isinstance(speed, bool) or not isinstance(speed, (int, float))
            or not math.isfinite(speed) or speed <= 0
            or isinstance(tmin, bool) or not isinstance(tmin, (int, float))
            or not math.isfinite(tmin) or tmin < 0
            or isinstance(tmax, bool) or not isinstance(tmax, (int, float))
            or not math.isfinite(tmax) or tmax < tmin):
        raise ValueError('hyperspace transit rules must be finite and ordered')
    raw = distance / speed
    return max(tmin, min(tmax, raw))


def jump_destination(state, player: int, target, *, require_unexplored: bool = False) -> Vec3 | None:
    """Parse a strict finite triple inside the map; never coerce malformed input."""
    if player not in state.players:
        return None
    if isinstance(target, Vec3):
        target = (target.x, target.y, target.z)
    if not isinstance(target, (list, tuple)) or len(target) != 3:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in target):
        return None
    half = state.map_info.bounds / 2.0
    if any(abs(v) > half for v in target):
        return None
    return Vec3(*target)


def jump_footprint_valid(state, player: int, pos: Vec3, radius: float,
                         *, require_unexplored: bool = False) -> bool:
    """Require the entire hull inside bounds, independent of exploration.

    The legacy keyword is accepted for existing completion callers only;
    exploration never restricts either destination or footprint validation.
    """
    half = state.map_info.bounds / 2.0
    if (not math.isfinite(radius) or radius < 0
            or abs(pos.x) + radius > half or abs(pos.z) + radius > half
            or abs(pos.y) + radius > half):
        return False
    return True


def plan_jump_exits(state, player: int, ships, target: Vec3):
    """Reserve nearby lattice slots in stable id order, all-or-nothing.

    Single ships retain the exact click. Groups search a bounded square spiral,
    moving inward around map boundaries rather than clamping ships onto
    one point. Clearance includes the simulation's 1.15 separation margin.
    """
    ships = sorted(ships, key=lambda e: e.id)
    if not ships:
        return None
    spacing = 2.3 * max(e.radius for e in ships) + 10.0
    rings = math.ceil(math.sqrt(len(ships))) + 2 if len(ships) > 1 else 0
    offsets = sorted(((x, z) for x in range(-rings, rings + 1)
                      for z in range(-rings, rings + 1)),
                     key=lambda p: (p[0] * p[0] + p[1] * p[1], p[0], p[1]))
    reserved = [(e.jump_target, e.radius) for e in state.entities.values()
                if e.owner == player and e.alive and e.jump_target is not None]
    result = []
    for e in ships:
        for x, z in offsets:
            pos = Vec3(target.x + x * spacing, target.y, target.z + z * spacing)
            if (jump_destination(state, player, pos) is None
                    or not jump_footprint_valid(state, player, pos, e.radius)):
                continue
            if any((pos - other).length() < 1.15 * (e.radius + radius)
                   for other, radius in reserved):
                continue
            reserved.append((pos, e.radius))
            result.append((e, pos))
            break
        else:
            return None
    return result
