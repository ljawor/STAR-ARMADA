# STAR ARMADA — post-S08 merge handover: S09 → S10 → S11

Prepared: October 19, 2026. Repository: `~/Downloads/Project/STAR-ARMADA`.

## Paste this into the next chat

> You are continuing STAR ARMADA's Blender model migration. Read `HANDOVER-S09.md`, `docs/BLENDER_MODEL_MIGRATION_ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/GRAPHICS_DRAW_SCOPE_REUSE.md`, and `docs/GRAPHICS_BENCHMARK.md` before acting. S08 and its prerequisite are merged into `main` at `5980890c47f973b50fc677a962242e893e96f001`; the tracked tree equals final tested S08 head `340b5a23af6d70271840d1e1d907c73cdb10dd84`. Select S09 only: establish an immutable candidate and a protected acceptance plan; confirm owner performance targets/resolution and outstanding platform access/waivers before claiming acceptance. Preserve approved art, user files, simulation semantics and the legacy production default. Do not restart S00–S08, silently waive Windows/package/hardware gates, perform the S11 switch, or merge/tag/release without separate authorization. S10 is exact-lock owner sign-off and rollback rehearsal; S11 is the subsequent explicitly authorized default switch, not more model authoring.

This is a suggested next-chat kickoff, not authorization to execute S09–S11 in the current merge-only task.

## 1. Verified landed state

The owner requested: “Merge and create a handover md doucment that I can post in the nect chat. Take into account in th ehandover the next gates S09, S10, S11”. This authorized landing the existing prerequisite/S08 stack, not activation, a new asset revision, a platform waiver, a version bump, a tag or a release.

Both PRs were merged bottom-up with **merge commits**, preserving the reviewed branch history:

| Layer | Reviewed head | Merge into main |
|---|---|---|
| #134 — coverage report refresh / S07 suite receipt follow-up | `5517ad4d642e72f7a9a8c886e9946b5f49ea8490` | `e8925cff60606c5a1c91f987b40f67333ffd6d91` |
| #135 — S08 visual-pack/update/cosmetic compatibility | `340b5a23af6d70271840d1e1d907c73cdb10dd84` | `5980890c47f973b50fc677a962242e893e96f001` |

- #134 merged at 11:50:47 UTC on October 19, 2026; its merge tree exactly equals its reviewed head.
- #135 was then retargeted from the prerequisite branch to `main` and merged at 11:51:11 UTC. Its head was unchanged; merge commands were guarded by exact head SHA.
- Primary checkout was fast-forwarded to `5980890c47f973b50fc677a962242e893e96f001`, matching `origin/main`.
- Main's entire tracked tree equals the final S08 head: Git tree `b28b48ab07abe0c4b5040f4696ffaf14d7e6ef12`. Merge introduced no source/asset changes beyond the tested stack.
- Both GitHub PR states were read back as `MERGED`. No open PRs remained at that check. Recheck all live state next chat.
- **Legacy remains the stock production default. S09, S10 and S11 are not accepted.** No release/tag/default switch was performed.

### Historical wording that must not mislead the next agent

The committed roadmap's S08 rows, `docs/BLENDER_MODEL_S08_PLAN.md`, `art/manifests/handoffs/s08.md`, and the original PR body describe the **pre-merge** delivery. Their “review-ready / not merged / #134 open / merge unauthorized” statements are historical and superseded by the actual merges above. Their engineering limits and S09–S11 gates remain valid. This handover does not rewrite byte-attested historical evidence. Any tracked status refresh must use a feature branch/PR, not direct commits to main.

The original local `HANDOVER-S08.md` is older still and was preserved unchanged. Do not use it to restart already-completed work.

## 2. S08 delivered scope and evidence

S08 is compatibility engineering, not new catalogue art approval:

