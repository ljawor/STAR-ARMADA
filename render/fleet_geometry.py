"""Closed beveled armor lofts, generated once then cached in GL display lists.

Coordinates remain in model space; neither geometry nor materials touch sim RNG.
"""
from __future__ import annotations
import math


def armor_loft(sections, bevel=2.0):
    """Return (unit normal, triangle) tuples from (z, halfwidth, top, bottom).

    Eight-sided cross sections retain flat readable decks while chamfered edges
    catch the key light. Width can taper along the hull (unlike a scaled cube).
    """
    if len(sections) < 2 or bevel <= 0:
        raise ValueError('a loft needs two sections and a positive bevel')
    rings = []
    for z, w, top, bottom in sections:
        if w <= 0 or top <= bottom:
            raise ValueError('sections require positive width and height')
        b = min(bevel, w * .45, (top-bottom) * .3)
        rings.append([(-w+b, top, z), (w-b, top, z), (w, top-b, z),
                      (w, bottom+b, z), (w-b, bottom, z), (-w+b, bottom, z),
                      (-w, bottom+b, z), (-w, top-b, z)])
    if any(b[0] <= a[0] for a,b in zip(sections, sections[1:])):
        raise ValueError('section z coordinates must increase')
    result = []

    def triangle(a,b,c,ref):
        u = tuple(b[i]-a[i] for i in range(3))
        v = tuple(c[i]-a[i] for i in range(3))
        n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        if sum(n[i]*((a[i]+b[i]+c[i])/3-ref[i]) for i in range(3)) < 0:
            b,c = c,b
            n = tuple(-x for x in n)
        length = math.sqrt(sum(x*x for x in n))
        result.append((tuple(x/length for x in n), (a,b,c)))

    for index,(a,b) in enumerate(zip(rings, rings[1:])):
        ref = (0, (sections[index][2]+sections[index][3])/2,
               (sections[index][0]+sections[index+1][0])/2)
        for i in range(8):
            j = (i+1)%8
            triangle(a[i], b[i], b[j], ref)
            triangle(a[i], b[j], a[j], ref)
    for ring,section,direction in ((rings[0], sections[0], 1), (rings[-1], sections[-1], -1)):
        center = (0, (section[2]+section[3])/2, section[0])
        ref = (center[0], center[1], center[2]+direction)
        for i in range(8):
            triangle(center, ring[i], ring[(i+1)%8], ref)
    return result


# Pure, immutable hardware meshes: six bounded material roles, generated once.
from functools import lru_cache
from types import MappingProxyType

ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


