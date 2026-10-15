"""Deterministic inclined satellite orbits; no wall-clock or renderer state."""
from game.core import detmath as math  # deterministic sim math, never the platform libm
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


def orbit_position(planet, station_radius, phase, slot=0, *, state=None):
    cfg = colony_rules()
    if state is None:
        radius = orbit_radius(planet, station_radius, slot, cfg)
        node, inclination = orbit_plane(planet.id, slot, cfg)
    else:
        plan = orbit_geometry(state, planet, station_radius, slot)
        if plan is None:
            return None
        radius, node, inclination = plan
    x = math.sin(phase) * radius
    z = math.cos(phase) * radius * math.cos(inclination)
    y = math.cos(phase) * radius * math.sin(inclination)
    return planet.pos + Vec3(x * math.cos(node) - z * math.sin(node), y,
                             x * math.sin(node) + z * math.cos(node))


def ring_distance(center, radius, node, inclination, point):
    """Exact minimum center-distance from a point to the COMPLETE circle."""
    delta = point - center
    u = Vec3(math.cos(node), 0, math.sin(node))
    v = Vec3(-math.sin(node) * math.cos(inclination), math.sin(inclination),
             math.cos(node) * math.cos(inclination))
    projected = math.hypot(delta.dot(u), delta.dot(v))
    return math.sqrt(max(0., delta.length_sq() + radius * radius - 2 * radius * projected))


def rings_clear(center_a, plan_a, center_b, plan_b, minimum):
    """Certify ALL phase pairs; uncertainty/budget exhaustion rejects.

    Distance to a closed set is 1-Lipschitz. On each arc of circle A,
    distance to the complete circle B is at least its midpoint distance
    minus A's radius * half-angle (an upper bound on point displacement).
    Subdivide only uncertified arcs, never accept from samples alone.
    """
    return _rings_clear(center_a.to_tuple(), tuple(plan_a), center_b.to_tuple(),
                        tuple(plan_b), minimum)


from functools import lru_cache


@lru_cache(maxsize=4096)
def _rings_clear(center_a, plan_a, center_b, plan_b, minimum):
    if not all(math.isfinite(v) for v in (*center_a, *center_b, *plan_a, *plan_b, minimum)):
        return False
    a, b = Vec3(*center_a), Vec3(*center_b)
    ra, node, inclination = plan_a
    rb = plan_b[0]
    if min(ra, rb) <= 0 or minimum < 0:
        return False
    # Guard roundoff in analytic distances/subdivision, not a relaxed keep-out.
    guard = max(.001, max(abs(v) for v in (*center_a, *center_b, ra, rb)) * 1e-12)
    floor = minimum + guard
    centers = a.dist(b)
    if max(centers - ra - rb, abs(ra - rb) - centers) >= floor:
        return True
    if ra > rb:
        return _rings_clear(center_b, plan_b, center_a, plan_a, minimum)
    u = Vec3(math.cos(node), 0, math.sin(node))
    v = Vec3(-math.sin(node) * math.cos(inclination), math.sin(inclination),
             math.cos(node) * math.cos(inclination))
    pending = [(math.pi, math.pi, 0)]
    for _ in range(4096):
        if not pending:
            return True
        phase, half, depth = pending.pop()
        point = a + (u * math.sin(phase) + v * math.cos(phase)) * ra
        distance = ring_distance(b, *plan_b, point)
        if distance - ra * half >= floor:
            continue
        if distance < floor or depth >= 18:
            return False
        half *= .5
        pending.append((phase + half, half, depth + 1))
        pending.append((phase - half, half, depth + 1))
    return False


