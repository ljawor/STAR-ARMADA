# Rim Syndicate rework prototypes

Data-only visual pack holding the three Rim Syndicate hulls the faction never had:
`syndicate:bomber`, `syndicate:battleship`, `syndicate:supercapital`.

## Status: unapproved prototype, not activated by default

The pack is not listed in `assets/models/packs.json`, so nothing loads it unless a
caller asks for it by path with `AssetResolver.activate_packs()`. That is deliberate:
no appearance decision has been bound to these revisions yet, and the repo rule is
that an unapproved revision never reaches the default load path.

## Provenance

| | |
|---|---|
| Authored by | `tools/art/build_syndicate_imperium.py` (Blender 5.0.1, headless) |
| Design language | `tools/art/syndicate_imperium_designs.py` |
| Geometry API | `tools/art/syndicate_imperium_geometry.py` |
| Editable masters | `art/blender/syndicate_{bomber,battleship,supercapital}.blend` |
| Runtime meshes | `assets/models/syndicate_{stem}.mesh.json` in this pack |
| Manifests | `assets/models/manifests/{stem}.json` in this pack |
| Review stills | `artifacts/syndicate-rework/stills/` |

Rebuild all three (idempotent, refuses to overwrite accepted output):

```sh
blender -b --python tools/art/build_syndicate_imperium.py -- --replace-own --render
```

## Envelope

Each mesh is fitted inside the box measured from the live procedural geometry it
replaces (`render/fleet_geometry.ship_mesh`), recorded on the binding as its
containment box with decision `syndicate-rework-envelope-2026-10-23`. Measured
boxes, in world coordinates (X beam, Y up, +Z forward):

| binding | min | max |
|---|---|---|
| `syndicate:bomber` | -11.74, -4.93, -23.62 | 19.63, 12.00, 20.16 |
| `syndicate:battleship` | -53.48, -20.36, -141.68 | 84.63, 82.00, 124.80 |
| `syndicate:supercapital` | -71.84, -34.00, -197.33 | 116.68, 82.00, 175.20 |

The fit scale per axis is printed in the build report. Contained meshes keep the
legacy length, camera framing, collision radius and every simulation field.

## What is deliberately absent

No gameplay data rows. `tests/test_native_unit_catalogue.py` requires every declared
buildable ship to resolve an authored CPU mesh binding, and these three bindings are
still `authoring_pending` with no core manifest. Adding rows before bounded
registration would make a shipped unit unrenderable, so the rows land together with
the registration decision, after the appearance of these revisions is approved.
