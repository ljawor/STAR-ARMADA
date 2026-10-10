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
from .experience import rank_for, defense_multiplier


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
                attacker=hit.get("attacker_entity") or hit.get("attacker"),
                attacker_id=hit.get("attacker_id", -2),
                weapon=hit.get("weapon"),
                impact_pos=hit.get("impact_pos"),
                impact_direction=hit.get("impact_direction"),
                effect_seed=hit.get("effect_seed"),
            )

        # 2. shield regeneration
        for e in st.entities.values():
            if not e.operational or e.is_planet:
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
                craft = st.entities.get(eid)
                if craft is not None and craft.boarding:
                    from .boarding import BoardingSystem
                    BoardingSystem(st)._remove(craft)
                else:
                    st.entities.pop(eid, None)
            st.dead_ids.clear()

    # ------------------------------------------------------------------ damage
    def _apply_damage(self, target, raw_damage: float, shield_mult: float,
                      armor_mult: float, system_mult: float,
                      attacker=None, attacker_id: int = -2, weapon=None,
                      impact_pos=None, impact_direction=None,
                      effect_seed=None) -> None:
        st = self.state
        if target is None or not target.alive or target.is_planet:
            return
        source_owner = attacker.owner if attacker is not None else attacker_id
        # Enforce nonaggression at resolution too: queued beams/impacts may
        # predate an alliance change. Keep neutral/environmental physics intact.
        if source_owner >= 0 and target.owner in st.allied_player_ids(source_owner):
            return

        # quadrant facing: which shield arc was hit?
        quad = "front"
        if impact_pos is not None:
            quad = self._quadrant_for(target, impact_pos)
        else:
            quad = "front"

        remaining = max(0.0, raw_damage) * defense_multiplier(target)
        actual_damage = 0.0

        # --- shields first
        if target.max_shield_quad > 0 and target.shields.get(quad, 0) > 0:
            absorbed = min(target.shields[quad], remaining * shield_mult)
            actual_damage += absorbed
            target.shields[quad] -= absorbed
            remaining -= absorbed / max(shield_mult, 0.01)
            if absorbed > 0:
                self._spawn_hit("shield_hit", target, impact_pos, attacker,
                                absorbed, impact_direction, effect_seed)
            if target.shields[quad] <= 0.0:
                target.shields[quad] = 0.0
                # Local absorbed contact already renders the collapse; do not
                # add the old whole-unit shield_down billboard on top.

        target.last_hit_time = st.time

        # --- armor/hull
        if remaining > 0:
            hull_damage = min(max(0.0, target.hull), remaining * max(0.0, armor_mult))
            actual_damage += hull_damage
            target.hull -= hull_damage
            # subsystem chip
            self._chip_systems(target, hull_damage, system_mult)
            # hull threshold effects
            self._hull_threshold_effects(target)
            if hull_damage > 0:
                self._spawn_hit("hull_hit", target, impact_pos, attacker,
                                hull_damage, impact_direction, effect_seed)

        # --- attacker XP
        if self._eligible_for_xp(attacker, target):
            attacker.xp += actual_damage * self.ds.rules.get("experience", {}).get(
                "xp_per_damage", 0.01)
            self._update_level(attacker)

        # --- death
        if target.hull <= 0:
            self._kill(target, attacker, attacker_id)

    def _spawn_hit(self, kind, target, impact_pos, attacker, damage,
                   impact_direction=None, effect_seed=None):
        """Visual metadata only; never consume the simulation RNG."""
        delta = (impact_pos - target.pos) if impact_pos is not None else Vec3()
        if delta.length() < 1e-6 and attacker is not None:
            delta = attacker.pos - target.pos
        if delta.length() < 1e-6 and impact_direction is not None:
            delta = impact_direction * -1.0
        if delta.length() < 1e-6:
            delta = Vec3(math.sin(target.yaw), 0, math.cos(target.yaw))
        normal = delta * (1.0 / delta.length())
        direction = (impact_direction * (1.0 / impact_direction.length())
                     if impact_direction is not None and impact_direction.length() > 1e-6
                     else normal * -1.0)
        radius = target.radius * (1.35 if kind == "shield_hit" else .6)
        contact = target.pos + normal * radius
        seed = (int(effect_seed) if effect_seed is not None else
                ((self.state.seed * 73856093) ^ (self.state.tick * 19349663)
                 ^ (target.id * 83492791) ^ int(damage * 1000)) & 0xffffffff)
        self.state.spawn_effect(kind, contact, target_id=target.id,
                                center=target.pos.to_dict(), normal=normal.to_dict(),
                                direction=direction.to_dict(), radius=radius,
                                target_radius=target.radius,
                                size=min(18.0, max(2.0, target.radius * .12)),
                                seed=seed, damage=damage,
                                color=([.12, .65, 1.] if kind == "shield_hit"
                                       else [1., .46, .12]))

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
        target.crew_cargo = 0  # passengers are casualties, never reclaimed pool crew
        target.crew_mission.clear()
        target.alive = False
        if st._crew_recovery_system is not None:
            st._crew_recovery_system.validate()
        target.hull = 0.0
        st.dead_ids.append(target.id)
        # `seed` varies the blast shape per kill. Drawn from the SIM's rng (not
        # the renderer's) so it stays bit-identical across replays/lockstep.
        st.spawn_effect("explosion", target.pos.copy(), size=target.radius,
                        seed=int(st.rng().random() * 1000))
        if target.owner >= 0:
            # crew reclaim (spec §4)
            p = st.players.get(target.owner)
            if p and (target.is_ship or target.is_squadron):
                p.crew += max(0, target.crew) * ds.rules.get("sim", {}).get(
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
            if self._eligible_for_xp(attacker, target):
                xp_gain = target.max_hull * ds.rules.get("experience", {}).get(
                    "xp_per_kill_fraction", 0.12)
                attacker.xp += xp_gain
                self._update_level(attacker)
        st.events.publish("unit_destroyed", entity_id=target.id, owner=target.owner,
                          data_id=target.data_id, killed_by=aid,
                          killer_owner=aid,
                          cargo_credits=target.cargo_credits,
                          pos=target.pos.to_dict(),
                          is_station=target.is_station)

    def _eligible_for_xp(self, attacker, target) -> bool:
        return (attacker is not None and attacker.alive and attacker.owner >= 0
                and not attacker.is_station and (attacker.is_ship or attacker.is_squadron)
                and target.owner >= 0 and not target.is_planet
                and (target.is_ship or target.is_squadron or target.is_station)
                and self.state.is_enemy(attacker.owner, target.owner))

    def _update_level(self, e) -> None:
        new_level = rank_for(e)
        old_level = e.level
        e.level = new_level
        if new_level > old_level:
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