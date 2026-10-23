# Free Systems Alliance — complete 26-model redesign

## Approved ordinary-game delivery

All **26 existing Alliance bindings** have new editable Blender masters and strict-runtime-validated exports: 10 ship/logistics, 10 orbital stations, 2 satellites, and 4 surface installations. Crew transports and generated trade convoys share their existing single binding. No classes, balance, gameplay, saves, or simulation changed.

The models are **active through ordinary `main.py`, including fresh installs**:
- Fresh defaults enable all 15 packs; saved selections exactly matching either historical 13- or 14-pack shipped cohort migrate to the new list. Custom/reordered/subset/extended/empty lists and unrelated preferences are preserved.
- `saves/settings.json` enables the new pack alongside all 14 accepted Imperium packs. Every other saved preference is preserved.
- The actual native entry catalogue contains all 26 new mesh hashes.
- Ordinary `main.py --smoke` passed: `SMOKE_CPP_OK`, 30 simulated seconds, 367 published frames.

```sh
.venv/bin/python main.py
```

Choose Free Systems Alliance normally. No art viewer, command-line art switch or runtime Blender installation is required.

**Owner appearance, normal-game activation and merge approved:** “Looks good merge”. `OWNER_REVIEW.json` binds that decision to all 26 exact reviewed exports. Fresh defaults and both historical saved-settings migrations are implemented, not optional-only. No tag or release is authorized by this decision.

Earlier review receipts and unchanged pack provenance/labels retain their review-time pending wording. They are historical; `OWNER_REVIEW.json` and this delivery status supersede that wording without rewriting sealed capture evidence or changing reviewed mesh bytes.

## Actual evidence

- `fleet-review.png`, `stations-review.png`, `hardware-review.png`: all 26 native-rendered models, individually framed, **not** relative-size fleet charts.
- `native-full-faction/`: same-subject close/rear/tactical BEFORE/AFTER pairs. Its 27 subjects include an Imperial Vigil with **zero changed pixels in all three views**.
- `native-full-faction/metrics.json`: exact mesh paths/hashes, cameras, drawn lengths and per-view image differences. Every Alliance pair changes.
- `native-full-faction/evidence-sha256.json`: retained PNG/snapshot/report hashes and the exact capture script, builder, descriptor and native executable hashes. Retained PNG recompression preserves decoded pixels.
- `normal-game-catalogue.json`: exactly **26 / 103** native asset rows changed; all other **77 rows** are identical. The only other payload change is `metadata.visual_selection`; cameras, instances and all other metadata are identical.
- `normal-main-smoke.{json,txt}`, `native-full-faction-supervised.{json,txt}`: real bounded execution receipts.
- `coverage.json`: actual live IDs, original hashes/envelopes and every new export/hash.
- `build/complete-faction.json`: actual Blender 5.0.1 counts, roles and source hashes.
- `measured-resources.json`: **96,708 Alliance triangles**, combined with unchanged accepted Imperium **223,872 / 240,000**, leaving **16,128** triangles. All six roles are populated, no degenerate triangles were skipped, existing vertex/byte/triangle ceilings stay unchanged.

The normal smoke proves startup and a live match, not organic construction of every class, physical owner play-testing, packaged Windows/macOS delivery or FPS. Publication timings exclude simulation/rendering and are not FPS.

## Design and containment

Modular/naval Alliance construction rather than recolored Imperial wedges: blunt crossheads, pressure spines, replaceable armor/machinery, open carrier hangars and drydock cradles, attached cranes, habitats and working industrial frames. Capitals received substantive raised panel banks and exposed service machinery after a rejected initial full-family render showed overly plain surfaces.

Every model stays within its existing replacement envelope with small inward clearance. Original core masters/exports and accepted Imperium assets/helpers are unchanged. Integration updates `assets/cpp/catalogue.snap`, normal defaults/settings migration in `render/menus.py`, and focused regression tests.

Masters: `art/blender/alliance_redesign_<kind>.blend`.
Pack: `visual_packs/alliance-redesign/`.
Offline live/template IDs, budgets and dispatch: `tools/art/alliance_redesign_catalogue.py`.

The dedicated review exporter uses production `station_binding` and actual owner factions; it does not inherit the generic benchmark exporter's Imperial-station assumption. Snapshot metadata describes actual isolated subjects, not the old four-Imperial-fleet workload.

## Reproduce

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/art/build_alliance_redesign.py
.venv/bin/python tools/art/package_alliance_redesign.py
.venv/bin/python -m pytest -q tests/test_alliance_redesign_*.py \
  tests/test_alliance_game_activation.py
.venv/bin/python tools/render/verify_alliance_redesign.py --include-control \
  --out /absolute/fresh/path/native-pairs
```

Existing new outputs require explicit `--replace-own`; never run this on accepted original builders/masters. Combined optional-pack limits are validated together, so splitting packs cannot bypass them.

## Historical evidence

`native-specimens/`, `style-specimens.png`, `build/specimens.json`, `specimen-independent-review.json` and `repeat-export.json` describe the first two-model checkpoint **5db9886e0541436301cba59899228815982dde03**. Its two runtime meshes remain identical, but old source/descriptor pins refer to that checkpoint, not the later full-faction tooling. They are historical, not the current activation claim.

`first-full-iteration-review.json` records the rejected first complete visual pass; original native pixels remain archived in scratch. The orbital detail worker was interrupted after writing changes: parent independently ran current CPU tests, built every actual Blender model, strictly loaded the whole pack and captured the final native frames.
