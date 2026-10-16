"""Render-only faction stations in the established nominal-radius-50 space.

The three canonical faction families have ten bespoke functional layouts each.
Import hardware locally: fleet_geometry can dispatch here without an import cycle.
External/mod identifiers never enter the bounded thirty-entry geometry cache.
"""
from functools import lru_cache
import math
from types import MappingProxyType

FACTIONS = ('rebel', 'confederacy', 'syndicate')
STATION_TYPES = ('command_station', 'shipyard', 'research_station', 'defense_platform',
                 'mining_station', 'sensor_station', 'trade_station', 'fighter_platform',
                 'repair_dock', 'energy_relay')


def station_mesh(faction, data_id):
    """Return immutable six-role triangles; unknown faction keeps Imperial fallback.

    Unknown types canonicalize to research_station before cache lookup. Arguments
    need not be hashable. No entity, team color, time or simulation data is read.
    """
    kind = data_id if isinstance(data_id, str) and data_id in STATION_TYPES else 'research_station'
    if not isinstance(faction, str) or faction not in FACTIONS:
        from .fleet_geometry import _station_mesh as imperial_station
        return imperial_station(kind)
    return _station_mesh(faction, kind)


def _capsule(h, role, width, length, height, center=(0, 0, 0), yaw=0):
    sections = [(t*length, width*w, height/2, -height/2)
                for t,w in ((-.5,.12),(-.46,.60),(-.37,.92),(-.20,1),
                            (0,1),(.24,.94),(.39,.73),(.47,.38),(.5,.08))]
    h.loft(role, sections, min(width*.38, height*.30), center, yaw)


def _ellipse(h, role, outer, inner, height, sx, sz, center=(0,0,0), pitch=0):
    from .fleet_geometry import _ring
    mesh = []
    for normal, tri in _ring(outer, inner, height, 32):
        n = (normal[0]/sx, normal[1], normal[2]/sz)
        length = math.sqrt(sum(v*v for v in n))
        mesh.append((tuple(v/length for v in n),
                     tuple((x*sx,y,z*sz) for x,y,z in tri)))
    h.add(role, mesh, center, pitch=pitch)


def _cargo(h, x, y, z, size=1.0, yaw=0):
    h.plate('dark',(13*size,10*size,21*size),(x,y,z),.8,yaw)
    h.plate('trim',(13.8*size,1,22*size),(x,y+5.4*size,z),.4,yaw)
    for t in (-.33,.33):
        h.plate('accent',(14*size,1.5,1.6),(x,y+6.1*size,z+t*21*size),.3,yaw)


def _crew(h, x, y, z, width=9, length=30, yaw=0):
    """Linked rounded habitat with exterior roof glazing and cooling ribs."""
    _capsule(h,'base',width,length,12,(x,y,z),yaw)
    _capsule(h,'accent',width*.7,length*.74,.8,(x,y+6.5,z),yaw)
    _capsule(h,'lit',width*.44,length*.4,.7,(x,y+7.3,z),yaw)
    h.vent((x,y+6.4,z-length*.31),width*.9,5)
    h.plate('cool',(width*.8,.5,1),(x,y+7.1,z+length*.30),.15,yaw)


def _cell(h, x, y, z, radius=14, height=14):
    """Repeatable machine cell; annular upper housing exposes its dark core."""
    h.ring('base',radius,.1,height,(x,y,z),sides=6)
    h.ring('base',radius,radius*.67,4,(x,y+height/2+2,z),sides=6)
    h.ring('dark',radius*.65,.1,.8,(x,y+height/2+.5,z),sides=6)
    h.ring('cool',radius*.82,radius*.73,.6,(x,y+height/2+4.4,z),sides=6)
    h.plate('accent',(radius*.8,.7,3),(x,y+height/2+4.5,z+radius*.65),.2)
    h.plate('lit',(radius*.4,.5,2),(x,y+height/2+1.1,z),.15)
    h.ring('trim',radius*1.05,radius*.95,1,(x,y-height/2,z),sides=6)


