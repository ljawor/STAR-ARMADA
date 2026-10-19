# Handoff: S06 B3b — faction mining stations, sensor stations and energy relays (9 stations)

Slice 1 of the small faction stations: the mining station, the sensor station and the energy relay,
authored for the three families that reach a station through the `mesh_for` seam — Alliance
(`rebel`), Legion (`confederacy`) and Syndicate (`syndicate`) — nine specimens in one batch
(`s06-b3b-stations-slice-1`). Every specimen is **pending owner appearance approval**: it is
authored, exported, guarded and captured, and it is **not** an approval record, a registry entry
or a runtime manifest. Nothing here selects an asset in production, and no production binding,
registry entry, gameplay number or renderer file was touched.

## Owned files and bindings

| binding | specimen | master | mesh | guard |
| --- | --- | --- | --- | --- |
| `rebel:mining_station` | `alliance_mining_station` | `art/blender/alliance_mining_station.blend` | `assets/models/alliance_mining_station.mesh.json` | in this batch |
| `confederacy:mining_station` | `legion_mining_station` | `art/blender/legion_mining_station.blend` | `assets/models/legion_mining_station.mesh.json` | in this batch |
| `syndicate:mining_station` | `syndicate_mining_station` | `art/blender/syndicate_mining_station.blend` | `assets/models/syndicate_mining_station.mesh.json` | in this batch |
| `rebel:sensor_station` | `alliance_sensor_station` | `art/blender/alliance_sensor_station.blend` | `assets/models/alliance_sensor_station.mesh.json` | in this batch |
| `confederacy:sensor_station` | `legion_sensor_station` | `art/blender/legion_sensor_station.blend` | `assets/models/legion_sensor_station.mesh.json` | in this batch |
| `syndicate:sensor_station` | `syndicate_sensor_station` | `art/blender/syndicate_sensor_station.blend` | `assets/models/syndicate_sensor_station.mesh.json` | in this batch |
| `rebel:energy_relay` | `alliance_energy_relay` | `art/blender/alliance_energy_relay.blend` | `assets/models/alliance_energy_relay.mesh.json` | in this batch |
| `confederacy:energy_relay` | `legion_energy_relay` | `art/blender/legion_energy_relay.blend` | `assets/models/legion_energy_relay.mesh.json` | in this batch |
| `syndicate:energy_relay` | `syndicate_energy_relay` | `art/blender/syndicate_energy_relay.blend` | `assets/models/syndicate_energy_relay.mesh.json` | in this batch |

Supporting files: `tools/art/build_b3b_stations.py` (one seed, nine designs),
`tools/art/export_<identifier>.py` ×9 (generated from `tools/art/templates/export_wrapper.tmpl` by
`tools/art/gen_export_wrappers.py`), `art/manifests/pending/S06-BATCH-B3B-STATIONS.json` (the batch
sheet), the nine per-asset sidecars `art/manifests/pending/S06-<FACTION>-<KIND>.json`,
`tests/test_alliance_blender_b3b_stations.py` (27 guards) and the evidence under
`artifacts/s06_alliance_batch_review/b3b-stations/`.

## What each station is

Each kind is a shared kit of station primitives — the families share a vocabulary, not a body with
different paint — and each of the three designs per kind is deliberately different:

* `rebel:mining_station` — elliptical processing ring with a hopper drum and four drill booms.
* `confederacy:mining_station` — twin-arm extractor on a long keel with an ore silo.
* `syndicate:mining_station` — open truss drilling rig with lashed ore drums and a hab cab.
* `rebel:sensor_station` — lattice disc carrying a mast and three dishes.
* `confederacy:sensor_station` — blade spine with a stacked array and a forward dish.
* `syndicate:sensor_station` — crooked scaffold of bolted dishes.
* `rebel:energy_relay` — twin collector rings on a spine with radiator panels.
* `confederacy:energy_relay` — stepped cell column with coolant fins.
* `syndicate:energy_relay` — chain of power cells on a truss with cable runs.

Every part name matches the geometry's own noun. Four flat plates that had inherited the
encirclement word `band` are now `… belt`, and `09 Drill collar …` — a solid block wearing the same
word a ring would use — is now `09 Drill clamp …`. A ring-name guard that cannot tell a hollow ring
from a flat belt is worthless, so the naming and the guard were fixed together, not the guard alone.

