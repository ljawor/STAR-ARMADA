# Handoff: S06 — five placement repairs before B3c

## 1. State and scope

Status: **engineering repair verified; new appearances pending owner approval**.
Branch `feat/s06-next-model-batch`, draft PR #127. Repair base
`a5f3312ac93d317d6c8e51e8e613b92b5d840831`; PR base
`bd4709f858ae73c39cf11e33b1c6fb01a38dadfb`. Read the exact pushed head and CI
receipt from the latest PR comment, not a self-referential hash in this file.
The owner's live checkout remains untouched and is not the working copy.

This closes kickoff §4.1–4.2 only. It supersedes the outstanding-five-repairs
paragraphs in S06-B3B-STATIONS.md and the scratch kickoff; those records remain
historical. The cruiser deep review and B1/B2/B3a authoring are not to be rerun.
No B3c asset was authored, no approval inferred, no registry, gameplay, renderer,
roadmap, production-default, tag or release change. No merge authorized.

## 2. Owned files and bindings

Two initial-authoring seeds: `tools/art/build_b3b_stations.py` and
`tools/art/build_alliance_carrier.py`; five editable masters and runtime exports
listed below; `tests/test_s06_placement_repairs.py`; ten regenerated pending
sidecars (carrier plus nine B3b records because their shared seed hash moved);
B1/B3b actual-game evidence; `artifacts/s06-placement-repairs/`; this handoff.

| Binding | Identifier | Repair | Triangles | Runtime SHA-256 |
|---|---|---|---:|---|
| `syndicate:sensor_station` | `syndicate_sensor_station` | Mast runs from its keel seat to its head underside | 3832 | `e35b084c73b2702ab12f0611730bb4f99b24eefd80925344300360f68bb7a947` |
| `syndicate:mining_station` | `syndicate_mining_station` | Rig deck and deck hardware derive their height from the keel rail; derrick feet follow the deck | 3728 | `6ce810fdf0be8ba5a3c7485fd9df4d6b3ff5fc5ae5e8a0f9a8fe4bc5b88692aa` |
| `syndicate:energy_relay` | `syndicate_energy_relay` | Pods seat under transverse truss; grids follow pod undersides | 3720 | `fabcb1e166385a6e0ae6c07fb3dd2fb040a309a332511aa8e19d638ff2f27af8` |
| `confederacy:mining_station` | `legion_mining_station` | Spine deck centred in keel frame and extended to ram rear face | 4268 | `32bb2c2b72ac9dacee83ae841d3e5ecf6b0e7c4246ee4e99f0548b28d9695d8f` |
| `rebel:supercapital` | `alliance_carrier` | Six glazing solids straddle the exterior island flank and follow its taper | 8656 | `44e64c9ceed6d01d4e25eab1b4b0afec909bdc10d293af7d0d43a043dad64891` |

Authority remains **blend**; seeds are initial recipes, not permission to overwrite
future hand edits. Blender 5.0.1, schema 1; exporters unchanged. Master, seed and
runtime hashes and byte counts are in the generated pending sidecars;
`artifacts/s06-placement-repairs/reproducibility.json` independently records the
five first-repair master/runtime hashes; `carrier-correction.json` supersedes its
carrier row after independent review rejected buried glazing. `alliance_common.py`, `max_brace=10` and every
exporter are unchanged. No generated long scaffold was added to evade refusal.

## 3. Verification and retained failures

- Five original unchanged seeds refused (exit 1) before saving; master hashes
  unchanged. Complete `refused-*.txt` and `refusal-summary.json` retained.
- First actual Legion refusal is 12.01 units, not the historical member audit's
  17.18; these are different measurements of the old design, not a changed cap.
- Two successful reseeds per asset; three byte-identical exports per asset;
  export leaves each master unchanged. Every exported bound equals repair base
  exactly on all six sides. Master binaries need not repeat byte-identically.
- Station logs state `clusters_left=1`, `SEED_OK`, `breaches=0`. The existing
  carrier seed has no `SEED_OK`/`SELFCHECK` instrumentation; successful save,
  `clusters_left=1` and independent export/bounds checks are the evidence.
- New Blender-free placement test observed failures for all five baseline assets
  before repair, then green, with displacement/empty-geometry controls. It
  measures minimum AABB connectivity while ignoring generated weld members;
  it is not a surface-intersection or exact weld-order proof. Existing exported
  floating-parts checks and real Blender runs complement it.
- Worker shared invocation: 125 tests passed; new module: 3 tests passed.
  Parent independently ran their union: **128 tests passed in 11.017 s**,
  no skips (`parent-128-tests.txt`). That invocation preceded the carrier correction.
  Final independent parent invocation: **132 tests passed in 10.941 s**
  (`parent-final-tests.txt`), including live-recipe/exterior-face, evaluated-triangle
  ray, buried-panel and taper-defect controls. All pending sidecars: **0 stale**.