def _tank(h, x, y, z, radius=12, height=30):
    h.ring('base',radius,.1,height,(x,y,z),sides=12)
    for dy in (-height*.35,height*.35):
        h.ring('trim',radius+1,radius-.5,2,(x,y+dy,z),sides=12)
    h.ring('accent',radius+.4,radius-.8,1,(x,y+height/2+.6,z),sides=12)
    h.ring('cool',radius*.7,radius*.5,.8,(x,y+height/2+1.3,z),sides=12)
    h.plate('dark',(5,height*.7,3),(x+radius,y,z),.5)
    h.plate('lit',(2,height*.5,.6),(x+radius,y,z+1.7),.2)


def _crane(h, x, y, z, reach=35, height=35, yaw=0):
    h.ring('dark',7,.1,4,(x,y,z),sides=8)
    h.plate('trim',(5,height,6),(x,y+height/2,z),1)
    h.plate('base',(reach,5,6),(x-reach/2+3,y+height,z),1,yaw)
    h.plate('accent',(reach*.7,1,4),(x-reach/2+3,y+height+3,z),.3,yaw)
    h.plate('trim',(2,height*.4,2),(x-reach+5,y+height*.8,z),.4)
    h.plate('cool',(5,1,5),(x-reach+5,y+height*.6,z),.3)


def _dish(h, x, y, z, radius=23, pitch=25):
    h.plate('dark',(5,24,5),(x,y-12,z),1)
    h.ring('base',radius,5,2,(x,y,z),pitch=pitch,sides=24)
    h.ring('trim',radius+2,radius,3,(x,y,z),pitch=pitch,sides=24)
    h.ring('cool',radius*.86,radius*.78,.7,(x,y+1.7,z),pitch=pitch,sides=24)
    h.plate('trim',(2,20,2),(x,y+8,z),.4)
    h.plate('lit',(3,1,3),(x,y+18.6,z),.3)


def _alliance_shipyard_slice(h):
    """Open-ended cradle with lateral work arms and an offset control loft."""
    for side in (-1,1):
        _capsule(h,'base',10,112,14,(side*50,-4,0))
        h.plate('base',(12,9,100),(side*50,-17,0),1.5)
        h.plate('accent',(7,1,84),(side*50,3.7,0),.3)
        for z in (-33,33):
            # Paired partial portals never span or roof the construction lane.
            h.plate('base',(8,37,9),(side*45,12,z),1.2)
            h.plate('base',(23,7,10),(side*36,29,z),1.2)
            h.plate('dark',(8,10,9),(side*28,21,z),.8)
            h.plate('cool',(7,.7,7),(side*28,26.5,z),.2)
            h.plate('trim',(14,5,8),(side*57,-2,z),1)
            _crew(h,side*63,0,z,7,26)
        for z in (-14,14):
            h.vent((side*50,3.5,z),10,12)
            h.plate('trim',(5,18,6),(side*48,10,z),.7)
            h.plate('base',(17,5,7),(side*40,19,z),.8)
            h.plate('cool',(6,.6,5),(side*35,22,z),.2)
        h.bay((side*50,-4,63),14,10,14)
        # Docking plane and exposed lower spine cooling, outside central void.
        h.plate('dark',(5,5,78),(side*41,-12,0),.6)
        h.plate('cool',(1,.6,65),(side*42,-8.9,0),.2)
    # Low end ties provide load paths without filling the working volume.
    for z in (-48,48):
        h.plate('base',(96,7,8),(0,-21,z),1)
        h.plate('trim',(76,1,5),(0,-16.9,z),.3)
    _capsule(h,'base',11,34,19,(48,38,-28))
    _capsule(h,'lit',7,20,.8,(48,48.4,-28))
    h.plate('base',(9,13,13),(48,25,-28),1)
    h.plate('accent',(14,1,8),(48,48.1,-36),.3)


