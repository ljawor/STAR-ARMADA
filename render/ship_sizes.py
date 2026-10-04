"""Renderer-only lengths normalized to the unchanged standard corvette.

Collision radii, save fields and balance data are deliberately not inputs.
Bounds include every hardware/material role, not only the main hull loft.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import math
from render.fleet_geometry import ship_mesh

RATIOS = {'fighter_squadron': .6, 'corvette': 1., 'frigate': 1.5,
          'cruiser': 2.5, 'battleship': 3.5, 'supercapital': 5.,
          'construction': 1.}
READABILITY_PX = 7.
READABILITY_HALF = 26.
READABILITY_SCALE = .7
READABILITY_FLOOR = .01


@lru_cache(maxsize=5)
def _bounds(shape):
    points = [p for mesh in ship_mesh(shape).values() for _,tri in mesh for p in tri]
    lo = tuple(min(p[i] for p in points) for i in range(3))
    hi = tuple(max(p[i] for p in points) for i in range(3))
    radius = max(math.sqrt(sum(x*x for x in p)) for p in points)
    return lo, hi, radius


@dataclass(frozen=True)
class ShipSize:
    shape: str
    scale: float
    length: float
    radius: float
    stern: float
    half_width: float


def ship_size(ds, data_id):
    shape = ds.ship_visual(data_id)['shape']
    shape = shape if shape in ('wedge', 'needle', 'cruiser', 'dagger') else 'box'
    data = ds.ships.get(data_id)
    ratio = RATIOS.get(data.category, 1.) if data else 1.
    lo, hi, radius = _bounds(shape)
    nlo, nhi, _ = _bounds('needle')
    length = (nhi[2]-nlo[2])*.7*ratio
    scale = length/(hi[2]-lo[2])
    return ShipSize(shape, scale, length, radius*scale, lo[2]*scale,
                    max(abs(lo[0]), abs(hi[0]))*scale)


def readable_size(ds, data_id, px_per_world):
    """One shared corvette-calibrated zoom multiplier preserves class ratios.

    Keep the committed corvette's 7px/26-unit half-extent floor exactly, but
    apply its multiplier to all classes instead of independently inflating hulls.
    """
    size = ship_size(ds, data_id)
    # An eye-plane/behind-eye contact has no projected size. The readability
    # floor must not turn that sentinel into a 1000x hull surrounding the eye.
    if px_per_world <= 0.:
        return size
    boost = max(1., READABILITY_PX / (max(READABILITY_FLOOR,
                                        READABILITY_HALF * px_per_world) * READABILITY_SCALE))
    return replace(size, **{field: getattr(size, field)*boost for field in
                           ('scale', 'length', 'radius', 'stern', 'half_width')})


@lru_cache(maxsize=5)
def _ray_mesh(shape):
    """Five immutable triangle arrays, never keyed by entity/camera/heading."""
    import numpy as np
    triangles = np.asarray([tri for mesh in ship_mesh(shape).values() for _,tri in mesh])
    a = triangles[:,0]
    ab, ac = triangles[:,1]-a, triangles[:,2]-a
    q = np.cross(-a, ab)
    numerator = np.einsum('ij,ij->i', ac, q)
    for array in (a, ab, ac, q, numerator): array.flags.writeable = False
    return a, ab, ac, q, numerator


def hull_contact_distance(size, normal, yaw):
    """Center-out ray against all-role triangles, batched for busy combat."""
    import numpy as np
    ca, sa = math.cos(yaw), math.sin(yaw)
    ray = np.asarray((normal[0]*ca-normal[2]*sa, normal[1], normal[2]*ca+normal[0]*sa))
    a, ab, ac, q, numerator = _ray_mesh(size.shape)
    p = np.cross(ray, ac)
    det = np.einsum('ij,ij->i', ab, p)
    valid = np.abs(det)>1e-9
    inv = np.divide(1., det, out=np.zeros_like(det), where=valid)
    u = np.einsum('ij,ij->i', -a, p)*inv
    v = np.einsum('ij,j->i', q, ray)*inv
    distance = numerator*inv
    valid &= (u>=0)&(u<=1)&(v>=0)&(u+v<=1)&(distance>0)
    return float(distance[valid].max(initial=0.))*size.scale
