# Handoff: S06 B3c — the remaining seventeen faction station rows

Status: **review-ready** — authored, exported, guarded and captured; **nothing approved and
nothing activated**. This is the last authorable faction station batch: research station, defense
platform, trade station, fighter platform and repair dock across Alliance (`rebel`), Legion
(`confederacy`) and Syndicate (`syndicate`), plus the Legion and Syndicate shipyards —
seventeen specimens in one batch (`s06-b3c-stations`).

Base commit / branch: `89b9c7b4b5f5976c6f4920cbda1bbe062b9ecb0a` on `feat/s06-next-model-batch`
(the head the placement-repair checkpoint was published at). PR **#127**. The exact pushed head,
its CI run and the attempt history are in the PR comment for this batch, not in this file: a
committed file cannot contain the hash of the commit that contains it.

## Owned files and bindings

| binding | specimen | master | mesh |
| --- | --- | --- | --- |
| `rebel:research_station` | `alliance_research_station` | `art/blender/alliance_research_station.blend` | `assets/models/alliance_research_station.mesh.json` |
| `confederacy:research_station` | `legion_research_station` | `art/blender/legion_research_station.blend` | `assets/models/legion_research_station.mesh.json` |
| `syndicate:research_station` | `syndicate_research_station` | `art/blender/syndicate_research_station.blend` | `assets/models/syndicate_research_station.mesh.json` |
| `rebel:defense_platform` | `alliance_defense_platform` | `art/blender/alliance_defense_platform.blend` | `assets/models/alliance_defense_platform.mesh.json` |
| `confederacy:defense_platform` | `legion_defense_platform` | `art/blender/legion_defense_platform.blend` | `assets/models/legion_defense_platform.mesh.json` |
| `syndicate:defense_platform` | `syndicate_defense_platform` | `art/blender/syndicate_defense_platform.blend` | `assets/models/syndicate_defense_platform.mesh.json` |
| `rebel:trade_station` | `alliance_trade_station` | `art/blender/alliance_trade_station.blend` | `assets/models/alliance_trade_station.mesh.json` |
| `confederacy:trade_station` | `legion_trade_station` | `art/blender/legion_trade_station.blend` | `assets/models/legion_trade_station.mesh.json` |
| `syndicate:trade_station` | `syndicate_trade_station` | `art/blender/syndicate_trade_station.blend` | `assets/models/syndicate_trade_station.mesh.json` |
| `rebel:fighter_platform` | `alliance_fighter_platform` | `art/blender/alliance_fighter_platform.blend` | `assets/models/alliance_fighter_platform.mesh.json` |
| `confederacy:fighter_platform` | `legion_fighter_platform` | `art/blender/legion_fighter_platform.blend` | `assets/models/legion_fighter_platform.mesh.json` |
| `syndicate:fighter_platform` | `syndicate_fighter_platform` | `art/blender/syndicate_fighter_platform.blend` | `assets/models/syndicate_fighter_platform.mesh.json` |
| `rebel:repair_dock` | `alliance_repair_dock` | `art/blender/alliance_repair_dock.blend` | `assets/models/alliance_repair_dock.mesh.json` |
| `confederacy:repair_dock` | `legion_repair_dock` | `art/blender/legion_repair_dock.blend` | `assets/models/legion_repair_dock.mesh.json` |
| `syndicate:repair_dock` | `syndicate_repair_dock` | `art/blender/syndicate_repair_dock.blend` | `assets/models/syndicate_repair_dock.mesh.json` |
| `confederacy:shipyard` | `legion_shipyard` | `art/blender/legion_shipyard.blend` | `assets/models/legion_shipyard.mesh.json` |
| `syndicate:shipyard` | `syndicate_shipyard` | `art/blender/syndicate_shipyard.blend` | `assets/models/syndicate_shipyard.mesh.json` |

Supporting files: `tools/art/build_b3c_stations.py` (one seed, seventeen designs),
`tools/art/export_<identifier>.py` ×17 (generated from `tools/art/templates/export_wrapper.tmpl` by
`tools/art/gen_export_wrappers.py`), `art/manifests/pending/S06-BATCH-B3C-STATIONS.json` (the batch
sheet), the seventeen per-asset sidecars `art/manifests/pending/S06-<FACTION>-<KIND>.json`,
`tests/test_alliance_blender_b3c_stations.py` (31 guards), the batch's
`overview.{yaw,pitch,distance}` framing in that sheet (see below) and the evidence under
`artifacts/s06_alliance_batch_review/b3c-stations/`.

