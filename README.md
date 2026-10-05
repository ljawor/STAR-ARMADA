# STAR ARMADA

**STAR ARMADA** is a large-scale, fleet-based real-time strategy game in the spirit of
classic space-fleet RTS titles (Armada II / Fleet Operations era). It runs entirely on
Python 3 — deterministic simulation, AI, OpenGL rendering via pygame-ce and procedural audio.

**Current release: [v0.5.1](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.5.1)**
— macOS DMG and Windows ZIP, including combat ranks, fleet-selection HUD, LAN
multiplayer, alliances, and close-zoom/minimap camera fixes.

The setting is an original space-opera universe. Prototype faction/ship names are
placeholder-style data (Imperial / Rebel / Confederacy / Syndicate) so the feel reads
familiar, but **no copyrighted assets, code, maps, sounds or text from any commercial
game are used**. Every ship, weapon, faction, tech and map is a JSON data file — replace
them and the game changes with zero code edits.

---

## Quick Start

```bash
cd STAR-ARMADA
python3 -m venv .venv           # Python 3.11 recommended
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

python main.py                  # title screen → main menu → game
python main.py --skirmish       # straight into a skirmish vs AI (skips menus)
python main.py --smoke          # automated rendered gameplay smoke
python main.py --fullscreen     # start fullscreen
python main.py --load saves/quicksave.json
python main.py --mods example   # load a data override mod
```

For packaged builds, download the DMG or ZIP from the release above; Python is
not required. On macOS, drag the app to Applications. The app is ad-hoc signed,
not Apple-notarized; first launch may require right-click → Open. On Windows,
extract the entire ZIP and run `STAR ARMADA.exe` (unsigned).

## Controls

| Input | Action |
|---|---|
| Left-drag | Box select |
| Left-click | Select unit / station |
| Right-click | Attack target / colonize planet; attack-move on empty ground |
| Right-drag | Rotate camera |
| S | Stop selected units (pan down when nothing is selected) |
| H | Follow selection (legacy alias for Space) |
| Ctrl+1..9 | Assign control group |
| 1..9 | Select control group |
| F | Fleet panel (group selected ships into a fleet, pick commander) |
| J, then left-click | Hyperjump selected ships to a destination on the battlefield or minimap; explored and unexplored areas are allowed |
| Esc / right-click during jump selection | Cancel destination selection |
| Space | Follow selection |
| M | Toggle follow / free camera |
| Q / E | Rotate camera |
| WASD / arrows | Pan; manual pan releases follow (S stops when units are selected) |
| Mouse-wheel | Zoom (tactical → fighter scale); scroll roster/abilities when hovering their HUD lists |
| Left-click minimap | Recenter the camera and release follow mode |
| X | Tactical overview |
| P | Pause / resume |
| F5 / F9 | Quick save / quick load |
| F10 | Toggle mouse grab |
| ESC | Cancel placement / close fleet panel first; otherwise return to main menu |
| F11 | Toggle fullscreen |

## Combat experience and ship ranks

Ships and fighter squadrons begin at **rank 1**. Fighting earns XP from actual
shield and hull damage dealt to enemies (overkill is excluded), plus a kill
reward based on the destroyed unit's maximum hull. Own/allied units, neutral
terrain, dead attackers and station attackers cannot provide ship XP.
Already-fired projectiles still inflict damage after their shooter dies, but
cannot award that dead ship XP.

Every catalogue ship/squadron declares `max_rank` (currently **5**). Promotions
add **5% weapon damage** and **5 percentage points of incoming damage reduction**
per rank: rank 5 has +20% attack and 20% damage reduction. Reduction applies to
both shields and hull, not just shield capacity. Existing veteran utility/shield
bonuses remain, but there is no second veteran weapon-damage multiplier.

Balance lives in `assets/data/game_rules.json`: `experience.levels` defines
cumulative thresholds, scaled by each ship's `veteran_xp / 100`;
`experience.max_effective_level` is the global cap, and
`experience.per_level.attack_bonus` / `defense_bonus` configure promotions.
The effective cap is the minimum of the ship cap, global cap, available
thresholds and safety cap 5. XP can continue accumulating at the cap. DataStore
validates caps, thresholds and bonuses after mod overrides; older ship
definitions without `max_rank` default to 5, and old saves derive rank from XP.
Full-precision saves/replays preserve XP and projectile shooter identity.

## Fleet selection and tactical presentation

