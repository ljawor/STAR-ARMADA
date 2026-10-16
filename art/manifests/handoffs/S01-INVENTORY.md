# Handoff: S01 — inventory and batch design

Status: **complete** (owner scope review given 2026-10-16; see "Owner approval" below)

Base commit / branch: `16523bf0b06a39e3f77961d0c213b0af184a16b6` (`main`, version `0.15.1`) on
`docs/s01-model-inventory`

PR and exact pushed head: PR #115. The branch was created with
`git worktree add -b docs/s01-model-inventory <scratch> origin/main`, so no work happened in the
owner's live checkout. The head is read back in the receipt comment posted after each push;
commit `9dd67857` was the revision the owner reviewed, and the decision record in
`art/manifests/inventory_audit.json` (`owner_scope_decisions.binds_to`) names it.

Prerequisites verified:

- S00's published checkpoint is **draft PR #114**, unmerged, head
  `0f6531f4d14f649cbfed744c29b61b4537b0f5e8` (reconciled with `main` and republished during S00;
  the roadmap still quotes the older `313f968` head — see "Open issues"). Its handoff
  `art/manifests/handoffs/S00-PRESERVATION.md` and approval record `art/manifests/approvals.json`
  were read on that branch.
- `main` does **not** contain the trio: `_alliance_battleship_slice`, `_alliance_frigate_slice`,
  `_alliance_shipyard_slice` and `render/authored_mesh.py` are absent here. Every statement in
  this inventory that depends on them is labelled as checkpoint-relative.
