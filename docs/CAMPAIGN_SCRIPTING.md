# Deterministic campaign scripting (Phase 7 increment)

## Contract

Existing objective-only definitions continue to work. Scripts are optional `triggers`
on a mission definition. Every trigger has a unique string `id`, a `when` object,
and a nonempty `actions` list. Conditions are ANDed:

- `tick`: absolute simulation tick, nonnegative integer.
- `time`: absolute simulation seconds, finite and nonnegative; never wall-clock time.
- `event`: gameplay event name, optionally `match` for exact payload fields.
- `objective`: the ID of an objective which has completed.

Events latch per trigger immediately, including before a timer becomes due, and are
persisted. No reliance on the transient event log/ring or reinstalling callbacks
lazily. Triggers execute once in definition order in `MissionSystem.update`, after
normal trading. Gates see earlier actions in that pass. Objectives completed by the
normal objective scan enable their dependent triggers on the next mission pass.
Reinforcements are inserted after combat; they first act on the next manager tick.

Actions:

- `reinforcements`: ordered `units` with catalogue `ship`, existing player `owner`,
  and finite `[x,y,z]` `pos`. Each unit is produced by `UnitFactory`, including
  squadrons. Optional `crew` gives an integer initial complement (0 creates an
  owned derelict). Optional `shields_down: true` empties shields and disables the
  shield generator for a boardable drill target. These are scenario setup, not
  resource-paid production or a synthetic `ship_built` event.
- `activate_objective`: names an objective ID; preserves existing progress.
- `complete_objective`: marks an objective done without claiming player action.
- `fail_mission`: terminal failure; the remainder of the script pass stops.

An objective with `active: false` is hidden from progress text and cannot receive
build/capture/recovery/escort progress or accrue hold/survival progress. Only active
objectives participate in the completion test. Triggers default to `required: true`,
so an outstanding stage activation/wave blocks premature mission completion.
`required: false` permits optional triggers which may never fire before victory.
A scenario author must provide required activation gates for intended later stages.
No historical events are retroactively credited when a stage becomes active.

Human-force loss after the existing five-second grace and active failed objectives
are checked **before** scripts. Failure wins over simultaneous completion/deadline;
a scheduled reinforcement cannot resurrect a force already lost on that tick.
Once terminal, mission callbacks and scripts cannot mutate progress or republish
outcomes. Campaign outcomes remain objective-owned, not skirmish elimination.

## Tutorial objectives

`capture_unit` counts hostile-to-human ownership transfers emitted by the real
boarding system. Optional `ship` and `entity_id` narrow the target; `count` defaults
to 1. It is not completed by mere destruction, abandoned status or allied transfer.

`recover_crew` counts actual personnel transferred to operational human-owned hulls
via `crew_delivered` / `crew_replenished`; no hull repair, passenger loading or
initial staffed spawn earns progress. Optional `ship`, `entity_id`, and `method`
restrict attribution. `count` defaults to 1. This is a personnel-count milestone,
**not** a full-complement repair/recovery acceptance test. The real recovery system
continues to enforce ownership, life-support safety, resource costs and conservation.
Exact partial count and the last recovered entity ID are saved.

## Persistence and integration

`mission_state` contains the definition, objective progress and terminal flags plus
`script: {fired: [...], spawned: {trigger_id: [entity_id, ...]}, events: {...}}`.
IDs are inserted in definition/unit order; progress uses deep copies and full
precision. Restore consumes the temporary state snapshot and reinstalls subscriptions
before the first manager tick. Replay initial states include this same precise JSON;
no separate replay command type is needed. Exclude the live `mission.script` object
from generic introspection checksums; the canonical mission dictionary already
contains its authoritative state.

Catalogue and supplied/restored mission scripts are validated for unknown ships,
invalid timers, duplicate IDs and missing objective references. This is a bounded
script format, not a general sandbox. Authors remain responsible for reachable
geometry, existing player slots, sensible wave balance and acyclic activation chains.
No cinematics, arbitrary executable callbacks, repeat-wave DSL or editor is included.

## Actual content

- `m00_recovery_drill` precedes First Fleet: a cruiser/command station, scripted crew
  transport, owned abandoned frigate and shieldless hostile derelict. Capture opens
  the field-delivery objective. Healthy life support keeps repair teaching separate.
- `m01_first_fleet`: starts with a usable shipyard; briefing now agrees with the
  two-new-corvettes objective rather than claiming an unrequested constructor build.
- `m02_supply_line`: starts with one owned market; briefing asks for a second legal
  market so friendly trading is possible instead of depending on an enemy market.
- `m06_rebel_hunt`: two actual counter-strike waves at 60/120 simulation seconds;
  destroy-all clearance becomes active only after the second wave.

## QA evidence and limits

