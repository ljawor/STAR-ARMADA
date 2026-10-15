"""Closed surface hardware in a +Y outward, y=0 foundation frame.

Planet radius is already the rendered solid radius. No camera/readability
magnification is applied to foundations; anchors match paid simulation sites.
"""
from functools import lru_cache
import math
from render.fleet_geometry import _Hardware
from game.systems.planet_buildings import BUILDING_TYPES


def building_mesh(kind, faction='imperial'):
    if kind not in BUILDING_TYPES:
        raise ValueError('unknown surface hardware')
    faction = faction if faction in ('imperial','rebel','confederacy','syndicate') else 'imperial'
    return _building_mesh(kind, faction)


def planet_shield_fields(state):
    """Every colony shield field on the map, in ONE pass: `{planet_id: field}`.

    The renderer needs all of them each frame, so it must not rescan the entity
    dictionary once per planet the way a per-planet query would.
    """
    fields = {}
    for e in sorted(state.entities.values(), key=lambda e: e.id):
        if not (e.alive and e.operational
                and e.data_id == 'planet_shield_generator'):
            continue
        planet = state.entity(e.planet_id) if e.planet_id is not None else None
        if planet is None or getattr(planet, 'colonized_by', None) != e.owner:
            continue
        total = e.max_shield_total()
        if total <= 0:
            continue
        fields[planet.id] = (e, max(0.0, min(1.0, e.total_shield() / total)),
                             planet.radius * 1.04 + 48.0)
    return fields


def planet_shield_field(state, planet):
    """`(generator, strength, radius)` for ONE colonized planet's surface shield.

    The generator's quadrant pools absorb damage aimed at the planet's surface
    hardware only (`planet_buildings.absorb_surface_damage`), so the field it
    raises hugs the world just above its foundations. It deliberately does NOT
    reach the orbital shells: an exterior bubble would advertise protection for
    satellites and ships that the sim never shields. Returns `(None, 0.0, 0.0)`
    when the planet has no operational, owner-held generator.
    """
    if planet is None or getattr(planet, 'colonized_by', None) is None or planet.colonized_by < 0:
        return None, 0.0, 0.0
    # Clearance above the tallest surface hardware (~50 u) but far inside the
    # lowest satellite shell (planet.radius + orbit_clearance).
    return planet_shield_fields(state).get(planet.id, (None, 0.0, 0.0))


@lru_cache(maxsize=16)
def _building_mesh(kind, faction):
    h = _Hardware()
    sides = {'imperial':6, 'rebel':12, 'confederacy':8, 'syndicate':5}[faction]
    h.plate('base', (68,6,64), (0,3,0), 2)
    h.plate('dark', (56,3,52), (0,7.5,0), 1)
    for s in (-1,1):
        h.plate('accent', (6,1,48), (s*27,6.6,0), .3)
        h.plate('cool', (3,1,12), (s*27,7.3,18), .2)
    if kind == 'planet_extractor':
        # Paired refinery tanks, real collars, cooling ribs and central pump.
        for s in (-1,1):
            h.ring('base', 11,.1,24,(s*17,21,-7),sides=sides)
            h.ring('trim',12,9,3,(s*17,34,-7),sides=sides)
            h.ring('accent',11.5,10,3,(s*17,22,-7),sides=sides)
            h.plate('lit',(7,1,4),(s*17,36,-7),.3)
        h.plate('base',(18,18,22),(0,18,17),2)
        h.vent((0,27.5,17),14,16)
        h.plate('trim',(3,34,3),(0,26,-20),.5)
        h.plate('trim',(35,3,4),(0,39,-20),.5)
    elif kind == 'planet_trade_hub':
        # Low cargo terminal, raised glazed control tower, loading bays.
        h.plate('base',(42,15,38),(0,16.5,-5),3)
        h.plate('accent',(34,1,16),(0,24.6,-12),.3)
        h.plate('base',(16,23,16),(0,35,-14),2)
        h.plate('lit',(12,2,1),(0,43,-5.5),.3)
        h.plate('trim',(19,3,19),(0,48,-14),.7)
        for s in (-1,1):
            h.bay((s*15,15,26),17,12,13)
            h.plate('base',(12,8,13),(s*24,13,-19),1)
            h.plate('trim',(4,17,4),(s*29,17,15),.7)
    elif kind == 'planet_shield_generator':
        # Solid induction tower and exposed annular coils; NOT a planet bubble.
        h.ring('base',16,.1,30,(0,24,0),sides=sides)
        for y in (16,26,36):
            h.ring('trim',25,19,4,(0,y,0),sides=16)
            h.ring('cool',24,22,1,(0,y+2.6,0),sides=16)
        for s in (-1,1):
            h.plate('base',(7,37,10),(s*27,27,0),1)
            h.plate('accent',(8,1,11),(s*27,46,0),.3)
        h.ring('dark',13,.1,5,(0,42,0),sides=sides)
        h.plate('lit',(10,2,10),(0,45,0),.4)
    else:
        # Radially elevated pulsar cradle, long paired barrels and muzzle coils.
        h.ring('dark',22,.1,8,(0,13,0),sides=sides)
        h.plate('base',(30,16,27),(0,25,0),3)
        h.plate('accent',(22,1,17),(0,33.6,-3),.3)
        for s in (-1,1):
            h.plate('trim',(6,7,47),(s*9,36,18),1)
            h.ring('dark',6,3,7,(s*9,36,42),pitch=90,sides=12)
            h.ring('cool',6.4,4.4,2,(s*9,36,45),pitch=90,sides=12)
            h.plate('base',(9,17,20),(s*24,18,-10),1)
        h.plate('lit',(8,1,7),(0,35,-6),.3)
    return h.finish()


