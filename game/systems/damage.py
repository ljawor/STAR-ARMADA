"""DamageSystem — the single writer of hull/shield/subsystem state.

Pipeline per damage event:
  1. shields absorb (quadrant facing determines which quadrant absorbs)
  2. overflow hits hull; subsystem chips proportional to damage × system_mult
  3. hull thresholds degrade subsystems (spec §14) and emit events
  4. on death: crew reclaim, XP award, kill/loss tallies, events
Also applies queued beam/EMP damage and shield regeneration, and handles
veteran XP progression.
"""
from __future__ import annotations

import math

from ..core.entity import QUADRANTS, SubsystemState
from ..core.vectors import Vec3
from ..data.store import DataStore
from . import stats


class DamageSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    # ------------------------------------------------------------------ main
    def update(self, dt: float) -> None:
        st = self.state
        # 1. resolve queued damage (beams, EMP, projectile impacts already queued)
        queue, st.damage_queue = st.damage_queue, []
        for hit in queue:
            self._apply_damage(
                target=hit["target"],
                raw_damage=hit["damage"],
                shield_mult=hit["shield_mult"],
                armor_mult=hit["armor_mult"],
                system_mult=hit["system_mult"],
                attacker=hit.get("attacker_entity"),
                attacker_id=hit.get("attacker_id", -2),
                weapon=hit.get("weapon"),
                impact_pos=hit.get("impact_pos"),
            )

        # 2. shield regeneration
        for e in st.entities.values():
            if not e.alive or e.is_planet:
                continue
            if e.max_shield_quad <= 0:
                continue
            # regen pauses shortly after being hit
            if st.time - e.last_hit_time < 4.0:
                continue
            regen = stats.effective_shield_regen(st, e) * dt
            maxq = stats.effective_max_shield_quad(st, e)
            for q in QUADRANTS:
                if e.shields[q] < maxq:
                    e.shields[q] = min(maxq, e.shields[q] + regen)

        # 3. cleanup dead
        if st.dead_ids:
            for eid in st.dead_ids:
                st.entities.pop(eid, None)
            st.dead_ids.clear()

    # ------------------------------------------------------------------ damage
    def _apply_damage(self, target, raw_damage: float, shield_mult: float,
                      armor_mult: float, system_mult: float,
                      attacker=None, attacker_id: int = -2, weapon=None,
                      impact_pos=None) -> None:
        st = self.state
        if target is None or not target.alive or target.is_planet:
            return

        # quadrant facing: which shield arc was hit?
        quad = "front"
        if impact_pos is not None:
            quad = self._quadrant_for(target, impact_pos)
        else:
            quad = "front"

        remaining = raw_damage

        # --- shields first
        if target.max_shield_quad > 0 and target.shields.get(quad, 0) > 0:
            absorbed = min(target.shields[quad], remaining * shield_mult)
            target.shields[quad] -= absorbed
            remaining -= absorbed / max(shield_mult, 0.01)
            if target.shields[quad] <= 0.0:
                target.shields[quad] = 0.0
                st.spawn_effect("shield_down", target.pos.copy())

        target.last_hit_time = st.time

        # --- armor/hull
        if remaining > 0:
            hull_damage = remaining * armor_mult
            target.hull -= hull_damage
            # subsystem chip
            self._chip_systems(target, hull_damage, system_mult)
            # hull threshold effects
            self._hull_threshold_effects(target)
            if impact_pos is not None:
                st.spawn_effect("hull_hit", impact_pos.copy())

        # --- attacker XP
        if attacker is not None and attacker.alive and attacker.owner >= 0:
            attacker.xp += raw_damage * self.ds.rules.get("experience", {}).get(
                "xp_per_damage", 0.01)
            self._update_level(attacker)

        # --- death
        if target.hull <= 0:
            self._kill(target, attacker, attacker_id)

    def _quadrant_for(self, target, impact_pos) -> str:
        """Which shield quadrant does an impact at `impact_pos` hit?"""
        dx = impact_pos.x - target.pos.x
        dz = impact_pos.z - target.pos.z
        if abs(dx) > abs(dz):
            # left/right relative to facing
            fx = math.sin(target.yaw)
            fz = math.cos(target.yaw)
            side = dx * fz - dz * fx     # cross product Y component
            return "left" if side > 0 else "right"
        return "front" if dz > 0 else "rear"

    def _chip_systems(self, target, hull_damage: float, system_mult: float) -> None:
        st = self.state
        chip = hull_damage * 0.06 * max(0.2, system_mult)
        for sname, sub in target.systems.items():
            if sub.hp > 0:
                sub.hp = max(0.0, sub.hp - chip)
        # hull thresholds progressively degrade subsystems (spec §14)
        f = target.hull_fraction()
        if f < 0.7:
            self._degrade_below(target, "sensors", 0.7)
        if f < 0.5:
            self._degrade_below(target, "engines", 0.6)
        if f < 0.3:
            self._degrade_below(target, "weapons", 0.5)
            self._degrade_below(target, "shield_gen", 0.5)
        if f < 0.1:
            for sname in ("engines", "weapons", "sensors", "shield_gen", "hangar"):
                self._degrade_below(target, sname, 0.25)

    @staticmethod
    def _degrade_below(e, sname: str, fraction: float) -> None:
        sub = e.systems.get(sname)
        if sub and sub.max_hp > 0 and sub.hp > sub.max_hp * fraction:
            sub.hp = sub.max_hp * fraction

    def _hull_threshold_effects(self, target) -> None:
        st = self.state
        ds = self.ds
        f = target.hull_fraction()
        state = target.damage_state()
        if state != getattr(target, "_last_damage_state", -1):
            target._last_damage_state = state
            if state >= 3:
                st.spawn_effect("fire", target.pos.copy(), size=target.radius)
                if (target.is_ship or target.is_station) and target.owner >= 0:
                    st.float_text(target.pos, "SYSTEMS FAILING", (1, 0.6, 0.3))
                    st.events.publish("unit_critical", entity_id=target.id,
                                      owner=target.owner)

    def _kill(self, target, attacker, attacker_id: int) -> None:
        st = self.state
        ds = self.ds
        target.alive = False
        target.hull = 0.0
        st.dead_ids.append(target.id)
        st.spawn_effect("explosion", target.pos.copy(), size=target.radius)
        if target.owner >= 0:
            # crew reclaim (spec §4)
            p = st.players.get(target.owner)
            if p and (target.is_ship or target.is_squadron):
                unit = ds.ships.get(target.data_id)
                if unit:
                    p.crew += unit.crew_cost * ds.rules.get("sim", {}).get(
                        "crew_reclaim_fraction", 0.4)
            st.stats.setdefault(str(target.owner), {"kills": 0, "losses": 0, "credits_spent": 0})
            st.stats[str(target.owner)]["losses"] += 1
        if attacker is not None:
            aid = attacker.owner
        else:
            aid = attacker_id
        if aid >= 0:
            st.stats.setdefault(str(aid), {"kills": 0, "losses": 0, "credits_spent": 0})
            st.stats[str(aid)]["kills"] += 1
            if attacker is not None:
                xp_gain = target.max_hull * ds.rules.get("experience", {}).get(
                    "xp_per_kill_fraction", 0.12)
                attacker.xp += xp_gain
                self._update_level(attacker)
        st.events.publish("unit_destroyed", entity_id=target.id, owner=target.owner,
                          data_id=target.data_id, killed_by=aid,
                          is_station=target.is_station)

    def _update_level(self, e) -> None:
        ds = self.ds
        levels = ds.rules.get("experience", {}).get("levels", [0, 120, 320, 700, 1400])
        unit = ds.ships.get(e.data_id) if (e.is_ship or e.is_squadron) else None
        xp_req = unit.veteran_xp if unit else 100.0
        new_level = 1
        for i, threshold in enumerate(levels):
            if e.xp >= threshold * (xp_req / 100.0):
                new_level = i + 1
        if new_level > e.level:
            e.level = new_level
            self.state.float_text(e.pos, f"LEVEL {new_level}", (1, 0.9, 0.4))
            self.state.events.publish("unit_leveled", entity_id=e.id, level=new_level)

    # ------------------------------------------------------------------ EMP/etc
    def apply_emp(self, center: Vec3, radius: float, source_owner: int,
                  system_frac: float, shield_frac: float) -> None:
        st = self.state
        for tid in st.grid.query_sphere(st.entities, center, radius):
            t = st.entity(tid)
            if t is None or t.owner < 0 or not st.is_enemy(source_owner, t.owner):
                continue
            if t.is_planet:
                continue
            for sname, sub in t.systems.items():
                sub.hp = max(0.0, sub.hp - sub.max_hp * system_frac)
            for q in QUADRANTS:
                t.shields[q] = max(0.0, t.shields[q] * (1.0 - shield_frac))
            st.spawn_effect("emp", t.pos.copy())