"""The live producer: a running match, gathered into the rings the C++ window draws from.

`stream_ring.py` streams a *fixture*; this is the same transport for the game's own loop, so
`main.py --renderer cpp` can hand the window the match the player is actually playing. The rule
that holds everywhere else holds here: **Python decides, the window draws.** Nothing in this
module reads an input event, moves a ship or resolves a contact; it copies answers the simulation
already produced into bytes and publishes them.

Nothing here is a second copy of the renderer's *decisions* - only of its transport:

* the frame (instances, effects, projectiles, tables) - `render_bridge.collect`
* the HUD, painted by the same `render.hud` code the legacy window paints (design A) - `overlay`
* ownership cues - `render.primitive_batch`
* weapon fire, beams, shields, blasts, contacts, domes - `render.emissive_batch`
* the fog classification - `render.fog`
* planet textures - `render.planet_blobs`

What it does *not* do is decide who can see what: the renderer's visibility answers are computed
by the game and handed in, because `state.can_see` costs ~45 ms p95 (see docs/RENDER_BRIDGE_W02.md
section 4) and the bridge is supposed to receive that answer, not derive it.
"""
from __future__ import annotations

import time
from pathlib import Path

from render_bridge import camera as camera_codec
from render_bridge import emissive as emissive_codec
from render_bridge import fogmap as fog_codec
from render_bridge import markers as marker_codec
from render_bridge import overlay as overlay_codec
from render_bridge import planets as planet_codec
from render_bridge import collect, packed, ring


