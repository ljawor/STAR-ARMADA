"""Original non-Imperial ship hardware, in model space (+Z forward).

Pure triangle data only: no GL, catalogue, gameplay or random state. Material
roles and immutable storage are supplied by fleet_geometry's lazy _Hardware
import, allowing the legacy facade to dispatch here without an import cycle.
"""
from functools import lru_cache


FACTIONS = ('rebel', 'confederacy', 'syndicate')
SHIP_ROLES = ('fighter', 'bomber', 'corvette', 'frigate', 'cruiser',
              'battleship', 'supercapital', 'constructor', 'colonizer', 'convoy')


def ship_mesh(faction, role):
    """Return an immutable six-material mesh; normalize before bounded caching.

    Faction IDs are rebel/confederacy/syndicate, not display names. Unknown IDs
    raise ValueError instead of hiding a dispatch error behind another faction.
    """
    faction = faction.strip().lower() if isinstance(faction, str) else ''
    role = role.strip().lower() if isinstance(role, str) else ''
    if faction not in FACTIONS or role not in SHIP_ROLES:
        raise ValueError(f'unknown faction ship: {faction!r}:{role!r}')
    return _ship_mesh(faction, role)


@lru_cache(maxsize=30)
def _ship_mesh(faction, role):
    from render.fleet_geometry import _Hardware
    h = _Hardware()
    if role in ('fighter', 'bomber'):
        {'rebel': _alliance_small, 'confederacy': _legions_small,
         'syndicate': _syndicate_small}[faction](h, role == 'bomber')
    elif role in ('corvette', 'frigate', 'cruiser'):
        level = ('corvette', 'frigate', 'cruiser').index(role)
        {'rebel': _alliance_line, 'confederacy': _legions_line,
         'syndicate': _syndicate_line}[faction](h, level)
    elif role in ('battleship', 'supercapital'):
        {'rebel': _alliance_capital, 'confederacy': _legions_capital,
         'syndicate': _syndicate_capital}[faction](h, role == 'supercapital')
    else:
        {'rebel': _alliance_logistics, 'confederacy': _legions_logistics,
         'syndicate': _syndicate_logistics}[faction](h, role)
    return h.finish()


def _alliance_small(h, bomber):
    # Interceptor has a slim cockpit and two swept drive booms; the strike craft
    # adds a broad belly, separated torpedo cylinders and a rear gun mount.
    length, width, offset = (46,6,13) if bomber else (32,3.6,9)
    _capsule(h,'base',width,length,6 if bomber else 4)
    _capsule(h,'dark',width*.75,length*.34,4,(0,4,-2))
    _capsule(h,'lit',width*.48,length*.22,.5,(0,6.3,-1))
    for side in (-1,1):
        h.plate('trim',(offset,1.8,5),(side*offset/2,-.5,-4),.4,yaw=side*18)
        _capsule(h,'base',2.8,length*.8,5,(side*offset,0,-4))
        _capsule(h,'accent',1.3,length*.58,.5,(side*offset,2.9,-4))
        h.nozzle((side*offset,0,-6-length*.4),2)
        h.ring('trim',3,2.5,.6,(side*offset,0,-6),pitch=90,sides=12)
        h.loft('trim',((-8,.5,.5,-.5),(8,.4,.4,-.4)),.15,(side*offset,0,10))
        if bomber:
            for x in (side*5,side*8.5):
                _capsule(h,'dark',1.6,26,3,(x,-5,3))
                h.ring('accent',1.8,1.35,.7,(x,-5,11),pitch=90,sides=12)
            h.plate('base',(5,2,28),(side*6.5,-3,0),.5)
    if bomber:
        h.turret((0,4,-15),.3)
        h.vent((0,3.4,12),7,7)
    else:
        h.plate('trim',(1,6,4),(0,5,-12),.2,pitch=-18)