## What each station is

Each kind is a shared kit of station primitives — rings, members, block rows and a shared `9x`
detail layer — and each family's design differs from its siblings in vocabulary, role mix,
triangle count and where its parts sit inside the footprint they share:

* `rebel:research_station` — elliptical habitat band around a lab core, dish mast on the deck tower.
* `confederacy:research_station` — stepped array bastions under a forward dish tower.
* `syndicate:research_station` — open truss rig carrying bolted dishes and a hab cab.
* `rebel:defense_platform` — armoured disc with four battery hardpoints on its rim.
* `confederacy:defense_platform` — stepped bastion with two battery decks and a fire tower.
* `syndicate:defense_platform` — truss platform with bolted projector pods on outriggers.
* `rebel:trade_station` — cargo band around a hub with cranes and stacked containers.
* `confederacy:trade_station` — long keel with silos, gantry cranes and container racks.
* `syndicate:trade_station` — open quay deck: cargo forward, drums and crane aft, hab cab.
* `rebel:fighter_platform` — flat deck with an open launch bay and stacked bay blocks.
* `confederacy:fighter_platform` — two-tier armoured bay block with launch rails.
* `syndicate:fighter_platform` — open frame with forward launch cradles and an aft control tower.
* `rebel:repair_dock` — open cradle band with gantry arms and service decks.
* `confederacy:repair_dock` — twin towers bridged over a dry-dock well.
* `syndicate:repair_dock` — scaffold frames with cross members and spare drums.
* `confederacy:shipyard` — slipway rails under gantry frames, build hall forward.
* `syndicate:shipyard` — open slipway trusses with cranes and the build hall aft.

## Authored to the legacy extent — to the extent, not merely inside it

A station is not a ship: `render.camera_geometry.station_bounds` is what its camera, contact and
ray helpers read, and the legacy procedural station fills its declared box exactly, so the review
harness compares the authored footprint against the legacy station mesh within 1 % per axis. Each
design lands all six of its extremes — per axis *and* per side — with four *reach* parts sized
against the binding's own frame: a rail spanning the full depth, a transverse beam spanning the
full width, a part whose underside is the Y minimum and a cap whose top is the Y maximum. `plate`
carries no bevel, so a declared box is the evaluated box and the exporter's edge quantiser snaps
it onto the limit.

| binding | authored footprint | legacy footprint | worst axis |
| --- | --- | --- | --- |
| `rebel:research_station` | 80.0000 × 48.8800 × 61.5010 | 80.0000 × 48.8800 × 61.5010 | 0.0001 % |
| `confederacy:research_station` | 92.6312 × 26.2800 × 86.1600 | 92.6313 × 26.2800 × 86.1600 | 0.0001 % |
| `syndicate:research_station` | 76.4000 × 44.8800 × 60.3720 | 76.4000 × 44.8800 × 60.3720 | 0.0000 % |
| `rebel:defense_platform` | 91.8400 × 15.9660 × 88.6400 | 91.8400 × 15.9660 × 88.6400 | 0.0000 % |
| `confederacy:defense_platform` | 100.4086 × 24.9440 × 86.9564 | 100.4086 × 24.9440 × 86.9564 | 0.0000 % |
| `syndicate:defense_platform` | 76.3370 × 32.9000 × 56.5923 | 76.3370 × 32.9000 × 56.5923 | 0.0001 % |
| `rebel:trade_station` | 88.0000 × 12.0680 × 78.0960 | 88.0000 × 12.0680 × 78.0960 | 0.0000 % |
| `confederacy:trade_station` | 87.5336 × 24.8320 × 92.1064 | 87.5335 × 24.8320 × 92.1064 | 0.0001 % |
| `syndicate:trade_station` | 97.5693 × 33.3000 × 95.2089 | 97.5693 × 33.3000 × 95.2089 | 0.0000 % |
| `rebel:fighter_platform` | 96.0000 × 16.1200 × 78.4000 | 96.0000 × 16.1200 × 78.4000 | 0.0000 % |
| `confederacy:fighter_platform` | 84.8042 × 20.6800 × 72.4000 | 84.8041 × 20.6800 × 72.4000 | 0.0001 % |
| `syndicate:fighter_platform` | 71.7135 × 46.0000 × 78.4000 | 71.7135 × 46.0000 × 78.4000 | 0.0000 % |
| `rebel:repair_dock` | 76.8000 × 36.4000 × 73.2000 | 76.8000 × 36.4000 × 73.2000 | 0.0000 % |
| `confederacy:repair_dock` | 80.2944 × 41.2000 × 72.8000 | 80.2943 × 41.2000 × 72.8000 | 0.0001 % |
| `syndicate:repair_dock` | 77.1846 × 51.6000 × 76.8805 | 77.1846 × 51.6000 × 76.8805 | 0.0000 % |
| `confederacy:shipyard` | 124.0800 × 47.2000 × 107.4564 | 124.0800 × 47.2000 × 107.4564 | 0.0000 % |
| `syndicate:shipyard` | 99.1074 × 64.5928 × 102.0662 | 99.1074 × 64.5928 × 102.0662 | 0.0000 % |

