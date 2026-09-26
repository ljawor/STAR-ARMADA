# STAR ARMADA — Development Plan

Phases follow spec §48. The vertical slice (Phase 1–6 partial) is complete and playable;
later phases build on it without rewrites.

## Phase 1 — Window, camera, map, selection, movement ✅
pygame-ce window, modern-OpenGL renderer, 3D tactical camera (pan/rotate/zoom, fighter→
capital scale), map from JSON (planets, asteroids, nebulae, jump points), box select,
control groups, movement with acceleration/turn + soft collision separation.

## Phase 2 — Units, health, combat, weapons, shields ✅
Data-driven ships (fighter→supercapital), hull/shield quadrants, subsystem damage,
weapon types with multipliers vs shields/armor, projectiles, point defense,
experience levels.

## Phase 3 — Resources, mining, construction, stations ✅
Credits/materials/energy/crew + command capacity; mining stations on asteroid fields;
construction ships build all stations; shipyard builds ships; planets colonizable
(colony ships→build orders on planets) with bonuses; trade income.

## Phase 4 — Technology, upgrades, special abilities ✅
Per-faction tech trees (weapons/defense/propulsion/sensors/logistics), research stations
required, abilities (engine overdrive, shield recharge, weapon overcharge, EMP burst,
fighter scramble, repair drones, hyperspace jump) with cooldown/energy.

## Phase 5 — Fleet management, formations, fighters, carriers ✅
Fleets + commanders (4 archetypes with fleet-wide bonuses), formations
(line/wedge/column/diamond/screen/escort), squadrons with carrier reinforcement.

## Phase 6 — AI ✅ (prototype level)
Strategic AI 1 Hz (economy→expansion→tech→fleet→defense), tactical AI 5 Hz
(attack/retreat/focus). Difficulty via income/decision modifiers.

## Phase 7 — Campaign, missions, objectives, cinematics 🟠
MissionSystem + objectives implemented; 1 tutorial mission defined (`campaign/m01.json`).
Next: 10-mission chain per spec §29, briefing screens, scripted triggers, victory
cinematics.

## Phase 8 — Multiplayer architecture 🟠 next
Command-queue + serializable state already in place. Next: fixed-tick lockstep (20 Hz),
input-delay buffer, command log replay, per-tick checksums, lobby (LAN), reconnect.
Determinism requirements: no wall-clock in sim, seeded RNG in state, ordered command
consumption (all present).

## Phase 9 — Modding 🟠
All balance is JSON. Next: mod folders with override/merge semantics, in-game mod list,
asset-pack manifest, custom faction wizard.

## Phase 10 — Optimization, graphics, audio, UI polish, balancing 🔲
Current: spatial hash, AI tiers, pooled effects, display-list ships.
Next: LOD fighter simulation, GPU instancing for fighters, occlusion/LOD models,
spectrogram-tested procedural audio pack, balance pass with auto-battle harness
(headless AI vs AI batch runner exists: `python main.py --demo`).

## Post-slice backlog (spec sections)
- §26 Trading: trade station income ✅ (prototype) → routes, convoys, raiding
- §27 Capture/boarding: schema fields reserved (`boarding`) → disable+board minigame
- §28 Map objectives: destroy-station ✅ → convoy escort, hold-point, survival timers
- §32 Save: quick save ✅ → autosave ring, campaign slots, replay files
- §46 Victory: command-station ✅ → planet majority, economic, timed objectives

## Working rules
- Simulation stays UI-free; every new feature lands with a headless test first.
- No placeholder functions that silently do nothing — unfinished systems raise or are
  listed here explicitly.
- Balance values only in JSON.