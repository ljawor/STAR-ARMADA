# S06 five placement repairs — engineering evidence, not approval

Base: `a5f3312ac93d317d6c8e51e8e613b92b5d840831`, branch
`feat/s06-next-model-batch`. Scope is kickoff §4.1–4.2 only. Blender was
`5.0.1` (build `a3db93c5b259`). No renderer, gameplay data, registration,
approval, activation, roadmap or B3c changes. Implementation receipts below precede
publication; the latest PR #127 comment carries the exact pushed head and CI status.

## Results

All five unchanged seeds were first run with explicit `--replace-seed` and
refused before saving. `refused-*.txt` retains complete original Blender
output; `refusal-summary.json` records exit 1 and unchanged master hashes,
with the original source hashes in `baseline-hashes.json`.

| Asset | Actual first refusal | Placement repair | Final triangles |
|---|---|---|---:|
| syndicate_sensor_station | Mast head → Marker lights 0, 33.86 | Mast sized/centred between its keel seat and its head underside, both derived from the binding frame | 3832 |
| syndicate_mining_station | Rail post 0 → Base plating 10, 24.50 | Rig deck, bays and deck-mounted equipment placed from keel rail height (`lo[1] + 5`); derrick feet follow that deck | 3728 |
| syndicate_energy_relay | Relay pod left → Bay machinery 5, 20.01 | Both pods seated directly under their transverse truss at its Z centreline; grids follow pod undersides | 3720 |
| legion_mining_station | Forward ram → Drill arm left, 12.01 | Spine deck centred on keel frame and reaches the ram rear face | 4268 |
| alliance_carrier | Island window band 0 → Dorsal armour strake 2, 12.90 | Taper-following glazing solids straddle the external island flank | 8656 |

The handover's Legion 17.18 was an existing-member audit, not the first
refusal of the current seed. Both measurements concern the old design; the
retained actual refusal is 12.01. No `max_brace` change or new structural
scaffold braces were used; `alliance_common.py` is byte-identical to base.

`placement-attempt-1-*.txt` and `seed-pass-2-*.txt` are two successful
rebuilds per asset. The four station seeds report `clusters_left=1`,
`breaches=0` and `SEED_OK`. The existing carrier seed has no `SEED_OK` or
`SELFCHECK` instrumentation: its successful save and `WELD_TOTAL
clusters_left=1` are in its logs, and its exported geometry/bounds are
independently checked. Do not infer a carrier self-check line that it never
printed.

`export-pass-{1,2,3}-*.txt` retains three successful exports per asset:
one from the first rebuild, then two from the second rebuild. All runtime
bytes match across all three exports, all exports preserve their own
master's source hash, and all six bounds equal the base export to the
last digit. `reproducibility.json` records hashes, bounds and counts.
Blender master binaries need not be byte-reproducible between rebuilds.

## Carrier correction after failed independent review

The initial repair passed connectivity but buried the glazing inside the island.
`independent-review-1.json` preserves the failed review; `reproducibility.json`
and the first-repair logs remain historical, not final carrier acceptance.
`carrier-correction.json` supersedes that carrier row: two byte-identical exports,
unchanged master through export, exact six baseline bounds, 8,656 triangles,
5,026 vertices and 547,192 bytes. No shared guard or exporter changed.

`carrier-surface-red.txt` records the live-recipe and payload failures before the
correction. Six taper-following solids now straddle the actual external flank.
The tests execute the live recipe without Blender, check the exported coordinates,
ray-test actual opaque triangles and reject buried/midpoint-only controls.
The rejected first repair fails 53 ray samples (`carrier-ray-historical-red.txt`).
The final parent union passed **132 tests in 10.941 s** (`parent-final-tests.txt`);
sidecars report **0 stale**. The earlier 125/128-test receipts below predate this fix.

B1 review was regenerated at the same cameras with both 150-frame paired clips;
B3b evidence was retained unchanged by the carrier-only correction. Its protected
snapshot therefore records the earlier carrier, not a current dependency.
The prior carrier source/export/B1 evidence remain in local scratch
`s06-carrier-correction-backup/`. The parent inspected final close/rear frames:
glazing is visible on the close island flank; the rear camera hides those flanks.
No appearance approval follows these checks. Generated B1 ffmpeg whitespace was
normalized only; originals remain in that backup's `raw-ffmpeg/`, with hashes in
`carrier-ffmpeg-normalization.json`.

## Regression and batch verification

- `tests/test_s06_placement_repairs.py`: Blender-free AABB minimum-spanning
  connectivity gate ignoring generated `95 Weld` members, displacement and
  empty-geometry controls, plus exact six-bound preservation. Before seed
  edits, `regression-red.txt` records failures for all five baseline assets
  and a passing negative-control test. `regression-green.txt` is the first
  green, and `regression-final.txt` is the final three-test pass including
  the added exact-bounds preservation check.
