"""GameState: the single source of mutable truth.

Everything the simulation needs lives here and everything here is serializable.
The renderer reads it; systems write it; the save system dumps it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..systems.visibility import SensorQueries

from .vectors import Vec3
from .entity import Entity
from .world import IdGenerator, SpatialGrid, Fleet, Projectile
from .commands import PlayerCommand
from .events import EventBus


@dataclass(slots=True)
class PlayerState:
    id: int
    faction: str = "imperial"
    is_ai: bool = False
    ai_difficulty: str = "normal"          # easy|normal|hard
    name: str = "Player"
    credits: float = 0.0
    materials: float = 0.0
    energy: float = 0.0
    crew: float = 0.0
    command_capacity: int = 0
    team: int | None = None
    researched: set = field(default_factory=set)
    researching: dict = field(default_factory=dict)   # tech_id -> {"station_id","time_left","total"}
    color: tuple = (0.4, 0.7, 1.0)
    # transient income accumulator (per tick, not saved)
    income_frame: dict = field(default_factory=lambda: {
        "credits": 0.0, "materials": 0.0, "energy": 0.0, "crew": 0.0})

    def command_used(self, entities: dict) -> int:
        from ..data.store import DataStore  # local import to avoid cycle
        used = 0
        for e in entities.values():
            if e.alive and e.owner == self.id and (e.is_ship or e.is_squadron):
                used += DataStore.get().command_cost(e)
        return used

    def to_dict(self, precise: bool = False) -> dict:
        return {
            "id": self.id, "faction": self.faction, "is_ai": self.is_ai,
            "ai_difficulty": self.ai_difficulty, "name": self.name,
            "credits": self.credits if precise else round(self.credits, 2),
            "materials": self.materials if precise else round(self.materials, 2),
            "energy": self.energy if precise else round(self.energy, 2),
            "crew": self.crew if precise else round(self.crew, 2),
            "command_capacity": self.command_capacity, "team": self.team,
            "researched": sorted(self.researched),
            "researching": {k: v for k, v in self.researching.items()},
            "color": list(self.color),
        }

    @staticmethod
    def from_dict(d: dict) -> "PlayerState":
        p = PlayerState(
            id=d["id"], faction=d["faction"], is_ai=d.get("is_ai", False),
            ai_difficulty=d.get("ai_difficulty", "normal"), name=d.get("name", "Player"),
            credits=d.get("credits", 0), materials=d.get("materials", 0),
            energy=d.get("energy", 0), crew=d.get("crew", 0),
            command_capacity=d.get("command_capacity", 0), team=d.get("team"),
        )
        p.researched = set(d.get("researched", []))
        p.researching = dict(d.get("researching", {}))
        p.color = tuple(d.get("color", (0.4, 0.7, 1.0)))
        return p


@dataclass(slots=True)
class MapInfo:
    name: str = "skirmish01"
    bounds: float = 24000.0
    nebulas: list = field(default_factory=list)     # {pos,radius}
    jump_points: list = field(default_factory=list) # {pos}
    star: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "bounds": self.bounds, "nebulas": self.nebulas,
                "jump_points": self.jump_points, "star": self.star}

    @staticmethod
    def from_dict(d: dict) -> "MapInfo":
        m = MapInfo(d.get("name", "skirmish01"), d.get("bounds", 24000.0))
        m.nebulas = d.get("nebulas", [])
        m.jump_points = d.get("jump_points", [])
        m.star = d.get("star", {})
        return m


@dataclass(slots=True)
class GameState:
    # identity
    seed: int = 12345
    game_type: str = "skirmish"            # skirmish|campaign
    mission_id: str | None = None
    time: float = 0.0
    tick: int = 0

    # world content
    entities: dict = field(default_factory=dict)        # id -> Entity
    projectiles: dict = field(default_factory=dict)     # id -> Projectile
    players: dict = field(default_factory=dict)         # id -> PlayerState
    fleets: dict = field(default_factory=dict)          # id -> Fleet
    grid: SpatialGrid = field(default_factory=SpatialGrid)
    map_info: MapInfo = field(default_factory=MapInfo)
    # Persistent XZ exploration: world-origin floor(x / cell), floor(z / cell).
    visibility_cell_size: float = 500.0
    explored_cells: dict = field(default_factory=dict)
    discovered_planets: dict = field(default_factory=dict)  # pid -> eid -> Entity snapshot
    _visibility_system: object | None = field(default=None, repr=False, compare=False)
    _sensor_queries: SensorQueries | None = field(default=None, repr=False, compare=False)

    # command input
    command_queue: list = field(default_factory=list)   # PlayerCommand list

    # ids
    next_entity_id: int = 1
    next_fleet_id: int = 1
    next_projectile_id: int = 1

    # outcome
    winner: int | None = None
    game_over: bool = False
    game_over_reason: str = ""                          # victory mode that ended the game
    stats: dict = field(default_factory=dict)           # per-player kill/loss tallies

    # event bus (sync, rebuilt on load)
    events: EventBus = field(default_factory=EventBus)

    # transient combat plumbing (rebuilt by GameManager; not saved)
    damage_queue: list = field(default_factory=list)
    dead_ids: list = field(default_factory=list)
    dmg_system: object | None = None

    # replay recorder + net session (transient; not saved)
    _recorder: object | None = field(default=None, repr=False, compare=False)
    _net_session: object | None = field(default=None, repr=False, compare=False)

    def queue_command(self, cmd: PlayerCommand) -> None:
        self.command_queue.append(cmd)
        # replay + net hooks (set by main.py / net session; None in plain games)
        recorder = self._recorder
        if recorder is not None:
            recorder.on_command(cmd, self.tick)
        session = self._net_session
        if session is not None:
            session.submit(cmd, self.tick)

    # transient (not saved): effects for renderer
    effects: list = field(default_factory=list)
    floating_texts: list = field(default_factory=list)
    # transient (not saved): live ConstructionSystem for renderer-side ghost
    # validation (same rules as the sim). Wired by GameManager.__init__.
    _construction_system: object | None = field(
        default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ helpers
    def rng(self) -> random.Random:
        return random.Random(self.seed + self.tick)

    def entity(self, eid: int) -> Entity | None:
        e = self.entities.get(eid)
        return e if (e and e.alive) else None

    def allied_player_ids(self, player_id: int) -> list[int]:
        """Missing/negative teams are solo; team zero is a valid alliance."""
        me = self.players.get(player_id)
        if me is None:
            return []
        return sorted(p.id for p in self.players.values()
                      if p.id == player_id or (me.team is not None and me.team >= 0
                                              and p.team == me.team))

    def _live_sensors(self):
        if self._sensor_queries is None:
            from ..systems.visibility import SensorQueries
            self._sensor_queries = SensorQueries(self)
        return self._sensor_queries

    def sensor_sources(self, player_id: int) -> list[tuple[Entity, float]]:
        """Sorted live allied observers; range memoization validates live inputs."""
        return self._live_sensors().sources(player_id)

    def is_position_visible(self, player_id: int, pos: Vec3) -> bool:
        return self._live_sensors().visible(player_id, pos)

    def can_see(self, player_id: int, entity_id: int) -> bool:
        e = self.entity(entity_id)
        if player_id not in self.players or e is None:
            return False
        allies = self.allied_player_ids(player_id)
        return ((not e.is_planet and e.owner in allies)
                or self._live_sensors().visible(player_id, e.pos, allies))

    def add_entity(self, e: Entity) -> Entity:
        self.entities[e.id] = e
        return e

    def visibility_cell(self, pos: Vec3) -> tuple[int, int] | None:
        half = self.map_info.bounds / 2.0
        if not (-half <= pos.x <= half and -half <= pos.z <= half):
            return None
        import math
        # Upper boundary belongs to the last interior cell, not a phantom row.
        x = min(pos.x, math.nextafter(half, -math.inf))
        z = min(pos.z, math.nextafter(half, -math.inf))
        return (math.floor(x / self.visibility_cell_size),
                math.floor(z / self.visibility_cell_size))

    def is_position_explored(self, player_id: int, pos: Vec3) -> bool:
        cell = self.visibility_cell(pos)
        return cell is not None and any(
            cell in self.explored_cells.get(pid, set())
            for pid in self.allied_player_ids(player_id))

    def known_entity(self, player_id: int, entity_id: int) -> Entity | None:
        if self.can_see(player_id, entity_id):
            return self.entity(entity_id)
        for pid in self.allied_player_ids(player_id):
            snapshot = self.discovered_planets.get(pid, {}).get(entity_id)
            if snapshot is not None:
                import copy
                return copy.deepcopy(snapshot)
        return None

    def spawn_effect(self, kind: str, pos: Vec3, **kw) -> None:
        if len(self.effects) > 1200:      # hard cap, pooled by renderer anyway
            del self.effects[:200]
        self.effects.append({"kind": kind, "pos": pos.to_dict(), "t": 0.0, **kw})

    def float_text(self, pos: Vec3, text: str, color=(1, 1, 1)) -> None:
        if len(self.floating_texts) > 60:
            del self.floating_texts[:20]
        self.floating_texts.append({"pos": pos.to_dict(), "text": text,
                                    "color": list(color), "t": 0.0})

    def players_in_team(self, team: int) -> list:
        return [p for p in self.players.values() if p.team == team]

    def enemy_players(self, player_id: int) -> list:
        me = self.players.get(player_id)
        if me is None:
            return []
        return [p for p in self.players.values()
                if p.id not in self.allied_player_ids(player_id)]

    def is_enemy(self, a_owner: int, b_owner: int) -> bool:
        if a_owner < 0 or b_owner < 0 or a_owner == b_owner:
            return False
        pa, pb = self.players.get(a_owner), self.players.get(b_owner)
        if not pa or not pb:
            return False
        return b_owner not in self.allied_player_ids(a_owner)

    def in_nebula(self, pos: Vec3) -> bool:
        for n in self.map_info.nebulas:
            dx, dy, dz = pos.x - n["pos"][0], pos.y - n["pos"][1], pos.z - n["pos"][2]
            if dx * dx + dy * dy + dz * dz <= n["radius"] ** 2:
                return True
        return False

    def nearest_jump_point(self, pos: Vec3) -> Vec3 | None:
        best, bd = None, 1e18
        for jp in self.map_info.jump_points:
            d = (pos.x - jp["pos"][0]) ** 2 + (pos.y - jp["pos"][1]) ** 2 + (pos.z - jp["pos"][2]) ** 2
            if d < bd:
                best, bd = jp, d
        return Vec3(*best["pos"]) if best else None

    # ------------------------------------------------------------------ save/load
    def to_dict(self, precise: bool = False) -> dict:
        """Serialize. precise=True (replay/lockstep) skips float rounding —
        regular saves round for size/readability, replays need bit-exact state."""
        return {
            "format": 3,
            "seed": self.seed, "game_type": self.game_type, "mission_id": self.mission_id,
            "time": self.time if precise else round(self.time, 3),
            "tick": self.tick,
            "next_entity_id": self.next_entity_id,
            "next_fleet_id": self.next_fleet_id,
            "next_projectile_id": self.next_projectile_id,
            "map_info": self.map_info.to_dict(),
            "visibility_cell_size": self.visibility_cell_size,
            "explored_cells": {pid: [list(cell) for cell in sorted(cells)]
                               for pid, cells in sorted(self.explored_cells.items())},
            "discovered_planets": {
                pid: {eid: self._entity_dict(e, precise) for eid, e in sorted(memory.items())}
                for pid, memory in sorted(self.discovered_planets.items())},
            "players": {pid: p.to_dict(precise) for pid, p in self.players.items()},
            "fleets": {fid: f.to_dict(precise) for fid, f in self.fleets.items()},
            "entities": {eid: self._entity_dict(e, precise)
                         for eid, e in self.entities.items()},
            "projectiles": [p.to_dict(precise) for p in self.projectiles.values()],
            "winner": self.winner, "game_over": self.game_over,
            "game_over_reason": self.game_over_reason,
            "stats": self.stats,
            "command_queue": [c.to_dict() for c in self.command_queue],
        }

    @staticmethod
    def _entity_dict(e: Entity, precise: bool = False) -> dict:
        d = {
            "id": e.id, "kind": e.kind, "owner": e.owner, "data_id": e.data_id,
            "sensor_range": e.sensor_range,
            "pos": e.pos.to_dict(precise), "vel": e.vel.to_dict(precise),
            "yaw": e.yaw if precise else round(e.yaw, 4),
            "radius": e.radius, "is_ship": e.is_ship, "is_station": e.is_station,
            "is_squadron": e.is_squadron, "is_construction": e.is_construction,
            "is_planet": e.is_planet,
            "hull": e.hull if precise else round(e.hull, 2),
            "max_hull": e.max_hull,
            "shields": ({q: v for q, v in e.shields.items()} if precise else
                        {q: round(v, 2) for q, v in e.shields.items()}),
            "max_shield_quad": e.max_shield_quad, "shield_regen": e.shield_regen,
            "systems": {k: ({"hp": v.hp, "max_hp": v.max_hp} if precise else
                            {"hp": round(v.hp, 2), "max_hp": v.max_hp})
                        for k, v in e.systems.items()},
            "alive": e.alive, "xp": e.xp if precise else round(e.xp, 2),
            "level": e.level,
            "order_type": e.order_type,
            "energy": e.energy if precise else round(e.energy, 2),
            "max_energy": e.max_energy, "spawn_time": e.spawn_time,
        }
        if e.order_target_pos:
            d["order_target_pos"] = e.order_target_pos.to_dict(precise)
        if e.order_target_id is not None:
            d["order_target_id"] = e.order_target_id
        if e.build_queue:
            if precise:
                d["build_queue"] = [dict(item) for item in e.build_queue]
            else:
                d["build_queue"] = [
                    {k: (round(v, 2) if isinstance(v, float) else v) for k, v in item.items()}
                    for item in e.build_queue]
        if e.colonized_by is not None:
            d["colonized_by"] = e.colonized_by
        if e.cargo_credits:
            d["cargo_credits"] = e.cargo_credits if precise else round(e.cargo_credits, 2)
        if e.convoy_dest is not None:
            d["convoy_dest"] = e.convoy_dest
        if e.fighter_count or e.max_fighters:
            d["fighter_count"] = e.fighter_count
            d["max_fighters"] = e.max_fighters
        if e.hangar_id is not None:
            d["hangar_id"] = e.hangar_id
        if e.launched_from is not None:
            d["launched_from"] = e.launched_from
        if e.fleet_id is not None:
            d["fleet_id"] = e.fleet_id
        if e.formation_slot:
            d["formation_slot"] = e.formation_slot
        if e.jump_charge:
            d["jump_charge"] = e.jump_charge if precise else round(e.jump_charge, 2)
        if e.jump_target is not None:
            d["jump_target"] = e.jump_target.to_dict(precise)
        if e.name_override:
            d["name_override"] = e.name_override
        if e.patrol_a is not None:
            d["patrol_a"] = e.patrol_a.to_dict()
        if e.patrol_b is not None:
            d["patrol_b"] = e.patrol_b.to_dict()
        if e.ability_cooldowns:
            d["ability_cooldowns"] = {k: (v if precise else round(v, 2))
                                      for k, v in e.ability_cooldowns.items()}
        if e.ability_active:
            d["ability_active"] = {k: (v if precise else round(v, 2))
                                   for k, v in e.ability_active.items()}
        if e.weapon_cooldowns:
            d["weapon_cooldowns"] = {k: round(v, 3) for k, v in e.weapon_cooldowns.items()}
        if e.current_target is not None:
            d["current_target"] = e.current_target
        return d

    @staticmethod
    def _entity_from_dict(d: dict) -> Entity:
        e = Entity(
            id=d["id"], kind=d["kind"], owner=d["owner"], data_id=d["data_id"],
            pos=Vec3.from_dict(d["pos"]), vel=Vec3.from_dict(d["vel"]),
            yaw=d.get("yaw", 0.0), radius=d.get("radius", 20.0),
            is_ship=d.get("is_ship", False), is_station=d.get("is_station", False),
            is_squadron=d.get("is_squadron", False),
            is_construction=d.get("is_construction", False),
            is_planet=d.get("is_planet", False),
            hull=d["hull"], max_hull=d.get("max_hull", d["hull"]),
            max_shield_quad=d.get("max_shield_quad", 0.0),
            shield_regen=d.get("shield_regen", 0.0),
            alive=d.get("alive", True), xp=d.get("xp", 0.0), level=d.get("level", 1),
            order_type=d.get("order_type", "idle"),
            energy=d.get("energy", 100.0), max_energy=d.get("max_energy", 100.0),
            spawn_time=d.get("spawn_time", 0.0),
        )
        e.shields = dict(d.get("shields", {}))
        e.systems = {k: SubsystemStub(v["hp"], v["max_hp"])
                     for k, v in d.get("systems", {}).items()}
        e.last_hit_time = -999.0
        e.weapon_cooldowns = {int(k): v for k, v in d.get("weapon_cooldowns", {}).items()}
        e.ability_cooldowns = dict(d.get("ability_cooldowns", {}))
        e.ability_active = dict(d.get("ability_active", {}))
        if "order_target_pos" in d:
            e.order_target_pos = Vec3.from_dict(d["order_target_pos"])
        e.order_target_id = d.get("order_target_id")
        e.build_queue = list(d.get("build_queue", []))
        e.colonized_by = d.get("colonized_by")
        e.cargo_credits = d.get("cargo_credits", 0.0)
        e.convoy_dest = d.get("convoy_dest")
        e.fighter_count = d.get("fighter_count", 0)
        e.max_fighters = d.get("max_fighters", 0)
        e.hangar_id = d.get("hangar_id")
        e.launched_from = d.get("launched_from")
        e.fleet_id = d.get("fleet_id")
        e.formation_slot = d.get("formation_slot", 0)
        e.jump_charge = d.get("jump_charge", 0.0)
        if "jump_target" in d:
            e.jump_target = Vec3.from_dict(d["jump_target"])
        e.name_override = d.get("name_override")
        if "patrol_a" in d:
            e.patrol_a = Vec3.from_dict(d["patrol_a"])
        if "patrol_b" in d:
            e.patrol_b = Vec3.from_dict(d["patrol_b"])
        e.current_target = d.get("current_target")
        if "sensor_range" in d:
            e.sensor_range = float(d["sensor_range"])
        elif e.is_ship or e.is_squadron or e.is_station:
            # Old saves predate the base sensor field; only known definitions
            # get ranges. Unknown/neutral entities never gain free detection.
            from ..data.store import DataStore
            ds = DataStore.get()
            definition = (ds.stations.get(e.data_id) if e.is_station
                          else ds.ships.get(e.data_id))
            e.sensor_range = definition.sensor_range if definition else 0.0
        return e

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        s = cls(
            seed=d.get("seed", 12345), game_type=d.get("game_type", "skirmish"),
            mission_id=d.get("mission_id"), time=d.get("time", 0.0),
            tick=d.get("tick", 0),
        )
        s.next_entity_id = d.get("next_entity_id", 1)
        s.next_fleet_id = d.get("next_fleet_id", 1)
        s.next_projectile_id = d.get("next_projectile_id", 1)
        s.map_info = MapInfo.from_dict(d.get("map_info", {}))
        s.visibility_cell_size = float(d.get("visibility_cell_size", 500.0))
        s.explored_cells = {int(pid): {tuple(cell) for cell in cells}
                            for pid, cells in d.get("explored_cells", {}).items()}
        s.discovered_planets = {
            int(pid): {int(eid): cls._entity_from_dict(ed) for eid, ed in memory.items()
                       if ed.get("is_planet", False)}
            for pid, memory in d.get("discovered_planets", {}).items()}
        s.players = {int(pid): PlayerState.from_dict(pd)
                     for pid, pd in d.get("players", {}).items()}
        s.fleets = {int(fid): Fleet.from_dict(fd)
                    for fid, fd in d.get("fleets", {}).items()}
        s.entities = {int(eid): cls._entity_from_dict(ed)
                      for eid, ed in d.get("entities", {}).items()}
        s.projectiles = {p["id"]: Projectile.from_dict(p)
                         for p in d.get("projectiles", [])}
        s.winner = d.get("winner")
        s.game_over = d.get("game_over", False)
        s.game_over_reason = d.get("game_over_reason", "")
        s.stats = d.get("stats", {})
        s.command_queue = [PlayerCommand.from_dict(c)
                           for c in d.get("command_queue", [])]
        return s


class SubsystemStub:
    """Lightweight subsystem holder used on load (kept dict-friendly)."""
    __slots__ = ("hp", "max_hp")

    def __init__(self, hp: float, max_hp: float) -> None:
        self.hp = hp
        self.max_hp = max_hp