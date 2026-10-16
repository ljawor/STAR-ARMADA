# S01 — rendered-model inventory and coverage matrix

Base: `16523bf0b06a39e3f77961d0c213b0af184a16b6` (`main`), roadmap step **S01**. Regenerate with `.venv/bin/python tools/art/build_model_inventory.py`; `--check` fails on drift.

This document is generated from the tree, not transcribed. Every line reference below is measured by resolving the named symbol at the base commit, so a moved function re-bases instead of silently pointing at the wrong code. `art/manifests/model_inventory.json` is the machine-readable form of the same data.

What is measured here and what is merely reproduced: every `generator` and `dispatch_site` in the row tables is resolved to a real `def` at the base commit, and each dispatch path records whether the symbols it names exist in this tree. The audit was taken on the checkpoint tree, so the line ranges quoted inside its prose are reproduced, not re-measured — each row states whether that range still fits inside the file here, and a row whose symbols are absent from this tree is listed separately in section 5.1 instead of being blended into the live paths.

Code base: no renderer, gameplay, test or asset file differs from main, so every line reference in this inventory is valid for a reader of main.

## 1. What this covers

| item | count |
|---|---|
| total_bindings | 120 |
| ship_bindings | 41 |
| distinct_ship_mesh_keys | 32 |
| distinct_ship_mesh_keys_from_data_rows | 32 |
| ship_keys_in_registry | 35 |
| station_bindings | 40 |
| station_kinds | 10 |
| satellite_bindings | 8 |
| planet_installation_bindings | 16 |
| environment_prop_bindings | 13 |
| menu_cinematic_bindings | 1 |
| campaign_prop_bindings | 0 |
| campaign_only_models | 0 |
| bindings_in_scope_by_owner_decision | 10 |
| dispatch_paths | 25 |
| tooling_dispatch_paths | 5 |
| non_model_elements | 25 |
| hidden_duplicate_risk_paths | 16 |
| scope_questions_asked_and_answered | 3 |
| unresolved_items | 5 |

Coverage comes from the data, not from a hand-written list: ships are enumerated from `game.data.store.DataStore().ships`, stations and hardware from `assets/data/stations/stations.json`, and environment props from the union of planet kinds across every file in `assets/data/maps/`, so a new map kind appears here automatically.

## 2. Ships — bindings and the mesh the renderer actually selects

| binding | label | category | mesh key | shared with | generator |
|---|---|---|---|---|---|
| `ship:confederacy:battleship` | Bulwark Bastion | combat_hull | `confederacy:battleship` | 0 | `render/faction_ships.py:_legions_capital:165` |
| `ship:confederacy:bomber_squadron` | Hyena Strike Wing | squadron | `confederacy:bomber` | 0 | `render/faction_ships.py:_legions_small:74` |
| `ship:confederacy:colonizer` | Droid Foundry Barge | construction | `confederacy:colonizer` | 0 | `render/faction_ships.py:_legions_logistics:292` |
| `ship:confederacy:constructor` | Homing Spider Droid Rig | construction | `confederacy:constructor` | 0 | `render/faction_ships.py:_legions_logistics:292` |
| `ship:confederacy:corvette` | Droth Drone Corvette | combat_hull | `confederacy:corvette` | 0 | `render/faction_ships.py:_legions_line:421` |
| `ship:confederacy:crew_transport` | Confederacy Crew Transport | logistics_hull | `confederacy:convoy` | 1 | `render/faction_ships.py:_legions_logistics:292` |
| `ship:confederacy:cruiser` | Recusant Raider | combat_hull | `confederacy:cruiser` | 0 | `render/faction_ships.py:_legions_line:421` |
| `ship:confederacy:frigate` | Cobalt Frigate | combat_hull | `confederacy:frigate` | 0 | `render/faction_ships.py:_legions_line:421` |
| `ship:confederacy:supercapital` | Subjugator-class Sovereignty | combat_hull | `confederacy:supercapital` | 0 | `render/faction_ships.py:_legions_capital:165` |
| `ship:confederacy:vulture_squadron` | Vulture Drone Wing | squadron | `confederacy:fighter` | 0 | `render/faction_ships.py:_legions_small:74` |
| `ship:imperial:battleship` | Executor-class Dreadnought | combat_hull | `dagger` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:colonizer` | Colonial Outreach Frigate | construction | `box` | 3 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:constructor` | Engineering Corps Corvette | construction | `box` | 3 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:corvette` | Vigil Corvette | combat_hull | `needle` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:crew_transport` | Imperial Crew Transport | logistics_hull | `box` | 3 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:cruiser` | Gladiator Cruiser | combat_hull | `cruiser` | 0 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:frigate` | Lancer Frigate | combat_hull | `needle` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:supercapital` | Sovereign-class Star Dreadnought | combat_hull | `dagger` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:tie_bomber_squadron` | Hammer Torpedo Squadron | squadron | `wedge` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:imperial:tie_squadron` | Talon Interceptor Squadron | squadron | `wedge` | 1 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:rebel:battleship` | Hope-class Command Cruiser | combat_hull | `rebel:battleship` | 0 | `render/faction_ships.py:_alliance_capital:120` |
| `ship:rebel:colonizer` | Freedom Colony Ship | construction | `rebel:colonizer` | 0 | `render/faction_ships.py:_alliance_logistics:240` |
| `ship:rebel:constructor` | Alliance Engineering Sled | construction | `rebel:constructor` | 0 | `render/faction_ships.py:_alliance_logistics:240` |
| `ship:rebel:corvette` | Blockade Runner | combat_hull | `rebel:corvette` | 0 | `render/faction_ships.py:_alliance_line:391` |
| `ship:rebel:crew_transport` | Rebel Crew Transport | logistics_hull | `rebel:convoy` | 1 | `render/faction_ships.py:_alliance_logistics:240` |
| `ship:rebel:cruiser` | Liberty Cruiser | combat_hull | `rebel:cruiser` | 0 | `render/faction_ships.py:_alliance_line:391` |
| `ship:rebel:frigate` | Escort Frigate | combat_hull | `rebel:frigate` | 0 | `render/faction_ships.py:_alliance_line:391` |
| `ship:rebel:supercapital` | Independence-class Fleet Carrier | combat_hull | `rebel:supercapital` | 0 | `render/faction_ships.py:_alliance_capital:120` |
| `ship:rebel:x_squadron` | Falcon Fighter Squadron | squadron | `rebel:fighter` | 0 | `render/faction_ships.py:_alliance_small:48` |
| `ship:rebel:y_squadron` | Bulwark Bomber Squadron | squadron | `rebel:bomber` | 0 | `render/faction_ships.py:_alliance_small:48` |
| `ship:syndicate:colonizer` | Frontier Settlement Barge | construction | `syndicate:colonizer` | 0 | `render/faction_ships.py:_syndicate_logistics:334` |
| `ship:syndicate:constructor` | Scrapyard Hauler | construction | `syndicate:constructor` | 0 | `render/faction_ships.py:_syndicate_logistics:334` |
| `ship:syndicate:corvette` | Marauder Corvette | combat_hull | `syndicate:corvette` | 0 | `render/faction_ships.py:_syndicate_line:460` |
| `ship:syndicate:crew_transport` | Syndicate Crew Transport | logistics_hull | `syndicate:convoy` | 1 | `render/faction_ships.py:_syndicate_logistics:334` |
| `ship:syndicate:cruiser` | Reaver Assault Cruiser | combat_hull | `syndicate:cruiser` | 0 | `render/faction_ships.py:_syndicate_line:460` |
| `ship:syndicate:frigate` | Cutlass Frigate | combat_hull | `syndicate:frigate` | 0 | `render/faction_ships.py:_syndicate_line:460` |
| `ship:syndicate:raid_squadron` | Jackal Raid Wing | squadron | `syndicate:fighter` | 0 | `render/faction_ships.py:_syndicate_small:97` |
| `ship:imperial:trade_convoy` | — | logistics_hull | `box` | 4 | `render/fleet_geometry.py:_ship_mesh:170` |
| `ship:rebel:trade_convoy` | — | logistics_hull | `rebel:convoy` | 2 | `render/faction_ships.py:_alliance_logistics:240` |
| `ship:confederacy:trade_convoy` | — | logistics_hull | `confederacy:convoy` | 2 | `render/faction_ships.py:_legions_logistics:292` |
| `ship:syndicate:trade_convoy` | — | logistics_hull | `syndicate:convoy` | 2 | `render/faction_ships.py:_syndicate_logistics:334` |