def _legions_small(h, bomber):
    length, offset, width = (44,10,4.5) if bomber else (30,7,2.8)
    h.plate('dark',(offset*2,5,9),(0,0,-length*.25),.8)
    for side in (-1,1):
        h.loft('base',((-length*.45,width,3,-3),(-4,width,3,-3),
                       (length*.5,width*.5,2,-2)),.7,(side*offset,0,0))
        h.plate('accent',(width*1.3,.5,length*.7),(side*offset,3.4,0),.2)
        h.nozzle((side*offset,0,-length*.47),2)
        h.plate('trim',(1.1,1.1,10),(side*offset,0,length*.48),.2)
        _machine_pod(h,(side*(offset+width),0,-5),3.5,6)
        if bomber:
            for z in (-7,5):
                _machine_pod(h,(side*offset,-5,z),4,4,'trim')
                h.plate('dark',(5,3,8),(side*offset,-4,z),.6)
    _machine_pod(h,(0,3,-length*.25),5 if bomber else 3.5,7,'cool')
    h.plate('lit',(3,.5,1.2),(0,7,-length*.25),.2)
    if bomber:
        # Four box-launchers with exposed, forward-facing aperture collars.
        for side in (-1,1):
            h.bay((side*offset,-4,15),5,4,6)
        h.plate('trim',(2,8,2),(0,9,-12),.3)


def _syndicate_small(h, bomber):
    length, width = (42,9) if bomber else (30,6)
    h.loft('base',((-length*.5,width*.7,3,-4),(-4,width,3,-4),
                   (length*.48,width*.55,2,-3)),1)
    h.plate('base',(width*.7,5,length*.64),(-width*.8,3,1),.8,yaw=6)
    h.plate('accent',(width*.55,.5,length*.5),(-width*.8,5.9,1),.2,yaw=6)
    h.plate('dark',(5,4,9),(width*.5,4,-5),.7,yaw=-12)
    h.plate('lit',(3,.5,5),(width*.5,6.4,-4),.2,yaw=-12)
    h.plate('trim',(1,6,1),(width*.6,9,-8),.2)
    h.nozzle((-width*.4,-1,-length*.53),2.8)
    h.nozzle((width*.8,-1,-length*.52),1.8)
    _cargo(h,width,3,5,.35 if not bomber else .55)
    if bomber:
        h.plate('trim',(12,2,5),(width,0,-6),.5)
        h.plate('dark',(6,5,28),(width*1.8,-2,-2),.8)
        for z in (-7,2,11):
            _cargo(h,width*1.8,2,z,.32)
        h.bay((width*1.8,-2,17),6,5,7)
        h.turret((-width*.4,6,10),.3,yaw=8)
    else:
        h.plate('trim',(1,1,19),(-width*.8,2,15),.2)


def _alliance_capital(h, flagship):
    length, width, offset = (380,32,76) if flagship else (270,24,55)
    _capsule(h,'base',width,length,26 if flagship else 20)
    # Stepped command island follows the rounded fuselage rather than an
    # Imperial tower; forward turret banks occupy the remaining dorsal deck.
    for y,w,l,z in ((20,width*.75,length*.32,-length*.18),
                    (34,width*.48,length*.19,-length*.20)):
        _capsule(h,'base',w,l,14,(0,y,z))
    _capsule(h,'lit',width*.35,length*.12,.7,(0,41.7,-length*.20))
    for side in (-1,1):
        _capsule(h,'base',width*.65,length*.86,19,(side*offset,-2,-length*.08))
        _capsule(h,'accent',width*.28,length*.65,.8,(side*offset,8.2,-length*.08))
        for z in (-.30,-.12,.06,.24):
            h.ring('trim',width*.67,width*.58,1.8,
                   (side*offset,-2,length*z),pitch=90,sides=16)
            h.plate('dark',(offset,6,13),(side*offset/2,-3,length*z),1,yaw=side*10)
            h.turret((side*offset,9,length*z),1.2 if flagship else 1)
        h.nozzle((side*offset,-2,-length*.53),7 if flagship else 5.5)
        # Independent flight modules with empty space ahead of each bay.
        for z in ((-70,0,70) if flagship else (12,)):
            x = side*(offset+width+17)
            _capsule(h,'base',13,76,14,(x,-8,z))
            h.plate('trim',(width+22,4,12),(side*(offset+width/2+8),-6,z-20),1)
            if flagship and z != 70:
                h.bay((x+side*21,-8,z),22,12,20,yaw=side*90)
            else:
                h.bay((x,-8,z+46),22,12,20)
            if not flagship or z == -70:
                h.nozzle((x,-8,z-41),3.8)
            h.vent((x,-.6,z-16),15,17)
    for z in ((0,42,85,123) if flagship else (0,42,84)):
        h.turret((0,14 if flagship else 11,z),1.4 if flagship else 1.1)
    h.vent((0,14 if flagship else 11,-length*.40),width,22)
    h.plate('trim',(3,20,3),(0,47,-length*.22),.6)
    if flagship:
        # A ventral logistics keel and paired aft command auxiliary drives are
        # additional modules, not a uniformly enlarged battleship.
        _capsule(h,'dark',18,210,17,(0,-22,-30))
        for x in (-15,15):
            _capsule(h,'base',7,70,12,(x,-18,-140))
            h.nozzle((x,-18,-177),4)
        for side in (-1,1):
            h.bay((side*25,-20,83),16,12,18)


