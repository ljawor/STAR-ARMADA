# Alliance battleship — Blender authoring source

Original **Pelagic** visual study for the existing Alliance battleship catalogue entry. No external model, texture, or proprietary ship asset is used. Gameplay names, balance data, collision radii and catalogue length policy are unchanged.

## Build

From the repository root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python tools/art/build_alliance_battleship.py
```

Verified with Blender 5.0.1. This rebuilds the editable `art/blender/alliance_battleship.blend` and exports `assets/models/alliance_battleship.mesh.json`. Change the authored frames/detail placements in the script to reproduce edits; preserve a separately edited `.blend` before rebuilding because the authoring command deliberately reconstructs the scene.

The model uses the game's coordinate system: **X beam, Y up, +Z forward**. Named Blender objects retain material roles and editable bevel modifiers. Major forms are a continuous pressure vessel, flared armored ram, stepped deep keel, set-back raked bridge, separated aft drives with open bell throats, recessed machinery, naval identification bands, batteries, side service mouths and asymmetric sensors.

## Runtime contract

- Evaluated, triangulated Blender bevel geometry, not primitive proxies.
- 4,603 shared vertices, 8,701 triangles. Bounds `(-69, -31, -143.5)` to `(69, 61, 135)` model units.
- Six existing roles: `base` 3,329; `dark` 2,720; `trim` 1,740; `accent` 600; `lit` 112; `cool` 200 triangles.
- Structural pressure hull, bridge, drives and keel remain in `base` for existing LOD compatibility.
- Runtime mesh is approximately 595 KB; editable `.blend` approximately 164 KB. No runtime `bpy` import or Blender executable requirement.
- Each face is `[nx, ny, nz, vertex_index_a, vertex_index_b, vertex_index_c]`. Normals are derived from the quantized evaluated vertices.
- `render/authored_mesh.py` validates roles, dimensions, indices, budget, winding, face normals and metadata, then caches immutable tuples once. The existing faction facade retains its previous procedural hull as a warned missing/corrupt-art fallback.
- The existing all-role size policy preserves the battleship's catalogue length of **224.421225 world units**. No collision or simulation fields are changed.
- Runtime asset export SHA-256: `57a5496c539a0252a237ef7a3671509f705308416da3f2afe0c9555ff17e9fec`. Rebuilding twice produced byte-identical exports.

## Actual-renderer evidence

`artifacts/alliance_blender_battleship/` contains before/after close/detail/rear/tactical PNGs, `before-after-contact-sheet.jpg`, source manifests, camera plan, full focused-test output and `verification.json` with exact hashes/bounds.

Both variants use the same current renderer, normal fog/sensors, materials, 1280×800 framebuffer and actual 4× MSAA on Cocoa / Apple M4 / OpenGL 2.1 Metal. Immutable source seals and cameras bind both variants. Eleven captures per variant include frozen-repeat identity checks, and all 181 state-digest samples across 180 simulation ticks match. Rendering does not alter state; genuine combat events and shield/hull reductions were observed. Native sandbox protection and before/after inventories confirm user data/replays were unchanged.

Focused verification: **44 tests passed** (`test_alliance_blender_battleship`, `test_faction_ships`, `test_alliance_visual_slice`, `test_ship_sizes`, `test_detmath`). No full suite or LAN work was performed.

### Honest limits

The shape is materially different in-game, but the existing all-over noisy hull shading still dominates surfaces and mutes the intended accent/glazing/engine color separation. Global shading and `renderer.py` were deliberately not changed. Appearance is **not approved**. Tactical detail naturally reduces to silhouette. No Windows/native, frame-rate, paid-fleet-construction or release acceptance is implied. An optional low-angle view has the same horizon bar in both controls and is omitted from the contact sheet.

Reproducible capture harness, preserved before/iteration/final sources and all attempts remain under `/Users/lukaszjawor/.hermes/cache/scratch/graphics-blender-battleship/`; that scratch directory is ephemeral, while the selected evidence above is retained in the repository.
