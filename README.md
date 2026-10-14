# STAR ARMADA

**STAR ARMADA** is a large-scale, fleet-based real-time strategy game in the spirit of
classic space-fleet RTS titles (Armada II / Fleet Operations era). It runs entirely on
Python 3 — deterministic simulation, AI, OpenGL rendering via pygame-ce and procedural audio.

**Current release: [v0.14.0](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.14.0)**
— published October 14, 2026, with verified macOS DMG and **unsigned Windows ZIP**.
Adds hyperspace transit travel and post-jump shield lockdown, English/German/Polish language
packs, laser and photon weapon voices rebuilt against reference recordings, five paid station
refit levels, cancel refunds with cost-derived build times, family-shaped weapon fire with a
6720 pulsar reach, and campaign return with COMPLETE wins. The final **1,404-test** suite and
independent reviews passed. Both native builds are produced by GitHub Actions; the downloaded
DMG was hashed and inspected here, passes `hdiutil verify`, ships the three language packs and
runs the packaged app's simulation benchmark and LAN diagnostic with a state hash and
60-tick/600-tick fingerprints identical to the source build. Windows-source LAN
diagnostics/tests passed on a native CI runner; this does not prove frozen Windows gameplay or
mixed-platform live LAN. Interactive Windows, trusted signing/Smart App Control, human
listening/campaign and full-match balance remain open.
## Unreleased — Station balance: retunable refit gains and per-level build gates (#106)

The five-level station refit ladder is no longer fixed data. **Settings → Game Balance → Station
upgrades** (page 5 of 5) picks a faction, lists every station type its builders can lay down, and
edits the per-level gains that station actually uses — the individual rows the simulation reads,
not one percentage standing in for all of them. The second page sets **build levels**: a hull can
be made to wait until its station has paid for refit level 2..5 before it may be built, for every
player and for the AI alike. A gated hull stays on the build panel drawn locked with the level it
wants, and the AI buys the level rather than stalling when it can pay for it.

The configuration lives in `balance.json` beside `settings.json`, `campaign.json` and the saved
games in the per-user data directory, never in the app bundle: an update replaces
`assets/data/game_rules.json` and would otherwise revert the player's numbers. It is read
leniently when the player may have hand-edited it (unreadable entries drop out; the game still
starts) and strictly when it arrives over the network (a config that cannot be applied whole is
refused, never half-applied). One overlay is folded into the catalogue's live rules, so the
simulation, the station panel, the replay recorder, replay validation and the LAN handshake all
read the same numbers.

On LAN the tuning travels with the handshake instead of being compared: the content hash still
covers the shipped catalogue, mods and game version exactly, and the host's overlay rides in the
`welcome` so a peer whose own file differs adopts the host's numbers for that match — and gives
them back when the session closes, writing nothing to its own file. Full contract in
[`docs/STATION_UPGRADES.md`](docs/STATION_UPGRADES.md).

## v0.14.0 — Hyperspace transit, language packs, weapon voices and five-level station refits

Published October 14, 2026 with a verified macOS DMG and an unsigned Windows ZIP
([release notes](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.14.0)).

