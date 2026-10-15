"""Deterministic persistent exploration; simulation visibility is never cached.

Only an explicit synchronous read-only presentation scope batches sensor inputs;
ordinary GameState queries always validate current state, even within one tick.

Grid coordinates are world-origin floor(x/cell), floor(z/cell), clipped to the
map square [-bounds/2, bounds/2]. A cell is explored when its XZ rectangle
intersects the projected sensor sphere. This coarse memory never grants live
detection: GameState queries use exact 3D center distances and current stats.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..data.store import DataStore
from . import stats
from .colonies import eligible_planet


class SensorQueries:
    """Live queries with positive witnesses, never cached visibility answers.

    A witness is only a candidate: membership, alliance, life, geometry and every
    range dependency are checked on *each* query. Negative queries scan live
    entities, so unannounced spawns/moves/modifier mutations cannot be missed.
    This avoids eager all-source aggregation for the hot combat contact path.
    """
    def __init__(self, state):
        self.state = state
        self._ranges = {}
        self._witnesses = {}

    @staticmethod
    def _eligible(e, allies):
        # A hull in hyperspace transit detects nothing and cannot be detected
        # (issue #92): it drops out of live sensing for the whole ride.
        return (e.operational and e.owner in allies and not e.jump_travelling
                and (e.is_ship or e.is_station or e.is_squadron))

    def radius(self, e):
        st = self.state
        ds = DataStore.get()
        p = st.players.get(e.owner)
        techs = tuple((tid, ds.techs[tid].effects.get("sensor_range_mult"))
                      for tid in p.researched if tid in ds.techs) if p and p.researched else ()
        fleet = st.fleets.get(e.fleet_id) if e.fleet_id is not None else None
        commander = (ds.rules.get("commanders", {}).get(fleet.commander, {})
                     .get("sensor_range")) if fleet and fleet.commander else None
        xp = ds.rules.get("experience", {})
        ship = ds.ships.get(e.data_id) if e.is_ship or e.is_squadron else None
        nebula = st.in_nebula(e.pos)
        key = (e.sensor_range, e.sensor_multiplier(), e.crew, e.max_crew, techs, commander, e.xp,
               tuple(xp.get("levels", [0, 120, 320, 700, 1400])),
               xp.get("max_effective_level", 5), ship.veteran_xp if ship else 100.0,
               ship.max_rank if ship else 1, e.is_ship, e.is_squadron, e.is_station,
               e.ability_active.get("sensor_jammed", 0) > 0, nebula,
               ds.rules.get("sensors", {}).get("nebula_detection_multiplier", 0.3)
               if nebula else None)
        cached = self._ranges.get(e.id)
        if cached is None or cached[0] != key:
            radius = stats.effective_sensor_range(st, e)
            self._ranges[e.id] = (key, radius)
            return radius
        return cached[1]

    def sources(self, player_id):
        allies = self.state.allied_player_ids(player_id)
        if not allies:
            return []
        sources = []
        # Prune transient entries here, not per hot-path query.
        self._ranges = {eid: value for eid, value in self._ranges.items()
                        if eid in self.state.entities}
        for e in sorted(self.state.entities.values(), key=lambda e: e.id):
            if self._eligible(e, allies):
                radius = self.radius(e)
                if radius > 0:
                    sources.append((e, radius))
        return sources

    def _covers(self, e, pos):
        radius = self.radius(e)
        dx, dy, dz = e.pos.x-pos.x, e.pos.y-pos.y, e.pos.z-pos.z
        return radius > 0 and dx*dx + dy*dy + dz*dz <= radius*radius

    def visible(self, player_id, pos, allies=None):
        st = self.state
        if allies is None:
            allies = st.allied_player_ids(player_id)
        if not allies:
            return False
        witness = self._witnesses.get(player_id)
        if (witness is not None and st.entities.get(witness.id) is witness
                and self._eligible(witness, allies) and self._covers(witness, pos)):
            return True
        for e in st.entities.values():
            if e is not witness and self._eligible(e, allies) and self._covers(e, pos):
                self._witnesses[player_id] = e
                return True
        return False


class _PresentationSensorQueries:
    """Phase-local source/range snapshot, only for synchronous read-only views.

    Entity references retain the sensor_sources API for fog geometry. Callers
    must not mutate entities, modifiers or alliances until the scope exits.
    No visibility answers or live-query witnesses are retained across scopes.
    """
    def __init__(self, state):
        self.state = state
        self._sources = {}
        self._radii = {}
        self._spheres = {}

    def sources(self, player_id):
        if player_id not in self._sources:
            allies = self.state.allied_player_ids(player_id)
            sources = []
            for e in sorted(self.state.entities.values(), key=lambda e: e.id):
                if SensorQueries._eligible(e, allies):
                    if e.id not in self._radii:
                        self._radii[e.id] = stats.effective_sensor_range(self.state, e)
                    radius = self._radii[e.id]
                    if radius > 0:
                        sources.append((e, radius))
            self._sources[player_id] = tuple(sources)
            self._spheres[player_id] = tuple((e.pos.x, e.pos.y, e.pos.z, radius)
                                             for e, radius in sources)
        # Preserve the public list contract without exposing the stored batch.
        return list(self._sources[player_id])

    def visible(self, player_id, pos, allies=None):
        if player_id not in self._sources:
            self.sources(player_id)
        for x, y, z, radius in self._spheres[player_id]:
            dx, dy, dz = x-pos.x, y-pos.y, z-pos.z
            if dx*dx + dy*dy + dz*dz <= radius*radius:
                return True
        return False


@contextmanager
def presentation_sensor_batch(state):
    """Batch sensors only while a synchronous presentation phase is read-only.

    Never span simulation or input handling. Sources are captured lazily per
    viewer, with exact authoritative range arithmetic (no grid approximation).
    Nested views share the same batch; even exceptional exits restore the exact
    previous live-query object, including an uninitialized None.
    """
    previous = state._sensor_queries
    if isinstance(previous, _PresentationSensorQueries):
        yield
        return
    state._sensor_queries = _PresentationSensorQueries(state)
    try:
        yield
    finally:
        state._sensor_queries = previous


class VisibilitySystem:
    def __init__(self, state):
        self.state = state
        # Geometry-only, transient cache. Never used by current sensor queries.
        self._footprints = {}
        self._team_coverage = {}

    def _explored_footprint(self, e, radius):
        st = self.state
        size, half = st.visibility_cell_size, st.map_info.bounds / 2.0
        key = (size, half, e.pos.x, e.pos.z, radius)
        cached = self._footprints.get(e.id)
        if cached is not None and cached[0] == key:
            return cached[1]
        lo, hi = math.floor(-half / size), math.ceil(half / size) - 1
        cells = set()
        radius_sq = radius * radius
        # Precompute each axis once rather than clipping/testing both axes for
        # every Cartesian pair. The cell/sphere intersection remains exact.
        zs = []
        for iz in range(max(lo, math.floor((e.pos.z-radius)/size)),
                        min(hi, math.floor((e.pos.z+radius)/size)) + 1):
            dz = max(max(-half, iz*size)-e.pos.z, 0,
                     e.pos.z-min(half, (iz+1)*size))
            zs.append((iz, dz*dz))
        for ix in range(max(lo, math.floor((e.pos.x-radius)/size)),
                        min(hi, math.floor((e.pos.x+radius)/size)) + 1):
            dx = max(max(-half, ix*size)-e.pos.x, 0,
                     e.pos.x-min(half, (ix+1)*size))
            dx_sq = dx*dx
            for iz, dz_sq in zs:
                if dx_sq + dz_sq <= radius_sq:
                    cells.add((ix, iz))
        self._footprints[e.id] = (key, cells)
        return cells

    def update(self, dt: float = 0.0) -> None:
        st = self.state
        # Keep at most one footprint per still-live source entity.
        self._footprints = {eid: cached for eid, cached in self._footprints.items()
                            if eid in st.entities and st.entities[eid].alive}
        planets = sorted((e for e in st.entities.values() if e.alive and e.is_planet),
                         key=lambda e: e.id)
        processed = set()
        for pid in sorted(st.players):
            if pid in processed:
                continue
            allies = st.allied_player_ids(pid)
            processed.update(allies)
            cells = set()
            memory = {}
            for aid in allies:
                cells.update(st.explored_cells.get(aid, set()))
                memory.update({eid: st.planet_snapshot(e) for eid, e in
                               st.discovered_planets.get(aid, {}).items()})
            sources = st.sensor_sources(pid)
            group = tuple(allies)
            signature = (st.visibility_cell_size, st.map_info.bounds,
                         tuple((e.id, e.pos.x, e.pos.z, radius) for e, radius in sources))
            cached = self._team_coverage.get(group)
            if cached is None or cached[0] != signature:
                coverage = set()
                for e, radius in sources:
                    coverage.update(self._explored_footprint(e, radius))
                self._team_coverage[group] = (signature, coverage)
            else:
                coverage = cached[1]
            cells.update(coverage)
            for planet in planets:
                # Match can_see's always-visible colony policy, without rescanning
                # live observers for every other planet: sources are already current.
                if ((eligible_planet(planet) and planet.colonized_by in allies)
                        or any((e.pos.x-planet.pos.x) * (e.pos.x-planet.pos.x)
                               + (e.pos.y-planet.pos.y) * (e.pos.y-planet.pos.y)
                               + (e.pos.z-planet.pos.z) * (e.pos.z-planet.pos.z) <= radius*radius
                               for e, radius in sources)):
                    memory[planet.id] = st.planet_snapshot(planet)
            for aid in allies:
                if st.explored_cells.get(aid) != cells:
                    st.explored_cells[aid] = set(cells)
                st.discovered_planets[aid] = dict(memory)
