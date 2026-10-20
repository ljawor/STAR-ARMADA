# Visual model packs: S08 examples

These are installable **data-only compatibility examples**, not new model designs or
new owner appearance approvals. The catalogue itself became the production default in S11; these
example packs stay outside that default and alter no approved `.blend`, mesh, manifest, receipt or
release-asset-lock pin.

The shipped default selection is a different list: the thirteen owner-approved Imperial models in
`visual_packs/` — six ships, three stations and four dockyard units (decisions
`imperium-prototype-default-selection-2026-10-20`, `imperial-station-prototypes-2026-10-20` and
`imperial-dockyard-prototypes-2026-10-20`, see `MODEL_PREVIEW.md` §1). None of the two examples
below is enabled by default.

See `ASSET_EXTENSION_CONTRACT.md` and `art/schemas/` for normative v1 contracts.

## What ships

| Folder in `examples/visual_packs/` | Pack ID | Operation | Derived asset |
|---|---|---|---|
| `core-frigate` | `example:core_frigate` | replaces `rebel:frigate` (explicit `replace_of: core:alliance/frigate`) | `example:alliance/frigate` |
| `raider-addon` | `example:raider_addon` | adds `raiders:scout` from `gameplay:s08_raiders_fixture` | `example:raiders/scout` |

Each directory includes `visual-pack.json`, `SOURCE.md`, a model manifest under
`assets/models/manifests/`, and a `.mesh.json` under `assets/models/`. Copy the entire
directory, not just its descriptor. No scripts, Blender files, shaders or gameplay data
belong inside a visual pack.

Both use the real evaluated Alliance frigate export: 7,708 triangles, six material
roles, no textures, one LOD. The only appearance change is a bijective `trim` ↔ `accent`
role remap (including `parts[].role` metadata). Every vertex, triangle index, normal,
bound, pivot and nominal scale is retained. The scout intentionally reuses the full
frigate hull; its name does not claim a newly authored or downscaled small craft.
`SOURCE.md` records original input hashes and attribution. The input was exported from
Blender; the derivation itself is Python JSON processing, not a new Blender evaluation.

The derived payloads use `star-armada/mesh-export`, `contract_major: 1`, namespaced
asset identities and freshly computed file hashes and revisions. They do not carry
legacy `schema: 1`, `export.legacy_schema_int` or inherited `approval`. The original
revision's approval is not transferable to a role remap or another identity.

## Install outside the signed application

Put the two folders in **`USER_DIR/visual_packs/`**:

```text
USER_DIR/
  saves/settings.json
  visual_packs/
    core-frigate/visual-pack.json
    core-frigate/assets/models/frigate.mesh.json
    core-frigate/assets/models/manifests/frigate.json
    core-frigate/SOURCE.md
    raider-addon/visual-pack.json
    raider-addon/assets/models/scout.mesh.json
    raider-addon/assets/models/manifests/scout.json
    raider-addon/SOURCE.md
```

`USER_DIR` is the writable user-data root, not `assets/` or the application's
`Contents/Resources` directory. Frozen application defaults are:

- macOS: `~/Library/Application Support/STAR ARMADA`
- Windows: `%APPDATA%/STAR ARMADA`
- Linux: `$XDG_DATA_HOME/STAR ARMADA` (or `~/.local/share/STAR ARMADA`)

In a source checkout, `render.menus.USER_DIR` currently equals the repository root.
Thus source development uses `<checkout>/visual_packs/`; it must not be mistaken for
permission to edit a packaged/signed bundle. The GL-free resolver also supports an
explicit external `pack_root`, useful for isolated tooling/tests.

## Enable, order and preview

With the game closed, merge these fields into `USER_DIR/saves/settings.json` while
preserving other settings:

```json
{
  "model_preview": true,
  "visual_packs": ["core-frigate", "raider-addon"]
}
```

The settings list contains **directory names**, not pack IDs, absolute paths or
manifest filenames. It is unique and ordered, with a maximum of 32 entries. Discovery
is not alphabetical: the later accepted pack wins when multiple packs replace the
same binding. These two examples target different bindings, so neither masks the other.
A pack with any rejected entry is rejected transactionally; an earlier valid source
remains usable. Setting `model_preview` to false selects legacy presentation and does
not activate packs even if their directory names remain saved.

## The gameplay fixture is separate

`raider-addon` requires a real loaded gameplay mod, not just a string saying it is
installed. The source fixture lives at `mods/s08_raiders_fixture/` and is loaded with:

```python
import game.core  # Required project import prelude before direct DataStore imports.
from game.data.store import DataStore

ds = DataStore(mods=['s08_raiders_fixture'])
scout = ds.resolve_ship('s08_raiders_scout')
assert (scout.faction, scout.category) == ('raiders', 'scout')
```

