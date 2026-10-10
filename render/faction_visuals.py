"""Pure, finite render identities; ownership paint is deliberately separate.

Catalogue identity wins for ships (including captured ships). Shared stations
and catalogue-less commercial convoys use their owner's faction. Unknown mods
and neutral owners keep the protected Imperial fallback.
"""
FACTIONS = ('imperial', 'rebel', 'confederacy', 'syndicate')
SHIP_ROLES = ('fighter', 'bomber', 'corvette', 'frigate', 'cruiser',
              'battleship', 'supercapital', 'constructor', 'colonizer', 'convoy')
LEGACY_SHAPES = ('wedge', 'needle', 'cruiser', 'dagger', 'box')
SHIP_KEYS = LEGACY_SHAPES + tuple(f + ':' + r for f in FACTIONS[1:] for r in SHIP_ROLES)
KNOWN_SHIP_IDS = frozenset(
    prefix + '_' + suffix
    for prefix, suffixes in (
        ('imperial', ('tie_squadron', 'tie_bomber_squadron', 'corvette', 'frigate', 'cruiser',
                      'battleship', 'supercapital', 'constructor', 'colonizer')),
        ('rebel', ('x_squadron', 'y_squadron', 'corvette', 'frigate', 'cruiser',
                   'battleship', 'supercapital', 'constructor', 'colonizer')),
        ('confed', ('vulture_squadron', 'bomber_squadron', 'corvette', 'frigate', 'cruiser',
                    'battleship', 'supercapital', 'constructor', 'colonizer')),
        ('syndicate', ('raid_squadron', 'corvette', 'frigate', 'cruiser', 'constructor')))
    for suffix in suffixes)
STATION_TYPES = ('command_station', 'shipyard', 'research_station', 'defense_platform',
                 'mining_station', 'sensor_station', 'trade_station', 'fighter_platform',
                 'repair_dock', 'energy_relay')


def owner_faction(state, owner):
    player = getattr(state, 'players', {}).get(owner)
    faction = getattr(player, 'faction', 'imperial')
    return faction if faction in FACTIONS else 'imperial'


def normalize_ship_key(key):
    return key if isinstance(key, str) and key in SHIP_KEYS else 'box'


def normalize_station_key(data_id, faction='imperial'):
    if data_id not in STATION_TYPES:
        return 'imperial', 'research_station'
    return (faction if faction in FACTIONS else 'imperial'), data_id


def ship_visual_key(ds, data_id, faction=None):
    data = ds.ships.get(data_id)
    if data is None:
        if data_id == 'trade_convoy' and faction in FACTIONS[1:]:
            return faction + ':convoy'
        return normalize_ship_key(ds.ship_visual(data_id)['shape'])
    if data.category == 'crew_transport' and data.crew_capacity > 0:
        return data.faction + ':convoy' if data.faction in FACTIONS[1:] else 'box'
    if data_id not in KNOWN_SHIP_IDS or data.faction not in FACTIONS[1:]:
        return normalize_ship_key(ds.ship_visual(data_id)['shape'])
    role = data.category
    if role == 'fighter_squadron':
        role = 'bomber' if ('bomber' in data_id or data_id == 'rebel_y_squadron') else 'fighter'
    elif role == 'construction':
        role = 'colonizer' if data_id.endswith('_colonizer') else 'constructor'
    if role not in SHIP_ROLES:
        return normalize_ship_key(ds.ship_visual(data_id)['shape'])
    return data.faction + ':' + role
