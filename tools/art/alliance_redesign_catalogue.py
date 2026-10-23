"""Exact existing Alliance bindings, template/live IDs and bounded authoring allocations.

This is offline authoring metadata, not new gameplay classes or simulation data.
"""
ROWS=(
 ('fighter','alliance_interceptor','rebel_x_squadron','Falcon Fighter Squadron'),
 ('bomber','alliance_bomber','rebel_y_squadron','Bulwark Bomber Squadron'),
 ('corvette','alliance_corvette','rebel_corvette','Blockade Runner'),
 ('frigate','alliance_frigate','rebel_frigate','Escort Frigate'),
 ('cruiser','alliance_cruiser','rebel_cruiser','Liberty Cruiser'),
 ('battleship','alliance_battleship','rebel_battleship','Hope-class Command Cruiser'),
 ('supercapital','alliance_carrier','rebel_supercapital','Independence-class Fleet Carrier'),
 ('constructor','rebel_constructor','rebel_constructor','Alliance Engineering Sled'),
 ('colonizer','rebel_colonizer','rebel_colonizer','Freedom Colony Ship'),
 ('convoy','alliance_convoy','rebel_crew_transport','Rebel Crew Transport'),
 ('command_station','alliance_command_station','command_station','Command Station'),
 ('shipyard','alliance_shipyard','shipyard','Alliance Shipyard'),
 ('mining_station','alliance_mining_station','mining_station','Mining Station'),
 ('research_station','alliance_research_station','research_station','Research Station'),
 ('defense_platform','alliance_defense_platform','defense_platform','Defense Platform'),
 ('sensor_station','alliance_sensor_station','sensor_station','Sensor Station'),
 ('trade_station','alliance_trade_station','trade_station','Trade Station'),
 ('fighter_platform','alliance_fighter_platform','fighter_platform','Fighter Platform'),
 ('repair_dock','alliance_repair_dock','repair_dock','Repair Dock'),
 ('energy_relay','alliance_energy_relay','energy_relay','Energy Relay'),
 ('defense_satellite','alliance_defense_satellite','defense_satellite','Defense Satellite'),
 ('attack_satellite','alliance_attack_satellite','attack_satellite','Attack Satellite'),
 ('planet_extractor','alliance_planet_extractor','planet_extractor','Resource Extractor'),
 ('planet_trade_hub','alliance_planet_trade_hub','planet_trade_hub','Trade Hub'),
 ('planet_shield_generator','alliance_planet_shield_generator','planet_shield_generator','Surface Shield Generator'),
 ('planet_pulsar_cannon','alliance_planet_pulsar_cannon','planet_pulsar_cannon','Pulsar Cannon'),
)
SHIP_KINDS=frozenset(row[0] for row in ROWS[:10])
TRIANGLE_LIMITS={
 'fighter':2200,'bomber':2500,'corvette':4300,'frigate':9864,'cruiser':6500,
 'battleship':9500,'supercapital':9500,'constructor':2500,'colonizer':3500,'convoy':3600,
 'command_station':4000,'shipyard':10708,'mining_station':3200,'research_station':3500,
 'defense_platform':3200,'sensor_station':3000,'trade_station':3000,'fighter_platform':3000,
 'repair_dock':3200,'energy_relay':3000,'defense_satellite':2200,'attack_satellite':2200,
 'planet_extractor':2500,'planet_trade_hub':2500,'planet_shield_generator':2500,'planet_pulsar_cannon':2500,
}

def design_module(kind):
    if kind not in TRIANGLE_LIMITS:raise ValueError(kind)
    if kind=='frigate':return 'alliance_redesign_ship_designs'
    if kind=='shipyard':return 'alliance_redesign_station_designs'
    if kind in SHIP_KINDS:return 'alliance_redesign_fleet_designs'
    if kind.endswith('_satellite') or kind.startswith('planet_'):
        return 'alliance_redesign_hardware_designs'
    return 'alliance_redesign_orbital_designs'
