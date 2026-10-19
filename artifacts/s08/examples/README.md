# S08 example-pack evidence

- `verification.txt`: real combined unittest output (34 tests) and builder `--check` output.
- `source-pins.json`: deterministic input pins and derived asset/revision/geometry facts.
- `approved-input-preservation.json`: original source, export, manifest, provenance and exporter SHA-256 values compared to git HEAD; all equal.

## Test-first delivery

Observed before creating the corresponding deliverables:

1. `test_shipped_packs_preserve_evaluated_geometry_with_role_only_remap` failed for both absent `visual-pack.json` files, then passed after generation.
2. `test_gameplay_fixture_loads_through_real_datastore_and_supplies_addon_entity` failed because `mods/s08_raiders_fixture/data/ships/rebel.json` was absent, then passed after adding the real loader fixture.
3. `test_installation_documentation_and_gameplay_readme_ship_with_examples` failed because `docs/VISUAL_MODEL_PACKS.md` was absent, then passed after documentation was added.

Additional regression checks exercise installation into a disposable external USER_DIR,
actual `configure_from_settings(settings, data_store=loaded)` activation, loader-owned
ship provenance, corrupt installed payload rejection, disabling, deterministic builder
output and original input pin integrity. Neither a GL context nor Blender is required.

The evaluated frigate's 4,424 vertices and 7,708 triangles are retained in each pack.
Only identity/contract metadata and the trim/accent material-role bijection change.
Parts metadata is remapped consistently. No owner approval applies to either derived
revision, and no screenshot/appearance acceptance or complete playable faction is claimed.

One verification run overlapped an in-progress shared-worktree asset_registry edit and
caught a transient override-tuple unpack mismatch; no out-of-scope files were edited.
A fresh full rerun after that edit completed passed; `verification.txt` is that rerun.
