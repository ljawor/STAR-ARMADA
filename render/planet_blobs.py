"""W05: build the planet textures the window needs, once per distinct planet.

The Python renderer draws a planet as a textured sphere whose texture is procedural and seeded
from the planet's *name*, so the same world looks the same after a reload. That texture is the part
worth carrying: a sphere is a few hundred triangles on the far side.

`PlanetTextures` keeps one blob per `(data_id, name)` and hands the producer only the ones it has not
published yet, so a long match uploads each planet exactly once.
"""
from __future__ import annotations

import hashlib

from render_bridge import planets as codec


def seed_for(name: str) -> int:
    """The seed the live renderer uses for a planet texture (stable across processes)."""
    return int.from_bytes(hashlib.blake2s(name.encode(), digest_size=4).digest(), 'little') % 1000000


class PlanetTextures:
    """Distinct planet textures, encoded on demand."""

    def __init__(self, size=256):
        self.size = int(size)
        self._blobs = {}
        self._published = set()
        self.generated = 0
        self.published = 0
        self.reused = 0
        self.failures = []

    def blobs_for(self, state):
        """Every planet texture this state needs, keyed by binding name."""
        out = {}
        for entity in state.entities.values():
            if not entity.alive or not entity.is_planet:
                continue
            data_id = entity.data_id
            if data_id == 'asteroid_field':
                continue                       # drawn as rocks, not a textured sphere
            name = entity.name_override or data_id
            binding = codec.binding_name(data_id, name)
            blob = self._blobs.get(binding)
            if blob is None:
                try:
                    blob = self._build(data_id, name)
                except Exception as error:     # a texture failure must not stop the match
                    self.failures.append(f'{binding}: {error}')
                    continue
                self._blobs[binding] = blob
                self.generated += 1
            out[binding] = blob
        return out

    def pending(self, state):
        """Blobs the window has not been given yet, newest last."""
        pending = []
        for binding, blob in self.blobs_for(state).items():
            if binding in self._published:
                self.reused += 1
                continue
            self._published.add(binding)
            pending.append(blob)
            self.published += 1
        return pending

    def _build(self, data_id: str, name: str) -> bytes:
        import pygame
        from render import textures

        surface = textures.planet_texture(data_id, size=self.size, seed=seed_for(name))
        if surface.get_bitsize() != 32:
            surface = surface.convert(32)
        # The blob's name is what the window keys its texture table on, so it must be the same
        # string the frame binding carries.
        return codec.surface_blob(surface, name)

    def report(self):
        return {'texture_size': self.size,
                'generated': self.generated,
                'published': self.published,
                'reused': self.reused,
                'cached': len(self._blobs),
                'failures': self.failures[:8]}
