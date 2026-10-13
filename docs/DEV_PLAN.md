# STAR ARMADA — Development Plan

Phases follow spec §48. This is a delivery-status plan, not a claim of full-spec
completion. Phases 1–6 have playable prototype implementations. Later phases are
partly delivered; the remaining work is listed explicitly below.

## Status conventions

- **Delivered**: merged implementation; packaging/release coverage may vary.
- **Implemented, awaiting merge**: tested feature branch, not a released feature.
- **Pending**: missing deliverable, not merely an older roadmap label.
- Recommendations below define the proposed finish order, not additional approved scope.

## v0.12.0 release preparation — October 13, 2026

The user authorized a new macOS DMG and Windows ZIP including crew combat damage
(#79) and the fixes merged after v0.11.0. The #79 source is implemented on the
release branch; independent review and the final full suite remain pending. This section describes release scope;
publication and downloaded-package verification are pending until recorded below.

- **Crew damage (#79):** approved tuning is one operating-crew casualty per 10
  actual unshielded hull damage. Fractional hits accumulate deterministically and are persisted precisely.
  Automatic and retained attacks stop at abandonment; a fresh explicit attack on
  an already abandoned detected enemy can destroy it. Ownership/recovery and
  already-fired ballistic impacts retain their existing contracts.
- **Already merged fixes:** mixed-platform content hashing/deterministic math (#68),
  Escape abort/menu behavior (#71), orbiting defense-satellite targeting (#73),
  infrastructure/colony CMD accounting (#74), Recovery Drill crew completion (#82),
  elevated-fighter pursuit (#83), and crowded-map orbital clearance (#84).
- **Remaining issue work:** #78 post-jump 15-second shield lockout; #81 pulsar range
  intent/tuning; #77 five-level paid station upgrades. These are not included here.
- **Separate acceptance:** native Windows gameplay, mixed-platform live LAN,
  trusted Windows signing/Smart App Control, human campaign/audio acceptance and
  full-match balance remain open. Historical laptop benchmarks do not establish
  this release's Windows runtime acceptance.

## Current source and release scope

**Current release: v0.11.0**, published October 12, 2026. PR #66 is merged
and packaged: measured large-fleet CPU/fog optimizations and player-runnable
benchmark JSON for Filip's Windows laptop. The stable source passed 1,009
tests and independent review; 52 replay/content/performance tests passed after
version preparation. Twenty-four controlled baseline/candidate trials preserved
precise state and final rendered pixels. This increment also packages input,
fire-arc and planetary projectile/slot-lockout fixes in #61, #63, #64 and #65.
Both published downloads passed digest/integrity checks; 22 inspected runtime
modules and all 15 tracked assets match the immutable tag. Read-only frozen
macOS smoke and both frozen benchmark modes passed.
Native Windows measurements were taken on Filip's laptop in October 2026 (source
`da417ce` and the downloaded v0.11.0 package, both benchmark modes, integrated and
discrete GPU, 72 trials): the frozen Windows build runs and reports, rendering
dominates the frame, and OpenGL defaults to the integrated GPU. Interactive Windows
gameplay/feel, trusted Windows signing and
mixed-platform LAN acceptance remain open. See
[PERFORMANCE.md](PERFORMANCE.md) for measured scope and reporter commands.

**Previous release: v0.10.1**, published October 11, 2026. PR #47 fixes quiet
ship/fighter firing and live-volume silence; #49 prepares the authoritative version.
The unchanged runtime tree passed 956 tests; 36 replay/content-sensitive tests
passed after the version-only bump. Both downloaded package digests, three inspected
runtime modules and all 15 tracked assets match the immutable tag. Read-only
macOS frozen smoke passed. The Windows ZIP is explicitly **unsigned**; trusted
certificate signing / Smart App Control acceptance (#45), native listening and
Windows gameplay, Cocoa wheel-input and mixed-platform LAN gates remain open.

The preceding **v0.10.0** release includes PR #43 planetary surface hardware,
inclined satellite orbits, reduced satellite cost/durability and independent HUD
panel minimization. Its historical package verification covered 26 code modules
and all 15 tracked assets. The following older increments are historical.

GitHub v0.7.0 was published October 10, 2026 with
`STAR-ARMADA-v0.7.0-mac.dmg` and `STAR-ARMADA-v0.7.0-win.zip`. PRs #37, #38 and
#40 are merged and included. Release notes record downloaded SHA-256 verification,
DMG/ZIP integrity checks and a 30-second frozen macOS smoke (`SMOKE_OK`, version
0.7.0). Native interactive Windows gameplay was not exercised; mixed-platform LAN
acceptance remains open. Packaging is delivered, not missing infrastructure.

The **v0.8.0** source increment from PR #39 includes the user-requested
**5× planet resource and crew income**, deterministic campaign scripting and the
player-facing replay workflow. Package publication and downloaded artifact verification
are recorded separately in the v0.8.0 GitHub release notes; these features are absent
from v0.7.0. A 48-scenario, 120-second
faction/map/difficulty sweep and four 900-second same-faction probes completed;
these are bounded observations, not full-match balance acceptance. This increment
fixes campaign objective authority and abandonment/restore semantics.
See [GAMEPLAY_ACCEPTANCE.md](GAMEPLAY_ACCEPTANCE.md) for evidence and open gates.
Historical test counts below describe their original increments.

## Phase 1 — Window, camera, map, selection, movement ✅ prototype delivered

pygame-ce/OpenGL, 3D tactical camera, data-driven geography, selection/control groups,
nose-first movement, minimap, geometry-safe close zoom and consistent picking.
Four skirmish maps support 2–4 total players with factions/colors/teams/difficulty.

## Phase 2 — Units, health, combat, weapons, shields ✅ prototype delivered

Data-driven fighter-to-supercapital catalogue, shield quadrants, subsystem damage,
projectiles/point defense, combat standoff/orbits, capped XP ranks and rank inspector.
Crew/life-support/boarding extensions are merged in #37. Recovery, four faction
crew transports and proportional staffing are merged in #38 (`6c76978`). Both
increments are included in the v0.7.0 packaged release.

## Phase 3 — Resources, construction, stations ✅ prototype delivered

Credits/materials/energy/crew and command capacity; mining, reachable gas-giant energy
relays, constructor-range station orders, shipyards, research and colony bonuses.
Trade convoys, delivery, raiding and serialized commercial routes are implemented.
PR #40 colonies, timed capture, orbital satellites and paid support orders are merged
and packaged in v0.7.0; v0.8.0 includes the 5× planet resource and crew income follow-up.
Further economic/faction balance is not complete merely because these systems exist.

## Phase 4 — Technology and special abilities ✅ prototype delivered

Per-faction tech trees, research prerequisites and cooldown/energy-based abilities,
including repair drones and click-targeted hyperspace jumps.

## Phase 5 — Fleets, formations, fighters, carriers ✅ prototype delivered

Fleet commanders/formations, squadrons and carrier repair/reinforcement; multi-selection
roster and combined abilities. Merged #37 adds capture-safe carrier dependent cleanup.

## Phase 6 — AI 🟠 prototype delivered; gameplay completion pending

Strategic/tactical AI, difficulty modifiers, scouting, infrastructure and fleet combat
exist. Merged #38 adds cautious detected-target boarding, support/crew retreat,
repair infrastructure and transport logistics, including emergency mission interruption,
repair-destination reassessment and replacement of stranded abandoned transports.
Remaining: validate complete matches across factions/maps/difficulties and tune recovery
costs/rates/AI thresholds. Autonomous field repair dispatch to unsafe abandoned hulls
is not implemented; these hulls still require external repair assistance.
Full Syndicate parity remains unverified/incomplete;
faction-specific meshes must not be confused with complete faction gameplay.

## Phase 7 — Campaign, objectives and cinematics 🟠

**Delivered:** title/main/settings/campaign menus; 10-mission chain, briefing screens,
live build/destroy/colonize/survive/escort/hold objectives and persisted campaign progress.

**Implemented in the v0.8.0 source increment (PR #39):** persisted
simulation tick/time/event/objective triggers, once-only reinforcements, staged objectives
and real capture/crew attribution; recovery drill plus the original ten missions.
Stable-ID progress migration and paged selection preserve legacy unlocks.
See [CAMPAIGN_SCRIPTING.md](CAMPAIGN_SCRIPTING.md) for exact scope and QA limits.

**Pending:** natural-navigation campaign playthroughs, wave balance and cross-platform
acceptance. Short skippable cinematics were released in v0.9.0. Historical v0.8.0 source verification passed:
861 tests, independent re-review and real UI diagnostics; see
[PHASE78_ACCEPTANCE.md](PHASE78_ACCEPTANCE.md). Focused command and scripting
regressions do not complete full campaign playthrough QA.

## Phase 8 — Multiplayer and replay 🟠

**Delivered:** serialized commands, deterministic lockstep/input buffering/checksums,
replay recorder/player infrastructure and tests; direct-IP TCP LAN host/join, selectable
port, 2–4 humans with optional AI, readiness/configuration and content checks.
Disconnects/desync stop matches; LAN disables independent pause and save/load.

**Implemented in the v0.8.0 source increment (PR #39):** automatic human-command replay recording,
paged browser and read-only playback with pause/speed/end controls and content/version
validation. See [REPLAYS.md](REPLAYS.md). Reconnect has tested snapshots, authenticated
barriers, delayed-input journals and bounded transfer primitives only; these are NOT
enabled in production LAN. Live disconnects still terminate matches.

**Pending:** production distributed freeze/rollback, acknowledged-input reconciliation,
reconnect/resynchronization and atomic UI/recorder handoff; end-to-end mixed-platform
acceptance. Final replay/source verification passed; see [PHASE78_ACCEPTANCE.md](PHASE78_ACCEPTANCE.md).
See [LAN_RECONNECT.md](LAN_RECONNECT.md) for the remaining backend work.
Eight-player capacity is a separate pending expansion: maps, UI/setup and load/network
testing must all grow together. The existing LAN lobby is not a missing feature.

## Phase 9 — Modding 🟠

**Delivered:** CLI `--mods`, example mod, data-folder overrides, catalogue loading and
post-override validation. Overrides already exist; the current game-rules override
replaces that file rather than providing a general deep-merge contract.

**Pending:** defined/tested merge and load-order semantics, manifest/version/dependency
and compatibility metadata, in-game mod discovery/selection/error reporting, asset-pack
support and custom faction wizard. Preserve reproducible simulation content fingerprints
and matching content requirements for LAN/replay.

## Phase 10 — Performance, presentation and balance 🟠

**Delivered:** spatial hashing, AI cadence tiers, display-list meshes, optimized sensor
and camera queries, metal/material rendering, planets/deep space, local shield/hull
impacts, layered explosions, per-weapon procedural audio, player ownership markers,
and faction-specific ships/stations/convoys with protected Imperial geometry.

**Merged in #41 and packaged in v0.9.0:**
standard/night audio mix, mono/live gains and reserved alerts, short skippable
campaign intros/outros, paged F1 help/settings, optional recovery-drill hints,
high-contrast panels and reduced cinematic motion. Native macOS mixer and real
SDL/GL diagnostics passed at 1024×768 and 1280×800; a local frozen read-only DMG
candidate passed smoke; the published v0.9.0 DMG then passed a read-only frozen smoke,
and both published downloads passed digest/asset/code integrity checks. These changes
are not in v0.8.0. Human listening,
natural tutorial usability, native Windows and mixed-platform LAN remain open.
See [PHASE10_ACCEPTANCE.md](PHASE10_ACCEPTANCE.md) for exact gates and limits.

**Pending:** measured large-battle budgets and optimization, fighter simulation/model
LOD, GPU instancing/appropriate batching and occlusion where profiling justifies them;
human audio quality validation, broader UX/tutorial/accessibility polish, faction/economy/
combat balance and release acceptance on both platforms. Existing audio, faction visuals
and screen-size readability are not equivalent to completion of every original LOD,
audio-pack or livery requirement.

## Planetary hardware / HUD follow-up — released in v0.10.0

Independent panel minimization, inclined moving satellites with engagement pauses,
lower satellite cost/durability and six separate resource/trade/shield/pulsar surface
slots are implemented for v0.10.0. Independent reviews
approved the source and the final stable-tree suite passed 946 tests. Hardware GL
acceptance passed; final native Cocoa wheel-input QA is still focus-blocked. The user
authorized merge and release with that limit disclosed. PR #43 is merged and both
published packages passed digest, code/data integrity and macOS frozen-smoke checks.
See [PLANETARY_HARDWARE.md](PLANETARY_HARDWARE.md) for mechanics and evidence.

## Cross-cutting backlog

- **Planetary colonies and satellites:** merged in #40 and packaged in v0.7.0. Command-only colony
  ships for all four built-in factions, non-gas settlement, crew/type-resource output,
  timed capture after satellite destruction, planet-menu defense/attack production
  and AI integration. Historical PR #40 acceptance: 766 full-suite tests passed, independent review
  passed, and real SDL/GL diagnostics passed at 1280×800 and 1024×768.
  See [COLONIES.md](COLONIES.md); numeric defaults are balance proposals.

- **§27 Boarding:** merged in #37 and packaged in v0.7.0.
  Physical craft, contested control, ship/station ownership transfer, life-support
  attrition and intact abandoned hulls; historical branch acceptance: 608 headless tests passed plus
  real SDL/OpenGL boarding diagnostics. See [BOARDING.md](BOARDING.md).
- **Crew recovery:** base recruitment, commanded field transports, proportional staffing,
  cautious AI and integrated controls/diagnostics are merged in #38 (`6c76978`),
  packaged in v0.7.0; see [CREW_RECOVERY.md](CREW_RECOVERY.md).
  Historical PR #38 acceptance: 652 headless tests passed, 24 real SDL/OpenGL captures at
  1280×800 and 1024×768, exact restore/replay regressions and independent review.
  Baseline LAN test timing races were fixed without changing production LAN code.
  Numeric defaults are initial configurable balance proposals. Neutral salvage/towing
  and optional conversion/sale are outside this approved increment.
- **Planet income balance:** user-requested 5× resource and crew income is
  included in the v0.8.0 source increment, absent from v0.7.0. Focused income regressions and bounded
  faction/map/difficulty observations exist; statistical complete-match balance remains open.
- **Optional captured-vessel outcomes:** sale, conversion, captured-tech research and
  temporary use remain deferred, not required to close the core boarding loop.
- **§26 Trading:** convoy routes and persistence exist; improve convoy/escort legibility
  and audit self-trade profitability as part of the balance pass.
- **§28 Objectives:** escort/hold/survival exist; expanded scripting belongs to Phase 7.
- **§32 Saves:** quick save/load, rotating autosaves and campaign progress exist;
  player-facing replay workflow and exact future-state restoration are verified in v0.8.0 source;
  production LAN reconnect remains pending.
- **§46 Victory:** command-station/planet-majority/economic/timed modes and allied
  elimination exist. Regression-test new abandonment against each mode and campaign
  objective rules rather than assuming identical semantics.

## Proposed finish order

1. **Close interactive release acceptance.** v0.7.0 already packages #37/#38/#40;
   v0.8.0 adds the verified PR #39 source increment.
   Exercise boarding, recovery, colonies and support orders in native interactive
   Windows gameplay and mixed-platform LAN; existing CI/archive checks and the frozen
   macOS smoke do not prove these open gates. No packaging rebuild is inherently missing.
2. **Balance and integrated gameplay acceptance.** Validate the v0.8.0 5× planet
   resource income change, recruitment/loading/delivery costs and AI heuristics through
   repeatable long matches across factions/maps/difficulties. Historical source/GL
   results are not a new matrix pass; record actual results before claiming acceptance.
   No towing or neutrality expansion. The v0.12.0 release is user-authorized; later releases need separate approval.
3. **Complete campaign acceptance (Phase 7).** Scripting, reinforcement waves,
   staged/capture/crew objectives and stable-ID progression now exist. Run natural-navigation
   full playthroughs of all 11 missions and tune waves/objective pacing; do not rebuild scripting.
   Short skippable cinematics are released in v0.9.0; full natural
   mission playthrough acceptance remains separate.
4. **Next major feature: live multiplayer resilience (Phase 8).** Integrate distributed
   freeze/rollback, acknowledged-input reconciliation and atomic reconnect/resync handoff.
   Replay recording/browser/playback already exist; preserve deterministic scripting,
   capture and mid-match restoration while testing 2–4 human disconnect/rejoin scenarios.
5. **Complete faction gameplay and balance.** Resolve Syndicate scope/parity; run
   repeatable full-match economy/combat/AI benchmarks before scaling up player counts.
6. **Meet performance targets, then expand to eight players.** Profile realistic fleets,
   implement justified LOD/batching/instancing and add balanced larger maps/setup/UI.
   Require playable frame/tick times and network stability, not only eight slots.
7. **Finish mod delivery (Phase 9).** Stable merge rules, manifest/compatibility contract,
   mod selection/error UX, asset packs and faction authoring after schemas stabilize.
8. **Finish presentation acceptance (Phase 10).** Validate the v0.9.0 audio mix,
   short campaign cinematics and targeted tutorials/accessibility/UX. Human listening,
   natural recovery-drill/campaign and long skirmish/LAN playtests remain open;
   regression-check existing native macOS/Windows packaging and complete interactive
   acceptance, refreshed docs.

Optional captured-vessel outcomes can follow the core completion milestones; do not
let speculative features block shipping the required playable loop.

## Completion gates

- Each feature has simulation regressions; deterministic changes have exact restore
  and replay/LAN coverage, not only a coarse checksum.
- Player-facing changes have real SDL/OpenGL evidence and playtest acceptance.
- Full suite, independent review and branch → PR precede merge; no direct main commits.
- Released status requires verified packaged artifacts. Passing source tests alone
  does not prove Windows gameplay or cross-platform LAN readiness.
- Balance stays data-driven; the renderer remains a read-only simulation view.
