# STAR ARMADA — Design Document

This is the design contract for the vertical slice. Every claim here is implemented and
covered by the headless test suite (`tests/`).

## 1. Player fantasy
You are an admiral, not a squad leader. You gather resources, establish infrastructure,
research, assemble fleets, and command them in set-piece battles. Individual unit micro
matters far less than composition, positioning and timing.

## 2. Resources
| Resource | Source | Sink |
|---|---|---|
| Credits | planets, trade stations, mining bonus | everything (soft) |
| Materials | mining stations (asteroid fields), industrial planets | stations, capitals, defenses |
| Energy | gas-giant platforms, energy planets, reactors | advanced ships, shields, abilities |
| Crew | command stations, crew planets | ships, stations, squadrons |
| Command capacity | command stations (+tech, +military planets) | fleet size/weight |

Ships and stations cost a mix; destroyed ships refund a fraction of crew. Command
capacity gates spam: fighter squadron 1, corvette 2, frigate 4, cruiser 8, battleship 15,
supercapital 30.

## 3. Battlefield geography
Maps are JSON: planets (type → economic bonus, colonizable), asteroid fields (mining
targets), nebulae (sensor interference: −70% detection inside), hyperspace jump points
(prep-time strategic jumps), star, starfield. Resource placement creates contested
middle, safe flanks, chokepoints.

## 4. Combat model
- **Shields**: 4 quadrants (front/rear/left/right). Regen when not hit recently.
  Shield-gen subsystem damage reduces max/regen.
- **Hull**: thresholds 90/70/50/30/10% escalate subsystem degradation; visible damage
  state for the renderer (smoke/fire at low hull).
- **Subsystems**: engines (speed), weapons (damage), sensors (range), shield_gen,
  hangar (launch/recovery), life_support (onboard crew survival). Chipped by every
  hull hit; ion weapons hammer them. Below 25% life support, crew die gradually;
  zero crew leaves an intact, non-operational abandoned hull.
- **Weapons** (data-driven): laser, turbolaser, ion, missile, torpedo, plasma, beam,
  point-defense, tractor. Each has range, reload, accuracy, projectile speed,
  shield/armor multipliers, subsystem multiplier, hardpoint arc.
- **Abilities**: engine overdrive, emergency shield recharge, weapon overcharge,
  EMP burst, fighter scramble, repair drones, hyperspace jump. Cooldown + energy.
- **Experience**: damage dealt/destroyed kills → levels Recruit→Legendary (+accuracy,
  +regen, −cooldown, +speed, +sensors). Modest per level so veterans stay killable.

## 5. Fleet & formations
Group ships into a fleet (F key) with an optional commander archetype
(aggressive/defensive/logistics/recon). Fleets move in formation slots
(line/wedge/column/diamond/screen/escort) around the flagship; slot assignment is
stable and re-computed on membership change. Formation spacing scales with ship size.

## 6. Economy decisions
Mining stations cost upfront and pay back over minutes; trade stations generate passive
credits but are fragile; planets are long-term multipliers. Expansion beats turtling,
but expansion requires defense. AI mirrors this: it expands when safe, turtles when
threatened.

## 7. AI doctrine
Strategic (1 Hz): keep ≥ N miners; expand when safe (credits over threshold); build
defense near base when threatened; research when income is strong; assemble attack
fleet when fleet strength ≥ player's known strength × courage; attack weakest known
enemy structure; retreat damaged capitals to repair.
Tactical (5 Hz): interceptors chase fighters; bombers dodge to nearest carrier;
critically damaged ships fall back; carriers stay behind the line.

## 8. Victory
Skirmish: destroy all enemy command stations. Campaign missions can override with
objective lists (MissionSystem).

## 9. Originality
No third-party code, assets, names-as-trademarked-content or sounds. The JSON data is
the mod surface: rename/retheme everything without touching code.

## 10. Boarding and capture
Eligible frigate-and-larger ships deploy damageable boarding craft against detected
enemy ships or stations with shields down. Staffed targets also require a disabled
engine, weapon or life-support subsystem. Surviving attackers fight for control,
crew the captured hull and transfer ownership; empty hulls offer no resistance.
Press **B** or use the inspector's boarding button, then select the target.
See [BOARDING.md](BOARDING.md) for defaults, interruption rules, crew conservation,
save/replay coverage and explicitly deferred optional captured-vessel features.