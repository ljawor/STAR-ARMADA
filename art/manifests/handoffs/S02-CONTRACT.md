# Handoff: S02 — freeze the extension contract

Status: **review-ready** (schemas, examples, validator and decisions are in; the owner review of
the class budgets/LOD table and the legacy-migration window is the gate)

Base commit / branch: `ce431086dcfd2416306a1341c837d2560d7729c5` (`main`) on
`docs/s02-extension-contract`, worktree `<scratch>/star-armada-s02`

Prerequisites verified:

- S01's inventory and the owner's scope decision are merged on `main` (`ce43108`); this contract
  reuses the S01 status vocabulary instead of inventing a second one, so the two join.
- The three approved assets are on `main` since `c5b78eb` (PR #114). Their hashes are pinned in the
  migrated manifests, so this work cannot drift from what the owner approved without failing.
- No local prototype state is involved: everything here is derived from committed `main`.

What this step delivers:

| Artifact | Content |
|---|---|
| `docs/ASSET_EXTENSION_CONTRACT.md` | the contract in prose: identity and versioning, resolver and fallback, pack rules, compatibility with what already ships, caches, approval binding, budgets and LOD |
| `art/schemas/model-manifest.schema.json` | v1 manifest: pinned files + computed revision, envelope, six roles, provenance, engine requirement, approval |
| `art/schemas/binding-registry.schema.json` | v1 registry: canonical `<faction>:<class-or-kind>` binding → asset, with the S01 status vocabulary and legacy export names |
| `art/schemas/visual-pack.schema.json` | v1 render-only pack: replaces core bindings, adds namespaced models for entities a gameplay mod defines |
| `art/schemas/examples/` | the three approved assets migrated to manifests, a registry excerpt, one replacement pack and one additive pack with their payloads |
| `art/schemas/examples/invalid/` | 24 negative controls plus one runtime control, each with the rejection code it must produce in `EXPECTED.json` |
| `tools/art/validate_contract.py` | runs all of it; exit 0 only when valid documents pass *and* every control is rejected |
| `tests/test_asset_contract.py` | the same check as a suite test, asserting counts so a validator that skips its input cannot pass |
| `art/manifests/decisions.md` | 17 numbered decisions with what enforces each, plus the three items that need the owner |

What changed visibly:

Nothing the game draws. This PR adds documents, schemas, examples and a validator; no renderer,
gameplay or asset file is touched. The trio still resolves through the hardcoded identity checks
in `render/faction_ships.py` and `render/faction_stations.py`, which S04 replaces with the resolver
specified here. No production default changes, no model is activated, no model design is approved.

Verification (run for real at this head):

```
python3 tools/art/validate_contract.py
  → contract satisfied: 33 checks, 25 negative controls, 0 skipped   (exit 0)
python3 -m unittest tests.test_asset_contract
  → Ran 4 tests ... OK
```

The 8 valid documents include the three real approved exports, whose payloads are validated as
geometry: finite positions, `[nx, ny, nz, i0, i1, i2]` batch rows, every index inside the vertex
array, `triangle_count` equal to the batch row count (battleship 8,701 / frigate 5,128 / shipyard
7,935), and mesh bounds inside the declared envelope. The 25 controls cover every rejection rule,
including one symlink escape that cannot be committed as a file and is therefore built at runtime.

Retained failed attempts and corrections:

- The first validator checked only hashes and accepted payloads whose `batches` were not triangle
  lists. It was replaced by the geometry check above — a hash proves the file is the one we meant,
  not that it is a usable mesh.
- Its first run also rejected its own schemas (`maxLength` was outside the supported keyword set).
  The evaluator now either implements a keyword or refuses it, so a schema cannot be half-enforced.
- A registry `manifest` field was initially treated as a path, which is wrong: an asset id is not a
  path. Path safety now applies to genuine path fields, plus a pack's own manifest entries.
- Two negative controls initially produced the wrong code because structural failures fired before
  the intended rule. The registry now detects duplicates before the join it cannot satisfy, and the
  manifest envelope is ordered before anything is measured against it.

Open issues, blockers and decisions required:

1. **Class budgets and LOD expectations** (contract §9) need the owner's agreement before S06
   authors against them. They are proposed from the approved trio's measurements.
2. **The legacy-payload migration window** (decisions D-07). The trio ships with the bare integer
   `"schema": 1`; migrating means re-exporting files the owner approved, so it is a decision with a
   re-approval attached, not a cleanup.
3. **Whether the shipped packs are examples or acceptance material** (contract §5). This decides
   how much of the pack section has to be proven with a second real pack in S08.
4. Nothing here is implemented. The resolver, the persisted enabled-pack order and the
   visual/gameplay pack separation are S04 and S08 work, and the frozen builds' `sys._MEIPASS`
   asset discovery remains unverified.

Next executable step and its acceptance criteria:

**S03 — build a durable authoring pipeline.** Generalise the evaluated export and validation
without destroying hand edits, add the export-only path for blend-authoritative assets, declare
source authority per asset, record toolchain versions, and make `build-model` / `export-model` /
`validate-models` reproducible from a fresh clone on macOS and Windows with nonzero failure exits
and no user-data writes. Gate: *reproducible trio builds from a fresh clone, source ownership and
storage policy.* This contract is the specification S03's exporter must satisfy; `validate-models`
should be the existing validator, not a second opinion.

Do not start a catalogue batch, do not activate any model, do not merge a design approval, and do
not close the legacy migration window without the owner.