def _alliance(h, kind):
    if kind == 'command_station':
        _ellipse(h,'base',40,33,8,1.15,.70)
        _ellipse(h,'accent',40.3,38.5,1,1.15,.70,(0,4.8,0))
        for s in (-1,1):
            _capsule(h,'base',15,70,17,(s*45,0,0))
            h.plate('trim',(33,4,10),(s*23,-1,0),1)
            h.bay((s*45,0,34),20,11,16)
            _capsule(h,'base',7,24,9,(0,-1,s*30),90)
        _capsule(h,'base',11,36,30,(0,17,0))
        _capsule(h,'lit',8,22,1,(0,32.6,0))
        h.plate('dark',(9,3,17),(0,-4,0),1)
    elif kind == 'shipyard':
        _alliance_shipyard_slice(h)
    elif kind == 'research_station':
        # Two separated laboratories linked to a small observation habitat.
        _ellipse(h,'trim',27,24,3,1.25,.8,(0,-5,0))
        for s in (-1,1):
            _crew(h,s*35,0,-8,12,48)
            h.plate('dark',(22,4,7),(s*19,-2,-12),1)
            _ellipse(h,'base',15,12,4,1,.8,(s*35,0,-8),90)
        _crew(h,0,12,33,10,25,90)
        h.plate('trim',(5,12,20),(0,2,20),1)
        _dish(h,0,30,33,10,18)
    elif kind == 'defense_platform':
        _ellipse(h,'base',25,18,7,1.3,1)
        for x,z,a in ((-39,0,-90),(39,0,90),(0,37,0),(0,-37,180)):
            h.plate('dark',(7,5,22),(x*.68,-2,z*.68),1,a)
            _crew(h,x,0,z,9,25,a)
            h.turret((x,7,z),1.15,a)
        _crew(h,0,3,0,7,20)
    elif kind == 'mining_station':
        _crew(h,0,5,-10,15,45)
        for s in (-1,1):
            h.plate('trim',(25,5,8),(s*23,0,-10),1)
            _capsule(h,'base',13,48,19,(s*42,-3,0))
            _ellipse(h,'accent',14,11,2,1,1,(s*42,7,0))
            h.ring('dark',11,6,5,(s*42,-16,0),sides=16)
            h.ring('cool',9,7,1,(s*42,-19,0),sides=16)
            h.plate('lit',(12,.7,5),(s*42,7.1,12),.2)
        h.bay((0,-4,28),22,13,16)
    elif kind == 'sensor_station':
        _crew(h,0,-10,-14,10,34)
        h.plate('trim',(64,4,8),(0,-8,0),1)
        for s in (-1,1):
            _crew(h,s*35,-7,0,8,23)
            _dish(h,s*35,19,0,21,32)
    elif kind == 'trade_station':
        _ellipse(h,'base',32,26,7,1.2,.9)
        _ellipse(h,'cool',31,30,1,1.2,.9,(0,4.1,0))
        for s in (-1,1):
            _crew(h,s*44,0,0,11,54)
            h.plate('dark',(24,5,8),(s*28,-1,0),1)
            for z in (-26,26):
                h.bay((s*44,-1,z),18,11,11,180 if z<0 else 0)
            _crew(h,0,0,s*36,9,32,90)
        h.plate('trim',(5,5,16),(0,0,-21),1)
    elif kind == 'fighter_platform':
        # Broad parallel launch runways, never a single plate filling the gap.
        h.plate('dark',(80,7,14),(0,-8,-33),2)
        for s in (-1,1):
            _capsule(h,'base',17,98,10,(s*33,0,0))
            for dx in (-10,10):
                h.plate('cool',(1.3,.6,81),(s*33+dx,5.5,0),.2)
            h.plate('accent',(7,1,69),(s*33,5.7,0),.3)
            _crew(h,s*53,1,-22,7,31)
            h.bay((s*33,-4,43),24,9,14)
    elif kind == 'repair_dock':
        h.plate('dark',(70,8,14),(0,-12,-35),2)
        for s in (-1,1):
            _crew(h,s*38,-4,-25,10,30)
            _capsule(h,'base',6,89,9,(s*38,-9,5))
            for z in (-16,23):
                _ellipse(h,'trim',7,4,4,1,1,(s*38,0,z),90)
                h.plate('base',(6,30,7),(s*38,13,z),1)
                h.plate('trim',(20,5,7),(s*29,27,z),1)
                h.plate('cool',(8,1,5),(s*23,24,z),.3)
            h.plate('accent',(5,.8,65),(s*38,-3.9,3),.2)
    elif kind == 'energy_relay':
        _capsule(h,'base',14,32,20,(0,0,0))
        _ellipse(h,'cool',12,9,2,1,1,(0,11,0))
        _crew(h,0,4,-28,8,20,90)
        for s in (-1,1):
            h.plate('trim',(28,5,7),(s*23,-2,0),1)
            # Two large separated collector wings with segmented power cells.
            _ellipse(h,'base',24,19,5,.75,1.15,(s*45,3,0),24)
            for z in (-17,0,17):
                h.plate('dark',(23,3,12),(s*45,4,z),1,pitch=24)
                h.plate('accent',(20,.7,9),(s*45,6,z),.3,pitch=24)
                h.plate('cool',(17,.5,1),(s*45,7,z),.15)


