"""Procedural textures: planets, star, nebula billboards, hull panels.

All textures are generated with numpy at startup (no asset files needed) and
uploaded as GL_TEXTURE_2D. Replaces flat-shaded spheres so bodies read as
textured worlds (value-noise continents, polar caps, city lights for
industrial worlds, banding for gas giants).
"""
from __future__ import annotations

import math

import numpy as np
import pygame

from OpenGL.GL import (
    glBindTexture, glTexImage2D, glTexParameteri,
    GL_CLAMP, GL_LINEAR, GL_RGB, GL_RGBA, GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T, GL_UNSIGNED_BYTE,
)


def _arr_to_surface(rgb: np.ndarray, alpha: np.ndarray | None = None) -> pygame.Surface:
    """HxWx3 float [0,1] (+ optional HxW alpha) -> RGB/RGBA Surface."""
    h, w = rgb.shape[:2]
    depth = 32 if alpha is not None else 24
    surf = pygame.image.frombuffer(
        (np.dstack([rgb, alpha]) if alpha is not None else rgb
         ).astype(np.uint8).tobytes(), (w, h), "RGB" if alpha is None else "RGBA")
    return surf


def _value_noise(size: int, cells: int, seed: int) -> np.ndarray:
    """Smooth value noise in [0, 1] via bilinear-upsampled random grid."""
    rng = np.random.RandomState(seed)
    grid = rng.rand(cells, cells).astype(np.float32)
    # tile edges for seamlessness
    grid = np.pad(grid, ((0, 1), (0, 1)), mode="wrap")
    # bilinear upsample cells -> size x size
    xs = np.linspace(0.0, float(cells), size, endpoint=False, dtype=np.float32)
    xi = np.floor(xs).astype(np.int32) % cells
    fx = (xs - np.floor(xs))[None, :]
    ys = np.linspace(0.0, float(cells), size, endpoint=False, dtype=np.float32)
    yi = np.floor(ys).astype(np.int32) % cells
    fy = (ys - np.floor(ys))[:, None]
    g00 = grid[np.ix_(yi, xi)]
    g10 = grid[np.ix_(yi, xi + 1)]
    g01 = grid[np.ix_(yi + 1, xi)]
    g11 = grid[np.ix_(yi + 1, xi + 1)]
    top = g00 * (1 - fx) + g10 * fx
    bot = g01 * (1 - fx) + g11 * fx
    return top * (1 - fy) + bot * fy


