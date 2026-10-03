"""Strict fog view boundary (no reveal-all fallback).

GameState.can_see(pid, eid) gates all live contacts and picking. known_entity
returns only visible contacts or immutable last-observed static snapshots.
is_position_visible gates transient effects. The cached map mask rasterizes
only the authoritative sensor_sources effective spheres; is_position_explored
classifies charted ground. No observer discovery, sensor stat calculation or
ownership inference is duplicated in the view.
"""
from __future__ import annotations


from game.core.vectors import Vec3


def position(pos):
    """Normalize render effects/map JSON positions to the core's Vec3 API."""
    if isinstance(pos, Vec3):
        return pos
    if isinstance(pos, dict):
        return Vec3(pos['x'], pos['y'], pos['z'])
    return Vec3(*pos)


def known_entities(state, player_id):
    for eid in state.entities:
        entity = state.known_entity(player_id, eid)
        if entity is not None and entity.alive:
            yield entity


def effect_visible(state, player_id, effect):
    if not state.is_position_visible(player_id, position(effect['pos'])):
        return False
    target = effect.get('target_pos')
    if target is None:
        return True
    end = position(target)
    if not state.is_position_visible(player_id, end):
        return False
    return segment_visible(state, player_id, position(effect['pos']), end)


def segment_visible(state, player_id, start, end):
    """A beam/trail may not bridge unknown space between sensor islands.

    Merge analytic line/sphere intersections from the authoritative team sensor
    sources. Checking endpoints alone leaks the middle; finite samples can miss
    narrow gaps. This tests the entire segment without per-pixel source scans.
    """
    import math
    d = end - start
    a = d.x*d.x + d.y*d.y + d.z*d.z
    if a <= 1e-12:
        return state.is_position_visible(player_id, start)
    intervals = []
    for source, radius in state.sensor_sources(player_id):
        o = start - source.pos
        b = 2*(o.x*d.x + o.y*d.y + o.z*d.z)
        c = o.x*o.x + o.y*o.y + o.z*o.z - radius*radius
        disc = b*b - 4*a*c
        if disc >= 0:
            root = math.sqrt(disc)
            lo, hi = max(0., (-b-root)/(2*a)), min(1., (-b+root)/(2*a))
            if lo <= hi:
                intervals.append((lo, hi))
    covered = 0.
    for lo, hi in sorted(intervals):
        if lo > covered + 1e-9:
            return False
        covered = max(covered, hi)
        if covered >= 1.:
            return True
    return False


class FogMask:
    """One small map texture, rebuilt only when team coverage changes.

    Classification is one sample per exploration cell, not screen pixel. The
    cache includes effective ranges, source positions and explored membership;
    detector damage/death, allied movement, upgrades and reload invalidate it.
    Camera motion (including X overview) only reprojects the same texture.
    """
    def __init__(self):
        self._key = None
        self._surface = None
        self._uploaded_surface = None
        self.texture = None

    def surface(self, state, player_id):
        import math
        import pygame
        bounds = state.map_info.bounds
        cell = state.visibility_cell_size
        sources = tuple((e.id, e.pos.x, e.pos.y, e.pos.z, r)
                        for e, r in state.sensor_sources(player_id))
        explored = frozenset(state.explored_cells.get(player_id, set()))
        key = (id(state), player_id, bounds, cell, sources, explored)
        if key == self._key:
            return self._surface
        n = max(1, math.ceil(bounds / cell))
        surface = pygame.Surface((n, n), pygame.SRCALPHA)
        half = bounds / 2
        step = bounds / n
        # Vectorized raster of authoritative spheres: gather sources ONCE,
        # never ask the sim to rediscover every observer for every texel.
        import numpy as np
        centers = np.arange(n, dtype=float) * step - half + step / 2
        visible = np.zeros((n, n), dtype=bool)
        for _, sx, sy, sz, radius in sources:
            visible |= ((centers[:, None]-sx)**2 + sy*sy
                        + (centers[None, :]-sz)**2 <= radius*radius)
        for z in range(n):
            for x in range(n):
                pos = Vec3(centers[x], 0, centers[z])
                charted = state.is_position_explored(player_id, pos)
                alpha = 0 if visible[x, z] else (155 if charted else 255)
                color = (12, 22, 38, alpha) if charted else (3, 6, 13, alpha)
                surface.set_at((x, z), color)
        self._key, self._surface = key, surface
        return surface

    def draw(self, state, player_id):
        from OpenGL import GL
        import pygame
        surface = self.surface(state, player_id)
        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_TEXTURE_BIT |
                        GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT |
                        GL.GL_CURRENT_BIT | GL.GL_LIGHTING_BIT)
        try:
            if self.texture is None:
                self.texture = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
            if self._uploaded_surface is not surface:
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                                surface.get_width(), surface.get_height(), 0,
                                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                                pygame.image.tobytes(surface, 'RGBA', False))
                self._uploaded_surface = surface
            GL.glDisable(GL.GL_LIGHTING)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glDepthMask(False)
            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glColor4f(1, 1, 1, 1)
            half = state.map_info.bounds / 2
            GL.glBegin(GL.GL_QUADS)
            for u, v, x, z in ((0, 0, -half, -half), (1, 0, half, -half),
                                (1, 1, half, half), (0, 1, -half, half)):
                GL.glTexCoord2f(u, v)
                GL.glVertex3f(x, 0, z)
            GL.glEnd()
        finally:
            GL.glPopAttrib()

    def close(self):
        if self.texture is not None:
            from OpenGL import GL
            GL.glDeleteTextures([self.texture])
            self.texture = None