class LiveSession:
    """One running match, published into a directory of rings.

    The rings are created here and drained by the window whenever it attaches; a window that
    attaches late still gets the HUD because the first overlay frame is a whole surface and the
    session republishes one every `overlay_keyframe` seconds.
    """

    def __init__(self, state, ds, *, directory, local_player: int = 0, size=(1280, 800),
                 marker_mode: str = 'all', planet_texture: int = 256,
                 overlay_keyframe: float = 2.0, max_instances=None, max_effects=None,
                 fps_probe=None, camera=None):
        self.state, self.ds = state, ds
        # The game's own camera, if it was handed in: the window looks where the player looks, and
        # only then can a click mean anything.
        self.camera = camera
        self.local_player = int(local_player)
        self.size = (int(size[0]), int(size[1]))
        self.marker_mode = marker_mode
        self.overlay_keyframe = float(overlay_keyframe)
        self.fps_probe = fps_probe
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

        self.paths = {
            'frame': self.directory / 'frame.ring',
            'tables': self.directory / 'frame.ring.tables',
            'overlay': self.directory / 'hud.ring',
            'emit': self.directory / 'emit.ring',
            'markers': self.directory / 'markers.ring',
            'fog': self.directory / 'fog.ring',
            'planets': self.directory / 'planets.ring',
            'input': self.directory / 'input.ring',
            'camera': self.directory / 'camera.ring',
        }

        # The session tables are written once, beside the ring: frame records index them.
        from render import asset_selection
        from render.ship_sizes import ship_size
        _, _, seeded = collect.collect(
            state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.tables = seeded['tables']
        self.paths['tables'].write_bytes(self.tables.encode())
        self.collector = collect.FrameCollector(
            ds, self.tables, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, local_player=self.local_player,
            all_visible=False, visible_ids=set(), effect_allow=set(), projectile_allow=set())
        self.buffer = bytearray(packed.frame_size(max_instances or packed.MAX_INSTANCES,
                                                  max_effects or packed.MAX_EFFECTS))

        self._frames = ring.Ring.create(self.paths['frame'], slots=8, slot_bytes=1 << 20)
        self._emit = ring.Ring.create(
            self.paths['emit'], slots=8,
            slot_bytes=emissive_codec.HEADER.size
            + emissive_codec.MAX_RECORDS * emissive_codec.RECORD_BYTES)
        self._markers = ring.Ring.create(
            self.paths['markers'], slots=8,
            slot_bytes=marker_codec.HEADER.size
            + marker_codec.MAX_RECORDS * marker_codec.RECORD_BYTES)

        # HUD: composed here, the window only uploads the surface and its dirty rects.
        import pygame
        pygame.font.init()
        from render.hud import HUD
        self.hud = HUD(self.size[0], self.size[1], state)
        self._overlay = ring.Ring.create(
            self.paths['overlay'], slots=4,
            slot_bytes=(overlay_codec.HEADER_BYTES
                        + overlay_codec.MAX_RECTS * overlay_codec.RECT_BYTES
                        + self.size[0] * self.size[1] * 4))
        self._overlay_published = 0
        self._overlay_last_full = float('-inf')
        self._overlay_keyframes = 0

        import math
        from render import fog
        cells = max(1, math.ceil(state.map_info.bounds / state.visibility_cell_size))
        self._fog_mask = fog.FogMask()
        self._fog_cells = cells
        self._fog_generation = 0
        self._fog_last = None
        self._fog = ring.Ring.create(
            self.paths['fog'], slots=4,
            slot_bytes=fog_codec.HEADER_BYTES + cells * cells * 4 + 28)   # 20 begin + 8 trailer

        from render.planet_blobs import PlanetTextures
        self._planet_textures = PlanetTextures(size=int(planet_texture))
        self._planet_ring = ring.Ring.create(
            self.paths['planets'], slots=8,
            slot_bytes=planet_codec.HEADER_BYTES + planet_codec.MAX_NAME
            + int(planet_texture) * int(planet_texture) * 4)

        from render.emissive_batch import PlanetDomes
        self._domes = PlanetDomes()

        self._camera_ring = ring.Ring.create(
            self.paths['camera'], slots=4, slot_bytes=1024)   # the ring's own minimum

        self._radius_cache: dict = {}
        self.frames = 0
        self.perf = {'frame_ms': [], 'overlay_ms': [], 'emit_ms': [], 'fog_ms': []}
        self.counts = {'instances': 0, 'primitives': 0, 'markers': 0, 'overlay_bytes': 0,
                       'planet_blobs': 0, 'fog_uploads': 0}

    # ------------------------------------------------------------------ helpers
    def radius_of(self, entity):
        """World radius of the hull the frame drew, so a cue encloses what it is drawn around.

        Memoized per hull class: `ship_size` is a catalogue lookup, and it was being called once per
        entity per frame - 688 shields cost 138 ms, which is what the "emit block" measurement was
        actually looking at. The cache key is everything `ship_size` depends on.
        """
        if entity.is_planet or entity.is_station:
            return float(entity.radius)
        faction = (self.state.players[entity.owner].faction
                   if entity.owner in self.state.players else 'imperial')
        key = (entity.data_id, faction, float(entity.radius))
        cached = self._radius_cache.get(key)
        if cached is not None:
            return cached
        binding, scale = self.collector.visual(is_station=entity.is_station,
                                               data_id=entity.data_id, faction=faction,
                                               radius=entity.radius)
        if not isinstance(scale, (int, float)):
            return 0.0
        from render.ship_sizes import ship_size
        size = ship_size(self.ds, entity.data_id, faction)
        radius = float(getattr(size, 'radius', 0.0))
        self._radius_cache[key] = radius
        return radius

    def _weapon_type_of(self, weapon_id):
        weapon = self.ds.weapons.get(weapon_id) if weapon_id is not None else None
        return weapon.type if weapon is not None else None

    # ------------------------------------------------------------------ publish
    def publish(self, state, *, selection=(), visible_ids=None, effect_allow=None,
                shot_allow=None, dt: float = 1.0 / 30.0) -> dict:
        """Publish one frame. Every visibility argument is an *answer* from the game."""
        from render import emissive_batch, primitive_batch
        from render.renderer import projectile_extents

        self.collector.visible_ids = visible_ids
        self.collector.effect_allow = effect_allow
        self.collector.projectile_allow = shot_allow

        started = time.perf_counter()
        frame, counts = self.collector.collect_into(
            state, self.buffer, tick=state.tick, frame_index=self.frames)
        self._frames.publish(bytes(frame))
        frame_ms = (time.perf_counter() - started) * 1000.0

        effects = [fx for fx in state.effects
                   if effect_allow is None or id(fx) in effect_allow]
        shots = [shot for shot in state.projectiles.values()
                 if shot_allow is None or id(shot) in shot_allow]
        started = time.perf_counter()
        primitives, emit_stats = emissive_batch.build(
            effects, shots, self._weapon_type_of, projectile_extents)
        shown = self.collector.visible_ids
        shielded = [entity for entity in state.entities.values()
                    if entity.alive and (entity.is_ship or entity.is_squadron or entity.is_station)
                    and (shown is None or entity.id in shown)]
        primitives = (primitives + emissive_batch.shields(shielded, self.radius_of)
                      + emissive_batch.hits(effects)[0]
                      + self._domes.step(state, dt))
        self._emit.publish(bytes(emissive_codec.encode(primitives)))
        emit_ms = (time.perf_counter() - started) * 1000.0

        cues = primitive_batch.build(state, self.local_player, set(selection), shown,
                                     radius_of=self.radius_of, mode=self.marker_mode)
        self._markers.publish(bytes(marker_codec.encode(cues)))

        started = time.perf_counter()
        self.hud.compose(set(selection), None, self.local_player, False, '', 0.0, 0.0)
        dirty = self.hud.recorder.take_dirty()
        keyframe = (self._overlay_published == 0
                    or (self.overlay_keyframe > 0
                        and time.monotonic() - self._overlay_last_full >= self.overlay_keyframe))
        if keyframe:
            self._overlay_last_full = time.monotonic()
            self._overlay_keyframes += 1
            payload = overlay_codec.encode_surface_full(self.hud.overlay)
        else:
            payload = overlay_codec.encode_surface(self.hud.overlay, dirty)
        self._overlay.publish(payload)
        self._overlay_published += 1
        overlay_ms = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        pending = self._planet_textures.pending(state)
        for blob in pending:
            self._planet_ring.publish(blob)
        surface = self._fog_mask.surface(state, self.local_player)
        if surface is not self._fog_last:
            self._fog_last = surface
            self._fog_generation += 1
            import pygame
            rgba = pygame.image.tobytes(surface, 'RGBA', False)
            self._fog.publish(bytes(fog_codec.encode_blob(
                surface.get_width(), state.visibility_cell_size,
                state.map_info.bounds, self._fog_generation, rgba)))
            self.counts['fog_uploads'] += 1
        world_ms = (time.perf_counter() - started) * 1000.0

        self.frames += 1
        self.counts['instances'] = int(counts.get('instances', 0)) if isinstance(counts, dict) \
            else self.counts['instances']
        self.counts['primitives'] = len(primitives)
        self.counts['markers'] = len(cues)
        if self.camera is not None:
            self._camera_ring.publish(camera_codec.encode(self.camera))
        self.counts['overlay_bytes'] = len(payload)
        self.counts['planet_blobs'] += len(pending)
        for key, value in (('frame_ms', frame_ms), ('overlay_ms', overlay_ms),
                           ('emit_ms', emit_ms), ('fog_ms', world_ms)):
            self.perf[key].append(value)
        return dict(self.counts, frame_ms=frame_ms, overlay_ms=overlay_ms, emit_ms=emit_ms,
                    world_ms=world_ms, keyframe=keyframe)

    # ------------------------------------------------------------------ lifecycle
    def close(self):
        for handle in (self._frames, self._emit, self._markers, self._overlay, self._fog,
                       self._planet_ring, self._camera_ring):
            try:
                handle.close()
            except Exception:
                pass

    def report(self) -> dict:
        def stats(values):
            if not values:
                return {'samples': 0}
            ordered = sorted(values)
            return {'samples': len(values),
                    'median_ms': round(ordered[len(ordered) // 2], 3),
                    'p95_ms': round(ordered[int(len(ordered) * 0.95) - 1], 3)}

        return {
            'frames': self.frames,
            'rings': {name: str(path) for name, path in self.paths.items()},
            'counts': dict(self.counts),
            'keyframes': self._overlay_keyframes,
            'cost': {name: stats(values) for name, values in self.perf.items()},
            'note': 'publish cost only; it excludes simulation, the renderer and the window',
        }