## Authored to the legacy extent — to the extent, not merely inside it

A station is not a ship. `render.camera_geometry.station_bounds` derives the drawn footprint and
`station_scale = assets/data/stations/stations.json radius / 50.` the class scale (mining 1.4,
sensor 0.9, energy relay 1.1), and the legacy procedural station fills its declared box exactly —
so the review harness compares the authored footprint against the legacy station mesh **within 1 %
per axis**, and staying inside the extent would read as a wrong-sized station. Each specimen is
therefore authored *to* its binding's extent: the keel, rails, masts, booms and outriggers that
reach an extreme are sized against the binding's own frame and centred on
`(lo + hi) / 2` for their axis, because nothing centred on the origin reaches an asymmetric extent
(Syndicate mining spans X `-33.93 … 42.40`).

| binding | authored footprint | legacy footprint | worst axis |
| --- | --- | --- | --- |
| `rebel:mining_station` | 89.5000 × 25.5200 × 48.8294 | 89.6000 × 25.7200 × 48.8294 | 0.7776 % |
| `confederacy:mining_station` | 80.8372 × 42.5200 × 76.3200 | 81.3371 × 42.5200 × 76.3200 | 0.6146 % |
| `syndicate:mining_station` | 76.3322 × 72.0000 × 66.5279 | 76.3322 × 72.0000 × 66.5280 | 0.0001 % |
| `rebel:sensor_station` | 92.8000 × 43.2800 × 41.0400 | 92.8000 × 43.2800 × 41.0400 | 0.0000 % |
| `confederacy:sensor_station` | 72.2826 × 52.2526 × 63.0851 | 72.3825 × 52.4000 × 63.0851 | 0.2812 % |
| `syndicate:sensor_station` | 73.5565 × 61.1570 × 52.2793 | 73.5565 × 61.4570 × 52.2793 | 0.4882 % |
| `rebel:energy_relay` | 100.6000 × 21.6156 × 50.3446 | 100.8000 × 21.6157 × 50.3446 | 0.1984 % |
| `confederacy:energy_relay` | 82.5744 × 47.6000 × 71.9713 | 82.8743 × 47.6000 × 72.1713 | 0.3619 % |
| `syndicate:energy_relay` | 94.0878 × 34.5600 × 80.9413 | 94.0878 × 34.5600 × 80.9414 | 0.0001 % |

Worst axis across the batch is **0.7776 %**, inside the 1 % rule; five rows are exact or within
0.0001 %. Each wrapper also carries the binding's own footprint depth as `MIN_LENGTH` (48.6, 76.1,
66.3, 40.8, 62.9, 52.1, 50.1, 71.9, 80.7) and every authored length clears it — the tightest is
`confederacy:sensor_station` at 65.05 against 62.90.

## Not in this batch, deliberately

* **The ten imperial station rows** (`imperial:` command, mining, sensor, relay, shipyard …).
  `render/fleet_geometry.station_mesh(data_id, faction)` dispatches them straight to
  `_station_mesh(did)` with **no `mesh_for` seam**, so authoring them is a renderer change and an
  owner decision, not an asset batch. Deferred with the owner's agreement.
* **`rebel:shipyard`** — already delivered as the approved trio's `core` asset
  `alliance_shipyard`.
* **The three command stations** — the B3a batch, already authored, reviewed and
  appearance-approved by the owner. Their landing gate is separate and still open.

## Source authority / versions

Blender **5.0.1** (`/Applications/Blender.app/Contents/MacOS/Blender`), headless
`--background --factory-startup --python-exit-code 1`, run with `SDL_VIDEODRIVER` unset. Meshes
record `authoring: "Blender evaluated bevel mesh"` and `authority: blend` — the editable master is
the source, and `assets/models/*.mesh.json` is its export, never the other way round. No
proprietary geometry or textures; every part is generated by `tools/art/alliance_common.py`'s
primitives inside the seed script.

## Hashes of this revision