def orbit_geometry(state, planet, station_radius, slot):
    """Public fixed terrain determines safe rings, never hidden contacts.

    Keep normal rings where the entire circle fits. Crowded planets use
    near-polar planes normal to neighbouring bodies, not a smaller keep-out.
    A shared small shell offset preserves separation between every slot.
    The cache is derived geometry only, excluded from save/replay state.
    """
    cfg = colony_rules()
    from ..data.store import DataStore
    hulls = (station_radius, *(DataStore.get().stations[k].radius for k in SATELLITE_TYPES))
    if (any(type(r) not in (int, float) or not math.isfinite(r) or r <= 0 for r in hulls)
            or type(cfg['satellite_cap']) is not int or not 1 <= cfg['satellite_cap'] <= 64
            or any(type(cfg[k]) not in (int, float) or not math.isfinite(cfg[k]) or cfg[k] <= 0
                   for k in ('orbit_clearance', 'orbit_shell_spacing', 'orbit_inclination'))
            or cfg['orbit_inclination'] > math.pi):
        return None
    shell_radius = max(hulls)
    # Distinct planes cross, so radial shell gaps must protect the largest
    # modded hull pair. Never weaken spacing or rescale a mod's hardware.
    if cfg['satellite_cap'] > 1 and cfg['orbit_shell_spacing'] < 3.2 * shell_radius + .001:
        return None
    # Filter first: ID order of relevant terrain is unchanged, while the often
    # much larger fleet never enters this repeated terrain sort/cache key.
    terrain = sorted((e for e in state.entities.values()
                      if e.alive and e.is_planet and e is not planet
                      and e.data_id != 'asteroid_field'), key=lambda e: e.id)
    bodies = tuple((e.id, e.pos.x, e.pos.y, e.pos.z, e.radius)
                   for e in terrain)
    plans = _terrain_plans(planet.id, planet.pos.to_tuple(), planet.radius, shell_radius,
                           tuple(sorted(cfg.items())), bodies, state.map_info.bounds)
    return plans[slot] if plans is not None and 0 <= slot < len(plans) else None