- Initial independent review **failed**: connected glazing was buried inside the
  island. `independent-review-1.json` retains the finding. The correction uses
  taper-following solids spanning 0.2 units inside to 0.35 outside the flank.
  `carrier-surface-red.txt` records the initial failures; the historical corrected-
  once payload fails 53 ray samples (`carrier-ray-historical-red.txt`). The final
  carrier export repeated byte-identically twice, preserved its master and all
  six baseline bounds; `carrier-correction.json` binds its hashes/counts.
- Parent independently checked on-disk five runtime and master hashes against
  reproducibility records, exact baseline bounds, exact five-mesh delta and no
  render/game/data/approved-record changes. Index symlinks: 0; diff whitespace
  check passes. Final publication scope/head receipts live in the PR comment.

Commands and complete outputs are in `artifacts/s06-placement-repairs/README.md`.
Do not rerun the full suite or cruiser acceptance for each asset. Full local
suite, performance, native Windows graphics, packages and fresh-clone catalogue
rebuild remain unproven at this checkpoint; exact-head CI is reported separately.

## 4. Actual-game review and preservation

Refreshed evidence:
`artifacts/s06_alliance_batch_review/b1-alliance-combat/` (37 files),
`artifacts/s06_alliance_batch_review/b3b-stations/` (117 files).
Each contains `contact-sheet.png`, close/rear/tactical/common-scale captures and
`metrics.json`; B1 has corvette and carrier motion, B3b has rebel mining motion.
Apple M4, 1280×800, 4 MSAA, production shaders and native GL. All eleven rows
restore with 0 changed pixels, all repeats are 0, measured accent/dark/cool
ablations are nonzero, source/protected preservation and production-unselected
checks are true. Three paired clips each cover 150 frames with equal simulation
timelines. Mesh hashes recorded by the capture match the delivered exports.
Overview deltas versus procedural baseline: B1 19342 px, B3b 23328 px; these
are not improvement percentages over previous artwork.

Five changed close frames were inspected; parent additionally inspected carrier
close, Syndicate sensor close and Syndicate mining rear. Mining's fixed close
camera crops its lowered deck; rear shows the complete assembly. Carrier glazing
is visible on the island in the close frame, but the rear camera occludes its
flanks. Surface/ray tests establish attachment; these views do not establish
visibility at every camera angle or constitute appearance approval. Existing
context/HUD lines remain. No capture camera, spec, harness or acceptance bound
was retuned. Appearance approval remains the owner's separate decision.

Original files/reviews are also preserved in local scratch
`~/.hermes/cache/scratch/s06-placement-backup/`; earlier committed versions remain
in Git. The rejected first carrier repair and B1 review are separately retained
in local `s06-carrier-correction-backup/`; the final B1 review was regenerated,
while B3b evidence was not rerun for the carrier-only correction. Its preservation
snapshot consequently names the older carrier as a historical protected file,
not as a station dependency. No user save/replay was removed. Approved trio and B3a masters/meshes,
B2, cruiser and all unrelated meshes are unchanged. Earlier B3a appearance words
still bind the unchanged bytes; this repair does not reopen their review.

## 5. Corrections and next executable step

**The historical imperial-seam blocker is false in the live tree.**
`render/fleet_geometry.py:station_mesh` already consults
`mesh_for(f'{faction}:{data_id}')` before its imperial fallback. The existing test
named `test_the_imperial_station_rows_still_have_no_seam` checks unselected output
and procedural availability, not absence of dispatch. Do not add a duplicate seam
or quote that test as proof of absence. Imperial authoring/scope is still outside
this repair and must be reconciled with inventory and owner decisions explicitly.
Station pending sidecars also carry the generator's historical `ship:` canonical
prefix; that pre-existing record debt is not silently repaired here.

Next authoring slice: **B3c, the remaining 17 faction station rows** — research,
defense, trade, fighter platform and repair dock across three families, plus
confederacy/syndicate shipyards; skip approved `rebel:shipyard`. Read the live
station seam, inventory/scope decisions and S06-B3-STATIONS-PLAN.md envelope
measurements, but author **to** all six legacy extents, not merely inside them.
Use one shared seed and generated export wrappers, cheap per-asset guards,
batch actual-renderer review, generated pending sidecars and an enumerated
revision-bound approval sheet. No need to rerun closed cruiser acceptance.
Keep appearances pending; no automatic merge, registration or activation.

Owner questions remain: pending model appearances, imperial/shared-source scope,
trade-convoy envelope and separate landing authority. The roadmap ledger still
misdirects at cruiser-first and needs its own docs-only change, not an art-PR
rewrite. This repair does not answer those questions or authorize S11.