Selecting several ships shows a scrollable/paged roster rather than only one
representative ship. The HUD combines the selected owned units' special abilities,
with readiness, cooldown and energy feedback; commands apply only to eligible
owned recipients. Jump destination selection and targeted abilities are mutually
exclusive and can be canceled. Construction orders and progress are laid out
separately, including on smaller windows.

Ship sizes are normalized from rendered hull geometry: the largest hull is
**5× a corvette**, with a shared tactical readability scale. Metal hulls,
procedural planets/deep space, directional shield impacts, hull-hit effects and
per-weapon procedural audio distinguish fleets and combat. Close zoom now avoids
visible base geometry without changing requested zoom limits; ships behind the
camera no longer inflate into giant mesh planes. Picking, effects and audio use
the same effective camera view, and camera obstacle filtering avoids unnecessary
distant hidden-fleet visibility scans.

## Menus

`main.py` now starts at the **title screen** → **main menu** (Skirmish / Campaign /
Multiplayer / Settings / Quit). Settings (music/SFX volume, fullscreen, autosave,
camera pan speed) persist to `saves/settings.json` in source runs. Packaged builds
store settings, saves and campaign progress outside the application bundle:
`~/Library/Application Support/STAR ARMADA` on macOS and `%APPDATA%\STAR ARMADA`
on Windows. The **Campaign** screen lists the 10-mission
"Rise of the Outer Armada" chain (`assets/data/campaign/campaign.json`); each mission
has a briefing (story, objectives, enemy preview) before LAUNCH, and in-game objectives
are tracked live in the HUD with COMPLETE/FAILED states.

## Skirmish maps and setup contract

The built-in skirmish catalogue is restricted to these four map IDs. Capacity is
**total players**, including the human; selecting fewer opponents uses the first
consecutive spawn slots and leaves the remaining terrain/resources in place.

| Map ID | Public name | Capacity | Layout |
|---|---|---:|---|
| `skirmish01` | Sector Duel — Kotarri Sector | 2 | Original duel; legacy geometry, starts and loadout preserved |
| `skirmish02` | Trinary Reach | 3 | Equilateral triangle, personal expansion pockets, contested central mine |
| `skirmish03` | Crossroads | 4 | Open corner quadrants with broad flanking lanes and four inner reserves |
| `skirmish04` | Nebula Frontier | 4 | Cardinal starts, diagonal gas-giant barriers and sensor-reducing nebula banks |

New maps give each slot the same nearest mining-field distance and an equally
accessible temperate colony, with room for station construction. Kotarri retains
its existing asymmetric colony types and distances rather than changing campaign
or integration-fixture gameplay. Nebulae reduce sensors; they are not solid walls.
Each JSON exposes `name`, `description`, `max_players`, `bounds`, player `start`
positions and neutral geometry (`asteroid_fields`, `gas_giants`, `planets`,
`nebulas`, `jump_points`) for a public terrain preview, not live enemy intelligence.

Setup requirements/contract:

- One human in slot 0 plus **1–3 AI players**, limited to map capacity minus one.
  Choose **Team 1–4** for each player: matching teams are allies; different teams
  are enemies. At least two active teams are required to launch.
- Allied ships and stations are always visible, including allied AI fleets outside
  your own sensors. Allies share sensor coverage and exploration, but not control
  of each other's units. Unseen enemies remain hidden.
- Allies cannot attack each other. Trade routes connect only distinct **own or
  allied trading stations**, never enemy stations. Convoys cannot deliver back
  to their source market. Restored legacy convoys without recorded source-market
  identity remain idle and generate no delivery income; build new routes instead.
- Skirmish and LAN victory requires eliminating **every enemy ship, squadron and
  station**. Destroying only the enemy command station is insufficient. Victory
  belongs to the surviving team, including an ally whose own forces were eliminated.
  Campaign objectives retain their mission-specific rules.
- Active players must have distinct colors from **blue, red, green, purple,
  orange, cyan, yellow, pink**. Color identifies the player independently of faction.
- Difficulty is **easy**, **normal** (default), or **hard**, applied to AI players.
- Faction choices use registered data IDs: `imperial` (Galactic Imperium), `rebel`
  (Free Systems Alliance), `confederacy` (Automated Legions), and `syndicate`
  (Outer Rim Syndicate). Syndicate remains marked non-playable in the faction data;
  its prototype skirmish support should not be mistaken for full faction parity.
  Faction data determines starting resources and available engineering/combat hulls.
- Default map slots are all Imperial, with one command station, one shipyard, one
  constructor, two squadrons and two corvettes per slot. The JSON loadout uses
  generic ship roles, resolved to faction-specific hulls when the game starts.