Hyperjumps (#92) are no longer instant: the charge countdown ends with a departure
ring/sound and the hull rides hyperspace along the origin→exit corridor. Travel time
scales with distance (240 units/second, clamped 3–120 s). While in transit the ship
is invisible on the strategic view for every player, cannot be targeted, hit, boarded
or sensed, and its own sensors are inert — but it keeps moving on the minimap. On
arrival the reserved exit position is re-checked and shields stay down for 15 seconds
(#78): no regeneration and no emergency recharge until the lockdown expires. A group
jump still lands every ship on its deterministic reserved exit; saves, restores and
replays serialize the full transit state bit-exactly.

The final **1,404-test** suite passed (1 pre-existing, environment-dependent failure
in the menu-exit audio probe reproduces on v0.13.0 and is unrelated; 8 platform skips).

Beyond hyperspace, this increment collects everything merged since v0.13.0: the campaign
returns to the campaign screen after a mission and marks wins COMPLETE (#89); cancelling
paid queued work refunds exactly half of the bill that was paid and surface build times are
derived from the catalogue bill at 80 units/second ([`docs/COMMAND_CAPACITY.md`](docs/COMMAND_CAPACITY.md),
#94, #95); weapon fire is shaped by family and the pulsar cannon's reach is 6720 (#90, #81);
stations gain five paid refit levels ([`docs/STATION_UPGRADES.md`](docs/STATION_UPGRADES.md),
#77); the interface ships **English, German and Polish** ([`docs/LOCALIZATION.md`](docs/LOCALIZATION.md),
#93); and the laser and photon weapon families were re-voiced against reference recordings
([`docs/WEAPON_AUDIO.md`](docs/WEAPON_AUDIO.md), #91).

The setting is an original space-opera universe. Prototype faction/ship names are
placeholder-style data (Imperial / Rebel / Confederacy / Syndicate) so the feel reads
familiar, but **no copyrighted assets, code, maps, sounds or text from any commercial
game are used**. Every ship, weapon, faction, tech and map is a JSON data file — replace
them and the game changes with zero code edits.

### Weapon fire look and pulsar reach (#90, #81)

Weapon fire is shaped by family instead of every projectile being the same round
speck in a different colour. Laser, point-defence and turbolaser bolts are thin
rectangles elongated along their heading; torpedoes and missiles are squares. Each
is a soft additive halo around a hot core, expanded into triangles and emitted in a
single batched pass for the whole volley (the old path issued one glow call per
projectile, which is what made fleet-scale volleys expensive). Ion, plasma, kinetic
and beam weapons keep the previous round glow, so super weapons such as the pulsar
cannon are unchanged; a bolt fired straight at or away from the camera has no
screen-space heading and falls back to a vertical streak rather than collapsing to a
dot. Both extents carry a screen-space floor, because a world-only size is about one
pixel at overview range.

The pulsar cannon also out-ranged the map it defends: `planet_pulsar_beam` reached
8400 units on a ~24000-unit skirmish span, a third of the map from one planetary
battery. Reach is now **6720**, with the cannon's `sensor_range` moved with it —
detection gates every launch, so shortening one without the other would blind the
battery. The #52 regression ("when building a pulsar cannon we are not able to fire
it") now pins the guarantee rather than the number: the emplacement must see as far
as it shoots and must fire across that whole band, and never past it.

### Station upgrades — five paid refit levels (#77)

Stations are no longer fixed at the strength they were built with. Every station hull
laid down by a construction ship or a shipyard can be refitted through **five levels**
(level 1 is the hull as it leaves the yard; the four steps above it are paid work), and
the station panel carries the row: the level, the accumulated effect of the levels
already bought, and one button per step with its price and refit time.

A refit costs a fraction of the station's *own* catalogue build bill (0.75×, 1.10×,
1.50×, 2.00×) and takes a fraction of its build time (0.60×, 0.85×, 1.10×, 1.40×), so
a command station's refit is dearer than a sensor station's and a full ladder costs
5.35× the hull. Each level raises hull capacity, shields and shield regeneration, and
adds the category bonus the hull can actually use: firepower and an extra shot per
weapon mount for anything that can shoot, resource output for anything with an income
table, and more, fuller convoys for a trade station. Categories come from the
catalogue, not from station names, so a mod that arms a mining station gets a
firepower ladder for it.

The work is paid up front, queued on the station's own build queue and finished on a
timer while the station keeps operating — and it is cancellable like any other paid
work, refunding half of the exact bill that was paid (`cancel_build`, #94). Hull and
shield capacity are raised once at completion and the current quads and hull are
*scaled* with them, so a refit can never be bought as a cheap repair. `upgrade_level`
is hull state: a captured station keeps the level its previous owner paid for, the
level rides the save graph and the LAN reconnect snapshot, and it is part of the
per-tick desync digest, so two peers that disagreed about a refit fail loudly instead
of diverging. Saves made before #77 load as an all-level-1 fleet.

Planet-built hardware is deliberately out of scope: the four surface buildings and the
two orbit satellites are excluded, exactly as the issue specified. Full contract in
[`docs/STATION_UPGRADES.md`](docs/STATION_UPGRADES.md).

---

## v0.13.0 — Clean Classic menus, battle backgrounds, Saved Games and replay management

This release unifies menu presentation across every screen with the approved Clean Classic design: centered main menu, a clear seaglass primary action, proportional typography and restrained dark panels. A close-up looping battle sequence involving frigates and dreadnoughts now runs behind the title screen, main menu, Skirmish setup, LAN host/join/lobby, Settings, Campaign list and briefing screens. The Replay browser remains static and receives a Skirmish-style library/details/actions layout.

**Saved Games** is a new main-menu entry exposing the existing F5/F9 quicksave/quickload system through a Clean Classic library. Passive row selection shows UTC timestamps and save kind (Quick/Autosave); explicit **Load selected** restores the canonical state through the existing `GameState.from_dict` → `GameManager` pipeline, including campaign progress and a 120-tick full-precision continuation verified against the production F5 writer. **Delete selected** and **Delete all** operate on the managed namespace only (`quicksave.json`, `autosave.json`, `autosave_<digits>.json`), with Cancel-default confirmations; settings, campaign, replays and unknown files are protected.

The Replay browser adds newest-first timestamp ordering, select/delete-all/delete-selected with Cancel-default confirmations, and metadata-only rendering (no gameplay reconstruction). Native Windows safe deletion now includes seven real-kernel tests: the original six (4,101-file uncapped delete, symlink/junction containment, replacement blocking, handle cleanup) plus a new saved-games namespace test.

Independent integrated review passed after malformed-save and fixture-isolation regressions were fixed with strict RED→GREEN cycles. The final **1,266-test** suite passed.

## v0.12.1 — Renderer performance improvements

This release applies the PR#87 quality-preserving renderer optimizations:

- Per-frame cache for camera basis, owner colors/relations and per-entity view data.
- Role-batched ship/station draws (base/dark/trim, accent, lit/cool) to cut GL state changes.
- Distance/material-role LOD for small on-screen ships.
- Batched ownership markers and shield-shell detail LOD.
- Shield opacity tuning so dense fleets no longer additive-saturate to white.

Measured on the macOS 500-corvette stress benchmark (1280×800, 4× MSAA, vsync off):
- World render median: **98.5 ms → 65.0 ms** (~34% reduction).
- Full frame median: **133.5 ms → 100.0 ms** (~25% reduction).
- Station-heavy and developed-base scenes are already inside the 33 ms render budget.

Station rotation, MSAA, visual passes and gameplay are unchanged. The final
**1,162-test** suite passed; LAN network tests and `--netdiag` passed locally.
Native Windows interactive and mixed-platform live LAN acceptance remain separate
open gates.

## v0.12.0 — Crew casualties and gameplay fixes
**1,162-test** suite and real macOS crew-damage SDL/OpenGL checks passed. Both
published packages passed download integrity/code/data verification; native Windows
interactive and mixed-platform live LAN acceptance remain separate open gates.

Remaining issue work, outside this release: #78 (15-second post-jump shield lockout),
#81 (clarify pulsar range), and #77 (paid five-level station upgrades).

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
| Backspace | Stop selected units and cancel pending orders |
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
| WASD / arrows | Pan; manual pan releases follow |
| Mouse-wheel | Zoom (tactical → fighter scale); scroll roster/abilities when hovering their HUD lists |
| Left-click minimap | Recenter the camera and release follow mode |
| X | Tactical overview |
| P | Pause / resume |
| F5 / F9 | Quick save / quick load |
| F10 | Toggle mouse grab |
| ESC | Abort the current operation: ability/jump targeting, placement, fleet panel. Press twice to return to the previous screen |
| F11 | Toggle fullscreen |

## Boarding, crew and life support

Ships and stations carry onboard crew and damageable life support. Failing support
kills crew gradually. The v0.12.0 source also loses **one operating crew member per
10 actual hull damage** after shields and armor; smaller hits accumulate toward the
next casualty. Configure `combat.hull_damage_per_crew` in `game_rules.json` (`0`
disables combat casualties). Passengers and unassigned crew pools are unchanged.
Zero crew leaves an abandoned intact hull with its existing owner. Automatic and
retained attacks stop at abandonment, preserving the hull for recovery/capture;
a new explicit attack on a detected enemy derelict permits destruction.
Already-fired physical projectiles can still hit. AI does not deliberately destroy
derelicts: abandoned planetary satellites cannot be boarded and still block colony
capture, so an AI capture can stall indefinitely until that hardware is removed.
Frigate-and-larger
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

## Infrastructure command points (#70; released in v0.12.0)

All living stations, surface buildings and satellites consume **1 CMD**, except
research stations (**5 CMD**). Every owned eligible colony adds a command center's
capacity (**20** by default, mod-aware). Paid construction reserves CMD before
resources are charged; the HUD's used total includes reservations and its build rows
show their CMD costs. Abandoned hulls still count, while destruction/cancellation
releases usage. Losing capacity blocks new purchases, not already paid production.
See [the accounting and lifecycle contract](docs/COMMAND_CAPACITY.md).

### Cancelling paid work and cost-based building times (#94, #95)

Paid construction is now cancellable. A selected station's build-queue rows and a
colony's paid slot cells carry a **✕ Cancel** affordance that submits a
`cancel_build` command; it stops one queued item and refunds **half** of that
item's catalogue cost (the other half pays for work already done). The freed
command points — and, for a colony, the freed surface slot or orbit — return
immediately, because usage and reservations are derived from the live queues.
Colonisation is a standing fleet order with no resource cost, not paid
construction, so it is not cancellable this way; re-order the ship instead. A
cancel is never treated as a new order, so it cannot supersede the units' other
standing orders. Surface building time now follows the resource bill (#95):
seconds are the building's credits + materials + energy over
`planet_buildings.resource_units_per_second` (80 units/s shipped), so the
extractor and trade hub take 20 s, the shield generator 27.5 s and the pulsar
cannon 35 s instead of every type sharing one flat 24 s. The catalogue
`build_time` must mirror the derived value — the data store rejects a catalogue
that disagrees, which keeps the time the HUD prints equal to the one the
simulation runs. See [docs/COMMAND_CAPACITY.md](docs/COMMAND_CAPACITY.md) and
[docs/PLANETARY_HARDWARE.md](docs/PLANETARY_HARDWARE.md).

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
are tracked live in the HUD with COMPLETE/FAILED states. A finished mission is marked
COMPLETE in gold on the campaign screen and stays selectable for replay, and
acknowledging a campaign result returns to that campaign screen rather than the main menu.

Recovery Drill's current source objective (#80) is to capture the abandoned syndicate
corvette and restore **that captured corvette to 100% onboard crew**. Automatic
recruitment near a friendly base and loaded crew-transport delivery both count; a
full surviving boarding party can complete it immediately. The abandoned frigate
is optional practice, not a delivery requirement. Personnel costs, life-support
safety and campaign unlock-save migration are unchanged. The correction is merged
in #82 and released in v0.12.0; see `docs/CAMPAIGN_SCRIPTING.md`
for controlled QA evidence. Natural human playthrough acceptance remains separate.

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

## Localization — English, German, Polish (#93)

The game ships three languages. `Settings → Language` cycles them and applies immediately;
the choice persists in `saves/settings.json` as `"language": "pl"`.

A language is **presentation only**: packs are read at the drawing edges (the classic
canvas, the menu helpers, `HUD._label` and the word-wrap helper), a pack that is missing a
line falls back to English, and no module under `game/` can even import the layer — so two
lockstep peers may play the same match in different languages and still agree on every
ticksum. Assembled text (a victory banner, a refit level line, a resource bill) is asked
for as a template, e.g. `t('{credits} cr · {materials} mt')`, and every data-driven name
(ships, stations, factions, tech, weapons) is translated too:

| | English | Deutsch | Polski |
|---|---|---|---|
| Station panel | `REFIT · LEVEL 3/5` | `UMBAU · STUFE 3/5` | `PRZEBUDOWA · POZIOM 3/5` |
| Main menu | `Settings` | `Einstellungen` | `Ustawienia` |
| A hull | `Shipyard` | `Werft` | `Stocznia` |

Packs live in `assets/data/lang/`; `tools/lang_coverage.py` extracts the catalogue from the
source and reports coverage (currently **100%** for both packs: 326 UI strings + 96 names),
and `tools/build_lang_packs.py` refuses to write a pack that is missing a key or carrying a
dead one. See `docs/LOCALIZATION.md` and run `python tools/diag_i18n.py` to re-check that
geometry, truncation and lookup coverage all hold.

## Weapon audio — laser and photon voices (#91)

Every sound is synthesised by `render/audio.py` at load time; **no audio file ships with the
game**. Issue #91 was "improve sound effects" with no symptom named until two reference
recordings were supplied — a laser and a photon gun — so the voices were re-tuned against
what those recordings actually measure:

| voice | before | after |
|---|---|---|
| laser family | 85 ms chirp, centroid >5 kHz | 300 ms dark thump, centroid ~1.4 kHz, 137 ms tail |
| point-defense | short thin chirp | same gun smaller: brighter, over in 90 ms |
| turbolaser (+ heavy) | 280 ms band-limited crack | 500/680 ms broadband thump, rolloff ~7.3 kHz |
| plasma lance | short band-passed flame | same photon character, top end closing downward |

The references are a **target, not an asset**: they are not in the repo, and were measured
with `tools/sfx_character.py`, which measures a recording and a synthesised voice with the
same function (weight = spectral centroid, crack = 95 % magnitude rolloff, tail). Their
numbers live in that module's `REFERENCE_TARGETS`; `tools/diag_weapon_sfx.py` re-checks every
voice against the band they define and exports each as a WAV and a spectrogram, and
`tests/test_weapon_sfx.py` pins bands, voice relationships and "no two weapons measure as the
same shot". One deviation is deliberate: the recordings swell to their peak over 70–150 ms,
a game voice is punched in ~3 ms, because fire feedback cannot wait. See
`docs/WEAPON_AUDIO.md`.

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
| Procedural audio (original, no assets) | ✅ implemented; laser, turbolaser and plasma families re-voiced against reference recordings (#91) |
| Minimap, fleet roster/ability union, rank inspector, build/research progress | ✅ implemented |
| Title screen, main menu, settings menu (music/SFX volume, fullscreen, autosave, pan speed — persisted to `saves/settings.json`) | ✅ prototype; Clean Classic unified since v0.13.0; battle backgrounds on all non-replay screens |
| Language packs: English, German, Polish with a `Settings → Language` selector | ✅ implemented (#93); 422/422 strings and names translated, presentation-only so a language cannot reach the simulation |
| Campaign: ten combat missions plus recovery drill, persisted triggers/waves and staged capture/crew objectives | ✅ released since v0.8.0; recovery objective correction released in v0.12.0; natural full playthrough acceptance pending |
| Victory conditions: annihilation, planet majority, economic, timed (data-driven) | ✅ prototype |
| Trade convoys between trade stations + raiding (salvage loot) | ✅ prototype |
| Objectives: build/destroy/colonize/survive + escort_convoy, hold_point | ✅ prototype |
| Autosave ring (3 rotating slots) | ✅ prototype |
| LAN host/join, 2–4 humans, optional AI, configurable TCP port | ✅ implemented; matching version/content required |
| Deterministic lockstep, serialized commands, replay infrastructure | ✅ implemented and tested |
| Replay recording/browser/read-only playback | ✅ released in v0.8.0; timestamps, selection, bulk delete, metadata-only rendering since v0.13.0; strict version/content compatibility |
| LAN reconnect/resync | 🟠 experimental same-host live integration; known unfixed blockers, not production-ready or released |
| Four skirmish maps, player factions/colors/teams, AI difficulty | ✅ implemented; 2–4 total players by map |
| Boarding/capture, onboard crew/life support and abandoned hulls | ✅ merged in #37; released in v0.7.0 |
| Base crew recruitment, field crew transports, proportional staffing, cautious boarding/recovery AI | ✅ merged in #38; released in v0.7.0; balance acceptance remains open |
| Saved Games library (Load/Delete quick/autosaves) | ✅ implemented v0.13.0; managed namespace only, Cancel-default confirmations |
| Native Windows safe deletion acceptance | ✅ 7 real-kernel tests v0.13.0 (4,101-file uncapped, symlinks/junctions, containment, replacement blocking, handle cleanup, saved-games namespace) |
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

**[Download v0.14.0](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.14.0)**
(published October 14, 2026):

- **macOS:** `STAR-ARMADA-v0.14.0-mac.dmg`
- **Windows:** `STAR-ARMADA-v0.14.0-win.zip` (unsigned)

Both published downloads were re-downloaded from the release and hashed here: DMG
`2ff802dfb8bf1b5378a8ae454b77a546d61d06087547ad06a09e1f0cd91d4690`, ZIP
`74ccca2f039e784a4d1c76b46e05ee560b60b5c8cf7ecc5d0fb8b2a3c631b526`. The DMG passes
`hdiutil verify`, mounts with the app and the Applications symlink, ships all three language
packs, and the packaged app reports 0.14.0 and runs its simulation benchmark and LAN
diagnostic with the same initial-state hash and the same canonical (60-tick) and contact
(600-tick) fingerprints as the source build. The Windows ZIP passes `unzip -t` and contains
`STAR ARMADA.exe` and the language packs; the Windows executable itself was **not** run, so
frozen Windows gameplay and mixed-platform live LAN remain open. Full hashes and per-artifact
evidence are in the release notes.

**[Download v0.13.0](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.13.0)**
(published October 13, 2026):

- **macOS:** `STAR-ARMADA-v0.13.0-mac.dmg`
- **Windows:** `STAR-ARMADA-v0.13.0-win.zip` (unsigned)

Both published downloads match GitHub SHA-256 digests, pass DMG/ZIP integrity and match the immutable tag for inspected runtime modules and tracked assets. The downloaded macOS bundle reports 0.13.0 and passes a 30-second smoke from the read-only mount; new screenshot/replay data are written outside the app. Windows-source LAN checks passed in CI; native frozen Windows gameplay and mixed-platform live LAN acceptance remain open. Full hashes/evidence are in the release notes.

**[Download v0.12.0](https://github.com/ljawor/STAR-ARMADA/releases/tag/v0.12.0)**
(published October 13, 2026):

- **macOS:** `STAR-ARMADA-v0.12.0-mac.dmg`
- **Windows:** `STAR-ARMADA-v0.12.0-win.zip` (unsigned)

Both published downloads match GitHub SHA-256 digests, pass DMG/ZIP integrity
and match the immutable tag for 42 inspected runtime modules and all 15 tracked
assets. The downloaded macOS bundle reports 0.12.0 and passed a 30-second smoke
from the read-only mount; new screenshot/replay data were written outside the app.
Windows-source LAN checks passed in CI; native frozen Windows gameplay and
mixed-platform live LAN acceptance remain open. Full hashes/evidence are in the
release notes. Historical v0.11.0 laptop measurements remain separate evidence.

Tagged versions (`v*`) trigger native macOS and Windows builds and GitHub Release
publication. Version is defined once in `game/__init__.py`; merge the version
bump through a PR before tagging its merged commit. See `docs/PACKAGING.md` for
local builds (`./scripts/build_mac.sh`).

## Completed development

| Release | Delivered |
|---|---|
| **v0.14.0** | Hyperspace transit travel and post-jump shield lockdown (#92/#78); campaign return with COMPLETE wins (#89); cancel refunds and cost-derived surface build times (#94/#95); family-shaped weapon fire with a 6720 pulsar reach (#90/#81); five paid station refit levels (#77); English/German/Polish language packs with a Settings selector (#93); laser/photon weapon voices rebuilt against reference recordings (#91); verified DMG and Windows ZIP |
| **v0.13.0** | Clean Classic menu unification, looping battle backgrounds on all non-replay screens, Saved Games library with Load/Delete, replay management with timestamps/selection/bulk deletion, native Windows safe deletion acceptance (7 real-kernel tests); verified DMG and Windows ZIP |
| **v0.12.1** | Renderer performance improvements (per-frame cache, role-batched draws, LOD, marker batching, shield opacity) without visual quality loss; 500-corvette stress 133.5→100.0 ms full-frame, 98.5→65.0 ms world-render; verified DMG and Windows ZIP |
| **v0.12.0** | Crew hull-damage casualties and abandonment-safe targeting (#85/#79); mixed-platform deterministic LAN, Escape, orbit targeting, infrastructure CMD, Recovery Drill, elevated-fighter pursuit and crowded-map orbit fixes; verified DMG and Windows ZIP |
| **v0.11.0** | Large-fleet CPU/fog optimization and packaged benchmark reports (#66); input, capital arcs and planetary projectile/slot-lockout fixes |
| **v0.10.1** | Quiet firing audio and live-volume silence correction (#47) |
| **v0.10.0** | Surface resource/trade/shield/pulsar hardware, satellite orbits and independent HUD panel minimization (#43) |
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
and [replay notes](docs/REPLAYS.md). This source adds **experimental same-host LAN reconnect**
with freeze/drain, delayed-input reconciliation and UI/recorder handoff. It is enabled
by the LAN menus, but known admission, launch-delivery and resource-cleanup defects
remain; the integrated suite and persistence-preservation gate failed. This is not
a readiness or release claim; see [scope, blockers and evidence](docs/LAN_RECONNECT.md).
The Phase 10 audio/cinematic/help increment is packaged in v0.9.0; its acceptance limits
are listed above. Eight-player matches, natural full campaign playthroughs, full faction parity,
in-game mod management and further performance work remain pending. Current skirmish/LAN capacity is **2–4 total players**,
limited by the selected map. See `docs/DEV_PLAN.md` for the broader plan; the
feature matrix above describes the implemented release behavior.

## License / originality

All code and data in this repository are original. Ship/faction names are data; swap
`assets/data/*.json` for your own universe. Mechanics are inspired by the classic
fleet-RTS genre; no third-party code or assets are included.