def _legions_capital(h, flagship):
    length, split, width = (360,75,31) if flagship else (260,51,24)
    h.plate('dark',(split*2,20,length*.30),(0,-4,-length*.31),3)
    for side in (-1,1):
        h.loft('base',((-length*.48,width*.7,12,-12),(-length*.3,width,14,-12),
                       (length*.30,width,12,-12),(length*.48,width*.6,8,-8)),3,(side*split,0,0))
        h.plate('accent',(width*1.25,1.2,length*.65),(side*split,14.8,-6),.4)
        h.bay((side*split,0,length*.49+10),width*1.3,17,24)
        for x in (side*(split-9),side*(split+9)):
            h.nozzle((x,-3,-length*.49),5)
        # Interchangeable six-sided machine pods on lateral rails.
        for z in ((-105,-45,15,75) if flagship else (-67,-10,47)):
            x = side*(split+width+21)
            h.plate('trim',(35,6,12),(side*(split+width+5),-5,z),1)
            _machine_pod(h,(x,0,z),19 if flagship else 16,22)
            h.vent((x,11.4,z),15,14)
            h.turret((side*split,15,z-8),1.2)
        if flagship:
            # A second lower factory deck, with accessible bow launch mouths.
            h.plate('base',(38,12,170),(side*(split+width+22),-22,-26),2)
            h.bay((side*(split+width+22),-22,73),28,13,23)
    _machine_pod(h,(0,8,-length*.31),30 if flagship else 23,36,'cool')
    h.plate('lit',(16,.8,4),(0,27.2,-length*.31),.3)
    for x in (-12,12):
        h.plate('trim',(3,25,3),(x,37,-length*.31),.7)
    if flagship:
        _machine_pod(h,(0,0,-35),20,24,'cool')
        h.plate('dark',(14,9,55),(0,-4,-66),1)
        h.plate('lit',(9,.6,3),(0,12.7,-35),.2)


def _syndicate_capital(h, flagship):
    length, width = (365,57) if flagship else (260,42)
    h.loft('base',((-length*.5,width*.83,10,-16),(-length*.32,width,12,-16),
                   (length*.26,width*.9,9,-15),(length*.48,width*.65,5,-12)),3)
    for z in ((-125,-66,-7,52,111) if flagship else (-84,-28,28,84)):
        h.plate('base',(width*.75,15,48),(-width*.85,11,z),3,yaw=5 if z>0 else -4)
        h.plate('accent',(width*.62,1,35),(-width*.85,19.2,z),.4)
        h.turret((-width*.65,20,z),1.5 if flagship else 1.2,yaw=8)
        for x in (width*.25,width*.73):
            _cargo(h,x,19,z,1.25 if flagship else 1)
    # Tall offset bridge is recognizably the same accreted barge family.
    h.plate('base',(31,34,44),(width*.95,26,-length*.32),3,yaw=-9)
    h.plate('base',(22,17,28),(width*.99,49,-length*.34),2,yaw=-9)
    h.plate('lit',(17,.7,9),(width*.99,58.2,-length*.34),.3,yaw=-9)
    h.plate('trim',(3,30,3),(width*1.08,67,-length*.36),.6)
    # One-sided salvage deck: several empty hangar mouths in front of short
    # side modules, opposed by thick uninterrupted port armor.
    for z in ((-70,0,70) if flagship else (24,)):
        x = width*1.65
        h.plate('dark',(25,13,66),(x,-11,z-12),2,yaw=-5)
        h.plate('trim',(width,5,11),(width*1.20,-8,z-30),1)
        if flagship and z != 70:
            h.bay((x+22,-11,z),26,16,21,yaw=90)
        else:
            h.bay((x,-11,z+37),26,16,21)
        _cargo(h,x,7,z-15,.95)
    engines = ((-width*.6,-8,-length*.53,8),
               (width*.2,-9,-length*.51,6),
               (width*.9,-8,-length*.48,4.5))
    for x,y,z,radius in engines:
        h.nozzle((x,y,z),radius)
    h.vent((-width*.25,12.5,-length*.39),24,23)
    if flagship:
        # Suspended cargo spine and an unequal overhead loading crane.
        h.plate('dark',(30,10,200),(width*1.3,-29,-22),2)
        for z in (-85,-38,9,56):
            _cargo(h,width*1.3,-17,z,1.15)
        h.plate('trim',(5,44,7),(width*1.65,25,-95),1)
        h.plate('trim',(85,6,7),(width*.98,48,-95),1,yaw=11)
        h.plate('dark',(6,17,7),(width*.4,37,-103),1)
        for x in (-width*.25,width*.55):
            h.nozzle((x,-22,-length*.50),4)


