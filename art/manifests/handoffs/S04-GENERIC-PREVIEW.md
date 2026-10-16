# Handoff: S04 — generic opt-in model integration

Status: **in-progress**. This is not a completion or model-approval record.

## Base commit / branch

Base: `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c` (`origin/main`).
Branch: `feat/s04-generic-model-integration`, isolated scratch worktree.
PR and exact pushed head: **not published yet**. Read the final head from GitHub when published;
do not bake a self-referential head into this file.

## Prerequisites verified

Read the roadmap, S00–S03 handoffs, architecture, contract, schemas, decisions, inventory,
approvals, pipeline policies and authoring tools. Fresh baseline checks:

- `python3 tools/art/validate_contract.py`: 36 checks, 28 negative controls, 0 skipped.
- `python3 tools/art/validate-models --all`: 34/34 checks, 0 failures, 0 warnings.
- `python3 tools/art/build_model_inventory.py --check`: fails on the inventory and coverage matrix.
  Independent regeneration outside the worktree identifies only `base_commit` and nested
  `code_base` metadata changes, plus the matrix base heading; 120 binding rows unchanged.
  The attempted outside-root regeneration wrote both files then failed in its final
  `relative_to(ROOT)` progress print. A separate read/diff verified the outputs. This is
  diagnostic harness failure, not a successful generator invocation. Inventory repair stays separate.
- Older handoffs contain historical counts and unmerged status superseded by the actual tree.

## Owned files and assets/bindings

New resolver/selection: `render/asset_registry.py`, `render/asset_selection.py`.
Integration: faction/fleet geometry facades, renderer, menu settings and application session boundary.
Runtime registry/manifests: new metadata under `assets/models/` only.
Tests: dedicated resolver, selection and real-context lifecycle modules.
Records: this handoff, `art/manifests/decisions.md`, S04 evidence and contract documentation;
roadmap status only when the transition is backed by committed evidence.

## Source authority / Blender / exporter / schema versions

No new Blender work. Existing approved trio sources, scripts and runtime payloads are immutable.
The runtime consumes data only; authoring tools and `art/` are not bundled. Runtime metadata must
therefore live beneath shipped `assets/`, with source and frozen discovery exercised separately.

## Owner decision

`s04-pack-envelope-2026-10-16`, proposal: **reject the whole visual pack if a replacement exceeds
 the binding's approved envelope; keep collision radii unchanged.** Owner Lukasz Jawor's reply,
verbatim: **"yes"**. Recorded next to the parsed policy in `art/manifests/decisions.md` (D-21).
This authorizes that rule only, not merge/release, a new model revision or the S11 switch.

## What changed visibly

The opt-in model-preview toggle is on Settings → Readability & help, with an informational pack
count and persisted-order documentation. The stock default is legacy. The trio now passes through
the generic resolver in preview, including geometry and authored-material selection. Eight actual-GL
frames match the prototype baseline pixel-for-pixel; the legacy negative control differs in all eight.
The approved sources/mesh payloads themselves have not changed.

## Tests and commands actually executed

Strict test-first slices exercised absent preferences, persisted enabled order, malformed/duplicate
pack names, safe menu normalization, natural small-window toggle/persistence, explicit boundary
diagnostics, renderer ownership and coherent bounds/contact invalidation.

Latest focused command at this checkpoint:

```
SDL_VIDEODRIVER=cocoa PYTHONPATH=tests .venv/bin/python -m unittest \
  test_asset_registry test_asset_selection test_generic_model_preview \
  test_model_context_lifecycle test_runtime_asset_metadata test_alliance_blender_trio \
  test_alliance_blender_battleship test_alliance_visual_slice test_ship_material_passes \
  test_fleet_materials test_faction_ships test_faction_visuals test_ship_sizes test_detmath \
  test_renderer_constructor_cleanup test_gl_lifecycle test_i18n.SettingsIntegrationTests \
  test_presentation_ux test_frozen_paths test_model_pipeline test_asset_contract
```

184 tests, 0 failures/errors, one skip (`not a git checkout`: the old frozen-path test expects a
`.git` directory, not a worktree's `.git` file). Real context recreation, constructor rollback,
additive-asset display-list compilation, revision-keyed GPU caches and CPU helper invalidation run.
Fresh-clone supplemental validation is still pending publication. No full-suite claim.
Durable output and retained failures: `artifacts/s04_generic_preview/`.

## Evidence / platform / packaging limitations

Eight prototype/preview/legacy view triples, 1280×800 with actual 4× MSAA, Cocoa/Apple M4,
production shaders and normal fog. Zero differing preview channels, identical repeat frames and
simulation hashes; legacy differs in every view. `artifacts/s04_generic_preview/verification.json`,
`review-sheet.png`, selected full-resolution captures and reproducible scripts. Images inspected.
No Windows/native package acceptance. Full S05 approval-transfer matrix remains open.
No full suite run: S09 owns that broad milestone. Existing acceptance debt is retained.

## User-data preservation

No editing in the live checkout. Menu tests patch all five persistence constants to disposable roots
before construction; renderer tests use scratch state. Stage explicit files only; `.venv` is an
untracked local symlink and must never be committed. No merge, tag, release or cleanup of user data.

## Open work / next executable task

Runtime resolver, explicit preview/legacy boundary, generic geometry/material dispatch, bounded CPU
caches, revision-keyed GPU lists, transactional envelope rejection, replacement/additive fixture
integration, source/frozen discovery and reproducible shipped metadata are implemented and focused-green.
Finish independent review, resolve findings, refresh final receipts, validate a fresh clone, publish a
verified draft PR and retain its exact-head receipt. Do not call S04 complete before publication/review.

Two owner questions remain open: authoring extent drift versus collision policy, and advisory draw-call/
texture-byte columns. Neither has been answered by the pack-load envelope decision.
S05 owns the full approved-trio equivalence matrix; do not mark it complete from S04 unit tests.