Focused command:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_campaign_phase7_script test_campaign_lifecycle test_trading -q
```

The new regressions cover once-only waves, latched event restore, stage transitions,
first-active-tick trading subscriptions, failure precedence (including an actual
raided convoy versus a scripted completion), validation, exact JSON-normalized
`to_dict(precise=True)` equality immediately and on every continuation tick, and
replay initial snapshots with command injection. Existing lifecycle regressions
retain survival/loss, captures and campaign restore coverage.

The catalogue drill probe runs real serialized `board`, `crew_load` and
`crew_deliver` through `GameManager.step`, produces a real boarding craft/ownership
transfer and real personnel delivery, and compares a JSON replay snapshot during
capture plus a snapshot during delivery. For bounded automation it repositions the
cruiser/transport and disables cruiser weapons. The wave-content probe moves the
simulation clock to timer boundaries. The generic event-latch test publishes a
synthetic jump event **only to test trigger plumbing**; it is not campaign gameplay.
None of these is a full natural-navigation playthrough or human campaign acceptance.

Campaign progression and catalogue UI regressions:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_mission_hud_layout test_campaign_phase7_progress test_campaign_main test_campaign_phase7_script test_campaign_lifecycle test_trading -q
PYTHONPATH=. .venv/bin/python tools/diag_campaign_phase7.py --out <artifact-directory>
```

The expanded focused run passes 46 tests (28.150 seconds locally). Strict test-first reproduction caught legacy
`mission_index: 0` returning 0 instead of the current First Fleet index 1, then
caught an offscreen campaign row before paging was implemented. Schema v2 stores
`unlocked_mission_ids`; legacy indices map through the frozen original ten-mission
order. Migration is idempotent. A fresh profile unlocks only mandatory `m00`; legacy
index 0 retains both `m00` and First Fleet, without requiring the tutorial again.
Numeric load/save compatibility adapters remain available; the list uses stable
IDs rather than treating the highest index as a blanket unlock after reordering.

The actual Cocoa SDL/GL diagnostic enumerates all 11 exact row IDs over two pages
at 1024×768 and 1280×800, checks every rendered hitbox for viewport containment and
pairwise overlap, and selects **and renders the briefing of** every unlocked row
through production SDL input. All briefing panels remain onscreen and separate from
launch/back controls. It launches the tutorial, verifies read-only rendering and
zero GL errors, and writes 31 unique framebuffer captures per resolution (62 total).

**Mission HUD gates now pass.** The interrupted word-only wrapper left unbroken mod
tokens at 504px, wider than either card; the regression reproduced six failing
resolution/terminal-state subcases before the measured-glyph splitting fix. Existing
assertions were retained. The card reserves both side-control columns (344px wide
at 1024, 380px at 1280), wraps titles/objectives/terminal labels, and grows from
actual rendered line heights. The diagnostic records every actual text `blit`
rectangle emitted inside `_mission_panel` and its actual blocked card, not an old
380×62 estimate or the width of an unwrapped source string. Across 16 measured
frames per resolution, all 76/71 mission text blits remain inside padded cards,
with zero text/card-control overlap or overflow. Active/complete/failed long-token
stress frames and real mission-complete frames are included and visually inspected.

Natural initial input still covers boarding prompts, hidden-target rejection, crew
loading (15 passengers) and delivery navigation (294.221 units over six simulation
seconds). A separately labelled **controlled fixture** then repositions the cruiser
200 units from the hostile drill target and disables cruiser weapons. Real HUD
button/target clicks issue the detected-target `board` command, which the production
handler accepts and launches a physical boarding craft. The real `unit_captured`
event changes ownership and activates the crew-recovery objective. The loaded
transport is then repositioned 100 units from the frigate; another real HUD targeting
gesture issues `crew_deliver`. Fifteen real personnel deliveries complete the
tutorial. No timers are jumped or synthetic objective events published. This proves
controlled production-command/capture/objective continuation, **not** natural
whole-mission navigation, balance or human acceptance.

The earlier extended probe exposed a genuine AI future-state restore divergence at
tick 571. This is now fixed by canonical runtime persistence, not by shortening
acceptance probes. The rerun in `campaign-phase7-future-state-fixed/` matches exact
state immediately and through all 240 capture plus 90 delivery continuation ticks
at both resolutions. Additional save/replay regressions cover starts at ticks
37/150/300 for 360 subsequent ticks and actual tutorial stages for 420 ticks each.
The old divergence artifacts are retained as historical RED evidence, not an open
failure on the current tree.

Artifacts: `/Users/lukaszjawor/.hermes/cache/scratch/campaign-phase7-future-state-fixed/`.
Historical HUD/failure evidence: `campaign-phase7-hud-final/` under the same scratch root.

Outstanding: naturally navigated whole-mission human playthroughs;
combat-wave balance and all ten combat missions;
platform/release/LAN acceptance. Cinematics remain optional/deferred. Source-level
success must not be described as full human campaign acceptance or released delivery.
