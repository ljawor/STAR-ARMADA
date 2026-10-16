# Asset, registry and mod extension contract

**Status:** S02 deliverable, review-ready. Frozen for implementation, not yet implemented: S04
builds the resolver this document specifies, and the trio's current selection is migrated onto it
in S05. Nothing here changes what the game draws today.

**Step:** roadmap S02 ("Specify asset, registry and mod contracts").
**Gate:** reviewed versioned schemas, examples, resolver/fallback/compatibility decisions.

The machine-checked half of this contract lives in `art/schemas/` and is executed by
`tools/art/validate_contract.py`. Where this document and the schemas disagree, the schemas win
because they are the part a build can enforce; fix the document.

| Artifact | What it is |
|---|---|
| `art/schemas/model-manifest.schema.json` | v1 manifest: one immutable description of a renderable model |
| `art/schemas/binding-registry.schema.json` | v1 registry: canonical gameplay identity → asset |
| `art/schemas/visual-pack.schema.json` | v1 render-only pack: replaces core bindings, adds namespaced models |
| `art/schemas/examples/` | Valid examples that must pass |
| `art/schemas/examples/invalid/` + `EXPECTED.json` | Negative controls: each must be rejected with the declared code |
| `tools/art/validate_contract.py` | Runs all of it; exit 0 only when both halves hold |
| `art/manifests/decisions.md` | Why each choice was made, and what still needs the owner |

```
python3 tools/art/validate_contract.py          # 8 valid documents, 24 fixtures, 1 runtime control
python3 -m unittest tests.test_asset_contract   # the same thing as a test
```

## 1. Identity and versioning

Four names, never conflated:

| Name | Example | Stability |
|---|---|---|
| gameplay entity id | `rebel_battleship` | Owned by gameplay data. Never renamed by art. |
| binding key | `rebel:battleship` | The identity the renderer selects on: `<faction>:<class-or-kind>`. |
| visual asset id | `core:alliance/battleship` | Namespaced, stable across revisions. |
| asset revision | `58e9aaecc979…` | Content hash; changes whenever the pinned files change. |

The renderer binds on the **binding key**, resolved through the registry. A display name is never
a key: renaming "Alliance Battleship" in a string table must not change which mesh is drawn. A
filename is never a key either — `alliance_battleship.mesh.json` is where a payload happens to
live, not what it is.

Station faction and convoy/squadron identity are explicit in the registry
(`identity.station_faction`, `identity.variant`), because a station's owner is not recoverable
from its class name and a shared mesh across two owners is a claim that must be visible.

Version marks are separate on purpose:

- `contract` + `contract_major` — the document format (this contract).
- `export.contract` + `export.contract_major` — the exporter's payload format, pinned by the manifest.
- `requires.min_engine` — the game version the asset needs.
- `requires.material_profile` — the material description the roles are drawn with.
- `revision` — the content hash of the pinned files.
- `provenance.tool_version` — the exporter revision that produced them.

A single "version" field would make any one of these silently imply the others.

## 2. The manifest

The manifest is the only way the renderer obtains geometry.

```
contract, contract_major      format identity
asset                         namespaced id
revision                      sha256 over the pinned files (rule below)
files {mesh, lod1?, lod2?}     path + sha256 + bytes, resolved inside the owning root
coordinates                   "X beam; Y up; +Z forward"
pivot, bounds, nominal_scale  where it sits and how big it is
roles                         which of the six material roles the mesh fills
sockets?                      presentation-only attachment points
provenance                    author, tool, tool version, licence, source .blend
requires                      min engine, material profile, size ceilings
budgets                       measured triangles / draw calls / texture bytes
approval?                     decision id, revision, evidence
```

Rules that matter, all machine-checked:

- **`revision` is computed, not typed.** `sha256(asset + "\n" + "lod:sha256" joined by "\n" in
  ascending lod order)`. The validator recomputes it; a mismatch is a hard error. This is what
  makes `approval.reviewed_revision` meaningful.
- **Pinned files are verified.** Each `files[].path` must exist inside its root, be within the
  byte ceiling, and hash to the declared `sha256`. A manifest that names a file it does not ship
  fails.
