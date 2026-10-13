"""Deterministic onboard life support; player pools are never used as complements."""
from ..core.vectors import Vec3


def repair_life_support(entity, amount):
    """External engineers restore equipment, never regenerate its dead crew."""
    support = entity.systems.get('life_support')
    if support is not None and entity.alive:
        support.hp = min(support.max_hp, support.hp + max(0.0, amount))


def update_crew(state, dt):
    from .boarding import boarding_rules
    cfg = boarding_rules()
    rate = cfg['life_support_loss_per_second']
    threshold = cfg['life_support_failure_fraction']
    for e in sorted(state.entities.values(), key=lambda u: u.id):
        if not e.alive or e.is_planet or not (e.is_ship or e.is_station or e.is_squadron):
            continue
        support = e.subsystem_fraction('life_support')
        if e.crew_cargo > 0 and support < threshold:
            e.cargo_loss_accumulator += dt * rate * (1.0 - support / threshold)
            loss = min(e.crew_cargo, int(e.cargo_loss_accumulator))
            e.cargo_loss_accumulator -= loss
            e.crew_cargo -= loss
            if loss:
                state.events.publish('passengers_lost', entity_id=e.id, crew=loss)
        if e.crew > 0 and support < threshold:
            e.crew_loss_accumulator += dt * rate * (1.0 - support / threshold)
            loss = min(e.crew, int(e.crew_loss_accumulator))
            e.crew_loss_accumulator -= loss
            e.crew -= loss
            if loss:
                state.events.publish('crew_lost', entity_id=e.id, owner=e.owner, crew=e.crew)
                if e.crew == 0:
                    abandon_unit(state, e)
        if e.crew <= 0:
            stop_abandoned_unit(state, e)


def stop_abandoned_unit(state, e):
    if e.fleet_id is not None:
        from .jump import detach_jumpers
        detach_jumpers(state, [e])
    e.abandoned_attack_target = None
    e.vel = Vec3()
    e.order_type = 'idle'
    e.order_target_pos = e.order_target_id = e.current_target = None
    e.jump_charge = 0.0
    e.jump_target = None
    e.jump_travelling = False
    e.jump_origin = None
    e.jump_transit_total = 0.0
    e.ability_active.clear()
    for q in e.shields:
        e.shields[q] = 0.0


def abandon_unit(state, e):
    """Invalidate old combat intent in both directions at the casualty boundary."""
    stop_abandoned_unit(state, e)
    for other in state.entities.values():
        if other.abandoned_attack_target == e.id:
            other.abandoned_attack_target = None
        if other.current_target == e.id:
            other.current_target = None
        if other.order_type in ('attack', 'chase') and other.order_target_id == e.id:
            other.order_type = 'idle'
            other.order_target_id = other.order_target_pos = None
    if e.hull > 0:
        state.float_text(e.pos, 'ABANDONED', (1, .7, .3))
        state.events.publish('unit_abandoned', entity_id=e.id, owner=e.owner)
