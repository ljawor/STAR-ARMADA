"""Player-editable station balance (#106): upgrade gains and per-level build gates.

Why the overlay is not a catalogue file: `assets/data/game_rules.json` travels inside
the application bundle, so every update replaces it — the same reason settings and
campaign progress live in the user data directory. This module owns the *schema* of the
writable overlay; `render/menus.py` owns where it is read from and written to.

    {"version": 1,
     "station_upgrades": {"shipyard": {"hull_bonus": 0.15}},
     "build_levels": {"shipyard": {"imperial_battleship": 2}}}

The overlay is folded into the live `DataStore.rules` dict by :func:`merge_into_rules`
rather than consulted beside it: the simulation, the station panel, the replay recorder
and the LAN handshake all read `rules`, so a number that lived anywhere else would be
invisible to some of them and could desync a match without a single error.

Two readings of the same shape, deliberately:

* :func:`normalize` is lenient — a hand-edited file must never stop the game from
  starting; an entry it cannot read is dropped and the shipped value stands.
* :func:`validate` is strict — a config that arrived over the network is rejected
  outright instead of being silently half-applied.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = 1

#: Keys :func:`merge_into_rules` writes into the live rules dict.
RULES_KEY = 'station_balance'
BUILD_LEVEL_RULES_KEY = 'build_levels'

#: Per-level gains a player may retune, in the order the balance screen lists them.
#: Types match `upgrades.DEFAULTS`: fractions of the shipped shape for the first group,
#: whole extra shots / convoys per step for the counted pair.
FRACTION_KEYS = ('hull_bonus', 'shield_bonus', 'shield_regen_bonus', 'damage_bonus',
                 'production_bonus', 'convoy_cargo_bonus')
COUNT_KEYS = ('volley_shots_per_level', 'convoy_per_two_levels')
BONUS_KEYS = FRACTION_KEYS + COUNT_KEYS

#: Which rows a station type actually uses. Every yard hull has hull, shields and
#: regeneration; only an armed one has firepower, and only a collecting one has output,
#: cargo and convoys. `bonus_rows` applies this, so the screen never offers a row the
#: simulation would not read.
BASIC_KEYS = ('hull_bonus', 'shield_bonus', 'shield_regen_bonus')
ARMED_KEYS = ('damage_bonus', 'volley_shots_per_level')
PRODUCER_KEYS = ('production_bonus', 'convoy_cargo_bonus', 'convoy_per_two_levels')

#: Ceilings a config may not cross. Not balance opinion — a guard against a typo or a
#: corrupt file turning a refit into a win button, and against an overflow in a
#: multiplier the tick pipeline reads every frame.
MAX_FRACTION_GAIN = 10.0
MAX_COUNT_GAIN = 100

#: Level 1 is the hull as it leaves the yard, so it is the default gate and is never
#: stored: "buildable from level 1" is the absence of an entry, and resetting a gate is
#: a deletion. The shipped ladder is five levels (`upgrades.max_level`).
DEFAULT_BUILD_LEVEL = 1
DEFAULT_MAX_LEVEL = 5


def defaults() -> dict:
    return {'version': SCHEMA_VERSION, 'station_upgrades': {}, 'build_levels': {}}


# ------------------------------------------------------------------ reading a shape
def _max_level() -> int:
    """The shipped ladder's top level, without constructing a store just to read it."""
    try:
        from ..systems import upgrades
        from .store import DataStore
        store = DataStore._instance
        if store is None:
            return DEFAULT_MAX_LEVEL
        return int(upgrades.max_level(upgrades.upgrade_rules(store)))
    except Exception:
        return DEFAULT_MAX_LEVEL


def _gain(key: str, value):
    """A legal per-level gain, or None. `True` is rejected: it is an int in Python."""
    # Imported here, never at module scope: `game.data.store` imports this module while
    # `game.core` is still initializing, and a top-level detmath import closes that circle.
    from ..core import detmath as math  # deterministic sim math, never the platform libm
    if type(value) is bool or type(value) not in (int, float):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    if key in COUNT_KEYS:
        if number != int(number) or number > MAX_COUNT_GAIN:
            return None
        return int(number)
    return number if number <= MAX_FRACTION_GAIN else None


def _walk(raw, reject, max_level: int) -> dict:
    """One implementation behind both readings; `reject` records or raises."""
    config = defaults()
    if not isinstance(raw, dict):
        reject('config must be an object')
        return config
    version = raw.get('version', SCHEMA_VERSION)
    if type(version) is not int or isinstance(version, bool) or version != SCHEMA_VERSION:
        # A file written by a newer build is not guessed at: unknown sections would be
        # dropped silently and the player would lose settings they can see in the file.
        reject(f'config version {version!r} is not supported')
        return config

    entries = raw.get('station_upgrades', {})
    if not isinstance(entries, dict):
        reject('station_upgrades must be an object')
    else:
        for station_id, gains in entries.items():
            if not isinstance(station_id, str) or not isinstance(gains, dict):
                reject('each station_upgrades entry must be an object keyed by station id')
                continue
            cleaned = {}
            for key, value in gains.items():
                if key not in BONUS_KEYS:
                    reject(f'unknown upgrade gain {key!r} for {station_id or "?"}')
                    continue
                number = _gain(key, value)
                if number is None:
                    reject(f'{station_id}: {key} must be a number from 0 to '
                           f'{MAX_COUNT_GAIN if key in COUNT_KEYS else MAX_FRACTION_GAIN:g}')
                    continue
                cleaned[key] = number
            if cleaned:
                config['station_upgrades'][station_id] = cleaned

    gates = raw.get('build_levels', {})
    if not isinstance(gates, dict):
        reject('build_levels must be an object')
    else:
        for station_id, levels in gates.items():
            if not isinstance(station_id, str) or not isinstance(levels, dict):
                reject('each build_levels entry must be an object keyed by station id')
                continue
            cleaned = {}
            for ship_id, level in levels.items():
                if not isinstance(ship_id, str):
                    reject('build level keys must be ship ids')
                    continue
                if type(level) is not int or isinstance(level, bool) \
                        or not 2 <= level <= max_level:
                    reject(f'{station_id}.{ship_id}: build level must be an integer '
                           f'from 2 to {max_level}')
                    continue
                cleaned[ship_id] = level
            if cleaned:
                config['build_levels'][station_id] = cleaned
    return config