41 bindings resolve to 32 distinct meshes, and every one of those keys is declared in `render.ship_sizes.SHIP_KEYS` (35 keys). That containment is the coverage proof for hulls: no hull can reach the renderer without landing on an inventoried key.

### 2.1 Declared but unreachable

`SHIP_KEYS` also declares keys that no current data row can select. They are reported rather than deleted, because the question is whether the slot is planned or dead:

- `syndicate:bomber`
- `syndicate:battleship`
- `syndicate:supercapital`

**Owner decision 2026-10-16: keep them and plan the hulls.** Battleships and capital ships build at the shipyard; bombers build at the fighter platform. `shipyard.builds_ships` is `['*']`, so capital production there already holds; `fighter_platform.builds_ships` is an explicit list, so a new bomber hull stays unbuildable until its data id is added to it — a data change to make alongside the hull, not a model change.

## 3. Stations, satellites and planet installations

| binding pattern | label | category | generator | dispatch |
|---|---|---|---|---|
| `station:{faction}:command_station` | Command Station | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:mining_station` | Mining Station | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:shipyard` | Shipyard | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:research_station` | Research Station | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:defense_platform` | Defense Platform | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:sensor_station` | Sensor Station | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:trade_station` | Trade Station | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:fighter_platform` | Fighter Platform | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:repair_dock` | Repair Dock | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:energy_relay` | Energy Relay | station | `render/fleet_geometry.py:_station_mesh:290` | `render/fleet_geometry.py:station_mesh:249` |
| `station:{faction}:command_station` | Command Station | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:mining_station` | Mining Station | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:shipyard` | Shipyard | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:research_station` | Research Station | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:defense_platform` | Defense Platform | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:sensor_station` | Sensor Station | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:trade_station` | Trade Station | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:fighter_platform` | Fighter Platform | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:repair_dock` | Repair Dock | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:energy_relay` | Energy Relay | station | `render/faction_stations.py:_alliance:103` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:command_station` | Command Station | station | `render/faction_stations.py:_legions:204` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:mining_station` | Mining Station | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:shipyard` | Shipyard | station | `render/faction_stations.py:_legions:204` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:research_station` | Research Station | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:defense_platform` | Defense Platform | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:sensor_station` | Sensor Station | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:trade_station` | Trade Station | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:fighter_platform` | Fighter Platform | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:repair_dock` | Repair Dock | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:energy_relay` | Energy Relay | station | `render/faction_stations.py:_legions_roles:231` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:command_station` | Command Station | station | `render/faction_stations.py:_syndicate:311` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:mining_station` | Mining Station | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:shipyard` | Shipyard | station | `render/faction_stations.py:_syndicate:311` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:research_station` | Research Station | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:defense_platform` | Defense Platform | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:sensor_station` | Sensor Station | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:trade_station` | Trade Station | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:fighter_platform` | Fighter Platform | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:repair_dock` | Repair Dock | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `station:{faction}:energy_relay` | Energy Relay | station | `render/faction_stations.py:_syndicate_roles:346` | `render/faction_stations.py:_station_mesh:434` |
| `hardware:satellite:{faction}:defense_satellite` | Defense Satellite | satellite | `render/fleet_geometry.py:_satellite_mesh:266` | `render/fleet_geometry.py:_station_mesh:290` |
| `hardware:satellite:{faction}:attack_satellite` | Attack Satellite | satellite | `render/fleet_geometry.py:_satellite_mesh:266` | `render/fleet_geometry.py:_station_mesh:290` |
| `hardware:construction:{faction}:planet_extractor` | Resource Extractor | planet_installation | `render/planet_building_geometry.py:_building_mesh:59` | `render/planet_building_geometry.py:building_mesh:12` |
| `hardware:construction:{faction}:planet_trade_hub` | Trade Hub | planet_installation | `render/planet_building_geometry.py:_building_mesh:59` | `render/planet_building_geometry.py:building_mesh:12` |
| `hardware:construction:{faction}:planet_shield_generator` | Surface Shield Generator | planet_installation | `render/planet_building_geometry.py:_building_mesh:59` | `render/planet_building_geometry.py:building_mesh:12` |
| `hardware:construction:{faction}:planet_pulsar_cannon` | Pulsar Cannon | planet_installation | `render/planet_building_geometry.py:_building_mesh:59` | `render/planet_building_geometry.py:building_mesh:12` |

10 station kinds in data, drawn as 40 faction bindings; 8 satellite bindings and 16 planet-installation bindings reuse the same data rows through their own builders.

## 4. Environment and shared props

| binding | generator | dispatch |
|---|---|---|
| `environment:agricultural` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:asteroid_field` | `render/renderer.py:_draw_rock:1100` | `render/renderer.py:_draw_asteroid_field:1076` |
| `environment:barren` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:gas_giant` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:industrial` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:military` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:research` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:temperate` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:trade` | `render/renderer.py:_build_textured_sphere_list:1014` | `render/renderer.py:_draw_planets:962` |
| `environment:deep_space_sky_dome` | `render/renderer.py:_draw_starfield:784` | `render/renderer.py:_draw_starfield:784` |
| `environment:star` | `render/renderer.py:_draw_star:848` | `render/renderer.py:_draw_star:848` |
| `environment:nebula` | `render/renderer.py:_draw_nebulas:827` | `render/renderer.py:_draw_nebulas:827` |
| `environment:jump_point` | `render/renderer.py:_draw_jump_points:899` | `render/renderer.py:_draw_jump_points:899` |

