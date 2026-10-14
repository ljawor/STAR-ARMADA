"""Paid five-level station refits (#77): eligibility, cost, timing and bonuses.

Level 1 is the hull as it leaves the yard; each of the four paid steps above it is
bought from the station panel and completed on a timer. Every bonus is derived from
`Entity.upgrade_level` in one place, so the simulation, the HUD and a mod's rules
file cannot disagree about what a level is worth — see docs/STATION_UPGRADES.md for
the contract this module implements.
"""
from __future__ import annotations

from typing import Any

from ..core import detmath as math  # deterministic sim math, never the platform libm
from ..data import balance
from ..data.store import DataStore

# Hardware built *on* a planet is explicitly out of scope (the issue excludes it):
# the four surface buildings and the two orbit satellites.
EXCLUDED = frozenset((
    'planet_extractor', 'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon',
    'defense_satellite', 'attack_satellite',
))

#: Tuning; `station_upgrades` in game_rules.json overrides any key. cost_mult and
#: time_mult are indexed by the *current* level, so entry 0 buys level 2. They are
#: fractions of the station's own catalogue build cost and build time, so a command
#: station's refit is dearer than a sensor station's and a full ladder costs 5.35x
#: the hull over 3.95x its build time.
DEFAULTS: dict[str, Any] = dict(
    max_level=5,
    cost_mult=(0.75, 1.10, 1.50, 2.00),
    time_mult=(0.60, 0.85, 1.10, 1.40),
    hull_bonus=0.10,
    shield_bonus=0.10,
    shield_regen_bonus=0.08,
    damage_bonus=0.12,
    volley_shots_per_level=1,
    production_bonus=0.15,
    convoy_cargo_bonus=0.15,
    convoy_per_two_levels=1,
)


def upgrade_rules(ds=None, rules=None) -> dict:
    """Tuning merged over the shipped defaults; `station_upgrades` in game_rules.

    A plain merge, deliberately not memoized: callers patch the live rules dict in
    place (the established way to retune a value under test), and a cache keyed on
    that dict's identity would then hand back a stale merge. The merge is 11 keys
    and the hot callers are per-volley and per-tick-per-station, not per vertex.
    """
    ds = DataStore.get() if ds is None else ds
    configured = ds.rules.get('station_upgrades', {}) if rules is None else rules
    return dict(DEFAULTS, **(configured if isinstance(configured, dict) else {}))


def _number(rules: dict, key: str) -> float:
    value = rules.get(key, DEFAULTS[key])
    if type(value) not in (int, float):
        value = DEFAULTS[key]
    return float(value)


def max_level(rules=None) -> int:
    try:
        return max(1, int(_number(upgrade_rules() if rules is None else rules, 'max_level')))
    except (TypeError, ValueError):
        return 5


def station_level(e) -> int:
    """Refit level of a hull, 1 for anything that predates the field or is a ship."""
    value = getattr(e, 'upgrade_level', 1)
    if type(value) is not int or value < 1:
        return 1
    return min(value, max_level())


def eligible(e, ds=None) -> bool:
    """A station hull laid down by a yard — never a planet or planet-built hardware."""
    ds = DataStore.get() if ds is None else ds
    if e is None or not e.is_station or getattr(e, 'is_planet', False):
        return False
    if e.data_id in EXCLUDED:
        return False
    return e.data_id in ds.stations


def _station_data(e, ds=None):
    ds = DataStore.get() if ds is None else ds
    return ds.stations.get(e.data_id) if e is not None else None


def type_is_armed(ds, station_id: str) -> bool:
    """True when a catalogue hull carries a weapon that actually deals damage.

    Read from the data, never from the name, so a mod that arms a mining station gets a
    firepower ladder for it with no code change. Entity-free on purpose: the balance
    screen asks the same question about a station *type* before offering it a damage row.
    """
    data = (ds.stations or {}).get(station_id)
    if data is None:
        return False
    for wref in getattr(data, 'weapons', ()) or ():
        wid = wref.get('weapon') if isinstance(wref, dict) else wref
        if not isinstance(wid, str):
            continue
        wd = ds.resolve_weapon(wid)
        if wd is not None and float(wd.damage) > 0:
            return True
    return False


