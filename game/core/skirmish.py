"""Pure menu-options to map-definition conversion; no simulation mutations."""
from __future__ import annotations

from copy import deepcopy
import math


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False

PLAYER_COLORS = {
    "blue": (0.25, 0.55, 1.0),
    "red": (1.0, 0.25, 0.20),
    "green": (0.25, 0.85, 0.35),
    "purple": (0.65, 0.35, 1.0),
    "orange": (1.0, 0.55, 0.15),
    "cyan": (0.15, 0.90, 0.95),
    "yellow": (1.0, 0.90, 0.20),
    "pink": (1.0, 0.35, 0.70),
}
COLOR_NAMES = {key: key.title() for key in PLAYER_COLORS}
SKIRMISH_MAP_IDS = ("skirmish01", "skirmish02", "skirmish03", "skirmish04")


def default_skirmish_options(ds) -> dict:
    """Return independent, four-slot menu defaults (only active slots matter)."""
    return {"map_id": "skirmish01", "ai_count": 1,
            "colors": list(PLAYER_COLORS)[:4], "factions": ["imperial"] * 4,
            "ai_difficulty": "normal"}


def build_skirmish_map(ds, options: dict) -> dict:
    """Return a validated private map; reject malformed input with ValueError.

    Require four choice slots, validate only active choices, and never coerce
    counts/IDs. All map slots/spawns are validated before any simulation starts.
    """
    required = {'map_id', 'ai_count', 'colors', 'factions', 'ai_difficulty'}
    if not isinstance(options, dict) or not required <= options.keys():
        raise ValueError('Skirmish options require map_id, ai_count, colors, factions and ai_difficulty')
    map_id = options['map_id']
    if not isinstance(map_id, str) or map_id not in SKIRMISH_MAP_IDS or map_id not in ds.maps:
        raise ValueError('Unknown or unavailable skirmish map')
    ai_count = options['ai_count']
    if type(ai_count) is not int or not 1 <= ai_count <= 3:
        raise ValueError('AI count must be an integer from 1 to 3')
    difficulty = options['ai_difficulty']
    if (not isinstance(difficulty, str) or difficulty not in ('easy', 'normal', 'hard')
            or difficulty not in ds.rules.get('ai', {}).get('difficulty', {})):
        raise ValueError('Unsupported AI difficulty')
    active = ai_count + 1
    for key in ('colors', 'factions'):
        if not isinstance(options[key], list) or len(options[key]) != 4:
            raise ValueError(f'{key} must be a four-slot list')
    colors = options['colors'][:active]
    if any(not isinstance(c, str) or c not in PLAYER_COLORS for c in colors):
        raise ValueError('Unknown active player color')
    if len(set(colors)) != active:
        raise ValueError('Active player colors must be distinct')
    if any(not isinstance(f, str) or f not in ds.factions for f in options['factions'][:active]):
        raise ValueError('Unknown active player faction')
    source = ds.maps[map_id]
    if not isinstance(source, dict) or source.get('id') != map_id:
        raise ValueError('Skirmish map identity mismatch')
    bounds = source.get('bounds')
    if not isinstance(bounds, (int, float)) or not _finite_number(bounds) or bounds <= 0:
        raise ValueError('Map bounds must be finite and positive')
    players = source.get('players')
    if not isinstance(players, list) or not 2 <= len(players) <= 4 or active > len(players):
        raise ValueError('Selected AI count exceeds map capacity')
    spawns = set()
    kinds = set(ds.stations) | {'constructor', 'colonizer', 'squadron', 'corvette',
                              'frigate', 'cruiser', 'battleship', 'supercapital'}
    for slot, player in enumerate(players):
        if (not isinstance(player, dict) or type(player.get('slot')) is not int
                or player['slot'] != slot):
            raise ValueError('Map slots must be ordered consecutive integers starting at zero')
        start = player.get('start')
        if (not isinstance(start, (list, tuple)) or len(start) != 3
                or any(not _finite_number(x) or abs(x) > bounds / 2 for x in start)):
            raise ValueError('Map spawn must be a finite in-bounds coordinate triple')
        # Starting stations share the XZ plane, regardless of the input Y.
        spawn = (start[0], start[2])
        if spawn in spawns:
            raise ValueError('Map spawns must be distinct')
        spawns.add(spawn)
        units = player.get('start_units')
        if (not isinstance(units, dict)
                or any(k not in kinds or type(n) is not int or n < 0 for k, n in units.items())):
            raise ValueError('Invalid map starting unit loadout')
    result = deepcopy(source)
    result["players"] = result["players"][:options["ai_count"] + 1]
    for slot, player in enumerate(result["players"]):
        faction = options["factions"][slot]
        player.update(slot=slot, team=slot, is_ai=slot > 0, faction=faction,
                      name=f"{'Player' if slot == 0 else f'AI {slot}'} — {ds.factions[faction].display_name}",
                      color=PLAYER_COLORS[options["colors"][slot]],
                      ai_difficulty=options["ai_difficulty"])
    return result