| specimen | master `.blend` sha256 | `mesh.json` sha256 |
| --- | --- | --- |
| `alliance_mining_station` | `ab9a5c7e263fc7754e2b4abb8397cc40e87ea4794996246cca73e8c16f1bacef` | `ff14df049feaad5937326566ac8015a9d86dcf03671d7e3426f8952b7e53e9da` |
| `legion_mining_station` | `ebacae39583930f5b7d824a2f44734e7499db826ce52cd8baee50186495474b0` | `c04d23d84ab8916e5fb4e6a6efffe454f148349844779557e241bee400236bfb` |
| `syndicate_mining_station` | `54aa027886e7069e1edabcdac16372b4bb3f087cba6c164ef9f9766aa38ba8a0` | `ee86f98eeae7e69c2c5d345a9aa2736dd62e9911b4673a28c3f5b459ce382872` |
| `alliance_sensor_station` | `6cd5fe3878340770a455da9945023d62b4ebdf5ecb0e1d814a84c4582cedba03` | `02e7447e185ea4b01ddddd8e605247e2c99704736c9e0b4784b95545c2bff24e` |
| `legion_sensor_station` | `a5d7d33d83326573165a7505aa8e6f1b29ba09864521657dcea0396e990002d1` | `27d3b5803c10a386b8ed74f8574acb0f8d0a6eb5f7509ad4bd2726ac33163755` |
| `syndicate_sensor_station` | `dea77b42af5ec0450102fea28cc780b59ee154888ce96b249a097b7a6551e4aa` | `5240ed82fdd7f7385deb9143365aed20717d61f9d2550fa98b4fb7985bdbcbbb` |
| `alliance_energy_relay` | `64482d7da075ba883c730f873a6a239120f953fab7241e0563fdb0d1209a9518` | `fea920827bc7c690d022ce614455dfad7da0ca6e053af0e5fde793c0fa6173f8` |
| `legion_energy_relay` | `58bd7ca362e7336ca81387e65b193a2d6469dcf8bae851170743779d419548cc` | `8c260a988a6e0f66bb7a659832f8c289dcd797a82c4eab1f25725131086de7e0` |
| `syndicate_energy_relay` | `efb7ae3adb8a6916f1faba86af9319c33482dfddc19a991f9831d68d9ecc0722` | `44e2cdee342e0419242a29f6f49f091a89f56889eeaf810d312691d30f1d2ebf` |

## Cost

| kind | specimen | triangles (legacy procedural) | parts | bytes | verts |
| --- | --- | --- | --- | --- | --- |
| mining | `alliance_mining_station` | 4,948 (2,416) | 96 | 335,435 | 2,657 |
| mining | `legion_mining_station` | 4,280 (2,032) | 88 | 290,934 | 2,312 |
| mining | `syndicate_mining_station` | 3,740 (1,696) | 92 | 239,907 | 2,048 |
| sensor | `alliance_sensor_station` | 4,196 (3,344) | 81 | 274,873 | 2,158 |
| sensor | `legion_sensor_station` | 3,564 (1,200) | 83 | 230,217 | 1,944 |
| sensor | `syndicate_sensor_station` | 3,868 (1,248) | 88 | 255,665 | 2,098 |
| relay | `alliance_energy_relay` | 4,496 (2,208) | 78 | 310,433 | 2,396 |
| relay | `legion_energy_relay` | 3,484 (976) | 90 | 220,886 | 1,912 |
| relay | `syndicate_energy_relay` | 3,744 (2,144) | 89 | 239,922 | 2,040 |

Wrapper advisories are `MAX_TRIANGLES 11500`, `MAX_VERTICES 8000`, `MAX_BYTES 2_000_000`; the
loader's hard caps are 12,000 / 10,000 / 2,000,000 in `render/authored_mesh.py`. The heaviest
specimen uses 40 % of the advisory triangle budget. Every mesh fills all six material roles
(`base, dark, trim, accent, lit, cool`), which the loader requires — an empty role is rejected —
and the review's role ablation frames (`-ablated-accent/-cool/-dark.png`, one set per row) evidence
that the accent, cool and dark roles are visible in the real renderer.

## What changed visibly

