# S06 B4 - the satellite and planet-installation rows

Batch sheet: `art/manifests/pending/S06-BATCH-B4-HARDWARE.json` · branch `feat/s06-next-model-batch` ·
draft PR #127 · authored 2026-10-17.

## What this batch is

The satellite and planet-installation kinds that `assets/data/stations/stations.json` holds beside
the station kinds, across all four factions - **24 rows**: `defense_satellite` and
`attack_satellite`, plus `planet_extractor`, `planet_trade_hub`, `planet_shield_generator` and
`planet_pulsar_cannon`, for `rebel`, `confederacy`, `syndicate` and `imperial`.

The owner authorized this batch as `s06-b4-scope-2026-10-17`, and the imperial rows with it as
`s06-imperial-migration-2026-10-17` (`art/manifests/pipeline_policy.json`). Neither decision approves
a revision: **every row here is pending owner appearance approval**, `activation` is false, the
registry still reports `procedural_legacy` and `art/manifests/pipeline.json` does not carry them.

## How they were made

One recipe authors all 24 rows (`tools/art/build_b4_hardware.py`) because these are
repeated modular hardware: they are **script-authoritative** under the S03 source-authority policy,
so the recipe is the master and each `.blend` is a derived artefact kept for inspection. Every
dimension comes from the binding's own legacy extent, measured from the live code by
`tools/art/probe_b4_scope.py` rather than transcribed, and each design carries four *reach* parts
that land that extent exactly - per axis and per side - because the harness compares the authored
footprint against legacy hardware that fills its declared box. The legacy ring side count is kept
per faction (Alliance 12, Legion 8, Syndicate 5, Imperial 6), so a row still reads as the family's
hardware it replaces.

Extents are the legacy ones measured per row, and they are **not** uniform: the legacy satellite
mesh is parameterised by the faction's ring side count, so the syndicate's five-sided ring stops
short at the rear. Both of the rows that differ are called out here rather than smoothed over.

| binding | envelope (lo .. hi) | Z span |
|---|---|---|
| `rebel:defense_satellite` | (-41.1051, -9.0, -34.0) .. (41.1051, 19.5, 44.0) | 78.0 |
| `rebel:attack_satellite` | (-50.9795, -9.0, -34.0) .. (50.9795, 21.5, 58.0) | 92.0 |
| `rebel:planet_extractor` | (-34.0, 0.0, -32.0) .. (34.0, 43.0, 32.0) | 64.0 |
| `rebel:planet_trade_hub` | (-34.0, 0.0, -32.0) .. (34.0, 49.5, 32.0) | 64.0 |
| `rebel:planet_shield_generator` | (-34.0, 0.0, -32.0) .. (34.0, 46.5, 32.0) | 64.0 |
| `rebel:planet_pulsar_cannon` | (-34.0, 0.0, -32.0) .. (34.0, 42.4, 46.0) | 78.0 |
| `confederacy:defense_satellite` | (-41.1051, -9.0, -34.0) .. (41.1051, 19.5, 44.0) | 78.0 |
| `confederacy:attack_satellite` | (-50.9795, -9.0, -34.0) .. (50.9795, 21.5, 58.0) | 92.0 |
| `confederacy:planet_extractor` | (-34.0, 0.0, -32.0) .. (34.0, 43.0, 32.0) | 64.0 |
| `confederacy:planet_trade_hub` | (-34.0, 0.0, -32.0) .. (34.0, 49.5, 32.0) | 64.0 |
| `confederacy:planet_shield_generator` | (-34.0, 0.0, -32.0) .. (34.0, 46.5, 32.0) | 64.0 |
| `confederacy:planet_pulsar_cannon` | (-34.0, 0.0, -32.0) .. (34.0, 42.4, 46.0) | 78.0 |
| `syndicate:defense_satellite` | (-41.1051, -9.0, -27.5066) .. (41.1051, 19.5, 44.0) | 71.5 |
| `syndicate:attack_satellite` | (-50.9795, -9.0, -30.299) .. (50.9795, 21.5, 58.0) | 88.3 |
| `syndicate:planet_extractor` | (-34.0, 0.0, -32.0) .. (34.0, 43.0, 32.0) | 64.0 |
| `syndicate:planet_trade_hub` | (-34.0, 0.0, -32.0) .. (34.0, 49.5, 32.0) | 64.0 |
| `syndicate:planet_shield_generator` | (-34.0, 0.0, -32.0) .. (34.0, 46.5, 32.0) | 64.0 |
| `syndicate:planet_pulsar_cannon` | (-34.0, 0.0, -32.0) .. (34.0, 42.4, 46.0) | 78.0 |
| `imperial:defense_satellite` | (-41.1051, -9.0, -34.0) .. (41.1051, 19.5, 44.0) | 78.0 |
| `imperial:attack_satellite` | (-50.9795, -9.0, -34.0) .. (50.9795, 21.5, 58.0) | 92.0 |
| `imperial:planet_extractor` | (-34.0, 0.0, -32.0) .. (34.0, 43.0, 32.0) | 64.0 |
| `imperial:planet_trade_hub` | (-34.0, 0.0, -32.0) .. (34.0, 49.5, 32.0) | 64.0 |
| `imperial:planet_shield_generator` | (-34.0, 0.0, -32.0) .. (34.0, 46.5, 32.0) | 64.0 |
| `imperial:planet_pulsar_cannon` | (-34.0, 0.0, -32.0) .. (34.0, 42.4, 46.0) | 78.0 |

