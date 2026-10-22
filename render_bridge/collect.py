"""Gather one frame of live simulation state into W02 v2 packed records.

Read-only by construction: every function here reads `GameState` and the data store and
returns records. Nothing assigns to state, and the receipt tool re-hashes the state
before and after to prove it.

This is the W02 producer half. It deliberately mirrors, rather than shares, the
extraction in `tools/render/dump_snapshot.py`: that path is pinned by the W00 approval
and its JSON output, and rewriting it to serve a second consumer would put an approved
file's bytes at risk for no gain.

**Why the resolver cache exists.** The first honest measurement of this path cost about
136 ms per frame for 752 entities, and profiling put ~0.4 s of a 0.43 s run inside
`asset_registry.resolve` -> `_core_manifest` -> `_document`: every entity re-read and
re-validated its manifest JSON, with four `pathlib.resolve()` calls each. That is fine
for an offline export that runs once, and fatal for a per-frame producer. A frame only
needs the *answer* - binding id and scale per (kind, data id, faction) - and an entity
set has ~20 distinct types behind 752 instances, so the answer is memoized per
collector. The cache is per session: `reset_cache()` must be called if the visual
selection changes, and the writer owns that lifetime.
"""
from __future__ import annotations

from operator import attrgetter

import math
import zlib

from . import packed
from . import planets, stations

# Effect kinds raised by `GameState.spawn_effect` today. A kind outside this tuple is
# a hard error rather than a silently dropped picture element, so adding an effect to
# the simulation fails here first and the table is extended on purpose.
EFFECT_KINDS = (
    'beam', 'explosion', 'explosion_small', 'fire', 'jump_arrive', 'jump_charge',
    'jump_depart', 'muzzle', 'repair', 'shield_hit',
)

FLAG_DISABLED_HP = 0.02        # matches the renderer's "combat-ineffective" tint

_ZERO = {'x': 0.0, 'y': 0.0, 'z': 0.0}
_WHITE = (1.0, 1.0, 1.0, 1.0)

#: The instance id the placement preview (#171) rides under. No simulation entity can hold it, and
#: the window keys its per-entity interpolation on the id, so a constant one makes the ghost glide
#: between two frames' cursor positions instead of snapping.
GHOST_ENTITY = 0xFFFFFFFE

#: Legality colours, taken from the deleted legacy preview pass (`render/renderer.py::
#: _draw_placement_preview`, removed with the renderer in #160) so the ghost reads the same green
#: or red the HUD banner already reports. The alpha is the translucency: the window submits any
#: fleet instance below full alpha in its own view after the opaque world, so the preview shows
#: the site behind it instead of covering it.
GHOST_VALID = (0.30, 0.90, 0.55, 0.55)
GHOST_INVALID = (1.00, 0.25, 0.20, 0.50)


def station_binding(data_id, faction):
    from render.faction_visuals import normalize_station_key
    return ':'.join(normalize_station_key(data_id, faction))


def build_tables(bindings, weapon_ids):
    """Bindings plus effect kinds and weapon ids, sorted for a stable table CRC."""
    return packed.Tables.build(bindings, list(EFFECT_KINDS) + list(weapon_ids))


def _fractions(entity):
    # Entities carry `hull` / `max_hull`; `hp` / `max_hp` exist only on subsystems. Reading
    # the subsystem names here silently produced 0 for every entity, which is what the
    # frame carried until a test on a real fight caught it.
    hp = getattr(entity, 'hull', None)
    if hp is None:
        hp = getattr(entity, 'hp', 0.0) or 0.0
    max_hp = getattr(entity, 'max_hull', None)
    if max_hp is None:
        max_hp = getattr(entity, 'max_hp', 0.0) or 0.0
    shields = getattr(entity, 'shields', None) or {}
    max_quad = getattr(entity, 'max_shield_quad', 0.0) or 0.0
    shield = (sum(shields.values()) / (max_quad * len(shields))) if max_quad and shields else 0.0
    return (max(0.0, min(1.0, hp / max_hp)) if max_hp else 0.0,
            max(0.0, min(1.0, shield)))


_ENTITY_ID = attrgetter('id')
_WHITE_BYTES = (255, 255, 255, 255)


