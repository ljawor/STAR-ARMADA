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
    GL_CLAMP, GL_CLAMP_TO_EDGE, GL_LINEAR, GL_REPEAT, GL_RGB, GL_RGBA,
    GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_UNSIGNED_BYTE,
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
    # Terrain has fine elevation/albedo variation and shallow coastal shelves;
    # cloud decks use independent multi-scale weather, not continent outlines.
    detail = _fbm(size, seed + 213, octaves=5, base_cells=18)
    if kind in ("temperate", "agricultural", "trade", "research"):
        threshold = .45 if kind == "agricultural" else .5
        landmix = np.clip((n - threshold) / .018 + .5, 0, 1)
        shelf = np.exp(-((n - threshold + .017) / .020) ** 2)
        ocean = np.zeros_like(img) + np.array([.025, .10, .21])
        ocean += shelf[..., None] * np.array([.02,.15,.17])
        ground = np.zeros_like(img) + np.array([.19,.28,.16])
        dry = np.clip((detail - .38) * 2.5, 0, 1)
        ground += dry[..., None] * np.array([.22,.15,.08])
        ground *= (.68 + detail * .7)[..., None]
        if kind == "research":
            ground *= np.array([1.2,.85,1.4])
        img = ocean * (1-landmix[..., None]) + ground * landmix[..., None]
    else:
        img *= (.80 + detail * .4)[..., None]
    if kind not in ("barren", "asteroid_field", "gas_giant"):
        weather = _fbm(size, seed + 307, octaves=5, base_cells=12)
        fronts = np.sin(lon * 3 + lat * 7 + weather * 9) * .035
        clouds = np.clip((weather + fronts - .48) * 5, 0, .86)
        clouds *= np.clip(np.sin(lat), 0, 1) ** .35
        img = img * (1-clouds[..., None]) + np.array([.86,.89,.91]) * clouds[..., None]
    # polar caps (ice) except gas giants — irregular soft edge so they read
    # as terrain, not a flat gray disc
    if kind != "gas_giant":
        polar = np.abs(lat - math.pi / 2) / (math.pi / 2)   # 0 equator..1 pole
        cap_edge = _fbm(size, seed + 41, octaves=3, base_cells=10)
        threshold = 0.86 + (cap_edge - 0.5) * 0.12          # wavy boundary
        soft = np.clip((polar - threshold) / 0.08, 0, 1)    # soft transition
        # ice with faint blue-gray streaks (not featureless gray)
        streak = _fbm(size, seed + 55, octaves=2, base_cells=18)
        ice_r = 0.88 + streak * 0.06
        ice_g = 0.91 + streak * 0.05
        ice_b = 0.95 + streak * 0.03
        for c, ice_c in enumerate((ice_r, ice_g, ice_b)):
            img[..., c] = img[..., c] * (1 - soft) + ice_c * soft
    # Exact longitude closure and pole averages avoid a visible meridian or
    # pinwheel at the singularities of the UV sphere.
    img[:, -1] = img[:, 0]
    img[0, :] = img[0].mean(axis=0)
    img[-1, :] = img[-1].mean(axis=0)
    img = np.clip(img, 0.0, 1.0)
    return _arr_to_surface(img * 255.0)


def star_texture(size: int = 256, seed: int = 3) -> pygame.Surface:
    """Granulated hot-star surface (RGBA, radial limb falloff).

    The billboard is a camera-facing quad: without a radial alpha falloff the
    star reads as a SQUARE. Alpha fades from full in the core to 0 at the
    inscribed-circle rim so the disc is round against the starfield.
    """
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
    # radial alpha: round disc + limb darkening toward the rim
    yy, xx = np.mgrid[0:size, 0:size]
    fx = (xx / (size - 1)) * 2 - 1
    fy = (yy / (size - 1)) * 2 - 1
    r = np.sqrt(fx * fx + fy * fy)
    limb = np.clip(1.0 - (r - 0.55) / 0.45, 0, 1) ** 1.6   # 1 inside r<0.55
    img *= (0.62 + 0.38 * np.clip(1.0 - r, 0, 1))[..., None]
    alpha = limb * 255.0
    return _arr_to_surface(np.clip(img, 0, 1) * 255.0, alpha=alpha)


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