def _legions(h, kind):
    if kind not in ('command_station','shipyard'):
        return _legions_roles(h,kind)
    h.ring('base',22,.1,22,(0,5,0),sides=6)
    h.ring('cool',19,17,1,(0,16.6,0),sides=6)
    for i in range(3):
        a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
        h.plate('dark',(9,9,40),(s*34,0,c*34),1,a)
        if kind == 'shipyard':
            for side in (-1,1):
                x=s*52+side*c*16; z=c*52-side*s*16
                h.plate('base',(8,14,52),(x,0,z),2,a)
                h.plate('accent',(6,1,44),(x,7.8,z),.4,a)
                h.plate('lit',(5,.6,7),(x-s*12,8.6,z-c*12),.2,a)
                h.plate('trim',(4,29,6),(x,10,z),1,a)
            h.plate('trim',(36,4,6),(s*52,25,c*52),1,a)
        elif kind == 'command_station':
            h.ring('base',21,.1,15,(s*54,0,c*54),sides=6)
            h.ring('accent',19,16,1,(s*54,8.2,c*54),sides=6)
            h.bay((s*72,0,c*72),18,10,12,a)
            h.plate('lit',(7,1,.7),(s*54,8.8,c*54),.2,a)
        else:
            raise NotImplementedError(kind)
    h.ring('base',12,.1,20,(0,25,0),sides=6)
    h.plate('trim',(3,22,3),(0,41,0),.5)


