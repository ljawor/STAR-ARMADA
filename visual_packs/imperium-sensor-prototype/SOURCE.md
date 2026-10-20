# Galactic Imperium Sensor Station — visual prototype

An original Blender-authored asset in the visible-first replacement series. Replaces only
`imperial:sensor_station`; every core approved asset and gameplay definition is unchanged.

## Design

armoured base with twin sensor drums, braced lattice mast, great vertical scanner hoop with clamp ribs, and a dish-and-antenna crown. Homeworld-influenced silhouette language only: no proprietary geometry,
textures or purchased assets.

## Play

Run `Play Station Prototypes.command` from the repository to open the real game in a stock
Imperial skirmish with this station selected and framed. Test saves and settings stay beneath
`~/Library/Application Support/STAR ARMADA/Station Prototypes/`, separate from normal user data.
The installed application bundle is not replaced.

## Authoring

- Editable Blender source: `art/blender/imperium_sensor_prototype.blend`.
- Script-authoritative builder/exporter: `tools/art/build_imperial_station_prototypes.py`, Blender 5.0.1.
- Pack metadata builder: `.venv/bin/python tools/art/package_station_prototypes.py`.
- Six existing material roles, no shader or texture-pipeline changes.
- The binding's approved envelope is preserved exactly: in-game length, collision radii, ship
  sizes and simulation hashes are untouched.

Focused integration check: `PYTHONPATH=tests .venv/bin/python -m unittest test_station_prototypes -v`.