class _Hardware:
    def __init__(self):
        self.parts = {role: [] for role in ROLES}

    def add(self, role, mesh, center=(0, 0, 0), yaw=0, pitch=0):
        ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        def rotate(v):
            x, y, z = v
            y, z = y*cp-z*sp, y*sp+z*cp
            return (x*ca+z*sa, y, z*ca-x*sa)
        for n, triangle in mesh:
            points = tuple(tuple(a+b for a,b in zip(rotate(v), center)) for v in triangle)
            self.parts[role].append((rotate(n), points))

    def loft(self, role, sections, bevel=2, center=(0,0,0), yaw=0, pitch=0):
        self.add(role, armor_loft(sections, bevel), center, yaw, pitch)

    def plate(self, role, size, center=(0,0,0), bevel=1, yaw=0, pitch=0):
        x,y,z = size
        self.loft(role, ((-z/2,x/2,y/2,-y/2),(z/2,x/2,y/2,-y/2)), bevel, center, yaw, pitch)

    def ring(self, role, outer, inner, height, center=(0,0,0), pitch=0, sides=16):
        self.add(role, _ring(outer, inner, height, sides), center, pitch=pitch)

    def turret(self, center, scale=1, yaw=0):
        x,y,z=center
        self.ring('dark', 5*scale, .1*scale, 2*scale, (x,y,z), sides=12)
        self.plate('base',(9*scale,5*scale,10*scale),(x,y+3*scale,z),2*scale,yaw)
        for side in (-1,1):
            # Long paired barrels and thick muzzle collars, not turret cubes.
            a=math.radians(yaw)
            dx,dz=side*2.2*scale,9*scale
            p=(x+dx*math.cos(a)+dz*math.sin(a),y+3.5*scale,z+dz*math.cos(a)-dx*math.sin(a))
            self.loft('trim',((-7*scale,1.3*scale,1.3*scale,-1.3*scale),
                              (7*scale, .9*scale,.9*scale,-.9*scale)), .4*scale,p,yaw)
        self.plate('accent',(6*scale,.5*scale,4*scale),(x,y+5.8*scale,z),.2*scale,yaw)

    def bay(self, center, width, height, depth, yaw=0):
        # A genuinely OPEN mouth: outer rails, recessed walls/floor/back.
        x,y,z=center
        a=math.radians(yaw)
        def point(dx,dy,dz):
            return (x+dx*math.cos(a)+dz*math.sin(a),y+dy,z+dz*math.cos(a)-dx*math.sin(a))
        t=height*.17
        for sign in (-1,1):
            self.plate('base',(t,height,depth),point(sign*width/2,0,-depth/2),t*.3,yaw)
            self.plate('trim',(width+t,t,depth),point(0,sign*height/2,-depth/2),t*.3,yaw)
            self.plate('cool',(width*.8,t*.28,t*.35),point(0,sign*height*.38,.15),t*.08,yaw)
        self.plate('dark',(width,height,t*.3),point(0,0,-depth),t*.1,yaw)
        # Internal floor ribbing is visible through the opening.
        for k in range(3):
            self.plate('dark',(width*.8,t*.22,t*.8),point(0,-height*.35,-depth*(k+1)/4),t*.05,yaw)

    def nozzle(self, center, radius=3):
        # Hollow annular shroud faces aft; luminous throat is recessed behind lip.
        self.ring('dark',radius,radius*.65,radius*.9,center,pitch=90,sides=12)
        self.ring('trim',radius*1.08,radius*.72,radius*.17,
                  (center[0],center[1],center[2]-radius*.4),pitch=90,sides=12)
        self.plate('cool',(radius*1.25,radius*1.25,.2),
                   (center[0],center[1],center[2]+radius*.1),.15)

    def vent(self, center, width, length):
        self.plate('dark',(width,.7,length),center,.3)
        for i in range(5):
            self.plate('trim',(width*.8,.65,length*.055),
                       (center[0],center[1]+.5,center[2]+(i-2)*length*.16),.2)

    def finish(self):
        return MappingProxyType({role:tuple(mesh) for role,mesh in self.parts.items()})


def _ring(outer, inner, height, sides):
    """Closed annulus, including inward normals and real top/bottom thickness."""
    if not 0 < inner < outer or height <= 0 or sides < 3:
        raise ValueError('ring dimensions must be positive and inner < outer')
    mesh=[]
    def face(points, expected):
        for a,b,c in ((points[0],points[1],points[2]),(points[0],points[2],points[3])):
            u=tuple(b[i]-a[i] for i in range(3)); v=tuple(c[i]-a[i] for i in range(3))
            n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            if sum(x*y for x,y in zip(n,expected)) < 0:
                b,c=c,b; n=tuple(-x for x in n)
            length=math.sqrt(sum(x*x for x in n))
            mesh.append((tuple(x/length for x in n),(a,b,c)))
    for i in range(sides):
        a,b=2*math.pi*i/sides,2*math.pi*(i+1)/sides
        def p(r,y,t): return (r*math.sin(t),y,r*math.cos(t))
        up,down=height/2,-height/2
        o0,o1,o2,o3=p(outer,up,a),p(outer,up,b),p(outer,down,b),p(outer,down,a)
        n0,n1,n2,n3=p(inner,up,a),p(inner,up,b),p(inner,down,b),p(inner,down,a)
        radial=(math.sin((a+b)/2),0,math.cos((a+b)/2))
        face((o0,o1,o2,o3),radial)
        face((n0,n1,n2,n3),tuple(-x for x in radial))
        face((o0,o1,n1,n0),(0,1,0)); face((o3,o2,n2,n3),(0,-1,0))
    return tuple(mesh)


def ship_mesh(shape):
    """Immutable ship triangles. Unknown utility IDs share one canonical cache."""
    from render.faction_visuals import normalize_ship_key
    shape = normalize_ship_key(shape)
    if ':' in shape:
        from render.faction_ships import ship_mesh as faction_ship_mesh
        return faction_ship_mesh(*shape.split(':'))
    return _ship_mesh(shape)


