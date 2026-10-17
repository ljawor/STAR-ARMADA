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
`tests/test_alliance_blender_b3b_stations.py` (24 guards) and the evidence under
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
| `alliance_mining_station` | `b66b86994896c784543a0981a0d316347d6ccd1d447ad9023c215d77b3c4fcfd` | `7fc5d6791ac823fd521754ccc1c0e4c707e04b83e3db8a46849498cf64a9f08e` |
| `legion_mining_station` | `aaf7e3c5617029a2b448cd5a1a9d2a9234225bbf796e25180345317723032bc3` | `ea91c014382efd3dd7871d750f5ae9e249f9b84e7208f63ce86ec2ca8466bb93` |
| `syndicate_mining_station` | `878a16cfa90fa7bc849cb93149c4ffe5c9d17df19c50a97b4fe68b6913dfe6b1` | `ccfb7dd99ee912ac909a715fca820559a252efb21af26eeb54d8e30d8dfd04a5` |
| `alliance_sensor_station` | `cd6975a883e762b9f053949aa6d15140ac9dcb284550f69c7048e37d977417a5` | `b487fa26703961c04b58b864fc01e6f26846fb317deae80906a8ac76c4ad0ef9` |
| `legion_sensor_station` | `4e473fc6a7483bd0da5743ec7ca3a63e7fef0a17cd6fc4db0bfadd6c8e78c98d` | `8bad34f0a8b9faa608cb29e0e61766b1e391a35e97539d2f009c9abfc1d91098` |
| `syndicate_sensor_station` | `23faffa404d19ae75f4df9267ba4ca21d6ef826a5f1434a25be41ce9539111df` | `3447c375d41b564f3caf0628afcc4f62cd3b7dc0b62eba08efd52f7d11f4093e` |
| `alliance_energy_relay` | `2b46bbdcadf6a8a3b755c3aa17317c40041d1e2f063086412ed3c9db1f2fbc73` | `88bdfe64bc199694dd50b8bc2b29ea51ba27dedb4fb7818179214cbc3572a840` |
| `legion_energy_relay` | `502c992344652f74b3d81f94cad53bcb06904c183d9b4fa96501e6ac29d5b411` | `8949a2070706f989116e3b12507211b4b37591cd342471874271666a0938159f` |
| `syndicate_energy_relay` | `7db6eaf8b503a3060fb5fd9edec471af3e3752c1143688b1936dccc432b2fa3f` | `2f11b7459e09d7a5ba2b82d0c55e0f32b6a1fce35baa0c268b229b7f2341ba88` |

## Cost

| kind | specimen | triangles (legacy procedural) | parts | bytes | verts |
| --- | --- | --- | --- | --- | --- |
| mining | `alliance_mining_station` | 4,800 (2,416) | 89 | 327,469 | 2,569 |
| mining | `legion_mining_station` | 4,156 (2,032) | 83 | 284,152 | — |
| mining | `syndicate_mining_station` | 3,592 (1,696) | 85 | 231,909 | — |
| sensor | `alliance_sensor_station` | 4,060 (3,344) | 75 | 267,317 | — |
| sensor | `legion_sensor_station` | 3,428 (1,200) | 77 | 222,525 | — |
| sensor | `syndicate_sensor_station` | 3,684 (1,248) | 78 | 245,924 | — |
| relay | `alliance_energy_relay` | 4,384 (2,208) | 74 | 304,273 | — |
| relay | `legion_energy_relay` | 3,300 (976) | 80 | 211,418 | — |
| relay | `syndicate_energy_relay` | 3,572 (2,144) | 80 | 230,616 | — |

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
column frame with cell rows, radiator panels and a powered core. No wireframe, no placeholder
geometry and no floating parts in any of the twenty-four after-captures. The measured change
against the legacy procedural station in the same scene, at the same camera, is:

