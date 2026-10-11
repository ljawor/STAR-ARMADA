"""Typed save-shaped replay validation, before constructing or approving a game."""
from dataclasses import is_dataclass
import math
import types
from typing import get_args, get_origin, get_type_hints
from ..core.state import GameState, PlayerState, MapInfo
from ..core.entity import Entity, SubsystemState
from ..core.vectors import Vec3
from ..core.world import Fleet, Projectile
from ..core.commands import PlayerCommand


OVERRIDES = {
    GameState: {'players': dict[int, PlayerState], 'entities': dict[int, Entity],
                'fleets': dict[int, Fleet], 'projectiles': list[Projectile],
                'command_queue': list[PlayerCommand],
                'explored_cells': dict[int, list[tuple[int, int]]],
                'discovered_planets': dict[int, dict[int, Entity]]},
    PlayerState: {'researched': list[str], 'researching': dict[str, dict],
                  'color': tuple[float, float, float]},
    Entity: {'systems': dict[str, SubsystemState], 'shields': dict[str, float],
             'weapon_cooldowns': dict[int, float], 'ability_cooldowns': dict[str, float],
             'ability_active': dict[str, float], 'build_queue': list[dict]},
    Fleet: {'member_ids': list[int], 'rally_point': tuple[float, float, float] | None},
    Projectile: {'color': tuple[float, float, float]},
    MapInfo: {'nebulas': list[dict], 'jump_points': list[dict]},
}


def require(ok, path):
    if not ok:
        raise ValueError('Replay initial state schema: ' + path)


def typed(value, hint, path):
    origin, args = get_origin(hint), get_args(hint)
    if origin is types.UnionType:
        for option in args:
            try:
                typed(value, option, path)
                return
            except ValueError:
                pass
        require(False, path)
    base = origin or hint
    if base is float:
        require(type(value) in (int, float) and math.isfinite(value), path)
    elif base is Vec3:
        typed(value, tuple[float, float, float], path)
    elif is_dataclass(base):
        require(type(value) is dict, path)
        hints = get_type_hints(base, localns={'MissionSystem': object, 'SensorQueries': object})
        for key, item in value.items():
            if base is GameState and key == 'format':
                require(type(item) is int and item in (1, 2, 3), path + '.format')
                continue
            require(key in hints and not key.startswith('_'), path + '.' + str(key))
            typed(item, OVERRIDES.get(base, {}).get(key, hints[key]), path + '.' + key)
    elif base in (list, tuple, set):
        require(type(value) in (list, tuple), path)
        if args:
            if base is tuple and args[-1] is not Ellipsis:
                require(len(value) == len(args), path)
                for i, (item, expected) in enumerate(zip(value, args)):
                    typed(item, expected, path + f'[{i}]')
            else:
                for i, item in enumerate(value):
                    typed(item, args[0], path + f'[{i}]')
    elif base is dict:
        require(type(value) is dict, path)
        if args:
            seen = set()
            for key, item in value.items():
                if args[0] is int and type(key) is str:
                    require(key.isdecimal() and str(int(key)) == key, path + '.key')
                    key = int(key)
                typed(key, args[0], path + '.key')
                require(key not in seen, path + '.duplicate key')
                seen.add(key)
                typed(item, args[1], path + f'[{key}]')
    else:
        require(type(value) is base, path)


def validate_state(initial):
    typed(initial, GameState, 'state')
    require(initial.get('time', 0) >= 0 and initial.get('visibility_cell_size', 500) > 0,
            'time/cell size')
    for name in ('players', 'entities', 'fleets'):
        for key, record in initial.get(name, {}).items():
            require(record.get('id') == int(key), name + '.identity')
    map_info = initial.get('map_info', {})
    require(map_info.get('bounds', 24000) > 0, 'map.bounds')
    for feature in map_info.get('nebulas', []):
        typed(feature.get('pos'), Vec3, 'nebula.pos')
        typed(feature.get('radius'), float, 'nebula.radius')
    for feature in map_info.get('jump_points', []):
        typed(feature.get('pos'), Vec3, 'jump_point.pos')
    validate_payloads(initial)