- `game/data/store.py` tracks effective loaded gameplay-ship provenance; the last successful gameplay writer wins. `render/asset_selection.py` derives additive authorization from the actual loaded `DataStore`, not file presence or a cosmetic pack's claims.
- `main.py` closes the old renderer, configures selection with `gm.ds`, then creates the new renderer. Cosmetic selection stays outside authoritative game state, persistence/checksum schemas and gameplay compatibility.
- `render/asset_registry.py` stages optional packs transactionally, rejects unsafe/corrupt/incompatible/conflicting data without breaking preceding/later valid packs, and retains validated immutable all-LOD session snapshots. Session-boundary reactivation revalidates; there is no live-match hot reload.
- `examples/visual_packs/core-frigate` replaces one core binding; `raider-addon` adds a namespaced asset with the separate actual gameplay fixture `mods/s08_raiders_fixture`.
- Examples derive from the real 7,708-triangle Alliance frigate export by a documented trim/accent-role remap. Core Blender/source/export bytes and existing approvals are unchanged. These examples are not new owner-approved models or a complete playable Raiders faction.
- Same-path updates exercise CPU/contact/bounds caches and real native GL teardown/recreation/recompilation. Broken controls detect stale caches and leaked/wrongly keyed GL resources.
- Save/replay evidence has 16 generated current/legacy-fixture histories and 2,896 exact dictionary comparisons. Separate production TCP peers with different validated cosmetics match at 181 boundaries with eight delayed commands and actual movement/outcome assertions. Gameplay-changing-mod incompatibility remains strict.

### Evidence index

Read these committed files rather than depending on ephemeral scratch paths:

- `artifacts/s08/S08-RECEIPT.json`: sealed source/evidence/preservation receipt.
- `artifacts/s08/integrated/receipt.json`: final **150 tests / 18 isolated modules, zero skips**, plus four successful tool gates. This is not a whole S09 suite.
- `artifacts/s08/review.json` and `review-supplement.json`: original independent review (35 bounded headless tests) and final-delta review; no blocking findings. Later checkout-attribute fixes are explained separately; do not attribute them to an earlier independent verdict.
- `artifacts/s08/native-examples/report.json` and close/tactical PNGs: actual production-renderer core/replacement/disabled comparisons. Disabling restores exact core frames; appearance captures are not platform/performance acceptance.
- `artifacts/s08/integrated/cosmetic/`: final compatibility histories/checksums; standalone earlier evidence is labelled separately.
- `artifacts/s08/preservation.json`: 771 protected tracked files unchanged against prerequisite base.
- `docs/VISUAL_MODEL_PACKS.md`: real installation/order/dependencies/update/disabling/diagnostic contract.
- `art/manifests/handoffs/s08.md`, `docs/BLENDER_MODEL_S08_PLAN.md`: original bounded engineering criteria and limitations.
- #135 publication-verification comment, ID `6266468470`: exact-head remote blob/file-set verification and full final autocrlf fresh-clone receipt.

### Real prerequisites repaired; failed history retained

1. The exact pristine base lacked `art/manifests/approved-s07-scaffold-source-hashes.json`. Metadata reproduction/model validation failed before S08. The missing record was recovered only after independent regeneration, exact equality to the existing S07 record and verification of all five pins. SHA256: `bda9dca664be79de059e88643f7dccf5491a30f9885b83ebc528148aab2ba99c`. No asset/approval bytes changed. See `prerequisite-control/` and retained failed integration attempts.
2. Real network clones with `core.autocrlf=true` exposed inherited unprotected raw source pins. Exact-path `.gitattributes -text` rules preserve renderer and the remaining approved-pin closure; no renderer/diagnostic source bytes or approvals were rewritten. Actual RED logs and a GREEN control remain under `artifacts/s08/publication-autocrlf/`.
3. Final ordinary committed-attributes clone at head `340b5a2`: **35 focused headless tests, zero skips**, models/metadata/example checks passed; all 339 existing approved source-pin files matched the source checkout. This was a macOS checkout/EOL test, not native Windows execution.

### CI and post-merge verification

- Final S08-head Windows workflow `39246217311`: **LAN surface on real Windows passed**. Candidate Windows package was **skipped**, not passed. #134's corresponding LAN check also passed before merge.
- At handover preparation, main-head workflow `39247640571` for `5980890` was **in progress**, not yet verified green. Query its live state next chat. Do not substitute PR-head CI for a claimed main-head workflow result.
- After merging, on actual main, native write-deny barriers made the primary checkout and Application Support read-only to the four check processes. All exited 0:
  - `.venv/bin/python tools/art/validate-models --all`: **1034/1034 checks**, zero failures/warnings.
  - `.venv/bin/python tools/art/sync_runtime_metadata.py --check`: **112 files**, no mesh writes.
  - `.venv/bin/python tools/art/reconcile_model_coverage.py --check`: `CHECK_OK`.
  - `.venv/bin/python tools/art/build_s08_examples.py --check`: **nine files verified**, approved inputs read-only.