@lru_cache(maxsize=256)
def _terrain_plans(planet_id, center, planet_radius, station_radius, config, bodies, bounds):
    cfg = dict(config)
    center = Vec3(*center)
    # Radius is expanded only if even the best plane of an inner shell cannot
    # clear the body. 32u increments leave all configured inter-shell gaps intact.
    for offset in range(0, 513, 32):
        plans = []
        for slot in range(cfg['satellite_cap']):
            radius = planet_radius + station_radius + cfg['orbit_clearance'] + slot * cfg['orbit_shell_spacing'] + offset
            # Integration uses chords of at most .02 radians. Certify their
            # innermost point against the unchanged parent keep-out as well.
            if radius * math.cos(.01) < planet_radius + station_radius + 40 + .001:
                break
            candidates = [orbit_plane(planet_id, slot, cfg)]
            for _, x, y, z, _ in bodies:
                normal = (Vec3(x, y, z) - center).normalized()
                # Distinct slightly tilted planes; a body-normal ring maximizes
                # clearance at fixed radius. Try that optimum last as fallback.
                for tilt in ((slot + 1) * .015, -(slot + 1) * .015, 0.):
                    n = (normal + Vec3(0, tilt, 0)).normalized()
                    node = math.atan2(-n.x, n.z)
                    inclination = math.atan2(math.hypot(n.x, n.z), -n.y)
                    candidates.append((node, inclination))
            for node, inclination in candidates:
                if abs(center.x) + radius > bounds or abs(center.z) + radius > bounds:
                    continue
                if all(ring_distance(center, radius, node, inclination, Vec3(x, y, z))
                       >= (station_radius + other_radius) * 1.6 + .001
                       for _, x, y, z, other_radius in bodies):
                    plans.append((radius, node, inclination))
                    break
            else:
                break
        if len(plans) == cfg['satellite_cap']:
            return tuple(plans)
    # Impossible/modded geometry fails closed rather than spending on a ring
    # that looks legal at one phase but will inevitably freeze later.
    return None


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

    def legal_segment(self, e, planet, start, end):
        """Swept spheres, including paid sites; bounded angles alone can tunnel."""
        direction = end - start
        length_sq = direction.length_sq()
        def closest(point):
            fraction = max(0., min(1., (point - start).dot(direction) / length_sq)) if length_sq else 0.
            return start + direction * fraction
        for other in self.state.entities.values():
            if not other.alive or other is e or other.data_id == 'asteroid_field':
                continue
            if other is planet:
                floor = planet.radius + e.radius + 40
            elif other.planet_building_slot is not None and other.planet_id == planet.id:
                continue
            elif other.is_station:
                floor = self.construction.station_min_distance(e.data_id, other.data_id,
                    other.radius, e.owner, other.owner)
            else:
                floor = (e.radius + other.radius) * 1.6
            if closest(other.pos).dist(other.pos) < floor:
                return False
            for work in other.build_queue:
                if (work.get('kind') not in ('station', 'satellite') or work.get('status') != 'paid'
                        or work.get('pos') is None):
                    continue
                sd = self.construction.ds.stations[work['item']]
                floor = self.construction.station_min_distance(e.data_id, sd.id, sd.radius, e.owner)
                point = Vec3(*work['pos'])
                if closest(point).dist(point) < floor:
                    return False
        return self.legal(e, planet, end)

    def _advance(self, e, planet, seconds, cfg):
        plan = orbit_geometry(self.state, planet, e.radius, e.satellite_slot)
        if plan is None:
            return False
        radius, node, inclination = plan
        expected = orbit_position(planet, e.radius, e.satellite_orbit_phase,
                                  e.satellite_slot, state=self.state)
        if e.pos.dist(expected) > 1e-6:
            # Existing saves/replays retain their old plane. Rejoin the nearest
            # point on the certified ring at orbital speed, never teleport.
            delta = e.pos - planet.pos
            u = Vec3(math.cos(node), 0, math.sin(node))
            v = Vec3(-math.sin(node) * math.cos(inclination), math.sin(inclination),
                     math.cos(node) * math.cos(inclination))
            phase = math.atan2(delta.dot(u), delta.dot(v)) % (2 * math.pi)
            target = orbit_position(planet, e.radius, phase, e.satellite_slot, state=self.state)
            before_radius = delta.length()
            a, b = delta.normalized(), (target - planet.pos).normalized()
            angle = math.atan2(a.cross(b).length(), a.dot(b))
            distance = angle * max(radius, before_radius) + abs(radius - before_radius)
            fraction = min(1., seconds * cfg['orbit_speed'] * radius / max(distance, 1e-9))
            direction = (a * (1 - fraction) + b * fraction).normalized()
            pos = planet.pos + direction * (before_radius + (radius - before_radius) * fraction)
            if not self.legal_segment(e, planet, e.pos, pos):
                return False
            e.pos = pos
            if fraction == 1.:
                e.pos = target
                e.satellite_orbit_phase = phase
            return True
        phase = (e.satellite_orbit_phase + seconds * cfg['orbit_speed']) % (2 * math.pi)
        pos = orbit_position(planet, e.radius, phase, e.satellite_slot, state=self.state)
        if not self.legal_segment(e, planet, e.pos, pos):
            return False
        e.satellite_orbit_phase, e.pos = phase, pos
        return True

    def update(self, dt):
        cfg = colony_rules()
        for e in sorted(self.state.entities.values(), key=lambda e: e.id):
            if (not e.alive or e.data_id not in SATELLITE_TYPES or e.planet_id is None
                    or e.satellite_slot is None):
                continue
            e.vel = Vec3()
            planet = self.state.entity(e.planet_id)
            if planet is None:
                continue
            if e.satellite_orbit_phase is None:
                e.satellite_orbit_phase = e.satellite_slot * 2 * math.pi / cfg['satellite_cap']
            if not e.operational or self.engaged(e):
                continue
            before = e.pos.copy()
            # Bounded angular segments prevent tunnelling through fixed obstacles.
            segments = max(1, math.ceil(dt * cfg['orbit_speed'] / .02))
            for _ in range(segments):
                if not self._advance(e, planet, dt / segments, cfg):
                    break
            # Report the displacement actually accepted this tick, including a
            # partially blocked orbit. Gunnery leads this velocity; stations are
            # skipped by MovementSystem, so it must not be integrated again.
            if dt > 0:
                e.vel = (e.pos - before) * (1.0 / dt)
