# Extension-contract decisions

Decisions behind `docs/ASSET_EXTENSION_CONTRACT.md` and `art/schemas/*`. Each entry records what
was decided, why, and what it costs. "Needs owner" marks the ones a build cannot settle.

Machine-checked decisions carry the error code that enforces them, so a drift between this file
and the validator is visible: if a decision has no code, nothing enforces it.

| Id | Decision | Enforced by |
|---|---|---|
| D-01 | Three separate documents (manifest, registry, visual pack) instead of one combined file | three schemas, dispatch on `contract` |
| D-02 | The renderer binds on `<faction>:<class-or-kind>`, never a display name or filename | `E_UNKNOWN_BINDING`, registry pattern |
| D-03 | `revision` is a computed content hash over the pinned files | `E_REVISION_MISMATCH`, `E_FILE_HASH` |
| D-04 | The pinned export is validated as geometry, including index bounds and `triangle_count` | `E_EXPORT_SHAPE` |
| D-05 | The mesh must sit inside the declared envelope; the envelope is presentation only | `E_BOUNDS_MISMATCH`, `E_BOUNDS_DEGENERATE` |
| D-19 | A revision may move an extent by at most 1 % of that axis, or 2 units, whichever is smaller, before it needs a fresh approval | `E_EXTENT_DRIFT`, `envelope_decision` |
| D-20 | `budgets.triangles` is a declared cost, and a mesh that has outgrown it is a false claim | `E_MEASUREMENT_STALE` |
| D-06 | Six material roles in v1; a seventh role or a shader is a new major version | `E_SCHEMA`, `E_ROLE_MISMATCH` |
| D-07 | The legacy integer payload marker `"schema": 1` is accepted during a declared migration window | `E_EXPORT_SHAPE` accepts it explicitly |
| D-08 | Pack order is the persisted, documented enabled list — no filesystem precedence | decision only (S04 implements, S08 proves) |
| D-09 | Pack paths may not escape the pack root, by traversal, absolute path or symlink | `E_UNSAFE_PATH`, `E_SYMLINK_ESCAPE` |
| D-10 | An additive pack must name the gameplay mod defining its entities | `E_MISSING_GAMEPLAY_MOD` |
| D-11 | Duplicate bindings and duplicate pack entries are errors, not last-one-wins | `E_DUPLICATE_BINDING`, `E_DUPLICATE_ID` |
| D-12 | An additive entry colliding with a core binding is an error | `E_ASSET_COLLISION` |
| D-13 | Approval binds to a revision and to existing evidence; a stale approval fails | `E_APPROVAL_STALE`, `E_EVIDENCE_MISSING` |
| D-14 | A core binding with no manifest fails coverage rather than passing silently | `E_MANIFEST_UNRESOLVED` |
| D-15 | Unknown contract ids and majors fail; newer exports are never reinterpreted | `E_UNKNOWN_CONTRACT` |
| D-16 | `status` reuses the S01 inventory vocabulary so coverage is a join, not a third list | registry schema `enum` |
| D-17 | Non-finite numbers are rejected at parse time | `E_NON_FINITE` |
| D-18 | The examples pin the real payloads, so an approved revision re-pins them | `tools/art/update_contract_examples.py --check`, `E_FILE_SIZE`, `E_BOUNDS_MISMATCH` |
| D-21 | Validate each replacement against the approved binding envelope before activating its whole pack; never change collision radii | S04 resolver `E_EXTENT_DRIFT`, transactional pack tests |

## Why, briefly

**D-01/D-02/D-16.** One combined file would have to be rewritten to add a binding, which makes a
merge conflict into a correctness risk and makes "who owns this identity" unanswerable. The
registry is the one place identity is decided, and it is small enough to review by eye.

**D-03/D-13.** An approval that binds to a filename binds to nothing: the file can be replaced
without the approval noticing. Hashing the content is what lets the S00 approval and every later
one be checked instead of trusted. This is also why the validator recomputes the revision rather
than reading it.

**D-04.** The first version of this validator checked only hashes and was happy with a payload
whose batches were not triangle lists at all. Checking the geometry — finite positions, indices
inside the vertex array, `triangle_count` equal to the actual row count — is what turned the
check into evidence. The three approved exports satisfy all of it, which is why the real assets
are the primary positive control in this PR and not invented fixtures.