@lru_cache(maxsize=5)
def _ship_mesh(shape):
    h=_Hardware()
    if shape=='wedge':
        h.loft('base',((-24,7,5,-3),(-8,9,6,-3),(16,5,5,-2),(35,1,2,-1)),1.8)
        for s in (-1,1):
            # Swept taper changes the actual silhouette of the wings.
            h.loft('base',((-18,13,2,-1),(0,10,2,-1),(17,1,1,-1)),1,
                   (s*20,2,-7),s*28)
            h.loft('accent',((-15,9,2.5,1),(0,7,2.5,1),(13,1,2,1)),.4,
                   (s*20,2,-7),s*28)
            h.turret((s*29,3,-2),.45)
            h.nozzle((s*6,0,-26),3)
        h.loft('dark',((-6,5,10,5),(6,4,10,5),(14,1,6,4)),1)
        h.plate('lit',(7,.5,8),(0,10.3,1),.2)
        h.loft('trim',((-22,1,14,3),(-7,1,6,3)),.4)
        h.vent((0,6.3,-15),10,8)
    elif shape=='needle':
        h.loft('base',((-40,7,5,-4),(-26,11,6,-5),(15,8,6,-4),(48,1.1,2,-1)),2)
        h.loft('base',((-30,5,14,5),(-14,5,14,5),(-5,2,8,5)),1.5)
        for s in (-1,1):
            h.loft('base',((-27,4,4,-4),(-3,4,4,-4),(14,1,2,-2)),1,(s*12,-1,0))
            h.loft('accent',((-24,2,6,5),(12,1,6,5)),.3,(s*6,0,0))
            h.nozzle((s*5,0,-42),3.3)
            h.plate('lit',(.5,1.3,12),(s*5.2,11,-22),.2)
        h.turret((0,6,5),.7)
        h.vent((0,6.2,-7),9,10)
        h.bay((0,-2,34),6,4,6)
        h.plate('trim',(1.6,12,1.6),(0,18,-22),.4)
    elif shape in ('cruiser','dagger'):
        heavy=shape=='dagger'
        width=27 if heavy else 18
        aft=-75 if heavy else -58
        bow=108 if heavy else 78
        deck=10 if heavy else 7
        h.loft('base',((aft,width*.7,deck,-deck),(-35,width,deck,-deck),
                       (28,width*.85,deck,-deck),(bow,width*.065,4,-3)),3)
        h.loft('base',((-50 if heavy else -32,12 if heavy else 9,24 if heavy else 19,deck),
                       (-24 if heavy else -12,12 if heavy else 9,24 if heavy else 19,deck),
                       (-15 if heavy else -4,5,14,deck)),2)
        if heavy:
            h.loft('base',((-45,8,33,23),(-30,8,33,23),(-24,4,28,23)),1.8)
        for s in (-1,1):
            # Long tapered sponsons with open hangar mouths at the forward end.
            h.loft('base',((aft+6,5,5,-6),(-30,7,5,-6),(-2,5,4,-5)),1.5,(s*(width+4),0,0))
            h.bay((s*(width+4),0,16),10,9,18)
            h.loft('accent',((aft+12,3,deck+1.3,deck+.4),(22,2,deck+1.3,deck+.4),
                             (bow-12,.6,5.5,4.8)),.25,(s*(width*.48),0,0))
            for z in (-34,-10,14):
                h.plate('lit',(.5,1.5,13),(s*(width+11.2),1,z-15),.2)
            h.plate('lit',(.5,1.5,15),(s*(12.2 if heavy else 9.2),21 if heavy else 16,-34 if heavy else -23),.2)
        for z in ((-55,-4,29,58) if heavy else (-28,5,30)):
            h.turret((0,deck+1,z),1.25 if heavy else .9)
        h.vent((0,deck+.3,aft+12),width,14)
        for x in ((-15,-5,5,15) if heavy else (-9,0,9)):
            h.nozzle((x,-2,aft-3),4.5 if heavy else 4)
        h.plate('trim',(2,15,2),(0,32 if heavy else 24,-36),.5)
        h.plate('lit',(14,.8,.8),(0,33.5 if heavy else 19.4,-34 if heavy else -22),.2)
    else:
        # Twin cargo drums, raised glazed tug cab and an articulated work boom.
        h.loft('base',((-24,7,5,-5),(10,7,5,-5),(22,4,4,-3)),1.5)
        for s in (-1,1):
            h.loft('base',((-20,6,7,-7),(10,6,7,-7),(17,3,4,-4)),2,(s*14,0,0))
            h.plate('accent',(10,1,23),(s*14,7.4,-3),.3)
            h.nozzle((s*14,0,-23),3.5)
            h.vent((s*14,7.2,-10),8,10)
        h.loft('base',((6,6,17,6),(15,6,17,6),(23,3,11,6)),1.5)
        h.plate('lit',(9,2,.6),(0,14,19),.2)
        h.bay((0,-1,24),7,7,7)
        h.plate('trim',(3,19,3),(-10,17,-11),.7)
        h.plate('trim',(22,3,3),(0,25,-11),.7)
        h.plate('dark',(4,7,5),(11,21,-11),.7)
    return h.finish()