Worst axis across the batch is **0.0001 %** — every extreme of all 102 row-extremes
lands within a ten-thousandth of its legacy limit, and the export's own bounds are the legacy
envelope to the digit on every axis.

## Not in this batch, deliberately

* **The ten imperial station rows** — `render.fleet_geometry.station_mesh(data_id, faction)`
  dispatches them straight to `_station_mesh(did)`. (The generic entry does consult
  `mesh_for(f'{faction}:{data_id}')` *before* that fallback, so an imperial row is a seam
  question like any other; what it does not have is an owner-authorized scope decision. Authoring
  them is a scope decision, not an asset slip-in.)
* **`rebel:shipyard`** — already delivered as the approved trio's `core` asset
  `alliance_shipyard`.
* **The B3a command stations and the nine B3b small stations** — earlier batches; B3a is
  appearance-approved, B3b is pending.

## Source authority / versions

Blender **5.0.1** (`/Applications/Blender.app/Contents/MacOS/Blender`), headless
`--background --factory-startup --python-exit-code 1`, run with `SDL_VIDEODRIVER` unset. Meshes
record `authoring: "Blender evaluated bevel mesh"` and `authority: blend` — the editable master is
the source and the export is derived from it, never the other way round. No proprietary geometry
or textures: every part is generated by `tools/art/alliance_common.py`'s primitives inside the
seed script, which refuses to overwrite an existing master unless `--replace-seed` is explicit.

## Hashes of this revision

