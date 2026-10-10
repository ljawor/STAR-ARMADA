"""MissionSystem — campaign objectives (spec §28/§29).

Missions declare objective lists; this system tracks progress and publishes
mission_complete / mission_failed. Objective types implemented in the slice:
  build_station, build_ship, destroy_all_forces, colonize_planet, survive_time.
"""
from __future__ import annotations

from copy import deepcopy
from ..data.store import DataStore


class MissionSystem:
    def __init__(self, state, mission_def: dict | None = None):
        self.state = state
        self.ds = DataStore.get()
        saved = state.mission_state
        if mission_def is None and saved is not None:
            mission_def = saved.get("definition")
        self.mission = deepcopy(mission_def)
        self.objectives = []
        self.completed = False
        self.failed = False
        self._escorted_id = None       # the player convoy we are escorting
        state._mission_system = self
        if mission_def is not None:
            self.objectives = [dict(o, done=False) for o in mission_def.get("objectives", [])]
            if saved is not None and saved.get("definition") == mission_def:
                self.objectives = deepcopy(saved.get("objectives", self.objectives))
                self.completed = bool(saved.get("completed", False))
                self.failed = bool(saved.get("failed", False))
                self._escorted_id = saved.get("escorted_id")
            state.events.subscribe("station_built", self._on_station_built)
            state.events.subscribe("ship_built", self._on_ship_built)
            state.events.subscribe("unit_destroyed", self._on_unit_destroyed)
            state.events.subscribe("planet_colonized", self._on_colonized)
            if not self.completed and not self.failed and any(
                    o["type"] == "escort_convoy" and not o["done"] for o in self.objectives):
                state.events.subscribe("convoy_arrived", self._on_convoy_arrived)
                state.events.subscribe("convoy_raided", self._on_convoy_raided)
        self._escort_hooked = any(o["type"] == "escort_convoy" for o in self.objectives)
        # The restore snapshot is consumed; serialization now reads this system.
        state.mission_state = None

    def to_dict(self) -> dict | None:
        """Persist mission identity, exact progress and terminal outcome."""
        if self.mission is None:
            return None
        return deepcopy(dict(definition=self.mission, objectives=self.objectives,
                             completed=self.completed, failed=self.failed,
                             escorted_id=self._escorted_id))

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
                    e.operational and e.owner >= 0 and self._team_of(e.owner) == team
                    and (e.is_ship or e.is_squadron or e.is_station)
                    for e in st.entities.values())
                if not any_left:
                    o["done"] = True
            if o["type"] == "hold_point" and not o["done"]:
                self._update_hold_point(o, dt)
            if o["type"] == "escort_convoy" and not o["done"]:
                self._update_escort(o)
        # Failure takes precedence over a deadline reached on the loss tick.
        if self.failed:
            return
        human = [p for p in st.players.values() if not p.is_ai]
        for p in human:
            has_any = any(e.operational and e.owner == p.id
                          and (e.is_station or e.is_ship or e.is_squadron)
                          for e in st.entities.values())
            if not has_any and st.time > 5.0:
                self.failed = True
                st.events.publish("mission_failed")
                return
        if all(o["done"] for o in self.objectives):
            self.completed = True
            st.events.publish("mission_complete")

    def _team_of(self, owner: int) -> int:
        p = self.state.players.get(owner)
        return p.team if p else -99

    # ----------------------------------------------------- new objective types
    def _update_hold_point(self, o: dict, dt: float) -> None:
        """Player (human team) must keep >= count entities inside radius of
        a point for `duration` seconds (spec §28 hold-point)."""
        st = self.state
        pos = o.get("pos")
        if not pos or len(pos) < 2:
            o["done"] = True     # malformed objective auto-completes
            return
        px, pz = float(pos[0]), float(pos[2]) if len(pos) > 2 else float(pos[1])
        radius = float(o.get("radius", 800))
        need = int(o.get("count", 1))
        human_teams = {p.team for p in st.players.values() if not p.is_ai}
        inside = sum(
            1 for e in st.entities.values()
            if e.operational and e.owner >= 0
            and self._team_of(e.owner) in human_teams
            and (e.is_ship or e.is_squadron or e.is_station)
            and (e.pos.x - px) ** 2 + (e.pos.z - pz) ** 2 <= radius ** 2)
        if inside >= need:
            o["held"] = o.get("held", 0.0) + dt
            if o["held"] >= float(o.get("duration", 30.0)):
                o["done"] = True
        else:
            o["held"] = max(0.0, o.get("held", 0.0) - dt * 2.0)  # drains fast

    def _update_escort(self, o: dict) -> None:
        """Player's trade convoy must arrive alive (spec §26+§28 escort).
        done when one of the player's convoys publishes convoy_arrived.
        fails the mission if it is destroyed by an enemy."""
        st = self.state
        # Compatibility for objectives attached dynamically by callers.
        if not self._escort_hooked:
            st.events.subscribe("convoy_arrived", self._on_convoy_arrived)
            st.events.subscribe("convoy_raided", self._on_convoy_raided)
            self._escort_hooked = True
        # mission-failure path: the escorted convoy died to an enemy
        if o.get("failed"):
            self.failed = True
            st.events.publish("mission_failed")

    def _on_convoy_arrived(self, ev) -> None:
        """Complete the escort objective when the PLAYER's convoy lands.

        Must key on `convoy_owner`, not `owner`. With the default
        reward_owner="destination" the payload's `owner` is whoever was PAID —
        the destination's owner — so reading it here credited the player for
        an ENEMY convoy docking at their station (verified: objective flipped
        done on an AI-owned convoy at t=644s) while never completing for the
        player's own delivery to an enemy market.
        """
        for o in self.objectives:
            if o["type"] == "escort_convoy" and not o["done"] and \
                    self._is_human(ev.data.get("convoy_owner")):
                o["done"] = True
                self._escorted_id = ev.data.get("entity_id")

    def _on_convoy_raided(self, ev) -> None:
        """Fail the escort objective only for the PLAYER's own convoy.

        A raided enemy or AI convoy must not fail the player's mission.
        """
        for o in self.objectives:
            if o["type"] == "escort_convoy" and not o["done"]:
                if self._is_human(ev.data.get("convoy_owner")) or \
                        self._escorted_id == ev.data.get("entity_id"):
                    o["failed"] = True

    def progress_text(self) -> list:
        out: list = []
        for o in self.objectives:
            mark = "[x] " if o["done"] else "[ ] "
            txt = str(o.get("text", o["type"]))
            if o["type"] == "hold_point" and not o["done"]:
                need = float(o.get("duration", 30.0))
                held = float(o.get("held", 0.0))
                txt += f" ({held:0.0f}/{need:0.0f}s)"
            out.append(mark + txt)
        return out