"""VictorySystem — skirmish: destroy all enemy command stations (spec §46)."""
from __future__ import annotations

from ..data.store import DataStore


class VictorySystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        self._timer = 0.0

    def update(self, dt: float) -> None:
        st = self.state
        if st.game_over:
            return
        self._timer += dt
        if self._timer < self.ds.rules.get("sim", {}).get("victory_check_interval", 1.0):
            return
        self._timer = 0.0
        alive_teams = {}
        for p in st.players.values():
            has_command = False
            for e in st.entities.values():
                if e.alive and e.is_station and e.owner == p.id:
                    sd = self.ds.stations.get(e.data_id)
                    if sd and sd.command_capacity >= 15:  # command-station class
                        has_command = True
                        break
            if has_command or p.command_capacity >= 15:
                alive_teams[p.team] = alive_teams.get(p.team, 0) + 1
        if not st.players:
            return
        if len(alive_teams) <= 1:
            st.game_over = True
            if alive_teams:
                # winner = any player on the surviving team
                for p in st.players.values():
                    if p.team in alive_teams:
                        st.winner = p.id
                        break
            else:
                st.winner = None
            st.events.publish("game_over", winner=st.winner)