| specimen | master `.blend` sha256 | `mesh.json` sha256 |
| --- | --- | --- |
| `alliance_research_station` | `2f2522c077460483fd6e201424f042ef36142c41850401b848a88de0a51f6a12` | `1886a86b89cb1b0ef4a618a398216cccf44a0cd9dc84f950a0dce94b9892f870` |
| `legion_research_station` | `6766c3d7cdc1915b9952a432a6f429ac60c354611822c04d77041fcc1288382b` | `01485bb472f239ab70779b1f1a5dabb381c18347b8b9d2350a3cb2e045b7fd72` |
| `syndicate_research_station` | `44ddb5b052fb1ad51a4c00f56a00cd59386e83241f8f404677ac505254f2b57d` | `c2532f898553a4ff437be8f365d037551e4c1d1a5d5389f35e500c473c1b224c` |
| `alliance_defense_platform` | `8d4b53895400ffa40f355a3341f21b441032f0234792a858a51f610e7f2efb74` | `80b1f3daae8e73fdf050bde9ac6cff87364c987683d6570c475e57fc6e993fa1` |
| `legion_defense_platform` | `b3ae6919b48ddfd79c6f66ae90b4fbbcc9989278ba587e55253403a7bc99ba8f` | `637ca1293919ca6bf7667f5e1f60ad052b16d1adf08085196f8ec3adb4f4d983` |
| `syndicate_defense_platform` | `9170ecf71c77b6eeaa6134c501fd2d842c6594f33f702bc80989c025aab85672` | `d74eb09809cc081177b3edb7cd542dc393812d00f151d70a0d5235aa49e1245b` |
| `alliance_trade_station` | `721cdde1a2937f7a5ae8f9a12a1357ed8ec2cc1d2d3a449b01b51b0fec37a7cc` | `07fc9d41e83f80b517d0faf8b3a7839a8f0348d5629442a42d02b447301d8422` |
| `legion_trade_station` | `1f218aff89e3fa9856627f66728ffab4388739047bf450c724a249830f976644` | `567416bb0c267c8896eccdaf3210e9e347fc60ab0e92f80b9227a66e7ee82d49` |
| `syndicate_trade_station` | `7b84c5e0f47928eee805a8acfc0e018c5cd31ee3255803c7c7134c3e5b145252` | `6bae5343f97a9d1881d8b1b7bbf21270a1acddc26a6b58752e258dcb90bd9e1c` |
| `alliance_fighter_platform` | `d73a689a2b6146eca3d4f178e6c7b9ca1de57865b3e2486436867a0b4c82e394` | `4f06b97c93cd05c3fb132b67d0a0f2a18bfc07847d16402c4ec18cdbe3b77d6f` |
| `legion_fighter_platform` | `399010c3d7ad781ecc75f733e3cbf060d1593ce66df1ad2b55f7ff72de776f50` | `b88dd8ee806fc3b8167cd93252a64b87683430fc19cb0f3a177423ef46a32f9c` |
| `syndicate_fighter_platform` | `66eca9908acfc277b24cd3cf71959a9b63de7b40daa2f905e5fdee55f4a262eb` | `d3c1cd6a88c5087519a93a5ae5ed2debf756832d6a4298c9d0d2fe851115d036` |
| `alliance_repair_dock` | `5a5035a39251c5a9cacef545fb3ad7a6ecfef5f2256883872aa364a372b34f99` | `c7290bd9e1f51911c10bf5434de99d3294dd22ba6f6110f886c1677f46615d76` |
| `legion_repair_dock` | `e01b00e394eb894f9e18cf25e9e61efb94093b047d8deacc0b80490bcef385f4` | `3c865b62f82ce4b5d8053d022a481d992f96b69852d335fed6cc0cbde4079d76` |
| `syndicate_repair_dock` | `c608f2afebb2c1a56546441363d8ad24975c928353c35cce3a5cf669534c4770` | `39c5ef2886f1c56c4d2702f5e07fb9eb0adc7245a6711ae34e4cdf73851b9faa` |
| `legion_shipyard` | `3156021eef4c77f744ecdd1a25a8c1f96566e32761e88ee1ae7ac606a2741042` | `748c48aa54266073f5b0773f3ef0748b2cf049cd51523d65f66083163d794f01` |
| `syndicate_shipyard` | `420dedfee68a25da78f4831d93b2dbddb716ba94134a58f890c570cec9efb735` | `c1a0aad3e30a013b95c704390ef925f8beeb024924ddd4a5d525dc60156c4670` |

## Cost

| binding | triangles | verts | parts | bytes |
| --- | --- | --- | --- | --- |
| `rebel:research_station` | 4,812 | 2,580 | 91 | 321,940 |
| `confederacy:research_station` | 3,680 | 2,008 | 86 | 240,463 |
| `syndicate:research_station` | 3,904 | 2,118 | 87 | 259,774 |
| `rebel:defense_platform` | 4,248 | 2,288 | 86 | 285,563 |
| `confederacy:defense_platform` | 3,640 | 2,008 | 95 | 236,511 |
| `syndicate:defense_platform` | 3,520 | 1,936 | 89 | 223,464 |
| `rebel:trade_station` | 3,916 | 2,128 | 88 | 254,765 |
| `confederacy:trade_station` | 3,580 | 1,968 | 90 | 232,608 |
| `syndicate:trade_station` | 3,532 | 1,944 | 90 | 223,717 |
| `rebel:fighter_platform` | 4,288 | 2,312 | 88 | 286,581 |
| `confederacy:fighter_platform` | 3,620 | 2,000 | 96 | 229,697 |
| `syndicate:fighter_platform` | 3,544 | 1,952 | 91 | 222,560 |
| `rebel:repair_dock` | 4,696 | 2,516 | 88 | 316,320 |
| `confederacy:repair_dock` | 3,356 | 1,840 | 82 | 215,949 |
| `syndicate:repair_dock` | 3,548 | 1,952 | 90 | 226,350 |
| `confederacy:shipyard` | 3,772 | 2,064 | 98 | 236,690 |
| `syndicate:shipyard` | 3,784 | 2,072 | 99 | 241,812 |

Wrapper advisories are `MAX_TRIANGLES 11500`, `MAX_VERTICES 8000`, `MAX_BYTES 2_000_000` (the
station budget policy B3a and B3b use); the loader's hard caps are 12,000 / 10,000 / 2,000,000 in
`render/authored_mesh.py`. The heaviest specimen uses 42 % of the
advisory triangle budget and 32 % of the vertex budget. Every mesh fills all six
material roles (`base, dark, trim, accent, lit, cool`), which the loader requires — an empty role
is rejected at load with `ValueError: empty authored <x> role`.

