"""WeaponSystem — target acquisition and firing.

Target acquisition: nearest valid enemy within the longest weapon range, using the
spatial grid. Weapons fire independently on cooldown; projectiles/beam ticks are
handed to ProjectileSystem. Auto-targeting respects weapon `targets` restrictions
(fighters-only point defense, capital-only torpedoes).
"""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3
from ..core.world import Projectile
from ..data.store import DataStore
from . import stats


def mount_arcs(wref, wd) -> tuple:
    """Sectors one hardpoint may fire into.

    The ship's own mount spec wins: `{"weapon": ..., "count": n, "arcs": [...]}`
    lists the sectors that mount was fitted for. The weapon catalogue's single
    `hardpoint` is only the fallback for mounts that declare none (#58: those
    per-mount lists were never read, so every capital's main battery silently
    fell back to `hardpoint: "front"` and could not shoot past its nose).
    """
    arcs = wref.get("arcs") if isinstance(wref, dict) else None
    if arcs:
        return tuple(arcs)
    return (wd.hardpoint,)


def mount_needs_nose(wref, wd) -> bool:
    """True when every sector of this mount points forward, so the hull must aim."""
    return all(arc == "front" for arc in mount_arcs(wref, wd))


def combat_target_allowed(st, e, target, *, automatic=False) -> bool:
    """Live combat policy; explicit derelict permission never authorizes acquisition."""
    return bool(target is not None and target.alive and not target.is_planet
                and not target.jump_travelling
                and st.is_enemy(e.owner, target.owner)
                and st.can_see(e.owner, target.id)
                and (target.operational or (not automatic
                     and e.owner in st.players and not st.players[e.owner].is_ai
                     and e.abandoned_attack_target == target.id
                     and e.order_type == 'attack' and e.order_target_id == target.id)))


def clear_unseen_targets(st, e) -> None:
    """Drop contact-dependent orders before any system reads a live position."""
    if e.current_target is not None:
        target = st.entity(e.current_target)
        if not combat_target_allowed(st, e, target):
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
        forbidden_attack = (e.order_type in ("attack", "chase")
                           and not combat_target_allowed(st, e, target))
        if target is None or forbidden_attack or (not commercial_route
                              and st.is_enemy(e.owner, target.owner)
                              and not st.can_see(e.owner, target.id)):
            e.order_target_id = None
            e.order_target_pos = None
            e.order_type = "idle"
    if e.order_type != "attack" or e.order_target_id != e.abandoned_attack_target:
        e.abandoned_attack_target = None


class WeaponSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    # ------------------------------------------------------------------ helpers
    def _target_valid(self, e, tid: int, *, automatic=False) -> bool:
        t = self.state.entity(tid)
        if not combat_target_allowed(self.state, e, t, automatic=automatic):
            return False
        if e.data_id == 'defense_satellite' and not t.is_squadron:
            return False
        if e.data_id in ('attack_satellite', 'planet_pulsar_cannon') and (not t.is_ship or t.is_squadron):
            return False
        craft = self.state.entity(e.boarding_party_id) if e.boarding_party_id is not None else None
        if (craft is not None and craft.boarding.get('source') == e.id
                and craft.boarding.get('target') == tid
                and craft.boarding.get('phase') != 'return'):
            return False  # do not shoot the hull our own party is capturing
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

    def _in_arcs(self, e, target, arcs) -> bool:
        """True when the target sits in any sector this hardpoint was fitted for."""
        return any(self._in_arc(e, target, arc) for arc in arcs)

    def find_target(self, e, scan_radius: float):
        """Nearest valid enemy in radius (None otherwise)."""
        st = self.state
        best, best_d = None, 1e18
        for tid in st.grid.query_sphere(st.entities, e.pos, scan_radius):
            if tid == e.id:
                continue
            t = st.entity(tid)
            if t is None:
                continue
            # Visibility is a live (potentially expensive) sensor query. A
            # farther candidate cannot replace the winner even when visible.
            # Preserve grid iteration order and strict '<' equal-distance ties.
            d = e.pos.dist_sq(t.pos)
            if (d >= best_d or not t.operational
                    or not self._target_valid(e, tid, automatic=True)):
                continue
            # squadrons prefer fighters, etc. handled by weapon filters at fire time
            best, best_d = t, d
        return best

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> None:
        st = self.state
        for e in st.entities.values():
            if not e.operational:
                continue
            if e.is_station or e.is_planet:
                continue   # stations fire via DefenseSystem? no — same loop below
            self._ship_weapons(e, dt)
        # stations/planets weapons
        for e in st.entities.values():
            if e.operational and (e.is_station or e.is_planet):
                self._ship_weapons(e, dt, is_static=True)

    def _ship_weapons(self, e, dt: float, is_static: bool = False) -> None:
        st = self.state
        if e.owner < 0 or not e.operational:
            return
        if e.jump_travelling:
            # In hyperspace: sensors and weapon locks are inert for the whole
            # ride. Arrival clears the state; nothing fires or tracks (issue #92).
            e.current_target = None
            return
        if e.data_id == 'planet_pulsar_cannon' and e.subsystem_fraction('weapons') <= 0:
            e.current_target = None
            return
        if e.order_type == 'explore':
            e.current_target = None
            return  # survey missions evade; already-fired projectiles stay ballistic
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
            if not is_static and not self._in_arcs(e, target, mount_arcs(wref, wd)):
                continue
            # energy check
            if wd.energy_cost > 0 and e.energy < wd.energy_cost:
                continue
            e.energy -= wd.energy_cost
            e.weapon_cooldowns[key] = stats.effective_weapon_cooldown(st, e, wd.reload)
            count = wref["count"] if isinstance(wref, dict) else 1
            from .upgrades import extra_shots   # #77: refit adds shots per mount
            count = count + extra_shots(e)
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
        # The muzzle sits `0.8 * radius` ahead of the hull along its facing, so
        # every shot has to be aimed FROM the muzzle. Aiming from `e.pos`
        # instead displaces the whole trajectory sideways by the muzzle offset
        # whenever the hull is not pointing exactly at its target - and a ship
        # in a firing orbit points broadside at it (90 degrees, measured), which
        # is the full 72-unit offset on a cruiser. That is wider than a surface
        # building's or a corvette's hit sphere (27-50 units), so no shot could
        # ever land: hulls under ~120 radius were effectively invulnerable, and
        # the reported surface hardware could not be destroyed at all (#60).
        muzzle = e.pos + base * (e.radius * 0.8)
        for i in range(count):
            # aim with lead + spread
            aim = target.pos.copy()
            spread = Vec3(
                (st.rng().random() - 0.5) * target.radius,
                (st.rng().random() - 0.5) * target.radius * 0.5,
                (st.rng().random() - 0.5) * target.radius,
            )
            aim.add_scaled(spread, 1.0)
            vel = aim - muzzle
            d = max(1.0, vel.length())
            # lead the target
            tv = target.vel
            t_impact = d / wd.projectile_speed
            aim2 = aim + tv * t_impact
            vel = aim2 - muzzle
            d = max(1.0, vel.length())
            vel = vel * (wd.projectile_speed / d)
            p = Projectile(
                id=st.next_projectile_id, owner=e.owner, weapon_id=wd.id,
                pos=muzzle.copy(), vel=vel, target_id=target.id,
                damage=dmg, shield_mult=wd.shield_mult, armor_mult=wd.armor_mult,
                system_mult=wd.system_mult, life=wd.range / wd.projectile_speed + 1.0,
                color=wd.color, size=wd.size, attacker_entity_id=e.id,
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
