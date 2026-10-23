# Automated Legions — complete 26-model redesign

## Ordinary-game owner review build

All **26 existing Automated Legions (`confederacy`) bindings** now have original editable Blender masters and strictly runtime-validated exports: 10 ships/logistics, 10 orbital stations, 2 satellites and 4 surface installations. Crew transports and generated trade convoys retain their shared existing binding. No gameplay, balance, classes, simulation or save format changed.

The complete family is **active in this owner's ordinary `main.py` checkout**, not only a diagnostic viewer:
- Owner saved settings contain the previous 15 accepted packs plus `legions-redesign`; unrelated preferences are unchanged and the original settings are backed up.
- The actual production native catalogue contains all 26 current replacement paths/hashes. Exactly 26 asset rows changed; all other 77 rows and all unrelated scene/metadata fields are identical.
- Ordinary `main.py --smoke` passed: exit 0, no timeout/orphans, `SMOKE_CPP_OK`, 30 simulated seconds and 374 published frames.

```sh
.venv/bin/python main.py
```

Choose Automated Legions normally. No alternate viewer, art flag or runtime Blender installation is required.

**Not owner appearance-approved and not merged.** Public fresh defaults remain the prior 15 packs while awaiting the owner's decision. Before an approved merge, add the pack to fresh defaults and migrate exact historical 13-/14-/15-pack shipped cohorts, preserving custom/reordered/subset/extended/empty selections and unrelated preferences. A disabled/optional-only merge is not acceptable. No release/tag is authorized.

## Verification and evidence

- Final local union: **223 tests and 281 subtests passed**, including optimized-Python activation guards and transaction rollback regressions. CPU/loader compatibility is separate from appearance acceptance.
- `fleet-review.png`, `stations-review.png`, `hardware-review.png`: all 26 actual native models, individually framed, not a true-size fleet comparison.
- `native-full-faction/`: 27 subjects including an unchanged Imperial Vigil control; three matched before/after views each. Actual snapshot mesh paths/hashes and image metrics are retained, and all PNGs were losslessly compressed with decoded-pixel equality checks.
- `native-full-faction/evidence-sha256.json`: hashes of every retained capture/snapshot/report and four exact source/executable pins.
- `build/complete-faction.json`: real Blender 5.0.1 evaluated counts, bounds, roles and current source hashes.
- `complete-repeat-export.json`: all **26 mesh exports byte-identical** from an independent fresh full Blender reconstruction.
- `normal-game-catalogue.json`, `normal-main-smoke.{json,txt}`: production activation and bounded ordinary-game execution receipts.
- `coverage.json`: exact actual factory/template IDs, original envelopes, current master/export hashes and per-kind limits.
- `measured-resources.json`: **103,664 Legions triangles**; all active designs combined **327,536 / 360,000 triangles** and **21,539,000 / 32,000,000 mesh bytes**. Strict resolver activation also enforces retained metadata/geometry resource limits.
- **654 existing source/asset files** verified unchanged, including accepted Imperium and Alliance masters, meshes and helpers.

Independent geometry and integration/evidence reviews verified the current 26 exports and ordinary-game activation with no geometry/integration logic errors. Their receipts are retained in `geometry-independent-review.json` and `integration-independent-review.json`. The activation helper was then hardened with explicit optimization-resistant exceptions and atomic, rollback-capable I/O; `activation-security-followup-review.json` independently passed that correction with **no security concerns or logic errors**. The original finding remains in its historical receipt rather than being silently erased.

## Resource authorization and boundaries

The owner explicitly approved: “Approve the 360,000-triangle shared ceiling for the full Legions redesign”. `resource-budget-authorization.json` retains that decision. Only the shared retained-geometry triangle ceiling changes; the shared byte ceiling and per-model 12,000-triangle / 10,000-vertex / 2,000,000-byte limits remain unchanged. This is not FPS acceptance.

Large segmented carapaces, forked machine hulls, distributed computation nodes, robotic assembly cradles, open launch/dock corridors and supported industrial machinery distinguish the faction from Imperium wedges and Alliance naval architecture. The initial overly plain/cyan-banded station/hardware pass was rejected and all sixteen designs revised before the final real exports and captures. `first-iteration-review.json` identifies that historical pass; it is not current appearance evidence.

CPU guards cover closed geometry, envelopes, six roles, functional features, sampled visibility/clearance and attachment. Broad-phase AABB connectivity does not prove every exact solid contact; stronger convex/ray guards cover declared features, not every possible camera or part. Ordinary smoke is not organic construction of every class, physical owner play-testing, frozen Windows/macOS delivery or a performance/FPS gate.

`cpu-checkpoint.json` is historical pre-export evidence. The screen-sharing restriction was respected during that phase; Blender/native work resumed only after the owner said sharing had ended.

## Reproduce

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/art/build_legions_redesign.py
.venv/bin/python tools/art/package_legions_redesign.py
.venv/bin/python -m pytest -q tests/test_legions_redesign_*.py tests/test_legions_game_activation.py
.venv/bin/python tools/render/verify_legions_redesign.py --include-control --out /absolute/fresh/path
```

Existing new masters/exports require explicit `-- --replace-own` after Blender's script arguments. Never run reconstructing tools on accepted baseline masters. Source authority is `build_legions_redesign.py` plus the dedicated Legions design modules; masters live at `art/blender/legions_redesign_<kind>.blend`, runtime data under `visual_packs/legions-redesign/`.
