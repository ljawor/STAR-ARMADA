"""MissionSystem — campaign objectives (spec §28/§29).

Missions declare objective lists; this system tracks progress and publishes
mission_complete / mission_failed. Objective types implemented in the slice:
  build_station, build_ship, destroy_all_forces, colonize_planet, survive_time.
"""
from __future__ import annotations

from ..data.store import DataStore


class MissionSystem:
    def __init__(self, state, mission_def: dict | None = None):
        self.state = state
        self.ds = DataStore.get()
        self.mission = mission_def
        self.objectives = []
        self.completed = False
        self.failed = False
        if mission_def:
            self.objectives = [dict(o, done=False) for o in mission_def.get("objectives", [])]
            state.events.subscribe("station_built", self._on_station_built)
            state.events.subscribe("ship_built", self._on_ship_built)
            state.events.subscribe("unit_destroyed", self._on_unit_destroyed)
            state.events.subscribe("planet_colonized", self._on_colonized)

    # ------------------------------------------------------------------ events
    def _player_team(self, player_id: int) -> int:
        p = self.state.players.get(player_id)
        return p.team if p else -99

    def _on_station_built(self, ev) -> None:
        for o in self.objectives:
            if o["type"] == "build_station" and not o["done"]:
                if o.get("station") == ev.data.get("station") and \
                        self._is_human(ev.data.get("owner")):
                    o["done"] = True

    def _on_ship_built(self, ev) -> None:
        for o in self.objectives:
            if o["type"] == "build_ship" and not o["done"]:
                if o.get("ship") == ev.data.get("ship") and \
                        self._is_human(ev.data.get("owner")):
                    o["count_done"] = o.get("count_done", 0) + 1
                    if o["count_done"] >= o.get("count", 1):
                        o["done"] = True

    def _on_unit_destroyed(self, ev) -> None:
        pass  # destroy_all_forces is checked by scan below

    def _on_colonized(self, ev) -> None:
        for o in self.objectives:
            if o["type"] == "colonize_planet" and not o["done"]:
                if o.get("planet") in (None, ev.data.get("planet_id")) and \
                        self._is_human(ev.data.get("owner")):
                    o["done"] = True

    def _is_human(self, owner) -> bool:
        p = self.state.players.get(owner)
        return bool(p and not p.is_ai)

    # ------------------------------------------------------------------ check
    def update(self, dt: float) -> None:
        if self.mission is None or self.completed or self.failed:
            return
        st = self.state
        for o in self.objectives:
            if o["type"] == "survive_time" and not o["done"]:
                if st.time >= o.get("time", 300):
                    o["done"] = True
            if o["type"] == "destroy_all_forces" and not o["done"]:
                team = o.get("team")
                any_left = any(
                    e.alive and e.owner >= 0 and self._team_of(e.owner) == team
                    and (e.is_ship or e.is_squadron or e.is_station)
                    for e in st.entities.values())
                if not any_left:
                    o["done"] = True
        if all(o["done"] for o in self.objectives):
            self.completed = True
            st.events.publish("mission_complete")
        # failure: player loses all stations
        human = [p for p in st.players.values() if not p.is_ai]
        for p in human:
            has_any = any(e.alive and e.owner == p.id and (e.is_station or e.is_ship)
                          for e in st.entities.values())
            if not has_any and st.time > 5.0:
                self.failed = True
                st.events.publish("mission_failed")
                break

    def _team_of(self, owner: int) -> int:
        p = self.state.players.get(owner)
        return p.team if p else -99

    def progress_text(self) -> list:
        return [("[x] " if o["done"] else "[ ] ") + o.get("text", o["type"])
                for o in self.objectives]