"""Deterministic inclined satellite orbits; no wall-clock or renderer state."""
import math
from ..core.vectors import Vec3
from .colonies import colony_rules, SATELLITE_TYPES
from . import stats


def orbit_plane(planet_id, slot, cfg):
    """Deterministic per-satellite orbital plane.

    Every satellite used to share one plane derived from `planet.id`, so a
    planet's whole constellation rode a single ring. Derive node AND
    inclination from (planet, slot) instead: stable across save/restore and
    across peers (nothing new to serialize), but visually distinct orbits.
    """
    h = ((planet_id * 73856093) ^ ((slot + 1) * 19349663)) & 0xffffffff
    node = (h % 4096) / 4096.0 * 2 * math.pi
    spread = 0.45 + 0.9 * (((h >> 12) & 0x3ff) / 1023.0)
    return node, cfg['orbit_inclination'] * spread


def orbit_radius(planet, station_radius, slot, cfg):
    """Nested shells: distinct radii keep crossing orbits collision-free."""
    return (planet.radius + station_radius + cfg['orbit_clearance']
            + slot * cfg['orbit_shell_spacing'])


def orbit_position(planet, station_radius, phase, slot=0):
    cfg = colony_rules()
    radius = orbit_radius(planet, station_radius, slot, cfg)
    node, inclination = orbit_plane(planet.id, slot, cfg)
    x = math.sin(phase) * radius
    z = math.cos(phase) * radius * math.cos(inclination)
    y = math.cos(phase) * radius * math.sin(inclination)
    return planet.pos + Vec3(x * math.cos(node) - z * math.sin(node), y,
                             x * math.sin(node) + z * math.cos(node))


def missile_engagement(state, defender, projectile, ds):
    """Contact requires present detection of its hostile launch source."""
    source = state.entity(projectile.attacker_entity_id)
    wd = ds.weapons.get(projectile.weapon_id)
    return bool(wd and 'missile' in wd.id and defender.operational
        and defender.data_id == 'defense_satellite'
        and stats.interception_efficiency(defender) > 0
        and state.is_enemy(defender.owner, projectile.owner)
        and source is not None and state.can_see(defender.owner, source.id)
        and projectile.pos.dist(defender.pos) <= ds.weapons['point_defense'].range)


class SatelliteOrbitSystem:
    def __init__(self, state, weapons, construction):
        self.state, self.weapons, self.construction = state, weapons, construction

    def engaged(self, e):
        st, ds = self.state, self.weapons.ds
        if e.subsystem_fraction('weapons') <= 0:
            return False
        unit = ds.stations[e.data_id]
        weapons = [ds.resolve_weapon(ref['weapon'] if isinstance(ref, dict) else ref)
                   for ref in unit.weapons]
        radius = max((wd.range for wd in weapons), default=0.0)
        candidates = st.grid.query_sphere(st.entities, e.pos, radius)
        for tid in sorted(candidates, key=lambda tid: (e.pos.dist_sq(st.entities[tid].pos), tid)):
            target = st.entity(tid)
            if not self.weapons._target_valid(e, tid):
                continue
            if any(e.pos.dist(target.pos) <= wd.range
                   and self.weapons._weapon_can_hit(wd, target) for wd in weapons):
                # The same contact pauses navigation and fires in this tick;
                # the ordinary idle retarget delay must not hold a paused orbit.
                e.current_target = tid
                return True
        e.current_target = None
        return any(missile_engagement(st, e, p, ds) for p in st.projectiles.values())

    def legal(self, e, planet, pos):
        if not self.construction._check_station_spacing(e.data_id, pos, e.owner, ignore_entity=e)[0]:
            return False
        for other in self.state.entities.values():
            if not other.alive or other is e or other is planet or other.data_id == 'asteroid_field':
                continue
            if other.planet_building_slot is not None and other.planet_id == planet.id:
                continue
            if pos.dist(other.pos) < (e.radius + other.radius) * 1.6:
                return False
        return True

    def update(self, dt):
        cfg = colony_rules()
        for e in sorted(self.state.entities.values(), key=lambda e: e.id):
            if (not e.alive or e.data_id not in SATELLITE_TYPES or e.planet_id is None
                    or e.satellite_slot is None):
                continue
            planet = self.state.entity(e.planet_id)
            if planet is None:
                continue
            if e.satellite_orbit_phase is None:
                e.satellite_orbit_phase = e.satellite_slot * 2 * math.pi / cfg['satellite_cap']
            e.vel = Vec3()
            if not e.operational or self.engaged(e):
                continue
            # Bounded angular segments prevent tunnelling through fixed obstacles.
            segments = max(1, math.ceil(dt * cfg['orbit_speed'] / .02))
            for _ in range(segments):
                phase = (e.satellite_orbit_phase + dt * cfg['orbit_speed'] / segments) % (2 * math.pi)
                pos = orbit_position(planet, e.radius, phase, e.satellite_slot)
                if not self.legal(e, planet, pos):
                    break
                e.satellite_orbit_phase = phase
                e.pos = pos