def deep_space_texture(size: int = 1024, seed: int = 17) -> pygame.Surface:
    """Dim, seamless sky panorama: blue dust, violet filaments, dark lanes.

    Cached by the renderer, centered on the eye, not a camera-facing cloud card.
    Stars remain a separate crisp pass. No simulation or global RNG is touched.
    """
    lat, lon = _sphere_equirect(size)
    coarse = _fbm(size, seed, octaves=5, base_cells=3)
    fine = _fbm(size, seed + 71, octaves=5, base_cells=9)
    belt = np.exp(-((lat - math.pi / 2 + .48 * np.sin(lon * 2)) / .55) ** 2)
    cloud = np.clip((coarse - .27) * 2.1, 0, 1) ** 1.7 * belt
    wisps = np.clip((fine - .38) * 3.1, 0, 1)
    dust = np.clip((.52 - fine) * 5.0, 0, 1) ** 2
    rgb = np.zeros((size, size, 3), dtype=np.float32)
    rgb[:] = (.009, .016, .032)
    rgb += cloud[..., None] * np.array([.12, .20, .29])
    rgb += (cloud * wisps)[..., None] * np.array([.11, .035, .15])
    rgb *= (1 - dust * cloud * .82)[..., None]
    # Pole average removes pinwheels and exact edge equality avoids meridians.
    polar = np.clip(np.sin(lat), 0, 1) ** .5
    rgb = rgb * polar[..., None] + np.array([.009,.016,.032]) * (1-polar[..., None])
    rgb[:, -1] = rgb[:, 0]
    return _arr_to_surface(np.clip(rgb, 0, 1) * 255)


def hull_texture(size: int = 256, seed: int = 7) -> pygame.Surface:
    """Tileable grayscale hull-panel texture (plates, seams, rivets, grunge).

    Ships render with GL_MODULATE so the owner color multiplies this map:
    grayscale stays in [~0.5, 1.0] so hulls keep their faction hue while
    gaining panel plating, seam grooves and rivet rows. Tiles cleanly
    (GL_REPEAT): panel grid and seams wrap at the borders.
    """
    rng = np.random.RandomState(seed)
    panels = 8
    cell = size // panels
    img = np.ones((size, size), dtype=np.float32) * 0.88
    # per-panel plating shade; some panels recessed (darker armor inserts)
    shade = rng.rand(panels, panels).astype(np.float32) * 0.14 + 0.80
    shade[rng.rand(panels, panels) < 0.18] -= 0.10
    for iy in range(panels):
        for ix in range(panels):
            img[iy * cell:(iy + 1) * cell, ix * cell:(ix + 1) * cell] = shade[iy, ix]
    # seam grooves at cell borders (some skipped -> larger plate clusters)
    seam = np.zeros((size, size), dtype=np.float32)
    for iy in range(panels + 1):
        if rng.rand() < 0.75:
            seam[(iy * cell) % size:(iy * cell) % size + 2, :] = 1.0
    for ix in range(panels + 1):
        if rng.rand() < 0.75:
            seam[:, (ix * cell) % size:(ix * cell) % size + 2] = 1.0
    img[seam > 0] = 0.58
    # rivet dots flanking the seams
    riv = np.zeros((size, size), dtype=np.float32)
    for iy in range(panels + 1):
        y = (iy * cell) % size
        for x in range(4, size, 12):
            riv[(y + 3) % size, x:x + 2] = 1.0
            riv[(y - 5) % size, x:x + 2] = 1.0
    img[riv > 0] = 0.50
    # occasional hatches / access panels
    for iy in range(panels):
        for ix in range(panels):
            if rng.rand() < 0.08:
                y0, x0 = iy * cell + 4, ix * cell + 4
                img[y0:y0 + cell - 8, x0:x0 + cell - 8] = 0.66
    # grime + fine wear
    img += (_fbm(size, seed + 3, octaves=4, base_cells=6) - 0.5) * 0.12
    img += (_value_noise(size, 32, seed + 9) - 0.5) * 0.06
    # keep the floor high enough that GL_MODULATE never blackens faction hues
    img = np.clip(img, 0.58, 1.0)
    return _arr_to_surface(np.repeat(img[..., None], 3, axis=2) * 255.0)


# --------------------------------------------------------------------------- GL
def surface_to_texture(surf: pygame.Surface, mipmaps: bool = False,
                       repeat: bool = False) -> int:
    """Upload a pygame Surface as a GL texture (returns tex id).

    Format-aware: surfaces without an alpha channel upload as GL_RGB —
    tostring("RGBA") on an opaque surface emits alpha=0 bytes, which
    disappears completely when alpha blending is enabled (star/nebula
    billboards rendered black because of this).
    repeat=True sets GL_REPEAT wrapping (tileable hull-panel maps).
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
    wrap = GL_REPEAT if repeat else GL_CLAMP_TO_EDGE
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexImage2D(GL_TEXTURE_2D, 0, internal, w, h, 0, fmt,
                 GL_UNSIGNED_BYTE, data)
    return tex


def _gl():
    import OpenGL.GL as GL
    return GL