def _legions_roles(h, kind):
    if kind == 'research_station':
        # Computation pods stand above a recessed, visibly open processing core.
        h.ring('base',20,12,14,(0,-7,0),sides=6)
        h.ring('dark',12,.1,2,(0,-13,0),sides=6)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('trim',(8,5,29),(s*27,-5,c*27),1,a)
            _cell(h,s*48,1,c*48,17,23)
            h.plate('dark',(22,3,25),(s*48,-14,c*48),1,a)
            h.plate('cool',(17,.7,18),(s*48,-12,c*48),.3,a)
    elif kind == 'defense_platform':
        _cell(h,0,-4,0,18,12)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('base',(12,9,28),(s*27,-3,c*27),2,a)
            _cell(h,s*44,0,c*44,16,12)
            h.turret((s*44,11,c*44),1.6,a)
    elif kind == 'mining_station':
        _cell(h,0,0,0,20,18)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('base',(12,7,26),(s*28,-4,c*28),1,a)
            _cell(h,s*44,-2,c*44,14,15)
            # Identical deep extractor cylinders and toothed intake throats.
            h.ring('dark',11,6,28,(s*44,-23,c*44),sides=6)
            for y in (-18,-29,-37):
                h.ring('trim',13,9,3,(s*44,y,c*44),sides=6)
            h.ring('cool',8,6,1,(s*44,-38.8,c*44),sides=6)
    elif kind == 'sensor_station':
        _cell(h,0,-8,0,18,18)
        h.plate('trim',(5,33,5),(0,16,0),1)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('base',(7,6,32),(s*24,-5,c*24),1,a)
            h.plate('trim',(5,31,5),(s*41,8,c*41),1)
            h.plate('dark',(32,38,4),(s*41,29,c*41),1,a)
            # Three planar antenna arrays, not circular dishes.
            for y in (17,29,41):
                h.plate('base',(29,9,3),(s*41,y,c*41),.7,a)
                h.plate('cool',(26,7,.6),(s*43.1,y,c*43.1),.2,a)
    elif kind == 'trade_station':
        h.ring('base',34,23,10,sides=6)
        h.ring('cool',32,30,1,(0,5.8,0),sides=6)
        for i in range(6):
            a=i*60; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('dark',(9,6,23),(s*36,-2,c*36),1,a)
            h.bay((s*57,0,c*57),19,14,17,a)
            _cell(h,s*41,13,c*41,9,10)
    elif kind == 'fighter_platform':
        # Six deep drone launch cells on two factory rails, open central lane.
        h.plate('dark',(76,8,13),(0,-7,-39),1)
        for side in (-1,1):
            h.plate('base',(13,12,90),(side*33,-2,0),2)
            for z in (-27,0,27):
                _cell(h,side*43,4,z,11,12)
                h.bay((side*31,0,z+10),18,12,15)
            h.plate('accent',(6,.8,72),(side*33,4.7,0),.3)
    elif kind == 'repair_dock':
        h.plate('dark',(73,9,13),(0,-14,-37),2)
        for side in (-1,1):
            h.plate('base',(12,12,91),(side*35,-8,0),2)
            for z in (-28,0,28):
                _cell(h,side*42,-1,z,9,10)
                # Repeated robotic clamps reach toward, not across, the lane.
                h.plate('trim',(5,34,6),(side*29,13,z),1)
                h.plate('base',(15,6,8),(side*24,30,z),1)
                h.plate('cool',(5,2,6),(side*18,26,z),.4)
    elif kind == 'energy_relay':
        _cell(h,0,-4,0,22,20)
        for i in range(3):
            a=i*120; s,c=math.sin(math.radians(a)),math.cos(math.radians(a))
            h.plate('trim',(8,6,26),(s*27,-7,c*27),1,a)
            h.plate('base',(8,58,29),(s*43,9,c*43),2,a)
            h.plate('dark',(9,48,23),(s*43.8,9,c*43.8),1,a)
            for y in (-9,8,25):
                h.plate('cool',(1,10,20),(s*48,y,c*48),.3,a)
            h.plate('accent',(7,1,25),(s*43,39,c*43),.3,a)


