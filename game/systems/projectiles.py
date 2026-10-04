"""ProjectileSystem — projectile flight, proximity hit detection, beam damage queue.

The combat pipeline: WeaponSystem launches projectiles and appends beam damage to
state.damage_queue; this system moves projectiles, detects hits, and forwards
impacts to DamageSystem via the same queue. DamageSystem is the single writer of
hull/shield/subsystem state.
"""
from __future__ import annotations

from ..core.vectors import Vec3
from ..data.store import DataStore


class ProjectileSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    def update(self, dt: float) -> None:
        st = self.state
        dead = []
        for pid, p in st.projectiles.items():
            p.pos.add_scaled(p.vel, dt)
            p.life -= dt
            if p.life <= 0:
                dead.append(pid)
                continue
            # hit detection: check entities near the projectile
            hit = self._find_hit(p)
            if hit is not None:
                target, e = hit
                if st.is_enemy(p.owner, target.owner):
                    st.damage_queue.append({
                        "attacker_id": p.owner,
                        "attacker_entity": (st.entity(p.attacker_entity_id)
                                            if p.attacker_entity_id is not None else None),
                        "target": target,
                        "damage": p.damage,
                        "shield_mult": p.shield_mult,
                        "armor_mult": p.armor_mult,
                        "system_mult": p.system_mult,
                        "weapon": self.ds.weapons.get(p.weapon_id),
                        "impact_pos": p.pos.copy(),
                        "impact_direction": p.vel.copy(),
                        "effect_seed": ((st.seed * 73856093) ^ (st.tick * 19349663)
                                        ^ (p.id * 83492791)) & 0xffffffff,
                    })
                    # DamageSystem emits exactly the contacts that absorbed
                    # damage; a generic glow here doubled every hull hit.
                    st.events.publish("projectile_hit", target_id=target.id,
                                      target_owner=target.owner, weapon=p.weapon_id,
                                      impact_pos=p.pos.to_dict())
                    dead.append(pid)
        for pid in dead:
            st.projectiles.pop(pid, None)

    def _find_hit(self, p):
        st = self.state
        r = 30.0
        for tid in st.grid.query_sphere(st.entities, p.pos, r):
            t = st.entity(tid)
            if t is None:
                continue
            if not st.is_enemy(p.owner, t.owner):
                continue
            if t.is_planet:
                continue
            # proximity check against entity radius
            if p.pos.dist(t.pos) <= max(t.radius * 0.6, 14.0):
                return (t, st.entities.get(tid))
        # fallback: targeted entity check (fast projectiles can tunnel the grid cell)
        t = st.entity(p.target_id)
        if t is not None and st.is_enemy(p.owner, t.owner):
            if p.pos.dist(t.pos) <= max(t.radius * 1.1, 24.0):
                return (t, st.entities.get(p.target_id))
        return None