## What changed visibly

At the close view each specimen is a solid shaded structure with its own silhouette — a ringed
research band and mast, an armoured disc with battery hardpoints, a cargo band with cranes, an open
launch deck, a cradle dock, a slipway with gantry frames — and no wireframe or placeholder geometry
in any of the after-captures. Every part is welded: the seed runs `weld_scene()` before it reports
its extent, and the exported meshes are re-measured for detached parts by
`test_no_part_of_any_station_floats_clear_of_the_rest`. Welding was also where this batch's design
guard did its work: `weld_scene` judges a joint by the clear space between two parts' boxes, so a
hardware row stepped wider than its own blocks leaves each block standing alone, and the first cut
of the seed failed on eight of the seventeen specimens for exactly that reason - the rows now step
by less than one block width.

Measured change against the legacy procedural station, same scene, same cameras, same tick:

| binding | close | rear | tactical | common-scale |
| --- | --- | --- | --- | --- |
| `rebel:research_station` | 23.9902 % | 19.4785 % | 1.1672 % | 0.2271 % |
| `confederacy:research_station` | 33.1424 % | 29.0291 % | 1.66 % | 0.4439 % |
| `syndicate:research_station` | 44.0691 % | 34.6971 % | 2.3563 % | 0.4085 % |
| `rebel:defense_platform` | 16.4207 % | 11.1978 % | 1.1275 % | 0.1258 % |
| `confederacy:defense_platform` | 19.4248 % | 14.7287 % | 1.0826 % | 0.1358 % |
| `syndicate:defense_platform` | 27.6663 % | 20.6692 % | 2.4305 % | 0.0953 % |
| `rebel:trade_station` | 27.7538 % | 19.053 % | 1.6605 % | 0.146 % |
| `confederacy:trade_station` | 23.4964 % | 17.4725 % | 1.2886 % | 0.1659 % |
| `syndicate:trade_station` | 34.4824 % | 26.0563 % | 2.0319 % | 0.2021 % |
| `rebel:fighter_platform` | 29.5594 % | 21.8303 % | 1.8854 % | 0.3716 % |
| `confederacy:fighter_platform` | 35.2002 % | 27.5523 % | 2.2854 % | 0.2255 % |
| `syndicate:fighter_platform` | 40.1647 % | 32.8266 % | 2.0646 % | 0.188 % |
| `rebel:repair_dock` | 42.518 % | 34.829 % | 2.7335 % | 0.1635 % |
| `confederacy:repair_dock` | 44.1488 % | 35.4422 % | 2.3185 % | 0.1855 % |
| `syndicate:repair_dock` | 46.021 % | 41.2356 % | 2.7867 % | 0.1787 % |
| `confederacy:shipyard` | 38.73 % | 30.4134 % | 2.6356 % | 2.0598 % |
| `syndicate:shipyard` | 44.8101 % | 43.1285 % | 2.2159 % | 1.1888 % |

Batch totals: close 5,853,167 / rear 4,706,715 / tactical 345,405
changed pixels over 3 px. The close and rear views are each row's own framing and are the honest
appearance evidence; `tactical` is a 5.6× shot and `common-scale` is one shared camera. A station
that changes few pixels at tactical range is a low-profile one seen from 5.6×, not a missing model:
every row is non-zero in all four views, which the sheet's guard asserts.

## Review-harness corrections made in this batch

All three are review-tooling corrections; no production renderer, gameplay, catalogue or registry
file changed.

1. **`overview` framing for a seventeen-row line.** The earlier station batches frame the overview
   at yaw 48 / pitch 50 / distance 1100, where the eye is displaced ~0.43 × distance *along* the row
   axis: it ends up level with the far end of the line, rows beyond it are behind the camera, and
   the near ones project past the frame edge. Measured on this spec's first run, the far rows came
   back with negative depth and the near end at `x_ndc -1.25`, so the file that reads as "the batch
   overview" showed four objects. This batch's sheet uses yaw 90 / pitch 40 / distance 2800, where
   the line is perpendicular to the view: all seventeen rows sit at 2800 units and inside
   (±0.82 `x_ndc`), so the lineup is a true single-scale comparison with no perspective spread. It
   is a spec value in this batch's own sheet; every earlier batch keeps its committed frames.
