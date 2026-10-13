"""AbilitySystem — cooldowns, active durations and ability effects."""
from __future__ import annotations

from ..core.vectors import Vec3
from ..data.store import DataStore
from . import stats


class AbilitySystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    # ------------------------------------------------------------------ tick
    def update(self, dt: float) -> None:
        st = self.state
        for e in st.entities.values():
            if not e.operational:
                continue
            # cooldowns
            for aid in list(e.ability_cooldowns.keys()):
                if e.ability_cooldowns[aid] > 0:
                    e.ability_cooldowns[aid] = max(0.0, e.ability_cooldowns[aid] - dt)
            # active durations
            for aid in list(e.ability_active.keys()):
                if e.ability_active[aid] > 0:
                    e.ability_active[aid] = max(0.0, e.ability_active[aid] - dt)
                    self._tick_active(e, aid, dt)
                elif e.ability_active[aid] == 0 and aid in self._on_expire:
                    self._on_expire[aid](self, e)
                    del e.ability_active[aid]
            # energy regen
            if e.energy < e.max_energy:
                e.energy = min(e.max_energy, e.energy + 4.0 * dt)

    def _tick_active(self, e, aid: str, dt: float) -> None:
        st = self.state
        a = self.ds.abilities.get(aid)
        if a is None:
            return
        if aid == "repair_drones":
            rate = a.effects.get("repair_hps", 60) * stats.effective_repair_rate(st, e.owner, e)
            for tid in st.grid.query_sphere(st.entities, e.pos, a.radius):
                t = st.entity(tid)
                if t is None or t.owner != e.owner or t is e or t.is_planet:
                    continue
                from .crew import repair_life_support
                repair_life_support(t, rate * dt)
                if t.hull < t.max_hull:
                    t.hull = min(t.max_hull, t.hull + rate * dt)
                    st.spawn_effect("repair", t.pos.copy())

    # expiry hooks -------------------------------------------------------------
    @property
    def _on_expire(self):
        return {"sensor_jammed": AbilitySystem._expire_sensor_jam}

    def _expire_sensor_jam(self, e) -> None:
        pass  # multiplier recomputed from ability_active each tick; nothing to undo

    # ------------------------------------------------------------------ activation
    def activate(self, e, ability_id: str, target_id: int | None = None,
                 target_pos: Vec3 | None = None) -> bool:
        """Returns True if the ability fired. Checks ownership, cooldown, energy."""
        st = self.state
        a = self.ds.abilities.get(ability_id)
        if a is None or not e.operational:
            return False
        # Validate entity-targeted intent before spending resources. Area effects
        # (including sensor_jam) do not need an entity lock.
        if target_id is not None:
            target = st.entity(target_id)
            if target is None or (st.is_enemy(e.owner, target.owner)
                                  and not st.can_see(e.owner, target_id)):
                return False
        if ability_id == "tractor_beam":
            target = st.entity(target_id) if target_id is not None else None
            if target is None or not st.is_enemy(e.owner, target.owner):
                return False
        if e.ability_cooldowns.get(ability_id, 0.0) > 0:
            return False
        if ability_id == "emergency_shield_recharge" and \
                e.ability_cooldowns.get("shield_lockdown", 0.0) > 0:
            # #78: shields stay down right after hyperspace exit; recharge
            # cannot bypass the lockdown.
            return False
        if e.energy < a.energy_cost:
            return False
        e.energy -= a.energy_cost
        e.ability_cooldowns[ability_id] = a.cooldown
        st.spawn_effect("ability", e.pos.copy(), text=a.display_name)
        st.float_text(e.pos, a.display_name, (0.8, 0.9, 1.0))
        st.events.publish("ability_used", entity_id=e.id, ability=ability_id)

        # instant effects
        eff = a.effects
        if ability_id == "emergency_shield_recharge":
            maxq = stats.effective_max_shield_quad(st, e)
            frac = eff.get("shield_restore_fraction", 0.6)
            for q in e.shields:
                e.shields[q] = min(maxq, e.shields[q] + maxq * frac)
        elif ability_id == "fighter_scramble":
            # instantly complete reinforcement on docked squadrons
            for tid in st.grid.query_sphere(st.entities, e.pos, 900):
                t = st.entity(tid)
                if t and t.is_squadron and t.owner == e.owner and \
                        t.hangar_id == e.id and t.fighter_count < t.max_fighters:
                    t.fighter_count = t.max_fighters
        elif ability_id == "emp_burst":
            from .damage import DamageSystem
            st.dmg_system.apply_emp(e.pos.copy(), a.radius, e.owner,
                                    eff.get("system_damage", 0.5),
                                    eff.get("shield_damage_fraction", 0.35))
        elif ability_id == "tractor_beam":
            if target_id is not None:
                t = st.entity(target_id)
                if t and st.is_enemy(e.owner, t.owner):
                    t.ability_active["tractor_slowed"] = a.duration
        elif ability_id == "sensor_jam":
            for tid in st.grid.query_sphere(st.entities, e.pos, a.radius):
                t = st.entity(tid)
                if t and st.is_enemy(e.owner, t.owner):
                    t.ability_active["sensor_jammed"] = a.duration
        else:
            # timed self-buffs: store duration; stats.py reads ability_active
            if a.duration > 0:
                e.ability_active[ability_id] = a.duration
        return True

    def can_use(self, e, ability_id: str) -> bool:
        a = self.ds.abilities.get(ability_id)
        if a is None:
            return False
        return (e.ability_cooldowns.get(ability_id, 0.0) <= 0.0
                and e.energy >= a.energy_cost)