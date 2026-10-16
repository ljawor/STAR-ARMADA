# Handoff: S04 — generic opt-in model integration

Status: **complete and merged** as `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c` (PR #124). Not a model-approval transfer or S11 authorization. Historical review checkpoints below are retained.

## Base commit / branch

Base: `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c` (`origin/main`).
Branch: `feat/s04-generic-model-integration`, isolated scratch worktree.
PR: **#124**, merged after owner authorization. Initial verified code commit: `45e4ed3b731fde6c376fdb894088a248abc774e9`.
Read the exact final pushed head and remote blob receipt from the PR comment; it cannot be baked
into this self-referential document.

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
Fresh clone of code commit `45e4ed3b731fde6c376fdb894088a248abc774e9`: **184 tests, 0 failures/errors/skips**;
contract 36 checks / 28 negative controls / 0 skipped; pipeline 34/34; nine metadata files reproduced.
The supplemental run executes the worktree-skipped frozen-path test. Both original and fresh logs are
retained, not retroactively combined. No full-suite claim.
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
Independent review initially rejected three logic defects; separate-context fixes and regression tests
passed a scoped re-review. Initial and final verdicts are retained. Draft PR #124 publishes the code;
its final receipt names the exact head, remote blob comparison and current CI status.
Next owner gate: review S04 PR #124. After it is accepted, S05 executes the full approved-trio
equivalence/approval-transfer matrix; do not start catalogue authoring or S11 from this handoff.

Two owner questions remain open: authoring extent drift versus collision policy, and advisory draw-call/
texture-byte columns. Neither has been answered by the pack-load envelope decision.
S05 owns the full approved-trio equivalence matrix; do not mark it complete from S04 unit tests.

## CI integration repair and final fresh-clone receipt

Windows runs `38952034998` and `38952529212` exposed an S04 catalogue reproducibility defect.
The second also failed LAN recovery (tick 6 != 8); two immutable baseline and two immutable candidate
local repetitions passed. This is **not reproduced locally**, not proven pre-existing. No deadline
or assertion was relaxed. Both Windows logs and classifications are retained.

All four language packs now reproducibly include the six preview strings (366 UI keys, 96 names),
through authored translations and UTF-8/LF writers. The real settings pack-count row is localized.
A real autocrlf checkout then exposed conversion of hash-pinned mesh JSON and its approval evidence.
Scoped `-text` attributes now **disable conversion**, preserving committed runtime, authoring, schema
and evidence bytes; no approved mesh, Blender or exporter content changed. The intermediate failures
and RED controls are retained. This is not a broad LF normalization or a changed approval hash.

Final code: `19d63f7d677cd2cdb5b5fd60e4a9e95c810c63d5`. A fresh clone with `core.autocrlf=true` passes
**195 focused tests, no failures/errors/skips**, nine-file metadata reproduction and pipeline 34/34.
Unprotected render source really contains CRLF in that clone; language catalogues remain LF and
all eleven approved source/runtime hashes match baseline. Capture source hashes match this commit;
eight views still have zero preview differences and equal simulation hashes.
See `final-fresh-clone-tests.txt` and `final-fresh-clone-verification.json` in the evidence directory.
The final focused command extends the original module list with `test_language_tools`.
Independent review passed the language repair; parent additionally verified the byte-preserving
attribute follow-up in the real clone. Native Windows CI must pass the next pushed head; this local
checkout is not native Windows rendering/package acceptance. No full suite or S11 authorization.

## Merge completion and next step

Owner instruction, verbatim: **"OK we can merge and continue with next step"**.
Verified head `311edc24c66084a3e145d07e23aad7b839487b5d` passed Windows CI `38955424960`,
including LAN and replay deletion; manual package job skipped. Squash merge
`7030dd252ddb4da3bb4f69fecb2f2028650ffe6c` has exactly the same Git tree
(`e28b24faa1c1c6bc574635e481493f51490774fa`) as that tested head.
Read `art/manifests/equivalence/S04-MERGE.json` and the PR merge receipt.
S05 is now in progress on its own branch, with criteria frozen in
`art/manifests/equivalence/S05-CRITERIA.json`. No tag, release, new model revision or S11 activation.