- **The payload is validated as geometry**, not just as bytes: strict JSON (so a `NaN` vertex is
  refused rather than drawn), a finite 3-vector per vertex, batch rows in the exporter's
  `[nx, ny, nz, i0, i1, i2]` form, every index inside the vertex array, and
  `triangle_count` equal to the number of batch rows. An out-of-range index draws a garbled hull
  instead of failing loudly, which is exactly the failure a validator exists to catch.
- **The mesh must fit the declared envelope.** `bounds` is the conservative visual envelope;
  payload bounds outside it fail. Presentation may not silently grow past what camera, picking,
  contacts and shields were sized for.
- **Roles agree with the payload.** A manifest claiming a role the mesh does not fill means a
  material pass draws nothing. The six roles (`base`, `dark`, `trim`, `accent`, `lit`, `cool`)
  are the v1 compatibility target; a seventh role, or a shader, is a new major version with a
  declared fallback — never an extra string.
- **`bounds`/`nominal_scale` are presentation.** Collision, gameplay size, weapon range and
  checksums are not in the contract and a visual asset cannot reach them.

## 3. The registry

The registry is a list of bindings, one per rendered identity:

```
binding            rebel:battleship
category           combat_hull | station | satellite | planet_installation | …
identity           faction, class_or_kind, variant?, station_faction?
manifest           the asset id this binding resolves to
legacy_identifiers pre-contract export names this binding replaces (e.g. alliance_battleship)
shared_source_with other bindings resolving to the same revision
envelope           the envelope the binding may occupy
status             core | authoring_pending | procedural_legacy | keep_procedural_proposed | out_of_scope
```

`status` deliberately reuses the vocabulary of `art/manifests/model_inventory.json` so a coverage
report is a join of two files rather than a third hand-written list. The S01 inventory says what
exists today and what the owner decided about scope; the registry says what the renderer will
resolve. A row that is `authoring_pending` in the inventory and `core` in the registry is a bug,
and the join finds it without anyone re-reading the roadmap.

`legacy_identifiers` is how old saves, old replays and already-packaged builds keep working: the
resolver tries the binding, then the legacy name, and never asks for a save migration to make a
cosmetic upgrade work.

## 4. Resolution and fallback

```
entity → binding key → registry entry → (visual pack override?) → manifest → validated payload
```

1. A pack enabled later in the persisted order overrides the core binding. There is **no implicit
   precedence**: no filesystem enumeration, no directory-name ordering, no newest-file-wins. The
   order is the player's enabled list, and diagnostics print it.
2. If no pack overrides the binding, the core registry answers.
3. The manifest's `files[].path` is resolved inside the root that owns it: the game's `assets/`
   for core, the pack root for a pack. A pack cannot name a file outside itself.
4. Failure behaviour is split, because the two cases are not the same:

| Case | Behaviour |
|---|---|
| Missing or corrupt **core** export | A loud diagnostic plus the procedural legacy fallback, so a player is never left with an invisible ship. **Never counted as catalogue coverage:** the inventory row stays `procedural_legacy`, and the coverage report fails if a required core binding falls back. |
| Missing/invalid **pack** export | The pack is rejected transactionally before activation, with the reason; the next valid source is used. Never a partial activation, never a crash. |
| Unknown contract id or major version | Fail with a clear message. Silently reinterpreting a newer export is forbidden. |

5. A pack that adds models for entities core does not define must name the gameplay mod that
   defines them (`requires.gameplay_mod`, `adds[].entity_source`). A model pack does not create
   units and cannot make a faction playable.

## 5. Packs

A visual pack is render-only. It may replace a core binding or add a namespaced model for an
entity a gameplay mod already defines. It may not:

- carry executable content: no Python, no pickle, no `eval`, no `.blend`, no arbitrary shader code;
- write into the app bundle (packs live in a writable root outside it);
- change gameplay ids, sizes, collision, balance or checksums;
- introduce a binding that collides with core in an additive entry, or name the same binding twice.

Validation is transactional and happens before activation: unknown contract, oversized resources,
non-finite geometry, out-of-range indices, absolute paths, traversal and symlink escape from the
pack root are all rejections with a reason, not warnings. Texture memory is bounded as decoded
bytes, not only as file size.

