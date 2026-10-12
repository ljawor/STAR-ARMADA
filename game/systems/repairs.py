"""Constructor field repairs: persistent orders, equipment only, pay per HP."""
from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..data.store import DataStore
from ..core.vectors import Vec3
from .stats import effective_repair_rate

DEFAULTS = dict(hp_per_second=20.0, credits_per_hp=.2, materials_per_hp=.1, range=400.0)


def repair_rules():
    return {**DEFAULTS, **DataStore.get().rules.get('engineer_repairs', {})}


def validate_repair_rules(rules):
    cfg = rules.get('engineer_repairs', {})
    if not isinstance(cfg, dict):
        raise ValueError('engineer_repairs must be an object')
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'engineer_repairs {key} must be finite and positive')


def builder_capable(state, entity):
    sd = DataStore.get().ships.get(entity.data_id) if entity else None
    return bool(entity and entity.operational and entity.is_ship
                and not entity.is_station and not entity.is_squadron and not entity.is_planet
                and not entity.boarding and sd and sd.is_construction
                and sd.can_build_stations and not sd.can_colonize)


def repair_reason(state, source, target):
    """Read-only eligibility; out-of-range legal targets are approached."""
    if not builder_capable(state, source):
        return 'needs an operating constructor'
    if source.jump_charge > 0 or source.jump_target is not None:
        return 'constructor is jumping'
    if (target is None or state.entity(target.id) is not target
            or target is source or not target.alive or target.hull <= 0
            or target.owner != source.owner or target.is_planet or target.boarding
            or not (target.is_ship or target.is_station or target.is_squadron)):
        return 'choose an owned hull'
    if missing_hp(target) <= 0:
        return 'target equipment healthy'
    return ''


def missing_hp(target):
    return max(0.0, target.max_hull - target.hull) + sum(
        max(0.0, s.max_hp - s.hp) for s in target.systems.values())


class RepairSystem:
    def __init__(self, state):
        self.state = state

    def cancel(self, source):
        if source.order_type != 'repair':
            return
        source.order_type = 'idle'
        source.order_target_id = source.order_target_pos = source.current_target = None
        source.vel = Vec3()

    def start(self, source, target, player):
        if (type(player) is not int or player not in self.state.players or source is None
                or self.state.entity(source.id) is not source
                or source.owner != player or not builder_capable(self.state, source)):
            return False
        self.cancel(source)
        if repair_reason(self.state, source, target):
            return False
        from .jump import clear_jump_orders, detach_jumpers
        detach_jumpers(self.state, [source])
        clear_jump_orders(source)
        source.order_type = 'repair'
        source.order_target_id = target.id
        source.vel = Vec3()
        self.validate()
        return True

    def validate(self):
        """Pre-movement ownership checks and safe explicit approach positions."""
        for source in sorted(self.state.entities.values(), key=lambda e: e.id):
            if source.order_type != 'repair':
                continue
            target = self.state.entity(source.order_target_id) if type(source.order_target_id) is int else None
            if repair_reason(self.state, source, target):
                self.cancel(source)
                continue
            reach = source.radius + target.radius + repair_rules()['range']
            offset = source.pos - target.pos
            if offset.length() <= reach:
                source.order_target_pos = None
                source.vel = Vec3()
            else:
                source.order_target_pos = target.pos + offset.normalized() * (reach - 20.0)

    def update(self, dt):
        self.validate()
        if not math.isfinite(dt) or dt <= 0:
            return
        cfg = repair_rules()
        for source in sorted(self.state.entities.values(), key=lambda e: e.id):
            if source.order_type != 'repair':
                continue
            target = self.state.entity(source.order_target_id)
            if source.pos.dist(target.pos) > source.radius + target.radius + cfg['range']:
                continue
            p = self.state.players.get(source.owner)
            if p is None:
                self.cancel(source)
                continue
            amount = min(missing_hp(target), dt * cfg['hp_per_second'] *
                         effective_repair_rate(self.state, source.owner, source),
                         max(0.0, p.credits) / cfg['credits_per_hp'],
                         max(0.0, p.materials) / cfg['materials_per_hp'])
            remaining = amount
            # Single shared budget: life support, hull, alphabetical subsystems.
            support = target.systems.get('life_support')
            if support:
                gain = min(remaining, max(0.0, support.max_hp - support.hp))
                support.hp += gain
                remaining -= gain
            gain = min(remaining, max(0.0, target.max_hull - target.hull))
            target.hull += gain
            remaining -= gain
            for name in sorted(target.systems):
                if name == 'life_support':
                    continue
                subsystem = target.systems[name]
                gain = min(remaining, max(0.0, subsystem.max_hp - subsystem.hp))
                subsystem.hp += gain
                remaining -= gain
            repaired = amount - remaining
            p.credits -= repaired * cfg['credits_per_hp']
            p.materials -= repaired * cfg['materials_per_hp']
            if missing_hp(target) <= 1e-9:
                self.cancel(source)
