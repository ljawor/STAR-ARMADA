"""SquadronSystem — fighter/bomber behavior, carrier docking and reinforcement.

Squadrons are single entities whose `fighter_count` scales combat power. Behaviors
(spec §21): interceptors chase enemy fighters, bombers strike capitals and avoid
enemy fighters, damaged squadrons return to their hangar to repair + reinforce.
"""
from __future__ import annotations

import math

from ..core.vectors import Vec3
from ..data.store import DataStore
from . import stats
from .weapons import clear_unseen_targets


class SquadronSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        self._tactical_timer = 0.0

    def update(self, dt: float) -> None:
        st = self.state
        self._tactical_timer += dt
        do_tactical = self._tactical_timer >= 0.2
        if do_tactical:
            self._tactical_timer = 0.0
        for e in st.entities.values():
            if not e.operational or not e.is_squadron:
                continue
            clear_unseen_targets(st, e)
            if do_tactical:
                self._squadron_behavior(e)
            self._reinforce_and_repair(e, dt)

    # ------------------------------------------------------------------ behaviors
    def _squadron_behavior(self, e) -> None:
        st = self.state
        # manual orders win: attack/attack_move/move by player are respected
        if e.order_type in ("move", "attack_move", "explore"):
            return
        if e.order_type == "attack" and st.entity(e.order_target_id or 0) is not None:
            return
        if e.owner < 0:
            return
        sd = self.ds.resolve_ship(e.data_id)
        is_bomber = any(
            (wref["weapon"] if isinstance(wref, dict) else wref) == "proton_torpedo"
            for wref in sd.weapons)
        # damaged? return to hangar
        if e.hull_fraction() < self.ds.rules.get("squadrons", {}).get(
                "return_hull_fraction", 0.45):
            hangar = st.entity(e.hangar_id) if e.hangar_id else None
            if hangar is not None and hangar.operational and hangar.owner == e.owner:
                if e.order_type != "follow" or e.order_target_id != hangar.id:
                    e.order_type = "follow"
                    e.order_target_id = hangar.id
                return
        # find targets
        fighter_target = None
        capital_target = None
        scan = sd.sensor_range
        for tid in st.grid.query_sphere(st.entities, e.pos, scan):
            t = st.entity(tid)
            if (t is None or not st.is_enemy(e.owner, t.owner) or t.is_planet
                    or not st.can_see(e.owner, tid)):
                continue
            if t.is_squadron and fighter_target is None:
                fighter_target = t
            elif (t.is_ship or t.is_station) and capital_target is None:
                # prefer closest
                if capital_target is None or e.pos.dist_sq(t.pos) < e.pos.dist_sq(capital_target.pos):
                    capital_target = t
        if is_bomber:
            # bombers avoid enemy fighters: if one is close, evade toward hangar
            if fighter_target is not None and e.pos.dist(fighter_target.pos) < 600:
                hangar = st.entity(e.hangar_id) if e.hangar_id else None
                if hangar is not None and hangar.operational and hangar.owner == e.owner:
                    e.order_type = "follow"
                    e.order_target_id = hangar.id
                    return
            if capital_target is not None:
                e.order_type = "attack"
                e.order_target_id = capital_target.id
                e.current_target = capital_target.id
        else:
            if fighter_target is not None:
                e.order_type = "attack"
                e.order_target_id = fighter_target.id
                e.current_target = fighter_target.id
            elif capital_target is not None:
                e.order_type = "attack"
                e.order_target_id = capital_target.id
                e.current_target = capital_target.id

    # ------------------------------------------------------------------ hangars
    def _reinforce_and_repair(self, e, dt: float) -> None:
        st = self.state
        # Validate assignments even for healthy squadrons after carrier loss/capture.
        hangar = st.entity(e.hangar_id) if e.hangar_id else None
        if hangar is None or not hangar.operational or hangar.owner != e.owner:
            hangar = self._find_hangar(e)
            e.hangar_id = hangar.id if hangar is not None else None
        if hangar is None or (e.fighter_count >= e.max_fighters and e.hull >= e.max_hull):
            return
        radius = self.ds.rules.get("squadrons", {}).get("landing_radius", 450)
        if e.pos.dist(hangar.pos) > radius + hangar.radius:
            return
        # repair + reinforce; hangar system gates rate
        hangar_data = self.ds.stations.get(hangar.data_id) if hangar.is_station else \
            self.ds.ships.get(hangar.data_id)
        hangar_ok = hangar.subsystem_fraction("hangar") if "hangar" in hangar.systems else 0.5
        if hangar_ok <= 0.05:
            return
        rate = self.ds.rules.get("squadrons", {}).get("reinforce_rate_per_fighter", 6.0)
        if hangar.is_station and hangar_data:
            rate /= max(0.2, min(1.0, hangar_ok))
        rate /= max(0.2, stats.effective_reinforce_mult(st, e.owner))
        staffing = stats.staffing_fraction(hangar)
        # repair
        if e.hull < e.max_hull:
            e.hull = min(e.max_hull, e.hull + e.max_hull * 0.05 * dt * staffing)
        # reinforce
        if e.fighter_count < e.max_fighters:
            e.fighter_count = min(e.max_fighters, e.fighter_count + dt * staffing / max(0.5, rate))
            if e.fighter_count >= e.max_fighters:
                e.fighter_count = e.max_fighters
                # undock: drift away
                away = e.pos - hangar.pos
                if away.length_sq() < 1.0:
                    away = Vec3(1, 0, 0)
                e.pos.add_scaled(away.normalized(), hangar.radius + 120)
                if e.order_type != 'explore':
                    e.order_type = "idle"
                    e.order_target_id = None

    def _find_hangar(self, e):
        st = self.state
        best, best_d = None, 1e18
        for h in st.entities.values():
            if not h.operational or h.owner != e.owner or h.is_planet:
                continue
            if h.is_station:
                hd = self.ds.stations.get(h.data_id)
                if not hd or (hd.fighter_capacity <= 0 and not hd.builds_ships):
                    continue
            elif h.is_ship:
                hd = self.ds.ships.get(h.data_id)
                if not hd or hd.hangar_capacity <= 0:
                    continue
            else:
                continue
            d = e.pos.dist_sq(h.pos)
            if d < best_d:
                best, best_d = h, d
        return best

    # ------------------------------------------------------------------ launching
    def launched_squadron_strength(self, e) -> float:
        """Damage multiplier from remaining fighters (spec §11: losses weaken output)."""
        if e.max_fighters <= 0:
            return 1.0
        return 0.35 + 0.65 * (e.fighter_count / e.max_fighters)