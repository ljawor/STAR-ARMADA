# STAR ARMADA — Blender model migration roadmap

> **Delivered 2026-10-19, engine `0.16.0`.** S00–S11 are complete: every required binding is
> authored, approved and pinned in `art/manifests/release-asset-lock.json`, and the shipped
> default is that catalogue (decision `s11-default-switch-2026-10-19`). The 60/30 FPS reference
> is **not met** and is carried into a separate performance engagement; native Windows graphics
> and package smoke remain waived. Read §6 for the ledger and §2.1 for the evidence.

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

### 2.1 Delivery checkpoints — verified through S07 merge, October 19, 2026

The observations and local-only warning above are the **historical document-creation baseline**, not the
current storage status.

**Performance — done and on `main`.** PR #113 landed as the single squashed commit
`16523bf0b06a39e3f77961d0c213b0af184a16b6`, whose tree is identical to the tested head
`a24a4ed32f0cec6c76b40c30640a61bee6f60a2b`. All three performance passes are integrated and the version
is `0.15.1`. The protected whole suite ran 1,668 tests with zero failures/errors and nine documented
skips against an immutable performance-only archive, and the exact-head Windows CI run `38858140567`
passed. No tag or release was created.

**Art — S00 preserved, published and merged into `main`.** Draft PR #114 was marked ready and merged by
the owner on 2026-10-16 as the single squashed commit `c5b78eb2d4ceba909ffb7444a56b7dec1f35d1b4`
(96 files), after its branch was reconciled with `main` — branch delta art-only, the merged draw-scope
performance code intact — and its published blobs were re-read and verified byte-for-byte. Earlier heads
`313f9683e9e7e4f376b05cedaeb28bb2dd300c9f` and `0f6531f4d14f649cbfed744c29b61b4537b0f5e8` remain in that
branch's history: the reconciliation was a merge, not a rewrite. `main` therefore now contains the trio's
Blender sources, exporters, runtime exports, loader, material integration, focused tests, owner-bound
approval records and selected evidence. Durable record: `art/manifests/handoffs/S00-PRESERVATION.md`;
machine-readable decision: `art/manifests/approvals.json`.

**The explicit activation boundary is implemented and merged.** S04 PR #124 (`7030dd2`) replaced
the trio's hardcoded activation with the generic registry and a persisted opt-in preview boundary.
The stock default is legacy; S11 remains unauthorized. New model revisions must use the generic
path after approval, not new identity checks. Pending S06 designs remain review-only.

**S01 is complete** in PR #115: `art/manifests/model_inventory.json` (120 bindings, references
resolved at its historical audit base), `art/manifests/inventory_audit.json` (dispatch audit plus the owner scope
decision), `art/manifests/reviews/S01-coverage-matrix.md` and `art/manifests/handoffs/S01-INVENTORY.md`.
The owner answered all four scope questions on 2026-10-16 (`s01-scope-2026-10-16`): the planet bodies,
asteroid props and menu backdrop come **into** the catalogue, the three declared-but-unreachable mesh
keys become planned hulls (battleships and capital ships at the shipyard, bombers at the fighter
platform), and the five authoring batches are approved in the recommended order. That is scope and plan
approval only: no individual model design is approved, and the broader catalogue default is still
unswitched. S02–S07 have since closed and merged (below); S08–S10 remain open. **S11 is not done or authorized.** No
release or tag is part of any of these deliveries.

**S02 is complete and merged, and still implements nothing in the game.** `docs/ASSET_EXTENSION_CONTRACT.md`
with `art/schemas/` defines three versioned documents — model manifest, binding registry and
render-only visual pack — migrates the three approved assets into specimen manifests, and ships
`tools/art/validate_contract.py`, green on **36 checks and 28 negative controls**, so every rejection
rule is exercised rather than asserted. The owner answered the four questions this step left open on
2026-10-16 and each answer is now an enforced rule with a control of its own: real class budgets sized
below the loader's hard cap (capital 11,888 / escort 8,000 / station 11,500, with 12,000 kept as the
loader's hard failure), an extent gate of 1 % of an axis or two units, whichever is smaller
(`E_EXTENT_DRIFT`, D-19), `E_MEASUREMENT_STALE` so a declared triangle budget below its own mesh is a
failure rather than a comment, the legacy `"schema": 1` window open until the S11 cutover (D-07), and the
pack examples recorded as illustration rather than acceptance material. S04 has since implemented
the resolver this contract specifies, and S05 has revalidated the approved trio through it.

