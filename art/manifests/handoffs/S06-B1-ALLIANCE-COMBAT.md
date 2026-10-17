# Handoff: S06 B1 — Alliance combat batch (Blockade Runner + Independence-class Fleet Carrier)

Status: review-ready (evidence complete; **owner appearance approval not obtained**)
Base commit / branch: branch `feat/s06-next-model-batch`, base `33c85031256b36f6d0bf34247f2a2cd325154596`
(PR #127, draft). Roadmap merge `bd4709f858ae73c39cf11e33b1c6fb01a38dadfb`; merge base with
`origin/main` is `bd4709f`.
PR and exact pushed head: draft PR #127. The pushed head is written in the PR comment that
accompanies this handoff — read it from GitHub, not from this file, because this file ships in
the same commit.
Prerequisites verified: S01 inventory rows for both bindings; S03 source-authority policy
(blend-authoritative default for new silhouettes, export-only rebuild, seed must refuse an
existing master); S04 preview seam `render.asset_selection.mesh_for`; approved trio unchanged.

## Owned files and bindings

| Binding | Identity | Identifier | State |
|---|---|---|---|
| `ship:rebel:corvette` | Blockade Runner | `alliance_corvette` | authored, exported, reviewed — pending approval |
| `ship:rebel:supercapital` | Independence-class Fleet Carrier | `alliance_carrier` | authored, exported, reviewed — pending approval |

- `tools/art/build_alliance_corvette.py`, `tools/art/build_alliance_carrier.py` — initial seeds,
  each refusing to overwrite an existing master without `--replace-seed`.
- `tools/art/export_alliance_corvette.py`, `tools/art/export_alliance_carrier.py` — export-only;
  each opens its declared master itself (the S03 pipeline refuses an exporter that does not,
  `E_EXPORT_NOT_FROM_SOURCE`) and refuses to write over it through any alias.
- `art/blender/alliance_corvette.blend`, `art/blender/alliance_carrier.blend` — editable masters.
- `assets/models/alliance_corvette.mesh.json`, `assets/models/alliance_carrier.mesh.json` — runtime meshes.
- `art/manifests/pending/S06-BATCH-B1-ALLIANCE-COMBAT.json` — batch sheet: the two specimens, the
  review cameras and the per-asset evidence paths. Not an approval record and not a registry entry.
- `art/manifests/pending/S06-ALLIANCE-CORVETTE.json`, `S06-ALLIANCE-CARRIER.json` — review-only sidecars.
  Regenerate with `python3 tools/art/write_pending_sidecars.py`; `--check` fails on drift, so no
  hash in them is hand-typed.
- `tools/art/write_pending_sidecars.py` — sidecar generator (reads every hash, size and count off disk).
- `tools/diag_alliance_batch_review.py` — the batch contact-sheet harness (see the recipe below).
- `tests/test_alliance_blender_b1_combat.py` — 13 focused guards for both specimens.

No `game/`, `assets/data/`, approved-manifest or approved-mesh file is touched. The production
renderer is not modified; the harness injects geometry through the existing `mesh_for` seam in
process, and restores it (asserted) before it exits.

## Source authority / versions

Authority `blend` for both. Blender `5.0.1` (pinned in the seed/export scripts). Contract schema 1;
`render/authored_mesh.py` loader limits 12,000 triangles / 10,000 vertices / 2,000,000 bytes;
`alliance_common.export()` asserts `1,800 < triangles < 11,888` and ≤ 9,500 vertices.

## Changed source and runtime hashes (this revision)

| Asset | Master `.blend` sha256 | Seed sha256 | Exporter sha256 | Runtime sha256 | Triangles | Vertices | Bytes |
|---|---|---|---|---|---|---|---|
| Blockade Runner | `b8ccd72faab4151a8a77b55f946ff800b61549c2759ab5f68fea4a4c788dbe72` | `61838dc1f455de80821945d226d9c9c3fa995cb0af663554f85209b5f26e2381` | `4c9cad303ee3990437e486d90bb0926c5ef016e344072e16dd1c6c66b1016b96` | `bfa1751fd8574bda4145562067acb2e0340498be7ce74d387383079ab7a17c78` | 4,348 | 2,506 | 274,794 |
| Fleet Carrier | `a4c1a577914fda920a6823315b91fb922a6b5903cb76fce74971d4e9fe1710a4` | `0d0e6e90709069032e2eda14202ab1dc93a57e6488d48dd4c5221ec807a844a9` | `b839bc9f7e41b635b116ffa54f3e8dcc425c46cd02de7c6dc2be7b8b82d0bb05` | `4be599d3cfd7b8fdff80716d923c589b322996728b50424b1d6398f8eea3167f` | 8,632 | 5,014 | 543,887 |

Both meshes fill their binding's legacy procedural envelope exactly
(`corvette [[-21.9,-6.0,-46.46],[21.9,15.3,45.0]]`, `supercapital [[-146.51,-30.5,-204.8],[146.51,57.0,190.0]]`
— the carrier's authored dorsal peak is 56.955), so `render.ship_sizes.ship_size` derives the
**unchanged** drawn length: 64.12035 for `rebel_corvette` and 320.60175 for `rebel_supercapital`,
both identical in the candidate and the legacy geometry (asserted live in the harness at a 1%
review tolerance and re-asserted in the tests). Collision radii and every simulation field are
untouched: no `assets/data/` file is in this change.

## What changed visibly

- **Blockade Runner** (4,348 tri): slender spine hull with a deep ventral keel fin, forward bridge
  bastion with graphite visor and roof armour, comms mast, prow ram, swept outboard drive nacelles
  with cowling armour, pylon root fairings, flank vent louvre banks, layered flank plating, keel
  reinforcement, deck machinery banks and crossbrace, blue window bands and an orange lit hatch.
- **Fleet Carrier** (8,632 tri): broad flight deck over a ventral hangar spine, command island with
  visor and window band, radar mast with sensor array and IFF blade, two flight-deck lifts, wing decks
  with underslung frames and support pylons, hangar bay recesses with lit interiors, layered flank
  armour, drive bank casings with six recessed drives in two banks of three, deck and hull
  machinery/vent banks.
- Both keep the owner's blue accent (measured by role ablation), warm lit glazing and cyan drive emission.

## Review-harness correction made in this batch (worth carrying forward)

The first authored corvette had its emitter discs recessed 2.5 units behind a 1.9-radius aperture.
The harness's *requested* rear camera pitch of 5° resolves to the camera's 60-unit height floor, so
a 64-unit escort is actually viewed from ~34–40° elevation — and 0–5% of each disc survived. The
role ablation caught it as **95 changed pixels** where the approved cruiser's drives measure
212–245 each. Geometry fix: recess 0.76 units behind a 2.55 aperture with a 1.9-radius disc, and the
declared `emitter_centers` moved with it. Measured after the fix: **705** changed pixels for the
corvette's `cool` role (7.4× the buried version), with the discs 87% unoccluded from the resolved
rear eye (the earlier 0% figure and the carrier's contradictory probe output were both harness bugs;
a clean re-implementation of the same ray test and the rendered ablations agree that the carrier's
six drives are fully visible). **A declared `emitter_centers` that does not match the exported
emitter geometry is now a failing test**, which is what caught the stale metadata after the move.

## Owner approval

**None.** No owner decision is recorded for either revision in this handoff; the batch sheet is
evidence for review, not an approval. Both remain pending appearance approval, unregistered, and
unselected in production. `rebel:corvette` and `rebel:supercapital` keep registry status
`procedural_legacy`.

## Tests and commands actually executed

`PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b1_combat -v` → **13 passed**
(geometry/loader contract and budget; legacy envelope + unchanged drawn length; named-feature
presence; declared emitter centres matching exported emitter geometry with five negative controls;
clear-aft-ray plus a discriminating buried control per emitter; five corruption modes rejected by the
production loader; four master-alias refusals per exporter; export-only AST check; seed refuses an
existing master; batch spec/pending-registration guards).

Shared guard set re-run on this head — `test_alliance_blender_cruiser`, `test_alliance_blender_trio`,
`test_alliance_blender_battleship`, `test_asset_contract`, `test_model_pipeline`,
`test_generic_model_preview`, `test_model_context_lifecycle` together with the 13 new B1 guards:
**59 tests, OK** (`Ran 59 tests in 4.423s`), no failures or errors.

Evidence run: `.venv/bin/python tools/diag_alliance_batch_review.py --spec
art/manifests/pending/S06-BATCH-B1-ALLIANCE-COMBAT.json --out artifacts/s06_alliance_batch_review/b1-alliance-combat
--motion rebel:supercapital` → rc=0. Reported by that run: 4 MSAA on an Apple M4 with production
shaders available; repeat-capture delta 0 pixels on every view of both specimens; paired-motion
state samples equal across all 150 frames; `source_preserved`, `protected_files_preserved`
(`saves/`, `replays/`, `art/blender/`, `tools/art/` hashed before and after) and
`production_candidates_unselected_after_review` all true; role ablations accent 2,043 / dark 6,701 /
cool 705 (corvette) and 577 / 14,278 / 2,443 (carrier).

Not run, and not claimed: the full suite, performance/benchmark modes, native Windows graphics,
packaging, and any Blender-free fresh-clone rebuild of these two assets. **The cruiser's deep
acceptance matrix was deliberately not repeated** for these hulls, per the owner's batch direction.

## Actual-game captures and recipe

`artifacts/s06_alliance_batch_review/b1-alliance-combat/`:
`contact-sheet.png` (batch sheet), `overview-before/after.png` (one shared-scale row),
`{corvette,carrier}-{before,after}-{close,rear,tactical,common-scale}.png`,
`{corvette,carrier}-ablated-{accent,dark,cool}.png`, `{corvette,carrier}-close-restored.png`,
`corvette-after-motion.mp4` and `carrier-{before,after}-motion.mp4`, `metrics.json`.

Recipe: production `Renderer`/`Camera`/`HUD` on a real-driver 1280×800 4MSAA context, normal fog and
production shaders, real 1/30 s `gm.step` ticks, identical union-safe cameras for both variants,
1280×800 raw frames piped to ffmpeg (150 frames, 5 s). Each specimen is shown beside the same
camera on the legacy procedural hull, so the pairs are look comparisons, **not** scale comparisons;
`common-scale` and the batch overview are the scale views. The carrier's motion is captured because
its geometry/scale warrants it.

## Performance / packaging / platform

Not measured here, by design: per the owner's batch direction these are S09/integrated-milestone
gates. No frame-rate, memory or Windows claim is made. The three approved assets and the approved
pipeline are unchanged, so the earlier S05 evidence still describes them.

## User-data preservation and unrelated work

`protected_files_preserved: true` — `saves/`, `replays/`, `art/blender/` and `tools/art/` hashes are
identical before and after the review run. The live user checkout was never used for authoring and
its local `main`/working tree is untouched. Explicit-path staging only; `.venv` (an untracked symlink
in the worktree) is not staged. The cruiser revision, its records and its evidence are unchanged.

## Open issues, blockers and decisions required

1. **Owner appearance approval is outstanding for all three S06 revisions** (cruiser, corvette,
   carrier). Enumerated on the batch sheet, bound to the hashes above. One word per asset is enough;
   the harness and records are already in place so an approval lands as a records commit.
2. The drive-aperture lesson above should be applied to the escort-sized hulls in the remaining
   batches rather than rediscovered: **a hull whose length is comparable to the camera's 60-unit
   height floor is viewed at 35–50° elevation, so keep a coaxial drive recess under ~0.4 × the disc
   radius and the aperture at least the disc radius.**
3. B2 (squadrons/logistics, 15 bindings), B3 (stations, 40 bindings), B4 (satellites/planet
   installations, 24 bindings) and B5 (environment props) remain. `trade_convoy` rows have no
   `ShipData` row (minted by the trading system) and need an owner decision on their envelope.
4. No merge, tag, release or production-default activation is authorized. Registry status for both
   new bindings must stay `procedural_legacy` until an approval is recorded.

## Next executable step and its acceptance criteria

Author the **B2 squadrons/logistics** batch with shared tooling: one squadron builder parameterised by
faction silhouette, one logistics hull; per asset the cheap guards above (bounded geometry/normals/
winding/roles/envelope, safe export, source preservation, one reproducibility check); then one shared
batch contact sheet at close/tactical/rear plus a paired-motion check where geometry warrants it.
Acceptance: every listed B2 binding has a master, an export-only script, a pending sidecar regenerated
by `write_pending_sidecars.py --check`, focused tests green, and evidence committed under
`artifacts/s06_alliance_batch_review/`; no production registration and no merge.