At the close view each specimen is a solid, shaded structure with a distinct silhouette: the
mining stations read as a processing deck with a cell ring, a mast and extractor booms carrying
pods; the sensor stations as a disc or spine carrying a mast and dishes; the relays as a ring or
column frame with cell rows, radiator panels and a powered core. No wireframe and no placeholder
geometry in any of the twenty-four after-captures. Every part is welded to the rest. This revision
was first cut with one hundred parts standing clear of everything else - the legion sensor station's
forward dish floated 25 units above its body, 120 px of daylight in its own capture, and a shared
marker-light ring sat 1.4 units above the deck of all nine designs. The seed now runs `weld_scene()`,
the lights sit on the vent row they belong to, a guard measures the exported meshes for it, and
the envelope did not move: the bounds of all nine are bit-identical to the revision reviewed before
this one. Triangles are up 24 to 156 per station, all of it weld members and the extra light blocks. The measured change
against the legacy procedural station in the same scene, at the same camera, is:

| binding | close | rear | tactical | common-scale |
| --- | --- | --- | --- | --- |
| `rebel:mining_station` | 24.51 % | 19.10 % | 1.36 % | 0.135 % |
| `confederacy:mining_station` | 40.47 % | 34.83 % | 1.79 % | 0.254 % |
| `syndicate:mining_station` | 33.32 % | 24.90 % | 1.86 % | 0.231 % |
| `rebel:sensor_station` | 9.29 % | 6.65 % | 0.85 % | 0.056 % |
| `confederacy:sensor_station` | 12.29 % | 9.91 % | 1.89 % | 0.051 % |
| `syndicate:sensor_station` | 14.67 % | 13.66 % | 3.43 % | 0.073 % |
| `rebel:energy_relay` | 19.13 % | 13.34 % | 1.04 % | 0.096 % |
| `confederacy:energy_relay` | 27.82 % | 22.03 % | 1.69 % | 0.107 % |
| `syndicate:energy_relay` | 22.95 % | 17.36 % | 1.35 % | 0.118 % |

The close and rear views are the rows' own framing, so they are the honest appearance evidence;
`tactical` is a 5.6× shot and `common-scale` is one shared camera for the whole batch. The sensor
stations change least at close range because a lattice disc presents far less surface than a
mining deck from the same distance — the frame is the evidence, not the percentage.

## Review-harness corrections made in this batch

Two additive corrections, both of them **spec fields**, so every earlier batch keeps its frames
bit-for-bit and no committed capture moves:

1. **`overview.close_distance_floor` (new, optional, defaults to off).** These stations frame at
   65–146 units where the B3a command stations framed at 250. The shared scene carries a context
   group of ships up to 231 units long, so for the closest row (`confederacy:sensor_station`) the
   near eye landed inside a context hull and `capture_slice.camera_check` refused the capture:
   `camera not outside union`. The floor lifts the batch's two *near* views to a clearance the B3a
   frames already had. It is a spec value, not a retuned multiplier, precisely because a multiplier
   would reinterpret every earlier batch's committed frames. The guard asserts the field exists,
   that the harness reads it from the spec and defaults to off, and that the floor sits between the
   batch's own narrowest and widest framing — it must lift the closest row and must not shrink
   every specimen.