**S03 is complete and merged: the authoring pipeline exists, with its acceptance frozen before it was
built.** `art/manifests/pipeline_policy.json` (`s03-pipeline-policy-2026-10-16`) fixes ordinary Git with a
declared 5 MiB per-file LFS threshold, blend-authoritative as the default for silhouette work and
script-authoritative for repeated or modular pieces, and rebuilds from a fresh clone on macOS and Windows.
`tools/art/model_pipeline.py` and the `build-model` / `export-model` / `validate-models` forwarders then
implement it: a rebuild is compared against the approved byte record instead of trusted, export-only is
enforced by scanning the script rather than intended, a script-authoritative generator runs inside a
throwaway copy of the tree, and `validate-models` fails when the S02 contract validator is absent instead
of passing on its own weaker checks. The owner's own half of that acceptance (D5) is a byte-identical
in-game frame set against the committed reference (`s03-d5-2026-10-16`), so a visible change to the
approved trio would have been a failure of that step, not a feature of it. `validate-models --all` is now
green **34/34** on `main`, contract validator included. **One half stays open: no Windows machine has ever
run this pipeline** (D3), which is an S09 gate, not an S03 receipt.

**The trio's hull surface detail has since been authored and approved, one revision per binding.**
`rebel:battleship` (PR #120 → `47b0161`) and `rebel:frigate` + `rebel:shipyard` (PR #121 → `047c380`), with
the record correction in PR #122 → `96cd92e`. Detail is placed from the frame it sits on, costs
11,457 / 7,708 / 10,767 triangles, and changes no silhouette, no catalogue length and no simulation
field — the battleship's beam moved 69.0 → 73.349998 to cover flank detail standing proud of the widest
section, which is exactly why the contract now carries an extent gate. The guard raise that made the pass
possible is an owner decision, not a quiet edit (`s07-detail-budget-2026-10-16`: exporter ceiling 11,888
triangles / 9,500 vertices), and every revision is bound in `art/manifests/approvals.json` to the exact
`.blend`, builder and runtime bytes the owner approved. This is S06 work taken early on the three
specimens; the remaining bindings keep their inventory status and are not covered by it.

**S06 — catalogue closed for this milestone and merged into `main`.** PR #127 → `cdb1d53` and
PR #130 → `ab62d6d` landed the remaining batch specimens, and `main` now registers **103 of the 119
registry bindings** as authored and approved: 98 bindings under **eleven** `s06-b*` batch decisions
(B1–B9, with B3
split into 3a/3b/3c), and five rows approved outside those batches (the original hull trio,
`rebel:shipyard`, and the construction scaffold under `s07-scaffold-appearance-2026-10-18`). The
other sixteen rows are covered by an explicit owner exception rather than left
unaccounted: `s07-s06-coverage-exception-2026-10-19` records 12 `authoring_pending` bindings (eight
planet environments, `menu:cinematic_backdrop`, and the three Syndicate hulls) and 4
`keep_procedural_proposed` rows (sky dome, jump point, nebula, star). Every registered asset is
asserted to carry an approval decision, and the exception may not widen: the receipt refuses to
build unless it enumerates exactly the registry's non-core rows.

**S07 — integration complete and merged into `main`.** PR #129 → `4ab1472` carried the coverage
reconciliation and the bounded S07 plan; PR #131 → `d427f66` carried the opt-in integration: the
construction scaffold
registered as the 103rd asset, the motion/ownership repair of `_draw_ships`, `_draw_ship`,
`_draw_ship_role_batch` and `_draw_station` (renderer `9aff3414`), the B5 pin record refreshed to
those bytes, and `artifacts/s07-runtime-final/S07-FINAL-RECEIPT.json` — **15 criteria, overall
pass**, bound to 870 re-captured native frames, a 360-frame rebuilt movie, one independent
byte-bound review and a per-module suite gate of 205 modules / 2,245 tests. One failure is carried
as recorded pre-existing: `test_crew_recovery_ui` expects the legacy box shape where the tree
returns `imperial:convoy`, contradicting `s06-imperial-convoy-parity-2026-10-18`, and it fails
identically on the pre-merge base commit.

The five PRs were merged bottom-up with merge commits, not squashes, so each stacked PR kept its
merge-base and its evidence-bound hashes. **The default is still legacy**, packaging remains
skipped and not accepted, native Windows graphics remain unproven, and S11 remains unauthorized:
registration is not activation.

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

S02 froze this contract, and S04 implemented generic preview resolution. Catalogue-wide integration
continues through the versioned registry; the original hardcoded specimen profiles are not the extension API.

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
| S01 | Inventory every model and approve scope | S00 | **Complete** 2026-10-16: owner-reviewed coverage matrix (`s01-scope-2026-10-16`); no silently omitted dispatch paths |
| S02 | Specify asset, registry and mod contracts | S01 | **Complete** 2026-10-16: contract validator with 36 checks and 28 negative controls, the owner's four answers implemented as rules (PR #117 → `b2b6b75c4f7d90b99e943bf74b79b811c09e3785`) |
| S03 | Standardize Git authoring/export tools | S02 | **Complete** 2026-10-16: policies frozen before implementation (PR #118 → `fd08ac7`), pipeline green 34/34 from a fresh clone (PR #119 → `b5414b5`); D3's Windows half unproven |
| S04 | Implement generic opt-in model integration | S02, S03 | **Complete and merged**, PR #124 → `7030dd2`; tested head/tree preserved, Windows CI passed |
| S05 | Revalidate the trio on the generic path | S04 | **Complete and merged**, PR #125 → `f873a33`; two exact current matrices, owner-authorized repeat policy, retained historical limitation |
| S06 | Author and approve remaining model batches | S01, S03; preview via S04 | **Closed for this milestone**: 103 of 119 registry bindings authored and approved — 98 under eleven `s06-b*` batch decisions, five approved outside them — merged in PR #127 → `cdb1d53` and #130 → `ab62d6d`; the remaining 16 rows are covered by the explicit exception `s07-s06-coverage-exception-2026-10-19` (12 `authoring_pending`, 4 `keep_procedural_proposed`) |
| S07 | Complete catalogue integration and LOD/contact behavior | S05, S06 | **Complete and merged**, PR #129 → `4ab1472` and #131 → `d427f66`: every registered path resolves through the opt-in registry, renderer `9aff3414`, `S07-FINAL-RECEIPT.json` 15/15 criteria; legacy default retained |
| S08 | Validate visual mods and asset-update compatibility | S07 | Replacement/example packs, safe failure, revision/caches and save/replay tests |
| S09 | Performance, package and platform acceptance | S07, S08 | **Merged**, PR #136 → `62f11d0`; the measured cost is recorded and the accepted 60/30 FPS reference is **not met** (`s09-performance-target-2026-10-19`); the frozen authored package crashed on its own symlinked assets, fixed by PR #137 → `2f74430`; native Windows graphics and package smoke waived (`s09-platform-waiver-2026-10-19`) |
| S10 | Final owner catalogue review and cutover readiness | S09 | **Complete** with the switch: `art/manifests/release-asset-lock.json` pins 103 required bindings / 21,126,346 payload bytes with hashes checked against disk; rollback rehearsed in `RollbackRehearsalTests` and in the frozen legacy run; owner sign-off `s11-default-switch-2026-10-19` |
| S11 | **Switch the game default to Blender models** | S10 + explicit switch authorization | **Delivered in PR #138** (pending merge): default is the approved catalogue at engine `0.16.0`; fresh, pre-switch-upgrade and explicit-legacy frozen smokes pass (upgrade effectively identical to fresh at 0.055 %, authored vs legacy 2.774 %); legacy fallback retained and documented |


**The migration is closed as of engine `0.16.0`.** Every required binding is authored, approved and
locked; the shipped default is that catalogue; returning to legacy is a settings change. What this
does **not** claim, and what the next engagement owns:

- **Performance.** The authored catalogue costs 4.5–6.2× the legacy frame time (188.22 ms stock
  distributed, 292.73 ms stock combat at 1280×800 / 4× MSAA), so the 60 FPS reference S09 adopted is
  unmet; legacy itself is 2.5–3.4× over the 60 FPS budget. Measurement and optimisation are a
  separate stream by the owner's decision `s11-default-switch-2026-10-19`.
- **Windows platform evidence.** Still covered only by the scoped waiver.
- **Cosmetic label.** The settings row still reads "preview"; correcting it is a language-pack
  revision, not part of the switch.
- **Two pre-existing test-fixture defects** and **two unrun pristine-checkout controls** remain
  recorded as debt, not as passes.
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

#### S02 completion

Merged 2026-10-16 as `b2b6b75c4f7d90b99e943bf74b79b811c09e3785` (PR #117). The owner answered the four
questions this step left open, and each answer is enforced by a rule with its own negative control, so
the contract now runs **36 checks over 28 negative controls**: class budgets sized below the loader's hard
cap and recorded per asset in `art/manifests/pipeline.json` with the decision named in its `budget_policy`;
an extent gate (`E_EXTENT_DRIFT`) where the approved extent is named by the binding itself
(`envelope_decision`) and the re-pin tool refuses to widen it past the grace without `--accept-extent`;
`E_MEASUREMENT_STALE`, which makes a declared budget below its own mesh a failure; the D-07 legacy window
left open until S11; and the pack examples recorded as illustration. Decisions are numbered D-01…D-20 in
`art/manifests/decisions.md`. Three questions remained at S02 completion; D-21 subsequently answered
pack-envelope rechecking, leaving two unrelated owner questions open. S02 itself was specification
work; S04 and S05 subsequently delivered resolution and trio equivalence.

### S03 — Build a durable authoring pipeline

- Generalize evaluated export and validation without destroying hand edits. Add an export-only path for blend-authoritative assets; declare source authority per asset.
- Adopt the section 4 layout with safe path migration. Record toolchain versions; make build/export instructions work on Mac and Windows without hardcoded user directories.
- Provide commands for one asset, a batch and validation-only, with nonzero failure exits and no user-data writes. Names below are proposed interfaces, not existing commands: `build-model`, `export-model`, `validate-models`.
- Test repeated byte-exact runtime exports, fresh-clone completeness, provenance and Git/LFS storage policy. Avoid requiring Blender for ordinary gameplay tests; use a dedicated asset-rebuild job/environment.

#### S03 acceptance — frozen by the owner before implementation

Decision record: `s03-pipeline-policy-2026-10-16` in `art/manifests/pipeline_policy.json` (owner's
wording verbatim). The owner adopted all three proposed policies and the definition of done, so this
step is reviewed against agreed criteria rather than against whatever gets built.

**1. Storage policy.** Ordinary Git for current sources and evidence; declared Git LFS threshold
**5 MiB per file**; LFS is *not* adopted until an asset actually crosses it. LFS early costs clone
friction on the second machine for no current benefit (12 MiB of artifacts, ~1 MiB of sources), and a
pointer without fetched content is not a valid asset delivery, so adoption must be atomic —
attributes, build/test fetching and a fresh-clone check in the same change.

**2. Source authority.** **Blend-authoritative is the default** for anything with real silhouette
work: the `.blend` is the master and the exporter is export-only and must never overwrite hand edits.
Script-authoritative remains for repeated or modular pieces (satellites, environment props, rails,
hardware) and for the three already-approved assets, whose existing build scripts reproduce them. Every
asset declares exactly one authority, recorded with its provenance entry.

**3. Platform scope.** Rebuild and validation must work from a fresh clone on **macOS and Windows**:
no `/Applications/Blender.app`, no `sandbox-exec`, no absolute home directories. Blender-side
authoring tooling stays on macOS; Windows rebuilds and validates, it does not author.

**Definition of done** (each item names who can check it):

| Id | Claim | Checked by |
|---|---|---|
| D1 | `build-model`, `export-model` and `validate-models` work for one asset, a batch and validation-only; every failure path exits nonzero and no command writes user data | machine |
| D2 | `validate-models` **is** the S02 contract validator, not a second, weaker opinion | machine |
| D3 | a fresh clone reproduces the three approved runtime exports byte-identically, and a second export is byte-stable | machine |
| D4 | provenance recorded per asset: Blender version, exporter version, source and runtime hashes, declared authority, coordinate/scale policy | machine + skim |
| D5 | **the approved trio is unchanged**: nothing under `assets/models/` differs from `main`, and a before/after in-game capture shows the same silhouettes, worklights and aft emitters | **owner** |
| D6 | no `.blend1`, autosave, temporary render or raw capture run committed; editable sources and authoring tools stay out of the packaged build | machine |

The owner's review is therefore the unchanged-trio capture set (D5), the build/validate receipt
including fresh-clone hashes (D1, D3), and a skim of the provenance record (D4). There is nothing new
to judge visually here: a visible change to the approved trio is a failure of this step, not a feature
of it.

#### S03 completion

Merged 2026-10-16 as `fd08ac7` (PR #118, the frozen policy) and `b5414b5` (PR #119, the implementation):
`tools/art/model_pipeline.py`, the `build-model` / `export-model` / `validate-models` forwarders and 14
focused tests. D1, D2, D4 and D6 are machine-checked and green. D3 is proven on macOS from a plain
`python3` in a fresh clone with no local state, and **half-proven overall: no Windows machine has run this
pipeline**, so that half moves to S09 rather than counting as an S03 receipt. D5 is the owner's
unchanged-trio capture set. `validate-models --all` reports 34/34 with the S02 contract validator included.

### S04 — Generic preview integration

- Implement registry, bounded manifest/mesh loading and render-only mod resolution outside authoritative simulation. Keep approved specimen rendering as a control.
- Add an explicit persisted preview/default selection boundary; stock production behavior remains legacy until S11. Preview activation must be visible in diagnostics and not change saves.
- Resolve size/contact/material/LOD once per asset revision where safe; keep entity transforms and current visibility live. Provide missing/corrupt built-in and optional-pack behavior separately.
- Test selection changes, context teardown/recreation, bounded caches and source/frozen path discovery. Include one replacement mod and one new namespaced asset for an existing mod entity fixture.

#### S04 completion

PR #124 merged as `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c`, with its entire tree equal to tested
head `311edc24c66084a3e145d07e23aad7b839487b5d`. The final autocrlf fresh clone passed 195 focused
tests with no skips; metadata reproduced, pipeline 34/34 and Windows run `38955424960` passed.
Manual package job skipped, not passed. The explicit preview gate is now on `main`; stock remains
legacy. Earlier checkpoints and failed attempts remain in the S04 handoff/evidence, not erased.
Machine receipt: `art/manifests/equivalence/S04-MERGE.json`. No release/tag or S11 switch.

### S05 — Transfer trio approvals to the generic pipeline

**Complete and merged.** Owner instructed: **"Merge and upatte the progress on BLENDER_MODEL_MIGRATION_ROADMAP.md and continue with S06"**.
PR #125 merged as `f873a3344553c6ec5a806b7e7ff7a843a8c321ea` on 2026-10-17. Its complete Git tree
is identical to tested head `e74bf9724728612a06b73290d5396a9fa132ded1`. Windows workflow
`39004868017` passed; manual candidate Windows package skipped, not passed.

Two complete executions each have 102 exact prototype/generic frame pairs, all eight owner colours,
361 matching state hashes over 360 ticks, real combat and individual lamp/emitter controls. Neither
execution needed a nonzero repeat allowance. Fresh clone: 57 focused tests passed, pipeline 34/34,
nine-file runtime metadata reproduction. Existing owner-bound mesh/source revisions are unchanged.
The scoped engineering-equivalence sidecar is `art/manifests/equivalence/S05-TRIO-EQUIVALENCE.json`;
criteria, policy and failure history remain in the S05 handoff and evidence.

The owner-authorized background-only frozen-repeat policy (`"ok go"`) is retained with its fixed
bounds and protected regions. **The old 96-pixel pair still rejects with 15 protected differences.**
No mask was shrunk and no rendering cause is claimed fixed. Current matrix equivalence and owner
merge authorization do not establish infinite framebuffer repeatability, new appearance approval,
full-suite/performance, native Windows graphics/package acceptance, or an S11 switch.

### S06 — Produce, show and approve every remaining batch

#### Historical S06 ledger at published head `4ffdc600` — October 18, 2026 (superseded)

Superseded on October 19, 2026 by the S07 merge: batches B7–B9 landed in PR #130 (`ab62d6d`) and
the opt-in registration in PR #131 (`d427f66`), so the counts below describe the state audited at
that earlier head. They are kept as the record of that audit, not as a live ledger; the current
disposition is 103 registered and approved against 16 explicitly excepted rows (§2.1).

This status is derived from published S06 head `4ffdc600306ecdf4f35265fca689b495e35dd3fe`
(draft PR #127), not from the owner's live checkout. The coverage reconciliation and S07 plan
are on `docs/s06-coverage-s07-plan`, stacked on that exact implementation head. The supporting
report is `art/manifests/reviews/S06-COVERAGE-RECONCILIATION.json`; regenerate/check it with
`python3 tools/art/reconcile_model_coverage.py --check` on that branch. The historical S01
inventory stays unchanged; old implementation statuses are not a live completion ledger.

**Correction:** the earlier ledger/handoff incorrectly declared S06 complete and S10/S11 the
only remaining gate. It also mixed old counts, claimed eleven B6 models when only eight runtime
bindings were authored, and described an absent Imperial station seam that already exists.
The dependency table remains authoritative: S07 has since been completed and merged (§2.1);
S08 and S09 have not been completed.

| Batch | Delivered revisions | Current state |
|---|---|---|
| Trio hull detail (early) | Alliance battleship, frigate, shipyard | Approved and merged (#120/#121/#122), registered for opt-in preview |
| B1 Alliance combat | Cruiser, corvette, supercapital | Three appearance-approved; cruiser has its own decision, pair shares another |
| B2 squadrons/logistics | Eight meshes across Alliance, Confederacy and Syndicate | Appearance-approved; four total faction convoy candidates including B6 need explicit trade-alias integration proof |
| B3a/B3b/B3c orbital stations | Three command, nine small, seventeen remaining station meshes | All 29 appearance-approved; with the trio shipyard, 30 of 40 orbital station inventory rows have approved meshes |
| B4 hardware | Eight satellites and sixteen planet installations across four factions | All 24 appearance-approved (`s06-b4-hardware-2026-10-17`); not awaiting appearance approval |
| B5 environment | One shared asteroid prop | Appearance-approved; ten texture rows deferred to their existing pipeline and two effects plus menu movie outside the mesh catalogue under `s06-b5-scope-2026-10-17` |
| B6 Imperial ships | Five combat hulls, two squadrons, one convoy mesh | Eight appearance-approved; constructor/colonizer remain unbuilt, trade convoy is a shared candidate, not another model |

There are **73 new approved specimens across nine `appearance-batch-revisions` decisions**,
plus the original three approved assets: **76 unique approved assets**. *(Historical counts: §2.1
carries the current 103 registered / 16 excepted.)* At this head all new batch specimens
remain unregistered and unactivated (`procedural_legacy` or `authoring_pending`); the authoring
pipeline still contains only the original trio. Appearance approval is not preview-registration,
merge, production-default activation, packaging or release authorization.

Every one of the **120 historical inventory rows** is accounted for:

| Disposition | Rows | What remains |
|---|---|---|
| Approved asset | 76 | Preserve existing revision approvals; integrate new assets only after registration authorization |
| Shared convoy candidate | 4 | Both crew/trade paths, owner mapping and envelopes/scale require S07 proof; not claimed as accepted integration |
| Missing mesh | 27 | Eight combat hulls, ten Imperial orbital stations, eight constructor/colonizer hulls and one shared construction scaffold |
| Deferred texture pipeline | 10 | Owner B5 scope decision; not Blender meshes or authorization to open a texture class |
| Outside mesh catalogue | 3 | Sky dome, jump glyph, baked menu backdrop under that decision |

The eight missing combat hulls are Confederacy battleship/supercapital/cruiser/frigate/corvette
and Syndicate cruiser/frigate/corvette. **Three additional planned Syndicate keys** — bomber,
battleship and supercapital — sit outside that historical 120-row denominator, with neither
ship-data definitions nor approved meshes. Their production sites were owner-confirmed in S01;
their stats/data implementation boundary is not invented by this reconciliation. The fighter
platform's explicit build list will need the bomber id alongside an authorized data change.

The ten Imperial orbital station rows are missing art, **not a missing seam**:
`fleet_geometry.station_mesh` already consults the generic registry before falling back.
Imperial ships also use the generic `ship_binding` consult. The convoy-only gate correction
must not be generalized to the stock Imperial procedural key gate.

Existing appearance records and reviewed bytes are preserved. Do not rerun completed model
reviews unless a meaningful revision changes their appearance. The B1–B6 delivered sheets being
approved does not discharge uncovered inventory rows or imply an owner-approved exception.
The source-authority, class budget, small-prop and per-binding envelope policies remain in force.

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

**Delivered and merged** 2026-10-19 — PR #129 → `4ab1472` (coverage reconciliation and this plan),
PR #131 → `d427f66` (opt-in registration of 103 bindings, the four-method repair at renderer
`9aff3414`, refreshed pin record, and `S07-FINAL-RECEIPT.json` with 15 criteria, overall pass).
The requirements below are retained as the acceptance criteria they were met against.

**How it closed:** `docs/BLENDER_MODEL_S07_PLAN.md` defined route identity, selected Imperial
station consumers, bounds/contact/ownership, LOD semantics, retained non-mesh scope and the
integrated preview receipt; that plan was executed rather than left as a proposal. The S06
prerequisite was met by explicit coverage exception (§2.1), not by pretending the sixteen
unauthored rows were finished. Closing S07 authorized opt-in registration only — it authorized no
default switch, and the legacy default is unchanged.

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

This is the current progress ledger; initial planning and failed attempts remain in the referenced handoffs. Update completion only from committed evidence and owner-bound receipts.

| Step | Current status | Next action / blocking condition |
|---|---|---|
| S00 | **Complete and merged** — PR #114 landed as `c5b78eb2d4ceba909ffb7444a56b7dec1f35d1b4` (96 files) | Preservation closed; S04/S05 subsequently merged. Retain the known art-integrated acceptance debt |
| S01 | **Complete** — PR #115 carries the inventory, audit, coverage matrix and handoff | Owner-approved scope/order retained; use rows to select S06 assets, not stale historical implementation statuses |
| S02 | **Complete and merged** 2026-10-16 — PR #117 landed as `b2b6b75c4f7d90b99e943bf74b79b811c09e3785`; 36 checks and 28 negative controls | Closed. S04 implements the resolver; the two unrelated open owner questions remain open |
| S03 | **Complete and merged** 2026-10-16 — policies PR #118 `fd08ac7`, pipeline PR #119 `b5414b5`; D1/D2/D4/D6 machine-green, D5 signed by the owner | D3's Windows half is unproven: no Windows machine has run the pipeline. S09 owns that gate |
| S04 | **Complete and merged**, PR #124 → `7030dd2` | Closed; S05 subsequently merged. No S11 authorization |
| S05 | **Complete and merged**, PR #125 → `f873a33`; 57 tests, two 102-frame current matrices, exact hashes and Windows CI | Closed by explicit owner merge authorization. Historical capture failure still rejected; no root-cause fix claimed |
| S06 | **Closed for this milestone and merged** — PR #127 → `cdb1d53`, PR #130 → `ab62d6d`; 103 of 119 bindings authored and approved (98 under eleven `s06-b*` batch decisions, five outside them) | 16 rows explicitly excepted (`s07-s06-coverage-exception-2026-10-19`): 12 `authoring_pending`, 4 `keep_procedural_proposed`. No activation |
| S07 | **Complete and merged** — PR #129 → `4ab1472`, PR #131 → `d427f66`; opt-in registration of 103 bindings, four-method repair at renderer `9aff3414`, pin record refreshed, receipt 15/15 criteria | Default remains legacy; packaging skipped and not accepted; native Windows graphics still S09; S11 unauthorized |
| S08 | **Complete and merged** 2026-10-19 — #134 → `e8925cff`, #135 → `5980890c` (merge commits, reviewed heads unchanged); main's tree equals the tested S08 head | Closed for its delivered scope; default remains legacy, S09 owns suite/cost/package/platform acceptance |
| S09 | **In progress, not accepted** — candidate frozen at `5980890c` (tree identical to main); protected per-module sweep 210 modules / 2,281 tests / 208 pass, 2 real pre-existing failures classified; validators 1034/1034, 112 files, `CHECK_OK`; owner adopted the 60/30 FPS reference and a scoped Windows waiver (`s09-performance-target-2026-10-19`, `s09-platform-waiver-2026-10-19`); exact-candidate Mac package built and inspected | Measured: authored catalogue costs **4.5-6.2× legacy frame time** (stock 42→188 ms, 57→293 ms) with simulation and checksums identical, so the adopted reference is **not met**; the frozen Mac package **cannot start with the catalogue selected** (`E_SYMLINK_ESCAPE`, pre-existing). Open: packaging fix decision, two test-fixture repairs, Windows |
| S10 | Not started | Final owner asset lock and switch authorization |
| S11 | Not started | Last step only: verified, reversible default switch |

The original S00-only kickoff is historical and retained in Git/handoff history; the current next task below supersedes it.

### 8.1 Current delivery ledger

| Workstream | Current state | Next gate |
|---|---|---|
| S00 preservation | **Merged into `main`** as `c5b78eb2d4ceba909ffb7444a56b7dec1f35d1b4` (PR #114, squashed, 2026-10-16, 96 files); branch delta art-only; earlier heads `313f968`/`0f6531f4` retained in history; blobs verified byte-for-byte before the merge | S04 preview boundary and S05 equivalence are merged. Retain known art-integrated acceptance debt |
| Performance PR #113 | **Merged** to `main` as `16523bf0b06a39e3f77961d0c213b0af184a16b6` (tree identical to tested head `a24a4ed`); version `0.15.1`; protected whole suite 1,668 tests, 0 failures/errors, 9 skips; Windows CI `38858140567` passed | Closed. Performance remains headroom, not an art upgrade. Measurement targets still need owner agreement |
| S01 inventory | **Complete** in PR #115: 120 bindings, 30 dispatch paths, 25 non-model elements; owner decision `s01-scope-2026-10-16` answered all four scope questions and planned the three unreachable mesh keys | Scope/order closed; no design or activation is approved by it. S06 uses these rows and the current merged tree |
| S02 extension contract | **Complete and merged** 2026-10-16 as `b2b6b75c4f7d90b99e943bf74b79b811c09e3785` (PR #117): three versioned schemas, the three approved assets as specimen manifests, `tools/art/validate_contract.py` green on **36 checks and 28 negative controls**, decisions D-01…D-20 in `art/manifests/decisions.md`; the class budgets, the extent gate and the legacy window are the owner's answers as enforced rules | Closed. S04 generic resolution and S05 trio equivalence are now merged |
| S03 authoring pipeline | **Complete and merged** 2026-10-16 — policies in PR #118 (`fd08ac7`), `tools/art/model_pipeline.py` with the three forwarders and 14 focused tests in PR #119 (`b5414b5`); D1/D2/D4/D6 machine-checked, D5 signed by the owner, D3 proven on macOS from a fresh clone with plain `python3` | D3's Windows half: no Windows machine has run the pipeline. S09 owns that gate |
| Trio hull detail (S06, early) | **Approved and merged** — one revision per binding: battleship #120 `47b0161`, frigate + shipyard #121 `047c380`, record correction #122 `96cd92e`; 11,457 / 7,708 / 10,767 triangles, no silhouette, scale or simulation change; the guard raise is the owner decision `s07-detail-budget-2026-10-16` (11,888 tri / 9,500 verts) | None outstanding. Not a catalogue batch: the remaining bindings keep their inventory status |
| S04 generic integration | **Complete and merged**, PR #124 → `7030dd2`; autocrlf clone 195/195; contract 36/28; pipeline 34/34; Windows CI passed | Closed. Manual package skipped; full S05 matrix subsequently completed under its recorded policy |
| S05 trio equivalence | **Complete and merged**, PR #125 → `f873a33`, tree-identical to tested head `e74bf97`; Windows CI `39004868017` passed | Closed with historical capture limitation retained; manual package skipped, no native graphics/package claim |
| S06 authoring | **Closed for this milestone via explicit exception**: 103 of 119 bindings registered and approved (98 under eleven `s06-b*` batch decisions, five outside them); merged in #127 `cdb1d53` / #130 `ab62d6d` | 16 rows excepted rather than finished: 12 `authoring_pending` (eight planet environments, `menu:cinematic_backdrop`, three Syndicate hulls) and 4 `keep_procedural_proposed`. Their authoring is later work, not a claim of completion |
| S07 integration | **Complete and merged** — #129 `4ab1472` (coverage reconciliation + plan), #131 `d427f66` (103-binding opt-in registration, four-method repair at renderer `9aff3414`, refreshed pin, `S07-FINAL-RECEIPT.json` 15/15); evidence: 870/870 native captures and 360/360 movie frames on the final bytes, one independent byte-bound review, per-module suite gate 205 modules / 2,245 tests with one recorded pre-existing failure | Default is legacy; packaging skipped, not accepted; native Windows graphics and performance targets remain S09 owner gates; S11 unauthorized |
| S08 | **Merged** 2026-10-19 as #134 `e8925cff` then #135 `5980890c`, both with merge commits and unchanged reviewed heads; main's tracked tree equals tested head `340b5a2`. 150 tests / 18 isolated modules plus four tool gates, packed-pack and differing-cosmetic peer evidence | Closed. Its main.py `data_store=gm.ds` change left `test_gl_lifecycle`'s AST fixture stale — carried as recorded pre-existing debt into S09 |
| S09 | **In progress, not accepted** — candidate `5980890c` frozen in an isolated checkout behind a native write barrier; per-module sweep 210 modules / 2,281 tests / 208 pass, the 2 failures classified (one S08 fixture defect, one carried convoy guard); 10 further single-process failures proven to be instrument defects; both owner decisions recorded; complete-catalogue cost measured with simulation and checksums identical; evidence in `artifacts/s09/`, plan in `docs/BLENDER_MODEL_S09_PLAN.md`, numbers in `artifacts/s09/PERFORMANCE.json` | Mac package build/inspection, the two test-fixture repairs, and the owner's decision on whether to fund renderer cost work against the unmet 60/30 FPS reference |
| S10 | **Not started** | Owner asset-lock/rollback review after S09 acceptance; no hardware waiver inferred |
| S11 | **Not started, not authorized, not done** | Final explicit owner-controlled catalogue switch only after S10 |

**Current delivery: S09 in progress on an immutable candidate; S09 is not accepted.**
#134 and #135 were merged bottom-up with merge commits on 2026-10-19 (`e8925cff`, `5980890c`),
so the reviewed heads and their evidence-bound hashes survive; main's tracked tree equals the
tested S08 head `340b5a2`. S09 froze that tree (`b28b48ab…`) in an isolated checkout and ran the
protected per-module sweep: 210 modules, 2,281 tests, 208 pass, two real pre-existing failures
(an S08 fixture omission and the carried convoy guard) and ten single-process results proven to be
instrument defects. Read `docs/BLENDER_MODEL_S09_PLAN.md`, `art/manifests/handoffs/s09.md` and
`artifacts/s09/CLASSIFICATION.json` before continuing. The remaining art rows are later authoring
work, not prerequisites to restart S06/S07. Keep the legacy default.

The old `S06-TO-S10-HANDOVER.md` claim that only landing remains was corrected on
`docs/s06-coverage-s07-plan`, which is now merged. Read its coverage report and
`docs/BLENDER_MODEL_S07_PLAN.md` for how S07 was accepted. S00–S07 remain closed: do not restart
those reviews. No remaining model approval is inferred.

The owner accepted the reconciliation/S07-planning proposal with **"agree. Let do this"**, and the
S07 merge, the S06 coverage exception and the bottom-up merge of the five stacked PRs were each
authorized separately on 2026-10-19. None of that authorizes new model designs, a default switch,
a tag or release, gameplay-stat changes, or an engineering/platform waiver.

Recommended remaining-art order for later batches: ten Imperial orbital stations; eight existing
Confederacy/Syndicate combat hulls; eight constructor/colonizer hulls plus the shared scaffold.
Keep the three planned Syndicate hulls visible as additional work requiring the data/stat boundary
to be settled. This order is a recommendation, not a new owner-approved scope exception or design.

Registering approved revisions for **opt-in** preview is separate from S10's final release lock and
S11's default switch, and it does not itself require or authorize a release. Preserve the
production legacy default throughout.

Two owner policy questions remain: authoring extent drift versus collision policy and advisory
draw-call/texture-byte columns. Do not answer them yourself. Public gameplay dependency discovery
stays S08; Windows rebuild/native graphics/package, broad-suite and performance gates stay S09.
Deferred hardware acceptance needs evidence or an explicit owner waiver, never an assumed pass.

The reported LAN observations (1/30 standalone, 1/4 suite, 0/12 pristine control) remain retained
acceptance debt; they do not prove either a branch regression or a baseline defect. Do not repeat
the previous handoff's unsupported causal dismissal. PR #127 head `4ffdc60` now has a successful
Windows workflow `39102141681`; the manual Windows package job was **skipped**, not passed.
That CI receipt does not establish catalogue art validation or S09 acceptance.

Historical kickoff instructions remain in Git and their handoffs; they do not override this
reconciled next task or the dependency gates in section 6.