- `main` is the performance-only merge (`16523bf`, PR #113, CI run `38858140567` passed).
  `render/renderer.py` here carries the draw-scope/perf code and **not** the art hunks.

Owned files and assets/bindings:

- `art/manifests/model_inventory.json` — the machine-readable catalogue the roadmap §4 already
  names (143 asset bindings plus the dispatch audit; 163 KB).
- `art/manifests/inventory_audit.json` — the curated renderer-dispatch audit used as input (53 KB).
- `art/manifests/reviews/S01-coverage-matrix.md` — the owner-facing coverage matrix (44 KB).
- `art/manifests/handoffs/S01-INVENTORY.md` — this file.
- `tools/art/build_model_inventory.py` — the generator for the two generated files.
- `docs/BLENDER_MODEL_MIGRATION_ROADMAP.md` — ledger rows for S00/#113/S01 only.
No renderer, gameplay, data, asset or test file is touched by this change.

Source authority / Blender / exporter / schema versions:

No Blender source, exporter or runtime mesh is added or modified here — S01 is analysis. Every
model generator named in the inventory is the **procedural** authority in this tree. The
inventory uses `s01-model-inventory/v2`; the audit uses `s01-render-audit/v1`; both are declared
in the files themselves. The approved trio's `.blend` files, exporters and runtime meshes remain
on PR #114 and are referenced, not duplicated.

Changed source and runtime hashes / asset-lock revision:

None. No `.mesh.json`, `.blend` or asset byte changes. `git status` for this branch contains only
the six paths listed above.

What changed visibly:

Nothing in the game: this PR is documentation plus a build tool. The visible output is the
coverage matrix — counts, per-binding rows, every renderer dispatch path, the hidden
second-copy risks and the batch proposal.

Owner approval: **given 2026-10-16, decision `s01-scope-2026-10-16`**, against the matrix at the
revision the owner reviewed (`9dd67857`). The owner answered all four questions put to them, and
their own wording is preserved in `art/manifests/inventory_audit.json`:

1. Scope exceptions — "let bring them into catalog": the planet bodies (E05), the asteroid/
   environment props (E07) and the menu cinematic backdrop (E23) are **in scope**. They now carry
   `in_scope_authoring_pending` and an inventory binding (`menu:cinematic:backdrop` was added so
   the decision is bound to a binding, not to a sentence).
2. The three declared-but-unreachable mesh keys — "plan the hulls": kept as planned hulls, with
   the production site recorded per hull (`s01-hull-plan-2026-10-16`).
3. Batch order — "as recommended": B1 Alliance combat hulls, B2 squadrons/logistics, B3 stations,
   B4 satellites and planet installations, B5 environment props.
4. Batch plan — "approved", as a plan and as scope.

Two honest boundaries on that approval. First, the elements in section 7 of the matrix that were
**not** put to the owner (starfield sky dome, star, nebula, jump point) keep their
`keep procedural` **proposal**; they are carried as proposals, not presented as approved. Second,
this is scope and plan approval only: it does not approve any model design, does not merge PR
#114, does not activate the trio, and does not change the production default.

The separate trio decision `approved-trio-2026-10-16` (`rebel_battleship`, `rebel_frigate`,
Alliance-owned/rebel `shipyard`) is recorded in `art/manifests/approvals.json` on PR #114 and is
unchanged. Every other row stays `UNASSIGNED` for model owner.

Tests and commands actually executed, counts and retained failed attempts:

```
.venv/bin/python tools/art/build_model_inventory.py
  base_commit 16523bf0b06a39e3f77961d0c213b0af184a16b6     EXIT=0   invariants ok
  total_bindings 119
  by_category {combat_hull 18, construction 9, environment_prop 13, logistics_hull 8,
               planet_installation 16, satellite 8, squadron 7, station 40}
  by_faction  {confederacy 27, imperial 27, rebel 27, shared 14, syndicate 24}
  by_status   {approved_blender_draft_unmerged 3, procedural_legacy 103,
               unknown_needs_owner_scope_decision 13}
  ship_bindings 41 -> distinct_ship_mesh_keys 32, ship_keys_in_registry 35
  declared_ship_keys_without_a_data_row ['syndicate:bomber', 'syndicate:battleship',
                                         'syndicate:supercapital']
  dispatch_paths 25, tooling_dispatch_paths 5, non_model_elements 25,
  hidden_duplicate_risk_paths 16, owner_scope_decisions_required 3, unresolved_items 5
.venv/bin/python tools/art/build_model_inventory.py --check     EXIT=0 (no drift)
```

Retained failed attempts, because they changed the result:

1. The first generator run built 143 rows: station kinds were taken from every key in
   `assets/data/stations/stations.json`, which also holds the two satellite and four
   planet-installation rows, so 24 bindings were double-counted. Fixed by excluding those kinds
   from the orbital-station set; the row count is 119 and matches the independent audit.
2. The first invariant asserted that 41 ship bindings cover `SHIP_KEYS` *exactly* (32 vs 35) and
   failed. The check was wrong, not the data: three registry keys have no data row at all. It is
   now a containment check plus an explicit `declared_ship_keys_without_a_data_row` list, which
   is a real finding rather than a hidden failure.
3. An early check of the audit's citations used `main` as the base while the audit had been
   taken on the art-integrated tree: 55 of 119 line numbers differ. That is why the generator
   now resolves symbols instead of trusting numbers, and why the two reference bases are
   labelled per row.

The audit input is committed verbatim except for base-labelling: three risk rows and the
draft-only trio-site section are marked as checkpoint-relative, and a `reference_base_note`
records why. The generator re-checks the audit's symbol claims on every run.

Actual-game captures/video: none produced by this step, and none is claimed. The three
checkpoint captures already in the repository (`artifacts/alliance_blender_trio/`) remain on PR
#114; S01 required inventory and scope, not new renders.

Performance / packaging / platform evidence and limitations:

No performance, package or platform claim is made. The 25 runtime dispatch paths and 5
tooling-only paths are static-read results with real line references; no benchmark, capture or
CI graphics run was needed for a documentation change. Headless Windows CI cannot validate this
change's content, and nothing here is offered as platform acceptance.

User-data preservation and unrelated work retained:

The owner's live checkout `~/Downloads/Project/STAR-ARMADA` was never written to: the branch was
created in a separate worktree off `origin/main`, and the live tree's dirty/untracked set was
hashed to scratch first (S00). No stash, checkout, reset or file write happened there. No
`saves/`, `replays/`, settings, campaign, replay or unrelated prototype file is staged. No
credential or token appears in any committed file.

Open issues, blockers and decisions required:

None of the original blockers remains open; all four questions were answered (see "Owner
approval"). What is carried forward rather than resolved:

1. **Whether the menu backdrop is drawn live or baked per catalogue revision** is an S02/S04
   implementation choice, not part of the scope answer. The bake exists to avoid paying
   battle-scene cost behind every menu, so it is recorded as the default until the owner says
   otherwise.
2. **The starfield sky dome, star, nebula and jump point** keep their `keep procedural`
   proposal: they were not among the questions put to the owner, so they are proposals, not
   approvals. Raise them if that reading is wrong.
3. **Roadmap ledger text on `main` is stale**: §8.1 still describes #113 as an unmerged plan and
   #114 as in-progress at `313f968`. This branch corrects those rows; PR #114 carries its own
   edit to the same rows, so expect one documentation conflict when the two land. Resolve it as
   a ledger merge: keep #114's S00 rows, add this branch's S01 row, keep a single "current next
   task" line.
4. The audit's quoted line ranges are checkpoint-relative for rows `R09`/`R10`; each row states
   this in its `line_reference_base` column rather than silently pointing at the wrong code.
5. No model design is approved and no authoring has started: S06 still requires per-asset owner
   approval against an enumerated list.

Next executable step and its acceptance criteria:

**S02 — freeze the extension contract** (roadmap §6), on its own branch. Deliverable: versioned
asset/registry/mod schemas with minimal core, replacement and additive-pack examples; the
migration path from the specimen schema and profile loader; resolver, fallback and compatibility
decisions; failure diagnostics, pack ordering and security bounds; approval invalidation and
cache/resource invalidation rules; plus class budgets and LOD expectations agreed initially.
Write the design choices to `art/manifests/decisions.md`. Gate: *reviewed versioned schemas,
examples, resolver/fallback/compatibility decisions.*

Why S02 is the right next step and not S06: the trio's activation inside PR #114 is still
hardcoded and unconditional, and S04 cannot restore an explicit preview gate without S02's
contract. Authoring batches (S06) can then run against a settled contract.

Carry these forward into S02/S06:
- `syndicate_bomber`'s data id must be added to `fighter_platform.builds_ships` when the hull is
  created, or the hull will exist but be unbuildable.
- B5 now contains real work: the planet bodies, the asteroid props and the menu backdrop.
- The 30 dispatch paths and the R24/R25 hidden legacy generators are the S07 checklist; do not
  rediscover them.