def _fbm(size: int, seed: int, octaves: int = 4, base_cells: int = 4) -> np.ndarray:
    """Fractal brownian motion of value noise, [0,1]."""
    acc = np.zeros((size, size), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        acc += _value_noise(size, base_cells * (2 ** o), seed + o * 17) * amp
        total += amp
        amp *= 0.55
    return acc / max(total, 1e-6)


def _sphere_equirect(size: int) -> tuple[np.ndarray, np.ndarray]:
    """Latitude/longitude grids for a size×size equirectangular map."""
    v = np.linspace(0.0, math.pi, size, dtype=np.float32)      # 0..pi (pole..pole)
    u = np.linspace(0.0, 2 * math.pi, size, dtype=np.float32)  # 0..2pi
    lon, lat = np.meshgrid(u, v)
    return lat, lon


def planet_texture(kind: str, size: int = 256, seed: int = 5) -> pygame.Surface:
    """Equirectangular planet texture per planet type."""
    lat, lon = _sphere_equirect(size)
    n = _fbm(size, seed=seed)
    img = np.zeros((size, size, 3), dtype=np.float32)

    if kind == "gas_giant":
        # latitude bands with turbulent wobble
        bands = np.sin(lat * 9.0 + n * 5.0) * 0.5 + 0.5
        base = np.array([0.82, 0.70, 0.52], dtype=np.float32)
        dark = np.array([0.55, 0.42, 0.30], dtype=np.float32)
        for c in range(3):
            img[..., c] = dark[c] + (base[c] - dark[c]) * bands
        # great storm spot
        spot = np.exp(-(((lat - 1.9) ** 2) / 0.02 + ((lon - 4.2) ** 2) / 0.08))
        img[..., 0] += spot * 0.25
        img[..., 1] -= spot * 0.10
    elif kind == "industrial":
        land = n > 0.52
        base = np.array([0.16, 0.17, 0.20], dtype=np.float32)
        lit = np.array([0.85, 0.65, 0.30], dtype=np.float32)
        for c in range(3):
            img[..., c] = base[c] + (lit[c] - base[c]) * land * (
                0.6 + 0.4 * np.sin(lon * 40.0 + n * 30.0) * 0.5)
        # night-side city glow dots
        city = (n > 0.72) & land
        img[..., 0] += city * 0.55
        img[..., 2] += city * 0.15
    elif kind == "agricultural":
        land = n > 0.45
        sea = np.array([0.10, 0.28, 0.42], dtype=np.float32)
        crop = np.array([0.42, 0.62, 0.28], dtype=np.float32)
        m = land.astype(np.float32)
        for c in range(3):
            img[..., c] = sea[c] + (crop[c] - sea[c]) * m
        img += (n - 0.5)[..., None] * 0.12
    elif kind == "military":
        land = n > 0.5
        base = np.array([0.30, 0.28, 0.30], dtype=np.float32)
        fort = np.array([0.62, 0.35, 0.32], dtype=np.float32)
        m = land.astype(np.float32)
        for c in range(3):
            img[..., c] = base[c] + (fort[c] - base[c]) * m
        # grid-like fortification lines
        gridline = (np.sin(lon * 24.0) > 0.97) & land
        img += gridline[..., None] * np.array([0.4, 0.2, 0.2], dtype=np.float32)
    else:  # temperate / barren / trade / research / asteroid_field
        if kind == "barren":
            land = np.ones_like(n, dtype=np.float32)
            base = np.array([0.48, 0.46, 0.44], dtype=np.float32)
            img[:] = base
            img += (n - 0.5)[..., None] * 0.25
            craters = _fbm(size, seed + 99, octaves=3, base_cells=16) > 0.78
            img -= craters[..., None] * 0.18
        else:
            land = n > 0.5
            sea = np.array([0.08, 0.22, 0.45], dtype=np.float32)
            ground = np.array([0.28, 0.52, 0.30], dtype=np.float32)
            if kind == "trade":
                ground = np.array([0.55, 0.50, 0.38], dtype=np.float32)
                sea = np.array([0.15, 0.30, 0.50], dtype=np.float32)
            elif kind == "research":
                ground = np.array([0.42, 0.38, 0.60], dtype=np.float32)
            elif kind == "asteroid_field":
                ground = np.array([0.40, 0.38, 0.35], dtype=np.float32)
                sea = np.array([0.05, 0.05, 0.06], dtype=np.float32)
            m = land.astype(np.float32)
            for c in range(3):
                img[..., c] = sea[c] + (ground[c] - sea[c]) * m
            img += (n - 0.5)[..., None] * 0.10
    # polar caps (ice) except gas giants
    if kind != "gas_giant":
        polar = np.clip((math.pi / 2 - np.abs(lat - math.pi / 2)) < 0.0, 0, 1)
        polar = np.clip((np.abs(lat - math.pi / 2) / (math.pi / 2)), 0, 1)
        ice = (polar > 0.82).astype(np.float32)
        for c in range(3):
            img[..., c] = img[..., c] * (1 - ice) + 0.88 * ice
    img = np.clip(img, 0.0, 1.0)
    return _arr_to_surface(img * 255.0)


def star_texture(size: int = 256, seed: int = 3) -> pygame.Surface:
    """Granulated hot-star surface."""
    lat, lon = _sphere_equirect(size)
    n = _fbm(size, seed, octaves=5, base_cells=8)
    granule = _fbm(size, seed + 7, octaves=3, base_cells=24)
    img = np.zeros((size, size, 3), dtype=np.float32)
    base = np.array([1.0, 0.85, 0.55], dtype=np.float32)
    hot = np.array([1.0, 1.0, 0.9], dtype=np.float32)
    dark = np.array([0.85, 0.55, 0.25], dtype=np.float32)
    t = 0.55 * n + 0.45 * granule
    for c in range(3):
        img[..., c] = dark[c] + (base[c] - dark[c]) * t
        img[..., c] = np.where(t > 0.75, hot[c], img[..., c])
    return _arr_to_surface(np.clip(img, 0, 1) * 255.0)


def nebula_texture(size: int = 256, seed: int = 11,
                   color=(0.4, 0.2, 0.55)) -> pygame.Surface:
    """RGBA cloud sprite (transparent rim, wispy alpha)."""
    n = _fbm(size, seed, octaves=5, base_cells=3)
    n2 = _fbm(size, seed + 31, octaves=4, base_cells=6)
    t = n * 0.65 + n2 * 0.35
    alpha = np.clip((t - 0.35) * 1.8, 0, 1) ** 1.5
    # radial + border falloff: alpha MUST reach ~0 at all four edges or the
    # billboard quad shows as a seam box against the starfield
    yy, xx = np.mgrid[0:size, 0:size]
    fx = (xx / (size - 1)) * 2 - 1
    fy = (yy / (size - 1)) * 2 - 1
    edge = 1.0 - np.clip(np.maximum(np.abs(fx), np.abs(fy)) - 0.55, 0, 1) / 0.45
    radial = np.clip(1.0 - (fx * fx + fy * fy) / 2.0, 0, 1) ** 1.2
    alpha = alpha * np.minimum(edge, radial)
    img = np.zeros((size, size, 4), dtype=np.float32)
    for c in range(3):
        img[..., c] = color[c] * (0.7 + 0.5 * n2)
    img[..., 3] = alpha
    return _arr_to_surface(np.clip(img[..., :3], 0, 1) * 255.0,
                           alpha=np.clip(img[..., 3], 0, 1) * 255.0)


# --------------------------------------------------------------------------- GL
def surface_to_texture(surf: pygame.Surface, mipmaps: bool = False) -> int:
    """Upload a pygame Surface as a GL texture (returns tex id).

    Format-aware: surfaces without an alpha channel upload as GL_RGB —
    tostring("RGBA") on an opaque surface emits alpha=0 bytes, which
    disappears completely when alpha blending is enabled (star/nebula
    billboards rendered black because of this).
    """
    w, h = surf.get_size()
    has_alpha = surf.get_masks()[3] != 0
    if has_alpha:
        data = pygame.image.tobytes(surf, "RGBA")
        fmt, internal = GL_RGBA, GL_RGBA
    else:
        data = pygame.image.tobytes(surf, "RGB")
        fmt, internal = GL_RGB, GL_RGB
    tex = _gl().glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
    glTexImage2D(GL_TEXTURE_2D, 0, internal, w, h, 0, fmt,
                 GL_UNSIGNED_BYTE, data)
    return tex


def _gl():
    import OpenGL.GL as GL
    return GL