def _alliance_logistics(h, role):
    if role == 'constructor':
        _capsule(h,'base',8,64,12,(0,0,-6))
        _capsule(h,'dark',6,22,9,(0,10,-5))
        _capsule(h,'lit',4,13,.7,(0,15,-3))
        for side in (-1,1):
            _capsule(h,'base',6,53,10,(side*19,-1,-8))
            _capsule(h,'accent',3,35,.6,(side*19,4.5,-8))
            h.nozzle((side*19,-1,-37),3)
            h.plate('trim',(24,4,7),(side*11,0,-17),1)
            # Two-jointed elevated work booms and inward-facing solid jaws.
            h.plate('trim',(3,25,4),(side*19,16,7),.6,pitch=-20)
            h.plate('trim',(4,4,24),(side*19,28,22),.7,pitch=12)
            h.plate('dark',(9,6,5),(side*16,26,33),.8)
            h.plate('cool',(3,.5,3),(side*16,29.4,33),.2)
            h.ring('trim',6,5,.8,(side*19,-1,-12),pitch=90,sides=16)
        h.bay((0,-2,33),10,8,9)
    elif role == 'colonizer':
        _capsule(h,'base',11,91,14)
        _capsule(h,'base',8,33,20,(0,14,-12))
        _capsule(h,'lit',6,21,.7,(0,24.8,-12))
        for side in (-1,1):
            # Habitat cylinders carry wide exterior roof lights and docking
            # collars; a shared raised loop connects them to the command pod.
            _capsule(h,'base',13,80,22,(side*29,0,-2))
            _capsule(h,'dark',6,49,1,(side*29,11.5,-2))
            _capsule(h,'lit',4,34,.6,(side*29,12.4,-2))
            h.plate('accent',(16,1,30),(side*29,11.9,24),.3)
            for z in (-23,1,25):
                h.ring('trim',13.5,12.3,1.2,(side*29,0,z),pitch=90,sides=16)
            h.plate('dark',(37,6,9),(side*17,-4,-16),1)
            h.nozzle((side*29,0,-45),4)
            h.bay((side*29,-2,48),16,12,14)
        h.ring('trim',23,20,3,(0,7,-10),sides=24)
        h.plate('trim',(2,13,2),(0,30,-22),.4)
    else:  # convoy: exposed rounded freight tanks on an open central spine.
        h.plate('dark',(11,8,123),(0,-5,-2),1)
        _capsule(h,'base',7,29,14,(0,8,43))
        _capsule(h,'lit',5,17,.6,(0,15.7,43))
        for side in (-1,1):
            _capsule(h,'base',5,51,10,(side*26,-4,-43))
            _capsule(h,'accent',2.4,35,.6,(side*26,1.5,-43))
            h.nozzle((side*26,-4,-71),3.5)
            for z in (-31,0,31):
                h.plate('trim',(31,3,7),(side*15,-4,z),.7)
                _capsule(h,'base',10,27,17,(side*20,2,z))
                _capsule(h,'dark',5,20,.6,(side*20,11.1,z))
                h.ring('trim',10.4,9.4,.9,(side*20,2,z),pitch=90,sides=16)
                h.plate('accent',(11,.6,4),(side*20,11.8,z),.2)
        h.vent((0,-.5,-49),8,13)


