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
        for e in st.entities.values():
            if not e.alive or e.is_station or e.is_planet:
                continue
            clear_unseen_targets(st, e)
            if e.jump_charge > 0:
                # charging hyperspace: engines locked
                e.vel.set_scaled(e.vel, 0.9)
                continue
            if e.ability_active.get("hyperspace_transit", 0) > 0:
                continue

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
                if alignment > 0.35:
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

            # integrate
            e.pos.add_scaled(e.vel, dt)
            # soft map bounds
            b = st.map_info.bounds
            if abs(e.pos.x) > b or abs(e.pos.z) > b or abs(e.pos.y) > b * 0.5:
                e.pos.x = max(-b, min(b, e.pos.x))
                e.pos.z = max(-b, min(b, e.pos.z))
                e.pos.y = max(-b * 0.5, min(b * 0.5, e.pos.y))
                e.vel.set_scaled(e.vel, 0.5)

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