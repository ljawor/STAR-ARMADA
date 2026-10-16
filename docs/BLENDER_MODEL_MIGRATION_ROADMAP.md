# STAR ARMADA — Blender model migration roadmap

## 1. Purpose, authority and owner decisions

**Deliverable: replace the existing in-game 3D model catalogue with owner-approved Blender-authored assets through a versioned, moddable asset pipeline.** This is an implementation roadmap for separate chats and potentially different AI agents, not permission to replace the whole catalogue in one task.

Owner decisions recorded in this conversation:

- Blender-authored models are the approved direction. The Alliance battleship, frigate and shipyard gameplay comparisons establish the initial visual reference.
- **Every model must pass through Blender and receive explicit owner approval.** Approval of the direction, one faction or one model does not approve other models.
- Editable Blender files and the runtime exports must be stored in Git, not only on a developer's machine or in chat attachments.
- The integration must support future model improvements and mods without editing renderer dispatch code for each replacement.
- **The final implementation step is the controlled switch from legacy models to the approved Blender catalogue.** Earlier steps build and exercise an opt-in preview path; they must not silently change the production default.

Visual progress is the priority. Work in small, visible batches: create models, integrate in preview, show actual-game pictures, obtain approval. Do not replace this workflow with repeated optimization rounds or long test cycles between minor artistic changes. Run focused checks per batch and broad acceptance at integration milestones.

This roadmap supersedes `GRAPHICS_UPGRADE_PLAN.md` for model authoring, storage, approval, mod compatibility and catalogue migration sequencing. That document still supplies graphics/performance context; `ARCHITECTURE.md` remains authoritative for simulation/render separation. Unrelated engine, shader, UI and gameplay redesigns are not included.

## 2. Current baseline and honest status

Repository observations when this roadmap was written, October 16, 2026:

| Area | Observed state | What this does not establish |
|---|---|---|
| Git baseline | Feature branch `docs/graphics-upgrade-plan`; latest committed implementation before this document is `6ea098fa4e4de755705cb83b4c163b1a88d41eda`; PR #113 is open | The later working-tree prototype is not contained in that commit |
| Approved visual slice | Alliance `rebel_battleship`, `rebel_frigate`, and Alliance-owned `shipyard`; owner approved the shown Blender direction and trio | Approval of all catalogue assets or any later visual revision |
| Authoring | `.blend` files in `art/blender/`, scripts in `tools/art/`, exported meshes in `assets/models/` | A generic registry, complete mod interface or complete catalogue |
| Runtime | `render/authored_mesh.py` validates three asset-specific profiles; faction facades dispatch them; material-pass fixes and authored-surface selection exist in the working tree | Production-ready generic resolution, packaged-platform acceptance or final rollout |
| Evidence | Trio comparisons in `artifacts/alliance_blender_trio/`; earlier battleship/material comparisons in adjacent artifact directories | Durable remote storage until explicitly committed and verified |
| Tests | Latest trio evidence records 79 focused tests, 181 matching combat-state samples and preservation of user files | A clean full suite, native Windows graphics or packaged acceptance |
| Known acceptance debt | An earlier 1,671-test full run had one LAN recovery `tick 6 != 8` failure; five isolated baseline and five candidate repetitions later passed | The failure's cause is not established by those passes; do not mark it fixed |
| User replay files | Four replay additions during that run were confirmed by the owner as their own | No permission to remove or restore those files |

**At document creation the new art, exporters, loader, tests and renderer changes are still local, uncommitted work. This documentation-only commit does not publish them.** S00 must preserve and publish that coherent prototype before another machine or AI can rely on it. Do not mark S00 complete because this roadmap is pushed.

Read `art/blender/README.md` critically: its initial battleship-only notes predate the material fix and later owner approval. Reconcile those notes in S00 rather than treating their old “not approved” wording as the latest decision.

Catalogue data currently contains 37 ship definitions (Imperial 10, Alliance/rebel 10, Confederacy 10, Syndicate 7), 16 station definitions and four faction records. Syndicate is currently non-playable. **These are data-entry counts, not a complete mesh workload.** Shared types, faction-specific station variants, squadrons, transports, planet hardware, previews and campaign props require a rendered-model inventory. Do not multiply these counts and invent a final asset total.

