# STAR ARMADA

**STAR ARMADA** is a large-scale, fleet-based real-time strategy game in the spirit of
classic space-fleet RTS titles (Armada II / Fleet Operations era). It runs entirely on
Python 3 — deterministic simulation, AI, OpenGL rendering via pygame-ce and procedural audio.

**Current release: [v0.10.1](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.10.1)**
— published October 11, 2026, with macOS DMG and **unsigned Windows ZIP**.
Fixes quiet ship/fighter firing sounds and silence after live volume changes;
includes v0.10.0 planetary hardware and HUD improvements. Downloaded hashes,
three inspected runtime modules and all 15 tracked assets match tagged source;
read-only frozen macOS smoke passed. Trusted Windows certificate signing (#45),
native listening/Windows gameplay, Cocoa wheel-input QA and mixed-platform LAN
acceptance remain open. Smart App Control may still block the unsigned Windows build.

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
| B, then left-click | Board a detected shields-down enemy ship/station with an eligible ship; otherwise toggle build menu |
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

## Boarding, crew and life support

Ships and stations carry onboard crew and damageable life support. Failing support
kills crew gradually; zero crew leaves an abandoned intact hull. Frigate-and-larger
ships can deploy real boarding craft against detected enemy ships/stations
with all shields down, fight for control and capture them. Select a capable ship,
press **B** or click **Board enemy hull**, then click the target. Successful capture
stabilizes life support to at least **10%**, but does not revive crew. Abandoned hulls have
no defenders and are easier to capture. Repair docks repair owned ships/fighters only;
engineer ships can explicitly repair owned ships, fighters and stations for CR/MT.
Equipment repair does not replace dead crew. See [docs/SUPPORT_ORDERS.md](docs/SUPPORT_ORDERS.md)
for the PR #40 support-order changes and [docs/BOARDING.md](docs/BOARDING.md) for the
underlying boarding mechanics.

Crew recovery (merged in PR #38 and included in v0.7.0) adds automatic owned-hull
recruitment near friendly bases and faction crew transports.
Build/select a transport: **L** loads passengers at a base; **R** / **Deliver crew**
then click an owned hull for field delivery. **Cancel crew order** keeps passengers.
Repair life support to **50%** first. Recruitment/loading consumes unassigned crew and
credits over time; delivery does not charge twice. Cargo is separate from onboard crew,
never powers the ship, and is lost without refund on destruction. Understaffing
proportionally reduces movement, weapons, sensors, repairs, production and research;
life-support effectiveness is not staffing-scaled. Cautious AI uses the same commands.
No towing, allied reclaim or neutral salvage. Initial defaults and limitations:
[docs/CREW_RECOVERY.md](docs/CREW_RECOVERY.md).

## Planetary hardware / HUD follow-up (released in v0.10.0)

The v0.10.0 increment adds independently minimizable left/right/mission panels,
3D satellite orbits that pause for engagement, lower satellite cost/durability, and
six separate planetary surface slots for resource, trade, surface-only shield and
long-range pulsar buildings. Basic colony income remains unchanged. This increment
is merged in #43 and included in the verified published v0.10.0 packages. The final
946-test suite and independent source reviews passed; final native wheel-input QA
remains focus-blocked and disclosed.
See [PLANETARY_HARDWARE.md](docs/PLANETARY_HARDWARE.md)
for mechanics, configurable tuning and pending/executed acceptance gates.

## Planetary colonies and satellites (released in v0.7.0)

PR #40, merged October 10, 2026 and included in v0.7.0, extends colony ships for all
four built-in factions (including a new Syndicate colony hull): command-center-only
production, non-gas planetary settlement,
crew/resource income and timed enemy-colony capture after all defending satellites
are destroyed. Successful control consumes the colony ship without an extra fee.
Owned planets expose paid defense/attack satellite construction with a shared limit.
Historical PR #40 acceptance: player controls, AI and persistence passed the
**766-test suite**, independent review and real SDL/OpenGL diagnostics. The release adds paid engineer repairs,
ship/fighter-only repair docks, universal build crew-cost labels and automatic fighter
exploration that avoids detected enemies. Trade stations require 1,500-unit spacing;
new stations/satellites require 3,000-unit clearance from enemy command centers.
See [docs/SUPPORT_ORDERS.md](docs/SUPPORT_ORDERS.md) and
[docs/COLONIES.md](docs/COLONIES.md) for the approved rules, initial tuning and diagnostics.

**Released balance follow-up:** **5× colonized-planet resource and crew income**
was merged in PR #39 and packaged in v0.8.0, together with campaign objective/abandonment
save-restore fixes. It is not included in v0.7.0. Bounded AI matrix and long-probe observations,
mechanic regressions and open acceptance gates are recorded in
[docs/GAMEPLAY_ACCEPTANCE.md](docs/GAMEPLAY_ACCEPTANCE.md); these do not establish
statistical full-match balance or Windows/mixed-platform LAN acceptance.

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

## Faction ships and stations

Faction identity now comes from **3D geometry**, independently of player color:

| Faction | Ships | Stations |
|---|---|---|
| **Galactic Imperium** | Existing tapered escorts and capitals retained | Existing station look retained |
| **Free Systems Alliance** | Segmented hulls, twin nacelles and open hangars | Linked habitats and open oval frames |
| **Automated Legions** | Forked bows and repeated robotic machinery | Threefold hubs and modular machine docks |
| **Outer Rim Syndicate** | Asymmetric armored barges and offset bridges | Salvaged modules, unequal docks and cranes |

The redesign covers all **32 existing catalogue ships**, all **40 faction/station
combinations** (ten station types per faction), and four faction convoy designs.
Construction previews and sites match the faction hardware; camera bounds, shields
and hull-hit contacts follow the rendered geometry, including open docking/fork gaps.
Galactic Imperium geometry and material treatment remain unchanged. No new ship
classes, balance changes or full Syndicate gameplay parity are implied.
See [the faction hardware notes](docs/FACTION_VISUALS.md) for design and diagnostics.

Ownership remains a separate visual channel: colored hull accents and screen-clamped
markers distinguish players and hostiles. Settings allow markers on all units,
hostiles only, or off; markers obey current sensor visibility.

## Menus

`main.py` now starts at the **title screen** → **main menu** (Skirmish / Campaign /
Multiplayer / Settings / Quit). Settings (music/SFX volume, fullscreen, autosave,
camera pan speed) persist to `saves/settings.json` in source runs. Packaged builds
store settings, saves and campaign progress outside the application bundle:
`~/Library/Application Support/STAR ARMADA` on macOS and `%APPDATA%\STAR ARMADA`
on Windows. Since v0.8.0, the **Campaign** screen pages an introductory
recovery drill plus the original ten-mission "Rise of the Outer Armada" chain (`assets/data/campaign/campaign.json`); each mission
has a briefing (story, objectives, enemy preview) before LAUNCH, and in-game objectives
are tracked live in the HUD with COMPLETE/FAILED states.

### Phase 10 presentation (released in v0.9.0)

The v0.9.0 increment adds:

- **Audio:** standard/night dynamic-range profiles, mono output, live music/SFX gain
  controls and reserved ambient/critical/objective channels. Own notifications are
  independent of camera distance; spatial enemy combat cues still require detection.
- **Campaign:** short in-engine intros and success/failure outros. Enter, Space,
  Escape or mouse click skips; camera and simulation time are restored without
  catch-up. Cinematics can be disabled and never run in LAN or replay playback.
- **Help:** F1 opens paged controls/support help; Escape/F1 closes. It consumes gameplay
  input, clears held gestures/targeting, and does not independently pause LAN.
- **Targeted accessibility:** high-contrast help/hint panels, optional recovery-drill
  hints placed around existing HUD controls, and reduced cinematic pan/fades.
  This is not whole-game scaling, screen-reader support or removal of all combat effects.
- **Settings:** keyboard/mouse-reachable pages; all new options persist and reject
  malformed/nonfinite values.

Native macOS audio and SDL/OpenGL diagnostics pass at 1024×768 and 1280×800;
the published v0.9.0 frozen app also passes a read-only DMG smoke. Human listening,
natural tutorial usability, native Windows and mixed-platform LAN remain open.
See [Phase 10 acceptance](docs/PHASE10_ACCEPTANCE.md) for evidence and limits.
Both published downloads passed package verification; those checks do not close
the human/platform acceptance gates above.

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
| Faction-specific ship/station/convoy hardware, protected Imperial look | ✅ implemented across the existing catalogue |
| Four data-driven factions | ✅ faction-selectable setup; Syndicate remains a prototype, not full parity |
| Resources: credits/materials/energy/crew, command capacity | ✅ prototype |
| Stations: command, mining, shipyard, research, defense, sensor, fighter platform, repair, trade, energy relay | ✅ prototype |
| Planetary colonies, timed capture and orbital satellites; asteroid fields, nebulae, jump points | ✅ prototype; colonies/satellites merged in #40 and released in v0.7.0 |
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
| Campaign: ten combat missions plus recovery drill, persisted triggers/waves and staged capture/crew objectives | 🟠 implemented on current branch; full playthrough acceptance pending |
| Victory conditions: annihilation, planet majority, economic, timed (data-driven) | ✅ prototype |
| Trade convoys between trade stations + raiding (salvage loot) | ✅ prototype |
| Objectives: build/destroy/colonize/survive + escort_convoy, hold_point | ✅ prototype |
| Autosave ring (3 rotating slots) | ✅ prototype |
| LAN host/join, 2–4 humans, optional AI, configurable TCP port | ✅ implemented; matching version/content required |
| Deterministic lockstep, serialized commands, replay infrastructure | ✅ implemented and tested |
| Replay recording/browser/read-only playback | ✅ verified in v0.8.0 source; see release notes for package verification |
| LAN reconnect/resync | 🔲 production integration pending; tested standalone foundation only |
| Four skirmish maps, player factions/colors/teams, AI difficulty | ✅ implemented; 2–4 total players by map |
| Boarding/capture, onboard crew/life support and abandoned hulls | ✅ merged in #37; released in v0.7.0 |
| Base crew recruitment, field crew transports, proportional staffing, cautious boarding/recovery AI | ✅ merged in #38; released in v0.7.0; balance acceptance remains open |
| 8-player skirmish | 🔲 planned; current capacity is 2–4 total players |

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
build→gather→research→fleet→attack→win loop. Historical v0.6.0 acceptance: its source tree passed **577
headless tests**, plus real SDL/OpenGL catalogue checks for 32 ships, 40 station
variants, four convoys, all station placement/construction views and all four
faction close-camera keep-outs. **19 protected Imperial pixel comparisons were
unchanged.** Independent code review, ship-size/close-zoom regressions and the
30-second rendered gameplay smoke also passed. Render diagnostics in `tools/`
need a working window server/OpenGL context; they are separate from headless tests.
Historical v0.7.0 acceptance recorded **766 headless tests**, independent support-order
review and real SDL/OpenGL diagnostics at 1280×800 and 1024×768. Current branch
observations and exact campaign restore regressions are recorded separately in
[docs/GAMEPLAY_ACCEPTANCE.md](docs/GAMEPLAY_ACCEPTANCE.md); release-era tests are
not proof of statistical full-match balance.

## Releases

**[Download v0.9.0](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.9.0)**
(published October 11, 2026):

- **macOS:** `STAR-ARMADA-v0.9.0-mac.dmg`
- **Windows:** `STAR-ARMADA-v0.9.0-win.zip`

The release notes record successful native macOS/Windows CI builds, downloaded
assets matching GitHub SHA-256 digests, DMG checksum and Windows ZIP integrity
checks. The published macOS bundle reports 0.9.0 and passed a 30-second frozen-app
smoke (`SMOKE_OK`). **Native interactive Windows gameplay was not exercised;
mixed-platform LAN acceptance remains open.** Packaging is delivered, not a
missing feature; these remaining interactive checks are separate acceptance gates.

Tagged versions (`v*`) trigger native macOS and Windows builds and GitHub Release
publication. Version is defined once in `game/__init__.py`; merge the version
bump through a PR before tagging its merged commit. See `docs/PACKAGING.md` for
local builds (`./scripts/build_mac.sh`).

## Completed development

| Release | Delivered |
|---|---|
| **v0.9.0** | Standard/night audio mix, mono/live controls, short skippable campaign cinematics, paged help/settings, recovery hints and targeted accessibility (#41); verified published macOS DMG and Windows ZIP |
| **v0.8.0** | Campaign scripting/reinforcements, eleven-mission catalogue, stable-ID progression, canonical runtime restore, replay recording/browser/playback and 5× colonized-planet income (#39); published macOS DMG and Windows ZIP |
| **v0.7.0** | Boarding and crew/life support (#37), crew recovery/transports and cautious AI (#38), colonies/capture/satellites and support orders (#40); published macOS DMG and Windows ZIP |
| **v0.6.0** | Distinct ships, ten station types and convoys for every faction; Imperial look preserved; faction construction previews, geometry-safe cameras and exact hull contacts |
| **v0.5.2** | Ownership hull shading and screen-clamped friend/hostile markers with configurable visibility |
| **v0.5.1** | Close/very-close base camera safety, minimap recenter/follow correction, behind-eye ship-size fix, consistent projection/picking/audio, and large-fleet camera query optimization |
| **v0.5.0** | Combat XP and capped ship ranks with attack/defense bonuses; selected-fleet roster and combined special abilities; construction-progress layout fixes; alliances/team elimination and normalized hull sizes |
| **v0.4.0** | LAN host/join with human and AI slots and selectable port; click-targeted hyperjump; combat standoff/orbit behavior; metal hulls, planets, deep-space and shield/hull impact graphics |
| **v0.3.0** | Per-weapon combat audio/pitch fixes, layered explosions, reachable trade convoys, and writable user data outside frozen application bundles |
| **v0.2.0** | Menus/settings, 10-mission campaign, data-driven victory conditions, trading/raiding, escort/hold-point objectives and rotating autosaves |

### Still in development

The game remains a playable prototype, not the full design specification.
Boarding/capture (#37), crew recovery/staffing/AI (#38), and colonies/support orders
(#40) are merged and packaged in v0.7.0. Long-match balance, native interactive
Windows and mixed-platform LAN acceptance remain open. The 5× colonized-planet
resource and crew income follow-up is packaged in v0.8.0, not v0.7.0; bounded
observations and remaining balance gates are documented separately. Campaign scripting,
staged capture/crew objectives and replay recording/browser/playback are implemented
in v0.8.0; package checks are recorded in release notes.
See [campaign notes](docs/CAMPAIGN_SCRIPTING.md)
and [replay notes](docs/REPLAYS.md). Reconnect has standalone tested foundations only:
**live LAN disconnects still end matches**. Production freeze/rollback, input
reconciliation and UI handoff remain pending; see [reconnect scope](docs/LAN_RECONNECT.md).
The Phase 10 audio/cinematic/help increment is packaged in v0.9.0; its acceptance limits
are listed above. Eight-player matches, natural full campaign playthroughs, full faction parity,
in-game mod management and further performance work remain pending. Current skirmish/LAN capacity is **2–4 total players**,
limited by the selected map. See `docs/DEV_PLAN.md` for the broader plan; the
feature matrix above describes the implemented release behavior.

## License / originality

All code and data in this repository are original. Ship/faction names are data; swap
`assets/data/*.json` for your own universe. Mechanics are inspired by the classic
fleet-RTS genre; no third-party code or assets are included.