2. **`overview.close_distance_floor`, reused from B3b** (150): these stations frame at 110–215 units
   and the shared scene's context group would otherwise put the near eye inside a hull, which
   `capture_slice.camera_check` refuses as `camera not outside union`.
3. **`overview.png` was a leftover row capture.** The harness saved it from the `pixels` buffer the
   last row's last draw left behind, so the file that reads as the batch overview did not move when
   the overview camera moved - a framing check run against it inspects the wrong frame. It now
   saves the frame the overview draw made, and a guard asserts that.

Guards added for these: `test_the_row_line_cannot_overlap_and_fits_the_overview_frame` (reproduces
the projection from the harness's own camera constants and requires every row in frame, in front of
the camera, and within 1.35× of the others' distance) and
`test_the_sheet_overview_file_comes_from_the_overview_draw`.

## Review metrics (the numbers behind the captures)

`tools/diag_alliance_batch_review.py --spec art/manifests/pending/S06-BATCH-B3C-STATIONS.json
--out artifacts/s06_alliance_batch_review/b3c-stations --motion
rebel:research_station,confederacy:shipyard,syndicate:defense_platform` — one process, the real
application, the candidate injected through `render.asset_selection` only:

* 221 evidence files: 17 rows × (before + after) × 4 views, per-row role-ablation and
  restored-simulation frames, three paired motion clips, the overview pair and the contact sheet.
* `status: pending_owner_approval`; `production_shaders: true`; `source_preserved: true`;
  `protected_files_preserved: true`; `production_candidates_unselected_after_review: true`.
* `restored_changed_pixels: 0` on all seventeen rows — the specimen does not perturb the restored
  simulation, so nothing here is a gameplay change.
* `repeat_changed_pixels: 0` on every capture of every row: the same frame twice, same tick.
* Role ablations, minimum per role across the batch: accent 1,582 / dark 25,365 / cool 823 changed pixels — every role reaches
  pixels on every row, measured from the camera that can see it (accent and dark from the close
  view, cool from the rear view).
* Three paired motion clips, 150 frames each, `paired_samples_equal: true` on each: the moving
  camera sees the station without perturbing the simulation.
* Overview: `yaw 90, pitch 40, distance 2800`, target `[-4200, 0, 3120]`,
  20,607 changed pixels across all seventeen rows.

| binding | accent (close) | dark (close) | cool (rear) |
| --- | --- | --- | --- |
| `rebel:research_station` | 1,582 | 26,137 | 3,780 |
| `confederacy:research_station` | 2,798 | 42,990 | 9,964 |
| `syndicate:research_station` | 1,893 | 42,302 | 8,991 |
| `rebel:defense_platform` | 31,751 | 25,365 | 2,438 |
| `confederacy:defense_platform` | 9,037 | 29,174 | 823 |
| `syndicate:defense_platform` | 6,671 | 27,889 | 3,371 |
| `rebel:trade_station` | 22,185 | 33,635 | 2,621 |
| `confederacy:trade_station` | 10,856 | 56,404 | 3,002 |
| `syndicate:trade_station` | 7,228 | 38,955 | 4,457 |
| `rebel:fighter_platform` | 19,747 | 32,774 | 6,416 |
| `confederacy:fighter_platform` | 3,349 | 29,641 | 4,323 |
| `syndicate:fighter_platform` | 2,619 | 62,312 | 5,632 |
| `rebel:repair_dock` | 20,644 | 56,306 | 4,896 |
| `confederacy:repair_dock` | 10,118 | 70,719 | 1,117 |
| `syndicate:repair_dock` | 13,493 | 55,333 | 6,012 |
| `confederacy:shipyard` | 19,135 | 75,767 | 10,398 |
| `syndicate:shipyard` | 20,584 | 69,990 | 19,267 |

## Tests and commands actually executed

* `PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b3c_stations` →
  **Ran 31 tests, OK** (`Ran 31 tests in 1.1s`). This module is the batch's own guard set:
  loader/envelope/budget contract, reaching the legacy extent per axis and side, the 1,800-triangle
  floor and the half-of-legacy bar, all six material roles, the distinct-design and shared-footprint
  guards, the ring-noun/annulus guard, export-only source safety (17 assets × 4 master aliases),
  the seed's refusal to overwrite a master, the seed's extent self-check noise/real pair, the
  generated-wrapper catalogue, the station seam and legacy dispatch, the completeness of the whole
  faction station table (30 rows = B3a 3 + B3b 9 + B3c 17 + the approved `rebel:shipyard`), the
  imperial rows still having no authorized seam, the spec/sidecar/evidence records, and the
  nothing-floats guard over the exported meshes.
* The shared focused union (this module + `test_s06_placement_repairs` + the B1/B2/B3a/B3b batch
  modules + `test_alliance_blender_cruiser/_trio/_battleship` + `test_asset_contract`,
  `test_model_pipeline`, `test_generic_model_preview`, `test_model_context_lifecycle`) →
  **Ran 163 tests in 12.070s / OK**.
* Seeding: Blender 5.0.1, `build_b3c_stations.py --asset <binding> --replace-seed` per specimen →
  17 masters, `SEED_OK`, and `SELFCHECK <label> breaches=0 tolerance=0.001` on every one. The first
  cut of this seed refused on eight specimens (`weld_scene`'s 10-unit brace rule) and printed the
  pair and the clear space; the designs were re-placed rather than the rule relaxed.
* Exporting: seventeen wrappers exit 0, each printing `GAME_EXPORT` with bounds on the legacy
  extent to the digit and its own triangle count. None is near the 1,800 floor.
* Sidecars: `tools/art/write_pending_sidecars.py --batch s06-b3c-stations` then `--check` →
  seventeen sidecars, `0 stale sidecar(s)`.
* The evidence-path guard is red until the review run finishes (the harness refuses an existing
  `--out` directory, so a re-capture starts with `rm -rf`), which is the guard working rather than
  a regression — it is what caught the B1 sheet pointing at a clip no run had produced.

## Actual-game captures and recipe

The review harness renders the **real application** with the candidate injected through
`render.asset_selection` only — one process per batch, `SDL_VIDEODRIVER` unset, each row owned by a
player of its own faction (a station's faction comes from its **owner**,
`render.renderer.owner_faction(state, e.owner)`, not from its data row), every row placed as a
station rather than spawned as a ship, and every row labelled uniquely so no capture can overwrite
another. Frames live in `artifacts/s06_alliance_batch_review/b3c-stations/`: `contact-sheet.png`
(UNAPPROVED REVIEW ONLY), `overview.png` (all seventeen at one scale) and per row
`<label>-after-close.png`, `<label>-after-rear.png`, `<label>-after-tactical.png`,
`<label>-after-common-scale.png`, the three ablation frames and the restored frame. Three rows also
carry `<label>-before-motion.mp4` and `<label>-after-motion.mp4`.

## Performance / packaging / platform

No production geometry, material, shader, gameplay or registry file changed, so there is nothing to
re-measure in the shipped renderer: the frames above are the *candidate* path only. Triangle, vertex
and byte costs sit inside both the wrapper advisories and the loader's hard caps. Packaging is
untouched — no release, tag, DMG or ZIP; the Windows package job stays skipped by design. This is an
offline orbit capture set: production draw and real simulation ticks, not paced FPS, battle
acceptance or native Windows graphics acceptance.

## Open issues, blockers and decisions required

1. **Appearance approval of these seventeen specimens** — the ask below. Each is bound to the
   hashes above; approval of one is not approval of another.
2. **The imperial station rows** — ten bindings that need an owner scope decision before they can be
   authored (and a landing decision for the seam behind them).
3. **Landing**: every S06 specimen (B1, B2, B3a, B3b, B3c) stays `procedural_legacy` with
   `activation: false` until each revision is explicitly approved and landed behind its own gate.
4. **`trade_convoy`'s envelope** remains an owner/renderer decision and is not authored here.

## Status of this batch vs. the S06 scope

With B1 (corvette + carrier), B2 (8 squadron/logistics hulls), B3a (3 command stations), B3b (9
small stations) and this batch (17), every authorable faction station row in
`assets/data/stations/stations.json` is now accounted for: 3 + 9 + 17 + the approved
`alliance_shipyard` = the 30 faction rows of the catalogue's ten station kinds. What remains in B3 is
the imperial seam and the owner's approvals — not more authoring of these kinds. The next authoring
slice in the approved order is B4 (satellites and planet installations), which the B3 handoff
enumerates as `stations.json` keys minus the station kinds.

## Owner approval

One line is what this needs: **do these seventeen stations look like the right direction?** A yes
approves appearance for the revisions whose hashes are listed here; it does not merge, tag, release,
land or switch any production default, and each landing stays its own decision.