## 3. Scope and invariants

### 3.1 What “all models” means

S01 inventories every rendered 3D asset and every dispatch path: ships including squadron members and logistics, faction station variants, construction sites, satellites, planet installations, neutral/environment objects and campaign-only objects. Reused assets must have explicit bindings; a shared source is acceptable only when the owner approves that reuse. Non-playable factions are not silently dropped or made playable.

Every inventory row must end in an approved Blender asset/binding or an **explicit owner-approved exception**. Procedural planets, terrain, sky backgrounds, particles and screen-space effects need a recorded scope decision if they are not discrete model replacements. No agent may silently interpret “all models” as only the three specimen assets or only combat ships. Pure effects are not automatically a new mesh assignment.

### 3.2 Constraints

- Original designs only; no copied proprietary models or unapproved purchases. Record provenance and licensing for dependencies, textures and source assets.
- Keep `rebel`, `imperial`, etc. canonical identifiers even when display names differ. Art names must not rename gameplay definitions or break old saves.
- Rendering reads state; it does not mutate simulation, collision radii, weapon ranges, build rules, health, ownership, replay data or checksum semantics.
- Visual sockets are presentation metadata, not authority for gameplay firing positions. Any gameplay socket change is a separate, explicit design task.
- Preserve fog/contact visibility, ownership cues, catalogue scale, selection/picking, camera keep-outs, shields, hit contacts and construction previews.
- Preserve existing quality, including normal fog, material passes and baseline MSAA. Do not buy speed by silently removing geometry or effects.
- No direct commits to `main`, stash/reset/checkout of somebody else's work, automatic merge, tag or release. Stage explicit files only after reading status.
- Keep saved games, settings, campaign progress, balances and user replays untouched. Never “clean up” user data to make a test pass.
- No runtime Blender or `bpy` dependency. The game consumes validated exported data only.

## 4. Git storage and source-of-truth policy

Retain and generalize the existing separation instead of moving files merely for tidiness:

```text
art/blender/<faction>/<asset_id>/
    model.blend                 # editable source, checked in
    SOURCE.md                   # authoring authority, Blender version, provenance
    approval.md                 # owner decision bound to the reviewed revision
    review/                     # selected durable close/rear/tactical evidence
assets/models/
    registry.json               # proposed built-in visual bindings
    <namespace>/<asset_id>/
        manifest.json           # versioned metadata and runtime content hashes
        lod0.mesh.json          # evaluated export; additional LODs when required
        ...                     # approved textures/LODs, never authoring tools
art/manifests/
    model_inventory.json        # machine-readable catalogue and completion ledger
    approvals.json              # references to explicit owner decisions
    handoffs/                   # durable per-step completion/blocker records
    reviews/                    # batch contact sheets and capture recipes
    budgets.json                # agreed class/LOD/runtime budgets
    decisions.md                # architectural decisions and open questions
    release-asset-lock.json     # exact pack/model revisions for final rollout
    legacy-bindings.json        # rollback mapping, retained through cutover
    schemas/                    # asset/registry/mod schemas and examples
    ...
tools/art/
    ...                         # reproducible build/export/validation tools
mods/example_model_pack/
    mod.json                    # proposed visual-pack extension, not working yet
    models/                     # data-only exported replacements and manifests
```

This is the **target layout**, not a claim these files already exist. Existing flat trio paths may remain during S00; S03 moves them only with reference updates, hash verification and tests. Avoid duplicate authoritative copies.

Rules:

1. Commit `.blend`, exporter/tool changes, runtime exports, manifests and necessary textures together for a model revision. A local path or ephemeral scratch folder is not a deliverable.
2. Each asset declares either **script-authoritative** (rebuild scene then export) or **blend-authoritative** (edit `.blend`, export its evaluated scene). An exporter must not overwrite hand-edited work by accident. Both paths produce a stored `.blend` and reviewed runtime data.
3. Record exporter version, Blender version, coordinate/scale policy, source and runtime hashes. Rebuild the runtime export twice; require byte-identical output for the same declared inputs/toolchain. Binary `.blend` metadata need not rebuild byte-identically.
4. Exclude `.blend1`, temporary renders, autosaves and giant raw capture runs. Keep selected review evidence and reproducible capture recipes in Git. Preserve unrelated existing artifacts.
5. Review repository growth before large batches. Use ordinary Git for current small sources; decide and document a Git LFS threshold/policy in S03 before large textures or models land. If LFS is adopted, configure attributes, CI/build fetching and a fresh-clone check together. A pointer without fetched content is not a valid asset delivery.
6. Do not package editable `.blend` sources or authoring tools into the game. Runtime exports and manifests are packaged; authoring sources remain accessible in Git.

