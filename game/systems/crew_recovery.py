"""Deterministic personnel logistics; passengers never power a hull."""
from ..data.store import DataStore

DEFAULTS = dict(base_range=600.0, transfer_range=180.0, recruitment_rate=4.0,
                delivery_rate=8.0, credits_per_crew=2.0, support_threshold=.5,
                base_types=['command_station', 'shipyard', 'repair_dock'],
                ai_support_retreat=.65, ai_staffing_retreat=.6, ai_board_ratio=1.5)


def recovery_rules():
    return {**DEFAULTS, **DataStore.get().rules.get('crew_recovery', {})}


def validate_recovery_rules(rules):
    from game.core import detmath as math  # deterministic sim math, never the platform libm
    cfg = rules.get('crew_recovery', {})
    if not isinstance(cfg, dict):
        raise ValueError('crew_recovery rules must be an object')
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if key == 'base_types':
            if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value):
                raise ValueError('crew_recovery base_types must be a nonempty list')
        elif type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'crew_recovery {key} must be finite and positive')
        elif key in ('support_threshold', 'ai_support_retreat', 'ai_staffing_retreat') and value > 1:
            raise ValueError(f'crew_recovery {key} must not exceed 1')


class CrewRecoverySystem:
    def __init__(self, state):
        self.state = state

    def base_for(self, e):
        cfg = recovery_rules()
        bases = [b for b in self.state.entities.values()
                 if b is not e and b.operational and b.is_station
                 and b.data_id in cfg['base_types']
                 and b.owner in self.state.allied_player_ids(e.owner)
                 and e.pos.dist(b.pos) <= b.radius + cfg['base_range']]
        return min(bases, key=lambda b: (e.pos.dist_sq(b.pos), b.id), default=None)

    def repairs_support(self, base, e):
        # Economy repair service is own-only; allied recruitment service does
        # not make an allied dock a usable life-support repair destination.
        sd = DataStore.get().stations.get(base.data_id) if base else None
        from .economy import dock_repairable
        return bool(dock_repairable(e) and base and base.operational and base.owner == e.owner
                    and sd and sd.repair_rate > 0)

    def capacity(self, e):
        sd = DataStore.get().ships.get(e.data_id)
        return sd.crew_capacity if sd and e.is_ship and not e.is_squadron else 0

    def reason(self, e, phase, target=None):
        if phase == 'recover':
            if not e.operational or not e.is_ship or e.boarding or e.jump_charge > 0:
                return 'needs an operating ship'
            if (target is None or not target.operational or not target.is_station
                    or target.data_id not in recovery_rules()['base_types']
                    or target.owner not in self.state.allied_player_ids(e.owner)):
                return 'choose a friendly recovery base'
            return ''
        if not e.operational or not self.capacity(e) or e.boarding:
            return 'needs an operating crew transport'
        if e.jump_charge > 0 or e.jump_target is not None:
            return 'transport is jumping'
        if e.subsystem_fraction('life_support') < recovery_rules()['support_threshold']:
            return 'repair transport life support to 50%'
        if phase == 'load':
            if e.crew_cargo >= self.capacity(e):
                return 'passenger hold full'
            if self.base_for(e) is None:
                return 'move near a friendly base'
        elif phase == 'deliver':
            if e.crew_cargo <= 0:
                return 'no passengers loaded'
            if (target is None or target is e or target.owner != e.owner
                    or target.is_planet or target.boarding
                    or not (target.is_ship or target.is_station or target.is_squadron)):
                return 'choose an owned hull'
            if target.crew >= target.max_crew:
                return 'target complement full'
            if target.subsystem_fraction('life_support') < recovery_rules()['support_threshold']:
                return 'repair target life support to 50%'
        else:
            return 'invalid recovery order'
        return ''

    def status(self, e):
        """Read-only live inspector text; does not trust stale cached reasons."""
        cfg = recovery_rules()
        if e.crew_mission:
            info = e.crew_mission
            target = self.state.entity(info.get('target'))
            reason = self.reason(e, info['phase'], target)
            if not reason:
                reason = info.get('reason') or 'transfer in progress'
                if info['phase'] == 'load':
                    p = self.state.players[e.owner]
                    if p.crew < 1 or p.credits < cfg['credits_per_crew']:
                        reason = 'insufficient unassigned crew or credits'
            return f"CREW {info['phase'].upper()} · next crew {info['progress'] % 1:.0%}", reason
        if e.subsystem_fraction('life_support') < cfg['support_threshold']:
            reason = 'repair life support to 50%'
        elif self.base_for(e) is None:
            reason = 'needs friendly base / ordered transport'
        else:
            p = self.state.players[e.owner]
            reason = ('insufficient unassigned crew or credits' if p.crew < 1 or p.credits < cfg['credits_per_crew']
                      else 'recruiting from own unassigned pool')
        return f'CREW AUTO · next crew {e.recruitment_progress % 1:.0%}', reason

    def cancel(self, e):
        if not e.crew_mission:
            return
        e.crew_mission.clear()
        e.order_type = 'idle'
        e.order_target_id = e.order_target_pos = e.current_target = None
        from ..core.vectors import Vec3
        e.vel = Vec3()

    def start(self, e, phase, target=None):
        reason = self.reason(e, phase, target)
        if reason:
            self.state.float_text(e.pos, 'Crew: ' + reason, (1, .6, .4))
            self.state.events.publish('crew_order_rejected', entity_id=e.id, reason=reason)
            return False
        self.cancel(e)
        from .jump import clear_jump_orders, detach_jumpers
        from ..core.vectors import Vec3
        detach_jumpers(self.state, [e])
        clear_jump_orders(e)
        e.vel = Vec3()
        e.crew_mission = dict(phase=phase, owner=e.owner,
                              target=target.id if target else None, progress=0.0)
        e.order_type = 'hold' if phase == 'load' else 'follow'
        e.order_target_id = target.id if target else None
        return True

    def validate(self):
        # Preflight before movement as well as at transfer: stale targets must
        # not leak enemy coordinates after ownership/destruction transitions.
        for e in sorted(self.state.entities.values(), key=lambda e: e.id):
            info = e.crew_mission
            if not info:
                continue
            target = self.state.entity(info.get('target'))
            if (info.get('owner') != e.owner or not e.operational
                    or info.get('phase') not in ('load', 'deliver', 'recover')
                    or (info.get('phase') == 'deliver' and
                        (target is None or target.owner != e.owner))
                    or (info.get('phase') == 'recover' and self.reason(e, 'recover', target))):
                self.cancel(e)

    def _purchase(self, e, capacity, dt, cfg, progress):
        p = self.state.players[e.owner]
        price = cfg['credits_per_crew']
        if p.crew < 1 or p.credits < price:
            return 0, 0.0
        progress = min(capacity, progress + dt * cfg['recruitment_rate'])
        count = min(int(progress), capacity, int(p.crew), int(p.credits / price))
        p.crew -= count
        p.credits -= count * price
        return count, progress - count

    def update(self, dt):
        self.validate()
        cfg = recovery_rules()
        for e in sorted(self.state.entities.values(), key=lambda e: e.id):
            if (not e.alive or e.owner not in self.state.players or e.is_planet
                    or e.boarding or not (e.is_ship or e.is_station or e.is_squadron)):
                continue
            self._mission_tick(e, dt, cfg)
            if e.crew >= e.max_crew or e.subsystem_fraction('life_support') < cfg['support_threshold']:
                e.recruitment_progress = 0.0
                continue
            if self.base_for(e) is None:
                e.recruitment_progress = 0.0
                continue
            count, e.recruitment_progress = self._purchase(
                e, e.max_crew - e.crew, dt, cfg, e.recruitment_progress)
            e.crew += count
            if count:
                self.state.events.publish('crew_replenished', entity_id=e.id, crew=count)

    def _mission_tick(self, e, dt, cfg):
        info = e.crew_mission
        if not info:
            return
        phase = info['phase']
        target = self.state.entity(info['target'])
        reason = self.reason(e, phase, target)
        if reason:
            info['progress'] = 0.0
            info['reason'] = reason
            if reason in ('target complement full', 'no passengers loaded', 'passenger hold full'):
                self.cancel(e)
            return
        info['reason'] = ''
        if phase == 'recover':
            repairing = self.repairs_support(target, e)
            info['reason'] = 'repairing / replenishing' if repairing else 'replenishing / awaiting safe support'
            # A recruitment-only base cannot repair residual equipment damage.
            # Resume once safe and fully staffed there; at a usable repair dock
            # finish the requested repair instead of leaving at the AI threshold.
            support_goal = .99 if repairing else max(cfg['support_threshold'], cfg['ai_support_retreat'])
            if (e.crew >= e.max_crew and e.subsystem_fraction('life_support') >= support_goal
                    and e.pos.dist(target.pos) <= target.radius + cfg['base_range']):
                self.cancel(e)
            return
        if phase == 'load':
            count, info['progress'] = self._purchase(
                e, self.capacity(e) - e.crew_cargo, dt, cfg, info['progress'])
            e.crew_cargo += count
            if count == 0 and (self.state.players[e.owner].crew < 1 or
                              self.state.players[e.owner].credits < cfg['credits_per_crew']):
                info['reason'] = 'insufficient unassigned crew or credits'
            if e.crew_cargo >= self.capacity(e):
                self.cancel(e)
        else:
            if e.pos.dist(target.pos) > e.radius + target.radius + cfg['transfer_range']:
                info['reason'] = 'approaching target'
                info['progress'] = 0.0
                return
            info['progress'] += dt * cfg['delivery_rate']
            count = min(int(info['progress']), e.crew_cargo, target.max_crew - target.crew)
            info['progress'] -= count
            e.crew_cargo -= count
            target.crew += count
            if count:
                self.state.events.publish('crew_delivered', entity_id=e.id, target=target.id, crew=count)
            if e.crew_cargo == 0 or target.crew == target.max_crew:
                self.cancel(e)
