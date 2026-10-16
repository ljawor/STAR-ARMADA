# Model preview and visual-pack selection

## 1. Activation boundary

The stock default is **legacy procedural models**. Settings → Readability & help →
**Blender model preview (next session)** is an explicit opt-in. The choice is persisted in
`saves/settings.json` beside the other presentation preferences. It is not stored in game saves,
replays, gameplay-mod compatibility hashes or simulation state.

The application applies selection after the old renderer closes and before constructing the next
session renderer. Switching with any live renderer is refused, including while current and candidate
renderers coexist during recovery. This is not in-battle hot reload. Disabling preview returns to
legacy without changing a save. S11 remains a separate, owner-authorized catalogue-default switch.

## 2. Enabled pack order and writable paths

Preferences, in explicit ascending precedence order:

```json
{
  "model_preview": true,
  "visual_packs": ["escort-red", "escort-blue"]
}
```

Install each data-only pack at `<USER_DIR>/visual_packs/<directory>/visual-pack.json`. Use directory
names made from letters, digits, dots, underscores or hyphens, starting with a letter or digit.
The enabled list is edited in settings JSON; the menu displays its count, not a pack-order editor.
**Later valid entries override earlier valid entries.** Filesystem enumeration never establishes
precedence. Duplicate directory names and duplicate pack identities are errors, not last-one-wins.

`USER_DIR` follows the existing application rule:

- Source run: the source checkout (never use the owner's live checkout for acceptance probes).
- Frozen macOS: `~/Library/Application Support/STAR ARMADA`.
- Frozen Windows: `%APPDATA%/STAR ARMADA`.
- Frozen Linux: `$XDG_DATA_HOME/STAR ARMADA`, or `~/.local/share/STAR ARMADA`.

Packs must stay outside a frozen bundle. Traversal, absolute payload paths and symlink escapes are
rejections. The runtime reads only JSON triangle data and the supported six material roles; it
refuses executable files, Blender sources and pack-provided material profiles. No Blender dependency
is imported by the game.

## 3. Validation, fallback and approval

`render/asset_registry.py` resolves canonical `<faction>:<class-or-kind>` keys; unknown bindings
fail with `E_UNKNOWN_BINDING`. Explicit legacy export aliases remain supported. Missing/corrupt core
assets produce diagnostics and procedural fallback, but never count as required-core coverage.
Invalid packs are rejected transactionally before activation; their valid entries cannot partially
replace the previous source.

Owner policy `s04-pack-envelope-2026-10-16` requires checking replacement meshes against the target
binding's **approved envelope**. One oversized replacement rejects its whole pack. This runtime check
does not apply authoring extent grace and never changes gameplay collision radii. Bindings without an
approved envelope cannot accept a replacement until the envelope is established.

An additive pack must declare its gameplay dependency and bind to an entity already supplied by that
dependency. S04 exercises the resolver with an explicit validated gameplay-entity fixture and a real
export, including the ship-size/fleet facade path. Public gameplay-mod dependency discovery and
mixed-peer/save/replay compatibility acceptance remain S08 work; the normal application's boundary
currently supplies no additive dependency map and therefore safely rejects additions rather than
inventing gameplay entities. Replacement packs require no gameplay dependency.

Approved manifests carry a packaged receipt pinning the complete manifest, reviewed revision,
decision id and original evidence hashes. This is a **build-time attestation, not a cryptographic
signature or a new owner approval**. It allows runtime validation without shipping `art/` or review
movies. Source checks reproduce the receipt from the real evidence. Mods may remain unapproved in
opt-in preview; that never grants them catalogue approval or production activation.

## 4. Runtime metadata and resource lifetime

The packaged dependency closure lives under `assets/models/`: registry, catalogue map, manifests,
three schema files and approval receipts. `sys._MEIPASS` supplies the frozen root; editable `.blend`
sources and authoring tools are not bundled. The original three mesh exports remain byte-identical.

Regenerate/check metadata without Blender or mesh writes:

```sh
python3 tools/art/sync_runtime_metadata.py --write
python3 tools/art/sync_runtime_metadata.py --check
```

The catalogue map preserves all 120 inventory identities. Today's crew-transport and commercial
convoy identities share four runtime bindings; three planned Syndicate keys are also declared.
This yields 119 runtime keys, **not** 119 approved or authored models. Pending entries remain
procedural; this step does not claim S07 catalogue-wide render-path integration.

Manifest and mesh reads are capped at 2,000,000 bytes per file; meshes at 10,000 vertices and 12,000
triangles. The geometry LRU defaults to 64 entries; failed resolutions have a bounded cache too.
Enabled packs are capped at 32, pack traversal at 4,096 entries, and retained diagnostics at 256.
These defensive limits are not the unresolved owner advisory draw-call/texture-memory budgets.
Textures and additional material profiles are not implemented by this initial six-role path.

GPU list keys include resolved content/pack revision and material/LOD identity; their owning renderer
provides GL-context scope. Teardown releases all lists. Accepted session changes clear geometry,
bounds, contact-ray and camera-derived helpers together; no resource may survive a recreated context.

For diagnostics, call `render.asset_selection.diagnostics()` after activation. It reports effective
mode, generation, the persisted enabled order, accepted/rejected pack order and error codes. The
application also logs the boundary result through `render.asset_selection`.

## 5. Verification and remaining gates

`artifacts/s04_generic_preview/verification.json` and `review-sheet.png` record eight real-driver
frozen views: prototype at `5bddd7b` versus generic preview, plus legacy as a discriminating negative
control. All preview channels match; simulation hashes match; 1280×800, 4× MSAA, normal fog and
production shaders were used. Selected full-resolution captures and reproducible scripts are kept
beside the report.

This is S04 engineering parity, **not** S05's complete colour/motion/combat approval transfer, S08's
public mod-compatibility matrix, S09's actual Mac/Windows package acceptance or permission for S11.
No native Windows render or built package is claimed from source/frozen-path unit tests.