## 5. Target runtime and mod contract

S02 must finalize this design before catalogue-wide integration. The existing three hardcoded profiles are a prototype to migrate, not the permanent extension API.

### 5.1 Stable identity and versioned data

- Distinguish gameplay entity ID, stable namespaced visual asset ID (for example `core:alliance/frigate`), asset revision/content hash, file-format schema version, exporter version and material-profile version.
- Store bindings in a registry keyed by canonical gameplay/faction/variant identity, not translated display names or arbitrary filename conventions. Station faction and convoy/squadron identity must be explicit.
- A versioned model manifest declares mesh/LOD files, hashes, coordinates/pivot, bounds, nominal scale, allowed material profile/roles, optional presentation sockets, provenance and required engine/schema compatibility.
- Keep the current six role names (`base`, `dark`, `trim`, `accent`, `lit`, `cool`) as the initial compatibility target. New roles/material features require versioned support and fallbacks; do not treat arbitrary shader code as model metadata.
- Preserve current catalogue world-size policy. Visual replacements may not change collision/gameplay size. Define and validate conservative visual envelopes for camera, picking, contacts and shields.
- Bind approval to the `.blend`, exported runtime files, material profile and relevant exporter revision. A meaningful visual change invalidates the affected approval until reviewed again; a filename alone does not carry approval.

### 5.2 Model resolution, updates and mods

- Default built-in lookup: entity binding -> core asset manifest -> validated immutable mesh/LOD/material description. No new per-model `if` branch in the renderer.
- Proposed visual-only mod order: explicitly enabled visual packs in a persisted, documented order, then built-in binding. Later enabled override wins; duplicate IDs within a pack are errors. Show effective origin and conflicts in diagnostics. No implicit filesystem-enumeration precedence.
- Distinguish “replace a core binding” from “add a namespaced model for a mod entity.” Unknown gameplay entities still require a compatible gameplay mod; a model pack does not create units or make factions playable.
- Extend the existing `mods/<name>` mechanism deliberately. `DataStore._load_mod` currently overlays gameplay data and records raw text; it is **not** a complete model resolver and must not import render/GL code into simulation.
- Separate visual pack selection from gameplay-mod selection. Pure visual packs stay outside authoritative state, gameplay compatibility hashes and lockstep checksums; gameplay-affecting packs retain existing compatibility rules. Prove identical simulation with different visual packs on peers.
- Cache by resolved pack/content revision and material/LOD profile, not just entity type or path. Scope GPU resources to the GL context. Switching packs between sessions invalidates CPU/GPU caches and bounds/contact helpers coherently; release resources on context teardown.
- Initial scope: apply updates at a safe menu/session boundary. Live in-battle hot reload, mod downloads/workshop and executable mod scripting are out of scope unless separately approved.
- Validate packs transactionally before activation. Reject incompatible schema, oversized resources, NaN/invalid triangles, path traversal, absolute paths and symlink escape from the allowed pack root. Bound decoded texture memory as well as file size. No `eval`, pickle, Python imports, `.blend` execution or arbitrary shaders from packs.
- A broken optional mod falls back to the next valid source with a clear diagnostic, never a crash or partial activation. Missing/invalid **required built-in** exports fail validation/packaging. Retain a visible runtime recovery fallback for corruption; never use it to claim catalogue coverage.
- Preserve old saves/replays by resolving their existing entity IDs through the current registry. Store optional visual-pack diagnostics separately; never make a cosmetic upgrade a save migration requirement.

### 5.3 Export and render requirements

