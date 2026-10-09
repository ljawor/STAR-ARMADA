# Faction hardware

Faction identity comes from geometry, not ownership paint. The Galactic Imperium keeps its existing meshes and material treatment; the other factions follow the approved faction geometry studies.

| Faction | Ship language | Station language |
|---|---|---|
| Galactic Imperium | Existing needle escorts, tapered capitals, tiered bridges | Existing hardware, unchanged |
| Free Systems Alliance | Rounded segmented hulls, separated twin nacelles, open hangars | Linked habitats and oval/open frames |
| Automated Legions | Forked bows, repeated hexagonal machinery, robotic fabrication | Threefold hubs, repeated machine cells and docks |
| Outer Rim Syndicate | Asymmetric barges, offset bridges, unequal armor, exposed cargo | Salvaged module clusters, unequal docks and cranes |

This is a renderer-only feature. Ship statistics, collisions, weapons, faction availability and save/replay data are not redesigned. Syndicate remains non-playable in the current catalogue; its existing units and stations nevertheless have dedicated geometry for scenarios/mods that use them.

## Coverage

All existing ship catalogue entries receive the appropriate faction geometry, including fighters, bombers, escorts, capitals, constructors and colonizers wherever that faction has those classes. Data-less commercial convoys use their owner's faction. Missing catalogue classes are not added.

All ten shared station IDs have faction variants: command, mining, shipyard, research, defense, sensor, trade, fighter platform, repair dock and energy relay. Shared stations follow the owning player's faction; ordinary catalogue ship hardware follows its recorded faction. Player colors remain a separate ownership channel.

New hardware uses the existing six material roles and production hull shading. All-role mesh bounds must feed normalized ship size, visual contact mapping and camera safety. Geometry and display-list caches must remain bounded by canonical faction/role/type keys, never arbitrary mod IDs or per-entity state.

## Verification

Run the headless suite:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
```

Run the production SDL/OpenGL catalogue probe on a real window server (do not use SDL's dummy video driver):

```sh
PYTHONPATH=. SDL_AUDIODRIVER=dummy .venv/bin/python tools/diag_faction_hardware.py --out /path/to/output
```

The probe captures all catalogue ships, all 40 faction/station combinations and four faction convoys. It checks nonempty unclipped subjects, OpenGL errors, exact full-precision state preservation, player-color differentiation and shield rendering. It compares Imperial meshes and pixels against the pre-feature commit, and checks non-Imperial station pixels differ from the legacy renderer. All 40 station placements have valid/invalid framebuffer controls and caller-state restoration checks; all 40 construction sites render, with outline-disabled differential controls for the 30 new faction variants. Close-camera tests require the expected visible station obstacle and an active keep-out for each faction before checking safety. Contact sheets use individual framing and are **not** ship-size comparisons.

Factory/DamageSystem regression tests verify contact placement on actual all-role triangles at rotated/scaled transforms, including rays through docking or fork gaps. Ray misses use nearest triangle surfaces, not the entity center; Imperial contact and shield behavior remain protected.

Existing close-camera and ship-size diagnostics remain important regression checks:

```sh
PYTHONPATH=. SDL_AUDIODRIVER=dummy .venv/bin/python tools/diag_close_zoom.py --out /path/to/close-camera
PYTHONPATH=. SDL_AUDIODRIVER=dummy .venv/bin/python tools/diag_ship_sizes.py --out /path/to/ship-sizes
```
