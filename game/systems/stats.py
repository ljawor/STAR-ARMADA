"""Stat aggregation: tech + commander + veteran + ability modifiers in one place.

Every system asks these helpers instead of re-implementing modifier math, so
balance changes land in exactly one file.
"""
from __future__ import annotations

from ..core.entity import Entity
from ..data.store import DataStore
from .experience import rank_for, attack_multiplier, SAFETY_MAX_RANK


def staffing_fraction(e: Entity) -> float:
    """Operating complement only; passengers never contribute efficiency."""
    return min(1.0, max(0.0, e.crew / e.max_crew)) if e.max_crew > 0 else 0.0


def tech_mult(state, player_id: int, key: str, default: float = 1.0) -> float:
    """Multiply together every researched tech effect for `key`."""
    p = state.players.get(player_id)
    if p is None:
        return default
    mult = default
    ds = DataStore.get()
    for tid in p.researched:
        t = ds.techs.get(tid)
        if t is None:
            continue
        v = t.effects.get(key)
        if isinstance(v, (int, float)):
            mult *= float(v)
    return mult


def tech_bonus(state, player_id: int, key: str, default: float = 0.0) -> float:
    """Sum additive tech effects for `key`."""
    p = state.players.get(player_id)
    if p is None:
        return default
    total = default
    ds = DataStore.get()
    for tid in p.researched:
        t = ds.techs.get(tid)
        if t is None:
            continue
        v = t.effects.get(key)
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def commander_mult(state, entity: Entity, key: str, default: float = 1.0) -> float:
    """Fleet-wide commander bonus if the entity belongs to a fleet with a commander."""
    if entity.fleet_id is None:
        return default
    fleet = state.fleets.get(entity.fleet_id)
    if fleet is None or fleet.commander is None:
        return default
    ds = DataStore.get()
    rules = ds.rules.get("commanders", {})
    v = rules.get(fleet.commander, {}).get(key)
    return default * (1.0 + float(v)) if v is not None else default


def veteran_fraction(entity: Entity) -> float:
    """0..1 progress through veteran levels (capped)."""
    return (rank_for(entity) - 1) / (SAFETY_MAX_RANK - 1)


def effective_max_shield_quad(state, e: Entity) -> float:
    base = e.max_shield_quad
    m = tech_mult(state, e.owner, "shield_max_mult")
    v = 1.0 + 0.10 * veteran_fraction(e)
    return base * m * v


def interception_efficiency(e: Entity) -> float:
    return staffing_fraction(e) * max(0.0, e.subsystem_fraction('weapons'))


def surface_shield_efficiency(e: Entity) -> float:
    return staffing_fraction(e) * max(0.0, e.subsystem_fraction('shield_gen'))


def effective_shield_regen(state, e: Entity) -> float:
    base = e.shield_regen
    m = tech_mult(state, e.owner, "shield_regen_mult")
    m *= commander_mult(state, e, "shield_regen")
    m *= e.subsystem_fraction('shield_gen')
    if e.data_id == 'planet_shield_generator':
        m *= staffing_fraction(e)
    active = e.ability_active.get("boost_shields", 0) > 0 or \
        e.ability_active.get("emergency_shield_recharge", 0) > 0
    if active and "boost_shields" in (e.ability_active or {}):
        ds = DataStore.get()
        a = ds.abilities.get("boost_shields")
        if a and e.ability_active.get("boost_shields", 0) > 0:
            m *= a.effects.get("shield_regen_mult", 1.0)
    v = 1.0 + 0.15 * veteran_fraction(e)
    return base * m * v


def effective_weapon_damage(state, e: Entity, base_damage: float) -> float:
    dmg = base_damage
    dmg *= tech_mult(state, e.owner, "weapon_damage_mult")
    dmg *= commander_mult(state, e, "weapon_damage")
    if e.ability_active.get("weapon_overcharge", 0) > 0:
        ds = DataStore.get()
        a = ds.abilities.get("weapon_overcharge")
        if a:
            dmg *= a.effects.get("damage_mult", 1.0)
    if e.is_squadron:
        dmg *= tech_mult(state, e.owner, "squadron_damage_mult")
    dmg *= e.damage_multiplier()
    dmg *= attack_multiplier(e)
    return dmg * staffing_fraction(e)


def effective_weapon_cooldown(state, e: Entity, base_cd: float) -> float:
    cd = base_cd
    cd *= 1.0 - 0.06 * veteran_fraction(e)
    return max(0.05, cd)


def effective_accuracy(state, e: Entity, base_acc: float) -> float:
    acc = base_acc
    acc += tech_bonus(state, e.owner, "accuracy_bonus")
    acc += 0.04 * veteran_fraction(e)
    return min(0.99, max(0.1, acc))