- Export evaluated Blender geometry after modifiers; triangulate, transform normals correctly and validate winding, finite positions, nondegenerate faces, indices and bounds.
- Use consistent X beam / Y up / +Z forward and declared pivot/scale. Document conversion if artist-facing Blender axes differ.
- Set class-specific triangle, memory, draw-call and texture budgets from measurements. Existing specimen counts are references, not automatic universal budgets. Preserve essential silhouette in every supported LOD.
- Integrate the same resolved model in gameplay, menus, previews, construction stages, picking, camera bounds, contact VFX and shields. Avoid separate hidden dispatch paths retaining old geometry.
- Test source and frozen builds. `star_armada.spec` currently bundles `assets`; explicitly verify asset discovery under `sys._MEIPASS` instead of assuming a source-tree-relative loader works in a package. Writable mod roots must be outside the signed/read-only app bundle, with explicit platform paths.

## 6. Execution steps and dependency gates

Each step is a reviewable task/PR with a durable handoff. “Complete” requires its stated outputs and checks, not an agent's intention. Do not run all steps in one chat. Approval gates cannot be satisfied by another AI.

| Step | Work package | Depends on | Completion gate |
|---|---|---|---|
| S00 | Preserve and publish approved prototype | This roadmap | Coherent tracked sources/exports/evidence and exact Git/PR receipt |
| S01 | Inventory every model and approve scope | S00 | Owner-reviewed coverage matrix; no silently omitted dispatch paths |
| S02 | Specify asset, registry and mod contracts | S01 | Reviewed versioned schemas, examples, resolver/fallback/compatibility decisions |
| S03 | Standardize Git authoring/export tools | S02 | Reproducible trio builds from a fresh clone, source ownership and storage policy |
| S04 | Implement generic opt-in model integration | S02, S03 | Registry/pack resolver, source/frozen loading, lifecycle and mod replacement tests |
| S05 | Revalidate the trio on the generic path | S04 | Same approved appearance in-game, parity and durable owner-bound approval records |
| S06 | Author and approve remaining model batches | S01, S03; preview via S04 | Every in-scope asset/binding approved and tracked; exceptions explicitly signed off |
| S07 | Complete catalogue integration and LOD/contact behavior | S05, S06 | All render paths use opt-in registry consistently; no unexplained legacy usage |
| S08 | Validate visual mods and asset-update compatibility | S07 | Replacement/example packs, safe failure, revision/caches and save/replay tests |
| S09 | Performance, package and platform acceptance | S07, S08 | Measured complete candidate; source/frozen packages and required test gates pass |
| S10 | Final owner catalogue review and cutover readiness | S09 | Exact release asset lock approved, coverage complete, rollback rehearsed |
| S11 | **Switch the game default to Blender models** | S10 + explicit switch authorization | Clean-install and upgraded-install verification; legacy recovery retained, PR verified |

S06 may author batches while S04 is built, but only with disjoint files/ownership and an agreed S02/S03 contract. Never run heavy Blender/GL/profile/full-suite jobs concurrently. Catalogue expansion is now planned, not blanket approval of model designs.

### S00 — Publish the approved prototype without losing work

- Inventory current status and copy/hash the local prototype before edits. Separate third render optimization work from asset/material work; do not accidentally stage all unrelated changes.
- Retain all three approved sources, build scripts, runtime meshes, material-state fixes, loader, focused tests and selected comparison evidence. Inspect dependencies before splitting commits so no committed facade imports an untracked module.
- Record the actual owner approvals and exact shown revisions in durable approval records, including references to the reviewed captures. Direction approval is not a claim of complete engineering acceptance.
- Update the stale battleship README and clearly label known acceptance debt. Keep original failed logs; user-created replays are not test pollution.
- Commit a coherent preview prototype on a feature branch/PR, verify remote file hashes and provide its exact head to the next chat. Do not mark existing local activation as final catalogue switchover. If the preview is currently on by hardcoded dispatch, S04 must restore an explicit gated path before broader rollout.

### S01 — Inventory and batch design

