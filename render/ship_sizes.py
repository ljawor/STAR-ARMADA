"""Renderer-only lengths normalized to the unchanged standard corvette.

Collision radii, save fields and balance data are deliberately not inputs.
Bounds include every hardware/material role, not only the main hull loft.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math
from render.fleet_geometry import ship_mesh
from render.faction_visuals import SHIP_KEYS, normalize_ship_key, ship_visual_key

RATIOS = {'fighter_squadron': .6, 'corvette': 1., 'frigate': 1.5,
          'cruiser': 2.5, 'battleship': 3.5, 'supercapital': 5.,
          'construction': 1., 'crew_transport': .8}
READABILITY_PX = 7.
READABILITY_HALF = 26.
READABILITY_SCALE = .7
READABILITY_FLOOR = .01


def _bounds(shape):
    return _canonical_bounds(normalize_ship_key(shape))


@lru_cache(maxsize=len(SHIP_KEYS))
def _canonical_bounds(shape):
    points = [p for mesh in ship_mesh(shape).values() for _,tri in mesh for p in tri]
    lo = tuple(min(p[i] for p in points) for i in range(3))
    hi = tuple(max(p[i] for p in points) for i in range(3))
    radius = max(math.sqrt(sum(x*x for x in p)) for p in points)
    return lo, hi, radius


_bounds.cache_info = _canonical_bounds.cache_info
_bounds.cache_clear = _canonical_bounds.cache_clear


@dataclass(frozen=True)
class ShipSize:
    shape: str
    scale: float
    length: float
    radius: float
    stern: float
    half_width: float


def ship_size(ds, data_id, faction=None):
    shape = ship_visual_key(ds, data_id, faction)
    data = ds.ships.get(data_id)
    ratio = RATIOS.get(data.category, 1.) if data else 1.
    if data_id == 'boarding_craft':
        ratio = .4
    lo, hi, radius = _bounds(shape)
    nlo, nhi, _ = _bounds('needle')
    length = (nhi[2]-nlo[2])*.7*ratio
    scale = length/(hi[2]-lo[2])
    return ShipSize(shape, scale, length, radius*scale, lo[2]*scale,
                    max(abs(lo[0]), abs(hi[0]))*scale)


def readable_size(ds, data_id, px_per_world, faction=None):
    """One shared corvette-calibrated zoom multiplier preserves class ratios.

    Keep the committed corvette's 7px/26-unit half-extent floor exactly, but
    apply its multiplier to all classes instead of independently inflating hulls.
    """
    size = ship_size(ds, data_id, faction)
    # An eye-plane/behind-eye contact has no projected size. The readability
    # floor must not turn that sentinel into a 1000x hull surrounding the eye.
    if px_per_world <= 0.:
        return size
    boost = max(1., READABILITY_PX / (max(READABILITY_FLOOR,
                                        READABILITY_HALF * px_per_world) * READABILITY_SCALE))
    return replace(size, **{field: getattr(size, field)*boost for field in
                           ('scale', 'length', 'radius', 'stern', 'half_width')})


def _ray_mesh(shape):
    return _canonical_ray_mesh(normalize_ship_key(shape))


@lru_cache(maxsize=len(SHIP_KEYS))
def _canonical_ray_mesh(shape):
    """Finite immutable triangle arrays, never keyed by entity/camera/heading."""
    return _triangle_arrays(ship_mesh(shape))


_ray_mesh.cache_info = _canonical_ray_mesh.cache_info
_ray_mesh.cache_clear = _canonical_ray_mesh.cache_clear


def _triangle_arrays(mesh):
    import numpy as np
    triangles = np.asarray([tri for triangles in mesh.values() for _,tri in triangles])
    a = triangles[:,0]
    ab, ac = triangles[:,1]-a, triangles[:,2]-a
    q = np.cross(-a, ab)
    numerator = np.einsum('ij,ij->i', ac, q)
    for array in (a, ab, ac, q, numerator): array.flags.writeable = False
    return a, ab, ac, q, numerator


def hull_contact_distance(size, normal, yaw):
    """Center-out ray against all-role triangles, batched for busy combat."""
    return _contact_distance(_ray_mesh(size.shape), size.scale, normal, yaw)


@lru_cache(maxsize=40)
def _station_ray_mesh(faction, data_id):
    from render.fleet_geometry import station_mesh
    return _triangle_arrays(station_mesh(data_id, faction))


def station_contact_distance(data_id, faction, radius, normal, yaw):
    from render.faction_visuals import normalize_station_key
    faction, data_id = normalize_station_key(data_id, faction)
    return _contact_distance(_station_ray_mesh(faction, data_id), radius / 50., normal, yaw)


def station_contact_offset(data_id, faction, radius, normal, yaw, desired_offset):
    """World-oriented surface offset, or None when no finite surface resolves.

    Preserve the center-out hit when present. Open/disconnected hardware may
    miss that ray: project the desired impact onto every material-role triangle
    instead, never invent a radial/bounding-sphere contact through docking voids.
    """
    from render.faction_visuals import normalize_station_key
    faction, data_id = normalize_station_key(data_id, faction)
    return _surface_contact_offset(_station_ray_mesh(faction, data_id), radius / 50.,
                                   normal, yaw, desired_offset)


def hull_contact_offset(size, normal, yaw, desired_offset):
    """Actual readable hull surface, including disconnected/open hardware."""
    return _surface_contact_offset(_ray_mesh(size.shape), size.scale,
                                   normal, yaw, desired_offset)


def _surface_contact_offset(arrays, scale, normal, yaw, desired_offset):
    """Keep ray hits; on misses choose the nearest actual triangle point."""
    import numpy as np
    if (not math.isfinite(scale) or scale <= 0. or not math.isfinite(yaw) or
            not np.isfinite(normal).all() or not np.isfinite(desired_offset).all()):
        return None
    distance = _contact_distance(arrays, scale, normal, yaw)
    if distance > 0. and math.isfinite(distance):
        return tuple(float(v)*distance for v in normal)
    ca, sa = math.cos(yaw), math.sin(yaw)
    x, y, z = desired_offset
    desired = np.asarray((x*ca-z*sa, y, z*ca+x*sa)) / scale
    a, ab, ac, _, _ = arrays
    finite = np.isfinite(a).all(axis=1) & np.isfinite(ab).all(axis=1) & np.isfinite(ac).all(axis=1)
    a, ab, ac = a[finite], ab[finite], ac[finite]
    if not len(a):
        return None
    cross = np.cross(ab, ac)
    squared = np.einsum('ij,ij->i', cross, cross)
    valid = squared > 1e-18
    # The plane projection is a candidate only inside its actual triangle.
    delta = desired-a
    factor = np.divide(np.einsum('ij,ij->i', delta, cross), squared,
                       out=np.zeros_like(squared), where=valid)
    projected = desired-factor[:,None]*cross
    d00 = np.einsum('ij,ij->i', ab, ab)
    d01 = np.einsum('ij,ij->i', ab, ac)
    d11 = np.einsum('ij,ij->i', ac, ac)
    d20 = np.einsum('ij,ij->i', projected-a, ab)
    d21 = np.einsum('ij,ij->i', projected-a, ac)
    determinant = d00*d11-d01*d01
    valid &= determinant > 1e-18
    u = np.divide(d11*d20-d01*d21, determinant, out=np.zeros_like(determinant), where=valid)
    v = np.divide(d00*d21-d01*d20, determinant, out=np.zeros_like(determinant), where=valid)
    candidates = [projected[valid & (u>=0.) & (v>=0.) & (u+v<=1.)]]
    # Boundary minima (including degenerate triangles) lie on these segments.
    for start, edge in ((a, ab), (a, ac), (a+ab, ac-ab)):
        squared = np.einsum('ij,ij->i', edge, edge)
        t = np.divide(np.einsum('ij,ij->i', desired-start, edge), squared,
                      out=np.zeros_like(squared), where=squared>0.)
        candidates.append(start+np.clip(t, 0., 1.)[:,None]*edge)
    points = np.concatenate(candidates)
    points = points[np.isfinite(points).all(axis=1)]
    if not len(points):
        return None
    point = points[np.argmin(np.sum((points-desired)**2, axis=1))]*scale
    return (float(point[0]*ca+point[2]*sa), float(point[1]),
            float(point[2]*ca-point[0]*sa))


def _contact_distance(arrays, scale, normal, yaw):
    import numpy as np
    ca, sa = math.cos(yaw), math.sin(yaw)
    ray = np.asarray((normal[0]*ca-normal[2]*sa, normal[1], normal[2]*ca+normal[0]*sa))
    a, ab, ac, q, numerator = arrays
    p = np.cross(ray, ac)
    det = np.einsum('ij,ij->i', ab, p)
    valid = np.abs(det)>1e-9
    inv = np.divide(1., det, out=np.zeros_like(det), where=valid)
    u = np.einsum('ij,ij->i', -a, p)*inv
    v = np.einsum('ij,j->i', q, ray)*inv
    distance = numerator*inv
    valid &= (u>=0)&(u<=1)&(v>=0)&(u+v<=1)&(distance>0)
    return float(distance[valid].max(initial=0.))*scale