def surface_frame(planet, slot):
    """Foundation + column basis, matching the authoritative six surface sites."""
    from game.systems.planet_buildings import planet_building_site
    pos, normal = planet_building_site(planet, slot)
    up = normal.to_tuple()
    seed = (0.,0.,1.) if abs(up[2]) < .9 else (1.,0.,0.)
    right = (up[1]*seed[2]-up[2]*seed[1], up[2]*seed[0]-up[0]*seed[2], up[0]*seed[1]-up[1]*seed[0])
    length = math.sqrt(sum(v*v for v in right))
    right = tuple(v/length for v in right)
    forward = (right[1]*up[2]-right[2]*up[1],right[2]*up[0]-right[0]*up[2],right[0]*up[1]-right[1]*up[0])
    origin = tuple(v + n for v,n in zip(pos.to_tuple(),up))
    return origin, (right,up,forward)


def station_frame(state, entity, station_angle=0.):
    """One transform for drawing, camera bounds, contacts and input picking.

    Surface hardware never spins. Satellites follow sim yaw at the real xyz.
    Only legacy free stations retain their cosmetic station-angle animation.
    """
    if entity.planet_building_slot is not None and entity.planet_id is not None:
        planet = state.entity(entity.planet_id)
        if planet is not None:
            origin,basis = surface_frame(planet,entity.planet_building_slot)
            return origin,basis,entity.radius/50.
    angle = entity.yaw if entity.satellite_slot is not None else station_angle
    ca,sa = math.cos(angle),math.sin(angle)
    return entity.pos.to_tuple(), ((ca,0.,-sa),(0.,1.,0.),(sa,0.,ca)), entity.radius/50.


def transform_point(point, frame):
    origin,basis,scale = frame
    return tuple(origin[i]+scale*sum(point[j]*basis[j][i] for j in range(3)) for i in range(3))


def station_world_mesh(state, entity, station_angle=0.):
    from render.fleet_geometry import station_mesh
    from render.faction_visuals import owner_faction
    frame = station_frame(state,entity,station_angle)
    basis = frame[1]
    return {role: tuple((tuple(sum(normal[j]*basis[j][i] for j in range(3)) for i in range(3)),
                               tuple(transform_point(p,frame) for p in tri)) for normal,tri in mesh)
            for role,mesh in station_mesh(entity.data_id,owner_faction(state,entity.owner)).items()}


def attached_contact_point(state, entity, normal, desired):
    """Resolve contacts in the same outward frame as the actual solid mesh."""
    from render.faction_visuals import owner_faction
    from render.ship_sizes import _station_ray_mesh, _surface_contact_offset
    origin, basis, scale = station_frame(state, entity)
    local_normal = tuple(sum(normal[i] * axis[i] for i in range(3)) for axis in basis)
    delta = tuple(desired[i] - origin[i] for i in range(3))
    local_desired = tuple(sum(delta[i] * axis[i] for i in range(3)) for axis in basis)
    local = _surface_contact_offset(
        _station_ray_mesh(owner_faction(state, entity.owner), entity.data_id),
        scale, local_normal, 0., local_desired)
    if local is None:
        return None
    return tuple(origin[i] + sum(local[j] * basis[j][i] for j in range(3)) for i in range(3))