- Generate inventory from both data and renderer dispatch. Include shared aliases, faction/owner combinations, campaign-only uses, transports, squadron members, satellites/planet installations, environment props and legacy fallbacks.
- For every row record: canonical binding, display label, faction/category, current generator/source, target asset ID, shared-source relationship, expected scale/envelope, previews/VFX/sockets, model owner and status.
- Ask the owner to settle scope exceptions, faction identities/reuse and batch priority. Preserve non-playable status. Recommended first batches: remaining Alliance combat hulls, Alliance support/civilian hulls and stations/planet hardware, then owner-selected faction batches and shared/environment assets.
- Group a few related models per review. No requirement to finish an entire faction before the owner sees progress.

### S02 — Freeze the extension contract

- Write schemas and minimal core/replacement/additive-pack examples for section 5. Record design choices in `art/manifests/decisions.md`.
- Define migration from the specimen schema/profile loader, immutable resource interfaces and schema upgrade policy. Unknown major schemas fail clearly; do not silently reinterpret exports.
- Define failure diagnostics, pack ordering/root locations, security bounds, approval invalidation, render-only compatibility policy and cache/resource invalidation.
- Agree class budgets and LOD expectations initially; revise only with measured evidence and owner approval when visual quality changes.

### S03 — Build a durable authoring pipeline

- Generalize evaluated export and validation without destroying hand edits. Add an export-only path for blend-authoritative assets; declare source authority per asset.
- Adopt the section 4 layout with safe path migration. Record toolchain versions; make build/export instructions work on Mac and Windows without hardcoded user directories.
- Provide commands for one asset, a batch and validation-only, with nonzero failure exits and no user-data writes. Names below are proposed interfaces, not existing commands: `build-model`, `export-model`, `validate-models`.
- Test repeated byte-exact runtime exports, fresh-clone completeness, provenance and Git/LFS storage policy. Avoid requiring Blender for ordinary gameplay tests; use a dedicated asset-rebuild job/environment.

### S04 — Generic preview integration

- Implement registry, bounded manifest/mesh loading and render-only mod resolution outside authoritative simulation. Keep approved specimen rendering as a control.
- Add an explicit persisted preview/default selection boundary; stock production behavior remains legacy until S11. Preview activation must be visible in diagnostics and not change saves.
- Resolve size/contact/material/LOD once per asset revision where safe; keep entity transforms and current visibility live. Provide missing/corrupt built-in and optional-pack behavior separately.
- Test selection changes, context teardown/recreation, bounded caches and source/frozen path discovery. Include one replacement mod and one new namespaced asset for an existing mod entity fixture.

### S05 — Transfer trio approvals to the generic pipeline

- Run identical cameras/quality through the specimen control and generic path. Recheck close, rear, tactical, owner colors and motion/combat, with state hashes and normal fog.
- Verify Blender source/runtime files and authored material appearance match the approved captures. Recheck four individual shipyard worklights and recessed drive emitters; an “any emissive triangle exists” test is insufficient.
- If unchanged, record engineering equivalence to the approved revision. If appearance changes, show the owner the change and obtain explicit renewed approval. Do not substitute another AI's visual judgement.

### S06 — Produce, show and approve every remaining batch

For **each** batch:

1. Select inventory rows, lock file ownership and record the baseline commit/asset hashes.
2. Build original Blender models with functional silhouettes, clean armor/machinery separation, owner accents, readable glazing/drives and distinct faction language. Share tooling, not identical hulls with different paint.
3. Export/validate and integrate only in preview. Keep core silhouettes in LODs; retain gameplay and scale contracts.
4. Show before/after actual-game close and tactical images plus motion where geometry/emission/animation warrants it. Use identical union-safe cameras and quality, not Blender beauty shots as proof of game integration. Label individually framed shots as not scale comparisons; include a common-scale view.
5. Run focused geometry/material/contact/visibility/determinism tests. Verify all unselected assets and already approved assets remain unchanged or obtain explicit review for any change.
6. Obtain explicit owner acceptance of every listed asset/revision. Rejected/pending models stay pending. Batch approval is valid only with an enumerated asset list, not “the rest of the faction.”
7. Commit source, runtime data, manifests, tests, selected evidence and approval record together; push and verify the remote. Update inventory and handoff. Never make another chat depend on a scratch path.

Every meaningful improved/replaced model revision repeats the relevant export, capture and approval gate, including revisions after the eventual rollout.

### S07 — Close integration gaps