def is_armed(e, ds=None) -> bool:
    """True when a live hull's station type is armed; a ship or planet never is."""
    ds = DataStore.get() if ds is None else ds
    return type_is_armed(ds, e.data_id) if _station_data(e, ds) is not None else False


def type_produces(ds, station_id: str) -> bool:
    """True when a catalogue hull carries an income table a collected load can fill."""
    data = (ds.stations or {}).get(station_id)
    return bool(getattr(data, 'income', None)) if data is not None else False


def produces(e, ds=None) -> bool:
    """True when a live hull's station type has an income table to collect."""
    ds = DataStore.get() if ds is None else ds
    return type_produces(ds, e.data_id) if _station_data(e, ds) is not None else False


def step_multiplier(rules: dict, level: int, key: str) -> float:
    """The multiplier for the step that buys `level + 1`, clamped to the table."""
    table = rules.get(key, DEFAULTS[key])
    if not isinstance(table, (list, tuple)) or not table:
        table = DEFAULTS[key]
    entries = list(table)
    index = max(0, min(level - 1, len(entries) - 1))
    return float(entries[index])


def queued_refit(station):
    """The pending refit item on a hull, or None. Only one may be pending."""
    for work in getattr(station, 'build_queue', ()) or ():
        if work.get('kind') == 'station_upgrade':
            return work
    return None


def next_level(e) -> int:
    return station_level(e) + 1


def upgrade_cost(e, ds=None) -> dict | None:
    """Resource bill for the next level, or None when it cannot be bought.

    Crew is deliberately excluded: a refit works on a hull that already has its
    complement, so it must not consume the player's unassigned crew pool the way a
    new hull's `crew_cost` does.
    """
    ds = DataStore.get() if ds is None else ds
    if not eligible(e, ds):
        return None
    level = station_level(e)
    rules = upgrade_rules(ds)
    if level >= max_level(rules):
        return None
    data = ds.stations[e.data_id]
    mult = step_multiplier(rules, level, 'cost_mult')
    return {
        'credits': int(round(float(data.cost_credits) * mult)),
        'materials': int(round(float(data.cost_materials) * mult)),
        'energy': int(round(float(data.cost_energy) * mult)),
    }


def upgrade_time(e, ds=None) -> float | None:
    """Refit seconds, or None when the hull cannot be upgraded."""
    ds = DataStore.get() if ds is None else ds
    if not eligible(e, ds):
        return None
    level = station_level(e)
    rules = upgrade_rules(ds)
    if level >= max_level(rules):
        return None
    data = ds.stations[e.data_id]
    return float(data.build_time) * step_multiplier(rules, level, 'time_mult')


# --------------------------------------------------------------------- bonuses
def _steps(e) -> int:
    """Levels gained so far; every bonus is a multiple of this."""
    return station_level(e) - 1 if e is not None and e.is_station else 0


def _level_factor(level: int, key: str, rules=None) -> float:
    rules = upgrade_rules() if rules is None else rules
    return 1.0 + _number(rules, key) * max(0, int(level) - 1)


def station_rules(e, rules=None, ds=None) -> dict:
    """The tuning one hull actually uses: the global table plus its type's overrides.

    The global table is the shipped shape; a player may replace individual gains for a
    station type (#106). Merging here — rather than at each call site — keeps hull,
    shields, firepower, output and the panel's effect line reading one dict, so a hull
    can never be scaled by one set of numbers and described by another.
    """
    if rules is not None:
        # An explicit table means the caller took control (the established way to retune
        # under test); file overrides are deliberately not folded on top of it.
        return rules
    ds = DataStore.get() if ds is None else ds
    base = upgrade_rules(ds)
    if e is None or not e.is_station:
        return base
    try:
        # Read from the catalogue's own rules, not from the merged upgrade table: the overlay
        # is a sibling key there, so folding it into `base` first would have hidden it.
        overrides = balance.station_overrides(ds.rules, e.data_id)
    except Exception:                       # a hand-edited rules file must not crash a tick
        return base
    return dict(base, **overrides) if overrides else base


