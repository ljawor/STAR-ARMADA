# Issue #76 — Nebula Frontier fighter altitude

## Outcome and scope

The user's last replay reproduces this defect. Fighter **28** is detected and
pickable; the attack commands are accepted, but the four corvettes cannot reach
its altitude. The fix changes **MovementSystem only**, with no catalogue tuning,
range inflation, XZ-only sensor tests, position flattening or projectile changes.

The steering direction now includes elevation while retaining yaw-directed
horizontal thrust, the existing acceleration/speed limit and swept 3-D combat
keep-out. Combat orbits converge toward the detected contact's elevation plane;
a directly overhead contact gets a deterministic horizontal tangent so it cannot
remain forever outside a yaw-only front weapon arc. Coplanar combat remains
full-precision identical to the immutable original for 300 executed manager ticks,
including three actual pursuer firing events (a separate coplanar control scene).

## Immutable compatible replay baseline

- File: `match-403f1985031d4e199ef6cdb9cf434e8e.json` (read-only user recording).
- SHA-256: `7f896227524facb7c764a4f8cd35856e5098735ad69dfa42c7eeeb495261a142`.
- Created: `2026-10-12T14:59:30.684411+00:00`; v2; game `0.11.0`.
- Map: `skirmish04`, **Nebula Frontier**; seed 12345; 214 human commands.
- Content digest: `9820514e0960032f93c0f8c8d9b137cf6a93c2110f75330df48f104028402461`.
- Source: `f913802`; exact version/content checks passed. All **111156** recorded
  ticks were executed, including the commandless tail; baseline run took 661.51s.
- The published `v0.11.0` tag was tried first but rejected by the content check.
  That was a probe compatibility failure, not a gameplay reproduction; validation
  was not bypassed. The assigned source base matches both recorded metadata fields.

## Actual fighter path and root cause

Fighter 28 starts at `(12971.877955147836, 0, -595.8634409809512)`.
Small nonzero separation offsets exist by tick 9000. At tick **20716**, the
SeparationSystem gravity pass changes its vertical velocity from 0 to
`0.12037575456622737`. Its pre-pass position is
`(4787.690703029671, 2.7919535694444266, -1775.487207542673)`:
it is 2160.0159305206234 units from gas giant 10, inside that giant's
`2100 + 22 + 40 = 2162` keep-out. The nearest *centre* is planet 14, but that
smaller planet is not the responsible overlapping well. The stage trace records
928 significant vertical-velocity changes through tick 24000; the largest accepted
vertical velocity is `137.67418097943434` at tick 21094.

By tick 24000 the fighter is lofted to y `1884.7437345410965`. Original movement
thrust is `Vec3(sin(yaw), 0, cos(yaw))`; its nose-first projection rewrites only
velocity X/Z, leaving gravity-generated Y motion unsteered. Later braking leaves
the fighter stuck at that altitude even though its move destination is on y=0.
Pursuers use the same horizontal-only thrust. This is an altitude-navigation
failure, not a picking, secrecy, projectile collision or hull-damage failure.

Actual human attacks on fighter 28 occur at ticks **96677** and **109825**, with
units `[535, 536, 537, 545]`. At tick 109825:

- fighter: `(11463.46860285947, 1884.7437345410965, 171.1095634896808)`, hull 60;
- corvette 535: `(11104.395418883423, 0, -162.7707522800506)`;
- all four corvettes already have accepted `attack`, `order_target_id=28` and
  `current_target=28`; detection is true through the actual remote observers;
- their physical 3-D separation exceeds the unchanged 900-unit laser range.

## Executed acceptance evidence

| Gate | Result |
|---|---|
| Regression before implementation | Replay-altitude pursuit and pure vertical move fail; corrected fixtures also fail under immutable original code. |
| Overhead-contact edge | Added red test exposed the vertical-pole orbit/front-arc stall, then passed with elevation-plane orbit steering. |
| Final original-code control | Exactly 3 expected failures, no test errors: altitude pursuit, vertical move, overhead contact. |
| Focused tests | **95 passed**, covering six new altitude tests, standoff, sensor combat, projectile aim, arcs, fighter exploration and multiplayer determinism. |
| Exact continuation | Full JSON-normalized precise state equal immediately after mid-flight restore and every executed subsequent tick: baseline 300; fixed 181 through terminal victory. A separate minimized fixture compares 300 step calls. |
| Real SDL/GL | Cocoa SDL, Apple M4, 1280×900; actual production Renderer, Camera, InputController picking, posted SDL right-click, command handler and complete combat pipeline. |
| Projection/picking | True-altitude camera projection agrees with real `gluProject` within 0.1 px; picker returns 28 and SDL dispatch queues the exact recorded attack payload. |
| Non-vacuous framebuffer control | Initial baseline/fixed PNG bytes identical; read-only render/pick state, nonempty framebuffer and zero GL errors asserted. |
| Original exact scene | 1331 executed ticks, corvettes remain y=0, **0 launched projectiles / 0 hits**, fighter remains at full hull 60. |
| Fixed exact scene | **13 launched projectiles / 8 hits**; pursuers climb as high as 605.0634550065254; fighter dies at tick **110081**. |

The fixed continuation starts from the real baseline snapshot immediately before
the second recorded attack; no entity repositioning, sensor enlargement or weapon
changes are used in the GL proof. The minimized unit fixture uses one explicit
remote observer in place of the replay's developed detection network.
The diagnostic camera is an **inferred view**, not recorded replay camera telemetry.
PNG captures are before flip and vertically corrected. Snapshot restoration omits
transient effects, but the subsequent combat frames contain real generated effects.

## Repeatable commands

From the assigned worktree, with the canonical environment:

```sh
PY=/Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python
REPLAY=/Users/lukaszjawor/Downloads/Project/STAR-ARMADA/replays/match-403f1985031d4e199ef6cdb9cf434e8e.json
OUT=/Users/lukaszjawor/.hermes/cache/scratch/evidence76

# Full immutable-original playback, with version/content validation and snapshots.
PYTHONPATH=. "$PY" tools/trace_nebula_fighter.py \
  --replay "$REPLAY" --baseline f913802 --out "$OUT/retrace"
# Shorter, stage-instrumented origin trace executed separately with --until 24000.

PYTHONPATH=tests:. "$PY" -m unittest \
  test_nebula_altitude test_combat_standoff test_sensor_combat \
  test_projectile_aim test_fire_arcs test_fighter_exploration test_multiplayer -q

PYTHONPATH=. "$PY" tools/diag_nebula_altitude.py \
  --snapshot "$OUT/state-109825.json" --out "$OUT/gl"
```

Retained local evidence is under `evidence76/`: original `trace.jsonl`, precise
`state-*.json`, `origin/gravity-velocity-changes.json`, `origin/trace-report.json`,
`immutable-red-tests.log`, `focused-tests.log`, `gl-run.log`, `gl/report.json`,
`gl/baseline-before.png`, `gl/baseline-after.png`, `gl/fixed-before.png`,
`gl/fixed-climbing.png`, `gl/fixed-first-hit.png`, `gl/fixed-after.png` and exact
mid-flight save dictionaries. Full original playback log is the sibling
`evidence76-run.log`. No user recordings or saves were overwritten.

## Pending acceptance

Independent parent review, stable integrated whole-suite execution, natural human
playthrough and native Windows acceptance remain open. No full suite, push, PR,
merge, version bump or release was performed. The fixed full replay from tick zero
was not used to claim equivalence: the intentional navigation correction changes
subsequent decisions; the immutable complete baseline plus exact failing-scene
continuation establish this bug and its repair.
