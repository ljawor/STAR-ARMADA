# STAR ARMADA — Development Plan

Phases follow spec §48. This is a delivery-status plan, not a claim of full-spec
completion. Phases 1–6 have playable prototype implementations. Later phases are
partly delivered; the remaining work is listed explicitly below.

## Status conventions

- **Delivered**: merged implementation; packaging/release coverage may vary.
- **Implemented, awaiting merge**: tested feature branch, not a released feature.
- **Pending**: missing deliverable, not merely an older roadmap label.
- Recommendations below define the proposed finish order, not additional approved scope.

## Phase 1 — Window, camera, map, selection, movement ✅ prototype delivered

pygame-ce/OpenGL, 3D tactical camera, data-driven geography, selection/control groups,
nose-first movement, minimap, geometry-safe close zoom and consistent picking.
Four skirmish maps support 2–4 total players with factions/colors/teams/difficulty.

## Phase 2 — Units, health, combat, weapons, shields ✅ prototype delivered

Data-driven fighter-to-supercapital catalogue, shield quadrants, subsystem damage,
projectiles/point defense, combat standoff/orbits, capped XP ranks and rank inspector.
Crew/life-support/boarding extensions are merged in #37. Recovery, four faction
crew transports and proportional staffing are merged in #38 (`6c76978`). Neither
increment is included in the v0.6.0 packaged release.

## Phase 3 — Resources, construction, stations ✅ prototype delivered

Credits/materials/energy/crew and command capacity; mining, reachable gas-giant energy
relays, constructor-range station orders, shipyards, research and colony bonuses.
Trade convoys, delivery, raiding and serialized commercial routes are implemented.
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

**Pending:** deterministic scripted triggers (reinforcements, timed/event-driven waves,
objective transitions), cinematic presentation and complete campaign playthrough QA.
Integrate new capture/crew mechanics into mission semantics and tutorial objectives.
Survival timers already exist; do not list them again as missing infrastructure.

## Phase 8 — Multiplayer and replay 🟠

**Delivered:** serialized commands, deterministic lockstep/input buffering/checksums,
replay recorder/player infrastructure and tests; direct-IP TCP LAN host/join, selectable
port, 2–4 humans with optional AI, readiness/configuration and content checks.
Disconnects/desync stop matches; LAN disables independent pause and save/load.

**Pending:** reconnect/resynchronization, player-facing replay recording/browser/playback,
and end-to-end mixed-platform multiplayer acceptance. Eight-player capacity is a
separate pending expansion: maps, UI/setup and load/network testing must all grow together.
The existing LAN lobby is not a missing feature.

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

**Pending:** measured large-battle budgets and optimization, fighter simulation/model
LOD, GPU instancing/appropriate batching and occlusion where profiling justifies them;
final audio quality/mix validation, UX/tutorial/accessibility polish, faction/economy/
combat balance and release acceptance on both platforms. Existing audio, faction visuals
and screen-size readability are not equivalent to completion of every original LOD,
audio-pack or livery requirement.

## Cross-cutting backlog

- **§27 Boarding:** merged in #37; not included in the v0.6.0 packaged release.
  Physical craft, contested control, ship/station ownership transfer, life-support
  attrition and intact abandoned hulls; 608 headless tests passed on that branch plus
  real SDL/OpenGL boarding diagnostics. See [BOARDING.md](BOARDING.md).
- **Crew recovery:** base recruitment, commanded field transports, proportional staffing,
  cautious AI and integrated controls/diagnostics are merged in #38 (`6c76978`),
  not packaged/released; see [CREW_RECOVERY.md](CREW_RECOVERY.md).
  Final acceptance: 652 headless tests passed, 24 real SDL/OpenGL captures at
  1280×800 and 1024×768, exact restore/replay regressions and independent review.
  Baseline LAN test timing races were fixed without changing production LAN code.
  Numeric defaults are initial configurable balance proposals. Neutral salvage/towing
  and optional conversion/sale are outside this approved increment.
- **Optional captured-vessel outcomes:** sale, conversion, captured-tech research and
  temporary use remain deferred, not required to close the core boarding loop.
- **§26 Trading:** convoy routes and persistence exist; improve convoy/escort legibility
  and audit self-trade profitability as part of the balance pass.
- **§28 Objectives:** escort/hold/survival exist; expanded scripting belongs to Phase 7.
- **§32 Saves:** quick save/load, rotating autosaves and campaign progress exist;
  replay infrastructure exists, but player-facing replay workflow remains pending.
- **§46 Victory:** command-station/planet-majority/economic/timed modes and allied
  elimination exist. Regression-test new abandonment against each mode and campaign
  objective rules rather than assuming identical semantics.

## Proposed finish order

1. **Release acceptance for boarding.** #37 is merged; verify boarding during real LAN
   play and native packaged gameplay before a separately approved version bump/release.
2. **Balance and release-test crew recovery.** #38 is merged and independently reviewed;
   source tests and real GL acceptance passed. Tune recruitment/loading/delivery costs
   and AI heuristics through long matches, then complete native packaged and mixed-platform
   LAN acceptance. No towing or neutrality expansion; no new release has been created.
3. **Next feature: complete campaign gameplay (Phase 7 logic).** Persisted deterministic triggers,
   waves/objective transitions, capture/crew objectives and playable mission progression.
   Keep cinematic polish after the mission logic is stable.
4. **Finish multiplayer/replay resilience (Phase 8).** Reconnect/resync and user replay
   workflow; prove commands, scripting, captures and saves/replays stay deterministic.
5. **Complete faction gameplay and balance.** Resolve Syndicate scope/parity; run
   repeatable full-match economy/combat/AI benchmarks before scaling up player counts.
6. **Meet performance targets, then expand to eight players.** Profile realistic fleets,
   implement justified LOD/batching/instancing and add balanced larger maps/setup/UI.
   Require playable frame/tick times and network stability, not only eight slots.
7. **Finish mod delivery (Phase 9).** Stable merge rules, manifest/compatibility contract,
   mod selection/error UX, asset packs and faction authoring after schemas stabilize.
8. **Final campaign/presentation/release pass (Phase 10).** Cinematics, audio mix,
   tutorials/accessibility/UX, complete campaign and long skirmish/LAN playtests,
   native macOS/Windows packaging and interactive acceptance, refreshed docs.

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