def visible_surface_slots(state, viewer, selection):
    """Only current own selected colonies expose queue/slot intelligence."""
    from game.systems.colonies import eligible_planet
    result=[]
    for pid in sorted(selection):
        planet=state.entities.get(pid)
        if not eligible_planet(planet) or planet.colonized_by != viewer or not state.can_see(viewer,pid):
            continue
        for slot in range(6):
            occupied=next((e for e in state.entities.values() if e.alive and e.owner == viewer
                           and e.planet_id == pid and e.planet_building_slot == slot
                           and state.can_see(viewer,e.id)),None)
            queued=next((q for q in planet.build_queue if q.get('kind')=='planet_building' and q.get('slot')==slot),None)
            status='occupied' if occupied else 'building' if queued else 'empty'
            progress=max(0.,min(1.,1.-queued.get('time_left',0)/max(.1,queued.get('total',1)))) if queued else 0.
            origin,basis=surface_frame(planet,slot)
            result.append(dict(planet_id=pid,slot=slot,origin=origin,basis=basis,status=status,
                               kind=occupied.data_id if occupied else queued.get('item') if queued else None,
                               progress=progress,radius=min(planet.radius*.085,55.)))
    return tuple(result)


@lru_cache(maxsize=64)
def _station_local_bounds(faction, data_id):
    """Immutable model extrema; callers canonicalize visual IDs before lookup."""
    from render.fleet_geometry import station_mesh
    mesh = station_mesh(data_id, faction)
    points = [p for role in mesh.values() for _, tri in role for p in tri]
    return (tuple(min(p[i] for p in points) for i in range(3)),
            tuple(max(p[i] for p in points) for i in range(3)))


def station_camera_box(state, entity, station_angle=0.):
    """Conservative world AABB supported by the existing safe-eye slab solver."""
    from render.faction_visuals import owner_faction, normalize_station_key
    from itertools import product
    faction, data_id = normalize_station_key(entity.data_id, owner_faction(state, entity.owner))
    lo, hi = _station_local_bounds(faction, data_id)
    frame=station_frame(state,entity,station_angle)
    points=[transform_point(p,frame) for p in product(*zip(lo,hi))]
    origin=frame[0]
    low=tuple(min(p[i] for p in points)-origin[i] for i in range(3))
    high=tuple(max(p[i] for p in points)-origin[i] for i in range(3))
    return origin,0.,low,high


def station_pick_distance(state, entity, camera, mouse, floor):
    """Projected solid triangle hit wins over the underlying planet center.

    Call only after current-visibility filtering. Back-face surface stations
    are excluded using the rendered planet sphere, not hidden ownership data.
    """
    frame=station_frame(state,entity,camera._station_angle())
    if entity.planet_building_slot is not None and hasattr(camera,'eye_position'):
        planet=state.entity(entity.planet_id)
        eye=camera.eye_position()
        up=frame[1][1]
        if sum((eye[i]-frame[0][i])*up[i] for i in range(3)) < 0:
            return math.inf
    sp=camera.world_to_screen(*entity.pos.to_tuple())
    distance=math.dist(sp[:2],mouse) if sp else math.inf
    for role in station_world_mesh(state,entity,camera._station_angle()).values():
        for _,tri in role:
            points=[camera.world_to_screen(*p) for p in tri]
            if any(p is None for p in points):
                continue
            a,b,c=points
            def side(p,q):
                return (q[0]-p[0])*(mouse[1]-p[1])-(q[1]-p[1])*(mouse[0]-p[0])
            signs=(side(a,b),side(b,c),side(c,a))
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area)>1e-8 and (min(signs)>=-1e-7 or max(signs)<=1e-7):
                return -1.
            for p,q in ((a,b),(b,c),(c,a)):
                dx,dy=q[0]-p[0],q[1]-p[1]
                squared=dx*dx+dy*dy
                t=max(0.,min(1.,((mouse[0]-p[0])*dx+(mouse[1]-p[1])*dy)/squared)) if squared else 0.
                distance=min(distance,math.hypot(mouse[0]-p[0]-t*dx,mouse[1]-p[1]-t*dy)+floor*.5)
    return distance
