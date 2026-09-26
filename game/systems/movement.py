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


class MovementSystem:
    def __init__(self, state):
        self.state = state

    def update(self, dt: float) -> None:
        st = self.state
        ds = DataStore.get()
        for e in st.entities.values():
            if not e.alive or e.is_station or e.is_planet:
                continue
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
                    # brake while turning
                    e.vel.set_scaled(e.vel, 0.97)

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