- The setup payload has `map_id`, integer `ai_count`, four-slot `colors` and
  `factions` lists, `ai_difficulty`, and an optional four-slot integer `teams` list
  (values 0–3). Omitting teams retains free-for-all defaults; inactive choices do
  not participate. Setup conversion must not mutate the shared DataStore map definition.

Focused map acceptance checks (real headless GameManager starts, actual starter
footprints/gravity clearance, resource access, legal AI sites and short deterministic
AI runs; not a substitute for full-match or rendered-menu playtesting):

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_skirmish_maps -v
```

## LAN multiplayer

Open **Multiplayer** to host or join by LAN IPv4 address. The host selects a
**TCP port** (default **7777**) and uses the same four maps as Skirmish, with
**2–4 human players** and optional AI within map capacity. Cooperative play puts
humans on a shared team against AI; free-for-all uses separate teams.

For setup, Windows Firewall commands, and troubleshooting, see **docs/LAN.md**.
Firewall rules are not changed automatically. All computers must use the same game
version and simulation content. LAN matches disable independent pause and save/load.

## Gameplay loop

```
BUILD mining stations → GATHER credits/materials/energy → RESEARCH upgrades
→ BUILD fleet (fighters → corvettes → frigates → cruiser → battleship)
→ FORM fleets with commanders → FIGHT and earn ranks
→ ELIMINATE all enemy ships, squadrons and stations → TEAM VICTORY
```

## Sensors and fog of war

Space has three visibility states: **unexplored**, **explored but outside sensor coverage**,
and **currently detected**. Exploring a region charts its fixed map features; it does
not grant permanent tracking of enemy fleets. Enemy ships and stations require current
friendly sensor coverage to appear on the battlefield or minimap and to be targeted.

Every ship and station uses its own data-defined `sensor_range`. Friendly teammates
share detection. Sensor stations extend the network significantly: their base range is
5,200 units, compared with 3,000 for command stations and 1,000–2,000 for most other
stations. Ship ranges vary by class and faction. Sensor damage, jamming, nebulae,
research and recon commanders modify effective range.

Losing detection breaks the target lock: weapons cannot fire new shots or keep chasing
an unseen target's live position. Already-fired ballistic shots continue travelling;
guided projectiles cannot keep tracking a target outside sensor coverage. A remote
friendly sensor can provide detection for another ship's longer-range weapons.

## Feature matrix (vertical slice vs full spec)

| Spec section | Status |
|---|---|
| 3D tactical camera, minimap recenter, geometry-safe close zoom | ✅ implemented |
| Box/drag select, control groups, fleets | ✅ prototype |
| Four data-driven factions | ✅ faction-selectable setup; Syndicate remains a prototype, not full parity |
| Resources: credits/materials/energy/crew, command capacity | ✅ prototype |
| Stations: command, mining, shipyard, research, defense, sensor, fighter platform, repair, trade, energy relay | ✅ prototype |
| Planets (colonize, bonuses), asteroid fields, nebulae, jump points | ✅ prototype (colonize: build) |
| Ships: fighter→supercapital, construction ship | ✅ prototype |
| Fighter **squadrons** with losses + carrier reinforcement | ✅ prototype |
| Hull / shields / **subsystem damage** (engines, weapons, sensors, shields, hangar) | ✅ prototype |
| Directional shields (front/rear/left/right) | ✅ prototype |
| Weapons: laser/turbolaser/ion/missile/torpedo/plasma/point-defense/beam (data-driven) | ✅ prototype |
| Special abilities (overdrive, shield recharge, EMP burst, scramble, repair drones, jump) | ✅ prototype |
| Hyperspace jump (two-layer movement) | ✅ prototype (jump points + prep time) |
| Formations: line/wedge/column/diamond/screen/escort | ✅ prototype |
| Fleet command + commanders (aggressive/logistics/recon/defensive) | ✅ prototype |
| Technology tree (data-driven, per faction) | ✅ prototype |
| Combat XP, per-ship capped ranks, attack and defense promotions | ✅ implemented; rank/XP HUD |
| Strategic + tactical AI, update-frequency tiers | ✅ prototype |
| Skirmish/LAN team victory: eliminate all enemy forces | ✅ implemented; shared allied detection/exploration |
| Save / load (quick save F5 / load F9) | ✅ implemented; disabled during LAN matches |
| Procedural audio (original, no assets) | ✅ prototype |
| Minimap, fleet roster/ability union, rank inspector, build/research progress | ✅ implemented |
| Title screen, main menu, settings menu (music/SFX volume, fullscreen, autosave, pan speed — persisted to `saves/settings.json`) | ✅ prototype |
| Campaign: 10-mission chain with briefing screens, live objectives panel, progress persists across sessions | ✅ prototype |
| Victory conditions: annihilation, planet majority, economic, timed (data-driven) | ✅ prototype |
| Trade convoys between trade stations + raiding (salvage loot) | ✅ prototype |
| Objectives: build/destroy/colonize/survive + escort_convoy, hold_point | ✅ prototype |
| Autosave ring (3 rotating slots) | ✅ prototype |
| LAN host/join, 2–4 humans, optional AI, configurable TCP port | ✅ implemented; matching version/content required |
| Deterministic lockstep, serialized commands, replay infrastructure | ✅ implemented and tested |
| Four skirmish maps, player factions/colors/teams, AI difficulty | ✅ implemented; 2–4 total players by map |
| 8-player skirmish, boarding/capture | 🔲 planned (see DEV_PLAN.md) |

## Repository layout

```
main.py                  entry point
game/                    simulation core (no rendering imports)
  core/                  vectors, entity, events, commands, state, manager, ids
  data/                  loaders + dataclasses mirroring the JSON schema
  systems/               simulation systems (movement, combat, economy, ...)
  ai/                    strategic & tactical AI
  net/                   LAN lobby, transports, lockstep and replay