def _legions_logistics(h, role):
    length = {'constructor':66,'colonizer':100,'convoy':128}[role]
    split = 19 if role == 'constructor' else 26
    h.plate('dark',(split*2,10,19),(0,-2,-length*.32),1.5)
    for side in (-1,1):
        h.loft('base',((-length*.48,6,6,-6),(-length*.1,7,6,-6),
                       (length*.45,4,4,-4)),1.2,(side*split,0,0))
        h.plate('accent',(7,.8,length*.61),(side*split,6.6,-5),.3)
        h.nozzle((side*split,0,-length*.5),3.5)
    _machine_pod(h,(0,8,-length*.25),10,16,'cool')
    h.plate('lit',(7,.6,3),(0,16.8,-length*.25),.2)
    if role == 'constructor':
        for side in (-1,1):
            _machine_pod(h,(side*30,3,-9),9,12)
            h.plate('trim',(12,4,8),(side*25,0,-9),.7)
            h.plate('trim',(4,26,5),(side*19,15,12),.8)
            h.plate('base',(5,5,19),(side*19,28,20),.8)
            h.ring('cool',5,4,1,(side*19,28,31),pitch=90,sides=6)
            h.plate('dark',(9,6,6),(side*16,26,31),.8)
        h.bay((0,-3,24),13,9,11)
    elif role == 'colonizer':
        for side in (-1,1):
            for z in (-21,15):
                _machine_pod(h,(side*39,7,z),16,25,'trim')
                h.ring('lit',12,10,.7,(side*39,20.5,z),sides=6)
                h.plate('dark',(18,5,9),(side*31,-3,z),1)
            h.bay((side*split,0,55),13,10,13)
        _machine_pod(h,(0,22,-25),7,11,'accent')
        h.plate('lit',(6,.7,3),(0,28.4,-25),.2)
        h.plate('trim',(2,17,2),(0,35,-25),.4)
    else:
        # Rectangular freight saddles underneath repeated hexagonal containers,
        # leaving the split nose visible at the head of this machine train.
        for side in (-1,1):
            for z in (-37,-5,27):
                h.plate('dark',(21,12,27),(side*split,7,z),1)
                _machine_pod(h,(side*split,15,z),12,10,'trim')
                h.plate('accent',(9,.8,7),(side*split,20.9,z),.3)
                h.plate('trim',(split*2,3,6),(0,-5,z),.7)
        h.plate('trim',(3,15,3),(0,22,-length*.25),.5)