- Validate all inventory bindings across gameplay, main-menu cinematics, build icons/previews where 3D is used, construction, squadron/member rendering, convoys, satellites, campaign encounters, fog/contact remapping, picking and VFX.
- Exercise all LOD transitions, near/far views, bounds under rotation and faction/owner remaps. Keep collision and simulation fields unchanged.
- Generate a completeness report with zero missing required built-ins, no unapproved bindings and no unintended procedural fallback hits. Approved shared-source rows count explicitly, not as missing unique files.
- Keep registry-backed preview and legacy default independently testable. Do not remove the rollback path.

### S08 — Prove model replacement and mod compatibility

- Ship documented example visual packs: replace one core model and add a namespaced asset bound by an existing test gameplay mod. Explain installation, pack order, updates, disabling and diagnostics.
- Test duplicate/conflicting IDs, disabled/missing/corrupt/incompatible packs, oversized payloads, traversal/symlink attacks, invalid bounds, missing textures/LODs and partial update rollback.
- Test asset revision replacement between sessions and confirm old CPU/GL resources and contact/bounds caches cannot survive incorrectly. No forced live-match hot reload.
- Load old saves/replays before/after a cosmetic replacement; compare authoritative state and outcomes. Run peers with different visual packs and identical gameplay configuration, proving equal simulation/checksums without requiring identical cosmetic files.
- Preserve the distinction between a visual-only mod and a gameplay-changing mod; do not relax existing gameplay compatibility to make a visual test pass.

### S09 — Broad acceptance, packages and measurable cost

- Run focused checks per batch; now run the protected complete suite on the immutable integrated candidate. Classify every failure with an actually executed pristine control, retain failed attempts and never weaken assertions to obtain green.
- Use native descendant write barriers, disposable fixture paths, before/after inventories and preservation canaries. Concurrent user play can add legitimate files; record that fact rather than deleting them or blaming the suite. Avoid competing heavy workloads.
- Measure complete catalogue rendering/memory/load cost and LOD on both representative stock-queueable and approved stress fixtures from `GRAPHICS_BENCHMARK.md`. Preserve quality and workload inputs. Report CPU/GPU/render versus simulation/checksum costs separately; diagnostic frame cost is not interactive FPS.
- Confirm performance targets/resolutions with the owner rather than adopting previously proposed numbers as approved. Investigate bounded regressions; no open-ended optimization detour.
- Build Mac and Windows packages from the exact candidate, verify manifests/content hashes inside them, and run clean-install and existing-user-data smoke tests without Blender or a source checkout. Ensure authoring sources are not accidentally shipped.
- Verify native rendering, colors/roles, fog, LOD, asset lookup, read-only bundle behavior and external writable mod roots. Headless Windows CI does not prove native graphics.
- Filip's laptop/physical mixed-machine testing remains deferred unless explicitly reauthorized. Record any outstanding platform gate as a blocker or owner-accepted waiver; do not silently call it passed.

### S10 — Owner sign-off and rollback rehearsal

- Present a durable catalogue gallery, batch approvals, common-scale fleet/station views and normal gameplay footage. List any shared-source/environment exceptions and remaining platform/performance limitations.
- Produce `release-asset-lock.json` mapping every required binding to approved model/export/material revisions and hashes. Validate it against inventory and approval records.
- Rehearse returning to legacy via the preview/default selector without changing saves, balance, replays or installed mods. Keep old bindings and recovery diagnostics.
- Obtain explicit owner authorization to change the default for this exact asset lock. Appearance approval alone does not authorize merge/release or waive failed engineering gates.

### S11 — Final switch from legacy to Blender models

- Change the default to the locked, fully approved Blender registry in one small, reversible feature PR. Do not combine it with new artistic revisions, unrelated optimization or legacy code deletion.
- Verify fresh installs, upgrades with old settings/saves/replays, disabled/installed visual mods and frozen Mac/Windows packages. Existing preview preferences must migrate explicitly; missing assets must never quietly produce a mixed catalogue labelled complete.
- Recheck visibility, picking/contact/scale behavior, representative fleet cost, asset completeness, focused regressions and required CI on the exact final commit. Read back remote files/head and PR checks.
- Document legacy recovery and rollback, effective asset/pack diagnostics and known accepted exceptions. Keep legacy fallback for at least the initial Blender rollout; deletion is a separate later proposal, not part of this switch.
- Hand back the verified PR and package/evidence receipts. **Merge, tag and release require separate explicit owner authorization.** The final milestone is complete only when the default switch is actually delivered and verified, not when models merely exist in Git.