**D-05/D-06.** Presentation may not grow past the envelope that camera, picking, contacts and
shields were sized for, and a role the mesh does not fill silently draws nothing. Both are silent
failures in a game and loud failures here.

**D-07.** The trio already shipped with `"schema": 1` as a bare integer. Migrating them to
`contract`/`contract_major` is a byte change to files the owner has approved, so this contract leaves
them untouched and accepts both forms. The owner answered the window's question on 16 October 2026:
it stays open **until the production cutover (S11)**, when the trio is re-exported and re-approved
once. **Do not close it silently, and do not close it early.**

**D-08.** Implicit precedence ("later directory wins") is how a cosmetic system becomes
non-reproducible; two players with the same packs must get the same result, and diagnostics must
be able to say which pack won. The ordering rule is settled here; proving identical simulation
with different visual packs is S08's.

**D-09.** A pack is untrusted input from the renderer's point of view. Traversal and absolute
paths are refused by the schema; symlink escape needs a real filesystem, so it is the one
negative control the validator builds at runtime instead of committing as a fixture.

**D-14.** This is the S01 finding made mechanical. The inventory already reports three declared
`SHIP_KEYS` with no data row; a registry that names a manifest nobody defines must fail the same
way rather than rendering a fallback and calling it covered.

**D-18.** The examples describe the three real exports, which is what lets the contract verify
itself against the tree, so they are coupled to every approved revision by design. That coupling bit
once, and usefully: the battleship's surface-detail revision (S06) took the mesh's beam from 69.0 to
73.349998 while its length extent stayed identical, and the contract's envelope check was the only
thing that noticed — every other check passed, and the approval record had described the revision as
changing no silhouette. The size, hash, recomputed revision, envelope and approval binding are
therefore re-derived by a tool rather than edited by hand, each negative control keeps exactly one
defect, and `--check` makes staleness a failure instead of a surprise. Note what this does *not* fix:
the contract has no rule about how far a revision may move an extent. The owner's answer to that
question is D-19 below.

**D-19.** An extent is what camera framing, picking, contact radii and shield placement were sized
for, so moving one is a gameplay-adjacent change however it looks. A flat "any movement needs a fresh
approval" rule would make every raised belt an approval event, because detail is placed from the frame
it sits on and stands proud of the surface; a rule with no limit is how the S06 pass widened the
battleship's beam by 6.3 % with nothing to say about it. The owner's answer — 1 % of that axis, or two
units, whichever is smaller, then a fresh approval — is the middle. Mechanically the binding's
`envelope` is the approved extent, `envelope_decision` names the approval that accepted a widened one
and must be the approval its manifest carries, and the re-pin tool refuses to widen past the grace
without being handed that id.

**D-20.** `budgets.triangles` is described by its own schema as *measured, not aspirational*, and
nothing read it — so it rotted: after S06 and S07 the three specimens still declared their pre-detail
counts, 2,756 / 2,580 / 2,832 triangles short of the meshes they pinned. A declaration the mesh has
outgrown is a claim about a file that no longer exists, so the contract now refuses it while still
allowing a declared ceiling above the mesh (a pack may promise more room than its stub uses). Draw
calls stay a declaration: their count depends on how the renderer batches roles, not on the payload,
so nothing here can weigh them.

## Decided by the owner

Put to the owner on 16 October 2026. The words are his, verbatim, and each answer is the record the
table, the validator and the registry implement.