STATION_TYPES = ('command_station', 'shipyard', 'research_station', 'defense_platform',
                 'mining_station', 'sensor_station', 'trade_station', 'fighter_platform',
                 'repair_dock', 'energy_relay')


def station_mesh(data_id, faction='imperial'):
    """Station mesh at radius 50, matching ship-scale material coordinates."""
    from render.faction_visuals import normalize_station_key
    faction, data_id = normalize_station_key(data_id, faction)
    if data_id in ('defense_satellite', 'attack_satellite'):
        return _satellite_mesh(data_id, faction)
    if faction != 'imperial':
        from render.faction_stations import station_mesh as faction_station_mesh
        return faction_station_mesh(faction, data_id)
    return _station_mesh(data_id)


@lru_cache(maxsize=8)
def _satellite_mesh(kind, faction):
    """Closed planetary hardware; shared roles, faction-specific silhouettes."""
    h = _Hardware()
    sides = {'imperial': 6, 'rebel': 12, 'confederacy': 8, 'syndicate': 5}[faction]
    h.ring('base', 32, .1, 18, sides=sides)
    h.ring('trim', 34, 29, 3, (0, 10, 0), sides=sides)
    h.plate('accent', (42, 2, 22), (0, 12, 0), 1)
    h.plate('cool', (12, 1, 8), (0, 14, 0), .3)
    for angle in (0, 120, 240):
        a = math.radians(angle)
        x, z = math.sin(a)*35, math.cos(a)*35
        h.plate('dark', (12, 8, 18), (x, 0, z), 1, angle)
        h.plate('accent', (10, 1, 14), (x, 5, z), .5, angle)
        h.plate('lit', (6, 1, 3), (x, 6, z), .3, angle)
        if kind == 'attack_satellite':
            h.plate('base', (9, 10, 34), (x, 12, z), 1, angle)
            h.plate('trim', (3, 3, 46), (x, 20, z), .5, angle)
        else:
            h.ring('base', 9, .1, 9, (x, 12, z), sides=8)
            h.plate('trim', (3, 3, 18), (x, 18, z), .5, angle)
    return h.finish()