Kinds discovered in the maps: `agricultural`, `asteroid_field`, `barren`, `gas_giant`, `industrial`, `military`, `research`, `temperate`, `trade`. **Owner decision 2026-10-16: the planet bodies and the asteroid field are in scope** and carry `in_scope_authoring_pending`; they are authoring targets in batch B5. The sky dome, star, nebula and jump point were proposed `keep procedural` and were not among the questions asked, so they stay recorded as proposals.

## 5. Renderer dispatch paths

Every path through which the renderer obtains 3D geometry. The last column is measured here: it says whether the symbols named in the row exist in this tree at the base commit, so an unmerged path cannot pass for a live one.

| id | module:symbol | line reference | line range vs this file | emits | source call |
|---|---|---|---|---|---|
| `R01_ship_mesh_facade` | `render/fleet_geometry.py:ship_mesh` | L159-166 | within_file_at_this_base | ships: every SHIP_KEY - legacy Imperial shapes and all faction roles incl. squadron members (fighter/bomber), logistics (constructor/colonizer/convoy) | `faction_ships.ship_mesh(*shape.split(':')) when ':' in shape, else _ship_mesh(shape)` |
| `R02_legacy_imperial_ship_hull` | `render/fleet_geometry.py:_ship_mesh` | L169-241 (lru_cache maxsize=5) | within_file_at_this_base | ships: legacy Imperial/mod/neutral hulls - wedge, needle, cruiser, dagger, box (the 'box' utility hull also backs trade_convoy and unknown mods) | `_Hardware().loft(...)/plate(...)/turret(...)/nozzle(...)/vent(...)/bay(...) -> h.finish() (fully procedural, no authored asset, no GL)` |
| `R03_station_mesh_facade` | `render/fleet_geometry.py:station_mesh` | L249-262 | within_file_at_this_base | stations + satellites + planet surface buildings (the single entry the renderer, camera bounds and picking all use for station-family ids) | `building_mesh(data_id, faction) \| _satellite_mesh(data_id, faction) \| faction_stations.station_mesh(faction, data_id) \| _station_mesh(data_id)` |
| `R04_satellite_hardware_mesh` | `render/fleet_geometry.py:_satellite_mesh` | L265-286 (lru_cache maxsize=8) | within_file_at_this_base | planetary satellites / orbital hardware: defense_satellite and attack_satellite, faction-specific side counts and silhouettes | `_Hardware().ring(...) -> h.finish() (procedural; sides = {imperial:6, rebel:12, confederacy:8, syndicate:5})` |
| `R05_legacy_imperial_station_mesh` | `render/fleet_geometry.py:_station_mesh` | L289-427 (lru_cache maxsize=10) | within_file_at_this_base | stations: all 10 Imperial STATION_TYPES | `_Hardware() procedural build -> h.finish()` |
| `R06_faction_ship_mesh` | `render/faction_ships.py:ship_mesh / _ship_mesh` | L15-46 (cache maxsize=30) | within_file_at_this_base | ships: rebel/confederacy/syndicate, 10 SHIP_ROLES x 3 factions (small craft, capital, logistics, line hulls) | `dispatch helpers _alliance*/_legions*/_syndicate* -> _Hardware.finish(); capital and line hulls route through the authored slices` |
| `R09_faction_station_mesh` | `render/faction_stations.py:station_mesh / _station_mesh` | L17-27, L457-475 (cache maxsize=30) | range_extends_past_end_of_file_at_this_base | stations: rebel/confederacy/syndicate station variants; result normalised into the radius-50 material space | `{'rebel': _alliance, 'confederacy': _legions, 'syndicate': _syndicate}[faction](h, kind) -> MappingProxyType(... *0.8 fit)` |
| `R10_authored_shipyard_branch` | `render/faction_stations.py:_station_mesh (rebel shipyard branch)` | L459-463 (authored); procedural fallbac… | range_extends_past_end_of_file_at_this_base | rebel shipyard (the Alliance-owned/rebel station) from assets/models/alliance_shipyard.mesh.json | `if faction == 'rebel' and kind == 'shipyard': from .authored_mesh import shipyard_mesh; return shipyard_mesh()` |
| `R11_planet_building_mesh` | `render/planet_building_geometry.py:building_mesh / _building_mesh` | L12-17, L58-113 (cache maxsize=16) | within_file_at_this_base | colonized-planet surface hardware (BUILDING_TYPES incl. planet_shield_generator) | `_building_mesh(kind, faction) procedural (shared with _Hardware)` |
| `R12_renderer_batched_role_emission` | `render/renderer.py:_draw_ship_role_batch (called from _draw_ships L1262)` | L1385-1492; ship call L1448; station ca… | within_file_at_this_base | ships + squadrons + stations, one material role per pass (base/dark/trim/accent/lit/cool) for every visible entity | `glCallList(self._ship_display_list(size.shape + suffix)) and glCallList(self._station_detail_list(e.data_id, role, faction))` |
| `R13_renderer_per_ship_draw` | `render/renderer.py:_draw_ship` | L1943-2041; calls L1979, L1989-1991, L2… | within_file_at_this_base | one ship: six material roles plus an inlined engine-trail triangle | `lst = self._ship_display_list(vis['shape']) (+ '_dark'/'_trim'/'_lit'/'_accent'/'_cool' suffixes)` |
| `R14_renderer_ship_display_list_builder` | `render/renderer.py:_ship_display_list` | L2074-2111 (emit at L2105); cache write… | within_file_at_this_base | compiles six GL display lists per ship shape (base/dark/trim/accent/lit/cool) | `self._emit_detail_hull(shape, pname) -> self._emit_detail_mesh(ship_mesh(shape)[role]) (renderer.py:2486-2487)` |
| `R15_renderer_station_detail_list_builder` | `render/renderer.py:_station_detail_list` | L2461-2474 (emit at L2471); cache write… | within_file_at_this_base | compiles one GL display list per (faction, data_id, role) for stations, satellites and planet buildings | `self._emit_detail_mesh(station_mesh(data_id, faction)[role])` |
| `R16_renderer_per_station_draw` | `render/renderer.py:_draw_station` | L2401-2459; calls L2430, L2436, L2440, … | within_file_at_this_base | one station / satellite / planet building: roles base, dark, trim (metal passes) + accent, lit, cool, under the station_frame transform | `glCallList(self._station_detail_list(e.data_id, role, faction))` |
| `R17_renderer_station_outline_preview` | `render/renderer.py:_draw_station_outline` | L639-665; direct mesh call L643; emissi… | within_file_at_this_base | construction-stage / placement ghost: exact all-role hardware wireframe (GL_LINE polygon mode) at a candidate position | `mesh = station_mesh(data_id, faction) then for triangles in mesh.values(): self._emit_detail_mesh(triangles)` |
| `R18_renderer_placement_preview` | `render/renderer.py:_draw_placement_preview` | L619-637 (delegates at L637); invoked f… | within_file_at_this_base | live build-placement ghost outline for the local player's builder (green valid / red invalid) | `self._draw_station_outline(data_id, faction, pos, data.radius, color) -> station_mesh` |
| `R19_renderer_surface_slot_preview` | `render/renderer.py:_draw_surface_slots` | L546-601; mesh call L589-590; pad rings… | within_file_at_this_base | planet surface build pads: empty ticks, occupied rings, and a queued-building hardware wireframe (GL_LINE) plus progress arc | `glCallList(self._station_detail_list(pad['kind'], 'base', self.state.players[self.local_player].faction))` |
| `R20_renderer_construction_sites` | `render/renderer.py:_draw_construction_sites` | L667-739; station wireframe delegate L6… | within_file_at_this_base | construction-site scaffold (ring + 8 posts + height ring + progress arc, procedural) and, for non-imperial factions only, the target station's hardware wireframe | `if faction != 'imperial': self._draw_station_outline(item['item'], faction, pos, r, color) -> station_mesh` |
| `R21_camera_keepout_bounds` | `render/camera_geometry.py:station_bounds / _station_bounds / station_radius / _station_radius / scene_boxes` | L12-27, L17-18 (cache 40), L27-35, L32-… | within_file_at_this_base | no GL - camera keep-out world boxes and radii derived from station geometry, plus the readable-interval solve used by the tactical camera | `station_mesh(data_id, faction) -> min/max bounds` |
| `R22_ship_size_lod_and_contact_rays` | `render/ship_sizes.py:_bounds / _canonical_bounds / _ray_mesh / _canonical_ray_mesh / hull_contact_distance / hull_conta…` | L21-46, L79-101, L104-203; caches at L2… | within_file_at_this_base | no GL - readable-size LOD policy polygons and hull/station contact-surface offsets and hit rays derived from the resolved meshes | `ship_mesh(shape) and station_mesh(...) triangles -> contact/ray arrays` |
| `R23_planet_building_pick_and_frame` | `render/planet_building_geometry.py:station_world_mesh / _station_local_bounds / station_camera_box / station_pick_dista…` | L114-253; mesh call L149-156; bounds L1… | within_file_at_this_base | no GL - world-space mesh for click picking, per-building camera box, pick distance and surface contact point for planet installations | `station_mesh(entity.data_id, owner_faction(state, entity.owner)) triangles` |
| `R24_renderer_inline_legacy_hull_emit` | `render/renderer.py:_emit_hull (with _emit_glazing L2290-2356, _armor_loft L2113-2121, _station_ring L2358-2400 and the …` | L2122-2288 (glazing L2290-2356; armor_l… | within_file_at_this_base | a COMPLETE second procedural ship hull generator inside the renderer for shapes wedge/needle/cruiser/dagger/box, plus its own emissive glazing pass | `self._lit_box(...) / self._out_pyr(...) / self._dome(...) / self._octa_tube(...) / self._capsule(...) / self._armor_loft(...) / self._emit_glazing(...) - it never calls ship_mesh()` |
| `R25_renderer_inline_legacy_station_lit` | `render/renderer.py:_station_lit_list (with _emit_station_lit L2513-2669)` | L2490-2511 (calls _emit_station_lit at … | within_file_at_this_base | a second, unit-radius station emissive-detail geometry (windows / hangars / beacons / running lights) built from inline _lit_box calls per station type | `self._lit_box(...) chains keyed on data_id; does NOT call station_mesh` |

### 5.1 Paths that exist only on the checkpoint branch

These rows describe code in the unmerged trio checkpoint, not in this tree; the absent symbols are listed so the row is self-checking.

| id | module:symbol | absent here | emits |
|---|---|---|---|
| `R07_authored_battleship_slice` | `render/faction_ships.py:_alliance_battleship_slice (reached from _alliance_capital at L171-173)` | `render/faction_ships.py:_alliance_battleship_slice` | rebel:battleship hull from the Blender authored asset assets/models/alliance_battleship.mesh.json |
| `R08_authored_frigate_slice` | `render/faction_ships.py:_alliance_frigate_slice (reached from _alliance_line at L480-482 for level==1)` | `render/faction_ships.py:_alliance_frigate_slice` | rebel:frigate hull from assets/models/alliance_frigate.mesh.json |

Tool-only paths (5), which cannot affect the shipped renderer:

- `T01_tool_build_menu_movie` — `tools/build_menu_movie.py:build_movie / main L1-320 (renders through the production Renderer)` — the main-menu cinematic 3D background is authored offline by drawing a synthetic ship/station scene with the production renderer, then encoding it to assets/menu/battle.zip (the runtime blits frames only)
- `T02_tool_diag_faction_hardware` — `tools/diag_faction_hardware.py (committed_module + parity harness) L29 import; L41-47 committed_module; L109-114 current vs old; L153 station_mesh; L173-175 ship_mesh parity asserts` — diagnostic renders and exact-equality asserts comparing the current geometry against a BASELINE commit's render/fleet_geometry.py loaded from git
- `T03_tool_diag_ship_sizes` — `tools/diag_ship_sizes.py L26 import; L97, L181 ship_mesh triangles; L102/L134 current vs baseline Renderer` — readable-size / LOD parity diagnostics computed directly from ship_mesh triangle point clouds
- `T04_tool_renderer_probe_harness` — `tools/diag_models.py:79, tools/diag_detail.py:44, tools/diag_fleet_detail.py:61, tools/diag_station.py:41, tools/diag_corvette.py:51, tools/diag_close_zoom.py:87, tools/diag_planet_buildings.py:71, tools/diag_nebula_satellite_orbits.py:36, tools/diag_gfx3.py:100-113, tools/chk_selected_shield.py:56, tools/perf_shields.py:34 (70 tools/diag_*.py files exist in total) as listed (one representative line per tool)` — diagnostic captures / measurements that instantiate the production Renderer against synthetic GameStates and therefore exercise the same dispatch as gameplay
- `T05_tool_inline_legacy_probe` — `tools/probe_hull.py, tools/probe_inline.py, tools/diag_gl_lifecycle.py probe_hull.py L37,L55; probe_inline.py L1,L48; diag_gl_lifecycle.py L34,L49` — probes that call the renderer's legacy inline generator and display-list builder directly (rasterise _lit_box/_out_pyr with no display list; build _ship_display_list('needle'); exercise _ship_display_list('wedge') throu…

## 6. Paths that can hide a second copy of a model

- R02_legacy_imperial_ship_hull - private procedural imperial/mod/neutral hull library that remains the fallback geometry authority
- R05_legacy_imperial_station_mesh - private procedural imperial station library
- R07_authored_battleship_slice - in-function copy of the pre-Blender battleship hull kept as emergency fallback (faction_ships.py:139-168) [draft PR #114 only: this fallback pair exists on the checkpoint branch, not in this tree]
- R08_authored_frigate_slice - in-function copy of the pre-Blender frigate hull kept as emergency fallback (faction_ships.py:457-477) [draft PR #114 only: this fallback pair exists on the checkpoint branch, not in this tree]
- R10_authored_shipyard_branch - procedural _alliance_shipyard_slice fallback retained, and the authored branch skips the *0.8 radius fit the procedural stations get [draft PR #114 only: this fallback pair exists on the checkpoint branch, not in this tree]
- R12_renderer_batched_role_emission - geometry frozen in self.ship_lists GL display lists keyed by shape string
- R13_renderer_per_ship_draw - second call site into the same self.ship_lists cache
- R14_renderer_ship_display_list_builder - owns and never invalidates self.ship_lists[shape]
- R15_renderer_station_detail_list_builder - owns self.ship_lists['station_detail:...']
- R16_renderer_per_station_draw - shares the station_detail cache with R12 and R19
- R17_renderer_station_outline_preview - a second, non-display-list, non-cached dispatch straight into station_mesh that a display-list-only migration would silently miss
- R24_renderer_inline_legacy_hull_emit - a COMPLETE second inline ship-hull generator in renderer.py (_emit_hull/_emit_glazing/_armor_loft/_lit_box/_out_pyr/_dome/_octa_tube/_capsule, _station_ring has zero call sites) with NO production caller (only tests/test_modern_fleet.py:38). Highest-severity hidden dispatch path.
- R25_renderer_inline_legacy_station_lit - duplicate station emissive-detail generator (_station_lit_list/_emit_station_lit) with no production caller; only referenced by a tools/diag_gfx3.py monkeypatch
- T01_tool_build_menu_movie - bakes a frozen pixel copy of the current models into assets/menu/battle.zip
- T02_tool_diag_faction_hardware - loads a second full copy of render/fleet_geometry.py from a git BASELINE commit as a geometry control
- T05_tool_inline_legacy_probe - probe tools that pin the legacy inline generator (R24) as exercised

## 7. Not model replacements — owner scope decisions

| id | element | proposed decision |
|---|---|---|
| `E01_starfield_sky_dome` | eye-centred 40000-unit textured sphere used as the sky / deep-space background (angular parallax only, no translation) | keep procedural |
| `E02_nebula_billboards` | camera-facing textured billboards (two layers, 0.30/0.35 alpha) at map nebula positions, gated by exploration | keep procedural |
| `E03_star_billboard` | the system star: textured billboard plus a soft additive halo | keep procedural |
| `E04_jump_point_rings` | two counter-rotating wireframe rings marking a jump point | keep procedural |
| `E05_planet_surface_sphere` | each planet/asteroid_field-excluded body: a unit sphere scaled to e.radius, textured with a procedural equirect texture per planet type, slow axial spin | owner decision required |
| `E06_planet_atmosphere_shell` | thin translucent limb shell over a planet (air=0 for 'barren'), drawn via the same unit sphere with a shader pass | keep procedural |
| `E07_asteroid_field_rocks` | asteroid_field entities: 40 deterministic lumpy rock clusters per field, 3-5 vertex-jittered faceted sub-rocks each, slow tumble | owner decision required |
| `E08_ship_engine_trail` | camera-facing additive triangle trail behind a moving ship | keep procedural |
| `E09_ship_engine_glow` | additive billboard glow disc at a moving ship's stern | keep procedural |
| `E10_station_build_progress_ring` | rotating green line-strip arc around a station with a build queue | keep procedural |
| `E11_ownership_markers` | screen-clamped chevron (own/ally) or diamond (hostile) marker drawn on each currently-detected unit | keep procedural |
| `E12_collection_point_links` | world-space diamond+cross endpoint and link lines from a selected collection-capable station to its collection point | keep procedural |
| `E13_surface_slot_pad_rings` | line-loop pad rings and tick crosses marking empty/occupied/paid planet surface slots | keep procedural |
| `E14_surface_selection_box` | green line-loop box drawn on a selected planet building slot | keep procedural |
| `E15_projectiles` | shaped weapon fire: thin elongated bolts for lasers, squares for torpedoes/missiles, additive glow + point-sprite core for ion/plasma/kinetic/beam; expanded into one GL_TRIANGLES batch | keep procedural |
| `E16_explosions_beams_and_effect_geometry` | layered procedural detonation (lumpy rings, no per-particle state), beam ribbons, streaks, glow rings, shock shells, flat rings | keep procedural |
| `E17_hit_contacts_vfx` | small damage-resolved contact markings on shields/hull/impacts (deterministic pure geometry function) | keep procedural |
| `E18_shield_bubbles` | view-aligned unit-sphere shell with the rim Fresnel baked into per-vertex alpha; one list per strength bucket; per-quadrant flash faces | keep procedural |
| `E19_planet_shield_dome` | additive view-aligned translucent dome over a colonized world whose planet_shield_generator is operational, with absorption flash | keep procedural |
| `E20_selection_rings` | rotating line rings around selected units, colour-coded by hull fraction (red <0.35, amber <0.7) | keep procedural |
| `E21_fog_of_war_mask` | projected quads charting remembered terrain/explored space, composited after the planets and before planet shields | keep procedural |
| `E22_floating_texts` | sim floating texts (e.g. build rejections) projected to screen coords and blitted by the HUD | keep procedural |
| `E23_menu_cinematic_3d_background` | the main menu / non-replay menu backdrop: a baked JPEG movie of a 3D battle scene, blitted as a full-screen textured quad | owner decision required |
| `E24_presentation_campaign_overlay` | 2D mission-brief / outcome overlay panels | keep procedural |
| `E25_hud_and_menu_2d_layers` | the HUD overlay and menu chrome drawn as textured 2D quads | keep procedural |

### 7.1 Resolved by the owner, 2026-10-16

| element | owner decision, 2026-10-16 |
|---|---|
| E05_planet_surface_sphere | in scope — bring into the catalogue (`- are planet bodies (procedural equirect-textured spheres, shared display list with the sky dome) permanently out of the model catalogue, o…`) |
| E07_asteroid_field_rocks | in scope — bring into the catalogue (`- asteroid/neutral environment props are per-instance procedural (seeded private RNG). Roadmap 3.1 explicitly includes 'neutral/environment…`) |
| E23_menu_cinematic_3d_background | in scope — bring into the catalogue (`- the menu 3D backdrop is a baked JPEG movie (assets/menu/battle.zip) rather than a live render. Roadmap L164 requires menus to use the sam…`) |

The elements listed in section 7 above that are **not** in section 7.1 keep their `keep procedural` proposal. They were not put to the owner, so they are carried as proposals rather than presented as approved; say so if any of them should change.

## 8. Approved scope and its limits

Owner decision `approved-trio-2026-10-16`; preserved in draft PR #114 (feat/blender-approved-trio-checkpoint).

| binding | status | runtime asset | generator in this tree |
|---|---|---|---|
| `ship:rebel:battleship` | approved_blender_draft_unmerged | `assets/models/alliance_battleship.mesh.json` | `render/faction_ships.py:_alliance_capital:120` |
| `ship:rebel:frigate` | approved_blender_draft_unmerged | `assets/models/alliance_frigate.mesh.json` | `render/faction_ships.py:_alliance_line:391` |
| `station:rebel:shipyard` | approved_blender_draft_unmerged | `assets/models/alliance_shipyard.mesh.json` | `render/faction_stations.py:_alliance:103` |

Approval does **not** cover:
- any other hull, station, satellite or installation
- any other faction
- catalogue-wide rollout or a production default switch
- Windows or packaged-build acceptance

The three approved bindings still draw the procedural generator above in this tree; their authored overrides live only in the draft checkpoint.

## 9. Proposed review batches

Ordered so that each batch settles a question before the next one spends effort on it; counts are current bindings. **Owner decision 2026-10-16: approved in this order** (`s01-batch-plan`), as a plan and as scope — not as approval of any model design, which S06 still requires per asset with an enumerated list.

| batch | contents | bindings | question the owner answers |
|---|---|---|---|
| B1 | combat hulls, one faction (`rebel`) | 7 | does the approved battleship/frigate treatment extend to the rest of the fleet? |
| B2 | squadrons and logistics hulls, all factions | 15 | are squadron members and transports authored individually or as shared props? |
| B3 | stations, by faction | 40 | does the approved shipyard treatment extend to the other station kinds? |
| B4 | satellites and planet installations | 24 | orbit/surface hardware in scope at all? |
| B5 | environment props | 13 | in scope per the owner decision: planet bodies and the asteroid field are authored here; the sky/star/nebula/jump-point proposals still stand unless objected to |

## 10. Open items

- R17/R18/R19/R20 all funnel into station_mesh but are kept as separate rows because each is a distinct GL emission site with its own line reference; roadmap L164 requires previews and construction stages to be migrated too, so merging them would hide work.
- game/benchmark.py:199 instantiates Renderer but lives in game/ rather than tools/ - it is neither a pure runtime gameplay path nor a tools/diag_* path; treated as a measurement harness, not a dispatch path of its own.
- The renderer's pass orchestrators (render/renderer.py:draw L413, _draw_read_only L439-509, _draw_ships L1262) are NOT listed as individual rows because they emit no geometry themselves; they are the authority for pass order and the 'skip' set (stars/nebulas/star/jumppoints/planets/planet_shields/effects/projectiles/ships/shields/sites/surface_slots/markers/rings), and every geometry-emitting path above is reachable through them.
- Whether the roadmap intends asteroid fields (E07) as authored props is unknown; recorded as owner decision rather than assumed either way.
- No 'terrain' system separate from the planet sphere (E05) was found in render/ - 'terrain' in the roadmap has no independent implementation to inventory today.

### 10.1 Counted evidence behind the audit

| command | raw count | note |
|---|---|---|
| `grep -rn 'ship_mesh\\|station_mesh\\|armor_loft\\|_satellite_mesh\\|satellite_mesh' render/ game/ tools/ --include=*.py \| grep -v __pycache__ \| wc -l` | 56 | all mesh-symbol references (defs + call sites) |
| `grep -rn 'ship_mesh(\\|station_mesh(\\|armor_loft(\\|_satellite_mesh(\\|satellite_mesh(' render/ game/ tools/ --include=*.py \| grep -v 'def ' \| grep -v __pyc…` | 31 | call sites only; per-file: camera_geometry 2, faction_ships 2, faction_stations 1, fleet_geometry 6, planet_building_ge… |
| `grep -rln 'ship_mesh\\|station_mesh\\|armor_loft\\|_satellite_mesh\\|satellite_mesh' render/ game/ tools/ --include=*.py \| grep -v __pycache__ \| wc -l` | 10 | distinct files touching mesh dispatch |
| `grep -n 'ship_mesh(\\|station_mesh(\\|_ship_display_list(\\|_station_detail_list(\\|_emit_detail_mesh(\\|_emit_detail_hull(' render/renderer.py` | 21 | exact renderer mesh call sites, incl. renderer.py:643 station_mesh, renderer.py:1448 _ship_display_list, renderer.py:14… |
| `grep -n 'self\._lit_box(\\|self\._out_pyr(\\|self\._dome(\\|self\._octa_tube(\\|self\._capsule(\\|self\._armor_loft(\\|self\._station_ring(\\|self\._emit_glazi…` | 130 | ALL 130 hits fall inside _emit_hull (L2130-2286), _emit_glazing (L2329-2355) and _emit_station_lit (L2528-2669). _stati… |
| `grep -rn '_emit_hull\\|_emit_glazing\\|_station_lit_list\\|_emit_station_lit\\|_station_ring' tests/ tools/ --include=*.py` | 2 | tests/test_modern_fleet.py:38 calls renderer._emit_hull(shape,'base') (the ONLY caller anywhere); tools/diag_gfx3.py:11… |
| `grep -rn 'battleship_mesh\\|frigate_mesh\\|shipyard_mesh\\|authored_mesh' render/ tools/ tests/ --include=*.py \| wc -l` | 23 | render-side authored call sites: faction_ships.py:127/129/446/448, faction_stations.py:460/463, authored_mesh.py:94/99/… |
| `grep -rn 'rebel:battleship\\|"shipyard"\\|faction == "rebel"' render/ --include=*.py` | 6 | renderer.py:1420, 1461, 1997, 2408, 2547; faction_stations.py:459 - the hardcoded trio literals plus the dead _station_… |
| `grep -c 'glBegin\\|glCallList\\|glVertex3f\\|glDrawArrays\\|glNewList' render/*.py (per file)` | renderer.py 77 symbol-bearing lines; hud.py 2; menus.py 2; fog.py 1; cinematics.py 1; presentation.py 1; hit_effects.py 0; clean_classic.py 0; classic_screens.py 0; recovery_overlay.py 0; replay_library.py 0; save_library.py 0 | only renderer.py emits 3D world geometry; hud/menus/fog/cinematics/presentation emit 2D ortho quads only |
| `grep -rn 'Renderer(' --include=*.py . \| grep -v __pycache__ \| grep -v /tools/ \| grep -v /tests/` | 6 | main.py:292 (live), main.py:366 (prepared replay renderer), game/benchmark.py:199, plus artifacts/alliance_blender_trio… |
| `ls tools/diag_*.py \| wc -l ; ls tools/probe_*.py \| wc -l` | 70 diag tools, 11 probe tools | large tooling surface; representative dispatch-bearing tools inventoried as T02-T05 |
| `ls -la assets/models/` | 3 | exactly the three Blender trio meshes exist; no other authored mesh assets |
| `find . -name 'capture_showcase*'` | 0 | tools/capture_showcase.py named in the task does NOT exist in this repo |

## 11. Verification commands

```
# inventory regeneration is stable (second run must not change the files)
.venv/bin/python tools/art/build_model_inventory.py
.venv/bin/python tools/art/build_model_inventory.py --check

# every cited symbol still exists at the base
python3 - <<'PY'
import json,re,pathlib
root=pathlib.Path('.')
inv=json.loads((root/'art/manifests/model_inventory.json').read_text())
for r in inv['rows']:
    for f in (r['generator'], r['dispatch_site']):
        p,sym,ln=f.rsplit(':',2); L=(root/p).read_text().splitlines()
        assert re.match(r'\s*(def|class) '+re.escape(sym)+r'\B', L[int(ln)-1]), f
print('all row references resolve')
PY
```

## 12. Owner decisions recorded

`s01-scope-2026-10-16`, decided by owner (Lukasz Jawor), in chat; raw wording preserved below, bound to commit `9dd678570ab6e85878d34533625026e0ec1f63c5` (PR #115) and this document.

| question | answer | owner's own wording |
|---|---|---|
| `E05_planet_surface_sphere` | in scope — bring into the catalogue | “1.) scope exceptions: let bring them into catalog.” |
| `E07_asteroid_field_rocks` | in scope — bring into the catalogue | “(same answer)” |
| `E23_menu_cinematic_3d_background` | in scope — bring into the catalogue | “(same answer)” |
| `s01-declared_unreachable_keys` | keep — plan the hulls | “2.) plan the hulls . Battleshipo and capitol shoudl be buidl in ship yard, bomber in fighter yard.” |
| `s01-batch_order` | as recommended: B1 Alliance combat hulls, then B2 squadrons/logistics, B3 stations, B4 satellites and planet installations, B5 environment props | “3.) as recomendet” |
| `s01-batch_plan` | approved — as a plan and as scope. This does not approve any model design, and S06 still requires per-asset owner approval with an enumerated list. | “4.) approved” |

What this does not authorize:
- merging PR #114 or activating the trio in production
- changing the production default (that is S11, and only after S10)
- any specific model design — S06 requires per-asset owner approval with an enumerated list

Consequences carried into the inventory:
- Environment props move from 'scope decision required' to in-scope work. The planet kinds (E05) and the asteroid field (E07) become authoring targets in batch B5.
- The menu backdrop (E23) gets its own inventory row so the decision is bound to a binding rather than to a sentence: menu:cinematic:backdrop.
- The three unreachable SHIP_KEYS stay in the registry as planned hulls with a recorded production site.
- The starfield sky dome, star, nebula and jump point were proposed keep-procedural and were not among the questions asked; they are carried as proposed, not as owner-approved.

### 12.1 Planned hulls

Battleships and capital ships build at the shipyard; bombers build at the fighter platform (the owner's 'fighter yard'). Mechanism: game/systems/construction.py decides buildability from the station's builds_ships list: an exact ship id, or ['*'] for any ship

| mesh key | data row today | production site | status |
|---|---|---|---|
| `syndicate:battleship` | none | `shipyard` | planned_owner_confirmed |
| `syndicate:supercapital` | none | `shipyard` | planned_owner_confirmed |
| `syndicate:bomber` | none | `fighter_platform` | planned_owner_confirmed |

`fighter_platform.builds_ships` today: `imperial_tie_squadron`, `imperial_tie_bomber_squadron`, `rebel_x_squadron`, `rebel_y_squadron`, `confed_vulture_squadron`, `confed_bomber_squadron`, `syndicate_raid_squadron`. This list is explicit, so a new bomber hull is unbuildable until its data id is added to it. That is a data change S06 must make alongside the hull, not a model change.

## 13. Campaign coverage

Read from assets/data/campaign/campaign.json: 11 missions, 11 distinct ship data ids and 2 station ids referenced; **0 campaign-only models**.

- every ship and station the campaign references resolves to an inventoried binding
- ship ids referenced: `imperial_battleship`, `imperial_corvette`, `imperial_crew_transport`, `imperial_cruiser`, `imperial_frigate`, `imperial_supercapital`, `imperial_tie_squadron`, `rebel_corvette`, `rebel_frigate`, `rebel_x_squadron`, `syndicate_corvette`
- station ids referenced: `mining_station`, `trade_station`
- unresolved model-shaped references: none

`campaign_prop` is therefore empty because the campaign reuses existing bindings, not because campaign content was skipped.