def _syndicate_logistics(h, role):
    length = {'constructor':73,'colonizer':105,'convoy':141}[role]
    width = 17 if role == 'constructor' else 24
    h.loft('base',((-length*.5,width*.8,5,-9),(-length*.28,width,7,-9),
                   (length*.44,width*.73,4,-8)),2)
    # Compact starboard bridge and mismatched aft drives on every civilian hull.
    h.plate('base',(13,17,19),(width*.8,13,-length*.30),1.5,yaw=-10)
    h.plate('lit',(8,.6,5),(width*.8,22.1,-length*.30),.2,yaw=-10)
    h.plate('trim',(2,15,2),(width*.95,29,-length*.33),.4)
    h.nozzle((-width*.50,-2,-length*.53),4.5)
    h.nozzle((width*.8,-3,-length*.51-1),3)
    for z in (-length*.25,length*.06,length*.32):
        h.plate('base',(width*.6,8,length*.23),(-width*.8,6,z),1.3,yaw=5)
        h.plate('accent',(width*.5,.7,length*.17),(-width*.8,10.8,z),.25,yaw=5)
    if role == 'constructor':
        _cargo(h,7,11,10,.85)
        h.plate('trim',(5,30,6),(-width*1.2,17,-8),.9,yaw=8)
        h.plate('trim',(39,5,6),(-6,32,-8),.9,yaw=-11)
        h.plate('dark',(5,19,6),(12,22,-5),.7)
        h.plate('cool',(3,.5,4),(12,32,-5),.2)
        h.plate('dark',(10,6,28),(width*1.4,-3,8),1)
        h.bay((width*1.4,-3,32),11,8,10)
        h.vent((-5,7.5,-21),10,9)
    elif role == 'colonizer':
        # Unequal habitat blocks, one exposed circular docking habitat and a
        # second-hand port radiator make this a civilian colony barge.
        for x,y,z,w,l in ((-5,13,-9,20,29),(9,12,24,23,28),(-9,12,30,14,24)):
            h.plate('base',(w,14,l),(x,y,z),2,yaw=6 if x<0 else -4)
            h.plate('lit',(w*.6,.6,l*.4),(x,y+7.7,z),.2)
        h.ring('base',15,10,10,(width*1.35,6,8),sides=12)
        h.ring('lit',14,12,.7,(width*1.35,11.8,8),sides=12)
        h.plate('trim',(24,4,9),(width,2,8),.8)
        h.plate('dark',(10,2,49),(-width*1.15,-10,0),.5,yaw=8)
        for z in (-15,-3,9,21):
            h.plate('trim',(9,1,2),(-width*1.15,-8.4,z),.2,yaw=8)
        h.bay((0,-2,57),18,10,14)
    else:
        # Two rows of exposed freight, a one-sided low salvage cradle and the
        # little cab off-axis distinguish this from both colony and work tug.
        for z in (-39,-10,19,48):
            for x in (-3,16):
                _cargo(h,x,12,z,1)
            h.plate('trim',(40,3,6),(4,2,z),.7)
        h.plate('dark',(13,8,97),(width*1.35,-5,-5),1,yaw=-4)
        for z in (-27,6,39):
            _cargo(h,width*1.35,3,z,.60)
        h.plate('trim',(2,12,2),(width*1.4,13,-30),.5)


def _capsule(h, role, width, length, height, center=(0, 0, 0), yaw=0):
    """Rounded eight-sided ends with nine longitudinal armor segments."""
    sections = tuple((t*length, width*w, height/2, -height/2)
                     for t, w in ((-.5,.12),(-.46,.60),(-.37,.92),(-.20,1),
                                  (0,1),(.24,.94),(.39,.73),(.47,.38),(.5,.08)))
    h.loft(role, sections, min(width*.38, height*.30), center, yaw)


def _alliance_line(h, level):
    # Approved courier / escort / carrier studies: the twin nacelles stand proud
    # of the rounded center hull and retain clear gaps rather than wedge wings.
    length = (90, 145, 195)[level]
    width = (7, 11, 16)[level]
    offset = (17, 26, 38)[level]
    _capsule(h, 'base', width, length, 12+level*3)
    for side in (-1, 1):
        h.plate('dark', (offset,4,13), (side*offset/2,-1,-length*.22), 1, yaw=side*12)
        h.plate('trim', (offset,3,11), (side*offset/2,0,length*.14), 1, yaw=-side*12)
        _capsule(h, 'base', width*.68, length*.74, 10+level*3, (side*offset,0,-length*.12))
        _capsule(h, 'accent', width*.30, length*.56, .8,
                 (side*offset,6+level*1.5,-length*.12))
        h.nozzle((side*offset,0,-length*.5), 3+level)
        for z in (-.24, 0, .22):
            h.ring('trim', width*.7, width*.61, 1.2,
                   (side*offset,0,length*z-length*.10), pitch=90, sides=16)
        if level:
            # Mouth beyond the solid nacelle's rounded nose: not a dark decal.
            h.bay((side*offset,0,length*.26+7), 10+level*3, 8+level*2, 14+level*4)
            h.turret((side*offset,7+level,-length*.25), .5+level*.18)
    _capsule(h, 'dark', width*.70, length*.25, 9, (0,10+level*2,-length*.13))
    _capsule(h, 'lit', width*.48, length*.13, .6, (0,15+level*2,-length*.10))
    if level == 2:
        for side in (-1, 1):
            _capsule(h, 'base', 10, 75, 10, (side*56,-6,-18))
            h.plate('trim', (30,3,8), (side*43,-5,-42), 1)
            h.bay((side*56,-6,29), 17,9,18)