def payload(value, schema, required, path):
    require(type(value) is dict and not set(value) - schema.keys() and required <= value.keys(), path)
    for key, item in value.items():
        typed(item, schema[key], path + '.' + key)


def validate_payloads(initial):
    for player in initial.get('players', {}).values():
        for record in player.get('researching', {}).values():
            payload(record, {'station_id': int, 'time_left': float, 'total': float},
                    {'station_id', 'time_left', 'total'}, 'research')
    for record in initial.get('stats', {}).values():
        payload(record, {'kills': int, 'losses': int, 'credits_spent': float},
                {'kills', 'losses'}, 'stats')
    for entity in initial.get('entities', {}).values():
        for record in entity.get('build_queue', []):
            payload(record, {'kind': str, 'item': str, 'time_left': float, 'total': float,
                             'status': str, 'pos': tuple[float, float, float], 'planet_id': int,
                             'source_owner': int, 'target_owner': int | None, 'slot': int},
                    {'kind', 'item', 'time_left', 'total'}, 'build_queue')
            require(record['kind'] in ('ship', 'station', 'satellite', 'colonize'), 'build_queue.kind')
            if record['kind'] in ('station', 'satellite'):
                require('pos' in record, 'build_queue.pos')
            if record['kind'] == 'colonize':
                require('planet_id' in record, 'build_queue.planet_id')
        boarding = entity.get('boarding', {})
        if boarding:
            payload(boarding, {'source': int, 'target': int, 'target_owner': int,
                               'phase': str, 'progress': float, 'party_loss': float, 'defender_loss': float},
                    {'source', 'target', 'target_owner', 'phase', 'progress'}, 'boarding')
            require(boarding['phase'] in ('transit', 'control', 'combat', 'return'), 'boarding.phase')
        crew = entity.get('crew_mission', {})
        if crew:
            payload(crew, {'owner': int, 'target': int | None, 'phase': str,
                           'progress': float, 'reason': str},
                    {'owner', 'target', 'phase', 'progress'}, 'crew_mission')
            require(crew['phase'] in ('load', 'deliver', 'recover'), 'crew_mission.phase')


OBJECTIVE_TYPES = {'build_station', 'build_ship', 'destroy_all_forces', 'colonize_planet',
                   'survive_time', 'hold_point', 'escort_convoy', 'capture_unit', 'recover_crew'}
OBJECTIVE_FIELDS = {
    'id': str, 'type': str, 'text': str, 'ship': str, 'station': str,
    'planet': str, 'method': str, 'team': int, 'entity_id': int,
    'count': int, 'time': float, 'duration': float, 'radius': float,
    'active': bool, 'done': bool, 'failed': bool, 'count_done': int,
    'held': float, 'recovered_id': int,
}