def effective_speed(state, e: Entity) -> float:
    if e.is_station or e.is_planet:
        return 0.0
    s = DataStore.get().ships.get(e.data_id) if (e.is_ship or e.is_squadron) else None
    if s is None:
        # no ShipData: trade convoys are minted by TradingSystem and steer
        # themselves (movement must not fight that). Fall back to the trading
        # speed so any other data-less hull still moves rather than crashing.
        eco = DataStore.get().rules.get("economy", {}).get("trading", {})
        if e.data_id == 'boarding_craft':
            from .boarding import boarding_rules
            return boarding_rules()['craft_speed'] * staffing_fraction(e)
        return float(eco.get("speed", 55.0)) * staffing_fraction(e) if e.data_id == "trade_convoy" else 0.0
    spd = s.speed * e.speed_multiplier()
    spd *= tech_mult(state, e.owner, "speed_mult")
    spd *= 1.0 + 0.05 * veteran_fraction(e)
    spd *= ability_speed_mult(e)
    spd *= debuff_speed_mult(e)
    return spd * staffing_fraction(e)


def effective_turn_rate(state, e: Entity) -> float:
    s = DataStore.get().ships.get(e.data_id) if (e.is_ship or e.is_squadron) else None
    if s is None:
        # trade convoys snap-heading in TradingSystem (and have no ShipData)
        return 0.0
    base = s.turn_rate
    tr = base * (0.3 + 0.7 * max(0.0, e.subsystem_fraction("engines")))
    tr *= tech_mult(state, e.owner, "turn_mult")
    if e.ability_active.get("engine_overdrive", 0) > 0:
        ds = DataStore.get()
        a = ds.abilities.get("engine_overdrive")
        if a:
            tr *= a.effects.get("turn_mult", 1.0)
    return tr * staffing_fraction(e)


def effective_sensor_range(state, e: Entity) -> float:
    base = getattr(e, "sensor_range", 0)
    rng = base * e.sensor_multiplier()
    rng *= tech_mult(state, e.owner, "sensor_range_mult")
    rng *= commander_mult(state, e, "sensor_range")
    rng *= 1.0 + 0.08 * veteran_fraction(e)
    if e.ability_active.get("sensor_jammed", 0) > 0:
        rng *= 0.4
    if state.in_nebula(e.pos):
        rng *= DataStore.get().rules.get("sensors", {}).get(
            "nebula_detection_multiplier", 0.3)
    return rng * staffing_fraction(e)


def effective_reinforce_mult(state, player_id: int) -> float:
    """Tech multiplier on squadron reinforcement speed (reb_fighters_1)."""
    return tech_mult(state, player_id, "squadron_reinforce_mult")


def effective_build_speed(state, player_id: int, entity=None) -> float:
    m = tech_mult(state, player_id, "build_speed_mult")
    # logistics commander on any fleet: approximate via any fleet with logistics commander
    for fleet in state.fleets.values():
        if fleet.owner == player_id and fleet.commander == "logistics":
            ds = DataStore.get()
            m *= 1.0 + ds.rules.get("commanders", {}).get("logistics", {}).get("build_speed", 0)
            break
    return m * staffing_fraction(entity) if entity is not None else m


def effective_research_speed(state, e):
    return staffing_fraction(e)


def effective_production_rate(state, e, rate):
    return rate * staffing_fraction(e)


def effective_repair_rate(state, player_id: int, entity=None) -> float:
    m = tech_mult(state, player_id, "repair_mult")
    for fleet in state.fleets.values():
        if fleet.owner == player_id and fleet.commander == "logistics":
            ds = DataStore.get()
            m *= 1.0 + ds.rules.get("commanders", {}).get("logistics", {}).get("repair_rate", 0)
            break
    return m * staffing_fraction(entity) if entity is not None else m


def player_command_capacity(state, player_id: int) -> int:
    p = state.players.get(player_id)
    if p is None:
        return 0
    ds = DataStore.get()
    rules = ds.rules.get("sim", {})
    cap = int(rules.get("command_capacity_base", 10))
    for e in state.entities.values():
        if e.operational and e.is_station and e.owner == player_id:
            station = ds.stations.get(e.data_id)
            if station is not None:
                cap += station.command_capacity
    cap += int(tech_bonus(state, player_id, "command_capacity_bonus"))
    # Every eligible colony provides one command center's catalogue capacity.
    # Do not add the former military-only bonus or repeat base/technology gains.
    from .colonies import eligible_planet
    center = ds.stations.get('command_station')
    for e in state.entities.values():
        if eligible_planet(e) and e.colonized_by == player_id and center is not None:
            cap += center.command_capacity
    return cap


def ability_speed_mult(e: Entity) -> float:
    if e.ability_active.get("engine_overdrive", 0) > 0:
        ds = DataStore.get()
        a = ds.abilities.get("engine_overdrive")
        if a:
            return a.effects.get("speed_mult", 1.0)
    return 1.0


def debuff_speed_mult(e: Entity) -> float:
    m = 1.0
    if e.ability_active.get("tractor_slowed", 0) > 0:
        ds = DataStore.get()
        a = ds.abilities.get("tractor_beam")
        if a:
            m *= a.effects.get("target_speed_mult", 1.0)
    return m