## 7. Cross-chat execution and handoff protocol

### Start of every chat

1. Read this roadmap, `ARCHITECTURE.md`, the latest `art/manifests/handoffs/` entry, inventory, decisions and affected asset approval records. Fetch/read the referenced branch/PR; do not assume `main` contains local work from another chat.
2. Inspect actual Git status, branch, commit, staged files and prerequisite step state. If required sources exist only on another machine, stop and retrieve the committed handoff; never reconstruct plausible replacements silently.
3. Select exactly one step or named small S06 batch. State owned files, baseline hashes, expected visible output and acceptance checks. Never infer permission for catalogue-wide changes, deferred hardware, merges or releases.
4. Protect existing work by copy/hash, not stash/reset. Multiple agents need disjoint file ownership; one owner controls Blender/GL/test/profile compute. Shared dispatch/renderer changes must be serialized.

### Required handoff record

Write `art/manifests/handoffs/<step-or-batch>.md` in the implementation PR, using this template:

```markdown
# Handoff: <Sxx / batch ID>
Status: not-started | in-progress | blocked | review-ready | complete
Base commit / branch:
PR and exact pushed head:
Prerequisites verified:
Owned files and assets/bindings:
Source authority / Blender / exporter / schema versions:
Changed source and runtime hashes / asset-lock revision:
What changed visibly:
Owner approval: exact enumerated assets/revisions, decision, evidence reference
Tests and commands actually executed, counts and retained failed attempts:
Actual-game captures/video: repository-relative durable paths and recipe
Performance / packaging / platform evidence and limitations:
User-data preservation and unrelated work retained:
Open issues, blockers and decisions required:
Next executable step and its acceptance criteria:
```

Distinguish `review-ready` from `complete`. Approval must be attributable to the owner and bound to the shown revision. Do not manufacture approval timestamps or quote nonexistent owner decisions. If an AI stops mid-step, write `in-progress`/`blocked`, preserve artifacts and name the exact unfinished work.

### Completion checklist for each implementation PR

- [ ] Prerequisite gates and selected scope verified.
- [ ] All necessary source/runtime files tracked; fresh clone is sufficient.
- [ ] No unrelated files, user data or credentials staged.
- [ ] Required visible evidence inspected and owner approval recorded where required.
- [ ] Focused checks run; broader checks only when required by the milestone.
- [ ] Inventory, approvals, manifests and handoff updated together.
- [ ] Commit pushed; remote head/file hashes read back; current CI status reported honestly.
- [ ] No unrequested merge/tag/release or silent production-default switch.

## 8. Progress ledger and next task

This table is the initial planning state, **not implementation completion**. Future agents update it only with committed evidence and prerequisite/approval receipts.

| Step | Initial status | Next action / blocking condition |
|---|---|---|
| S00 | Not started; local approved prototype exists | Publish a coherent prototype with all source/export dependencies and owner-bound evidence |
| S01 | Not started | Inventory data plus every renderer/model dispatch and agree scope |
| S02 | Not started | Decide and specify generic asset/mod contracts |
| S03 | Not started | Standardize source authority, storage and reproducible exports |
| S04 | Not started | Generic gated integration, resolver and frozen-path support |
| S05 | Not started | Transfer approved trio through the generic path |
| S06 | Not started beyond the locally approved trio | Named small batches; explicit owner approval for every model |
| S07 | Not started | Complete catalogue render-path integration |
| S08 | Not started | Prove replacement packs, updates and cosmetic compatibility |
| S09 | Not started | Integrated suite/performance/package/platform gates |
| S10 | Not started | Final owner asset lock and switch authorization |
| S11 | Not started | Last step only: verified, reversible default switch |

**Next chat task: S00, not a new model batch and not S11.** Read the dirty working tree and approved trio evidence, publish the coherent sources without bundling unrelated work, and write the first durable handoff. The roadmap commit alone must remain documentation-only.
