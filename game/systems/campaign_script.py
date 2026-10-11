"""Once-only campaign triggers; clocks belong to the simulation."""
from copy import deepcopy
from ..core.vectors import Vec3
from .unit_factory import UnitFactory


class CampaignScript:
    def __init__(self, mission, saved=None):
        self.mission = mission
        self.state = mission.state
        self.triggers = (mission.mission or {}).get('triggers', [])
        self.progress = deepcopy(saved or {'fired': [], 'spawned': {}, 'events': {}})
        for name in sorted({t['when']['event'] for t in self.triggers if 'event' in t['when']}):
            self.state.events.subscribe(name, self._on_event)

    def _on_event(self, event):
        if self.mission.completed or self.mission.failed:
            return
        for trigger in self.triggers:
            when = trigger['when']
            if (trigger['id'] not in self.progress['fired'] and when.get('event') == event.type
                    and all(event.data.get(k) == v for k, v in when.get('match', {}).items())):
                self.progress['events'][trigger['id']] = True

    @property
    def pending(self):
        return any(t['id'] not in self.progress['fired'] and t.get('required', True)
                   for t in self.triggers)

    def update(self):
        # Definition order is authoritative; objective gates see this pass's earlier actions.
        for trigger in self.triggers:
            key = trigger['id']
            if key in self.progress['fired']:
                continue
            when = trigger['when']
            if 'tick' in when and self.state.tick < when['tick']:
                continue
            if 'time' in when and self.state.time < when['time']:
                continue
            if 'event' in when and not self.progress['events'].get(key):
                continue
            if 'objective' in when and not any(o.get('id') == when['objective'] and o['done']
                                               for o in self.mission.objectives):
                continue
            self.progress['fired'].append(key)
            for action in trigger['actions']:
                kind = action['type']
                if kind == 'reinforcements':
                    factory = UnitFactory(self.state)
                    ids = self.progress['spawned'].setdefault(key, [])
                    for unit in action['units']:
                        entity = factory.spawn_ship(unit['ship'], unit['owner'], Vec3(*unit['pos']))
                        if 'crew' in unit:
                            entity.crew = unit['crew']
                        if unit.get('shields_down'):
                            entity.shields = {q: 0.0 for q in entity.shields}
                            entity.systems['shield_gen'].hp = 0.0
                        ids.append(entity.id)
                elif kind in ('activate_objective', 'complete_objective'):
                    objective = next(o for o in self.mission.objectives if o.get('id') == action['objective'])
                    objective['active' if kind == 'activate_objective' else 'done'] = True
                elif kind == 'fail_mission':
                    self.mission.fail()
                if self.mission.completed or self.mission.failed:
                    return

    def to_dict(self):
        return deepcopy(self.progress)
