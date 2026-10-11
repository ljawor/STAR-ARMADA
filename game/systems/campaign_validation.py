"""Strict validation for the opt-in deterministic campaign script format."""
import math


def validate_campaign(mission, ds):
    def require(condition, reason):
        if not condition:
            raise ValueError('campaign: ' + reason)

    def number(value):
        return type(value) in (float, int) and math.isfinite(value)

    objectives = mission.get('objectives', [])
    ids = [o['id'] for o in objectives if 'id' in o]
    require(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)),
            'objective ids must be unique nonempty strings')
    for o in objectives:
        if 'active' in o:
            require(type(o['active']) is bool, 'active must be boolean')
        if o['type'] in ('capture_unit', 'recover_crew'):
            require(type(o.get('count', 1)) is int and o.get('count', 1) > 0, 'positive objective count')
            require(o.get('ship') is None or o['ship'] in ds.ships, 'unknown objective ship')
            require(o.get('method') in (None, 'crew_delivered', 'crew_replenished'), 'unknown recovery method')
    triggers = mission.get('triggers', [])
    require(isinstance(triggers, list), 'triggers must be a list')
    seen = set()
    for trigger in triggers:
        require(isinstance(trigger, dict), 'trigger must be an object')
        key = trigger.get('id')
        require(isinstance(key, str) and key and key not in seen, 'unique trigger id required')
        seen.add(key)
        require(type(trigger.get('required', True)) is bool, 'required must be boolean')
        when = trigger.get('when')
        require(isinstance(when, dict) and bool(when) and not set(when) -
                {'tick', 'time', 'event', 'match', 'objective'}, 'unknown/empty trigger condition')
        if 'tick' in when:
            require(type(when['tick']) is int and when['tick'] >= 0, 'tick must be nonnegative integer')
        if 'time' in when:
            require(number(when['time']) and when['time'] >= 0, 'time must be finite nonnegative')
        if 'objective' in when:
            require(when['objective'] in ids, 'unknown objective gate')
        if 'event' in when:
            require(isinstance(when['event'], str) and bool(when['event']), 'event name required')
        if 'match' in when:
            require('event' in when and isinstance(when['match'], dict), 'match needs event')
        actions = trigger.get('actions')
        require(isinstance(actions, list) and bool(actions), 'actions required')
        for action in actions:
            require(isinstance(action, dict), 'action must be an object')
            kind = action.get('type')
            require(kind in ('reinforcements', 'activate_objective', 'complete_objective', 'fail_mission'),
                    'unknown action')
            if kind in ('activate_objective', 'complete_objective'):
                require(action.get('objective') in ids, 'unknown action objective')
            if kind == 'reinforcements':
                units = action.get('units')
                require(isinstance(units, list) and bool(units), 'reinforcement units required')
                for unit in units:
                    require(isinstance(unit, dict), 'unit must be an object')
                    require(unit.get('ship') in ds.ships, 'unknown reinforcement ship')
                    require(type(unit.get('owner')) is int and unit['owner'] >= 0, 'nonnegative owner id')
                    pos = unit.get('pos')
                    require(isinstance(pos, list) and len(pos) == 3 and all(number(v) for v in pos),
                            'finite xyz position required')
                    if 'crew' in unit:
                        require(type(unit['crew']) is int and 0 <= unit['crew'] <= ds.ships[unit['ship']].crew_cost,
                                'crew must fit the ship complement')
                    require(type(unit.get('shields_down', False)) is bool, 'shields_down must be boolean')
                    require(not set(unit) - {'ship', 'owner', 'pos', 'crew', 'shields_down'},
                            'unknown reinforcement field')
