# S08 — visual replacement and mod compatibility

Status: **review-ready; focused S08 engineering gates passed**. Scope: roadmap S08 only.
This is an engineering acceptance plan and receipt index,
not an owner art decision, a release lock, a merge authorization, or an S11 activation.

## Baseline and ownership

Implementation branch: `feat/s08-model-mod-compatibility`, based on `5517ad4d642e72f7a9a8c886e9946b5f49ea8490`
(open prerequisite PR #134), itself based on main `0f4f1308a55c3861a34c5b2c6b31aa05d4a4e03b`.
Do not merge the prerequisite or this branch automatically. Preserve true merge history.
The primary working copy and its untracked `HANDOVER-S08.md` are untouched.

Owned surfaces: resolver optional-pack validation; session selection; gameplay-loader
ship provenance (pure loader metadata, no simulation/schema changes); example visual packs,
fixture gameplay mod, focused tests, documentation and S08 evidence.
Approved core geometry, Blender sources, approval decisions, registry and renderer bytes are
not artistic revision targets. The default remains legacy. No native Windows rendering,
physical mixed-machine test, package, performance threshold, asset lock or release claim.

## Criteria fixed before integration acceptance

| ID | Acceptance |
|---|---|
| E1 | Two documented, installable, data-only example visual packs use real evaluated Blender geometry: a core replacement and an additive namespaced asset for an actually loaded gameplay-mod fixture. No inherited/fabricated owner approval. |
| E2 | Additive dependency discovery uses effective loaded gameplay data, not a visual pack's declaration or mere presence on disk. Cosmetic selection does not create units. Existing gameplay compatibility remains strict. |
| E3 | Explicit saved order wins for core conflicts; duplicate IDs/bindings and invalid optional packs fail with diagnostics, preserve preceding valid sources, and allow later valid packs. |
| E4 | Security controls exercise incompatible/corrupt/missing/oversized payloads, unsafe absolute/traversal/symlink paths, invalid bounds and missing/invalid LODs. Unsupported texture/material declarations reject rather than pretending to load textures. |
| E5 | A partial update never partially activates a pack. Updates happen only at a session boundary; rejection falls back to a preceding valid source/core, not an unvalidated or half-new revision. |
| E6 | Same-path asset revision changes at a session boundary change resolved content identity and invalidate derived CPU bounds/contact helpers. Live renderer ownership prevents selection changes. |
| E7 | A native macOS GL test proves old display lists are deleted and new content is compiled across pack updates and context recreation; IDs may be reused by GL, so identity is checked by revision and compilation, not integer inequality. |
| E8 | Supported old-save/legacy-replay fixture loading and continuation are compared before/after cosmetic replacement through production APIs, with explicit limitations for historical data not stored by old formats. |
| E9 | Independent peers with identical gameplay but differing validated cosmetic payloads produce equal precise-state/checksum traces and outcomes. A gameplay-changing-mod negative control still rejects/differs. This is not physical mixed-machine acceptance. |
| E10 | Source/core approvals remain byte-preserved, required built-ins validate, focused gates execute nonzero tests, evidence binds to final inputs, and independent review has no unresolved blocking finding. |

## Evidence discipline

Record executed commands, runners, counts, skips and failures. New production behavior follows
RED→GREEN tests. Every rejection matrix asserts the intended diagnostic rather than counting
an earlier hash/schema failure as a geometry test. Fault-injection controls use disposable
copies or restored in-memory patches, never approved assets or user files.

Only run native GL/heavy gates under one owner. No suite runs while implementation writers or
manifest edits remain. Any broad sweep records the immutable source identity it actually ran;
subsequent source/manifest changes invalidate that gate rather than inheriting an older green.
Full package/platform/performance acceptance remains S09. No zero-test pass, silent fallback
catalogue coverage, simulated output, or inferred owner waiver.

## Executed acceptance and retained evidence

All paths below are repository-relative. `artifacts/s08/S08-RECEIPT.json` seals the final
input, evidence and preservation hashes; the exact pushed head is read back in the PR comment
rather than creating a self-referential commit receipt.

| Criteria | Executed evidence |
|---|---|
| E1–E2 | `test_s08_example_packs` (5 tests), `test_s08_gameplay_dependencies` (3), real fixture DataStore loading, reproducible example builder `--check`, `docs/VISUAL_MODEL_PACKS.md` |
| E3–E4 | `test_s08_pack_safety` (21) plus `test_asset_registry` (25), `artifacts/s08/pack-safety/COMMANDS.txt` and retained RED/GREEN outputs |
| E5–E7 | `test_s08_asset_updates` (3), existing selection/context/helper gates, `integrated/lifecycle-controls.txt`: each of three intentional regressions triggers an assertion, restored CPU/native checks pass |
| E8–E9 | `test_s08_cosmetic_compatibility` (3), `integrated/cosmetic/{summary,tick-checksums}.json`: 16 histories × 181 boundaries, 2,896 full-state comparisons; two separate production TCP peers compare 181 boundaries, exercise 8 delayed commands, verify movement/outcomes; gameplay-mod incompatibility remains enforced |
| E10 | 18 modules / 150 executed tests, zero skips; four tool gates; unchanged input hash map, approval-preservation tests, byte-bound independent review with 35 additional headless checks; final review supplement covers the two portable subprocess path fixes and prerequisite record |

`tools/art/run_s08_gates.py` runs serial isolated processes with bounded process groups and
native Cocoa GL, not a monolithic suite or the S09 gate. The parent invoked it with a native
write-deny sandbox protecting the primary checkout, installed application user-data root,
and the S08 worktree's saves/replays. Disposable tests do not initialize the application menu
or write real settings. The primary checkout remains outside this implementation worktree.

`artifacts/s08/native-examples/report.json` binds actual production-renderer captures and
sources: Apple M4 native GL, four samples, unchanged simulation state; close replacement
changes 9,141 pixels, tactical 776 (threshold >3), disabling restores both core frames exactly.
Parent inspected the close captures: the hull geometry is retained and role colours visibly
change. These are compatibility specimens, not an owner appearance decision.

### Baseline defect recovered, not suppressed

The first integrated attempt failed metadata/pipeline gates because prerequisite commit
`5517ad4` omitted `art/manifests/approved-s07-scaffold-source-hashes.json`.
`artifacts/s08/integrated-attempt1/` preserves that failure. A separate pristine worktree at
that exact commit reproduced metadata drift and `E_NO_APPROVED_RECORD`; see
`artifacts/s08/prerequisite-control/`. The missing record was recovered only after its bytes
matched both the existing S07 scratch record and independently regenerated metadata, and
all five pins matched the real unchanged files. SHA256:
`bda9dca664be79de059e88643f7dccf5491a30f9885b83ebc528148aab2ba99c`.
No geometry, authoring source, appearance approval, test assertion or exporter was changed.

### Limits and next gate

- Runtime snapshot ceilings are 240,000 triangles and 32,000,000 encoded bytes, not an exact
  Python RSS ceiling. All validated LOD snapshots remain immutable within a session.
- Static path containment/special-file checks are not an atomic filesystem sandbox against
  a concurrently hostile process changing paths during activation.
- V1 has no textures/custom-material files; unsupported fields reject. No texture-loading
  capability is invented to satisfy the roadmap's missing-texture negative case.
- Additive application discovery covers actually loaded ships, not station mod additions.
  The Raiders fixture is a catalogue/render seam specimen, not a new playable faction.
- Legacy fixtures are generated historical-field omissions, not actual historical user files.
- Independent review's exact-limit/replacement-budget extra cases remain a nonblocking
  suggestion; existing lowered-cap rollback tests execute both aggregate ceilings.
- S09 full-suite, frozen Mac/Windows packages, native Windows graphics/rebuild, physical
  mixed-machine play, RSS/performance targets and S10 owner asset lock remain unaccepted.
  Hardware deferrals need explicit owner authorization, never an assumed waiver.
- No merge, tag, version bump, release, default switch or new artwork approval is included.
