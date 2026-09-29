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
| Right-click | Order move (attack-move when cursor on enemy) |
| A | Attack-move |
| S | Stop |
| H | Hold position |
| Ctrl+1..9 | Assign control group |
| 1..9 | Select control group |
| F | Fleet panel (group selected ships into a fleet, pick commander) |
| Space | Follow selection |
| M | Toggle follow / free camera |
| Q / E | Rotate camera |
| WASD / arrows | Pan |
| Mouse-wheel | Zoom (tactical → fighter scale) |
| X | Tactical overview |
| P / F5 | Pause |
| F9 / F10 | Quick save / quick load |
| ESC | Quit (in-game ESC at mission end → main menu) |
| F11 | Toggle fullscreen |

## Menus

`main.py` now starts at the **title screen** → **main menu** (Skirmish / Campaign /
Settings / Quit). Settings (music/SFX volume, fullscreen, autosave, camera pan speed)
persist to `saves/settings.json`. The **Campaign** screen lists the 10-mission
"Rise of the Outer Armada" chain (`assets/data/campaign/campaign.json`); each mission
has a briefing (story, objectives, enemy preview) before LAUNCH, and in-game objectives
are tracked live in the HUD with COMPLETE/FAILED states.

## Gameplay loop (prototype = vertical slice)

```
BUILD mining stations → GATHER credits/materials/energy → RESEARCH upgrades
→ BUILD fleet (fighters → corvettes → frigates → cruiser → battleship)
→ FORM fleets with commanders → ATTACK enemy base → DESTROY command station → WIN
```

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