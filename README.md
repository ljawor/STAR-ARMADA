# STAR ARMADA

**STAR ARMADA** is a large-scale, fleet-based real-time strategy game in the spirit of
classic space-fleet RTS titles (Armada II / Fleet Operations era). It runs entirely on
Python 3 — simulation, AI, rendering (modern OpenGL via pygame-ce) and audio.

The setting is an original space-opera universe. Prototype faction/ship names are
placeholder-style data (Imperial / Rebel / Confederacy / Syndicate) so the feel reads
familiar, but **no copyrighted assets, code, maps, sounds or text from any commercial
game are used**. Every ship, weapon, faction, tech and map is a JSON data file — replace
them and the game changes with zero code edits.

---

## Quick Start

```bash
cd STAR-ARMADA
source .venv/bin/activate       # if you use the bundled venv
pip install pygame-ce PyOpenGL numpy   # skip if already installed

python main.py                  # title screen → main menu → game
python main.py --skirmish       # straight into a skirmish vs AI (skips menus)
python main.py --demo           # AI-vs-AI attract demo (no input needed)
python main.py --headless-test  # 1200-tick full-loop simulation test
python main.py --version
```

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
| Mouse-wheel | Zoom (tactical → fighter scale) |
| X | Tactical overview |
| P | Pause / resume |
| F5 / F9 | Quick save / quick load |
| F10 | Toggle mouse grab |
| ESC | Cancel placement / close fleet panel first; otherwise return to main menu |
| F11 | Toggle fullscreen |

## Menus

`main.py` now starts at the **title screen** → **main menu** (Skirmish / Campaign /
Settings / Quit). Settings (music/SFX volume, fullscreen, autosave, camera pan speed)
persist to `saves/settings.json`. The **Campaign** screen lists the 10-mission
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

- One human in slot 0 plus **1–3 AI opponents**, limited to map capacity minus one;
  each active slot has its own team (free-for-all).
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
  `factions` lists, and `ai_difficulty`; inactive choice slots do not participate.
  Setup conversion must not mutate the shared DataStore map definition.

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

## Gameplay loop (prototype = vertical slice)

```
BUILD mining stations → GATHER credits/materials/energy → RESEARCH upgrades
→ BUILD fleet (fighters → corvettes → frigates → cruiser → battleship)
→ FORM fleets with commanders → ATTACK enemy base → DESTROY command station → WIN
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
| 3D tactical camera (zoom/pan/rotate/bookmarks) | ✅ prototype |
| Box/drag select, control groups, fleets | ✅ prototype |
| 4 factions (data-driven) | ✅ prototype (playable: Empire) |
| Resources: credits/materials/energy/crew, command capacity | ✅ prototype |
| Stations: command, mining, shipyard, research, defense, sensor, fighter platform, repair | ✅ prototype |
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
| Experience levels (Recruit→Legendary) | ✅ prototype |
| Strategic + tactical AI, update-frequency tiers | ✅ prototype |
| Skirmish victory: destroy enemy command station | ✅ prototype |
| Save / load (quick save F9 / load F10) | ✅ prototype |
| Procedural audio (original, no assets) | ✅ prototype |
| Minimap, unit info panel, build/research panel | ✅ prototype |
| Title screen, main menu, settings menu (music/SFX volume, fullscreen, autosave, pan speed — persisted to `saves/settings.json`) | ✅ prototype |
| Campaign: 10-mission chain with briefing screens, live objectives panel, progress persists across sessions | ✅ prototype |
| Victory conditions: annihilation, planet majority, economic, timed (data-driven) | ✅ prototype |
| Trade convoys between trade stations + raiding (salvage loot) | ✅ prototype |
| Objectives: build/destroy/colonize/survive + escort_convoy, hold_point | ✅ prototype |
| Autosave ring (3 rotating slots) | ✅ prototype |
| Multiplayer / determinism tests | 🟠 architecture-ready (command queue + serializable state) |
| 8-player skirmish, boarding/capture | 🔲 planned (see DEV_PLAN.md) |

## Repository layout

```
main.py                  entry point
game/                    simulation core (no rendering imports)
  core/                  vectors, entity, events, commands, state, manager, ids
  data/                  loaders + dataclasses mirroring the JSON schema
  systems/               simulation systems (movement, combat, economy, ...)
  ai/                    strategic & tactical AI
render/                  OpenGL renderer, camera, UI, minimap, menus, audio, input
assets/data/             JSON: factions, ships, weapons, tech, maps, abilities, campaign
assets/audio/            (generated at runtime — no binary assets committed)
tests/                   headless simulation tests
docs/                    design + architecture notes
```

## Testing

```bash
python -m unittest discover -s tests -v
```

Tests run the **real simulation headless** — no window, no GPU — covering economy,
combat, subsystem damage, formations, squadrons, research, AI, save/load, victory
conditions, trade convoys, mission objectives and the full
build→gather→research→fleet→attack→win loop.

## Releases

Tagged versions build automatically on GitHub Actions (mac DMG + Windows ZIP):

```bash
git tag v0.3.0 && git push origin v0.3.0
```

Latest: **v0.3.0** — rebuilt combat audio (per-weapon voices, no more 2x-pitch
bug), professional layered explosions, trade convoys visible on the map,
reachable trading, and a fix for the crash when quitting from a menu. Earlier:
v0.2.0 — menus + settings, 10-mission campaign, victory conditions, trade
convoys, escort/hold-point objectives, autosave ring. See `docs/PACKAGING.md`
for local builds (`./scripts/build_mac.sh`).

## License / originality

All code and data in this repository are original. Ship/faction names are data; swap
`assets/data/*.json` for your own universe. Mechanics are inspired by the classic
fleet-RTS genre; no third-party code or assets are included.