| binding | close | rear | tactical | common-scale |
| --- | --- | --- | --- | --- |
| `rebel:mining_station` | 24.16 % | 19.08 % | 1.33 % | 0.131 % |
| `confederacy:mining_station` | 39.81 % | 34.80 % | 1.75 % | 0.249 % |
| `syndicate:mining_station` | 33.31 % | 24.56 % | 1.86 % | 0.231 % |
| `rebel:sensor_station` | 9.27 % | 6.62 % | 0.85 % | 0.056 % |
| `confederacy:sensor_station` | 13.34 % | 11.69 % | 2.29 % | 0.059 % |
| `syndicate:sensor_station` | 14.65 % | 13.45 % | 3.43 % | 0.073 % |
| `rebel:energy_relay` | 19.13 % | 13.34 % | 1.04 % | 0.096 % |
| `confederacy:energy_relay` | 27.59 % | 22.03 % | 1.66 % | 0.104 % |
| `syndicate:energy_relay` | 22.11 % | 16.97 % | 1.31 % | 0.113 % |

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
   inside its own contact-sheet frame (overview change rose from 13,579 to 23,222 changed pixels).

Neither correction touches the production renderer: `tools/diag_alliance_batch_review.py` is
review tooling, and the batch's `integration` field still records
`UNAPPROVED REVIEW-ONLY harness monkeypatch of mesh_for; no production activation or approval
records`.

## Review metrics (the numbers behind the captures)

`tools/diag_alliance_batch_review.py --spec art/manifests/pending/S06-BATCH-B3B-STATIONS.json
--out artifacts/s06_alliance_batch_review/b3b-stations --motion rebel:mining_station`, one process,
the real application, the candidate injected through `render.asset_selection` only:

* 120 evidence files: 9 rows × (before + after) × 4 views, plus per-row role ablation and
  restored-simulation frames, the batch overview and the contact sheet.
* `status: pending_owner_approval`; `production_shaders: true`; `source_preserved: true`;
  `protected_files_preserved: true`;
  `production_candidates_unselected_after_review: true`.
* `restored_changed_pixels: 0` on all nine rows — the specimen does not perturb the restored
  simulation, so nothing here is a gameplay change.
* Overview (`distance 1100`, `pitch 50`, `yaw 48`, target `[-4200, 0, 2400]`): 23,222 changed
  pixels across the nine-row line.
* `warning`: offline orbit captures — production draw and real simulation ticks, not paced FPS,
  battle acceptance or native Windows graphics acceptance.

## Owner approval

The only thing needed from the owner is the same one-line answer the B1, B2 and B3a sheets asked
for: **do these nine stations look like the right direction, and may the remaining station kinds be
authored the same way?** No merge, release or production-default switch is implied by a yes, and
each revision still lands only after a separate landing decision.

## Tests and commands actually executed

* `PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b3b_stations` →
  **Ran 24 tests, OK.**
* The shared guard set (`…_b3b_stations`, `…_b3_stations`, `…_b2_squadron`, `…_b1_combat`,
  `…_cruiser`, `…_trio`, `…_battleship`, `test_asset_contract`, `test_model_pipeline`,
  `test_generic_model_preview`, `test_model_context_lifecycle`) → **Ran 117 tests**, all passing
  except the 45 that are the new evidence-path guard firing while the review directory was deleted
  for the final re-run; that guard passes with the evidence in place, and it is reported here
  because a guard that cannot fail is not a guard.
* Seeding: Blender 5.0.1, `build_b3b_stations.py --all --replace-seed` → 9 masters, `SEED_OK`,
  and the extent self-check now reports **`breaches=0`** per asset (`SELFCHECK <label> breaches=0
  tolerance=0.001`), because the tolerance was 1e-6 world units while the bevel evaluation leaves a
  1.5e-06 float hair outside a 92.8-unit span — five of those printed as `BREACH` lines and none of
  them was a real overshoot (the smallest *real* under-reach this batch fixed was 0.03 units). The
  check was left alone mathematically and made noise-proof in its reporting; both directions are
  guarded (`test_the_seed_extent_self_check_ignores_float_noise_and_still_catches_a_real_shortfall`),
  so nobody has to trust a log again. **The masters were not re-seeded to prove this** — their bytes
  and hashes are the reviewed ones.
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