def validate_mission(saved, ds):
    if saved is None:
        return
    require(type(saved) is dict and not set(saved) -
            {'definition', 'objectives', 'completed', 'failed', 'escorted_id', 'script'}, 'mission')
    definition = saved.get('definition')
    require(type(definition) is dict, 'mission.definition')
    for key in ('id', 'name', 'map', 'player_faction', 'briefing'):
        if key in definition:
            typed(definition[key], str, 'mission.definition.' + key)
    objectives = definition.get('objectives', [])
    require(type(objectives) is list, 'mission.definition.objectives')

    def objective(record, progress=False):
        require(type(record) is dict and record.get('type') in OBJECTIVE_TYPES, 'mission.objective.type')
        for key, value in record.items():
            if key == 'pos':
                require(type(value) in (list, tuple) and len(value) in (2, 3), 'mission.objective.pos')
                for coordinate in value:
                    typed(coordinate, float, 'mission.objective.pos')
            else:
                require(key in OBJECTIVE_FIELDS, 'mission.objective.' + str(key))
                typed(value, OBJECTIVE_FIELDS[key], 'mission.objective.' + key)
                if key in ('count', 'time', 'duration', 'radius', 'count_done', 'held', 'entity_id', 'recovered_id'):
                    require(value >= (1 if key == 'count' else 0), 'mission.objective.' + key)
        if progress:
            require(type(record.get('done')) is bool, 'mission.objective.done')
        if record['type'] == 'hold_point':
            require('pos' in record, 'mission.objective.pos')
        if 'ship' in record:
            require(record['ship'] in ds.ships, 'mission.objective.ship')
        if 'station' in record:
            require(record['station'] in ds.stations, 'mission.objective.station')

    for record in objectives:
        objective(record)
    progress = saved.get('objectives', [dict(o, done=False) for o in objectives])
    require(type(progress) is list and len(progress) == len(objectives), 'mission.objectives')
    mutable = {'active', 'done', 'failed', 'count_done', 'held', 'recovered_id'}
    for original, record in zip(objectives, progress):
        objective(record, progress=True)
        require({k: v for k, v in record.items() if k not in mutable} ==
                {k: v for k, v in original.items() if k not in mutable}, 'mission.objective identity')
    for key in ('completed', 'failed'):
        typed(saved.get(key, False), bool, 'mission.' + key)
    require(not (saved.get('completed') and saved.get('failed')), 'mission terminal flags')
    typed(saved.get('escorted_id'), int | None, 'mission.escorted_id')
    for key in ('loadout', 'enemy'):
        value = definition.get(key, {})
        require(type(value) is dict, 'mission.' + key)
        if 'start_units' in value:
            typed(value['start_units'], dict[str, int], 'mission.start_units')
            require(all(n >= 0 for n in value['start_units'].values()), 'mission.start_units')
        if 'resources' in value:
            typed(value['resources'], dict[str, float], 'mission.resources')
        if 'team' in value:
            typed(value['team'], int, 'mission.team')
        if 'faction' in value:
            typed(value['faction'], str, 'mission.faction')
    # Validate script conditions/actions against catalogue and objective IDs.
    from ..systems.campaign_validation import validate_campaign
    validate_campaign(definition, ds)
    script = saved.get('script', {'fired': [], 'spawned': {}, 'events': {}})
    require(type(script) is dict and set(script) == {'fired', 'spawned', 'events'}, 'mission.script')
    typed(script['fired'], list[str], 'mission.script.fired')
    typed(script['spawned'], dict[str, list[int]], 'mission.script.spawned')
    typed(script['events'], dict[str, bool], 'mission.script.events')
    triggers = {t['id']: t for t in definition.get('triggers', [])}
    require(len(script['fired']) == len(set(script['fired'])) and
            set(script['fired']) <= triggers.keys(), 'mission.script.fired IDs')
    require(set(script['spawned']) <= set(script['fired']) and
            all(i >= 0 for ids in script['spawned'].values() for i in ids), 'mission.script.spawned IDs')
    require(set(script['events']) <= {key for key, trigger in triggers.items()
                                    if 'event' in trigger['when']}, 'mission.script.event IDs')


def reconstruct(initial, mods=None):
    """A controlled ValueError boundary, independent of any UI catch-all."""
    from copy import deepcopy
    from ..core.manager import GameManager
    try:
        validate_state(initial)
        from ..data.store import DataStore
        ds = DataStore(mods=mods or None)
        validate_mission(initial.get('mission_state'), ds)
        manager = GameManager(state=GameState.from_dict(deepcopy(initial), sanitize_save=False), mods=mods or None)
        # Save loading may cancel historical bad jump intent. Replay approval
        # instead rejects it, on the reconstructed canonical graph before ticks.
        from ..systems.jump import jump_destination, jump_footprint_valid
        for entity in manager.state.entities.values():
            if entity.alive and entity.jump_charge > 0:
                target = jump_destination(manager.state, entity.owner, entity.jump_target)
                require(target is not None and
                        jump_footprint_valid(manager.state, entity.owner, target, entity.radius),
                        'jump destination/footprint')
        if initial.get('runtime_state') is not None:
            import json
            visible = json.loads(json.dumps(manager.state.to_dict(precise=True)))
            source = json.loads(json.dumps(initial))
            for key, value in source.items():
                if key not in ('runtime_state', 'mission_state'):
                    require(visible.get(key) == value, 'future-state disagrees with ' + key)
        return manager
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        raise ValueError('Replay initial state cannot be reconstructed: ' + str(exc)) from exc