def _xyz(value, fallback=(0.0, 0.0, 0.0)):
    """Position from whatever shape the state holds: dict, list, tuple or nothing.

    Live effects keep `pos` as a list (Vec3.to_dict()), so a dict-only reader raised
    AttributeError the first time a frame carried a real effect.
    """
    if value is None:
        return fallback
    if isinstance(value, dict):
        return (float(value.get('x', fallback[0])), float(value.get('y', fallback[1])),
                float(value.get('z', fallback[2])))
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, IndexError, KeyError):
        return fallback


class FrameCollector:
    """Per-session producer: holds the tables and the resolver's memoized answers."""

    def __init__(self, ds, tables, *, asset_selection, ship_size, ship_binding,
                 local_player=0, all_visible=False, visible_ids=None,
                 effect_allow=None, projectile_allow=None,
                 effect_filter=None, projectile_filter=None):
        self.ds = ds
        self.tables = tables
        self._selection = asset_selection
        self._ship_size = ship_size
        self._ship_binding = ship_binding
        self.local_player = local_player
        self.all_visible = all_visible
        # The renderer already computes which entities a player can see once per
        # frame. Recomputing it here costs ~45 ms per frame (see the module note), so
        # a live writer must hand over that set instead of letting this module ask
        # `state.can_see` for every entity.
        self.visible_ids = visible_ids
        # Effects and shots are not entities, so they cannot travel in the id set. The
        # caller passes the renderer's own predicates instead of this module re-deriving
        # fog rules (`render.fog.effect_visible` needs the state, so it is closed over by
        # the caller). None means "keep everything", which is what an all-visible
        # diagnostic frame wants.
        # `*_allow` is the cheap form: a set of `id(effect)` / `id(shot)` the renderer
        # already decided on. A callable `*_filter` stays available for callers that want
        # the decision inline, but it costs a Python call per record (~0.1 ms per 1,000).
        self.effect_allow = effect_allow
        self.projectile_allow = projectile_allow
        self.effect_filter = effect_filter
        self.projectile_filter = projectile_filter
        self._colour_cache: dict = {}
        self._binding_index = {name: index for index, name in enumerate(tables.bindings)}
        self._kind_index = {name: index for index, name in enumerate(tables.kinds)}
        self.reset_cache()

    def _visible(self, state, entity) -> bool:
        if self.visible_ids is not None:
            return entity.id in self.visible_ids
        return state.can_see(self.local_player, entity.id)

    def reset_cache(self):
        """Drop memoized bindings/scales; call after a visual-selection change."""
        self._visual: dict = {}
        self._colour_cache.clear()

    def visual(self, *, is_station, data_id, faction, radius):
        """(binding id, scale) for one entity type, or (None, reason)."""
        key = (bool(is_station), data_id, faction)
        cached = self._visual.get(key)
        if cached is None:
            binding = (station_binding(data_id, faction) if is_station
                       else self._ship_binding(self.ds, data_id, faction))
            if binding is None or binding not in self._binding_index:
                cached = (None, binding or f'<unresolved {data_id}>')
            else:
                scale = radius / 50.0 if is_station else self._ship_size(
                    self.ds, data_id, faction).scale
                cached = (self._binding_index[binding], scale)
            self._visual[key] = cached
        return cached

    def ghost_instance(self, ghost, binding_index=None):
        """The station placement preview as one frame instance, or None (#171).

        `render/input.py::update_placement` already decides where the station would stand and
        whether the site is legal; this only turns that answer into the same record a real station
        is drawn from, so the window needs no ghost pass of its own and the preview is the actual
        authored mesh for that binding.

        Scale is `radius / 50`, the same nominal source radius the entity path uses for stations,
        and the pose is a plain yaw - a preview stands in the world, it does not sit on a surface
        frame. Deliberately no state: this reads the ghost dict and writes no simulation field.
        """
        if not ghost:
            return None
        kind = ghost.get('station_kind')
        faction = ghost.get('faction')
        world = ghost.get('world')
        if not kind or not faction or world is None:
            return None
        try:
            x, y, z = float(world[0]), float(world[1]), float(world[2])
        except (TypeError, IndexError, ValueError):
            return None
        index = self._binding_index if binding_index is None else binding_index
        binding_id = index.get(station_binding(kind, faction))
        if binding_id is None:
            # An unregistered binding is not an error: the ghost simply is not drawn, exactly as an
            # unknown hull is omitted rather than invented.
            return None
        try:
            scale = float(ghost.get('radius') or 120.0) / 50.0
        except (TypeError, ValueError):
            scale = 120.0 / 50.0
        try:
            yaw = float(ghost.get('yaw') or 0.0)
        except (TypeError, ValueError):
            yaw = 0.0
        cos_scaled, sin_scaled = math.cos(yaw) * scale, math.sin(yaw) * scale
        tint = packed.channels(GHOST_VALID if ghost.get('valid', True) else GHOST_INVALID)
        return (GHOST_ENTITY, binding_id, packed.FLAG_GHOST, *tint,
                cos_scaled, 0.0, -sin_scaled,
                0.0, scale, 0.0,
                sin_scaled, 0.0, cos_scaled,
                x, y, z, 1.0, 0.0)

    def collect_into(self, state, buffer, *, tick, frame_index, flags=0, extra_effects=(),
                     ghost=None):
        """Pack one frame straight into `buffer` and return (bytes written, stats).

        This is the frame-rate path. It skips the per-record validation that
        `packed.instance_record` performs, because it reads numbers the simulation
        already holds and the consumer validates the frame it decodes; the validating
        builder stays the API for tooling and tests. Tints are resolved once per owner
        instead of once per entity, and no intermediate record tuples are built.
        """
        view = memoryview(buffer)
        instance_size, effect_size = packed.INSTANCE.size, packed.EFFECT.size
        pack_instance, pack_effect = packed.INSTANCE.pack_into, packed.EFFECT.pack_into
        offset = packed.FRAME.size
        limit0 = len(buffer)
        tints, unknown, omitted, written = {}, set(), 0, 0
        players = state.players

        # attrgetter sorts in C; a lambda here costs ~0.1 ms of a 736-instance frame.
        all_visible, visible_ids = self.all_visible, self.visible_ids
        local_player = self.local_player
        visual_cache, binding_index = self._visual, self._binding_index
        ship_binding, ship_size, ds = self._ship_binding, self._ship_size, self.ds
        cos, sin = math.cos, math.sin
        # Imported here rather than at module scope: render.* imports this package, and the site
        # geometry belongs to the renderer's own surface-frame code, not to a second copy here.
        from render.planet_building_geometry import surface_frame
        trig: dict = {}
        for entity in sorted(state.entities.values(), key=_ENTITY_ID):
            if not entity.alive:
                continue
            # Per entity: only the entity standing on a foundation carries a surface basis. This
            # resets inside the loop - hoisting it one line up leaks a building's basis onto every
            # hull that follows it in id order, which is how a whole fleet becomes a skyscraper.
            surface = None
            # W05: planets travel as instances too. Their binding names the texture the window
            # keeps in its own table (`planet:<data_id>:<name>`), and the scale is the planet's
            # radius because the native body is a unit sphere. Asteroid fields are not spheres
            # and stay out until they have their own pass.
            if entity.is_planet:
                if entity.data_id == 'asteroid_field':
                    omitted += 1
                    continue
                binding_id = binding_index.get(
                    planets.binding_name(entity.data_id,
                                         entity.name_override or entity.data_id))
                if binding_id is None:
                    unknown.add(entity.data_id)
                    continue
                scale = float(entity.radius)
                faction, tint = 'imperial', _WHITE_BYTES
                key = None  # not from the visual cache
            else:
                # Inline the visibility test: it is one method call per entity otherwise, and
                # a supplied set makes it a plain membership test.
                if not all_visible and (
                        entity.id not in visible_ids if visible_ids is not None
                        else not state.can_see(local_player, entity.id)):
                    continue
                if entity.jump_travelling:
                    # A travelling hull has no hull, no glow and no marker in the world view for
                    # anyone, its owner included (issue #162; render/renderer.py sets the same gate
                    # in its one visibility list). Only the sim data path stays whole, so the HUD
                    # minimap keeps tracking the contact from its interpolated sim position.
                    continue
                if entity.owner in players:
                    player = players[entity.owner]
                    faction = player.faction
                    tint = tints.get(entity.owner)
                    if tint is None:
                        tint = tints[entity.owner] = packed.tint_bytes(player.color)
                else:
                    faction, tint = 'imperial', _WHITE_BYTES
                # W05: surface hardware stands on a planet's foundation. Its binding is the
                # per-faction asset (`imperial:planet_extractor`), not the `imperial:<id>` every
                # free-standing station shares, and its transform is the surface frame - a full
                # basis, which is why the record carries FLAG_SURFACE_FRAME and the matrix is used
                # verbatim instead of a heading and a scale.
                slot = entity.planet_building_slot
                planet_id = entity.planet_id
                if slot is not None and planet_id is not None:
                    planet = state.entity(planet_id)
                    if planet is not None:
                        surface = surface_frame(planet, slot)
                if surface is not None:
                    name = f'{faction}:{entity.data_id}'
                    binding_id = binding_index.get(name)
                    if binding_id is None:
                        binding_id = binding_index.get(f'imperial:{entity.data_id}')
                        name = f'imperial:{entity.data_id}'
                    if binding_id is None:
                        unknown.add(name)
                        continue
                    scale = float(entity.radius) / 50.0
                else:
                    key = (entity.is_station, entity.data_id, faction)
                    cached = visual_cache.get(key)
                    if cached is None:
                        cached = self.visual(is_station=entity.is_station, data_id=entity.data_id,
                                             faction=faction, radius=entity.radius)
                    binding_id, scale = cached
                    if binding_id is None:
                        unknown.add(scale)
                        continue
            if offset + instance_size > limit0:
                raise packed.FrameError('buffer too small for the frame')
            # Health and shields inline: _fractions() is a function call plus three
            # getattr calls per entity, and it measured a quarter of the instance half.
            max_hp = entity.max_hull
            hp_frac = entity.hull / max_hp if max_hp else 0.0
            if hp_frac <= FLAG_DISABLED_HP:
                entity_flags = packed.FLAG_DISABLED
            elif hp_frac < 0.5:
                entity_flags = packed.FLAG_DAMAGED
            else:
                entity_flags = 0
            if entity.is_station and surface is None:
                entity_flags |= packed.FLAG_DYNAMIC_MESH
            if surface is not None:
                entity_flags |= packed.FLAG_SURFACE_FRAME
            if hp_frac < 0.0:
                hp_frac = 0.0
            elif hp_frac > 1.0:
                hp_frac = 1.0
            shields = entity.shields
            quad = entity.max_shield_quad
            if shields and quad:
                shield_frac = 0.0
                for value in shields.values():
                    shield_frac += value
                shield_frac /= quad * len(shields)
                if shield_frac < 0.0:
                    shield_frac = 0.0
                elif shield_frac > 1.0:
                    shield_frac = 1.0
            else:
                shield_frac = 0.0
            if surface is not None:
                # origin and basis from surface_frame(): world = origin + scale * (right*x + up*y
                # + forward*z), so the columns are the axes and the translation is the foundation.
                origin, axes = surface
                (rx, ry, rz), (ux, uy, uz), (fx, fy, fz) = axes
                pack_instance(buffer, offset, entity.id, binding_id, entity_flags, *tint,
                              rx * scale, ry * scale, rz * scale,
                              ux * scale, uy * scale, uz * scale,
                              fx * scale, fy * scale, fz * scale,
                              origin[0], origin[1], origin[2],
                              hp_frac, shield_frac)
                offset += instance_size
                written += 1
                continue
            position, yaw = entity.pos, entity.yaw
            # Many hulls share a heading, so cos/sin are memoized per distinct yaw.
            pair = trig.get(yaw)
            if pair is None:
                pair = trig[yaw] = (cos(yaw), sin(yaw))
            cos_scaled, sin_scaled = pair[0] * scale, pair[1] * scale
            # Three columns of three, i.e. the W01 snapshot's 20-float column-major
            # instance transform with its constant 0/1 entries dropped:
            #   (c,0,-t) (0,s,0) (t,0,c) then the translation
            # which is the live renderer's `glRotatef(yaw, 0,1,0)` scaled uniformly.
            # An earlier version swapped the middle and last columns, which collapses the
            # vertical axis to zero and skews every hull with a non-zero yaw.
            pack_instance(buffer, offset, entity.id, binding_id, entity_flags, *tint,
                          cos_scaled, 0.0, -sin_scaled,
                          0.0, scale, 0.0,
                          sin_scaled, 0.0, cos_scaled,
                          position.x, position.y, position.z,
                          hp_frac, shield_frac)
            offset += instance_size
            written += 1

        for record in stations.construction_records(
                state, ds, binding_index, local_player=local_player,
                visible_ids=visible_ids, all_visible=all_visible):
            if offset + instance_size > limit0:
                raise packed.FrameError('buffer too small for the frame')
            pack_instance(buffer, offset, *record)
            offset += instance_size
            written += 1

        ghost_written = False
        if ghost is not None:
            record = self.ghost_instance(ghost, binding_index)
            if record is not None:
                if offset + instance_size > limit0:
                    raise packed.FrameError('buffer too small for the frame')
                pack_instance(buffer, offset, *record)
                offset += instance_size
                written += 1
                ghost_written = True

        effects_written = 0
        kind_index = self._kind_index
        colour_cache = self._colour_cache
        effect_filter, projectile_filter = self.effect_filter, self.projectile_filter
        effect_allow, projectile_allow = self.effect_allow, self.projectile_allow
        limit = len(buffer)

        # Effects, packed straight from the state's own dicts. The generator form that
        # `_transients` uses builds an eight-element tuple and resumes a frame per
        # transient, which measured 2.37 ms for the 1,046 transients of a live frame.
        # This loop reads the values in place, caches the colour conversion by object
        # identity (state effects hold the same tuple for their whole life) and does no
        # floating-point coercion: the values are already floats.
        for effect in state.effects:
            # try/except beats get() + a None test on the hot path: the kinds are in the
            # table for every effect a real frame carries, so the miss branch is rare.
            try:
                idx = kind_index[effect['kind']]
            except KeyError:
                unknown.add(f"<effect kind {effect.get('kind')}>")
                continue
            if effect_allow is not None and id(effect) not in effect_allow:
                continue
            if effect_filter is not None and not effect_filter(effect):
                continue
            if offset + effect_size > limit:
                raise packed.FrameError('buffer too small for the frame')
            p = effect.get('pos')
            kind_of_p = type(p)
            if kind_of_p is list or kind_of_p is tuple:
                px, py, pz = p[0], p[1], p[2]
            elif kind_of_p is dict:
                px, py, pz = p['x'], p['y'], p['z']
            else:
                px = py = pz = 0.0
            tail = effect.get('target_pos') or effect.get('center')
            if tail is None or tail is p:
                ex, ey, ez = px, py, pz
            else:
                kind_of_t = type(tail)
                if kind_of_t is list or kind_of_t is tuple:
                    ex, ey, ez = tail[0], tail[1], tail[2]
                elif kind_of_t is dict:
                    ex, ey, ez = tail['x'], tail['y'], tail['z']
                else:
                    ex, ey, ez = px, py, pz
            try:
                colour = effect['color']
            except KeyError:
                colour = _WHITE
            cached = colour_cache.get(id(colour))
            if cached is None or cached[0] is not colour:
                cached = colour_cache[id(colour)] = (colour, packed.channels(colour))
            pack_effect(buffer, offset, packed.EFFECT_CLASS, 0, idx,
                        px, py, pz, 0.0, 0.0, 0.0, ex, ey, ez,
                        effect['t'] if 't' in effect else 0.0,
                        effect['size'] if 'size' in effect else 1.0,
                        *cached[1])
            offset += effect_size
            effects_written += 1

        for projectile in state.projectiles.values():
            try:
                idx = kind_index[projectile.weapon_id]
            except KeyError:
                unknown.add(f'<weapon {projectile.weapon_id}>')
                continue
            if projectile_allow is not None and id(projectile) not in projectile_allow:
                continue
            if projectile_filter is not None and not projectile_filter(projectile):
                continue
            if offset + effect_size > limit:
                raise packed.FrameError('buffer too small for the frame')
            position = projectile.pos
            px, py, pz = position.x, position.y, position.z
            colour = projectile.color
            cached = colour_cache.get(id(colour))
            if cached is None or cached[0] is not colour:
                cached = colour_cache[id(colour)] = (colour, packed.channels(colour))
            pack_effect(buffer, offset, packed.PROJECTILE_CLASS,
                        1 if projectile.is_beam else 0, idx,
                        px, py, pz, 0.0, 0.0, 0.0, px, py, pz,
                        projectile.life, projectile.size, *cached[1])
            offset += effect_size
            effects_written += 1

        for record in extra_effects:  # measurement hook; empty in production
            if offset + effect_size > len(buffer):
                raise packed.FrameError('buffer too small for the frame')
            pack_effect(buffer, offset, *record)
            offset += effect_size
            effects_written += 1

        length = offset - packed.FRAME.size
        packed.FRAME.pack_into(buffer, 0, packed.MAGIC, packed.VERSION, packed.WORLD,
                               tick, frame_index, written, effects_written,
                               self.tables.crc32, flags, length,
                               zlib.crc32(view[packed.FRAME.size:offset]))
        return view[:offset], {
            'instances': written, 'effects': effects_written,
            'omitted_planets': omitted, 'unknown_bindings': sorted(unknown),
            'ghost': ghost_written, 'tables': self.tables}

    def collect(self, state, ghost=None):
        """Return (instances, effects, stats) for this state. Never writes state."""
        instances, omitted, unknown = [], 0, set()
        for entity in sorted(state.entities.values(), key=_ENTITY_ID):
            if not entity.alive:
                continue
            if entity.is_planet:
                # W05: planets ride as instances whose binding names their texture, with the
                # radius as the scale of the unit sphere the window draws.
                if entity.data_id == 'asteroid_field':
                    omitted += 1
                    continue
                binding_id = self._binding_index.get(
                    planets.binding_name(entity.data_id,
                                         entity.name_override or entity.data_id))
                if binding_id is None:
                    unknown.add(entity.data_id)
                    continue
                scale = float(entity.radius)
            else:
                if not self.all_visible and not self._visible(state, entity):
                    continue
                if entity.jump_travelling:
                    # See collect_into: in hyperspace there is nothing to draw, for anyone (#162).
                    continue
                faction = (state.players[entity.owner].faction
                           if entity.owner in state.players else 'imperial')
                binding_id, scale = self.visual(is_station=entity.is_station,
                                                data_id=entity.data_id,
                                                faction=faction, radius=entity.radius)
                if binding_id is None:
                    unknown.add(scale)
                    continue
            colour = (state.players[entity.owner].color
                      if entity.owner in state.players else (1.0, 1.0, 1.0))
            hp_frac, shield_frac = _fractions(entity)
            flags = packed.FLAG_DYNAMIC_MESH if entity.is_station else 0
            if hp_frac <= FLAG_DISABLED_HP:
                flags |= packed.FLAG_DISABLED
            elif hp_frac < 0.5:
                flags |= packed.FLAG_DAMAGED
            instances.append(packed.instance_record(
                entity_id=entity.id, binding_id=binding_id,
                matrix=packed.matrix_from_pose(entity.pos.to_tuple(), entity.yaw, scale),
                tint=(*colour, 1.0), flags=flags, hp=hp_frac, shield=shield_frac))

        instances.extend(stations.construction_records(
            state, self.ds, self._binding_index, local_player=self.local_player,
            visible_ids=self.visible_ids, all_visible=self.all_visible))
        record = self.ghost_instance(ghost)
        if record is not None:
            instances.append(record)
        effects = []
        for cls, kind, pos, end, life, size, colour, beam in self._transients(state, unknown):
            effects.append(packed.effect_record(
                cls=cls, kind_id=self._kind_index[kind], position=pos, end_position=end,
                life=life, size=size, color=colour, is_beam=beam))

        return instances, effects, {
            'instances': len(instances), 'effects': len(effects),
            'omitted_planets': omitted, 'unknown_bindings': sorted(unknown),
            'tables': self.tables}

    def _transients(self, state, unknown):
        """Yield (class, kind, pos, end, life, size, colour, is_beam) for effects and shots."""
        for effect in state.effects:
            kind = effect.get('kind')
            if kind not in self._kind_index:
                unknown.add(f'<effect kind {kind}>')
                continue
            pos = _xyz(effect.get('pos'))
            end = _xyz(effect.get('target_pos') or effect.get('center'), pos)
            colour = effect.get('color') or (1.0, 1.0, 1.0, 1.0)
            colour = tuple(float(c) for c in colour)
            yield (packed.EFFECT_CLASS, kind, pos, end,
                   float(effect.get('t', 0.0)), float(effect.get('size', 1.0)),
                   colour + (1.0,) * (4 - len(colour)), False)
        for projectile in state.projectiles.values():
            weapon = projectile.weapon_id
            if weapon not in self._kind_index:
                unknown.add(f'<weapon {weapon}>')
                continue
            colour = tuple(projectile.color) + (1.0,) * (4 - len(projectile.color))
            position = tuple(projectile.pos.to_tuple())
            yield (packed.PROJECTILE_CLASS, weapon, position, position,
                   float(projectile.life), float(projectile.size), colour,
                   bool(projectile.is_beam))


