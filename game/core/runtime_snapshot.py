"""JSON-only future simulation state; shared by saves and replay v2.

Reuse the reconnect whitelist codec, not its skirmish-only mission envelope.
Mission subscriptions/progress are reconstructed by MissionSystem's own schema.
Never serialize manager bindings, event callbacks or visibility caches.
"""
from dataclasses import fields
from typing import get_type_hints


def _codec():
    # Lazy import avoids manager/reconnect construction cycles.
    from game.net import reconnect
    return reconnect


def _names():
    from .state import GameState
    return {f.name for f in fields(GameState) if not f.name.startswith('_')
            and f.name not in {'grid', 'events', 'dmg_system', 'effects', 'floating_texts',
                               'runtime_state', 'mission_state'}}


def capture_runtime(manager):
    codec = _codec()
    state = {name: getattr(manager.state, name) for name in sorted(_names())}
    return dict(version=1, state=codec._encode(state),
                ai=codec._encode({pid: codec._attributes(ai) for pid, ai in manager.ai.ais.items()}),
                timers={name: getattr(getattr(manager, name), attr)
                        for name, attr in (('trading', '_timer'), ('squadrons', '_tactical_timer'),
                                           ('victory', '_timer'))})


def repair_saved_jump(entity):
    """Cancel numeric nonfinite jump intent in saves, never other state.

    Finite geometry/capability failures still use the manager's authoritative
    completion guard. Valid intent, AI, timers and pending work stay exact.
    """
    from game.core import detmath as math  # deterministic sim math, never the platform libm
    from ..systems.jump import clear_jump_orders
    values = [entity.jump_charge]
    if entity.jump_target is not None:
        values.extend((entity.jump_target.x, entity.jump_target.y, entity.jump_target.z))
    if any(type(v) is float and not math.isfinite(v) for v in values):
        entity.jump_charge = 0.0
        entity.jump_target = None
        clear_jump_orders(entity)


def migrate_saved_runtime(data):
    """Repair only the historical numeric invalid-jump save contract.

    This is NOT a replay/reconnect decoder. Replace nonfinite jump numbers
    temporarily, validate the entire Entity before cancelling its intent, and
    leave all other schema checks to the strict graph decoder. Never catch and
    discard a graph or rebuild its AI from the compatibility projection.
    """
    from game.core import detmath as math  # deterministic sim math, never the platform libm
    from copy import deepcopy
    codec = _codec()
    result = deepcopy(data)
    if type(result) is not dict:
        return result  # Strict decode will reject the original malformed schema.
    root = result.get('state')
    if type(root) is not list or len(root) != 2 or root[0] != 'dict' or type(root[1]) is not list:
        return result
    for pair in root[1]:
        if type(pair) is not list or len(pair) != 2 or pair[0] != ['scalar', 'entities']:
            continue
        entities = pair[1]
        if (type(entities) is not list or len(entities) != 2 or entities[0] != 'dict'
                or type(entities[1]) is not list):
            continue
        for entry in entities[1]:
            if type(entry) is not list or len(entry) != 2:
                continue
            node = entry[1]
            if (type(node) is not list or len(node) != 3 or node[:2] != ['object', 'Entity']
                    or type(node[2]) is not dict):
                continue
            attributes = node[2]
            numbers = [attributes.get('jump_charge')]
            target = attributes.get('jump_target')
            if (type(target) is list and len(target) == 3 and target[:2] == ['object', 'Vec3']
                    and type(target[2]) is dict):
                numbers.extend(target[2].values())
            changed = False
            for number in numbers:
                if (type(number) is list and len(number) == 2 and number[0] == 'scalar'
                        and type(number[1]) is float and not math.isfinite(number[1])):
                    number[1] = 0.0
                    changed = True
            if changed:
                # Validate even stale order fields BEFORE clearing them; corruption
                # outside numeric jump intent is still a hard error.
                entity = codec._decode(node)
                from ..systems.jump import clear_jump_orders
                entity.jump_charge = 0.0
                entity.jump_target = None
                clear_jump_orders(entity)
                entry[1] = codec._encode(entity)
    return result


def decode_runtime(data, manager):
    from .state import GameState
    from ..ai.ai import AIPlayer
    codec = _codec()
    if (type(data) is not dict or set(data) != {'version', 'state', 'ai', 'timers'}
            or type(data['version']) is not int or data['version'] != 1):
        raise ValueError('Invalid future-state schema')
    budget = [codec.MAX_DECODE_NODES]
    state = codec._decode(data['state'], _budget=budget)
    brains = codec._decode(data['ai'], _budget=budget)
    if type(state) is not dict or set(state) != _names():
        raise ValueError('Invalid future-state fields')
    hints = get_type_hints(GameState, localns={'MissionSystem': object, 'SensorQueries': object})
    for name, value in state.items():
        codec._validate_type(value, codec._CONTAINER_TYPES[GameState].get(name, hints[name]))
    for name in ('entities', 'projectiles', 'players', 'fleets'):
        if any(k != v.id for k, v in state[name].items()):
            raise ValueError('Invalid future-state identity')
    expected = {pid for pid, player in state['players'].items() if player.is_ai}
    if type(brains) is not dict or set(brains) - expected:
        raise ValueError('Invalid future-state AI ownership')
    # A manually constructed graph can intentionally have no brains yet, even
    # at a nonzero tick. Preserve that lazy state rather than inventing brains.
    for pid, attributes in brains.items():
        template = codec._attributes(AIPlayer(manager.state, pid))
        if type(attributes) is not dict or set(attributes) != set(template):
            raise ValueError('Invalid future-state AI fields')
        for name, hint in {'player_id': int, 'decision_timer': float, 'tactical_timer': float,
                           'last_strategic': dict, '_pending_site': dict[int, tuple[str, codec.Vec3]]}.items():
            codec._validate_type(attributes[name], hint)
        if set(attributes['last_strategic']) != {'attack_fleet_id'}:
            raise ValueError('Invalid future-state AI strategy')
        codec._validate_type(attributes['last_strategic']['attack_fleet_id'], int | None)
        if attributes['player_id'] != pid:
            raise ValueError('Invalid future-state AI player')
    timers = data['timers']
    if type(timers) is not dict or set(timers) != {'trading', 'squadrons', 'victory'}:
        raise ValueError('Invalid future-state timers')
    for value in timers.values():
        codec._validate_type(value, float)
        if value < 0:
            raise ValueError('Invalid future-state timer')
    # Validate formerly untyped runtime dictionaries with the same save-shaped
    # schema; a tagged canonical object is not permission to skip its payload.
    detached = GameState()
    for name, value in state.items():
        setattr(detached, name, value)
    from ..net.replay_validation import validate_state
    validate_state(detached.to_dict(precise=True))
    return state, brains, timers


def restore_runtime(manager, data):
    from ..ai.ai import AIPlayer
    state, brains, timers = decode_runtime(data, manager)
    # Install only after the complete detached graph has passed validation.
    for name, value in state.items():
        setattr(manager.state, name, value)
    manager.state.grid.rebuild(manager.state.entities)
    for pid, attributes in brains.items():
        brain = AIPlayer(manager.state, pid)
        vars(brain).update(attributes)
        manager.ai.ais[pid] = brain
    for name, attr in (('trading', '_timer'), ('squadrons', '_tactical_timer'), ('victory', '_timer')):
        setattr(getattr(manager, name), attr, timers[name])
