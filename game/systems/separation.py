"""SeparationSystem — soft collision avoidance (spec §42).

Large ships get strong separation, fighters/squadrons light separation.
Uses the shared spatial grid, runs every tick but is cheap (few neighbors).
"""
from __future__ import annotations

from ..data.store import DataStore


class SeparationSystem:
    def __init__(self, state):
        self.state = state

    def update(self, dt: float) -> None:
        st = self.state
        ds = DataStore.get()
        cell = st.grid.cell
        # check each entity against entities in its own + adjacent cells
        for e in st.entities.values():
            if not e.alive or e.is_planet:
                continue
            if e.is_station:
                continue    # stations are anchored: ships push away, not them
            cx, cy, cz = (int(e.pos.x // cell), int(e.pos.y // cell), int(e.pos.z // cell))
            push_x = push_y = push_z = 0.0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        ids = st.grid.cells.get((cx + dx, cy + dy, cz + dz))
                        if not ids:
                            continue
                        for oid in ids:
                            if oid == e.id:
                                continue
                            o = st.entities.get(oid)
                            if o is None or not o.alive or o.is_planet:
                                continue
                            # planets: bigger avoidance radius handled below
                            min_dist = e.radius + o.radius
                            if e.is_squadron and o.is_squadron:
                                min_dist *= 0.9
                            elif e.is_squadron or o.is_squadron:
                                min_dist *= 0.75
                            else:
                                min_dist *= 1.15
                            dxp = e.pos.x - o.pos.x
                            dyp = e.pos.y - o.pos.y
                            dzp = e.pos.z - o.pos.z
                            d2 = dxp * dxp + dyp * dyp + dzp * dzp
                            if d2 > min_dist * min_dist or d2 < 1e-6:
                                continue
                            d = d2 ** 0.5
                            overlap = (min_dist - d) / min_dist
                            strength = 60.0 if (e.is_squadron or o.is_squadron) else 26.0
                            push = overlap * strength * dt
                            push_x += dxp / d * push
                            push_y += dyp / d * push * 0.5
                            push_z += dzp / d * push
            if push_x or push_y or push_z:
                e.pos.x += push_x
                e.pos.y += push_y
                e.pos.z += push_z

        # planet gravity-well avoidance: simple radial push outside planet surface
        planets = [p for p in st.entities.values()
                   if p.alive and p.is_planet and p.data_id != "asteroid_field"]
        if planets:
            for e in st.entities.values():
                if not e.alive or e.is_planet:
                    continue
                for p in planets:
                    dx = e.pos.x - p.pos.x
                    dy = e.pos.y - p.pos.y
                    dz = e.pos.z - p.pos.z
                    d2 = dx * dx + dy * dy + dz * dz
                    rr = p.radius + e.radius + 40
                    if d2 < rr * rr and d2 > 1e-6:
                        d = d2 ** 0.5
                        push = (rr - d) * 2.0 * dt
                        e.pos.x += dx / d * push
                        e.pos.y += dy / d * push
                        e.pos.z += dz / d * push
                        # damp velocity into the planet
                        vr = (e.vel.x * dx + e.vel.y * dy + e.vel.z * dz) / d
                        if vr < 0:
                            e.vel.x -= dx / d * vr
                            e.vel.y -= dy / d * vr
                            e.vel.z -= dz / d * vr