def required_names(state, ds, *, ship_size, ship_binding, local_player=0, all_visible=False):
    """Bindings and weapon ids this state can select, for a session table."""
    bindings, weapons = set(), set()
    resolved: dict = {}
    for entity in state.entities.values():
        if not entity.alive:
            continue
        if entity.is_planet and all_visible is False and not state.can_see(local_player, entity.id):
            continue
        if not all_visible and not state.can_see(local_player, entity.id):
            continue
        faction = state.players[entity.owner].faction if entity.owner in state.players else 'imperial'
        if entity.is_planet:
            if entity.data_id != 'asteroid_field':
                bindings.add(planets.binding_name(entity.data_id,
                                                  entity.name_override or entity.data_id))
            continue
        key = (entity.is_station, entity.data_id, faction)
        if key not in resolved:
            resolved[key] = (station_binding(entity.data_id, faction) if entity.is_station
                             else ship_binding(ds, entity.data_id, faction))
        if resolved[key]:
            bindings.add(resolved[key])
    # Surface hardware is built during a match, not spawned with the map, so its bindings have to
    # be reserved before any building exists: the session table is built once and the collector
    # must be able to name a binding the moment the first foundation appears.
    from game.systems.planet_buildings import BUILDING_TYPES
    factions = {player.faction for player in state.players.values()} | {'imperial'}
    for faction in sorted(factions):
        from render.faction_visuals import STATION_TYPES
        for kind in (*BUILDING_TYPES, *STATION_TYPES):
            bindings.add(f'{faction}:{kind}')
    bindings.add(stations.SCAFFOLD)
    # A session's table never changes. Reserve the public unit/weapon catalogue,
    # not just hulls present at startup, or newly built types are silently omitted.
    for ship_id, data in ds.ships.items():
        binding = ship_binding(ds, ship_id, data.faction)
        if binding:
            bindings.add(binding)
    weapons.update(ds.weapons)
    weapons.update(projectile.weapon_id for projectile in state.projectiles.values())
    return bindings, weapons


def collect(state, ds, tables, *, asset_selection, ship_size, ship_binding,
            local_player=0, all_visible=False):
    """One-shot wrapper. Builds a table when `tables` is None.

    A per-frame producer must hold a `FrameCollector` instead: building the table and
    the resolver cache costs more than one frame.
    """
    if tables is None:
        table_bindings, table_weapons = required_names(
            state, ds, ship_size=ship_size, ship_binding=ship_binding,
            local_player=local_player, all_visible=all_visible)
        tables = build_tables(table_bindings, table_weapons)
    return FrameCollector(ds, tables, asset_selection=asset_selection,
                          ship_size=ship_size, ship_binding=ship_binding,
                          local_player=local_player,
                          all_visible=all_visible).collect(state)