def _syndicate(h, kind):
    if kind not in ('command_station','shipyard'):
        return _syndicate_roles(h,kind)
    h.plate('base',(42,15,45),(0,0,0),3,yaw=14)
    h.plate('base',(20,29,24),(-10,21,-12),2,yaw=-12)
    h.plate('lit',(14,2,1),(-10,30,0),.3,yaw=-12)
    h.plate('trim',(2,26,2),(-17,44,-16),.4)
    for x,y,z,a in ((-45,7,-16,77),(34,-4,24,-28),(4,-11,-48,7)):
        h.plate('dark',(11,9,49),(x*.6,y,z*.6),1,a)
        h.plate('base',(28,16,35),(x,y,z),2,a)
        _cargo(h,x,y+14,z,1.15,a)
    if kind == 'shipyard':
        h.plate('base',(11,12,104),(46,-4,4),2,yaw=-8)
        for z in (-25,29):
            h.plate('trim',(5,41,7),(48,13,z),1)
            h.plate('trim',(56,5,7),(23,34,z),1,yaw=-6)
        h.bay((46,-4,60),16,12,18)
        h.ring('base',26,21,6,(-33,2,35),pitch=73,sides=8)
    elif kind == 'command_station':
        h.ring('base',23,17,8,(37,8,25),pitch=18,sides=8)
        h.plate('accent',(27,1,19),(0,8.2,2),.4,yaw=14)
        h.bay((-45,7,6),20,12,15,yaw=-16)
    else:
        raise NotImplementedError(kind)


def _salvage_cab(h, x, y, z, yaw=0):
    h.plate('base',(15,21,20),(x,y,z),2,yaw)
    h.plate('accent',(13,1,16),(x,y+11,z),.3,yaw)
    h.plate('lit',(10,.7,8),(x,y+11.9,z),.2,yaw)
    h.plate('lit',(10,2,.7),(x,y+5,z+10.3),.2,yaw)
    h.vent((x,y+11.8,z-6),9,4)
    h.plate('cool',(5,.7,1),(x,y+12,z+7),.2,yaw)