def _legions_line(h, level):
    length = (85,135,180)[level]
    width = (12,18,25)[level]
    split = (15,23,33)[level]
    h.plate('dark', (split*2,10+level*3,length*.33), (0,0,-length*.24), 2)
    for side in (-1,1):
        h.loft('base', ((-length*.40,width*.65,8,-7),
                        (-length*.15,width,8,-7),
                        (length*.40,width*.80,7,-6),
                        (length*.48,width*.55,5,-5)), 2, (side*split,0,0))
        h.plate('accent', (width*1.1,1,length*.55), (side*split,8.6,0), .3)
        h.nozzle((side*split,0,-length*.43), 4+level)
        h.bay((side*split,0,length*.49+6), width*1.1,9,13)
        _machine_pod(h, (side*(split+width*.7),0,-length*.16), width*.8,14+level*3)
        if level:
            h.turret((side*split,9,-length*.11), .7+level*.2)
    _machine_pod(h, (0,5,-length*.25), width*.95,18, 'cool')
    # Exterior amber sensor slit, above the central core, not buried glazing.
    h.plate('lit', (width*.65,.6,2), (0,14.8,-length*.25), .2)
    if level == 2:
        for z in (-35,0,35):
            for side in (-1,1):
                _machine_pod(h, (side*65,-3,z),12,10)
                h.plate('trim', (18,3,7), (side*52,-4,z),1)


def _machine_pod(h, center, radius, height, glow='accent'):
    x,y,z = center
    h.ring('base', radius,.1,height,center,sides=6)
    h.ring(glow, radius*.85,radius*.65,1, (x,y+height/2+.6,z),sides=6)


def _cargo(h, x, y, z, size: float=1.0, yaw=0):
    h.plate('dark', (13*size,10*size,21*size), (x,y,z), .8,yaw)
    h.plate('trim', (13.8*size,1,22*size), (x,y+5.4*size,z), .4,yaw)
    for t in (-.33,.33):
        h.plate('accent', (14*size,1.5,1.6), (x,y+6.1*size,z+t*21*size), .3,yaw)


def _syndicate_line(h, level):
    length = (80,130,175)[level]
    width = (17,24,32)[level]
    h.loft('base', ((-length*.5,width*.8,5,-9),(-length*.3,width,6,-9),
                    (length*.25,width*.8,5,-9),(length*.48,width*.63,3,-8)),2)
    for z in (-.30,-.02,.25):
        yaw = 7 if z == .25 else -4
        h.plate('base', (width*.8,10,length*.24), (-width*.85,5,length*z),2,yaw)
        h.plate('accent', (width*.65,1,length*.17), (-width*.85,10.6,length*z),.4,yaw)
    for z in (-.28,-.04,.20):
        _cargo(h,width*.48,8,length*z,.8+level*.25)
    h.plate('base', (12+level*5,23,24), (width*.90,15,-length*.25),2,yaw=-9)
    # Roof lantern avoids the concept's partially buried front window strip.
    h.plate('lit', (12+level*4,.6,4), (width*.90,27,-length*.25+6),.2,yaw=-9)
    h.plate('trim', (2,20,2), (width*.90,34,-length*.25),.5)
    h.turret((-width*.50,12,length*.23),.7+level*.3,yaw=12)
    h.plate('dark', (width*.6,8,length*.48), (width*1.35,-4,-length*.1),1,yaw=-8)
    h.nozzle((-width*.55,-2,-length*.52),5+level)
    h.nozzle((width*.7,-1,-length*.50-(3+level)*.4),3+level)
    if level == 1:
        # Escort refit: an independent salvage mouth and aft point-defense bank
        # distinguish it from the courier without changing the approved barge.
        h.bay((width*1.35,-4,length*.14+8),11,7,12)
        h.turret((-width*.78,11,-length*.26),.5,yaw=-12)
    if level == 2:
        h.bay((width*1.4,-4,length*.17+8),19,12,16)
        for z in (-20,12,44):
            _cargo(h,width*1.45,7,z,.85)
        h.plate('trim',(44,4,5),(width*.7,20,-45),1,yaw=18)
