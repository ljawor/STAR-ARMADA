# Alliance authored sources — the approved Blender trio

Editable Blender sources for the three model revisions the owner has approved, their reproducible
exporters, and the runtime exports the game consumes.

> **This file replaces the earlier battleship-only notes.** Those predated the material-pass fix and
> the later frigate/shipyard approvals and stated that appearance was *not* approved. That wording is
> historical. The current decision is recorded below and machine-readably in
> `art/manifests/approvals.json`; the per-asset evidence receipts are in `artifacts/`.

## 1. Assets and approval scope

| Gameplay binding | Source (`.blend`) | Exporter | Runtime export | Triangles | Model bounds |
|---|---|---|---|---|---|
| `rebel_battleship` | `art/blender/alliance_battleship.blend` | `tools/art/build_alliance_battleship.py` | `assets/models/alliance_battleship.mesh.json` | 8,701 | `(-69, -31, -143.5)` – `(69, 61, 135)` |
| `rebel_frigate` | `art/blender/alliance_frigate.blend` | `tools/art/build_alliance_frigate.py` | `assets/models/alliance_frigate.mesh.json` | 5,128 | `(-34, -10, -80.7)` – `(34, 25.4, 73)` |
| Alliance-owned shipyard | `art/blender/alliance_shipyard.blend` | `tools/art/build_alliance_shipyard.py` | `assets/models/alliance_shipyard.mesh.json` | 7,935 | `(-55.7, -17, -46.5)` – `(55.7, 39.4, 51)` |

The owner approved the shown Blender **geometry and material direction** for exactly these three
bindings. Original designs only; no external, purchased or proprietary model, texture or ship asset
is used. **Approval does not extend to any other model, faction or catalogue entry**, and it is not a
claim of complete engineering acceptance.

Approval is bound to the exact revisions recorded in `art/manifests/approvals.json` and to the byte
manifest in `art/manifests/approved-trio-source-hashes.json`. A meaningful visual revision invalidates
the affected approval until the owner reviews the change again.

## 2. Build

Blender **5.0.1**, from the repository root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
  --python tools/art/build_alliance_battleship.py
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
  --python tools/art/build_alliance_frigate.py
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
  --python tools/art/build_alliance_shipyard.py