1. **Class budgets** (contract §9) — *"Set real advisory budgets below the loader's cap, sized from the
   approved specimens (capital 11,888 — the exporter's ceiling —, escort 8,000, station 11,500), and
   keep 12,000 as the loader's hard failure"*. The table carries those numbers; `advisory_budget_triangles`
   in `art/manifests/pipeline.json` is where a build weighs them (S03 records); the loader's hard
   failure is untouched.
2. **An extent change gets its own gate** — *"A revision may move an extent by at most 1% on that axis
   (or 2 units, whichever is smaller) before it needs a fresh approval; beyond that the contract
   refuses"* → D-19.
3. **The migration window** — *"Keep accepting \"schema\": 1 until the production cutover (S11), then
   re-export and re-approve the trio once"* → D-07.
4. **The example packs** — *"Examples stay illustrative — the three real exports are the acceptance
   controls, as the validator already uses them"* → contract §5.

## Needs the owner

Open on this contract, in the order they bite:

1. **The class table's second and third columns.** Triangles are settled (above); draw calls and
   texture bytes are still declarations with nothing to weigh them, so they are debt rather than
   budgets.
2. **What an extent move does to a collision.** D-19 governs authoring, and the game's radii come from
   the data files, not the mesh (`game/data/store.py` reads `radius` per ship and station). A beam that
   grew by 6 % can therefore disagree with the radius the game collides on, and nothing checks it yet;
   whether the authoring pipeline should refuse that drift, or the data row should be re-derived from
   the mesh, is the owner's call and not this contract's.
3. **Resolver envelope checks — answered for S04.** See D-21 below; implementation and
   transactional rejection tests are still required.

## S04 owner decision — D-21: pack-load envelope validation

- Decision id: `s04-pack-envelope-2026-10-16`.
- Owner: Lukasz Jawor.
- Baseline reviewed: `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c`.
- Proposal put to the owner: **reject the whole visual pack if a replacement exceeds the
  binding's approved envelope; keep collision radii unchanged.**
- Owner's reply, verbatim: **"yes"**.
- Parsed policy: before activation, validate every replacement mesh against the target binding's
  approved visual envelope. Reject the entire offending pack transactionally and retain the
  previous valid source. Visual metadata must not write or re-derive gameplay collision radii.
- This answers the pack-load envelope question only. It does not settle the authoring/collision
  drift policy or the draw-call/texture-byte columns, approve a model revision, authorize a
  production-default switch, or authorize merge/tag/release.
- Status: owner-adopted policy, implemented and exercised by S04 transactional rejection tests; published for owner review in draft PR #124.

## S06 B5 appearance revision — `s06-b5-environment-2026-10-25`

- Decision id: `s06-b5-environment-2026-10-25`, kind `appearance-revision` (the batch record of
  2026-10-17 keeps its own entry and history; its pins move here, with the previous values kept in
  `b5_asteroid_reauthor_correction`).
- Owner: Lukasz Jawor.
- Approved asset: `core:environment/asteroid_field` (`environment:asteroid_field`), the only asset
  this revision changes.
- Owner's words, verbatim: **"Asteroids look good"** — said after a before/after sheet of the field
  in a real skirmish frame and two native captures of that frame, all in
  `artifacts/s06_alliance_batch_review/b5-asteroid-v5/`.
- What changed: four overlapping bevelled boxes carrying faction hardware roles became one
  irregular boulder — a displaced icosphere with two impact dents, a flattened base and one sheared
  break face — on stone roles `base`/`dark`/`trim` only. 216 → 320 triangles, 126 → 162 vertices,
  6 → 3 draw calls. The envelope is unchanged (±0.58 X/Z, ±0.46 Y), so `ASTEROID_EXTENT` and every
  projected size hold.
- Why: the field's geometry has no visible tint control (instance tint moves 0 white, 0 dark and 25
  changed pixels on a rendered frame), so a field could only stop looking like one slab if the mesh
  itself changed.
- Revision hashes, re-derived from disk when the record was written: blend `aa3ded259475c79f091f8359a8b6c850e1eb92dfea0f65bc786746187b8829e1`,
  mesh `ebcfb21f78289ba6deda5165c965960f8b7c0d2fa4a50fdc7fa2c6b66f40a2ba`.
- What it does not authorise: landing, registration, activation, merge, tag or release; the S11
  catalogue switch; packaging; any gameplay value or the mining-station range rule; any other
  asset. The mesh's `features` block (`field_instances: 40`, `field_scale_range 12-46`) records the
  authoring intent from before the field was drawn this way and is explicitly not a claim about the
  draw — the renderer decides the count (64 per field) and the sizes.
- Evidence limits: the owner approved the picture. `native-field-verification.json` is an
  engineering measurement of the same revision, and it says what it cannot see: a field larger than
  the frame has a clipped bounding box, which is why the tool also refuses a field that touches the
  frame edge and checks the disc's fill.

## Not decided here

- Live in-battle pack switching, workshop distribution and executable mod scripting stay out of
  scope.
- `mods/<name>` gameplay overlays keep their existing rules; the visual resolver deliberately does
  not reuse `DataStore._load_mod`, because that path overlays gameplay data and must not import
  render/GL code into simulation.
- Authoring-tool interfaces (`build-model`, `export-model`, `validate-models`) are S03's; this
  contract only says what the exporter's output must satisfy.
