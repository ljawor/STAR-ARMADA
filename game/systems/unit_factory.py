"""UnitFactory — spawns ships, stations, squadrons, planets from data definitions."""
from __future__ import annotations

from ..core.entity import Entity, SubsystemState, QUADRANTS
from ..core.vectors import Vec3
from ..data.store import DataStore


class UnitFactory:
    def __init__(self, state):
        self.state = state

    # ------------------------------------------------------------------ ships
    def spawn_ship(self, ship_id: str, owner: int, pos: Vec3, yaw: float = 0.0,
                   name: str | None = None) -> Entity:
        ds = DataStore.get()
        sd = ds.resolve_ship(ship_id)
        st = self.state
        e = Entity(
            id=st.next_entity_id, kind="squadron" if sd.is_squadron else "ship",
            owner=owner, data_id=ship_id, pos=pos.copy(), yaw=yaw,
            radius=sd.radius,
            is_ship=not sd.is_squadron, is_squadron=sd.is_squadron,
            is_construction=sd.is_construction,
        )
        st.next_entity_id += 1
        tech_hull = 1.0
        p = st.players.get(owner)
        if p:
            for tid in p.researched:
                t = ds.techs.get(tid)
                if t and isinstance(t.effects.get("hull_mult"), (int, float)):
                    tech_hull *= t.effects["hull_mult"]
        e.max_hull = sd.hull * tech_hull
        e.hull = e.max_hull
        e.max_shield_quad = sd.shield_quad
        for q in QUADRANTS:
            e.shields[q] = sd.shield_quad
        e.shield_regen = sd.shield_regen
        e.systems = {}
        for sname, hp in sd.systems.items():
            if hp and hp > 0:
                e.systems[sname] = SubsystemState(hp=float(hp), max_hp=float(hp))
        e.energy = 100.0
        e.max_energy = 100.0
        e.sensor_range = sd.sensor_range
        if sd.is_squadron:
            e.fighter_count = sd.squadron_size
            e.max_fighters = sd.squadron_size
        if name:
            e.name_override = name
        st.add_entity(e)
        st.grid.cells.setdefault(
            (int(pos.x // st.grid.cell), int(pos.y // st.grid.cell),
             int(pos.z // st.grid.cell)), set()).add(e.id)
        return e

    # ------------------------------------------------------------------ stations
    def spawn_station(self, station_id: str, owner: int, pos: Vec3,
                      construction_complete: bool = True) -> Entity:
        ds = DataStore.get()
        sd = ds.resolve_station(station_id)
        st = self.state
        e = Entity(
            id=st.next_entity_id, kind="station", owner=owner, data_id=station_id,
            pos=pos.copy(), radius=sd.radius, is_station=True,
        )
        st.next_entity_id += 1
        e.max_hull = sd.hull
        e.hull = sd.hull if construction_complete else sd.hull * 0.05
        e.max_shield_quad = sd.shield_quad
        for q in QUADRANTS:
            e.shields[q] = sd.shield_quad if construction_complete else 0.0
        e.shield_regen = sd.shield_regen
        e.systems = {}
        for sname, hp in sd.systems.items():
            if hp and hp > 0:
                e.systems[sname] = SubsystemState(hp=float(hp), max_hp=float(hp))
        e.energy = 100.0
        e.max_energy = 100.0
        e.sensor_range = sd.sensor_range
        st.add_entity(e)
        st.grid.cells.setdefault(
            (int(pos.x // st.grid.cell), int(pos.y // st.grid.cell),
             int(pos.z // st.grid.cell)), set()).add(e.id)
        return e

    # ------------------------------------------------------------------ planets
    def spawn_planet(self, planet_def: dict) -> Entity:
        st = self.state
        e = Entity(
            id=st.next_entity_id, kind="planet", owner=-1,
            data_id=planet_def.get("type", "barren"),
            pos=Vec3(*planet_def["pos"]), radius=float(planet_def.get("radius", 600)),
            is_planet=True,
        )
        st.next_entity_id += 1
        e.max_hull = 1e9
        e.hull = 1e9
        e.name_override = planet_def.get("name", planet_def["id"])
        st.add_entity(e)
        return e

    # ------------------------------------------------------------------ helpers
    def ship_build_cost(self, ship_id: str) -> dict:
        sd = DataStore.get().resolve_ship(ship_id)
        return {"credits": sd.cost_credits, "materials": sd.cost_materials,
                "energy": sd.cost_energy, "crew": sd.crew_cost,
                "command": sd.command_cost}

    def station_build_cost(self, station_id: str) -> dict:
        sd = DataStore.get().resolve_station(station_id)
        return {"credits": sd.cost_credits, "materials": sd.cost_materials,
                "energy": sd.cost_energy, "crew": sd.crew_cost}