# STAR ARMADA — Architecture

## 1. Layering (strict)

```
┌─────────────────────────────────────────────────────────┐
│  render/  (OpenGL, camera, UI, audio, input mapping)    │  reads sim state only
├─────────────────────────────────────────────────────────┤
│  game/systems/ + game/ai/  (simulation)                 │  mutate GameState via systems
├─────────────────────────────────────────────────────────┤
│  game/core/ (state, entities, commands, events, ids)    │  pure data + logic, no I/O
├─────────────────────────────────────────────────────────┤
│  game/data/ (JSON loaders, schema dataclasses)          │  assets/data/*.json
└─────────────────────────────────────────────────────────┘
```

- **Simulation never imports pygame or OpenGL.** The entire game loop can run
  headless (`--headless-test`, tests). This is the foundation for the later
  deterministic-lockstep multiplayer architecture (spec §31).
- **Rendering is a pure view.** `render/renderer.py` reads `GameState` and draws.
  It may add transient visual-only state (effect list, camera) that never feeds back
  into simulation.
- **UI issues PlayerCommands.** The UI never mutates game state directly. Every player
  action becomes a `PlayerCommand` pushed into `GameState.command_queue`, consumed by
  `GameManager.step()` at the next tick. This is exactly the shape needed for
  lockstep networking later: serialize commands + seed, replay, verify.

## 2. Update pipeline (one tick)

```
GameManager.step(dt):
  1. consume player commands      (CommandQueue)
  2. MovementSystem.update        (accelerate/turn toward move_target/attack_target)
  3. SeparationSystem.update      (soft collision avoidance, spatial hash)
  4. SquadronSystem.update        (fighter slots, carrier reinforcement)
  5. WeaponSystem.update          (acquire targets in range, fire, spawn projectiles)
  6. ProjectileSystem.update      (move, hit detection via spatial hash)
  7. DamageSystem.resolve         (shields quadrants → armor → hull → subsystems → xp)
  8. AbilitySystem.update         (cooldowns, durations, effects)
  9. EconomySystem.update         (income, crew, command capacity, trade)
 10. ConstructionSystem.update    (build queue on stations, construction ships, planets)
 11. ResearchSystem.update        (research queues, tech unlocks)
 12. FormationSystem.update       (fleet formation slot assignment)
 13. SquadronSystem.update        (AI: bombers avoid fighters, damaged return to carrier)
 14. AIStrategic.update  (1 Hz)   (economy decisions, build order, expansion)
 15. AITactical.update   (5 Hz)   (attack/retreat/defend per fleet)
 16. VictorySystem.check          (command stations alive?)
 17. MissionSystem.check          (objectives)
```

Update-frequency tiers (spec §45): movement/projectiles every tick; tactical AI 5 Hz;
strategic AI 1 Hz; distant-fighter LOD simplification is a renderer concern plus a
`tactical_update` gate inside systems.

## 3. State & entities

`GameState` is one plain object holding **everything** mutable: entities, players,
projectiles, effects, world time, RNG. It is fully serializable (`to_dict`/`from_dict`)
— the save system is a thin wrapper (`SaveSystem.save(state, path)` = `json.dump`).

`Entity` is a dataclass with a stable integer `id` (from `IdGenerator`). Subtypes are
flags/roles, not class hierarchies: `is_station`, `is_ship`, `is_squadron`,
`is_construction`. Composition via dictionaries keeps the save format flat and modding
simple.

Units reference **data** by id (`data.ship_id == "imperial_star_destroyer"`); the
`DataStore` resolves it to `ShipData`. Balance edits are JSON-only.

## 4. Data-driven assets (spec §38)

```
assets/data/
  factions/imperial.json rebel.json confederacy.json syndicate.json
  ships/imperial.json rebel.json confederacy.json syndicate.json neutral.json
  weapons/weapons.json
  abilities/abilities.json
  technology/technology.json
  maps/skirmish01.json
  game_rules.json
```

Each ship JSON contains the full schema from spec §40: cost (credits/materials/energy),
crew cost, command cost, hull, shields, quadrants, speed/turn, weapons list, subsystem
strengths, abilities, hangar/fighter capacity, build time. The loader validates required
fields and raises on unknown weapon/ability ids — no silent typos.

## 5. Subsystem damage (spec §12/§14)

Each ship has `systems: {engines, weapons, sensors, shield_gen, hangar}` each with
`hp ≤ max_hp`. `DamageSystem.apply` routes damage: shields absorb first (per-quadrant),
then hull; each hull hit also chips subsystem HP proportional to damage; hull thresholds
(90/70/50/30/10 %) escalate subsystem degradation and trigger `unit_critical` events.
Effects: engines → speed/turn multiplier, weapons → damage multiplier, sensors →
detection range, shield_gen → shield regen/quad strength, hangar → launch/recovery rate.

## 6. Fighter squadrons (spec §11)

A squadron entity carries `fighter_count / max_fighters` rather than N entities.
Visual size scales with count. Squadrons land at carriers/stations with hangars to
reinforce (hangar system HP gates the rate). `SquadronSystem` implements behavioral
roles: interceptors chase fighters, bombers avoid interceptors and strike capitals,
damaged squadrons return for repair/reinforce.

## 7. AI (spec §20/§21/§45)

`AIStrategic` (1 Hz): income-aware build order — keep miners coming, expand when
credits exceed thresholds, tech up, build fleet up to command capacity, defends when
under attack. `AITactical` (5 Hz): per-fleet stance — retreat critically-damaged ships
toward base, focus nearest enemy, rally on attack. Both are plain systems reading/writing
the same GameState; swapping them for scripted mission AI later touches nothing else.

## 8. Multiplayer readiness (spec §31)

- All mutation flows through systems in a fixed order inside `GameManager.step`.
- Player input only enters as serialized `PlayerCommand`s.
- `GameState` serializes fully; entities have stable ids; world RNG is seeded and stored
  in state.
- Planned next: fixed-tick lockstep loop (e.g. 20 Hz sim, render interpolation),
  command log replay, checksum verification per N ticks. The seams already exist.

## 9. Performance plan (spec §44/§45)

- Spatial hash grid (`SpatialGrid`, cell 400u) for target acquisition, projectile hits,
  separation — no O(n²) scans.
- AI tiers as above; weapon retarget only when target invalid.
- Rendering: OpenGL display lists per ship class template + instanced-ish batching for
  fighters, particle pool for effects, frustum-independent (map is small in prototype;
  culling hook exists in camera).
- Object pools for projectiles/effects.

## 10. Extending

Add a ship: edit `assets/data/ships/<faction>.json` (+ weapons if new). Add a faction:
new faction JSON + ship JSON + tech section. Add a map: `assets/data/maps/`. Add an
ability/weapon: JSON + (if it needs new behavior) one small case in its system.
See DEV_PLAN.md for the phase roadmap beyond the vertical slice.