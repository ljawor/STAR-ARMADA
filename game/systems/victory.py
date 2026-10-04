"""VictorySystem — skirmish + configurable victory conditions (spec §46).

Modes:
  elimination — skirmish/LAN: destroy every enemy ship, station and squadron;
                surviving allied players share victory, even fallen members.
  command     — legacy saves/campaign: command-station annihilation plus
                optional planet-majority, economic and timed rules.

MapInfo.victory_mode selects the contract. The legacy command path keeps
rules.victory.modes and its command-capacity fallback unchanged.
"""
from __future__ import annotations

from ..data.store import DataStore


class VictorySystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        self._timer = 0.0

    # ------------------------------------------------------------------ util
    def _planets_by_team(self) -> dict:
        owned: dict = {}
        for e in self.state.entities.values():
            if e.alive and e.is_planet and e.colonized_by is not None \
                    and e.colonized_by >= 0:
                p = self.state.players.get(e.colonized_by)
                if p:
                    owned[p.team] = owned.get(p.team, 0) + 1
        return owned

    def _alive_teams_with_command(self) -> dict:
        alive = {}
        for p in self.state.players.values():
            has_command = False
            for e in self.state.entities.values():
                if e.alive and e.is_station and e.owner == p.id:
                    sd = self.ds.stations.get(e.data_id)
                    if sd and sd.command_capacity >= 15:
                        has_command = True
                        break
            if has_command or p.command_capacity >= 15:
                alive[p.team] = alive.get(p.team, 0) + 1
        return alive

    def _team_scores(self) -> dict:
        """Timed-victory score: economy (planets+stations) + military (units)."""
        score: dict = {}
        for e in self.state.entities.values():
            if not e.alive:
                continue
            # colonized planets count for their colonizer even though the
            # planet entity's owner is neutral (-1) until conquered
            owner_id = e.owner
            if e.is_planet and e.colonized_by is not None and e.colonized_by >= 0:
                owner_id = e.colonized_by
            if owner_id < 0:
                continue
            p = self.state.players.get(owner_id)
            if p is None:
                continue
            w = 3 if (e.is_station or e.is_planet) else 1
            score[p.team] = score.get(p.team, 0) + w
        return score

    def _finish(self, winner_team: int | None, reason: str) -> None:
        st = self.state
        st.game_over = True
        st.winner = None
        if winner_team is not None:
            for p in st.players.values():
                if p.team == winner_team:
                    st.winner = p.id
                    break
        st.game_over_reason = reason
        st.events.publish("game_over", winner=st.winner, reason=reason)

    # ----------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        st = self.state
        if st.game_over:
            return
        self._timer += dt
        if self._timer < self.ds.rules.get("sim", {}).get("victory_check_interval", 1.0):
            return
        self._timer = 0.0
        if not st.players:
            return

        # Skirmish/LAN victory is exclusively coalition elimination. Capacity,
        # planets, resources and time cannot end a round with enemy units alive.
        if st.map_info.victory_mode == "elimination":
            living = {tuple(st.allied_player_ids(e.owner))
                      for e in st.entities.values()
                      if e.alive and e.owner >= 0 and e.owner in st.players
                      and (e.is_ship or e.is_station or e.is_squadron)
                      and not e.is_planet}
            if len(living) <= 1:
                coalition = next(iter(living)) if living else ()
                st.game_over = True
                st.winner = coalition[0] if coalition else None
                st.game_over_reason = "elimination"
                st.events.publish("game_over", winner=st.winner, reason="elimination")
            return

        vic = self.ds.rules.get("sim", {}).get("victory", {})
        cfg = dict(vic)
        modes = cfg.get("modes", ["annihilation"])

        # --- annihilation (classic; always enforced so games always end)
        alive = self._alive_teams_with_command()
        if len(alive) <= 1:
            winner = next(iter(alive)) if alive else None
            self._finish(winner, "annihilation")
            return

        # --- planet majority
        if "planet_majority" in modes:
            frac = float(cfg.get("planet_majority", {}).get("fraction", 0.6))
            min_col = int(cfg.get("planet_majority", {}).get("min_colonized", 4))
            owned = self._planets_by_team()
            total = sum(owned.values())
            if total >= min_col:
                for team, n in owned.items():
                    if n / total > frac:
                        self._finish(team, "planet_majority")
                        return

        # --- economic
        if "economic" in modes:
            ecfg = cfg.get("economic", {})
            need_cr = float(ecfg.get("credits", 15000))
            need_pl = int(ecfg.get("planets", 3))
            for p in st.players.values():
                if p.credits >= need_cr and \
                        self._planets_by_team().get(p.team, 0) >= need_pl:
                    self._finish(p.team, "economic")
                    return

        # --- timed
        if "timed" in modes:
            limit = float(cfg.get("timed", {}).get("time_limit", 1200))
            if st.time >= limit:
                score = self._team_scores()
                best = max(score.values()) if score else 0
                leaders = [t for t, s in score.items() if s == best]
                self._finish(leaders[0] if len(leaders) == 1 else None,
                             "timed")
                return