def hull_multiplier(e, rules=None, ds=None) -> float:
    if e is None or not e.is_station:
        return 1.0
    return _level_factor(station_level(e), 'hull_bonus', station_rules(e, rules, ds))


def shield_multiplier(e, rules=None, ds=None) -> float:
    if e is None or not e.is_station:
        return 1.0
    return _level_factor(station_level(e), 'shield_bonus', station_rules(e, rules, ds))


def shield_regen_multiplier(e, rules=None, ds=None) -> float:
    if e is None or not e.is_station:
        return 1.0
    return _level_factor(station_level(e), 'shield_regen_bonus', station_rules(e, rules, ds))


def damage_multiplier(e, rules=None, ds=None) -> float:
    """Firepower bonus for an armed station; ships and planets are untouched."""
    if e is None or not e.is_station:
        return 1.0
    return _level_factor(station_level(e), 'damage_bonus', station_rules(e, rules, ds))


def extra_shots(e, rules=None, ds=None) -> int:
    """Extra projectiles/beam ticks each weapon mount fires per volley."""
    if e is None or not e.is_station:
        return 0
    rules = station_rules(e, rules, ds)
    return int(_number(rules, 'volley_shots_per_level') * _steps(e))


def production_multiplier(e, rules=None, ds=None) -> float:
    """Output bonus for a collecting station; planets stay at 1.0 (excluded)."""
    if not (e is not None and e.is_station and not getattr(e, 'is_planet', False)):
        return 1.0
    return _level_factor(station_level(e), 'production_bonus', station_rules(e, rules, ds))


def convoy_cargo_multiplier(e, rules=None, ds=None) -> float:
    if e is None or not e.is_station:
        return 1.0
    return _level_factor(station_level(e), 'convoy_cargo_bonus', station_rules(e, rules, ds))


