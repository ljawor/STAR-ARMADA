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

**D-07. Needs owner attention at S03.** The trio already shipped with `"schema": 1` as a bare
integer. Migrating them to `contract`/`contract_major` is a byte change to files the owner has
approved, so this contract leaves them untouched and accepts both forms for now. The window has
no end date yet: closing it is a decision for S03, and closing it means re-exporting and
re-approving the trio. **Do not close it silently.**

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
the contract has no rule about how far a revision may move an extent. That is the fourth question
below.

## Needs the owner

1. **Class budgets, extents and LOD expectations** (contract §9). The table is proposed from the
   approved trio's measurements, but it becomes a constraint on every later batch, so it needs
   agreement before the next batch is authored against it. Two things about it are now known to be
   wrong rather than merely unconfirmed: `combat hull <= 12,000` is exactly the loader's hard cap and
   `station <= 16,000` is above it, so neither can ever fire; and nothing at all budgets the mesh's
   extents, which is how the S06 detail pass widened the battleship's beam by 6.3 % without any check
   objecting. Numbers at or above a hard cap are documentation; the question is whether the owner
   wants real advisory budgets below the cap, and whether a revision should be allowed to move an
   extent at all without a fresh approval.
2. **Whether an extent change needs its own approval gate.** The battleship's beam moved 6.3 % inside
   a revision the owner approved on appearance. The owner did approve the render, so the artifact is
   not in doubt — but a rule such as "an extent may move at most N units / P % before the revision
   needs re-approval" is a contract decision this PR cannot take on the owner's behalf.
3. **The D-07 migration window.** When the trio is re-exported to the contract payload format, the
   approval has to be renewed. Re-exporting changes bytes of an approved asset; that is the
   owner's call, not a cleanup task.
4. **Whether visual packs ship in S08's acceptance or only as examples.** This determines how much
   of section 5 has to be proven with a second real pack rather than a fixture.

## Not decided here

- Live in-battle pack switching, workshop distribution and executable mod scripting stay out of
  scope.
- `mods/<name>` gameplay overlays keep their existing rules; the visual resolver deliberately does
  not reuse `DataStore._load_mod`, because that path overlays gameplay data and must not import
  render/GL code into simulation.
- Authoring-tool interfaces (`build-model`, `export-model`, `validate-models`) are S03's; this
  contract only says what the exporter's output must satisfy.