## Size

| binding | triangles | vertices | bytes |
|---|---|---|---|
| `confederacy:attack_satellite` | 2,432 | 1,360 | 141,204 |
| `confederacy:defense_satellite` | 2,180 | 1,216 | 127,275 |
| `confederacy:planet_extractor` | 2,596 | 1,456 | 144,966 |
| `confederacy:planet_pulsar_cannon` | 2,396 | 1,344 | 136,137 |
| `confederacy:planet_shield_generator` | 2,608 | 1,440 | 159,373 |
| `confederacy:planet_trade_hub` | 2,344 | 1,312 | 132,236 |
| `imperial:attack_satellite` | 2,312 | 1,300 | 131,117 |
| `imperial:defense_satellite` | 2,060 | 1,156 | 117,249 |
| `imperial:planet_extractor` | 2,500 | 1,408 | 137,123 |
| `imperial:planet_pulsar_cannon` | 2,300 | 1,296 | 128,327 |
| `imperial:planet_shield_generator` | 2,416 | 1,344 | 143,512 |
| `imperial:planet_trade_hub` | 2,248 | 1,264 | 124,411 |
| `rebel:attack_satellite` | 2,672 | 1,480 | 160,000 |
| `rebel:defense_satellite` | 2,420 | 1,336 | 146,073 |
| `rebel:planet_extractor` | 2,788 | 1,552 | 160,122 |
| `rebel:planet_pulsar_cannon` | 2,588 | 1,440 | 151,386 |
| `rebel:planet_shield_generator` | 2,992 | 1,632 | 189,744 |
| `rebel:planet_trade_hub` | 2,536 | 1,408 | 147,368 |
| `syndicate:attack_satellite` | 2,284 | 1,286 | 129,924 |
| `syndicate:defense_satellite` | 2,032 | 1,142 | 116,184 |
| `syndicate:planet_extractor` | 2,484 | 1,400 | 135,912 |
| `syndicate:planet_pulsar_cannon` | 2,284 | 1,288 | 127,078 |
| `syndicate:planet_shield_generator` | 2,352 | 1,312 | 138,031 |
| `syndicate:planet_trade_hub` | 2,232 | 1,256 | 123,191 |

Floor is the exporter's own 1,800-triangle refusal; the cap is this batch's declared 11,500
triangles / 8,000 vertices (the station class budget - the owner has set no separate modular-hardware
budget), under the runtime loader's 12,000 / 10,000. Worst case here is
2,992 triangles, so every row clears the floor and none approaches
the cap.

## Evidence

`artifacts/s06_alliance_batch_review/b4-hardware/` - **309 files** written by the real
application through `tools/diag_alliance_batch_review.py`: a contact sheet over every row, and per
row a before/after close frame, a tactical frame, three per-role ablation frames, a restored frame,
plus three paired motion clips. Every capture is of the row's own authored revision at its binding's
site, in a reviewed preview registry that is disabled again before the run ends, so nothing in the
run selects an asset in production.

## What the review measured

Read from the harness's own report (`review-b4.log`), not from intent:

| measure | result |
|---|---|
| authored footprint vs the legacy mesh it replaces | worst error **5.21e-05 %** per axis across all 24 rows - the rows reach the legacy extent and exceed nothing |
| drawn length (the class scale the renderer and collision radius read) | worst error **5.21e-05 %**; `station_scale` is 0.9 on every row, i.e. the catalogue radius 45 is untouched |
| close-view change vs the legacy hardware | 7.85 % - 18.61 % of pixels |
| tactical-view change | 0.90 % - 4.04 % |
| per-role ablation (`accent` / `dark` / `cool`) | smallest **3,719 / 964 / 128** pixels, median 6,199 / 11,326 / 208 - **no zero-pixel ablation anywhere** |

The `cool` role is the weakest signal by an order of magnitude (128-308 pixels): every row does carry
a vent row, but on these small hardware rows it is a small part of the mesh, so a reviewer reading
only the ablation frames will see very little. It is non-zero on all 24 rows, and the honest reading
is that the cooling detail is present but slight at these sizes.

## Tests and commands actually executed

* `Blender --background --python tools/art/build_b4_hardware.py -- --asset <binding> --replace-seed`
  for all 24 rows: every master reports `SELFCHECK <asset> breaches=0
  tolerance=0.001`, i.e. the evaluated mesh reaches its envelope inside float noise and exceeds
  nothing.
* `Blender --background --python tools/art/export_<identifier>.py` for all 24 rows:
  `GAME_EXPORT` with the bounds asserted inside the envelope and the triangle floor asserted.
* `PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b4_hardware` - the batch's own
  guards, which re-derive the mesh contract, the extent match, the role fill, the unique part names,
  the export wrappers, the seed's refusal and extent self-check, the seam, the sheet, the sidecars
  and the absence of any production selection.
* `PYTHONPATH=tests .venv/bin/python tools/art/validate-models --all --no-contract`.

## Owner approval

One line is what this needs: **do these twenty-four satellite and planet-installation models look
like the right direction?** A yes approves appearance for the revisions whose hashes are listed in
the sidecars; it does not merge, tag, release, land or switch any production default, and each
landing stays its own decision under S10/S11.
