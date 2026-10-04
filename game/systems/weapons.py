"""WeaponSystem — target acquisition and firing.

Target acquisition: nearest valid enemy within the longest weapon range, using the
spatial grid. Weapons fire independently on cooldown; projectiles/beam ticks are
handed to ProjectileSystem. Auto-targeting respects weapon `targets` restrictions
(fighters-only point defense, capital-only torpedoes).
"""
from __future__ import annotations

import math

from ..core.vectors import Vec3
from ..core.world import Projectile
from ..data.store import DataStore
from . import stats


def clear_unseen_targets(st, e) -> None:
    """Drop contact-dependent orders before any system reads a live position."""
    if e.current_target is not None:
        target = st.entity(e.current_target)
        if (target is None or not st.is_enemy(e.owner, target.owner)
                or not st.can_see(e.owner, target.id)):
            e.current_target = None
            if e.order_type in ("attack", "chase") and e.order_target_id is None:
                e.order_type = "idle"
                e.order_target_pos = None
    if e.order_target_id is not None:
        target = st.entity(e.order_target_id)
        # Trade routes have explicit stationary market endpoints, not enemy
        # combat locks. Preserve commerce/escort movement without relaxing any
        # attack, chase, or hostile follow order.
        from .trading import TradingSystem
        commercial_route = (e.data_id == "trade_convoy" and e.order_type == "move"
                            and e.order_target_id == e.convoy_dest
                            and e.order_target_pos is None
                            and TradingSystem.valid_destination(st, e, target))
        friendly_attack = (e.order_type in ("attack", "chase")
                           and target is not None
                           and not st.is_enemy(e.owner, target.owner))
        if target is None or friendly_attack or (not commercial_route
                              and st.is_enemy(e.owner, target.owner)
                              and not st.can_see(e.owner, target.id)):
            e.order_target_id = None
            e.order_target_pos = None
            e.order_type = "idle"


class WeaponSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    # ------------------------------------------------------------------ helpers
    def _target_valid(self, e, tid: int) -> bool:
        t = self.state.entity(tid)
        if (t is None or not self.state.is_enemy(e.owner, t.owner)
                or not self.state.can_see(e.owner, tid)):
            return False
        return True

    def _weapon_can_hit(self, weapon_data, target) -> bool:
        ttype = weapon_data.targets
        if ttype == "all":
            return True
        if ttype == "fighters":
            return bool(target.is_squadron)
        if ttype == "capital":
            return bool(target.is_ship or target.is_station)
        return True

    def _in_arc(self, e, target, hardpoint: str) -> bool:
        if hardpoint == "all":
            return True
        to_t = target.pos - e.pos
        if to_t.length_sq() < 1e-6:
            return True
        facing = Vec3(math.sin(e.yaw), 0, math.cos(e.yaw))
        d = to_t.normalized().dot(facing)
        if hardpoint == "front":
            return d > 0.3
        if hardpoint == "rear":
            return d < -0.3
        if hardpoint == "left":
            return abs(d) < 0.7 and (to_t.x * math.cos(e.yaw) - to_t.z * math.sin(e.yaw)) > 0
        if hardpoint == "right":
            return abs(d) < 0.7 and (to_t.x * math.cos(e.yaw) - to_t.z * math.sin(e.yaw)) < 0
        return True

    def find_target(self, e, scan_radius: float):
        """Nearest valid enemy in radius (None otherwise)."""
        st = self.state
        best, best_d = None, 1e18
        for tid in st.grid.query_sphere(st.entities, e.pos, scan_radius):
            if tid == e.id:
                continue
            t = st.entity(tid)
            if not self._target_valid(e, tid):
                continue
            # squadrons prefer fighters, etc. handled by weapon filters at fire time
            d = e.pos.dist_sq(t.pos)
            if d < best_d:
                best, best_d = t, d
        return best

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> None:
        st = self.state
        for e in st.entities.values():
            if not e.alive:
                continue
            if e.is_station or e.is_planet:
                continue   # stations fire via DefenseSystem? no — same loop below
            self._ship_weapons(e, dt)
        # stations/planets weapons
        for e in st.entities.values():
            if e.alive and (e.is_station or e.is_planet):
                self._ship_weapons(e, dt, is_static=True)

    def _ship_weapons(self, e, dt: float, is_static: bool = False) -> None:
        st = self.state
        if e.owner < 0:
            return
        clear_unseen_targets(st, e)
        # determine target
        target = None
        if e.current_target is not None:
            if self._target_valid(e, e.current_target):
                target = st.entity(e.current_target)
            else:
                e.current_target = None
        if target is None:
            e.retarget_cooldown -= dt
            if e.retarget_cooldown <= 0:
                e.retarget_cooldown = 0.5
                # scan radius: longest weapon range + small margin
                longest = 0.0
                unit = self._resolve_unit_data(e)
                if unit:
                    for wref in unit.weapons:
                        wd = self.ds.resolve_weapon(
                            wref["weapon"] if isinstance(wref, dict) else wref)
                        longest = max(longest, wd.range)
                if longest > 0:
                    t = self.find_target(e, longest * 1.15)
                    if t is not None:
                        target = t
                        e.current_target = t.id
        if target is None:
            return

        # attack orders: chase target if out of range
        dist = e.pos.dist(target.pos)
        if e.order_type in ("idle", "hold"):
            # hold position: only shoot what's in range (handled by weapons below)
            pass

        unit = self._resolve_unit_data(e)
        if not unit:
            return
        for idx, wref in enumerate(unit.weapons):
            wid = wref["weapon"] if isinstance(wref, dict) else wref
            wd = self.ds.resolve_weapon(wid)
            key = idx
            cd = e.weapon_cooldowns.get(key, 0.0)
            if cd > 0:
                e.weapon_cooldowns[key] = cd - dt
                continue
            if dist > wd.range or not self._weapon_can_hit(wd, target):
                continue
            if not self._in_arc(e, target, wd.hardpoint) and not is_static:
                continue
            # energy check
            if wd.energy_cost > 0 and e.energy < wd.energy_cost:
                continue
            e.energy -= wd.energy_cost
            e.weapon_cooldowns[key] = stats.effective_weapon_cooldown(st, e, wd.reload)
            count = wref["count"] if isinstance(wref, dict) else 1
            if wd.is_beam:
                # beams tick damage directly
                dmg = stats.effective_weapon_damage(st, e, wd.damage * count)
                self.state.damage_queue.append({
                    "attacker": e, "target": target, "damage": dmg,
                    "shield_mult": wd.shield_mult, "armor_mult": wd.armor_mult,
                    "system_mult": wd.system_mult, "weapon": wd,
                    # Visual-only direction: leave impact_pos absent, preserving
                    # the existing front-quadrant beam damage rule and XP path.
                    "impact_direction": target.pos - e.pos,
                    "effect_seed": ((st.seed * 73856093) ^ (st.tick * 19349663)
                                    ^ (e.id * 83492791) ^ idx) & 0xffffffff,
                })
                incoming = (target.pos - e.pos).normalized()
                shell = target.radius * (1.35 if target.shields.get("front", 0) > 0
                                          and wd.shield_mult > 0 else .6)
                contact = target.pos - incoming * shell
                st.spawn_effect("beam", e.pos.copy(), target_pos=contact.to_dict(),
                                target_id=target.id, resolved_contact=True,
                                color=list(wd.color))
                st.events.publish("weapon_fired", attacker_id=e.id, owner=e.owner,
                                  weapon=wd.id, heavy=wd.is_beam or wd.damage >= 25)
            else:
                self._launch_projectiles(e, target, wd, count)
                st.events.publish("weapon_fired", attacker_id=e.id, owner=e.owner,
                                  weapon=wd.id, heavy=wd.damage >= 25)

    def _launch_projectiles(self, e, target, wd, count: int) -> None:
        st = self.state
        if not self._target_valid(e, target.id):
            return
        dmg = stats.effective_weapon_damage(st, e, wd.damage)
        base = Vec3(math.sin(e.yaw), 0, math.cos(e.yaw))
        for i in range(count):
            # aim with lead + spread
            aim = target.pos.copy()
            spread = Vec3(
                (st.rng().random() - 0.5) * target.radius,
                (st.rng().random() - 0.5) * target.radius * 0.5,
                (st.rng().random() - 0.5) * target.radius,
            )
            aim.add_scaled(spread, 1.0)
            vel = aim - e.pos
            d = vel.length()
            if d < 1e-3:
                continue
            # lead the target
            tv = target.vel
            t_impact = d / wd.projectile_speed
            aim2 = aim + tv * t_impact
            vel = aim2 - e.pos
            d = max(1.0, vel.length())
            vel = vel * (wd.projectile_speed / d)
            muzzle = e.pos + base * (e.radius * 0.8)
            p = Projectile(
                id=st.next_projectile_id, owner=e.owner, weapon_id=wd.id,
                pos=muzzle.copy(), vel=vel, target_id=target.id,
                damage=dmg, shield_mult=wd.shield_mult, armor_mult=wd.armor_mult,
                system_mult=wd.system_mult, life=wd.range / wd.projectile_speed + 1.0,
                color=wd.color, size=wd.size,
            )
            st.next_projectile_id += 1
            st.projectiles[p.id] = p
        st.spawn_effect("muzzle", e.pos.copy(), color=list(wd.color))

    def _resolve_unit_data(self, e):
        ds = self.ds
        if e.is_station:
            return ds.stations.get(e.data_id)
        if e.is_ship or e.is_squadron:
            return ds.ships.get(e.data_id)
        return None
