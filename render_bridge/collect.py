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

import math
import zlib

from . import packed

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


def build_tables(bindings, weapon_ids):
    """Bindings plus effect kinds and weapon ids, sorted for a stable table CRC."""
    return packed.Tables.build(bindings, list(EFFECT_KINDS) + list(weapon_ids))


def _fractions(entity):
    hp = getattr(entity, 'hp', 0.0) or 0.0
    max_hp = getattr(entity, 'max_hp', 0.0) or 0.0
    shields = getattr(entity, 'shields', None) or {}
    max_quad = getattr(entity, 'max_shield_quad', 0.0) or 0.0
    shield = (sum(shields.values()) / (max_quad * len(shields))) if max_quad and shields else 0.0
    return (max(0.0, min(1.0, hp / max_hp)) if max_hp else 0.0,
            max(0.0, min(1.0, shield)))


class FrameCollector:
    """Per-session producer: holds the tables and the resolver's memoized answers."""

    def __init__(self, ds, tables, *, asset_selection, ship_size, ship_binding,
                 local_player=0, all_visible=False, visible_ids=None):
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

    def visual(self, *, is_station, data_id, faction, radius):
        """(binding id, scale) for one entity type, or (None, reason)."""
        key = (bool(is_station), data_id, faction)
        cached = self._visual.get(key)
        if cached is None:
            binding = ('imperial:' + data_id if is_station
                       else self._ship_binding(self.ds, data_id, faction))
            if binding is None or binding not in self._binding_index:
                cached = (None, binding or f'<unresolved {data_id}>')
            else:
                scale = radius / 50.0 if is_station else self._ship_size(
                    self.ds, data_id, faction).scale
                cached = (self._binding_index[binding], scale)
            self._visual[key] = cached
        return cached

    def collect_into(self, state, buffer, *, tick, frame_index, flags=0, extra_effects=()):
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
        tints, unknown, omitted, written = {}, set(), 0, 0
        players = state.players

        for entity in sorted(state.entities.values(), key=lambda e: e.id):
            if not entity.alive:
                continue
            if entity.is_planet:
                omitted += 1
                continue
            if not self.all_visible and not self._visible(state, entity):
                continue
            if entity.owner in players:
                player = players[entity.owner]
                faction, tint = player.faction, tints.get(entity.owner)
                if tint is None:
                    tint = tints[entity.owner] = packed.tint_bytes(player.color)
            else:
                faction, tint = 'imperial', (255, 255, 255, 255)
            binding_id, scale = self.visual(is_station=entity.is_station,
                                            data_id=entity.data_id,
                                            faction=faction, radius=entity.radius)
            if binding_id is None:
                unknown.add(scale)
                continue
            if offset + instance_size > len(buffer):
                raise packed.FrameError('buffer too small for the frame')
            hp_frac, shield_frac = _fractions(entity)
            entity_flags = 0
            if hp_frac <= FLAG_DISABLED_HP:
                entity_flags = packed.FLAG_DISABLED
            elif hp_frac < 0.5:
                entity_flags = packed.FLAG_DAMAGED
            position, yaw = entity.pos, entity.yaw
            cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
            cos_scaled, sin_scaled = cos_yaw * scale, sin_yaw * scale
            pack_instance(buffer, offset, entity.id, binding_id, entity_flags, *tint,
                          cos_scaled, 0.0, -sin_scaled,
                          sin_scaled, 0.0, cos_scaled,
                          0.0, 0.0, scale,
                          position.x, position.y, position.z,
                          hp_frac, shield_frac)
            offset += instance_size
            written += 1

        kind_index = self._kind_index
        effects_written = 0
        for effect in state.effects:
            kind = effect.get('kind')
            if kind not in kind_index:
                unknown.add(f'<effect kind {kind}>')
                continue
            if offset + effect_size > len(buffer):
                raise packed.FrameError('buffer too small for the frame')
            pos = effect.get('pos') or _ZERO
            end = effect.get('target_pos') or pos
            colour = effect.get('color') or _WHITE
            pack_effect(buffer, offset, packed.EFFECT_CLASS, 0, kind_index[kind],
                        pos.get('x', 0.0), pos.get('y', 0.0), pos.get('z', 0.0),
                        _ZERO['x'], _ZERO['y'], _ZERO['z'],
                        end.get('x', pos.get('x', 0.0)), end.get('y', pos.get('y', 0.0)),
                        end.get('z', pos.get('z', 0.0)),
                        float(effect.get('t', 0.0)), float(effect.get('size', 1.0)),
                        *packed.channels(colour))
            offset += effect_size
            effects_written += 1

        for projectile in state.projectiles.values():
            if projectile.weapon_id not in kind_index:
                unknown.add(f'<weapon {projectile.weapon_id}>')
                continue
            if offset + effect_size > len(buffer):
                raise packed.FrameError('buffer too small for the frame')
            pack_effect(buffer, offset, packed.PROJECTILE_CLASS,
                        1 if projectile.is_beam else 0, kind_index[projectile.weapon_id],
                        projectile.pos.x, projectile.pos.y, projectile.pos.z,
                        projectile.vel.x, projectile.vel.y, projectile.vel.z,
                        projectile.pos.x, projectile.pos.y, projectile.pos.z,
                        float(projectile.life), float(projectile.size),
                        *packed.channels(projectile.color))
            offset += effect_size
            effects_written += 1

        for record in extra_effects:            # measurement hook; empty in production
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
            'tables': self.tables}

    def collect(self, state):
        """Return (instances, effects, stats) for this state. Never writes state."""
        instances, omitted, unknown = [], 0, set()
        for entity in sorted(state.entities.values(), key=lambda e: e.id):
            if not entity.alive:
                continue
            if entity.is_planet:
                omitted += 1
                continue
            if not self.all_visible and not self._visible(state, entity):
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
            flags = 0
            if hp_frac <= FLAG_DISABLED_HP:
                flags |= packed.FLAG_DISABLED
            elif hp_frac < 0.5:
                flags |= packed.FLAG_DAMAGED
            instances.append(packed.instance_record(
                entity_id=entity.id, binding_id=binding_id,
                matrix=packed.matrix_from_pose(entity.pos.to_tuple(), entity.yaw, scale),
                tint=(*colour, 1.0), flags=flags, hp=hp_frac, shield=shield_frac))

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
            pos = effect.get('pos') or {}
            end = effect.get('target_pos') or pos
            colour = effect.get('color') or (1.0, 1.0, 1.0, 1.0)
            yield (packed.EFFECT_CLASS, kind,
                   (pos.get('x', 0.0), pos.get('y', 0.0), pos.get('z', 0.0)),
                   (end.get('x', pos.get('x', 0.0)), end.get('y', pos.get('y', 0.0)),
                    end.get('z', pos.get('z', 0.0))),
                   float(effect.get('t', 0.0)), float(effect.get('size', 1.0)),
                   tuple(colour) + (1.0,) * (4 - len(colour)), False)
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
        if not entity.alive or entity.is_planet:
            continue
        if not all_visible and not state.can_see(local_player, entity.id):
            continue
        faction = state.players[entity.owner].faction if entity.owner in state.players else 'imperial'
        key = (entity.is_station, entity.data_id, faction)
        if key not in resolved:
            resolved[key] = ('imperial:' + entity.data_id if entity.is_station
                             else ship_binding(ds, entity.data_id, faction))
        if resolved[key]:
            bindings.add(resolved[key])
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
