"""Persistent fighter survey intent; visibility alone records actual discoveries."""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3
from ..data.store import DataStore
from .jump import clear_jump_orders, detach_jumpers


DEFAULTS = {'threat_margin': 350.0, 'arrival_radius': 80.0}


def validate_exploration_rules(rules) -> None:
    block = rules.get('exploration', {})
    if not isinstance(block, dict):
        raise ValueError('exploration must be an object')
    for key, default in DEFAULTS.items():
        value = block.get(key, default)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f'exploration {key} must be finite and positive')


def exploration_capable(entity) -> bool:
    """Catalogue capability, without mutating entity or requiring ownership."""
    data = DataStore.get().ships.get(entity.data_id)
    return bool(data and data.is_squadron and data.category == 'fighter_squadron'
                and entity.is_squadron and not entity.is_station and not entity.is_planet
                and not entity.is_construction and not entity.boarding)


class ExplorationSystem:
    def __init__(self, state):
        self.state = state

    def start(self, entity, player: int) -> bool:
        if (player not in self.state.players or entity.owner != player
                or self.state.entity(entity.id) is not entity
                or not entity.operational or not exploration_capable(entity)
                or entity.jump_travelling):
            return False
        detach_jumpers(self.state, [entity])
        clear_jump_orders(entity)
        entity.jump_charge = 0.0
        entity.jump_target = None
        entity.order_type = 'explore'
        self.update(0)
        return True

    def cancel(self, entity) -> None:
        if entity.order_type == 'explore':
            clear_jump_orders(entity)

    def _cells(self, entity, *, unexplored_only=True):
        st = self.state
        half = st.map_info.bounds / 2
        cell = st.visibility_cell_size
        for x in range(math.floor(-half / cell), math.ceil(half / cell)):
            for z in range(math.floor(-half / cell), math.ceil(half / cell)):
                lo_x, hi_x = max(-half, x * cell), min(half, (x + 1) * cell)
                lo_z, hi_z = max(-half, z * cell), min(half, (z + 1) * cell)
                pos = Vec3((lo_x + hi_x) / 2, entity.pos.y, (lo_z + hi_z) / 2)
                if not unexplored_only or not st.is_position_explored(entity.owner, pos):
                    yield pos

    def _detour(self, entity, obstacles):
        """Stable grid BFS returns only its first hop; no unsaved route cursor.

        Replanning from the current cell gives identical paths after restore,
        even when intermediate waypoints were explored long before this mission.
        """
        from collections import deque
        st = self.state
        root = st.visibility_cell(entity.pos)
        if root is None:
            return None
        positions = {st.visibility_cell(p): p for p in self._cells(entity, unexplored_only=False)}
        positions[root] = entity.pos
        queue = deque([root])
        first_hop = {root: None}
        while queue:
            current = queue.popleft()
            if current != root and not st.is_position_explored(entity.owner, positions[current]):
                return positions[first_hop[current]].copy()
            x, z = current
            neighbors = sorted((x + dx, z + dz) for dx in (-1, 0, 1)
                               for dz in (-1, 0, 1) if dx or dz)
            for neighbor in neighbors:
                if (neighbor not in positions or neighbor in first_hop
                        or not self._route_safe(positions[current], positions[neighbor], obstacles)):
                    continue
                first_hop[neighbor] = neighbor if current == root else first_hop[current]
                queue.append(neighbor)
        return None

    def _obstacles(self, entity):
        """Only detected contacts may contribute live positions or weapon stats."""
        st = self.state
        ds = DataStore.get()
        for other in sorted(st.entities.values(), key=lambda e: e.id):
            if other.is_planet:
                # Planet geometry is public; ownership/crew/defenses are not.
                yield other.pos, other.radius * 1.2 + entity.radius + 80
                continue
            if (not other.operational or not st.is_enemy(entity.owner, other.owner)
                    or not st.can_see(entity.owner, other.id)):
                continue
            data = ds.stations.get(other.data_id) if other.is_station else ds.ships.get(other.data_id)
            reach = 0.0
            if data:
                for ref in data.weapons:
                    weapon = ds.resolve_weapon(ref['weapon'] if isinstance(ref, dict) else ref)
                    if weapon.targets in ('all', 'fighters'):
                        reach = max(reach, weapon.range)
            # Even unarmed detected hulls are not useful exploration waypoints.
            yield other.pos, max(reach, other.radius + entity.radius) + DataStore.get().rules.get(
                'exploration', {}).get('threat_margin', DEFAULTS['threat_margin'])

    @staticmethod
    def _route_safe(start, end, obstacles) -> bool:
        delta = end - start
        for center, radius in obstacles:
            offset = start - center
            if end.dist_sq(center) <= radius * radius:
                return False
            if offset.length_sq() <= radius * radius:
                # Escape an existing bubble, never travel deeper through it.
                if offset.dot(delta) < 0:
                    return False
                continue
            fraction = max(0.0, min(1.0, -offset.dot(delta) / max(1e-12, delta.length_sq())))
            if (offset + delta * fraction).length_sq() <= radius * radius:
                return False
        return True

    def update(self, dt: float) -> None:
        arrival = DataStore.get().rules.get('exploration', {}).get(
            'arrival_radius', DEFAULTS['arrival_radius'])
        for entity in sorted(self.state.entities.values(), key=lambda e: e.id):
            if entity.order_type != 'explore':
                continue
            if not entity.operational or not exploration_capable(entity):
                self.cancel(entity)
                continue
            entity.current_target = None
            entity.order_target_id = None
            target = entity.order_target_pos
            obstacles = list(self._obstacles(entity))
            unsafe = target is not None and not self._route_safe(entity.pos, target, obstacles)
            # Discovery is sensor/rectangle overlap, not waypoint arrival.
            # Finish a safe persisted hop even when its cell was just surveyed;
            # aborting on coverage strands fighters before the final cell and
            # repeatedly replans already-explored detour hops while turning.
            if target is None or entity.pos.dist(target) < arrival or unsafe:
                if unsafe:
                    entity.vel = Vec3()  # brake before turning away from new contacts
                cells = list(self._cells(entity))
                entity.order_target_pos = min((p for p in cells
                    if self._route_safe(entity.pos, p, obstacles)),
                    key=lambda p: (entity.pos.dist_sq(p), p.x, p.z), default=None)
                needs_escape = any(entity.pos.dist_sq(center) <= radius * radius
                                   for center, radius in obstacles)
                if entity.order_target_pos is None and (cells or needs_escape):
                    entity.order_target_pos = self._detour(entity, obstacles)
                if entity.order_target_pos is None and (cells or needs_escape):
                    # Avoid detected threats even when surveying is complete.
                    # Retreat without replacing the persistent survey mission.
                    homes = (h for h in self.state.entities.values()
                             if h.id != entity.id and h.owner == entity.owner
                             and h.operational and (h.is_ship or h.is_station)
                             and self._route_safe(entity.pos, h.pos, obstacles))
                    home = min(homes, key=lambda h: (entity.pos.dist_sq(h.pos), h.id), default=None)
                    if home is not None and entity.pos.dist(home.pos) >= arrival:
                        entity.order_target_pos = home.pos.copy()
                if entity.order_target_pos is None:
                    entity.vel = Vec3()
