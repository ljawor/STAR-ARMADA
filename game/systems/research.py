"""ResearchSystem — per-player research queues, prerequisites, completion effects."""
from __future__ import annotations

from ..data.store import DataStore


class ResearchSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    def available_techs(self, player_id: int) -> list:
        p = self.state.players.get(player_id)
        if p is None:
            return []
        out = []
        for tid, t in self.ds.techs.items():
            if t.faction != p.faction:
                continue
            if tid in p.researched or tid in p.researching:
                continue
            if all(r in p.researched for r in t.requires):
                out.append(tid)
        return out

    def can_research(self, player_id: int, tech_id: str) -> bool:
        p = self.state.players.get(player_id)
        t = self.ds.techs.get(tech_id)
        if p is None or t is None:
            return False
        if tech_id in p.researched or tech_id in p.researching:
            return False
        if t.faction != p.faction:
            return False
        return all(r in p.researched for r in t.requires)

    def has_research_station(self, player_id: int, station_id: int) -> bool:
        st = self.state
        station = st.entity(station_id)
        if station is None or not station.operational or station.owner != player_id or not station.is_station:
            return False
        sd = self.ds.stations.get(station.data_id)
        return bool(sd and sd.research)

    def start_research(self, player_id: int, station_id: int, tech_id: str) -> bool:
        st = self.state
        p = st.players.get(player_id)
        if p is None:
            return False
        if not self.has_research_station(player_id, station_id):
            st.float_text(st.entities[station_id].pos, "Needs research station",
                          (1, 0.6, 0.4)) if station_id in st.entities else None
            return False
        if not self.can_research(player_id, tech_id):
            return False
        t = self.ds.resolve_tech(tech_id)
        if (p.credits < t.cost_credits or p.materials < t.cost_materials
                or p.energy < t.cost_energy):
            return False
        cost = {"credits": t.cost_credits, "materials": t.cost_materials,
                "energy": t.cost_energy}
        p.credits -= cost["credits"]
        p.materials -= cost["materials"]
        p.energy -= cost["energy"]
        p.researching[tech_id] = {
            "station_id": station_id,
            "time_left": t.research_time,
            "total": t.research_time,
        }
        return True

    def update(self, dt: float) -> None:
        st = self.state
        finished = []
        for p in st.players.values():
            for tid in list(p.researching.keys()):
                info = p.researching[tid]
                # station must still exist
                station = st.entity(int(info["station_id"]))
                if station is None or station.owner != p.id or not station.operational:
                    del p.researching[tid]
                    continue
                from . import stats
                info["time_left"] -= dt * stats.effective_research_speed(st, station)
                if info["time_left"] <= 0:
                    del p.researching[tid]
                    p.researched.add(tid)
                    finished.append((p, tid))
        for p, tid in finished:
            t = self.ds.techs.get(tid)
            st.float_text((station.pos if False else _player_anchor(st, p.id)),
                          f"Research complete: {t.display_name}", (0.6, 1, 0.7))
            st.events.publish("research_complete", player=p.id, tech=tid)


def _player_anchor(state, player_id: int):
    """Anchor for floating text: first station of the player."""
    for e in state.entities.values():
        if e.alive and e.is_station and e.owner == player_id:
            return e.pos.copy()
    from ..core.vectors import Vec3
    return Vec3(0, 0, 0)