# S05 — approved-trio generic-path equivalence

Local engineering evidence passed; parent owns the equivalence/approval-transfer decision.
No new model approval, production switch, merge or release is recorded here.

## Sources and measured result

- Prototype: `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c`.
- Generic preview/legacy: `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c`.
- Both are immutable `git archive` snapshots, imported in separate serial interpreters.
- E1: approved Blender, exporter and runtime pins unchanged.
- E2/E3: **102 paired frames, zero differing pixels/channels**. Ten frozen views include close, low rear, common-scale and tactical; 32 owner-colour frames exercise all eight actual `PLAYER_COLORS` on the three bindings and common-scale. Each palette produces distinct pixels. Legacy differs in every paired frame.
- Actual 1280×800, 4× MSAA, Cocoa/Apple M4, production shader materials and normal fog. No skip/fixed-material switches. Explicit cameras, actual eye and matrices recorded.
- E4: 360 real simulation ticks; 361 equal per-tick hashes. Four real AttackCommands, 70 weapon-fired events, movement, projectiles and shield/hull damage observed. Rendering preserves state on every instrumented draw (529 control, 529 preview, 510 legacy).
- E5: individually removed/reinstated geometry at the actual display-list lookup, no source edits or stale-cache reuse. Four yard worklights contribute **185 / 261 / 276 / 413** local warm pixels. Two capital emitters contribute **504 / 618** and two escort emitters **232 / 243** local cyan pixels. Each passes the broad-face floor; absent controls fail; restored frames match. Full/absent hashes and metrics equal across sources.
- E6: exported images and decoded movie samples inspected; `inspection.json`. `verification.json` is the post-inspection result. The raw `summary.json` intentionally preserves its pre-inspection pending E6 rather than rewriting the original run.
- E7: no prototype/generic appearance difference detected; renewed appearance approval not triggered. No approval is inferred from AI judgement.

## Review artifacts

- `review-sheet.png`: prototype / generic preview / legacy, three close views.
- `owner-palette-sheet.png`: actual supported palette on the three specimens and common scale.
- `candidate/`: full-resolution selected captures, low-rear features and eight individual absent-feature controls.
- `paired-motion.mp4`: **60 frames / five seconds**, side-by-side. Samples span 12 seconds of real fixed-step simulation (2.4× time compression); common-scale, followed capital, followed escort, then yard. Yard translation is static; normal station presentation rotation, camera motion and surrounding battle continue. This is not a claim that a shipyard moves as a ship.
- `video-probe.json`, `video-decode.txt`, `video-{0,2,4}s.png`: counted and successfully decoded actual movie.
- Per-source `summary.json`: full tick hashes, states, commands, paired frame metrics, camera matrices, GL contract, feature metrics and source manifest preservation.
- `user-preservation.json`: byte hashes before/after for live checkout and worktree user saves/replays/settings; unchanged. Five menu paths patched before consumers construct.

## Exact execution commands

Run from `/Users/lukaszjawor/.hermes/cache/scratch/star-armada-s05`:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_trio_generic_equivalence test_alliance_blender_trio test_alliance_blender_battleship test_ship_material_passes test_asset_selection test_detmath
.venv/bin/python tools/diag_trio_generic_equivalence.py run --output /Users/lukaszjawor/.hermes/cache/scratch/s05-equivalence-run04
.venv/bin/python artifacts/s05_trio_generic_equivalence/publish.py --run /Users/lukaszjawor/.hermes/cache/scratch/s05-equivalence-run04 --out /Users/lukaszjawor/.hermes/cache/scratch/star-armada-s05/artifacts/s05_trio_generic_equivalence
```

The focused command actually ran **47 tests, OK**, including real-GL material-role checks; no full suite or benchmark. Reproduction needs a *fresh* run output path; existing run outputs are refused, not overwritten. `commands.json` retains the exact child invocations. Large raw comparison arrays and archived source trees stay in scratch run directories, not durable evidence.

## Retained attempts and limitations

- `tests-red-01.txt`, `tests-green-01.txt`, `tests-red-02.txt`, `tests-green-02.txt`: measurement helper RED/GREEN receipts (new helpers missing before implementation).
- `attempts/s05-equivalence-run01`: control completed; candidate encoder stdout attempted `/dev/null`, rejected by the inherited write guard. Encoder now logs inside output; guard unchanged.
- `attempts/s05-equivalence-run02`: 101 paired frames and E1–E5 passed. Later strengthened to pair escort low-rear explicitly, retain feature pixel hashes and assert palette discrimination.
- `attempts/s05-equivalence-run03`: one-warmup attempt had an unstable same-source repeat at motion tick 42. Original failure retained; not labelled an application defect. Final harness restores the mandated three warmups, still demands exact repeat equality and exports failed pixel pairs/metrics for future failures. Final run04 passes; no tolerance relaxed.
- No game/render/assets/exporter/existing-test files changed. Parent-owned roadmap/handoff/criteria edits are outside this worker's scope. Nothing staged, committed, pushed or merged.
- Not Windows/native package, full-suite, performance, new model approval or S11 acceptance.
