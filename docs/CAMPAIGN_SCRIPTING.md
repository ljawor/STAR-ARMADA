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

Opt-in `full_complement: true` changes `recover_crew` to a **live onboard-state**
goal. `captured_objective` must reference a single-unit `capture_unit` objective.
That capture persists its exact `captured_id`; recovery checks only that living,
human-owned hull and requires `crew >= max_crew > 0`. Another hull of the same
class, cumulative transfers, loaded passengers and equipment repairs cannot finish
it. Do not set `method`: both automatic recruitment and transport delivery count.
The scan runs after stage activation, so a boarding party that already fills the
complement completes immediately without a subsequent delivery/recruitment event.
The captured ID, partial onboard progress and stage state survive precise saves.
Existing event-count recovery definitions and saved definitions retain their old
semantics. Campaign unlock IDs and the frozen legacy-index migration are unchanged.

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
  a 100% onboard-crew objective on THAT captured syndicate corvette. Automatic base
  recruitment and transport delivery both count; no delivery event is required.
  The frigate remains optional practice, never a completion requirement. Healthy
  life support keeps repair teaching separate. A full surviving boarding party can
  finish immediately; general boarding and personnel mechanics are not changed.
- `m01_first_fleet`: starts with a usable shipyard; briefing now agrees with the
  two-new-corvettes objective rather than claiming an unrequested constructor build.
- `m02_supply_line`: starts with one owned market; briefing asks for a second legal
  market so friendly trading is possible instead of depending on an enemy market.
- `m06_rebel_hunt`: two actual counter-strike waves at 60/120 simulation seconds;
  destroy-all clearance becomes active only after the second wave.

## QA evidence and limits

### Issue #80 current source verification

`tests/test_recovery_drill.py` first failed on the old drill for full-complement,
automatic-recruitment and captured-corvette transport completion. Controlled
fixtures launch a real boarding craft, then reduce its complement to four survivors
to leave a meaningful recovery stage (a fully staffed cruiser otherwise captures
this corvette with 36/36 crew). Both recovery methods finish at exactly 36/36;
wrong-class-instance, hostile/dead target and partial-complement controls do not.
Full JSON-normalized precise equality holds immediately and every continuation tick
for mid-recruitment (300 ticks) and mid-delivery (120 ticks) restores.

The updated `tools/diag_campaign_phase7.py` passes on real Cocoa SDL/OpenGL at
1024×768 and 1280×800. Each resolution enumerates/renders all 11 campaign briefings,
records 32 framebuffers, verifies actual mission glyph blits inside padded cards,
hint glyph containment, read-only precise state, zero GL errors, and zero objective
overflow/control overlap. Exact restoration holds through 600 capture and 150
mid-objective-delivery ticks; the latter starts at 8/36 onboard crew, not after
completion. Captures and the exact mid-objective saves are in
`/Users/lukaszjawor/.hermes/cache/scratch/issue80-gl/` (`report.json`,
`1024_mid_objective_save.json`, `1280_mid_objective_save.json`); RED evidence is
`/Users/lukaszjawor/.hermes/cache/scratch/issue80-red.log`.

#### Strict replay review-blocker follow-up — October 12, 2026

Earlier direct state/ReplayPlayer restoration did **not** establish acceptance at
production's untrusted replay boundary. Before the schema fix, the new
`test_recovery_drill_replay` regressions ran red: four errors in 2.955 seconds,
rejecting fresh/mid-recovery `captured_objective` and legacy capture progress
`captured_id`. Log: `~/.hermes/cache/scratch/80-replay-schema-red.log`.
An additional immutable `e9152ed` schema control rejects all 12 combinations of
fresh/mid-recovery/legacy-capture and validate/save/load/PlaybackSession;
`~/.hermes/cache/scratch/80-replay-schema-baseline-entrypoints.json` records
exact errors and the audited objective field sets.

Audit confirmed `recovered_id` was **already** typed and mutable before #80.
The missing schema entries were `captured_objective: str`,
`full_complement: bool`, and `captured_id: int`; capture progress is now mutable,
while both definition fields remain identity-bound. Entity/capture/recovery IDs
are strict integers bounded to 0..100000000, matching replay command IDs.
Campaign validation still checks the referenced single-capture objective and
rejects method-specific full-complement definitions; unknown fields still reject.

The six new regressions exercise production MatchRecording validate/save/load
and PlaybackSession for fresh, mid-recruitment and legacy event-count capture
progress, full precise state immediately and every recorded tick (300 ticks
through mid-recruitment completion), malformed types/ranges/definition mutations,
accepted ID endpoints, and the warned legacy projection without runtime state.
Legacy tests use controlled historical-shape fixtures, not an archived user file;
missing future AI/timers still carry the existing compatibility limitation.
Final focused replay/campaign run: **81 tests passed in 72.622 seconds**, log
`~/.hermes/cache/scratch/80-replay-campaign-focused.log`. Compile and diff checks
passed. No new full-suite or independent re-review claim is made here.

After the final schema/test changes, real Cocoa campaign GL passed again:
`DIAG_CAMPAIGN_PHASE7_UI_AND_CONTROLLED_CONTINUATION_OK`, both 1024×768 and
1280×800, 64 PNG captures, 750 exact restore continuation ticks per resolution,
real capture and 36/36 crew completion, zero GL errors/overflow/control overlap.
Evidence: `~/.hermes/cache/scratch/80-replay-schema-campaign-gl/` and sibling
`.log`; completion captures at both sizes were also visually inspected.
This diagnostic verifies controlled campaign UI/restore, not the replay browser.

This is controlled production-command/HUD acceptance, not a naturally navigated
human playthrough. Repositioning, disabled cruiser weapons and four-survivor craft
setup are explicit fixtures. Windows, balance, release and integrated full-suite
acceptance remain separate. The following Phase 7 evidence is historical and its
frigate-delivery objective is superseded by #80.

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
PYTHONPATH=tests .venv/bin/python -m unittest test_mission_hud_layout test_campaign_phase7_progress test_campaign_completion_flow test_campaign_main test_campaign_phase7_script test_campaign_lifecycle test_trading -q
PYTHONPATH=. .venv/bin/python tools/diag_campaign_phase7.py --out <artifact-directory>
```

The expanded focused run passes 46 tests (28.150 seconds locally). Strict test-first reproduction caught legacy
`mission_index: 0` returning 0 instead of the current First Fleet index 1, then
caught an offscreen campaign row before paging was implemented. Schema v3 stores
`unlocked_mission_ids` plus `completed_mission_ids` (the won missions the campaign
screen marks COMPLETE in gold, still selectable for replay); legacy indices map
through the frozen original ten-mission order and v1/v2 files load with an empty
completed set. Migration is idempotent. A fresh profile unlocks only mandatory `m00`;
legacy index 0 retains both `m00` and First Fleet, without requiring the tutorial
again. Numeric load/save compatibility adapters remain available; the list uses stable
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