Visual pack selection is separate from gameplay-mod selection. Pure visual packs stay outside
authoritative state, compatibility hashes and lockstep checksums, so two peers with different
visual packs must produce identical simulation. That has to be proven in S08, not asserted here.

## 6. Compatibility with what is already shipped

The three approved assets on `main` are migrated, not rewritten:

- `assets/models/alliance_{battleship,frigate,shipyard}.mesh.json` stay exactly where they are,
  byte-identical, and keep the exporter's legacy integer marker. The v1 payload format accepts
  `"schema": 1` during the migration window declared in `art/manifests/decisions.md` (D-07); the
  manifest pins them with their real hashes and records `export.legacy_schema_int: 1`.
- The migrated manifests are the **specimen migration** for S05: they describe what is on `main`
  today, and `art/schemas/examples/manifests/*.json` are their checked form.
- Existing saves and replays keep resolving: `legacy_identifiers` maps `alliance_battleship` →
  `rebel:battleship`, so a save naming the old export still finds a model.
- Frozen builds: `star_armada.spec` bundles `assets/`, so discovery under `sys._MEIPASS` must be
  verified rather than assumed. Pack roots are outside the signed bundle. This is a stated S04/S09
  obligation, not a solved problem here.

## 7. Caches and invalidation

Cache keys are the resolved pack revision and content revision plus the material/LOD profile —
never the entity type alone and never a path. Consequences:

- switching packs between sessions invalidates CPU geometry, GPU buffers, bounds and contact
  helpers coherently;
- GPU resources are scoped to the GL context and released on teardown; nothing survives a context
  recreation by accident;
- `approval.reviewed_revision` and the manifest `revision` move together, so an approval cannot
  silently keep applying to geometry it never saw.

Updates apply at a menu or session boundary. Live in-battle hot reload, workshop downloads and
executable mod scripting are out of scope unless separately approved.

## 8. Approval

Approval binds to an exact revision and to the evidence shown: `decision_id`, `decided_by`,
`decided_on`, `reviewed_revision`, `reviewed_evidence` (paths that must exist). A meaningful
visual change — geometry, material profile, exporter revision — invalidates the approval until it
is reviewed again; a filename alone carries nothing.

The validator enforces this mechanically: an `approved` manifest whose `reviewed_revision` is not
its current `revision`, or whose evidence is missing from the tree, fails. That is what stops a
later edit from leaving this document's approvals looking valid.

## 9. Budgets and LOD

Initial expectations, to be confirmed by measurement, not adopted as universal ceilings:

| Class | Triangles | Draw calls | Texture bytes |
|---|---|---|---|
| combat hull | ≤ 12,000 | ≤ 8 | ≤ 8 MiB |
| squadron / small craft | ≤ 2,500 | ≤ 6 | ≤ 4 MiB |
| station | ≤ 16,000 | ≤ 10 | ≤ 16 MiB |
| satellite / planet installation | ≤ 6,000 | ≤ 8 | ≤ 8 MiB |

Measured against the approved trio: battleship 8,701 triangles / 6 roles, frigate 5,128, shipyard
7,935 — all inside the table, which is a sanity check on the table and not a claim about the
batches still to come.

LOD expectations: every supported LOD keeps the silhouette the owner approved; LOD selection is
presentation and may not change bounds, contacts or size. The specimen exports currently ship one
mesh with no lower-detail level, which is accepted debt recorded here rather than quietly ignored.
These numbers need the owner's agreement before S06 batches are authored against them — changing
them later changes visual quality, which is exactly the kind of change that needs a decision
record.

## 10. What this contract does not do

- It does not implement the resolver: S04 does, and until then the trio is still selected by the
  hardcoded identity checks in `render/faction_ships.py` and `render/faction_stations.py`.
- It does not switch any production default (S11), activate models, or approve any model design
  (S06 requires per-asset owner approval against an enumerated list).
- It does not cover the authoring pipeline (S03): source authority, reproducible exports, storage
  policy and the `build-model` / `export-model` / `validate-models` interfaces are S03's.