def extra_convoys(e, rules=None, ds=None) -> int:
    """Additional convoys a market releases each interval."""
    if e is None or not e.is_station:
        return 0
    rules = station_rules(e, rules, ds)
    return int(_number(rules, 'convoy_per_two_levels') * (_steps(e) // 2))


def bonus_table(e, ds=None) -> dict:
    """Human-facing effect of the current level, for the panel and diagnostics."""
    ds = DataStore.get() if ds is None else ds
    return {
        'level': station_level(e), 'max_level': max_level(upgrade_rules(ds)),
        'steps': _steps(e),
        'hull_bonus': hull_multiplier(e, ds=ds) - 1.0,
        'shield_bonus': shield_multiplier(e, ds=ds) - 1.0,
        'shield_regen_bonus': shield_regen_multiplier(e, ds=ds) - 1.0,
        'damage_bonus': damage_multiplier(e, ds=ds) - 1.0,
        'extra_shots': extra_shots(e, ds=ds),
        'production_bonus': production_multiplier(e, ds=ds) - 1.0,
        'convoy_cargo_bonus': convoy_cargo_multiplier(e, ds=ds) - 1.0,
        'extra_convoys': extra_convoys(e, ds=ds),
    }


# -------------------------------------------------------------------- applying
def apply_level(state, station, item: dict) -> bool:
    """Complete a refit: raise the level and the capacity that step paid for.

    Hull, shield capacity and regeneration are stored entity fields — damage,
    repair, AI strength and the desync digest all read them directly — so they are
    raised here, once. Current hull and shield quads are scaled by the same factor
    instead of being topped up, so a damaged station stays exactly as damaged as it
    was and a refit can never be bought as a repair.
    """
    ds = DataStore.get()
    data = _station_data(station, ds)
    if data is None or not station.is_station:
        return False
    current = station_level(station)
    target = item.get('level')
    target = max(current, min(int(target) if type(target) is int else next_level(station),
                             max_level()))
    if target == current:
        return False
    # The same table `bonus_table`/`hull_multiplier` report (#106): scaling capacity by the
    # shipped gain while the panel quoted the player's edited one would leave a station
    # permanently disagreeing with its own description.
    rules = station_rules(station, ds=ds)
    hull_factor = (_level_factor(target, 'hull_bonus', rules)
                   / _level_factor(current, 'hull_bonus', rules))
    shield_factor = (_level_factor(target, 'shield_bonus', rules)
                     / _level_factor(current, 'shield_bonus', rules))
    regen_factor = (_level_factor(target, 'shield_regen_bonus', rules)
                    / _level_factor(current, 'shield_regen_bonus', rules))
    station.upgrade_level = target
    station.max_hull = max(1.0, float(station.max_hull) * hull_factor)
    station.hull = max(0.0, min(station.max_hull, float(station.hull) * hull_factor))
    station.max_shield_quad = max(0.0, float(station.max_shield_quad) * shield_factor)
    station.shield_regen = max(0.0, float(station.shield_regen) * regen_factor)
    for quad in list(station.shields):
        station.shields[quad] = max(0.0, float(station.shields[quad]) * shield_factor)
    state.float_text(station.pos, f'Refit complete · level {target}', (0.6, 1, 0.7))
    state.events.publish('station_upgraded', entity_id=station.id, station=station.data_id,
                         owner=station.owner, level=target)
    return True


def validate_rules(ds) -> None:
    """Refuse a rules file that would make refits unaffordable, instant or free.

    The mirror check `validate_building_catalogue` applies to surface hardware has
    no analogue here — a station's capacity lives on the live entity, so there is no
    catalogue number to contradict — but the tuning itself must be sane.
    """
    cfg = ds.rules.get('station_upgrades', {})
    if not isinstance(cfg, dict):
        raise ValueError('station_upgrades must be an object')
    rules = dict(DEFAULTS, **cfg)
    if max_level(rules) < 2:
        raise ValueError('station_upgrades max_level must be at least 2')
    steps = max_level(rules) - 1
    for key in ('cost_mult', 'time_mult'):
        table = rules.get(key, DEFAULTS[key])
        if not isinstance(table, (list, tuple)) or len(table) < steps:
            raise ValueError(f'station_upgrades {key} needs one entry per level above 1')
        for value in list(table)[:steps]:
            if (type(value) not in (int, float) or not math.isfinite(float(value))
                    or float(value) <= 0):
                raise ValueError(f'station_upgrades {key} entries must be positive numbers')
    for key in ('hull_bonus', 'shield_bonus', 'shield_regen_bonus', 'damage_bonus',
                'production_bonus', 'convoy_cargo_bonus', 'volley_shots_per_level',
                'convoy_per_two_levels'):
        value = rules.get(key, DEFAULTS[key])
        if type(value) not in (int, float) or not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f'station_upgrades {key} must be a non-negative number')
    # The player overlay (#106) is written into this same rules dict by `DataStore`, so a
    # mod that ships one must not be able to hand the simulation a gain the balance screen
    # could never produce. Read with the strict reader, against the ladder just validated.
    overlay = {'version': balance.SCHEMA_VERSION,
               'station_upgrades': ds.rules.get(balance.RULES_KEY) or {},
               'build_levels': ds.rules.get(balance.BUILD_LEVEL_RULES_KEY) or {}}
    if overlay['station_upgrades'] or overlay['build_levels']:
        try:
            balance.validate(overlay, max_level(rules))
        except ValueError as exc:
            raise ValueError(str(exc)) from None