@lru_cache(maxsize=10)
def _station_mesh(did):
    h=_Hardware()
    if did == 'command_station':
        h.ring('base',50,42,8,sides=24)
        h.ring('dark',43,39,5,(0,-2,0),sides=24)
        h.ring('cool',49,48,1,(0,4.4,0),sides=24)
        h.ring('base',22,.15,22,(0,3,0),sides=12)
        h.ring('trim',23,21,3,(0,16,0),sides=12)
        for i in range(8):
            a=i*45; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('dark',(5,5,29),(s*32,-2,c*32),1,a)
            h.loft('base',((-10,7,8,-5),(7,7,8,-5),(13,3,4,-3)),2,(s*49,0,c*49),a)
            h.plate('accent',(10,1,15),(s*49,8.5,c*49),.3,a)
            h.plate('lit',(11,2,.6),(s*61.5,2,c*61.5),.2,a)
        h.loft('base',((-14,9,35,14),(8,9,35,14),(16,4,26,14)),2)
        h.plate('lit',(13,2,.7),(0,30,13),.2)
        h.plate('trim',(3,24,3),(0,43,0),.7)
        for s in (-1,1): h.bay((s*35,0,41),15,13,16)
    elif did == 'shipyard':
        # Split drydock: the negative space is the building's dominant feature.
        h.plate('base',(77,16,20),(0,0,-35),3)
        for s in (-1,1):
            h.loft('base',((-45,8,6,-7),(30,8,6,-7),(54,4,4,-4)),2,(s*35,-3,0))
            h.plate('accent',(10,1,65),(s*35,3.5,0),.3)
            h.plate('trim',(5,35,6),(s*35,14,-20),1)
            h.plate('trim',(5,30,6),(s*35,12,25),1)
            h.plate('cool',(1,1.2,72),(s*27,-.5,0),.3)
            for z in (-22,0,22):
                h.plate('dark',(16,5,6),(s*29,-7,z),1)
            h.bay((s*35,-1,55),14,12,16)
            h.plate('lit',(.7,2,18),(s*43.3,0,-29),.2)
        h.plate('trim',(75,5,7),(0,31,-20),1)
        h.loft('base',((-42,12,33,7),(-24,12,33,7),(-17,6,22,7)),2)
        h.plate('lit',(20,2,.7),(0,27,-20),.2)
        h.vent((0,33.4,-32),17,13)
    elif did == 'research_station':
        h.ring('base',18,.15,23,(0,2,0),sides=12)
        h.ring('trim',21,18,4,(0,14,0),sides=12)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('dark',(7,7,24),(s*27,0,c*27),1,a)
            h.loft('base',((-14,10,9,-8),(7,10,9,-8),(18,4,4,-4)),2,(s*46,1,c*46),a)
            h.plate('accent',(14,1,18),(s*46,10.5,c*46),.3,a)
            h.plate('lit',(14,2,.7),(s*62,2,c*62),.2,a)
            h.plate('dark',(22,2,32),(s*48,-14,c*48),.7,a)
            for k in (-1,1):
                h.plate('cool',(1,1,27),(s*48+k*c*8,-12.4,c*48-k*s*8),.2,a)
        h.ring('trim',17,13,3,(0,31,0),pitch=28,sides=16)
        h.plate('trim',(2,18,2),(0,21,0),.4)
        h.plate('lit',(16,2,.7),(0,8,18.2),.2)
    elif did == 'defense_platform':
        h.plate('base',(55,15,55),(0,-1,0),5,yaw=45)
        h.plate('dark',(61,5,61),(0,-11,0),2,yaw=45)
        h.loft('base',((-15,12,20,6),(10,12,20,6),(18,5,13,6)),2)
        for x in (-1,1):
            for z in (-1,1): h.turret((x*24,7,z*24),1.5,math.degrees(math.atan2(x,z)))
        h.plate('accent',(19,1,12),(0,20.5,0),.3)
        h.plate('lit',(8,2,.7),(0,10,18.4),.2)
        h.vent((0,7,-27),20,14)
        h.bay((0,-2,40),20,10,12)
    elif did == 'mining_station':
        h.loft('base',((-28,24,15,-10),(12,24,15,-10),(29,14,8,-6)),3)
        for s in (-1,1):
            h.loft('base',((-18,9,8,-8),(12,9,8,-8),(19,4,4,-4)),2,(s*29,22,-8),pitch=-90)
            h.ring('accent',10,8,4,(s*29,30,-8),sides=12)
            h.plate('dark',(17,4,9),(s*24,8,11),1)
            h.plate('lit',(.7,2,24),(s*24.5,3,-6),.2)
            # Exterior roof glazing remains visible from tactical overhead.
            h.plate('lit',(12,.7,5),(s*13,15.5,-8),.2)
        h.loft('dark',((-3,6,6,-6),(30,5,5,-5),(45,1,1,-1)),1,(0,-9,0),pitch=90)
        for y in (-17,-26,-35,-44): h.ring('trim',9,5,3,(0,y,0),sides=12)
        h.plate('accent',(30,1,15),(0,15.5,-7),.3)
        h.plate('lit',(22,2,.7),(0,5,25),.2)
        h.bay((0,1,35),18,12,10)
        h.vent((0,15.3,-17),20,10)
    elif did == 'sensor_station':
        h.loft('base',((-15,14,9,-9),(12,14,9,-9),(21,4,5,-5)),2,(0,-14,0))
        h.plate('dark',(8,45,8),(0,6,0),1.5)
        # Large open dish rim and radial array panels are legible at normal zoom.
        h.ring('trim',37,32,4,(0,38,0),pitch=38,sides=24)
        h.ring('base',30,8,2,(0,37,0),pitch=38,sides=24)
        h.ring('cool',28,27,1,(0,39,0),pitch=38,sides=24)
        h.plate('accent',(10,24,5),(0,15,4),1)
        h.plate('trim',(3,30,3),(0,43,0),.6)
        h.plate('lit',(6,2,.7),(0,-12,21.4),.2)
        h.plate('lit',(15,.7,5),(0,-4.5,-5),.2)
        h.vent((0,-4.5,-6),17,12)
    elif did == 'trade_station':
        h.ring('base',38,15,9,(0,0,0),sides=16)
        h.ring('base',28,11,7,(0,15,0),sides=16)
        h.ring('dark',31,28,4,(0,-6,0),sides=16)
        h.ring('cool',37,36,1,(0,5,0),sides=16)
        h.loft('base',((-12,10,38,19),(10,10,38,19),(14,4,29,19)),2)
        for i in range(4):
            a=i*90; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('dark',(7,5,21),(s*42,-2,c*42),1,a)
            h.bay((s*63,-1,c*63),17,13,20,a)
            h.plate('accent',(16,1,12),(s*54,7,c*54),.3,a)
            h.plate('lit',(15,2,.7),(s*27.8,17,c*27.8),.2,a)
        h.plate('trim',(3,17,3),(0,43,0),.6)
        h.plate('lit',(17,2,.7),(0,33,11.2),.2)
    elif did == 'fighter_platform':
        h.loft('base',((-42,33,8,-1),(24,33,8,-1),(44,22,8,-1)),3)
        h.plate('dark',(45,11,43),(0,-6,0),2)
        for s in (-1,1):
            h.plate('accent',(6,1,65),(s*24,8.6,0),.3)
            h.plate('cool',(1.5,1,72),(s*30,8.6,-1),.3)
        h.loft('base',((-37,8,37,8),(-22,8,37,8),(-17,4,25,8)),2,(20,0,0))
        h.plate('lit',(6,2,.7),(20,19,-16.6),.2)
        h.plate('lit',(11,.7,9),(20,37.4,-29),.2)
        h.bay((0,-2,30),26,11,12)
        h.plate('trim',(3,19,3),(20,44,-27),.6)
        h.vent((-20,8.4,-25),12,13)
    elif did == 'repair_dock':
        h.plate('base',(18,18,85),(0,-11,0),3)
        for s in (-1,1):
            h.plate('dark',(26,5,14),(s*17,-8,0),1)
            for z in (-26,26):
                h.plate('base',(7,33,9),(s*31,5,z),1.7)
                h.plate('trim',(17,5,9),(s*24,22,z),1)
                h.plate('cool',(1,24,3),(s*26.9,7,z),.3)
            h.plate('accent',(5,1,73),(s*6,-1.4,0),.3)
        h.loft('base',((-38,10,29,-1),(-25,10,29,-1),(-17,4,20,-1)),2)
        h.plate('lit',(16,2,.7),(0,23,-20),.2)
        h.vent((0,-1.5,16),12,22)
    else:  # energy_relay: toroidal core + three tall collector blades.
        h.ring('base',23,13,14,(0,0,0),sides=20)
        h.ring('cool',21,18,2,(0,8,0),sides=20)
        h.ring('dark',28,24,7,(0,-6,0),sides=20)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('base',(7,52,26),(s*33,8,c*33),2,a)
            h.plate('accent',(8,1,21),(s*33,34.5,c*33),.3,a)
            h.plate('trim',(4,57,5),(s*24,8,c*24),1,a)
            h.plate('lit',(5,2,.7),(s*46.4,8,c*46.4),.2,a)
        h.plate('trim',(3,32,3),(0,22,0),.7)
        h.plate('lit',(9,1.2,1),(0,11,21),.3)
    return h.finish()