The actual loader currently visits only its known ship filenames; the new ship is
therefore in `data/ships/rebel.json`, although its explicit faction is `raiders`.
The file merges only this one ID; it does not overwrite core Rebel ships. Its raw
content is recorded under `ds.mod_files['data/ships/rebel.json']`. The
session integration derives provenance from the loader-owned
`ds.ship_mod_sources['s08_raiders_scout'] == 's08_raiders_fixture'` rather than trusting
files merely present on disk. Visual packs themselves cannot create catalogue entries.
`render.asset_selection.active_gameplay_entities(ds)` maps the effective ship loader
provenance to `{'gameplay:s08_raiders_fixture': {'raiders:scout'}}`. Later gameplay
writers supersede earlier provenance for the same ID.

Application sessions call the implemented seam
`configure_from_settings(settings, data_store=gm.ds)`; `main.py` supplies the actual
session DataStore. This supports **ship additions only**, not station additions.
For GL-free resolver tooling, reuse the same helper rather than inventing entity evidence:

```python
from pathlib import Path
from render.asset_registry import AssetResolver
from render.asset_selection import active_gameplay_entities

resolver = AssetResolver(gameplay_entities=active_gameplay_entities(ds))
external = Path('/your/writable/visual_packs')
resolver.activate_packs(
    [external / name / 'visual-pack.json' for name in ('core-frigate', 'raider-addon')],
    pack_root=external,
)
print(resolver.active_order)
print(resolver.diagnostics)
```

Without that active gameplay entity evidence the addon is rejected; the independent
core replacement remains valid. Do not fake the evidence in an application session.

### Engine limitations

This fixture is not a complete playable Raiders faction, build menu, AI faction,
mission, balance proposal or campaign integration. Its stats mirror the core frigate
and its unknown `scout` category is sufficient for catalogue/render routing, not a
promise that every core UI/gameplay category branch supports it. No faction definition
or build unlock is added. Enable the gameplay fixture only in explicit tests or
controlled source-development sessions.

The current DataStore gameplay-mod loader reads `ROOT/mods/<name>`, where `ROOT` is
the app/source root; it does **not** discover gameplay mods from `USER_DIR/visual_packs`
or offer a general external gameplay-mod installer here. Do not modify a signed bundle
to install this fixture. External installation above applies to visual packs only.
Actual session activation must use its loaded DataStore, including when reconstructing
a save/replay, rather than a catalogue made from invented dataclass replacements.

## Updates and disabling

Exit the battle and close the game before replacing a complete pack folder. Reopen at
a session boundary so validation and content-keyed caches are rebuilt. There is no
live in-battle hot reload, workshop downloader or executable extension mechanism.
When publishing an update, regenerate file bytes, SHA-256 pins, asset revision and
pack version together; never retain an old approval for edited content. Back up user
settings and keep the same directory name if the saved selection should remain valid.

Remove `raider-addon` or `core-frigate` from `visual_packs` to disable individually;
`"visual_packs": []` restores core authored selection while preview stays true.
`"model_preview": false` restores legacy selection. Disable the addon before removing
its gameplay fixture. A missing/invalid pack also fails validation rather than partly
loading. These visual preferences do not install gameplay mods or authorize removing
a gameplay dependency from an existing save or replay.

## Diagnostics and validation

Check `render.asset_selection.diagnostics()` at a session boundary (or the model
selection entry in application logging). `enabled_order` is the persisted directory
list; `pack_order` records per-pack acceptance/rejection and reason, and `issues`
contains resolver diagnostics. For standalone tooling inspect `resolver.active_order`
and `resolver.diagnostics`. Useful reasons include `E_GAMEPLAY_ENTITY` (missing or
mismatched entity evidence), `E_FILE_HASH` (edited/corrupt payload), `E_UNSAFE_PATH`
(traversal), `E_EXECUTABLE_CONTENT`, `E_UNKNOWN_CONTRACT`, `E_ENGINE_VERSION`,
`E_DUPLICATE_ID`, `E_ASSET_COLLISION` and `E_EXTENT_DRIFT`. A missing gameplay
requirement may report a dependency diagnostic before the entity check. Read the
actual code/message rather than assuming every refusal is an install failure.

Do not edit pin values to silence corruption. Reinstall the complete validated pack.
The loader enforces safe contained paths, finite geometry, index validity, six known
roles, byte/triangle ceilings and binding envelopes; a manifest is not an escape hatch
for arbitrary model growth. Only the supported material profile and LOD are provided.

From the checkout (no GL, no Blender required):

```sh
python tools/art/build_s08_examples.py --check
PYTHONPATH=tests:. python -m unittest test_s08_example_packs -v
```

To intentionally regenerate derived data after reviewing source changes, run
`python tools/art/build_s08_examples.py` and review the new pins and revisions.
The builder only writes the example folders and
`artifacts/s08/examples/source-pins.json`; it never writes approved input files.
These checks verify data/installability and provenance, not new screenshot evidence,
owner appearance approval, full simulation compatibility or packaged-build acceptance.
