# Frigate and shipyard: surface detail

The second batch of the hull surface-detail roll-out. The capital hull was revised in
`s06-battleship-hull-detail-2026-10-16` (PR #120); this batch carries the same language to the two
remaining authored models of the trio and raises the authoring ceiling that would have stopped it.

Owner's ask, verbatim: *"we have a very plain hull / only grey without any details. Can we change
this. I out you some example picture that you can look through nad try maybe to work out something
based on it."* The three reference pictures were read for panel divisions, raised armour plates,
greeble clusters, trenches, vents and tonal steps beyond a single grey.

## The guard this batch had to raise first

`tools/art/alliance_common.py` capped an exported gameplay mesh at **9,000 triangles** and did not
watch vertices at all. The frigate sat at 5,128 and the shipyard at 7,935, so the yard had about a
thousand triangles of headroom: roughly a quarter of the detail the capital received.

Raised to a **11,888-triangle ceiling and a new 9,500-vertex ceiling**, recorded as its own policy
decision — `s07-detail-budget-2026-10-16` in `art/manifests/pipeline_policy.json` — with the owner's
`do it` quoted and the reasoning written down, because a guard change is a decision, not a tweak.
The reasoning: surface detail costs 12 triangles and 8 vertices per block, a 12-triangle block is
about four pixels at the shipped close camera, and the hard limits are the runtime loader's
(`render/authored_mesh.py`: 12,000 triangles, 10,000 vertices, 2,000,000 bytes) — past which the model
is refused and the build is wasted. Both ceilings sit deliberately just under those.

The same decision record notes an inconsistency it deliberately did **not** change:
`art/manifests/pipeline.json` gives the shipyard an advisory budget of 16,000 triangles while the
loader that reads the same registry caps at 12,000, so that advisory can never fire. Those advisories
are the S02 §9 class budgets still pending the owner's review (PR #117, question 1); retuning them in
an art PR would answer that question by accident.

## What changed

Both builders now name the loft frames they are built from (`HULL`, `CROWN`, `KEEL`, `ISLAND`,
`CASING`; `RAIL`, `RAIL_CROWN`, `CROSSHEAD`, `TOWER`, `HOUSING`) and place detail from those same
numbers through `tools/art/hull_detail.py`, so a panel line cannot float off a deck or sink into a
flank when a frame is retuned. Nothing here adds silhouette, scale or gameplay: every element stands
0.4 to 3 units proud of the surface it sits on, and `flank_detail(..., x_limit=...)` clips a bank to
the envelope the model has already declared, so detail may fill a bounding box but never widen it.

* **Deck and crown** — alternating transverse frame bands, longitudinal strakes, raised armour
  panels on the bow crown, machinery wells on the aft deck.
* **Flanks** — an armour belt with dark inter-plate trenches, a second lower belt row for a second
  tonal step, machinery banks, vent louvres (a dark recess with bright blades across it) and a row of
  deck-edge rail posts with feet.
* **Frigate only** — drive-casing machinery banks, clipped to the ±34 beam the casings already set,
  because a bounding box is a scale and not a surface.
* **Shipyard** — rail crown frame bands, plating panels, strakes and access hatches; rail flanks with
  belt, trenches, machinery banks, vent banks and a row of service pads down the outer face; gantry
  pedestal collars and gussets; guide-shoe contact plates and wear strips; crosshead machinery banks
  with radiator fins; operations-tower window bands with a dark inset under them; keel-tie ribs.

The first pass of this work (fine panel lines, ~0.8 % of the close-camera frame changed) was thrown
away as invisible and rewritten bolder at the same triangle budget; the rule that came out of it is
in the module docstring: spend the budget on bold steps, not hairline seams.

## Numbers

| | triangles | vertices | bounding box (X, Y, Z) |
|---|---|---|---|
| frigate before | 5,128 | 2,704 | 68.0, 35.35, 153.699997 |
| frigate after | **7,708** | **4,424** | 68.0, 35.35, 153.699997 *(identical)* |
| shipyard before | 7,935 | 4,269 | 111.400002, 56.400002, 97.5 |
| shipyard after | **10,767** | **6,157** | 111.400002, 56.400002, 97.5 *(identical)* |

Neither model changes size, so neither changes its in-game scale. `frigate-shipyard-detail-comparison.json`
holds these numbers with the runtime hashes and the per-view pixel statistics.

## The evidence, and the negative control

Both capture sets were taken from the S00 harness's own recipe, cameras and frozen view time
(`view_time = 3.0`, no ticks), with production default materials: BEFORE from the approved revision
this batch is stacked on (PR #120 head `7d54294`), AFTER from this batch's worktree. Same scene, same
cameras, same materials — the only difference is the two payloads.

* `frigate-shipyard-detail-review.png` — the sheet the owner reviews: both models before and after at
  the shipped cameras, with native-pixel crops of the frigate's flank and the yard's rails.
* Changed pixels of 1,024,000: escort-close **12,050** (1.177 %), yard-close **21,199** (2.07 %),
  common-scale 1,475 (0.144 %), tactical 671 (0.066 %).
* **Negative control:** the capital's payload is byte-identical between the two trees
  (`0a4e397d5c0b…`, 11,457 triangles both sides), and its frames move only where the escort and the
  yard are drawn — `changed-where-capital-close.png` paints every differing pixel red and none of it
  lands on the battleship. `changed-where-escort-close.png` and `changed-where-yard-close.png` show
  the two ships' diffs confined to their own surfaces, with no outline ring around either silhouette
  — the proof that the shape did not move (the identical bounding boxes above are the numeric half).

## Approved: `s07-frigate-shipyard-hull-detail-2026-10-16`

The owner reviewed the sheet above and answered **"Models looking good approved"**, recorded verbatim
as its own decision (`art/manifests/approvals.json`), bound to this revision's exact hashes:

| | frigate | shipyard |
|---|---|---|
| `.blend` | `721693dce2de…` | `2b66ad339f75…` |
| builder | `8a3822c0d39d…` | `22e98cf85620…` |
| shared helper `alliance_common.py` | `bc5ef04dee22…` | `bc5ef04dee22…` |
| shared detail module `hull_detail.py` | `aa6e8880b03e…` | `aa6e8880b03e…` |
| runtime | `8562c3c85424…` | `b0ee2678ab42…` |
| superseded runtime | `045d1383ac8a…` | `67d4db64c867…` |

The guard raise moved `alliance_common.py`, which the earlier battleship record also names as an
exporter, so that record's live binding is corrected to the current hash: the battleship's own
`.blend` and runtime hashes are untouched and still validate, so nothing about its approved
appearance changed. Its `decision_log` entry keeps the hash as recorded at that approval.

The receipts, in the order the records move:

```
tools/art/build-model  --asset rebel:frigate    # ok - 7708 triangles, runtime 8562c3c85424... matches the approved bytes
tools/art/export-model --asset rebel:frigate    # ok - byte-identical from a throwaway copy: the revision is reproducible
tools/art/build-model  --asset rebel:shipyard   # ok - 10767 triangles, runtime b0ee2678ab42... matches the approved bytes
tools/art/export-model --asset rebel:shipyard   # ok - byte-identical from a throwaway copy
tools/art/validate-models --all --no-contract   # satisfied - 32/32 checks, 0 failures
tools/art/validate-models --all                 # 32/33: the only failure is E_NO_CONTRACT_VALIDATOR (PR #117)
```

**The one place a hand edit forgets is the registry.** `tools/art/pipeline.json` is never written by
the pipeline — `expected_triangles` and `approval.decision_id` are updated by hand — and
`validate-models` caught exactly those two fields still holding `5,128` / `7,935` and
`approved-trio-2026-10-16` after everything else had moved. That is the guard earning its keep: the
numbers above were only accepted once `--no-contract` came back satisfied with them in place.

## A finding: the 73-entry pin does not cover these two models

`tests/fixtures/alliance_trio_unselected.sha256.json` pins 73 unselected catalogue meshes so an
authored revision cannot silently change a hull it does not own. It includes `ship/rebel/battleship`
but **not** `ship/rebel/frigate` and **not** `station/rebel/shipyard` — the two models this batch
changes. Both previews demonstrably depend on the authored payload:

```
render.faction_ships.ship_mesh('rebel','frigate')     8b743eac… → 43b79b1c…
render.faction_stations.station_mesh('rebel','shipyard') cd20bc77… → 4f85a4c5…
render.faction_ships.ship_mesh('rebel','battleship')  c53f7f65… → c53f7f65…   (unchanged, the control)
```

So for these two entries the pin is not a second opinion; the pipeline registry is the only record
that moved with them here. Tightening the pin means adding those two keys, which changes a test's
own expectation — a guard change, so it is offered rather than done.

## Reproducing

```
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
    --python tools/art/build_alliance_frigate.py
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
    --python tools/art/build_alliance_shipyard.py
PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_trio \
    test_alliance_blender_battleship test_detmath test_ship_sizes test_faction_ships \
    test_ship_material_passes test_alliance_visual_slice test_faction_visuals \
    test_fire_arcs test_combat_standoff test_skirmish_setup      # 105 tests OK
```

The captures come from `capture_views.py` (invoked with a tree, an output directory and a label)
against the approved revision and against this branch; `review_sheet.py` builds the sheet and the
comparison from those two sets.

Nothing here is a production default: the revision is approved as an art revision, and switching
either model on in the shipped game, tagging or releasing it is still the owner's separate call.
