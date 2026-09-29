"""ConstructionSystem — station construction by constructor ships, ship building at
shipyards/fighter platforms/command stations, colonization of planets.

Construction costs are paid up front; time passes on the builder's queue; can be
cancelled (refund 50%). Constructor ships must be in range of a valid site
(mining near asteroids, energy relay near gas giants).
"""
from __future__ import annotations

import math

from ..core.vectors import Vec3
from ..data.store import DataStore
from . import stats
from .unit_factory import UnitFactory


class ConstructionSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        self.factory: UnitFactory | None = None  # injected by GameManager

    # ------------------------------------------------------------------ validation
    def can_pay(self, player_id: int, cost: dict) -> bool:
        p = self.state.players.get(player_id)
        if p is None:
            return False
        return (p.credits >= cost.get("credits", 0)
                and p.materials >= cost.get("materials", 0)
                and p.energy >= cost.get("energy", 0)
                and p.crew >= cost.get("crew", 0))

    def pay(self, player_id: int, cost: dict) -> None:
        p = self.state.players.get(player_id)
        p.credits -= cost.get("credits", 0)
        p.materials -= cost.get("materials", 0)
        p.energy -= cost.get("energy", 0)
        p.crew -= cost.get("crew", 0)
        st = self.state.stats.setdefault(str(player_id), {"kills": 0, "losses": 0})
        st["credits_spent"] = st.get("credits_spent", 0) + cost.get("credits", 0)

    def refund(self, player_id: int, cost: dict, fraction: float = 0.5) -> None:
        p = self.state.players.get(player_id)
        if p is None:
            return
        p.credits += cost.get("credits", 0) * fraction
        p.materials += cost.get("materials", 0) * fraction
        p.energy += cost.get("energy", 0) * fraction
        p.crew += cost.get("crew", 0) * fraction

    def command_available(self, player_id: int, cmd_cost: int) -> bool:
        p = self.state.players.get(player_id)
        if p is None:
            return False
        used = 0
        ds = self.ds
        for e in self.state.entities.values():
            if e.alive and e.owner == player_id and (e.is_ship or e.is_squadron):
                sd = ds.ships.get(e.data_id)
                if sd:
                    used += sd.command_cost
        # queued ships also reserve command points
        for e in self.state.entities.values():
            if e.alive and e.is_station and e.owner == player_id:
                for item in e.build_queue:
                    if item.get("kind") == "ship" and item.get("status") == "paid":
                        sd = ds.ships.get(item.get("item", ""))
                        if sd:
                            used += sd.command_cost
        return used + cmd_cost <= p.command_capacity

    # ------------------------------------------------------------------ station build
    def start_station(self, builder_id: int, station_id: str, pos: Vec3,
                      player_id: int) -> bool:
        st = self.state
        builder = st.entity(builder_id)
        if builder is None or not builder.is_construction:
            return False
        ok, reason = self.check_site(station_id, pos, builder)
        if not ok:
            st.float_text(builder.pos, f"Cannot build: {reason}", (1, 0.5, 0.4))
            return False
        sd = self.ds.resolve_station(station_id)
        cost = self.factory.station_build_cost(station_id)
        if not self.can_pay(player_id, cost):
            missing = self.missing_resources(player_id, cost)
            st.float_text(builder.pos, f"Insufficient resources: {missing}",
                          (1, 0.6, 0.4))
            return False
        self.pay(player_id, cost)
        build_time = sd.build_time / max(0.1, stats.effective_build_speed(st, player_id))
        builder.build_queue.append({
            "kind": "station", "item": station_id, "time_left": build_time,
            "total": build_time, "pos": pos.to_dict(), "status": "paid",
        })
        # move builder to site
        builder.order_type = "move"
        builder.order_target_pos = pos.copy()
        builder.order_target_id = None
        return True

    def missing_resources(self, player_id: int, cost: dict) -> str:
        """Human-readable list of what the player is short of."""
        p = self.state.players.get(player_id)
        if p is None:
            return "no player"
        parts = []
        if p.credits < cost.get("credits", 0):
            parts.append(f"credits ({p.credits:0.0f}/{cost.get('credits', 0):0.0f})")
        if p.materials < cost.get("materials", 0):
            parts.append(f"materials ({p.materials:0.0f}/{cost.get('materials', 0):0.0f})")
        if p.energy < cost.get("energy", 0):
            parts.append(f"energy ({p.energy:0.0f}/{cost.get('energy', 0):0.0f})")
        if p.crew < cost.get("crew", 0):
            parts.append(f"crew ({p.crew:0.0f}/{cost.get('crew', 0):0.0f})")
        return ", ".join(parts) if parts else "unknown"

    # ---------------------------------------------------------- site validation
    def check_site(self, station_id: str, pos, builder) -> tuple[bool, str]:
        """Single source of truth for placement validity.

        Returns (ok, reason). The placement ghost and start_station() both
        call this, so a green ghost always means the sim will accept the
        build. `pos` is any (x, y, z) tuple or Vec3.
        """
        st = self.state
        sd = self.ds.resolve_station(station_id)
        x, y, z = (pos.x, pos.y, pos.z) if hasattr(pos, "x") else (
            pos[0], pos[1], pos[2])
        # map bounds
        b = st.map_info.bounds
        if abs(x) > b or abs(z) > b:
            return False, "outside the map bounds"
        # spacing vs planets and other stations
        for e in st.entities.values():
            if not e.alive:
                continue
            if e.is_planet and e.data_id == "asteroid_field":
                continue        # building inside asteroid fields is the point
            if e.is_planet:
                if math.dist((x, y, z), (e.pos.x, e.pos.y, e.pos.z)) < \
                        e.radius + sd.radius + 100:
                    return False, f"too close to planet {e.name_override or e.data_id}"
            if e.is_station:
                if math.dist((x, y, z), (e.pos.x, e.pos.y, e.pos.z)) < \
                        (e.radius + sd.radius) * 1.6:
                    return False, f"too close to {e.data_id.replace('_', ' ')}"
        # requires_range: some stations must be near a specific body
        for req_kind, rng in (sd.requires_range or {}).items():
            ok = False
            for e in st.entities.values():
                if e.alive and e.data_id == req_kind and \
                        math.dist((x, y, z), (e.pos.x, e.pos.y, e.pos.z)) <= rng:
                    ok = True
                    break
            if not ok:
                return False, f"must be within {rng:0.0f}u of {req_kind.replace('_', ' ')}"
        # can the builder legally build this station type?
        unit = self.ds.resolve_ship(builder.data_id)
        if unit is not None and station_id not in unit.can_build_stations:
            return False, f"{unit.display_name} cannot build this station"
        return True, ""

    # ------------------------------------------------------------------ ship build
    def station_can_build_ship(self, station, ship_id: str) -> bool:
        sd = self.ds.stations.get(station.data_id)
        if sd is None or not sd.builds_ships:
            return False
        if ship_id in sd.builds_ships:
            return True
        if "*" not in sd.builds_ships:
            return False
        if sd.build_role == "warships":
            # shipyards build the fleet; engineering hulls come from the
            # command station (which cannot build warships)
            shd = self.ds.ships.get(ship_id)
            if shd is not None and shd.category == "construction":
                return False
        return True

    def start_ship(self, station_id: int, ship_id: str, player_id: int,
                   count: int = 1) -> int:
        """Queue `count` ships; returns number queued."""
        st = self.state
        station = st.entity(station_id)
        if station is None or not station.is_station or station.owner != player_id:
            return 0
        sd = self.ds.resolve_ship(ship_id)
        if not self.station_can_build_ship(station, ship_id):
            st.float_text(station.pos, "Cannot build here", (1, 0.6, 0.4))
            return 0
        queued = 0
        for _ in range(count):
            cost = self.factory.ship_build_cost(ship_id)
            if not self.can_pay(player_id, cost):
                if queued == 0:
                    st.float_text(station.pos, "Insufficient resources", (1, 0.6, 0.4))
                break
            if not self.command_available(player_id, sd.command_cost):
                if queued == 0:
                    st.float_text(station.pos, "Command capacity reached", (1, 0.6, 0.4))
                break
            self.pay(player_id, cost)
            build_time = sd.build_time / max(0.1, stats.effective_build_speed(st, player_id))
            station.build_queue.append({
                "kind": "ship", "item": ship_id, "time_left": build_time,
                "total": build_time, "status": "paid",
            })
            queued += 1
        return queued

    # ------------------------------------------------------------------ colonize
    def start_colonize(self, colonizer_id: int, planet_id: int, player_id: int) -> bool:
        st = self.state
        unit = st.entity(colonizer_id)
        planet = st.entity(planet_id)
        if unit is None or planet is None or not planet.is_planet:
            return False
        ud = self.ds.ships.get(unit.data_id)
        if ud is None or not ud.can_colonize:
            return False
        if planet.colonized_by is not None:
            return False
        if unit.pos.dist(planet.pos) > planet.radius + 600:
            # move there first; colonization completes on arrival via queue
            unit.order_type = "move"
            unit.order_target_id = planet_id
            unit.order_target_pos = None
            unit.build_queue.append({
                "kind": "colonize", "item": str(planet_id), "time_left": 0.0,
                "total": 0.0, "planet_id": planet_id, "status": "traveling",
            })
            return True
        # in range: start timer
        cost = {"credits": 500, "materials": 200, "energy": 100, "crew": 300}
        if not self.can_pay(player_id, cost):
            st.float_text(unit.pos, "Insufficient resources", (1, 0.6, 0.4))
            return False
        self.pay(player_id, cost)
        unit.build_queue.append({
            "kind": "colonize", "item": str(planet_id), "time_left": 15.0,
            "total": 15.0, "planet_id": planet_id, "status": "paid",
        })
        return True

    # ------------------------------------------------------------------ tick queues
    def update(self, dt: float) -> None:
        st = self.state
        done_events = []
        for e in st.entities.values():
            if not e.alive or not e.build_queue:
                continue
            item = e.build_queue[0]
            if item.get("status") == "traveling":
                planet = st.entity(int(item["planet_id"]))
                if planet is None or planet.colonized_by is not None:
                    e.build_queue.pop(0)
                    continue
                if e.pos.dist(planet.pos) <= planet.radius + 600:
                    cost = {"credits": 500, "materials": 200, "energy": 100, "crew": 300}
                    if self.can_pay(e.owner, cost):
                        self.pay(e.owner, cost)
                        item["time_left"] = 15.0
                        item["total"] = 15.0
                        item["status"] = "paid"
                    else:
                        st.float_text(e.pos, "Insufficient resources", (1, 0.6, 0.4))
                        e.build_queue.pop(0)
                continue
            speed = 1.0
            if item.get("kind") == "ship" and e.is_station:
                speed = stats.effective_build_speed(st, e.owner)
            elif e.is_construction:
                speed = stats.effective_build_speed(st, e.owner)
            item["time_left"] -= dt * speed
            if item["time_left"] <= 0:
                e.build_queue.pop(0)
                done_events.append((e, item))
        for e, item in done_events:
            self._complete(e, item)

    def _complete(self, builder, item: dict) -> None:
        st = self.state
        kind = item.get("kind")
        if kind == "station":
            pos = Vec3(*item["pos"])
            station = self.factory.spawn_station(item["item"], builder.owner, pos)
            st.float_text(pos, "Station complete", (0.6, 1, 0.6))
            st.events.publish("station_built", entity_id=station.id,
                              station=item["item"], owner=builder.owner)
        elif kind == "ship":
            ship_id = item["item"]
            sd = self.ds.resolve_ship(ship_id)
            offset = Vec3(
                st.rng().uniform(-1, 1) * (builder.radius + 80),
                st.rng().uniform(-0.2, 0.2) * 60,
                st.rng().uniform(-1, 1) * (builder.radius + 80),
            )
            spawn_pos = builder.pos + offset
            ship = self.factory.spawn_ship(ship_id, builder.owner, spawn_pos,
                                           yaw=st.rng().uniform(0, 6.28))
            st.float_text(ship.pos, sd.display_name, (0.7, 0.9, 1))
            st.events.publish("ship_built", entity_id=ship.id, ship=ship_id,
                              owner=builder.owner)
        elif kind == "colonize":
            planet = st.entity(int(item["planet_id"]))
            if planet is not None and planet.is_planet and planet.colonized_by is None:
                planet.colonized_by = builder.owner
                st.float_text(planet.pos, "Planet colonized", (0.6, 1, 0.6))
                st.events.publish("planet_colonized", planet_id=planet.id,
                                  owner=builder.owner)
            # colonizer is consumed
            if builder.alive:
                builder.alive = False
                st.dead_ids.append(builder.id)
                st.spawn_effect("explosion_small", builder.pos.copy())