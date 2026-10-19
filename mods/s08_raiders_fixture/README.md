# S08 Raiders gameplay fixture

Test/development-only catalogue extension; not a playable faction or balance proposal.
Load with `DataStore(mods=['s08_raiders_fixture'])` after `import game.core`.

- Actual loader input: `data/ships/rebel.json` (a recognized loader filename).
- New gameplay ID: `s08_raiders_scout`.
- Explicit faction/category: `raiders` / `scout`; render binding `raiders:scout`.
- Visual dependency source: `gameplay:s08_raiders_fixture`.
- Compatible visual example: `examples/visual_packs/raider-addon/visual-pack.json`.
- `DataStore.mod_files` records the raw input under `data/ships/rebel.json`.

Only one ship is merged. Core IDs, factions, rules and build menus are not changed.
Stats intentionally mirror the built-in Rebel frigate (its default `veteran_xp` is
100). No new weapons, abilities, faction definition, build unlock or mission is
introduced. A visual pack alone does not create this unit. The `scout` category is
for the binding test and is not a claim of full engine/UI support for new categories.

The gameplay-mod loader currently uses app/source `ROOT/mods`, unlike writable
external visual packs. Keep this fixture in source-development/test deployments;
do not copy it into a signed application. Do not move this data into the visual pack.
See `docs/VISUAL_MODEL_PACKS.md` for install, preview/order, disabling and diagnostics.