def _syndicate_roles(h, kind):
    if kind == 'research_station':
        # Retrofitted longitudinal labs plus mismatched exposed coolant tanks.
        h.plate('base',(32,12,64),(-12,-3,0),2,11)
        h.plate('base',(23,16,33),(26,2,19),2,-19)
        h.plate('dark',(27,7,9),(6,-1,11),1)
        _salvage_cab(h,-17,13,-22,-9)
        _tank(h,30,12,-18,13,31)
        _tank(h,7,7,32,8,21)
        _dish(h,-35,28,19,13,43)
        _cargo(h,-32,8,6,.8,11)
    elif kind == 'defense_platform':
        h.plate('base',(69,16,52),(-5,0,0),4,8)
        h.plate('dark',(75,5,58),(-5,-11,0),2,8)
        # Unequal gun foundations and caliber, with bolted perimeter armor.
        for x,z,size,a in ((-29,17,1.8,-65),(23,19,1.15,42),(8,-22,.85,160)):
            h.plate('base',(18,9,17),(x,10,z),2,a)
            h.turret((x,15,z),size,a)
        _salvage_cab(h,-14,15,-16,-7)
        for z in (-14,7,25):
            h.plate('trim',(8,8,15),(-40,2,z),1,8)
        _cargo(h,29,7,-16,.8,-13)
    elif kind == 'mining_station':
        h.plate('base',(41,16,57),(-13,-7,0),3,9)
        _tank(h,-12,13,-5,21,43)
        h.plate('dark',(37,6,31),(27,-9,14),1,-12)
        for z in (-4,19,39):
            _cargo(h,32,1,z,1.05,-12)
        _crane(h,46,2,-17,49,44,-8)
        _salvage_cab(h,-33,9,22,12)
        h.ring('dark',16,8,11,(-12,-34,-5),sides=8)
        h.ring('trim',18,13,3,(-12,-39,-5),sides=8)
    elif kind == 'sensor_station':
        h.plate('base',(45,14,39),(-8,-15,0),3,-12)
        _salvage_cab(h,16,0,15,9)
        _dish(h,-23,31,-10,34,39)
        _cargo(h,25,-7,-19,.95,-8)
        h.plate('trim',(3,37,3),(24,26,16),.5)
        h.plate('accent',(5,17,5),(-23,9,-10),1)
    elif kind == 'trade_station':
        h.plate('base',(39,18,43),(-7,-2,-7),3,13)
        _salvage_cab(h,-18,18,-15,-13)
        for x,z,a,length in ((-42,12,-75,42),(33,25,24,62),(10,-41,170,36)):
            h.plate('dark',(12,8,length),(x*.68,-6,z*.68),1,a)
            h.plate('base',(24,10,length),(x,-3,z),2,a)
            h.bay((x+math.sin(math.radians(a))*length*.4,-1,
                   z+math.cos(math.radians(a))*length*.4),19,12,15,a)
            _cargo(h,x,8,z,.9,a)
        _cargo(h,8,20,0,.7,13)
    elif kind == 'fighter_platform':
        # Salvaged barge deck, side-mounted service tower and single crane.
        h.loft('base',((-49,24,5,-8),(-31,31,5,-8),(30,29,5,-8),(49,18,5,-8)),3)
        h.plate('dark',(37,14,51),(9,-12,-8),2,-7)
        _salvage_cab(h,-25,20,-25,5)
        _crane(h,-24,6,13,28,29)
        h.bay((9,-3,47),28,13,18)
        h.plate('accent',(7,1,77),(13,5.7,-1),.3)
        h.plate('cool',(1.5,.7,86),(25,5.7,0),.2)
        for z in (-29,-7):
            _cargo(h,34,3,z,.75,-7)
    elif kind == 'repair_dock':
        # Heavy asymmetric U cradle; salvage machinery stays outside its void.
        h.plate('base',(77,14,18),(0,-14,-37),2,-4)
        h.plate('base',(19,16,88),(-35,-10,3),2,3)
        h.plate('base',(12,10,64),(31,-11,-7),2,-8)
        for z in (-18,26):
            h.plate('trim',(9,33,8),(-31,8,z),1)
            h.plate('base',(17,7,10),(-25,24,z),1)
            h.plate('cool',(7,1,7),(-19,19,z),.3)
        _crane(h,35,-3,-20,39,43,-5)
        _salvage_cab(h,-35,12,-30,3)
        for z in (-1,23):
            _cargo(h,43,2,z,.8,-8)
    elif kind == 'energy_relay':
        h.plate('base',(33,14,34),(-8,-7,0),3,12)
        _tank(h,-9,9,0,16,37)
        _tank(h,18,0,-20,9,23)
        _salvage_cab(h,-26,5,-24,-7)
        for x,z,a,width,length in ((-42,8,-15,23,49),(35,20,32,34,33),(9,-43,-7,21,28)):
            h.plate('trim',(8,6,35),(x*.6,-6,z*.6),1,a)
            h.plate('base',(width,5,length),(x,-2,z),1,a)
            h.plate('dark',(width-3,1,length-4),(x,1.4,z),.4,a)
            for t in (-.3,0,.3):
                h.plate('accent',(width-5,.7,length*.23),(x,2.4,z+t*length),.2,a)
            h.plate('cool',(width*.75,.6,1),(x,3.2,z),.2,a)


@lru_cache(maxsize=30)
def _station_mesh(faction, kind):
    if faction == 'rebel' and kind == 'shipyard':
        from .authored_mesh import shipyard_mesh
        try:
            # Authored station is already in the final nominal-radius-50 space.
            return shipyard_mesh()
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            import warnings
            warnings.warn(f'Alliance shipyard asset unavailable; using procedural yard: {exc}',
                          RuntimeWarning, stacklevel=2)
    from .fleet_geometry import _Hardware
    h = _Hardware()
    {'rebel': _alliance, 'confederacy': _legions, 'syndicate': _syndicate}[faction](h,kind)
    # Concept studies were framed individually. Fit their dimensions back into
    # the established radius-50 material space without changing proportions.
    return MappingProxyType({role: tuple((n, tuple(tuple(v*.8 for v in p) for p in tri))
                                        for n,tri in triangles)
                             for role,triangles in h.finish().items()})
