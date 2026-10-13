"""Planet-only paid surface hardware; supplemental income is not colony income."""
from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3
from ..data.store import DataStore
from .colonies import eligible_planet

BUILDING_TYPES = ('planet_extractor', 'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon')
# Surface construction pacing: resource units (credits + materials + energy) the
# colony works through per second. It lives in game_rules.json so mods retune
# build pacing without touching code, and every building's time is derived from
# its own cost rather than hand-set per type (#95).
DEFAULTS = dict(slot_cap=6, resource_units_per_second=80)


def building_rules():
    return dict(DEFAULTS, **DataStore.get().rules.get('planet_buildings', {}))


def building_time(kind, store=None, rules=None) -> float:
    """Seconds a surface building needs, derived from its resource cost (#95).

    The time is the catalogue cost in resource units over
    `resource_units_per_second`, so a dearer building always takes longer and
    two buildings of equal cost take equal time. `validate_building_catalogue`
    refuses a catalogue whose own `build_time` disagrees with this value, so the
    HUD row (which prints the catalogue number) can never advertise a time the
    simulation does not use.
    """
    store = DataStore.get() if store is None else store
    cfg = building_rules() if rules is None else dict(DEFAULTS, **rules)
    sd = store.stations[kind]
    units = float(sd.cost_credits) + float(sd.cost_materials) + float(sd.cost_energy)
    return units / float(cfg['resource_units_per_second'])


def building_slots(state, planet):
    return {e.planet_building_slot for e in state.entities.values()
            if e.alive and e.planet_id == planet.id and e.planet_building_slot is not None} | {
        w['slot'] for w in planet.build_queue if w.get('kind') == 'planet_building'}


def planet_building_site(planet, slot):
    """Return world foundation position and outward unit normal (stable octahedron)."""
    normals = (Vec3(1, 0, 0), Vec3(0, 0, 1), Vec3(-1, 0, 0),
               Vec3(0, 0, -1), Vec3(0, 1, 0), Vec3(0, -1, 0))
    normal = normals[slot]
    return planet.pos + normal * planet.radius, normal


def building_income(state, planet):
    from . import stats
    rates = dict(credits=0.0, materials=0.0, energy=0.0, crew=0.0)
    if not eligible_planet(planet) or planet.colonized_by not in state.players:
        return rates
    for e in state.entities.values():
        if (e.operational and e.planet_id == planet.id and e.planet_building_slot is not None
                and e.owner == planet.colonized_by and e.data_id in BUILDING_TYPES):
            for res, rate in DataStore.get().stations[e.data_id].income.items():
                rates[res] += stats.effective_production_rate(state, e, rate)
    p = state.players[planet.colonized_by]
    if p.is_ai:
        mult = DataStore.get().rules.get('ai', {}).get('difficulty', {}).get(p.ai_difficulty, {}).get('income_mult', 1.0)
        rates = {r: v * mult for r, v in rates.items()}
    return rates


def start_building(construction, planet_id, kind, player):
    st = construction.state
    planet = st.entity(planet_id) if type(planet_id) is int else None
    if (type(player) is not int or player not in st.players or not eligible_planet(planet)
            or planet.colonized_by != player or kind not in BUILDING_TYPES):
        return False
    used = building_slots(st, planet)
    slot = next((s for s in range(building_rules()['slot_cap']) if s not in used), None)
    if slot is None:
        return False
    pos, _ = planet_building_site(planet, slot)
    if not construction._check_station_spacing(kind, pos, player)[0]:
        return False
    cost = construction.factory.station_build_cost(kind)
    if not construction.command_available(player, construction.ds.stations[kind].command_cost):
        st.float_text(planet.pos, "Command capacity reached", (1, 0.6, 0.4))
        return False
    if not construction.can_pay(player, cost):
        return False
    construction.pay(player, cost)
    seconds = building_time(kind, construction.ds)
    planet.build_queue.append(dict(kind='planet_building', item=kind, slot=slot,
        source_owner=player, time_left=seconds, total=seconds, status='paid'))
    return True


def absorb_surface_damage(state, target, damage, shield_mult):
    """Drain deterministic generator quadrant pools; never shield orbitals/ships."""
    from . import stats
    planet = state.entity(target.planet_id) if target.planet_id is not None else None
    if (target.planet_building_slot is None or not eligible_planet(planet)
            or target.owner != planet.colonized_by or shield_mult <= 0):
        return damage
    for e in sorted(state.entities.values(), key=lambda e: e.id):
        if (e is target or not e.operational or e.data_id != 'planet_shield_generator'
                or e.planet_building_slot is None or e.planet_id != planet.id
                or e.owner != planet.colonized_by):
            continue
        efficiency = stats.surface_shield_efficiency(e)
        if efficiency <= 0:
            continue
        budget = damage * shield_mult * min(1.0, efficiency)
        for quad in e.shields:
            absorbed = min(e.shields[quad], budget)
            budget -= absorbed
            e.shields[quad] -= absorbed
            damage -= absorbed / shield_mult
            if absorbed:
                e.last_hit_time = state.time
                state.spawn_effect('shield_hit', target.pos.copy())
            if damage <= 0:
                return 0.0
    return max(0.0, damage)


def transfer_buildings(state, planet, owner):
    """Captured completed hardware survives; former owner's paid queues do not."""
    from .jump import clear_jump_orders, detach_jumpers
    hardware = [e for e in state.entities.values()
                if e.alive and e.planet_id == planet.id and e.planet_building_slot is not None]
    for e in sorted(hardware, key=lambda e: e.id):
        detach_jumpers(state, [e])
        clear_jump_orders(e)
        e.owner = owner
        e.build_queue.clear()
        e.ability_active.clear()
        e.current_target = None
    ids = {e.id for e in hardware}
    for e in state.entities.values():
        if e.current_target in ids:
            e.current_target = None
        if e.order_target_id in ids:
            clear_jump_orders(e)


def validate_building_catalogue(ds):
    cfg = ds.rules.get('planet_buildings', {})
    if not isinstance(cfg, dict) or type(cfg.get('slot_cap', 6)) is not int or cfg.get('slot_cap', 6) != 6:
        raise ValueError('planet_buildings slot_cap must be 6')
    rate = cfg.get('resource_units_per_second', DEFAULTS['resource_units_per_second'])
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError('planet_buildings resource_units_per_second must be a positive number')
    # Build time is derived from cost, so a catalogue that hand-sets a different
    # number would make the HUD (which prints the catalogue) lie about the sim.
    for kind in BUILDING_TYPES:
        sd = ds.stations.get(kind)
        if sd is None:
            raise ValueError(f'missing surface building catalogue entry: {kind}')
        derived = building_time(kind, ds, cfg)
        if abs(float(sd.build_time) - derived) > 1e-9:
            raise ValueError(
                f'{kind} build_time {sd.build_time:g} must equal its cost-derived {derived:g}s')
    for ship in ds.ships.values():
        if any(kind in BUILDING_TYPES for kind in ship.can_build_stations):
            raise ValueError('surface buildings can only build through a planet')