- The 150-test native gate was not rerun after merge: exact Git-tree equality binds its existing tested payload to main. No new full-suite/package/performance/native-Windows-graphics claim is made.
- Additional local receipts: `~/.hermes/cache/scratch/s08-post-merge/receipt.json` and `s08-published-evidence/`. Scratch may expire; committed evidence and GitHub receipts are the durable sources.

## 3. Catalogue and known acceptance debt to carry forward

- S00–S08 are closed for their delivered scopes; do not restart their appearance reviews without a meaningful visual revision.
- Current accepted milestone: **103 of 119 registry bindings registered and approved**, with **16 explicit exceptions** under `s07-s06-coverage-exception-2026-10-19`: 12 `authoring_pending` and four `keep_procedural_proposed`. The historical inventory has 120 rows; it is a different denominator. Do not invent missing meshes by subtracting unrelated counts.
- Exceptions include eight planet environments, the cinematic backdrop and three planned Syndicate hulls; exceptions are not completed art and do not make Syndicate playable. Review their exact disposition at S10; don't widen it.
- S07 receipt: `artifacts/s07-runtime-final/S07-FINAL-RECEIPT.json`. Its broad per-module sweep is historical, not a new S09 pass. The recorded `test_crew_recovery_ui` legacy-shape expectation conflicts with the approved Imperial convoy and failed on the actual pristine control. Carry the concrete evidence; do not silently weaken it or infer current failure status without running it.
- Retain historical LAN recovery failures/controls and PR #133's specific recovery repair. Do not generalize that repair into proof that every historical LAN observation or the complete current suite is green.
- Resource limits are 240,000 triangles / 32,000,000 encoded snapshot bytes, **not measured Python RSS**. Pack checks are not an atomic sandbox against hostile concurrent filesystem mutation. V1 has no texture/custom-material files; loaded additive provenance covers ships, not station gameplay additions.

## 4. S09 — next engineering gate: broad acceptance, packages, measurable cost

Authoritative criteria: roadmap §S09, `docs/GRAPHICS_BENCHMARK.md`, and architecture/draw-scope invariants. **Not performed or accepted yet.**

1. **Freeze the integrated candidate.** Start from current main, inspect user work, record exact commit/tree and source/catalogue hashes, and establish a feature branch plus isolated disposable checkout. Name ownership and evidence paths. Avoid changing model bytes/approvals merely to produce acceptance logs.
2. **Protect the user before any broad run.** Use native descendant-inherited write barriers, disposable persistence roots, independent before/after inventories and canaries. Verify the protection itself; Python monkeypatches alone are insufficient for subprocesses/native writes. Never run unsafe discovery in the live playing checkout. Genuine user-created replays are not test pollution to delete.
3. **Run the actual complete suite.** Use appropriate runners for unittest and pytest-authored modules; zero collected tests are not passes. Classify every failure with an actually executed pristine exact-base control, preserve failures/skips/log hashes, and distinguish pre-existing issues from candidate regressions. Do not relax assertions, change balance or claim S08's 150 tests as whole-suite acceptance.
4. **Agree targets before declaring performance accepted.** Ask the owner for target resolution/frame budget and representative hardware. Measure the complete opt-in catalogue, loading, memory/RSS and LOD using the documented stock-queueable fixtures and separately approved stress fixtures. Pin quality, MSAA, fog, workload/catalogue and camera inputs. Separate rendering/CPU/GPU from simulation/checksum/network costs; diagnostic timings are not interactive FPS. Don't silently reduce quality or start an unlimited optimization project.
5. **Close the Windows authoring-pipeline half.** S03 D3 still needs a real Windows fresh-clone rebuild and repeated byte-stable approved runtime export. Headless Windows LAN CI and macOS autocrlf cloning do not satisfy it.
6. **Build and inspect exact-candidate Mac and Windows packages.** Verify runtime assets/manifests/hashes inside frozen products, `sys._MEIPASS` lookup, read-only bundle behavior and external writable mod roots. Exclude editable `.blend` files/authoring tools. Run without Blender or a source checkout. Use disposable clean-install and copied existing-user-data scenarios; never overwrite real saves/settings/replays. A local acceptance package is not permission to publish a tag/release.
7. **Exercise native graphics on required platforms.** Record roles/owner colors, visibility/fog, LOD, lookup, bounds/contact/picking and mod replacement/disabling. Dummy video, mocked GL and hosted LAN checks are separate, narrower evidence.
8. **Respect hardware deferral.** Filip's laptop/physical mixed-machine testing remains deferred unless explicitly reauthorized. Missing platform/hardware evidence stays a blocker or requires a specifically attributable owner waiver—never an inferred pass or permission to use that hardware.

