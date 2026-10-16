"""Bounded, GL-free loading of three authored Alliance specimen assets.

Only indexed triangle data/material roles cross this boundary. The editable
.blend and bpy exporter are development tools, never imported by the game.
"""
from functools import lru_cache
import json
import math
from pathlib import Path
from types import MappingProxyType

ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
ASSET_PATH = Path(__file__).resolve().parents[1] / 'assets/models/alliance_battleship.mesh.json'
MAX_BYTES = 2_000_000
MAX_VERTICES = 10_000
MAX_TRIANGLES = 12_000


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _load_profile(path, identifier, limits, min_length):
    """Validate the entire payload before returning deeply immutable role batches.

    Deliberately narrow bounds protect camera/contact code from malformed data;
    error handling/fallback belongs to the faction facade, not this validator.
    """
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('authored battleship exceeds file budget')
    asset = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(asset, dict) or asset.get('schema') != 1 or asset.get('asset') != identifier:
        raise ValueError('unsupported authored battleship schema or identifier')
    vertices, batches = asset.get('vertices'), asset.get('batches')
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_VERTICES:
        raise ValueError('authored battleship vertex budget')
    if not isinstance(batches, dict) or set(batches) != set(ROLES):
        raise ValueError('authored battleship material roles')
    for point in vertices:
        if not isinstance(point, list) or len(point) != 3 or any(
                not _finite_number(c) or not lo <= c <= hi for c, (lo, hi) in zip(point, limits)):
            raise ValueError('invalid authored battleship vertex/bounds')
    vertices = tuple(tuple(v) for v in vertices)
    result = {}
    total = 0
    for role in ROLES:
        faces = batches[role]
        if not isinstance(faces, list) or not faces:
            raise ValueError('empty authored battleship role')
        total += len(faces)
        if total > MAX_TRIANGLES:
            raise ValueError('authored battleship triangle budget')
        triangles = []
        for face in faces:
            if not isinstance(face, list) or len(face) != 6:
                raise ValueError('invalid authored battleship face')
            normal = tuple(face[:3])
            if not all(_finite_number(c) for c in normal) or abs(sum(c*c for c in normal)-1) > 1e-8:
                raise ValueError('invalid authored battleship normal')
            indices = face[3:]
            if any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
                raise ValueError('invalid authored battleship index')
            tri = tuple(vertices[i] for i in indices)
            a, b, c = tri
            u = tuple(b[i]-a[i] for i in range(3)); v = tuple(c[i]-a[i] for i in range(3))
            cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            area2 = math.sqrt(sum(x*x for x in cross))
            if area2 <= 1e-9 or sum(n*x for n, x in zip(normal, cross)) / area2 < 1 - 1e-8:
                raise ValueError('degenerate, reversed or incorrectly shaded authored battleship face')
            triangles.append((normal, tri))
        result[role] = tuple(triangles)
    lo = tuple(min(p[i] for p in vertices) for i in range(3))
    hi = tuple(max(p[i] for p in vertices) for i in range(3))
    if hi[2]-lo[2] < min_length or asset.get('triangle_count') != total or asset.get('bounds') != [list(lo), list(hi)]:
        raise ValueError('authored battleship metadata mismatch')
    return MappingProxyType(result)


def load_battleship(path):
    """Approved battleship profile, unchanged limits and validation semantics."""
    return _load_profile(path, 'alliance_battleship', ((-110, 110), (-35, 70), (-150, 140)), 240)


def load_frigate(path):
    return _load_profile(path, 'alliance_frigate', ((-37, 37), (-12, 27), (-82, 74)), 145)


def load_shipyard(path):
    return _load_profile(path, 'alliance_shipyard', ((-57, 57), (-20, 41), (-48, 52)), 90)


@lru_cache(maxsize=1)
def frigate_mesh():
    return load_frigate(ASSET_PATH.with_name('alliance_frigate.mesh.json'))


@lru_cache(maxsize=1)
def shipyard_mesh():
    return load_shipyard(ASSET_PATH.with_name('alliance_shipyard.mesh.json'))


@lru_cache(maxsize=1)
def battleship_mesh():
    """One asset, one cached parse, independent of entities/owners/GL contexts."""
    return load_battleship(ASSET_PATH)
