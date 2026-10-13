"""Deterministic physical boarding craft and capture; intent enters via commands."""
from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.entity import Entity, SubsystemState
from ..data.store import DataStore

DEFAULTS = {
    'life_support_loss_per_second': 1.0,
    'life_support_failure_fraction': .25,
    'range': 500.0,
    'party_fraction': .25,
    'craft_speed': 180.0,
    'craft_hull': 80.0,
    'control_seconds': 5.0,
    'resistance_seconds': 20.0,
    'combat_losses_per_second': 1.0,
    'capable_categories': ['frigate', 'cruiser', 'battleship', 'supercapital'],
}


def boarding_rules():
    return dict(DEFAULTS, **DataStore.get().rules.get('boarding', {}))


def validate_boarding_rules(rules):
    cfg = rules.get('boarding', {})
    if not isinstance(cfg, dict):
        raise ValueError('boarding rules must be an object')
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if key == 'capable_categories':
            if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
                raise ValueError('boarding capable_categories must be a list of category names')
        elif type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'boarding {key} must be finite and positive')
        elif key == 'party_fraction' and value > .5:
            raise ValueError('boarding party_fraction must not exceed 0.5')
        elif key == 'life_support_failure_fraction' and value > 1:
            raise ValueError('boarding life_support_failure_fraction must not exceed 1')


def boarding_capable(e):
    sd = DataStore.get().ships.get(e.data_id)
    return bool(e.operational and e.is_ship and not e.is_station and not e.is_squadron
                and not e.is_planet and sd and sd.category in boarding_rules()['capable_categories'])


def boarding_reason(state, source, target, *, ongoing=False):
    """Shared read-only UI preview; authoritative execution always rechecks."""
    if not boarding_capable(source):
        return 'ship cannot board'
    if not ongoing and source.crew < 2:
        return 'needs at least two onboard crew'
    if not ongoing and any(e.alive and e.boarding.get('source') == source.id
                           for e in state.entities.values()):
        return 'boarding party already deployed'
    if source.jump_charge > 0:
        return 'source is jumping'
    if target is None or not state.can_see(source.owner, target.id):
        return 'target not currently detected'
    if target.planet_id is not None or target.data_id in ('defense_satellite', 'attack_satellite'):
        return 'planetary satellites must be destroyed, not boarded'
    if (not target.alive or target.is_planet or target.boarding
            or not (target.is_ship or target.is_squadron or target.is_station)):
        return 'target is not a capturable hull'
    if not state.is_enemy(source.owner, target.owner):
        return 'target must be an enemy'
    if source.pos.dist(target.pos) > source.radius + target.radius + boarding_rules()['range']:
        return 'target out of boarding range'
    if target.total_shield() > 0:
        return 'lower all target shields'
    return ''