2. **Overview spacing 300, not 600.** Nine rows at 600 span 4,800 units while the 1,100-distance
   overview frame covers 1,833, so the outer rows fell outside the frame. At 300 the whole batch is
   inside its own contact-sheet frame (overview change rose from 13,579 to 20,838 changed pixels on this revision's frames).

Neither correction touches the production renderer: `tools/diag_alliance_batch_review.py` is
review tooling, and the batch's `integration` field still records
`UNAPPROVED REVIEW-ONLY harness monkeypatch of mesh_for; no production activation or approval
records`.

## Review metrics (the numbers behind the captures)

`tools/diag_alliance_batch_review.py --spec art/manifests/pending/S06-BATCH-B3B-STATIONS.json
--out artifacts/s06_alliance_batch_review/b3b-stations --motion rebel:mining_station`, one process,
the real application, the candidate injected through `render.asset_selection` only:

* 117 evidence files: 9 rows × (before + after) × 4 views, plus per-row role ablation and
  restored-simulation frames, the batch overview and the contact sheet.
* `status: pending_owner_approval`; `production_shaders: true`; `source_preserved: true`;
  `protected_files_preserved: true`;
  `production_candidates_unselected_after_review: true`.
* `restored_changed_pixels: 0` on all nine rows — the specimen does not perturb the restored
  simulation, so nothing here is a gameplay change.
* Overview (`distance 1100`, `pitch 50`, `yaw 48`, target `[-4200, 0, 2400]`): 20,838 changed
  pixels across the nine-row line.
* `warning`: offline orbit captures — production draw and real simulation ticks, not paced FPS,
  battle acceptance or native Windows graphics acceptance.

## What the weld pass changed after the first reviewed cut

This revision of the nine masters is not the one first put up for review, and the difference is a
defect the review frames had already shipped: parts authored *by centre and by reach* never
guarantee contact, and 100 of these stations' parts stood clear of everything else. The worst were
visible — the legion sensor station's forward dish floated **25 units** above its body, about
120 px of daylight in its own close frame, and a shared marker-light ring sat 1.4 units above the
deck of all nine designs. `tools/art/probe_floating_parts.py` names such parts; the fix is
`weld_scene()` in `tools/art/alliance_common.py`, called by the seed before it reports its extent,
and the marker lights were moved onto the vent row they belong to.

The envelope did not move — the bounds of all nine are unchanged from the reviewed revision, so the
station scale and footprint comparison above are the same numbers — and every part now touches:
the worst part-to-nearest gap is 0.10 units where the reviewed meshes had 1.43–23.75. Triangles are
up 24–156 per station, all of it weld members and the extra light blocks.

**Welding is not the same as scaffolding, and the first cut of this pass confused the two.** It
braced `legion_sensor_station`'s forward dish — authored at the station's origin while its mast head
sits 31 units forward — with three long booms spanning the distance, and in the capture those booms
read as an extra grey panel welded across the hull. A brace that long is not a weld. So:

* `weld_scene(max_brace=10.0)` now **refuses** a joint whose two clusters have more than 10 units of
  clear space between them, naming the pair: that is a design fault, and the part gets placed where
  it belongs instead. A refusal leaves the master untouched, because the pass runs before the save.
* A member now spans the **gap** — from one box's facing face to the other's — and never from centre
  to centre. Two long parts that almost touch used to get a member as long as the parts themselves,
  which is exactly how the booms appeared.
* `legion_sensor_station` was re-placed rather than braced: the dish now sits on its hub at the mast
  head, the hub on the mast, and the whole chain welds with four sub-unit fits (`06 Forward dish`
  grew 40 vertices onto its hub, 0.35 units of clear space) and two short brackets of 2.6 and
  4.21 units between neighbouring parts. Its bounds are the legacy extent to the digit, its
  triangle count went 3,576 → 3,564 and it carries two weld members instead of three booms.

**Outstanding, measured rather than asserted.** Measuring the committed meshes for the clear space
each existing weld member bridged — the member's box contains its two endpoints, so their mutual gap
is what the new rule judges — five designs still carry a joint over the 10-unit line, and their
*seeds* will therefore refuse until the part is placed where it belongs:

| specimen | clear space a member bridged |
| --- | --- |
| `syndicate_sensor_station` | 33.86 |
| `syndicate_mining_station` | 24.50 |
| `syndicate_energy_relay` | 20.01 |
| `legion_mining_station` | 17.18 |
| `alliance_carrier` | 12.90 |

Their committed meshes are welded — the frames in this handoff are the ones reviewed — but each
needs the same placement pass `legion_sensor_station` just had before its next rebuild. The seven
other specimens are inside the line; `legion_sensor_station` is now the cleanest of the nine at
0.00.

## Owner approval

The only thing needed from the owner is the same one-line answer the B1, B2 and B3a sheets asked
for: **do these nine stations look like the right direction, and may the remaining station kinds be
authored the same way?** No merge, release or production-default switch is implied by a yes, and
each revision still lands only after a separate landing decision.

## Tests and commands actually executed

* `PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b3b_stations` →
  **Ran 27 tests, OK.** The three that were added for the weld are
  `test_no_part_of_any_station_floats_clear_of_the_rest` (the exported meshes are re-measured
  for detached parts by union-find over shared vertex indices, with no Blender in the loop),
  `test_the_seed_welds_the_scene_before_it_reports_the_extent` (the seed must call the weld
  before its own bounds reporting, or the numbers measure a different scene) and
  `test_every_evidence_path_the_sheet_points_at_exists`.
* The shared guard set (`…_b3b_stations`, `…_b3_stations`, `…_b2_squadron`, `…_b1_combat`,
  `…_cruiser`, `…_trio`, `…_battleship`, `test_asset_contract`, `test_model_pipeline`,
  `test_generic_model_preview`, `test_model_context_lifecycle`) → **Ran 125 tests, OK**
  (`Ran 125 tests in 7.295s`). That set includes the evidence-path guard, which resolves every path
  each sheet points at against the filesystem: run it while a review directory is deleted and it goes
  red, which is the guard working rather than a regression — and it is what caught the B1 sheet
  pointing at a corvette clip no run had produced.
* Seeding: Blender 5.0.1, `build_b3b_stations.py --all --replace-seed` → 9 masters, `SEED_OK`,
  and the extent self-check now reports **`breaches=0`** per asset (`SELFCHECK <label> breaches=0
  tolerance=0.001`), because the tolerance was 1e-6 world units while the bevel evaluation leaves a
  1.5e-06 float hair outside a 92.8-unit span — five of those printed as `BREACH` lines and none of
  them was a real overshoot (the smallest *real* under-reach this batch fixed was 0.03 units). The
  check was left alone mathematically and made noise-proof in its reporting; both directions are
  guarded (`test_the_seed_extent_self_check_ignores_float_noise_and_still_catches_a_real_shortfall`),
  so nobody has to trust a log again. **The masters were not re-seeded to prove this**; they were
  re-seeded later for the weld pass below, and every hash in this handoff is of that
  post-weld revision — the one the frames in this handoff were rendered from.
* Exporting: nine wrappers exit 0, each printing `GAME_EXPORT` with bounds on the legacy extent and
  its own triangle count. Every one of them is at or above the pipeline's 1,800-triangle floor;
  eight of the nine initially failed it (1,532 / 884 / 1,436 / 804 / 1,032 / 1,760 / 676 / 948) and
  the fix was a real detail layer (`ring_blocks` + `bays`), not a relaxed floor.
* Sidecars: `tools/art/write_pending_sidecars.py --batch s06-b3b-stations-slice-1` then `--check`
  → nine sidecars, `0 stale sidecar(s)`.
* Batch review: command above → 120 files, metrics in that directory's `metrics.json`.

## Actual-game captures and recipe

The review harness renders the **real application** with the candidate injected through
`render.asset_selection` only — one process per batch, `SDL_VIDEODRIVER` unset so the real
backends are used, each row owned by a player of its own faction (a station's faction comes from
its **owner**, `render.renderer.owner_faction(state, e.owner)`, not from its data row), every row
placed as a station rather than spawned as a ship, and every row labelled uniquely so no capture
can overwrite another. Frames live in `artifacts/s06_alliance_batch_review/b3b-stations/`:
`contact-sheet.png`, `overview.png`, `<label>-after-close.png` per row, and one
`alliance mining station-after-motion.mp4` clip.

## Performance / packaging / platform

No production geometry, material or shader file changed, so there is nothing to re-measure in the
shipped renderer yet: the frames above are the *candidate* path only. The triangle, vertex and byte
costs sit inside both the wrapper advisories and the loader's hard caps. Packaging is untouched —
no release, tag, DMG or ZIP, and the Windows package job stays skipped by design.

## Open issues, blockers and decisions required

1. **Appearance approval of these nine specimens** (the ask above).
2. **The imperial station seam** — ten rows with no `mesh_for` seam, so they need a renderer
   decision before they can be authored as an asset batch.
3. **Landing**: the 14 B1/B2/B3a specimens plus these nine stay `procedural_legacy` with
   `activation: false` until each revision is explicitly approved and landed behind its own gate.
4. **`trade_convoy`'s envelope** is still an owner/renderer decision and is not authored here.

## Status of this batch vs. the S06 scope

With B1 (corvette + carrier), B2 (8 squadron/logistics hulls), B3a (3 command stations) and this
batch (9 small stations), the authorable faction catalogue with a `mesh_for` seam is complete for
the kinds covered here: mining station, sensor station, energy relay and command station across
alliance, legion and syndicate. What remains is the imperial seam, the `rebel:shipyard`
(non-)question, and the owner's landing decisions — not more authoring of these kinds.
