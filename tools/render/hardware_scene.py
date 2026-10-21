"""One colony building on one planet, shared by every side of the surface-hardware measurement.

A skirmish map has no colonies - planet buildings are constructed during a match - so the slice
that draws them needs a building that exists now. This plants one: a hull is relabelled as surface
hardware on a real planet, through the same fields the simulation uses (`planet_id`,
`planet_building_slot`), so the renderer's own `station_frame` and the collector's surface branch
both resolve it the way they would resolve a building the player paid for.

Nothing here decides anything: the transform comes from `planet_building_geometry.surface_frame`,
the mesh from the approved catalogue, and the binding from the faction the hull already belonged to.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FACTIONS = ('imperial', 'rebel', 'confederacy', 'syndicate')
KINDS = ('planet_extractor', 'planet_trade_hub', 'planet_shield_generator',
         'planet_pulsar_cannon')

# The extractor is the building with the most to get wrong - paired refinery tanks, collars, ribs
# and a pump - so a silhouette error shows up as a wrong shape rather than a missing dot.
KIND = 'planet_extractor'
#: Slot 4 is the north pole, so the foundation normal is world +Y and the building stands along the
#: camera's own up vector. Every other site leaves the building pointing at or away from the viewer:
#: correct, but foreshortened to a slab, and a comparison against that measures nothing.
SLOT = 4
RADIUS = 50.0                     # stations are authored at radius 50; the frame scale is r/50
BASE_Y = 6000.0                   # lift the planet clear of the map plane, like the other fixtures


def plant(state, *, kind=KIND, slot=SLOT, faction='imperial'):
    """Relabel one hull as surface hardware on the first planet that is not an asteroid field."""
    from game.core.vectors import Vec3

    planets = [e for e in sorted(state.entities.values(), key=lambda e: e.id)
               if e.alive and e.is_planet and e.data_id != 'asteroid_field']
    if not planets:
        raise SystemExit('the map has no planet to build on')
    # The smallest world, so a building 50 units across is a readable part of the frame and the
    # horizon behind it is a limb rather than a wall.
    planet = min(planets, key=lambda e: e.radius)
    planet.pos = Vec3(0.0, BASE_Y, 0.0)

    hull = None
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        if not (entity.alive and entity.is_ship):
            continue
        player = state.players.get(entity.owner)
        if player is not None and player.faction == faction:
            hull = entity
            break
    if hull is None:
        raise SystemExit(f'no {faction} hull on the map to plant the building on')

    hull.data_id = kind
    hull.planet_id = planet.id
    hull.planet_building_slot = slot
    hull.is_station = True
    hull.is_ship = False            # a building is not a hull: the ship pass must not claim it
    hull.radius = RADIUS
    hull.pos = Vec3(*planet.pos.to_tuple())
    if hasattr(hull, 'vel'):
        hull.vel = Vec3(0.0, 0.0, 0.0)
    return planet, hull


def target(planet, slot=SLOT) -> tuple:
    """Where the building actually stands, in world space - the camera looks at this, not the core."""
    from render.planet_building_geometry import surface_frame

    origin, _basis = surface_frame(planet, slot)
    return tuple(origin)


def meshes() -> dict:
    """The authored mesh for every (faction, kind) the session can field.

    Read through `render.asset_selection.mesh_for` - the same call `fleet_geometry.station_mesh`
    makes - so the window draws the mesh Python draws rather than a second copy of the design. A
    faction without an authored mesh falls back to the imperial one, exactly as `station_mesh` does.
    """
    from game.core.manager import GameManager            # noqa: F401  (import order)
    from render import asset_selection
    from render.fleet_geometry import station_mesh
    sys.path.insert(0, str(ROOT))
    from tools.render.dump_snapshot import _default_selection

    asset_selection.configure(_default_selection(), asset_root=ROOT,
                              pack_root=ROOT / 'visual_packs')
    out = {}
    for faction in FACTIONS:
        for kind in KINDS:
            name = f'{faction}:{kind}'
            mesh = asset_selection.mesh_for(name)
            if mesh is None:
                name = f'imperial:{kind}'
                mesh = asset_selection.mesh_for(name)
            if mesh is None:
                mesh = station_mesh(kind, faction)
            out[name] = mesh
    return out


def publish(ring_path, only=None) -> dict:
    """Encode every mesh a session can need and publish it into one ring, once per binding."""
    from render_bridge import hardware, ring

    available = meshes()
    if only:
        wanted = set(only)
        available = {name: mesh for name, mesh in available.items() if name in wanted}
        missing = wanted - set(available)
        if missing:
            raise SystemExit(f'no mesh for {sorted(missing)}')
    blobs, summary, largest = [], {}, 0
    for name, mesh in sorted(available.items()):
        blob = hardware.encode(name, mesh)
        blobs.append(blob)
        largest = max(largest, len(blob))
        summary[name] = {'triangles': sum(len(rows) for rows in mesh.values()),
                         'roles': sorted(mesh), 'bytes': len(blob)}
    pathlib.Path(ring_path).parent.mkdir(parents=True, exist_ok=True)
    with ring.Ring.create(str(ring_path), slots=max(4, len(blobs)), slot_bytes=largest + 64) as out:
        for blob in blobs:
            out.publish(blob)
    return {'bindings': summary, 'largest_blob_bytes': largest}


def camera(planet, slot=SLOT) -> dict:
    """A camera that fills the frame with the building and the ground it stands on."""
    return dict(target=target(planet, slot), distance=300.0, pitch=24.0, yaw=20.0)
