"""MovementSystem — arcade-tactical movement: accelerate toward target, turn, arrive.

Ships turn toward their move target (or attack target) with a capped turn rate,
thrust along facing, and decelerate inside the arrival radius. Planets and
stations never move. Formation slot targets are resolved before this system runs.
"""
from __future__ import annotations

import math

from ..core.vectors import Vec3
from ..data.store import DataStore
from . import stats
from .weapons import clear_unseen_targets


class MovementSystem:
    def __init__(self, state):
        self.state = state

    def update(self, dt: float) -> None:
        st = self.state
        ds = DataStore.get()
        combat_contacts = []
        # Physical frame snapshots make swept collision handling independent of
        # which hull integrates first. They are never destinations: only a target
        # that passes clear_unseen_targets AND live detection may use one.
        start_positions = {e.id: e.pos.copy() for e in st.entities.values() if e.alive}
        # Fleet assault travel is paced by its slowest active combat member.
        # Otherwise the light screen reaches the enemy minutes before capitals,
        # dies in its orbit, and takes allied remote detection with it.
        fleet_speeds = {}
        for fleet in st.fleets.values():
            speeds = [stats.effective_speed(st, member)
                      for mid in fleet.member_ids
                      if (member := st.entity(mid)) is not None
                      and member.order_type in ("attack", "chase", "attack_move")]
            if speeds:
                fleet_speeds[fleet.id] = min(speeds)
        for e in st.entities.values():
            if not e.operational or e.is_station or e.is_planet:
                continue
            clear_unseen_targets(st, e)
            if e.jump_charge > 0:
                # charging hyperspace: engines locked
                e.vel.set_scaled(e.vel, 0.9)
                continue
            if e.ability_active.get("hyperspace_transit", 0) > 0:
                continue

            # Only explicit combat travel uses an orbit. Ordinary move/follow,
            # commercial routes, hold and planetary colonization stay unchanged.
            combat_target = None
            if e.order_type in ("attack", "chase", "attack_move"):
                tid = e.current_target if e.order_type == "attack_move" else e.order_target_id
                if tid is None:
                    tid = e.current_target
                candidate = st.entity(tid) if tid is not None else None
                if (candidate is not None and not candidate.is_planet
                        and st.is_enemy(e.owner, candidate.owner)
                        and st.can_see(e.owner, candidate.id)):
                    combat_target = candidate

            # pick destination
            target_pos = None
            target_entity = None
            if e.order_target_id is not None:
                target_entity = st.entity(e.order_target_id)
                if target_entity is not None:
                    target_pos = target_entity.pos
                else:
                    e.order_target_id = None
                    e.order_type = "idle"
            if target_pos is None and e.order_target_pos is not None:
                target_pos = e.order_target_pos

            desired_speed = stats.effective_speed(st, e)
            if desired_speed <= 0:
                e.vel.set_scaled(e.vel, 0.95)
                continue

            combat_radius = None
            preferred = 0.0
            firing_window = False
            if combat_target is not None:
                target_entity = combat_target
                target_pos = combat_target.pos
                combat_radius, preferred = self._combat_ranges(e, combat_target)
                combat_contacts.append((e, combat_target, combat_radius,
                                        start_positions[e.id] - start_positions[combat_target.id]))

            if (e.order_type in ("attack", "chase", "attack_move")
                    and e.fleet_id in fleet_speeds
                    and (combat_target is None or e.pos.dist(combat_target.pos) > preferred * 1.6)):
                desired_speed = min(desired_speed, fleet_speeds[e.fleet_id])

            if target_pos is not None:
                to_target = target_pos - e.pos
                dist = to_target.length()
                # desired heading
                dir_t = to_target.normalized()
                # gravity-well avoidance: arc around planets on the path
                # (straight thrust into a keep-out bubble is damped by the
                # separation system every tick → ships stalled forever)
                gate = self._avoid_redirect(st, e, target_pos, dir_t, dist)
                if gate is not None:
                    to_target = gate - e.pos
                if combat_radius is not None:
                    radial = (e.pos - target_pos).normalized()
                    if radial.length_sq() < 1e-8:
                        radial = Vec3(math.sin(e.id * 2.399963229728653), 0,
                                      math.cos(e.id * 2.399963229728653))
                    side = 1.0 if e.id % 2 else -1.0
                    tangent = Vec3(radial.z * side, 0, -radial.x * side)
                    correction = max(-2.0, min(2.0, (preferred - dist) / max(80.0, preferred * .2)))
                    # Approach directly until near the firing shell; a large
                    # tangent bias on a distant contact can arc out of detection
                    # before the attacker ever reaches its useful weapon range.
                    orbit_weight = max(0.0, min(1.0, (preferred * 1.6 - dist) /
                                                max(1.0, preferred * .6)))
                    to_target = tangent * orbit_weight + radial * correction
                    # Curvature must be achievable even by slow-turning capitals.
                    desired_speed = min(desired_speed, preferred * math.radians(
                        stats.effective_turn_rate(st, e)) * .45)
                    unit = ds.ships.get(e.data_id)
                    front_reach = max((ds.resolve_weapon(ref["weapon"] if isinstance(ref, dict) else ref).range
                                       for ref in unit.weapons
                                       if ds.resolve_weapon(ref["weapon"] if isinstance(ref, dict) else ref).hardpoint == "front"),
                                      default=0.0) if unit else 0.0
                    # A tangent nose cannot also point inward. Alternate real
                    # nose-first travel with stopped, target-facing fire windows.
                    # Phase uses persisted sim time, never a local timer/RNG.
                    turn_time = 90.0 / max(1.0, stats.effective_turn_rate(st, e))
                    window = turn_time + 4.0
                    phase = (st.time + e.id * 1.618) % (window * 2 + 24.0)
                    firing_window = dist <= front_reach and phase < window
                    if firing_window:
                        to_target = target_pos - e.pos
                    elif gate is not None and dist > preferred * 1.25:
                        # Preserve the stable center-bound approach detour.
                        # Once in the firing shell, do not repeatedly replace
                        # local orbit steering with distant gravity-well gates.
                        to_target = gate - e.pos
                desired_yaw = math.atan2(to_target.x, to_target.z)
                turn = stats.effective_turn_rate(st, e)
                diff = self._angle_diff(desired_yaw - e.yaw)
                max_turn = math.radians(turn) * dt
                if abs(diff) <= max_turn:
                    e.yaw += diff
                else:
                    e.yaw += max_turn if diff > 0 else -max_turn

                facing = Vec3(math.sin(e.yaw), 0.0, math.cos(e.yaw))
                alignment = facing.dot(to_target.normalized())

                # arrive: slow down near destination
                arrival = 220.0
                speed = desired_speed * max(0.15, alignment)
                if e.order_type == "move" and dist < arrival:
                    speed = desired_speed * (dist / arrival)
                if firing_window:
                    e.vel.set_scaled(e.vel, 0.0)
                elif alignment > 0.35:
                    accel = desired_speed * 1.6
                    dv = facing * accel * dt
                    # steer velocity toward facing direction
                    e.vel.add_scaled(dv, 1.0)
                    # clamp speed
                    v = e.vel.length()
                    if v > desired_speed:
                        e.vel.set_scaled(e.vel, desired_speed / v)
                else:
                    # brake while turning (keep some flow — hard stops feel
                    # sluggish; nose-first projection still prevents crabbing)
                    e.vel.set_scaled(e.vel, 0.985)

                # station-keeping: stop at destination (or standoff at target entity)
                standoff = 0.0
                if target_entity is not None:
                    standoff = target_entity.radius + e.radius * 2.2 + 30
                    if e.is_squadron and target_entity.is_station:
                        standoff = target_entity.radius + 60
                    if e.is_squadron and target_entity.is_squadron:
                        standoff = target_entity.radius + e.radius + 40
                    if target_entity.is_planet:
                        standoff = target_entity.radius + e.radius + 80
                elif e.order_type in ("move", "attack_move") and dist < 25:
                    e.order_type = "idle"
                    e.order_target_pos = None
                if target_entity is not None and dist < standoff:
                    e.vel.set_scaled(e.vel, 0.85)
                    if e.order_type == "move":
                        e.order_type = "idle"
                        e.order_target_pos = None
                        e.order_target_id = None
            else:
                # no destination: gentle brake, keep facing
                e.vel.set_scaled(e.vel, 0.98)

            # NOSE-FIRST guarantee: project velocity onto facing before
            # integrating — the lateral (strafe) component is discarded and
            # reverse velocity is clamped to zero, so a ship can only ever
            # travel toward its nose (or hang while turning).
            facing = Vec3(math.sin(e.yaw), 0.0, math.cos(e.yaw))
            along = e.vel.x * facing.x + e.vel.z * facing.z
            if along < 0.0:
                along = 0.0
            e.vel.x = facing.x * along
            e.vel.z = facing.z * along

            # integrate: combat uses swept segment clipping, not endpoint-only
            # damping, so even an abnormally large dt cannot cross the target.
            if combat_radius is not None:
                self._combat_integrate(e, combat_target, combat_radius, dt)
            else:
                e.pos.add_scaled(e.vel, dt)
            # soft map bounds
            b = st.map_info.bounds
            if abs(e.pos.x) > b or abs(e.pos.z) > b or abs(e.pos.y) > b * 0.5:
                e.pos.x = max(-b, min(b, e.pos.x))
                e.pos.z = max(-b, min(b, e.pos.z))
                e.pos.y = max(-b * 0.5, min(b * 0.5, e.pos.y))
                e.vel.set_scaled(e.vel, 0.5)

        # Resolve a moving enemy that integrated later in dictionary order.
        # This is collision recovery only, not a hidden-target steering query.
        for e, target, radius, initial_offset in combat_contacts:
            if st.can_see(e.owner, target.id):
                self._combat_integrate(e, target, radius, 0.0, initial_offset)

    @staticmethod
    def _combat_integrate(e, target, radius, dt, initial_offset=None):
        offset = e.pos - target.pos
        if offset.length_sq() < radius * radius:
            # Explicit collision recovery is the sole positional sidestep;
            # propulsion remains nose-first, with no lateral velocity retained.
            radial = offset.normalized()
            if offset.length_sq() < 1e-12:
                radial = Vec3(math.sin(e.id * 2.399963229728653), 0,
                              math.cos(e.id * 2.399963229728653))
            e.pos.set(target.pos + radial * (radius + 1e-6))
            e.vel.set_scaled(e.vel, 0.0)
            return
        delta = e.vel * dt
        if initial_offset is not None:
            # Relative swept path catches a center moving through the attacker,
            # even when both final endpoints are outside the forbidden sphere.
            if initial_offset.length_sq() < radius * radius:
                return  # the initial overlap was already recovered above
            delta = offset - initial_offset
            offset = initial_offset
        a = delta.length_sq()
        b = offset.dot(delta)
        c = offset.length_sq() - radius * radius
        fraction = 1.0
        discriminant = b * b - a * c
        if a > 1e-12 and b < 0 and discriminant >= 0:
            entry = (-b - math.sqrt(discriminant)) / a
            if 0 <= entry <= 1:
                fraction = max(0.0, entry - 1e-8)
                e.vel.set_scaled(e.vel, 0.0)
        if initial_offset is None:
            e.pos.add_scaled(delta, fraction)
        elif fraction < 1.0:
            # Contact displacement follows the moving exclusion sphere; this
            # explicit collision correction does not introduce strafe velocity.
            e.pos.set(target.pos + offset + delta * fraction)

    @staticmethod
    def _combat_ranges(e, target):
        """Center-based reach, matching WeaponSystem; never shrink hull safety.

        Longest applicable weapon gives a useful orbit (78% range), leaving
        maneuver margin. An oversized target remains unreachable, not penetrable.
        """
        ds = DataStore.get()
        unit = ds.ships.get(e.data_id)
        ranges = []
        if unit is not None:
            for ref in unit.weapons:
                wd = ds.resolve_weapon(ref["weapon"] if isinstance(ref, dict) else ref)
                if (wd.targets == "fighters" and not target.is_squadron
                        or wd.targets == "capital" and not (target.is_ship or target.is_station)):
                    continue
                ranges.append(wd.range)
        hard = target.radius + e.radius + 40.0
        reach = max(ranges, default=0.0)
        margin = min(60.0, (reach - hard) * .5) if reach > hard else 60.0
        return hard, max(hard + margin, reach * .78)

    @staticmethod
    def _angle_diff(a: float) -> float:
        while a > math.pi:
            a -= 2 * math.pi
        while a < -math.pi:
            a += 2 * math.pi
        return a

    # ------------------------------------------------------------------ avoidance
    def _avoid_redirect(self, st, e, target_pos, dir_t, dist) -> Vec3 | None:
        """Tangent steering around planet gravity wells.

        If the straight path to `target_pos` cuts a planet's keep-out bubble
        (planet radius + ship radius + clearance) and the ship is heading into
        it, return a gate point on the bubble rim to steer toward instead.
        Ships already heading away (or beyond the bubble) get None.
        """
        clearance = 120.0
        best_gate = None
        best_cost = 1e18
        for p in st.entities.values():
            if not p.alive or not p.is_planet or p.data_id == "asteroid_field":
                continue
            well = p.radius + e.radius + clearance
            to_p = p.pos - e.pos
            d_p = to_p.length()
            if d_p > well + dist:      # planet can't be between ship and target
                continue
            # projection of planet onto the ship->target ray
            along = max(0.0, dir_t.dot(to_p))
            # miss distance of the straight path from the planet center
            miss_sq = max(0.0, d_p * d_p - along * along)
            if miss_sq >= well * well:
                continue               # path already clears the bubble
            # steer to the rim: tangent point offset perpendicular to the ray,
            # on the side the ship is already on (minimal sidestep)
            radial = to_p - dir_t * along
            radial_len = radial.length()
            if radial_len < 1.0:
                # head-on: pick perpendicular by current heading side
                side = 1.0 if math.sin(e.yaw) * dir_t.z - \
                    math.cos(e.yaw) * dir_t.x <= 0 else -1.0
                radial = Vec3(-dir_t.z * side, 0.0, dir_t.x * side)
                radial_len = 1.0
            radial /= radial_len
            gate = p.pos - radial * well
            # don't choose a gate that's farther than a usable one; prefer the
            # nearest threatening planet by along-track distance
            cost = along + (well - math.sqrt(miss_sq))
            if cost < best_cost:
                best_cost = cost
                best_gate = gate
        if best_gate is None:
            return None
        # only redirect while heading INTO the well (alignment vs gate > 0);
        # once abeam/behind, the rim push + separation resolve it naturally
        to_gate = best_gate - e.pos
        if to_gate.length() < 1.0:
            return None
        if to_gate.normalized().dot(dir_t) < 0.1:
            return None
        return best_gate