class BoardingSystem:
    def __init__(self, state):
        self.state = state

    def cancel(self, source):
        for craft in self.state.entities.values():
            if craft.boarding.get('source') == source.id:
                self._return(craft, 'order interrupted')

    def _remove(self, craft):
        source = self.state.entity(craft.boarding['source'])
        if source is not None and source.boarding_party_id == craft.id:
            source.boarding_party_id = None
        self.state.entities.pop(craft.id, None)

    def _return(self, craft, reason):
        if craft.boarding['phase'] != 'return':
            craft.boarding['phase'] = 'return'
            self.state.events.publish('boarding_interrupted', entity_id=craft.id,
                                      owner=craft.owner, reason=reason)
            self.state.float_text(craft.pos, 'BOARDING ABORTED: ' + reason, (1, .6, .4))

    def _travel(self, craft, destination, dt):
        delta = destination.pos - craft.pos
        distance = delta.length()
        docking_distance = 1.2 * (destination.radius + craft.radius)
        if distance <= docking_distance + 1e-6:
            return True
        from .stats import effective_speed
        travel = min(distance - docking_distance, effective_speed(self.state, craft) * dt)
        craft.pos = craft.pos + delta * (travel / distance)
        craft.yaw = math.atan2(delta.x, delta.z)
        return False

    def launch(self, source, target):
        st = self.state
        reason = boarding_reason(st, source, target)
        if reason:
            st.float_text(source.pos, 'Cannot board: ' + reason, (1, .6, .4))
            st.events.publish('boarding_rejected', entity_id=source.id, owner=source.owner, reason=reason)
            return False
        cfg = boarding_rules()
        party = min(source.crew - 1, max(1, int(source.crew * cfg['party_fraction'])))
        if party <= 0:
            return False
        from .jump import clear_jump_orders, detach_jumpers
        from ..core.vectors import Vec3
        detach_jumpers(st, [source])
        clear_jump_orders(source)
        source.order_type = 'hold'
        source.vel = Vec3()
        source.crew -= party
        craft = Entity(st.next_entity_id, 'ship', source.owner, 'boarding_craft',
                       pos=source.pos.copy(), is_ship=True, radius=12.0,
                       hull=cfg['craft_hull'], max_hull=cfg['craft_hull'],
                       crew=party, max_crew=party, name_override='Boarding Craft')
        st.next_entity_id += 1
        craft.systems['life_support'] = SubsystemState(100.0, 100.0)
        craft.boarding = dict(source=source.id, target=target.id,
                              target_owner=target.owner, phase='transit', progress=0.0)
        source.boarding_party_id = craft.id
        st.add_entity(craft)
        st.events.publish('boarding_launched', entity_id=craft.id, owner=source.owner,
                          source=source.id, target=target.id, crew=party)
        st.float_text(source.pos, 'BOARDING CRAFT LAUNCHED', (.7, 1, .8))
        return True

    def update(self, dt):
        st = self.state
        cfg = boarding_rules()
        for craft in sorted(list(st.entities.values()), key=lambda e: e.id):
            if not craft.alive or not craft.boarding:
                continue
            info = craft.boarding
            source = st.entity(info['source'])
            if source is None or source.owner != craft.owner or not source.operational or craft.crew <= 0:
                self._remove(craft)
                st.events.publish('boarding_failed', entity_id=craft.id, owner=craft.owner,
                                  reason='source or party lost')
                continue
            target = st.entity(info['target'])
            if info['phase'] != 'return':
                reason = boarding_reason(st, source, target, ongoing=True)
                if target is not None and target.owner != info['target_owner']:
                    reason = 'target ownership changed'
                if reason:
                    self._return(craft, reason)
            if info['phase'] == 'return':
                if self._travel(craft, source, dt):
                    restored = min(craft.crew, max(0, source.max_crew - source.crew))
                    source.crew += restored
                    # If capacity shrank, evacuate remaining survivors to the pool.
                    st.players[craft.owner].crew += craft.crew - restored
                    self._remove(craft)
                    st.events.publish('boarding_returned', entity_id=craft.id, owner=craft.owner,
                                      source=source.id, crew=craft.crew)
                continue
            if info['phase'] == 'transit':
                if not self._travel(craft, target, dt):
                    continue
                info['phase'] = 'control'
                st.events.publish('boarding_engaged', entity_id=craft.id, target=target.id,
                                  owner=craft.owner)
            defenders, party = target.crew, craft.crew
            if defenders > 0 and party > 0:
                rate = cfg['combat_losses_per_second']
                info['party_loss'] = info.get('party_loss', 0.0) + dt * rate * defenders / party
                info['defender_loss'] = info.get('defender_loss', 0.0) + dt * rate * party / defenders
                lost = min(craft.crew, int(info['party_loss']))
                info['party_loss'] -= lost
                craft.crew -= lost
                lost = min(target.crew, int(info['defender_loss']))
                info['defender_loss'] -= lost
                target.crew -= lost
                if lost and target.crew == 0:
                    from .crew import abandon_unit
                    abandon_unit(st, target)
            if craft.crew <= 0:
                self._remove(craft)
                st.events.publish('boarding_failed', entity_id=craft.id, target=target.id,
                                  owner=craft.owner, reason='party defeated')
                st.float_text(target.pos, 'BOARDING PARTY DEFEATED', (1, .5, .4))
                continue
            resistance = cfg['resistance_seconds'] * target.crew / craft.crew
            info['progress'] += dt / (cfg['control_seconds'] + resistance)
            if info['progress'] >= 1:
                from .jump import clear_jump_orders, detach_jumpers
                from .economy import EconomySystem
                old_owner = target.owner
                detach_jumpers(st, [target])
                clear_jump_orders(target)
                target.build_queue.clear()  # paid work belongs to the old owner; no refund/mint
                target.jump_charge = 0.0
                target.jump_target = None
                target.ability_active.clear()
                target.ability_cooldowns.clear()
                target.hangar_id = target.launched_from = None
                for dependent in st.entities.values():
                    if dependent.owner != old_owner:
                        continue
                    if dependent.hangar_id == target.id:
                        dependent.hangar_id = None
                    if dependent.launched_from == target.id:
                        dependent.launched_from = None
                    if dependent.order_type == 'follow' and dependent.order_target_id == target.id:
                        clear_jump_orders(dependent)
                target.convoy_source = target.convoy_dest = None
                for player in st.players.values():
                    for tid, research in list(player.researching.items()):
                        if research.get('station_id') == target.id:
                            del player.researching[tid]
                target.owner = craft.owner
                support = target.systems.get('life_support')
                if support is not None:
                    support.hp = max(support.hp, support.max_hp * .1)
                target.crew_mission.clear()
                target.recruitment_progress = 0.0
                if st._crew_recovery_system is not None:
                    st._crew_recovery_system.validate()
                target.crew = min(target.max_crew, craft.crew)
                target.crew_loss_accumulator = 0.0
                source = st.entity(info['source'])
                if source is not None:
                    surplus = craft.crew - target.crew
                    restored = min(surplus, max(0, source.max_crew - source.crew))
                    source.crew += restored
                    st.players[craft.owner].crew += surplus - restored
                self._remove(craft)
                EconomySystem.recompute_command_capacity(st)
                st.events.publish('unit_captured', entity_id=target.id, owner=target.owner,
                                  previous_owner=old_owner)
                st.float_text(target.pos, 'CAPTURED', (.6, 1, .7))