render/                  OpenGL renderer, camera, UI, minimap, menus, audio, input
assets/data/             JSON: factions, ships, weapons, tech, maps, abilities, campaign
assets/audio/            (generated at runtime — no binary assets committed)
tests/                   headless simulation tests
docs/                    design + architecture notes
```

## Testing

```bash
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -v
```

Tests run the **real simulation headless** — no window, no GPU — covering economy,
combat, subsystem damage, formations, squadrons, research, AI, save/load, victory
conditions, trade convoys, mission objectives and the full
build→gather→research→fleet→attack→win loop. The v0.5.1 release passed **525
automated tests**, plus **40 real SDL/OpenGL before/after camera cases** and
independent correctness/performance review. Render diagnostics in `tools/` need
a working window server/OpenGL context; they are separate from headless tests.

## Releases

**[Download v0.5.1](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.5.1)**:

- **macOS:** `STAR-ARMADA-v0.5.1-mac.dmg`
- **Windows:** `STAR-ARMADA-v0.5.1-win.zip`

The published DMG passed image integrity, signature, version and inspected
bundled-code checks, plus a gameplay smoke from a read-only mount. The Windows
ZIP passed native CI build, archive/executable/data integrity checks. Both
assets matched their published SHA-256 hashes. **Interactive Windows gameplay
was not tested.**

Tagged versions (`v*`) trigger native macOS and Windows builds and GitHub Release
publication. Version is defined once in `game/__init__.py`; merge the version
bump through a PR before tagging its merged commit. See `docs/PACKAGING.md` for
local builds (`./scripts/build_mac.sh`).

## Completed development

| Release | Delivered |
|---|---|
| **v0.5.1** | Close/very-close base camera safety, minimap recenter/follow correction, behind-eye ship-size fix, consistent projection/picking/audio, and large-fleet camera query optimization |
| **v0.5.0** | Combat XP and capped ship ranks with attack/defense bonuses; selected-fleet roster and combined special abilities; construction-progress layout fixes; alliances/team elimination and normalized hull sizes |
| **v0.4.0** | LAN host/join with human and AI slots and selectable port; click-targeted hyperjump; combat standoff/orbit behavior; metal hulls, planets, deep-space and shield/hull impact graphics |
| **v0.3.0** | Per-weapon combat audio/pitch fixes, layered explosions, reachable trade convoys, and writable user data outside frozen application bundles |
| **v0.2.0** | Menus/settings, 10-mission campaign, data-driven victory conditions, trading/raiding, escort/hold-point objectives and rotating autosaves |

### Still in development

The game remains a playable prototype, not the full design specification.
Eight-player matches, boarding/capture, expanded campaign scripting/cinematics,
full faction parity, in-game mod management and further rendering optimization
remain development work. Current skirmish/LAN capacity is **2–4 total players**,
limited by the selected map. See `docs/DEV_PLAN.md` for the broader plan; the
feature matrix above describes the implemented release behavior.

## License / originality

All code and data in this repository are original. Ship/faction names are data; swap
`assets/data/*.json` for your own universe. Mechanics are inspired by the classic
fleet-RTS genre; no third-party code or assets are included.