S09 exit: a byte-bound receipt for the complete integrated candidate, suite/failure-control classification, measured cost against agreed targets, exact-candidate package/content/smoke results, native platform evidence and explicit outstanding blockers/waivers. Do not mark complete while a required gate is merely planned or a package job is skipped.

### Tooling cautions

- `.venv/bin/python` is the project interpreter; do not resolve its symlink to a base interpreter lacking packages.
- On macOS, native GL uses Cocoa; headless selection/safety checks use dummy video. Use `os.pathsep` for portable worker `PYTHONPATH` construction.
- Some unittest modules require `import game.core` before loading tests. Inspect the real runner and test count.
- **Do not blindly rerun `tools/art/run_s08_gates.py` on main**: it hardcodes `artifacts/s08/integrated` and overwrites historical evidence. Reuse its patterns in an isolated copy/new output root; preserve the sealed original receipt.
- Serialize Blender, GL, profiling and broad tests. Avoid competing heavy jobs or changing workload inputs during measurement.

## 5. S10 — owner catalogue sign-off and rollback readiness

Depends on S09 acceptance; **not started / not accepted**. This is not the default-switch implementation.

- Present a durable exact-revision gallery, existing batch decisions, common-scale fleet/station views and normal gameplay footage. Preserve previous approvals unless the art changes; expose all shared/environment exceptions and platform/performance limitations.
- Produce and validate `release-asset-lock.json`: every required binding → approved model/export/material revisions and hashes. This is a required future deliverable, not a claim that an approved lock already exists. Reconcile inventory, registry, approval decisions and exact candidate.
- Rehearse returning to legacy using the preview/default selector while preserving saves, replay outcomes, gameplay balance and installed mods. Retain old bindings and recovery diagnostics.
- Obtain explicit owner sign-off and authorization to change the default **for that exact lock**. Approval of appearance, S08 merge or a package build is not that authorization and does not waive failing engineering gates.

S10 exit: owner-bound exact asset lock, explicit exception/limitation disposition, proven rollback rehearsal and separately recorded permission for the S11 default change.

## 6. S11 — final, explicitly authorized default switch

Depends on S10 **and explicit switch authorization**; **not started / not authorized / not done**.

- Make one small, reversible feature PR changing the default to the locked approved Blender registry. No new art, unrelated performance refactor, schema surprise or legacy-code deletion in the switch.
- Verify fresh installs and upgrades with old settings/saves/replays, explicit existing preview preferences, enabled/disabled/installed visual packs, and frozen Mac/Windows packages. Do not label a mixed/missing catalogue complete.
- Recheck visibility, picking/contact/scale, representative fleet cost, asset completeness, focused regressions and required CI on the exact final head; verify remote files and head after publication.
- Document recovery, effective asset/pack diagnostics and accepted exceptions. Retain legacy fallback for the initial rollout; deleting it requires a later proposal.
- Deliver the verified PR and package/evidence receipts. **Merge, tag and release each require separate explicit owner authorization.** The switch is not complete merely because its plan or models exist.

## 7. Workspace safety and next-chat preflight

At this handover, main's only pre-existing untracked file was `HANDOVER-S08.md`; this new `HANDOVER-S09.md` is intentionally a local untracked attachment. No tracked documentation/source edits were made after merging. The old handover's SHA256 remains `9599cf4b36e9da08a0cba17856be2a4bc4c4edeea6ed685b71c811c9c72b9b7c`.

Read these live next chat, rather than trusting the historical snapshot:

```sh
cd ~/Downloads/Project/STAR-ARMADA
git status --short --branch
git fetch origin
git rev-parse HEAD origin/main
gh pr view 134 --json state,mergeCommit
gh pr view 135 --json state,mergeCommit
gh run view 39247640571 --json headSha,status,conclusion,jobs
```

Read inventory/decisions/approval records and `art/manifests/pipeline_policy.json` before choosing acceptance scope. Use copy/hash preservation, never stash/reset/checkout over unrelated work. Never commit directly to main. Preserve scratch worktrees and source approvals; don't remove them just because their PR merged. Keep render metadata out of authoritative simulation. Start one bounded S09 workstream only when requested; S10/S11 are subsequent owner-controlled gates, not permission for automatic rollout.
