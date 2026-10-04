"""Read-only camera keep-outs from the exact hardware mesh material roles.

An oriented model-space box is deliberately conservative across holes/gaps;
Collision radii are not stand-ins for hardware bounds. Station radius is only
used as the renderer's exact mesh scale. Cached mesh data is model-only.
"""
from functools import lru_cache
import math
from render.fleet_geometry import station_mesh


@lru_cache(maxsize=10)
def station_bounds(data_id):
    vertices = [p for mesh in station_mesh(data_id).values() for _, tri in mesh for p in tri]
    return tuple(min(p[i] for p in vertices) for i in range(3)), tuple(max(p[i] for p in vertices) for i in range(3))


def scene_boxes(state, player_id, station_angle, ray=None):
    from game.data.store import DataStore
    ds = DataStore.get()
    boxes = []
    hardware = {}  # Per-query catalogue geometry; no live visibility cache.
    for e in state.entities.values():
        if e.is_planet:
            # Planets render last-observed snapshots, never hidden live owners.
            known = state.known_entity(player_id, e.id)
            if known is not None and known.alive and known.data_id != 'asteroid_field':
                radius = known.radius * (1. if known.data_id == 'barren' else 1.018)
                boxes.append(((known.pos.x, known.pos.y, known.pos.z), radius))
            continue
        if not e.alive or not (e.is_station or e.is_ship or e.is_squadron):
            continue
        if e.is_station:
            if ds.stations.get(e.data_id) is None:
                continue
            lo, hi = station_bounds(e.data_id)
            scale, angle = e.radius / 50., station_angle
        else:
            from render.ship_sizes import ship_size, _bounds
            if e.data_id not in hardware:
                size = ship_size(ds, e.data_id)
                lo, hi, _ = _bounds(size.shape)
                hardware[e.data_id] = (tuple(v * size.scale for v in lo),
                                       tuple(v * size.scale for v in hi))
            lo, hi = hardware[e.data_id]
            scale, angle = 1., e.yaw
        box = ((e.pos.x, e.pos.y, e.pos.z), angle,
               tuple(v * scale for v in lo), tuple(v * scale for v in hi))
        box = box if e.is_station else box + (True,)
        if ray is not None:
            origin, direction, clearance, slope, cap = ray
            # Use the complete positive orbit ray: chained obstacles can extend
            # the final eye beyond the first exit. Visibility remains live.
            relevant = (readable_intervals(origin, direction, box, clearance, slope, cap)
                        if len(box) == 5 else box_interval(origin, direction, box, clearance))
            if not relevant:
                continue
        if state.can_see(player_id, e.id):
            boxes.append(box)
    return tuple(boxes)


def box_interval(origin, direction, box, clearance):
    if len(box) == 2:
        center, radius = box
        offset = tuple(origin[i] - center[i] for i in range(3))
        b = sum(offset[i] * direction[i] for i in range(3))
        c = sum(v * v for v in offset) - (radius + clearance) ** 2
        discriminant = b * b - c
        if discriminant < 0:
            return None
        root = math.sqrt(discriminant)
        return (-b - root, -b + root) if -b + root >= 0 else None
    center, angle, lo, hi = box[:4]
    ca, sa = math.cos(angle), math.sin(angle)
    v = tuple(origin[i] - center[i] for i in range(3))
    o = (v[0] * ca - v[2] * sa, v[1], v[2] * ca + v[0] * sa)
    d = (direction[0] * ca - direction[2] * sa, direction[1],
         direction[2] * ca + direction[0] * sa)
    entry, exit = -math.inf, math.inf
    for i in range(3):
        low, high = lo[i] - clearance, hi[i] + clearance
        if abs(d[i]) < 1e-10:
            if o[i] < low or o[i] > high:
                return None
        else:
            a, b = (low - o[i]) / d[i], (high - o[i]) / d[i]
            entry, exit = max(entry, min(a, b)), min(exit, max(a, b))
    return (entry, exit) if exit >= max(0., entry) else None


def readable_intervals(origin, direction, box, clearance, slope, cap):
    """Exact ray keep-outs for the shared depth-dependent readability scale.

    Along the orbit ray, depth = distance - projected center. The multiplier
    has three affine pieces: base, linear depth floor, capped floor. Solve
    their slab inequalities directly, avoiding iterative/circular camera LOD.
    """
    center, angle, lo, hi = box[:4]
    ca, sa = math.cos(angle), math.sin(angle)
    v = tuple(origin[i] - center[i] for i in range(3))
    o = (v[0]*ca-v[2]*sa, v[1], v[2]*ca+v[0]*sa)
    d = (direction[0]*ca-direction[2]*sa, direction[1],
         direction[2]*ca+direction[0]*sa)
    projected = sum((center[i]-origin[i])*direction[i] for i in range(3))
    start, stop = projected + 1./slope, projected + cap/slope
    intervals = []
    for entry, exit, a, b in ((0., start, 0., 1.),
                              (max(0., start), stop, slope, -slope*projected),
                              (max(0., stop), math.inf, 0., cap)):
        for i in range(3):
            # Both inequalities are rate * distance >= rhs.
            for rate, rhs in ((d[i]-lo[i]*a, lo[i]*b-clearance-o[i]),
                              (hi[i]*a-d[i], o[i]-hi[i]*b-clearance)):
                if abs(rate) < 1e-12:
                    if rhs > 0.:
                        exit = -math.inf
                elif rate > 0.:
                    entry = max(entry, rhs/rate)
                else:
                    exit = min(exit, rhs/rate)
        if exit >= entry:
            intervals.append((entry, exit))
    return intervals


def camera_ray(target, requested_eye, near, fov, aspect, height=800):
    delta = tuple(requested_eye[i] - target[i] for i in range(3))
    length = math.sqrt(sum(v * v for v in delta))
    if length < 1e-9:
        return None
    direction = tuple(v / length for v in delta)
    # Bounding ball of the complete near-plane rectangle, not just its center.
    tangent = math.tan(math.radians(fov) / 2.)
    clearance = near * math.sqrt(1. + tangent * tangent * (1. + aspect * aspect)) + 2.
    from render.ship_sizes import READABILITY_PX, READABILITY_HALF, READABILITY_SCALE, READABILITY_FLOOR
    slope = READABILITY_PX * 2. * tangent / (READABILITY_HALF * READABILITY_SCALE * max(1, height))
    cap = READABILITY_PX / (READABILITY_FLOOR * READABILITY_SCALE)
    return (tuple(target), direction, clearance, slope, cap)


def safe_eye(target, requested_eye, boxes, near, fov, aspect, height=800):
    ray = camera_ray(target, requested_eye, near, fov, aspect, height)
    if ray is None:
        return requested_eye
    _, direction, clearance, slope, cap = ray
    length = math.dist(target, requested_eye)
    intervals = []
    for box in boxes:
        if len(box) == 5:
            intervals.extend(readable_intervals(target, direction, box, clearance, slope, cap))
        elif (interval := box_interval(target, direction, box, clearance)) is not None:
            intervals.append(interval)
    effective = length
    # Sorted interval union handles a second tall neighbor beyond the first exit.
    for entry, exit in sorted(intervals):
        if entry <= effective <= exit:
            effective = exit + 1e-5
    if effective == length:
        return requested_eye
    return tuple(target[i] + direction[i] * effective for i in range(3))