```

`tools/art/alliance_common.py` is shared authoring support for all three exporters.

All three assets are **script-authoritative**: the exporter reconstructs the scene from authored
parameters, so a rebuild overwrites the `.blend`. **Preserve any hand-edited `.blend` elsewhere before
running a generator.** Binary `.blend` metadata is not claimed reproducible; the *runtime* exports are
(rebuilding produced byte-identical output for the same declared inputs and toolchain — see
`artifacts/alliance_blender_trio/rebuild-verification.json`).

## 3. Runtime contract

- Evaluated, triangulated Blender geometry (bevel modifiers applied), not primitive proxies.
- Coordinate system matches the game: **X beam, Y up, +Z forward**. Bounds above are model units; the
  renderer's own size policy rescales the hull into place (section 4).
- Each face is `[nx, ny, nz, vertex_index_a, vertex_index_b, vertex_index_c]`; normals derive from the
  quantized evaluated vertices. Structural pressure hull, bridge, drives and keel stay in `base` for
  existing LOD compatibility.
- Six existing material roles with no new ones: `base`, `dark`, `trim`, `accent`, `lit`, `cool`.
  Per-asset role triangle counts, re-counted from the exports on this branch:

| Asset | base | dark | trim | accent | lit | cool | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| battleship (4,603 vertices) | 3,329 | 2,720 | 1,740 | 600 | 112 | 200 | 8,701 |
| frigate (2,704 vertices) | 2,132 | 1,144 | 1,220 | 432 | 112 | 88 | 5,128 |
| shipyard (4,269 vertices) | 3,223 | 1,380 | 2,316 | 564 | 196 | 256 | 7,935 |

- Runtime exports: battleship 594,859 bytes, frigate 358,072 bytes, shipyard 505,314 bytes. Editable
  `.blend` sources are 163,806 / 133,841 / 160,484 bytes.
- `render/authored_mesh.py` is a GL-free, bounded loader. It validates schema, asset identifier, role
  set, vertex/triangle/byte budgets, indices, finiteness, winding, face normals and metadata before
  returning deeply immutable role batches, cached once. Current limits: 2,000,000 bytes,
  10,000 vertices, 12,000 triangles per asset.
- **No runtime `bpy` import and no Blender executable requirement.** Editable `.blend` files and the
  authoring tools are development sources and must not be packaged into the game.
- The shipyard export declares four named worklight features in its metadata; the battleship export
  predates that `features` field and carries no such block. Both are valid under schema 1.
- A missing or corrupt export raises; the faction facade catches it, warns once, and falls back to the
  previous procedural hull so a saved battle still loads. That fallback is a recovery path, **never**
  catalogue coverage.

## 4. Size, gameplay and state

- The renderer-only size policy scales each authored hull to the pre-existing catalogue length:
  battleship **224.421225** world units, frigate **96.180525**; the shipyard keeps its unchanged data
  radius of 110 and is drawn at `radius / 50`. These were re-measured on this branch through
  `render.ship_sizes.ship_size`, not copied from an earlier report.
- Collision radii, weapon ranges, health, ownership, build rules, save/replay data and
  `state_sha256` semantics are unchanged. Rendering reads state only.

## 5. Activation boundary — read before integrating

These three assets are currently selected by **hardcoded identity checks** in the renderer
(`render/faction_ships.py` for the battleship and frigate shape keys, `render/faction_stations.py` for
`faction == "rebel" and data_id == "shipyard"`). There is **no persisted preview/default switch**.

Therefore:

- This is a **preview prototype**, not a catalogue switch. The production default remains legacy, and
  none of these assets exist on `main` at all.
- **S04** (with the **S02** contract) must replace the hardcoding with an explicit, persisted,
  reversible opt-in selection before any production art merge or wider rollout.
- Nothing here authorizes merging, tagging, releasing, or switching the default.

## 6. Evidence

Every path below is committed in this repository.

| Claim | Evidence |
|---|---|
| Review set, three assets in-game at common scale, motion | `artifacts/alliance_blender_trio/README.md`, `three-asset-review.jpg`, `trio-in-game.png`, `before-after-contact-sheet.jpg`, `before-after-aft-drives.jpg`, `before-after-motion.mp4` |
| Focused tests, per-tick state equality, user-data preservation, GL/quality context | `artifacts/alliance_blender_trio/verification.json` |
| Byte-exact rebuild of the runtime exports | `artifacts/alliance_blender_trio/rebuild-verification.json` |
| Four individually visible yard worklights (removed-and-measured) | `artifacts/alliance_blender_trio/worklight-pixels.json`, `pixel-checks/metrics.json`, `pixel-checks/*.png` |
| Capture/probe workflows, RED/GREEN logs, scoped diffs | `artifacts/alliance_blender_trio/evidence/` |
| Battleship material-pass before/after comparison | `artifacts/alliance_battleship_materials/before-after-contact-sheet.jpg`, `verification.json`, `before-after-motion.mp4` |
| Battleship geometry approval comparison | `artifacts/alliance_blender_battleship/` |

The full uncropped per-frame captures (`artifacts/alliance_blender_trio/baseline/`,
`artifacts/alliance_blender_trio/candidate/`), the showcase reel and poster
(`artifacts/showcase/`, `artifacts/star_armada_fight.mp4`, `artifacts/fight_poster.png`) and the
per-iteration material diagnostic runs are **not** committed: they are raw capture output, excluded
deliberately under the roadmap's storage rule. The contact sheets above use identical crops on both
variants, so they carry the comparison; the raw sets are not the source of truth for any claim.

## 7. Honest limits and acceptance debt

- Evidence is macOS / Apple M4 / Cocoa / OpenGL 2.1 Metal, 1280×800 framebuffer, real 4× MSAA, normal
  fog and the unchanged global material shader. **No Windows-native, packaged or frozen-build
  acceptance** exists for the trio.
- Specimens were placed with real factory entities and real combat commands, **not** a paid
  construction walkthrough.
- Tactical/play-distance views reduce detail to silhouette; this is expected, not a defect.
- An earlier whole-suite (1,671-test) art-integrated run had one LAN recovery `tick 6 != 8` failure
  that later isolated repetitions did not reproduce. The cause is **not** established and it is **not**
  classified as fixed. Four replay additions during that run were confirmed by the owner as their own
  and were left untouched.
- The trio's hardcoded activation has not been reviewed for the explicit preview gate that S04 owns.