def normalize(raw, max_level: int | None = None) -> dict:
    """Lenient read of a file a player may have hand-edited; bad entries are dropped."""
    return _walk(raw, lambda _message: None, _max_level() if max_level is None else int(max_level))


def validate(raw, max_level: int | None = None) -> dict:
    """Strict read of a config that arrived over the network: raise, never half-apply."""
    def reject(message):
        raise ValueError('station balance: ' + message)
    return _walk(raw, reject, _max_level() if max_level is None else int(max_level))


# --------------------------------------------------------------------- live rules
def merge_into_rules(rules: dict, config) -> None:
    """Fold an overlay into a live rules dict, in place.

    Both sections are always written, even when the overlay is empty: an absent key and
    an empty one must hash identically, or two peers with the same numbers would
    compute different digests and refuse each other's sessions.
    """
    overlay = config if isinstance(config, dict) else {}
    rules[RULES_KEY] = dict(overlay.get('station_upgrades') or {})
    rules[BUILD_LEVEL_RULES_KEY] = dict(overlay.get('build_levels') or {})


def station_overrides(rules, station_id: str) -> dict:
    """Edited gains for one station type; empty when the player has not touched it."""
    entries = (rules or {}).get(RULES_KEY) or {}
    gains = entries.get(station_id) if isinstance(entries, dict) else None
    return gains if isinstance(gains, dict) else {}


def gain(rules, station_id: str, key: str) -> float:
    """The per-level gain in force for a station type: edited when set, shipped else."""
    override = station_overrides(rules, station_id).get(key)
    if override is not None:
        return override
    from ..systems import upgrades
    return upgrades.DEFAULTS[key]


def build_levels(rules, station_id: str) -> dict:
    """Edited build gates for one station type: ship id -> minimum level."""
    entries = (rules or {}).get(BUILD_LEVEL_RULES_KEY) or {}
    levels = entries.get(station_id) if isinstance(entries, dict) else None
    return levels if isinstance(levels, dict) else {}


def build_level(rules, station_id: str, ship_id: str) -> int:
    """Minimum refit level a station type needs before it may lay this hull down."""
    level = build_levels(rules, station_id).get(ship_id)
    return level if type(level) is int and level >= DEFAULT_BUILD_LEVEL else DEFAULT_BUILD_LEVEL


def is_default(config) -> bool:
    """True when nothing is tuned, so the screen can say so and hide a reset action."""
    clean = normalize(config)
    return not clean['station_upgrades'] and not clean['build_levels']


#: The overlay every new catalogue picks up. Empty until the UI reads the player's file.
_active: dict | None = None


def active() -> dict:
    """The overlay the running game is using; shipped values when nothing is loaded.

    A process-wide default rather than an argument at every construction site: four places
    build a DataStore — startup, a match, a replay load and replay validation — and all four
    must see the same numbers, or a replay recorded with a tuned station would be refused on
    the very machine that recorded it. A LAN client, adopting the host's numbers for one
    match, passes an explicit overlay instead and leaves this alone.
    """
    return _active if _active is not None else defaults()


def set_active(config) -> dict:
    """Install (or clear, with None) the overlay every later DataStore picks up."""
    global _active
    _active = normalize(config) if config is not None else defaults()
    return _active


def digest(config) -> str:
    """Stable identity of an overlay, for the LAN handshake and for diagnostics."""
    payload = json.dumps(normalize(config), sort_keys=True, separators=(',', ':'),
                         allow_nan=False)
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


# ------------------------------------------------------------------ the catalogue
def faction_station_types(ds, faction_id: str) -> tuple[str, ...]:
    """Station types a faction can lay down, in catalogue order.

    Station hulls are faction-agnostic; what a faction *has* is the union of its
    builders' `can_build_stations` — the same list the constructor's build panel
    expands, so the balance screen and the game agree on which stations exist.
    """
    from ..systems import upgrades
    allowed = set()
    for ship in ds.ships.values():
        if ship.faction == faction_id:
            allowed.update(getattr(ship, 'can_build_stations', ()) or ())
    return tuple(station_id for station_id in ds.stations
                 if station_id in allowed and station_id not in upgrades.EXCLUDED)


def bonus_rows(ds, station_id: str) -> tuple[str, ...]:
    """The gains this station type actually uses, in the order the screen lists them."""
    from ..systems import upgrades
    rows = list(BASIC_KEYS)
    if upgrades.type_is_armed(ds, station_id):
        rows += list(ARMED_KEYS)
    if upgrades.type_produces(ds, station_id):
        rows += list(PRODUCER_KEYS)
    return tuple(rows)


def editable_ships(ds, station_id: str, faction_id: str) -> tuple[str, ...]:
    """Hulls this station type could be gated to build for this faction.

    The expansion is the simulation's own (`construction.buildable_ship_ids`), never a
    second copy here: a balance screen that offered a ship the sim refuses would be
    worse than no screen.
    """
    from ..systems import construction
    return construction.buildable_ship_ids(ds, station_id, faction_id)
