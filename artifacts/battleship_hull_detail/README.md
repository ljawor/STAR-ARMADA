# Alliance Pelagic — hull surface detail revision

Status: **approved** — the owner approved this revision on 2026-10-16 ("This looks good"),
recorded as `s06-battleship-hull-detail-2026-10-16` in `art/manifests/approvals.json`, which now
binds the battleship's approved revision to these hashes. Nothing here changes gameplay,
silhouettes, scale or the other two trio assets.

## What changed

The approved Pelagic battleship was sculpted but its surfaces were one continuous grey
plate between the major features. This revision adds hull surface detail to
`tools/art/build_alliance_battleship.py` and regenerates the asset from it:

| | before (main) | after |
|---|---|---|
| `assets/models/alliance_battleship.mesh.json` | 8,701 triangles, 4,603 vertices, 144 parts, 594,859 bytes | **11,457 triangles**, 6,419 vertices, 363 parts, 743,439 bytes |
| budget | — | loader `MAX_TRIANGLES` 12,000, generator guard `< 11,888`, file budget 2,000,000 bytes |

Added, all placed from the frame it sits on (`surface()` reads the same section lists the
loft is built from, so detail cannot float off or sink in):

- raised aft-deck plating with an edge trench each side, and banded armour plating down
  the bow crown with longitudinal strakes;
- two open bow machinery wells with raised coamings;
- a flank armour belt of large raised plates with dark inter-plate gaps, and machinery
  banks of two to three stacked blocks;
- four vent banks per side with real blades standing proud of the belt;
- bridge-base window bands with a dark inset under them, island machinery ledges;
- aft drive housings over the cowls and shoulder-deck machinery;
- ram-belt ribs and the owner-colour prow chevron and deck centre stripe.

Detail is deliberately **large-scale**: a 12-triangle block is about four pixels at the
shipped close camera, so the pass spends its triangles on bold steps, trenches and
machinery banks instead of hairline seams.

## Evidence in this directory

- `before-after-review.png` — the review sheet: approved hull versus this revision at
  capital-detail (310 u), capital-close (450 u) and tactical (3,100 u), plus native-pixel
  crops of the bow deck and the aft machinery.
- `comparison.json` — per-view changed-pixel counts, changed bounding box and frame
  sha256 for both revisions.
- `capture_views.py`, `review_sheet.py` — the capture and sheet scripts used, so the
  numbers above can be regenerated rather than trusted.

Raw 1280x800 frames are not committed (same policy as the S00 trio evidence); the sheet
carries the comparison.

## How it was produced and checked

```bash
# rebuild the asset from its script-authoritative builder (Blender 5.0.1)
/Applications/Blender.app/Contents/MacOS/Blender --background --python tools/art/build_alliance_battleship.py

# the two contracts that pin the asset
PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_battleship test_alliance_blender_trio test_detmath

# capture BOTH revisions with the S00 harness's own scene recipe and cameras
PYTHONPATH= .venv/bin/python capture_views.py <tree> <out-dir> <label>

# and build the sheet
PYTHONPATH= .venv/bin/python review_sheet.py <before-tree> <after-tree> <before-captures> <after-captures>
```

Measured in-game differences (1280x800 frames, same recipe, same frozen view time,
production default materials on an Apple M4 with 4x MSAA):

| view | changed pixels | of 1,024,000 |
|---|---|---|
| capital-detail (310 u) | 24,193 | 2.36 % |
| capital-close (450 u) | 12,932 | 1.26 % |
| capital-keel (400 u) | 9,096 | 0.89 % |
| tactical (3,100 u) | 832 | 0.08 % |
| common scale (1,800 u) | 1,092 | 0.11 % |
| escort close (155 u, frigate) | 6,530 | 0.64 % — only where the battleship stands behind it |
| yard close (450 u, shipyard) | **0** | **byte-identical frame** |

`tests/fixtures/alliance_trio_unselected.sha256.json` pins 73 catalogue entries so a
migration cannot silently change hulls it does not own. Exactly one entry moved —
`ship/rebel/battleship` (`46f3bf20…` → `c53f7f65…`); the other 72 were verified unchanged by
recomputing all of them.

## Approval

Approved by the owner on 2026-10-16 and recorded as `s06-battleship-hull-detail-2026-10-16`.
`art/manifests/approvals.json` now binds `core:alliance/battleship` to this revision's source,
exporter and runtime hashes, and `art/manifests/approved-trio-source-hashes.json` carries the
same numbers, so `tools/art/validate-models` reports the battleship as satisfying the approved
record again. The superseded runtime hash is kept under `superseded_revision`.

Deliberately not done here:

- the frigate and the shipyard are untouched; the same treatment rolls out to them as a
  separate batch, and that batch must fit the trio guard of 9,000 triangles per asset
  (frigate 5,128 used, shipyard 7,935 used) unless the class budgets are revisited.
- no budget was raised: the loader still caps a mesh at 12,000 triangles and the generator
  guard at 11,888, and this revision lands at 11,457.

## Pipeline receipt (after the approval record was updated)

```
python3 tools/art/build-model     --asset rebel:battleship
# ok - 11457 triangles, runtime sha256 0a4e397d5c0b60f7... matches the approved bytes
python3 tools/art/export-model    --asset rebel:battleship
# ok - 11457 triangles, runtime sha256 0a4e397d5c0b60f7... matches the approved bytes
#   (exported inside a throwaway copy; the declared .blend was not touched)
python3 tools/art/validate-models --all
# FAILED - 32/33 checks, 1 failures: E_NO_CONTRACT_VALIDATOR only
#   (tools/art/validate_contract.py arrives with the S02 contract, PR #117)
python3 tools/art/validate-models --all --no-contract
# satisfied - 32/32 checks, 0 failures, 1 warning
```

`art/manifests/pipeline.json` and `art/manifests/provenance/rebel-battleship.json` were updated by the
same commands: the registry's `expected_triangles` (8,701 -> 11,457) and approval `decision_id`, and a
fresh provenance record whose `source` hash is the approved `.blend` (the pipeline regenerates the
`.blend`, sees unchanged runtime bytes and restores it from Git, per policy). Until this update
`validate-models` correctly failed the revision with `E_TRIANGLE_COUNT` and `E_PROVENANCE_STALE` - the
artifact and the records have to move together, and the pipeline is what enforces that.
