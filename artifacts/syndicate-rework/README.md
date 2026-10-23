# Rim Syndicate rework — evidence

The three hulls the faction never had, registered into the core catalogue:
`syndicate:bomber` (Cutthroat Strike Wing), `syndicate:battleship` (Marauder
Battleship) and `syndicate:supercapital` (Leviathan Salvage Dreadnought).

Stations were never missing: the registry carried 26 Syndicate bindings against
26 Imperial ones, station for station, and the shipyard's `builds_ships: ["*"]`
already built anything the faction declared. The gap was three ship bindings
with `authoring_pending` and no mesh behind them.

## What is here

| path | what it proves |
|---|---|
| `stills/` | quarter/profile/bow stills of each hull, rendered through the same camera and lights as the accepted `imperial_battleship.blend` benchmark |
| `stills/imperial_battleship-*.png` | that benchmark, same renderer, same session |
| `build/all.json` | the build report: triangles, vertices, parts, bounds and the per-axis fit scale |
| `captures/` | the hulls drawn by the running game through ordinary `main.py` |

## Reproduce

```sh
# author the hulls (Blender 5.0.1, headless, idempotent)
blender -b --python tools/art/build_syndicate_imperium.py -- --replace-own --render

# register the meshes, manifests, receipts and pipeline batch
.venv/bin/python tools/art/register_syndicate_prototypes.py

# see them in the real game, isolated profile, source run only
.venv/bin/python tools/play_syndicate_fleet.py --focus marauder --capture artifacts/syndicate-rework/captures/marauder.png
```

## Containment

Each mesh is fitted inside the envelope measured from the live procedural
geometry it replaces (`render/fleet_geometry.ship_mesh`). The measured box is the
binding's containment box and the loader rejects anything outside it, so in-game
length, camera framing, collision radius and every simulation field stay put.

| binding | min | max |
|---|---|---|
| `syndicate:bomber` | -11.74, -4.93, -23.62 | 19.63, 12.00, 20.16 |
| `syndicate:battleship` | -53.48, -20.36, -141.68 | 84.63, 82.00, 124.80 |
| `syndicate:supercapital` | -71.84, -34.00, -197.33 | 116.68, 82.00, 175.20 |

## Gates

- 132 tests OK: asset selection, native unit catalogue, asset registry, asset
  contract, pack safety, station balance.
- `test_runtime_asset_metadata`, `test_s07_registration`,
  `test_s06_appearance_records` and `test_s07_scaffold_registration` are red on a
  pristine `git archive HEAD` baseline in this environment (a pinned registration
  file, `render/renderer.py`, is absent from the tree). Untouched here.

## Not in this batch

The 23 existing Syndicate meshes keep their current authoring. Re-authoring them
in this design language is a separate batch with one approval record per asset.