- The AABB gate measures minimum fitting-sized connectivity, not exact
  surface intersection, weld order, or historical brace provenance. Its
  failure pairs can therefore differ from the real seed refusal pair.
  Real Blender seed runs and the existing exported floating-parts guards
  are complementary evidence, not replaced by the AABB guard.
- `shared-125-tests.txt`: the requested eleven-module command passed
  **125 tests, 7.092 s**, in the supplied order, no skips or failures.
- `sidecars-*.txt`: regenerated B1 and B3b sidecars and checked each batch;
  `sidecars-all-check.txt`: **0 stale** across all pending batches.
  Only ten sidecars changed: carrier plus all nine B3b records because
  their shared seed hash changed. All remain pending with activation false.
- `scope-preservation.json`: exactly five runtime meshes, five masters,
  two seed scripts and ten pending sidecars changed among the preflight
  inventory; all other inventoried sources preserved. Approved trio, B3a,
  B2, cruiser and unrelated runtime meshes remain unchanged. Render and
  assets/data remain unchanged.

The requested shared invocation (no full suite/performance gate):

```sh
env -u SDL_VIDEODRIVER PYTHONPATH=tests .venv/bin/python -m unittest \
  test_alliance_blender_b1_combat test_alliance_blender_b2_squadron \
  test_alliance_blender_b3_stations test_alliance_blender_b3b_stations \
  test_alliance_blender_cruiser test_alliance_blender_trio \
  test_alliance_blender_battleship test_asset_contract test_model_pipeline \
  test_generic_model_preview test_model_context_lifecycle -v
PYTHONPATH=tests .venv/bin/python -m unittest test_s06_placement_repairs -v
.venv/bin/python tools/art/write_pending_sidecars.py --check
```

## Fresh actual-renderer evidence

Old output directories were moved, not removed, to
`/Users/lukaszjawor/.hermes/cache/scratch/s06-placement-backup/` alongside
original masters/exports and successful first-pass master/export copies.
That scratch backup is local preservation, not a publication artifact.

```sh
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_alliance_batch_review.py \
  --spec art/manifests/pending/S06-BATCH-B1-ALLIANCE-COMBAT.json \
  --out artifacts/s06_alliance_batch_review/b1-alliance-combat \
  --motion rebel:corvette,rebel:supercapital
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_alliance_batch_review.py \
  --spec art/manifests/pending/S06-BATCH-B3B-STATIONS.json \
  --out artifacts/s06_alliance_batch_review/b3b-stations \
  --motion rebel:mining_station
```

`review-b1.txt`, `review-b3b.txt` and `review-summary.json` retain the
results. B1 has 37 files, B3b 117. Contact sheets and full metrics:

- `artifacts/s06_alliance_batch_review/b1-alliance-combat/contact-sheet.png`
- `artifacts/s06_alliance_batch_review/b1-alliance-combat/metrics.json`
- `artifacts/s06_alliance_batch_review/b3b-stations/contact-sheet.png`
- `artifacts/s06_alliance_batch_review/b3b-stations/metrics.json`

Across all eleven reviewed rows: restored changed pixels **0**, repeated
capture changed pixels **0**, all three measured role ablations nonzero,
source/protected preservation **true**, production candidates unselected
**true**. Three paired motion rows each have **150 frames** and identical
before/after simulation hash timelines. Overview changed pixels versus
procedural baseline: B1 **19342**, B3b **23328** (not versus previous art).
Six generated ffmpeg review logs have only CR/progress whitespace
normalization; byte-originals are retained in scratch `raw-ffmpeg/`, with
hashes and normalized-byte verification in `ffmpeg-log-normalization.json`.

## Visual inspection and limitations

The five changed assets' after-close frames were loaded and inspected with
the vision tool, as were rear views for Syndicate mining/energy and carrier.
The sensor mast/head reads as continuous hardware; the mining rig sits on
its lower deck; relay pods visibly hang directly beneath the transverse
truss; Legion ram meets its deck; carrier has no remote island-window strips
or long grey weld booms. Existing long authored derrick/mast members remain
part of those station designs, not new generated weld scaffolding.

The fixed close camera crops the bottom of Syndicate mining's lowered deck;
its rear capture shows the full assembly. Rear views contain pre-existing
context/HUD lines and occlude some underside joints. Carrier glazing is
small and partly occluded at these cameras: these images do not establish
per-window visibility or a new appearance approval. No camera/spec/harness
retuning was slipped into this placement step. Full suite, performance,
Windows/native-platform acceptance, CI, owner appearance approval and
publication were not attempted here.

Two pre-existing documentation/record debts were intentionally untouched:
`fleet_geometry.station_mesh` already has the generic `mesh_for` seam before
its imperial fallback, contradicting historical claims that it is absent;
the B3b test named `test_the_imperial_station_rows_still_have_no_seam`
only verifies that no imperial candidate is currently selected and that its
procedural mesh exists; it is not a dispatch-seam test or proof of absence.
Station pending sidecars still use the generator's `ship:` canonical
prefix. Parent owns any correction/publication, not this repair.
