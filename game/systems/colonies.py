"""Shared read-only planetary eligibility and configurable tuning."""
from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..data.store import DataStore

DEFAULTS = dict(satellite_cap=6, control_seconds=15.0, approach_range=600.0, orbit_clearance=350.0,
                orbit_inclination=0.55, orbit_speed=0.06, orbit_shell_spacing=160.0,
                satellite_penalty_seconds=180.0)
SATELLITE_TYPES = ('defense_satellite', 'attack_satellite')


def colony_rules():
    return dict(DEFAULTS, **DataStore.get().rules.get('colonies', {}))


def validate_colony_catalogue(ds):
    cfg = ds.rules.get('colonies', {})
    if not isinstance(cfg, dict):
        raise ValueError('colonies must be an object')
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'colonies {key} must be finite and positive')
        if key == 'satellite_cap' and (type(value) is not int or value > 64):
            raise ValueError('colonies satellite_cap must be an integer from 1 to 64')
    for ship in ds.ships.values():
        if ship.can_colonize and ship.can_build_stations:
            raise ValueError('colony ships cannot build stations')
        if any(s in SATELLITE_TYPES for s in ship.can_build_stations):
            raise ValueError('satellites can only build through a planet')
    for station in ds.stations.values():
        if station.id != 'command_station' and any(getattr(ds.ships.get(s), 'can_colonize', False) for s in station.builds_ships):
            raise ValueError('colony ships require command station')
    for faction in ds.factions.values():
        if faction.playable:
            ships = [s for s in ds.ships.values() if s.faction == faction.id and s.can_colonize]
            if not ships or not all(s.id in ds.stations['command_station'].builds_ships for s in ships):
                raise ValueError('playable faction requires command-only colony ship')

COLONY_TYPES = frozenset(('temperate', 'industrial', 'agricultural', 'military', 'research', 'barren', 'trade'))


def defending_satellites(state, planet):
    return [e for e in state.entities.values()
            if e.alive and e.planet_id == planet.id and e.data_id in SATELLITE_TYPES]


def satellite_lock_remaining(state, planet, slot) -> float:
    """Seconds left before a destroyed satellite's slot may be rebuilt (#57).

    Read-only: rendering and UI must never prune simulation state.
    """
    if planet is None or slot is None or not planet.satellite_locks:
        return 0.0
    return max(0.0, planet.satellite_locks.get(slot, 0.0) - state.time)


def locked_satellite_slots(state, planet) -> set:
    """Slots still paying the destruction penalty (read-only).

    Expired entries are filtered, never removed here: the HUD asks for this every
    frame, and a draw call must not be able to change simulation state. Expiry is
    swept on tick by `prune_satellite_locks`.
    """
    if planet is None or not planet.satellite_locks:
        return set()
    return {slot for slot, until in planet.satellite_locks.items() if until > state.time}


def prune_satellite_locks(state) -> int:
    """Drop expired rebuild penalties. Simulation-side, once per tick."""
    dropped = 0
    for e in state.entities.values():
        if not e.satellite_locks:
            continue
        for slot in [s for s, until in e.satellite_locks.items() if until <= state.time]:
            e.satellite_locks.pop(slot, None)
            dropped += 1
    return dropped


def lock_satellite_slot(state, planet, slot) -> float:
    """Start (or extend) the rebuild penalty for a slot whose satellite died.

    Re-destruction can only push the deadline out, never pull it in.
    """
    if planet is None or slot is None or not eligible_planet(planet):
        return 0.0
    until = state.time + colony_rules()['satellite_penalty_seconds']
    planet.satellite_locks[slot] = max(planet.satellite_locks.get(slot, 0.0), until)
    return planet.satellite_locks[slot]


def eligible_planet(planet):
    return bool(planet and planet.alive and planet.is_planet and planet.data_id in COLONY_TYPES)
