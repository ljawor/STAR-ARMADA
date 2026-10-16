#!/usr/bin/env python3
"""Original Alliance Anchorage open construction cradle; editable industrial hardware."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import *
from hull_detail import *

# Two full-length structural rails; nothing fills the central construction slip.
# The rear service crosshead and two LOW under-keel ties leave an open +Z mouth.
# Frames are named because the surface-detail pass at the end reads the same
# numbers, so a panel line cannot drift off the structure it belongs to.
RAIL=((-43,5,5,-10),(-33,8,7,-12),(25,8,7,-12),(47,6,4,-8),(51,2,1,-5))
RAIL_CROWN=((-39,4,8,6),(-29,5,9,7),(28,5,9,7),(46,3,6,4))
CROSSHEAD=((-44,28,4,-8),(-39,36,9,-10),(-30,31,7,-9),(-26,25,3,-6))
TOWER=((-41,6,17,-5),(-34,8,28,-5),(-23,7,32,1),(-18,4,20,5))
HOUSING=((-9,4,4,-5),(-6,7,6,-7),(6,7,6,-7),(9,4,4,-5))
for side in (-1,1):
    x=side*33
    loft('01 Long cradle pressure rail '+str(side),'base',RAIL,.45,(x,0,0))
    loft('02 Ivory rail crown '+str(side),'trim',RAIL_CROWN,.22,(x,0,0))
    loft('Rail owner recognition band '+str(side),'accent',[(-36,1.8,9,8.2),
        (-26,2,10,9.2),(24,2,10,9.2),(42,1.3,7.5,6.8)],.05,(x+side*2,0,0))
    plate('Recessed rail machinery '+str(side),'dark',(3,1.4,53),(x-side*3,9.4,1))
    for z in range(-23,27,5):
        plate('Rail coolant rib '+str((side,z)),'base',(3.4,.8,1.4),(x-side*3,10.4,z))
    # Outboard service modules hang below the rails, never bridge the launch gap.
    for z in (-23,17):
        loft('Outboard machine housing '+str((side,z)),'base',HOUSING,.35,(side*45,-5,z))
        plate('Service housing dark face '+str((side,z)),'dark',(8,.8,12),(side*45,1.6,z))
        for dz in (-3,0,3):plate('Machine radiator fin '+str((side,z,dz)),'trim',(7,.6,1),(side*45,2.4,z+dz))
        cylinder('Side tank '+str((side,z)),'dark',(side*53,-7,z),2.3,14,n=10)
        for dz in (-5,5):annulus('Tank restraint '+str((side,z,dz)),'trim',side*53,-7,[(z+dz-.5,2.7,2.2),(z+dz+.5,2.7,2.2)],10)
    # Individual guide shoes and inward clamp fingers make the function legible.
    for z in (-23,0,24):
        plate('Cradle clamp saddle '+str((side,z)),'dark',(9,5,8),(side*27,-1,z))
        loft('Articulated construction jaw '+str((side,z)),'base',[(-3,6,2,-2),(3,5,2,-2)],.2,(side*23,2,z))
        plate('Jaw ivory contact '+str((side,z)),'trim',(3,2.4,5),(side*18.5,3.3,z))
        plate('Cyan slip alignment strip '+str((side,z)),'cool',(1.1,.5,5),(side*19,4.8,z))
    # Purpose-built low gantry frames open in the center, offset lifting hardware.
    for z in (-17,20):
        plate('Gantry vertical pedestal '+str((side,z)),'base',(5,17,6),(side*37,16,z))
        plate('Gantry hydraulic ram '+str((side,z)),'dark',(2.2,13,2.4),(side*33.1,17,z))
        plate('Gantry inward boom '+str((side,z)),'trim',(15,3.8,5),(side*31,25.4,z))
        plate('Gantry trolley '+str((side,z)),'accent',(4,4.5,6),(side*26,24,z))
        plate('Lift cable '+str((side,z)),'dark',(.8,9,.8),(side*25,18,z))
        plate('Lifting head '+str((side,z)),'base',(4,3,4),(side*25,13,z))
# Rear crosshead is a shaped pressure vessel, not a box across the whole facility.
loft('03 Rear service crosshead','base',CROSSHEAD,.55)
plate('Crosshead recessed machinery','dark',(39,1.2,5),(0,9.8,-35))
for x in range(-16,17,4):plate('Crosshead radiator '+str(x),'trim',(1.5,.8,4),(x,10.8,-35))
for z in (-18,30):
    plate('Under keel transverse tie '+str(z),'base',(68,4,6),(0,-15,z))
    plate('Tie center registration '+str(z),'accent',(10,.5,4),(0,-12.7,z))
# Offset starboard administration/habitat assembly with exposed warm glazing.
loft('04 Offset starboard operations tower','base',TOWER,.45,(43,0,0))
loft('Operations dark visor','dark',[(-35,6,31,24),(-27,7,34,26),(-20,4,28,21)],.28,(43,0,0))
loft('Operations roof armor','trim',[(-36,6.4,32,30),(-27,7.5,35.3,33.3),(-19,4.3,29.3,27.3)],.2,(43,0,0))
for side in (-1,1):
    plate('Operations exterior warm glazing '+str(side),'lit',(.7,1.8,7),(43+side*7.1,31.8,-27))
    for z in (-29,-25):plate('Operations glazing mullion '+str((side,z)),'dark',(1,2.1,.5),(43+side*7.25,31.8,z))
plate('Forward operations glazing','lit',(5.8,1.4,.6),(43,27.6,-19.8))
plate('Offset communications pedestal','base',(2.5,5,2.5),(46,36,-30))
cylinder('Communications dish','trim',(46,39,-30),3.2,.8,'Y',12)

# ---------------------------------------------------------------------------
# 05 Station surface detail. The cradle is a working structure, and at the
# shipped close camera (450 units, where one world unit is about half a pixel)
# its rails read as four long blank grey beams. Everything below is surface
# detail placed from the frame it sits on: it adds no silhouette, changes no
# clearance in the slip, and stands 0.4 to 3 units proud. Plating, trenches and
# machinery are sized for that camera, so they are units deep, not hairlines.
for side in (-1,1):
    x=side*33
    # Rail crowns: frame bands, plating panels, strakes and access hatches.
    for i,z in enumerate((-36,-26,-16,-6,4,14,24,34,44)):
        deck_seam(RAIL_CROWN,'05 Rail crown frame band',z,span=2.4,
                  role=('dark','trim')[i%2],lift=.6,x_offset=x)
    for z0,z1,role in ((-38,-18,'trim'),(-16,4,'base'),(6,26,'trim'),(28,46,'base')):
        deck_panel(RAIL_CROWN,'06 Rail crown plating',z0,z1,0,.78,role=role,lift=1.4,inset=.7,x_offset=x)
    deck_strake(RAIL_CROWN,'07 Rail crown strake',(-.5,.5),-36,44,steps=8,lift=.6,inset=.7,x_offset=x)
    for z0,z1 in ((-30,-20),(14,24)):
        deck_panel(RAIL_CROWN,'08 Rail crown access hatch',z0,z1,0,.34,role='dark',lift=1.2,inset=.8,x_offset=x)
    # Rail flanks: armour plating, dark inter-plate trenches, machinery banks and
    # vent louvres, plus a row of service pads so the long outer face repeats.
    flank_detail(RAIL,'09 Rail armour belt',side,(
        (-38,5.6,12.,'base',1.8,.85),(-24,6.6,14.,'trim',2.2,.8),(-8,6.,13.,'base',2.,.85),
        (8,6.4,13.,'trim',2.2,.8),(24,5.6,12.,'base',1.8,.85),(40,4.8,10.,'trim',1.6,.85)),
        x_offset=x)
    flank_detail(RAIL,'10 Rail plate trench',side,(
        (-31,8.,3.6,'dark',3.2,.82),(-16,8.4,3.8,'dark',3.4,.82),(0,8.,3.6,'dark',3.2,.82),
        (16,8.2,3.8,'dark',3.4,.82),(32,7.6,3.6,'dark',3.2,.82)),x_offset=x)
    flank_detail(RAIL,'11 Rail machinery bank',side,(
        (-34,5.8,6.,'base',2.6,.86),(-34,4.4,4.,'trim',3.4,.86),(-20,6.4,6.5,'base',2.8,.82),
        (-20,4.6,4.4,'dark',3.6,.82),(4,6.,6.,'trim',2.7,.84),(4,4.2,4.,'base',3.5,.84),
        (28,6.2,6.5,'base',2.8,.82),(28,4.4,4.4,'dark',3.6,.82)),x_offset=x)
    for z in (-28,2,32):
        louvre_bank(RAIL,'12 Rail vent bank',side,z,rows=4,pitch=2.6,tall=6.8,length=7.5,
                    role='trim',x_offset=x)
    for i,z in enumerate(range(-40,48,11)):
        w,top,bottom,c=surface(RAIL,z)
        panel(f'13 Rail service pad {side} {i}','trim',(2.6,3.4,3.4),(x+side*(w+.9),top-6.4,z))
        panel(f'14 Rail pad foot {side} {i}','dark',(3.4,1.4,5.),(x+side*(w+1.1),top-8.6,z))
    # Outboard housings: machinery banks and radiator fin banks.
    for z in (-23,17):
        flank_detail([(zz+z,w,t,b) for zz,w,t,b in HOUSING],'15 Housing machinery bank',side,(
            (z-3,4.,4.,'trim',2.2,.75),(z,4.8,5.,'dark',3.,.6),(z+3,4.,4.,'base',2.2,.75)),
            x_offset=side*45)
    # Gantry pedestals gain gussets and a machinery collar, so the lifting gear
    # reads as hardware rather than as four bare posts.
    for z in (-17,20):
        panel(f'16 Gantry pedestal collar {side} {z}','trim',(7.2,3.2,8.2),(side*37,9.6,z))
        panel(f'17 Gantry pedestal gusset {side} {z}','dark',(3.2,4.,3.2),(side*34.,11.8,z))
    # Slip-side guide shoes and jaws get contact plating.
    for z in (-23,0,24):
        panel(f'18 Guide shoe contact plate {side} {z}','trim',(11.,1.8,2.2),(side*27,1.6,z-2.8))
        panel(f'19 Guide shoe wear strip {side} {z}','dark',(11.4,.8,1.4),(side*27,2.7,z+2.8))

# Logistics racks: lid ribs, authored on the port side only.
for z in (-33,-19,-5):
    panel(f'20 Logistics rack rib {z}','trim',(9.4,1.,1.2),(-46,9.9,z))

# Crosshead: machinery banks with radiator fins and frame lines.
for z,role in ((-42,'trim'),(-36,'base'),(-30,'dark')):
    deck_panel(CROSSHEAD,'21 Crosshead machinery bank',z-.5,z+.5,0,.86,role=role,lift=2.4,inset=1.4)
for z in (-43,-37,-31,-27):
    deck_seam(CROSSHEAD,'22 Crosshead frame line',z,span=2.4,lift=.6)
for x in (-30,-18,18,30):
    panel(f'23 Crosshead machinery block {x}','dark',(6.4,1.8,5.),(x,11.2,-35))
    panel(f'24 Crosshead fin bank {x}','trim',(1.8,1.,4.2),(x-3.6,10.7,-35))

# Operations tower: window bands at the bridge base with a dark inset under them,
# and machinery ledges, replacing the single hairline glazing strip.
for side in (-1,1):
    for z in (-36,-30,-24):
        w,top,bottom,c=surface(TOWER,z)
        panel(f'25 Operations window band {side} {z}','lit',(.9,2.2,6.),(43+side*(w+.3),top-3.6,z))
        panel(f'26 Operations window inset {side} {z}','dark',(.6,2.8,7.),(43+side*(w+.05),top-5.8,z))
    panel(f'27 Operations machinery ledge {side}','trim',(2.2,3.,15.),(43+side*7.4,20.5,-29))

# Under-keel ties: ribs and a machinery block each, so they read as structure.
for z in (-18,30):
    for x in (-26,-8,8,26):
        panel(f'28 Keel tie rib {x} {z}','dark',(2.2,3.,2.),(x,-14.2,z+3.2))
    panel(f'29 Keel tie machinery {z}','trim',(14.,2.,2.4),(0,-12.9,z-2.8))

# Port storage racks balance mass without mirroring the bridge.
for z in (-37,-23,-9):
    plate('Logistics pallet '+str(z),'dark',(9,7,9),(-46,5,z))
    plate('Logistics ivory lid '+str(z),'base',(9.5,1.2,9.5),(-46,9.1,z))
    plate('Logistics owner label '+str(z),'accent',(6,.5,3),(-46,10,z))
# Four independent floodlights on raised outboard-to-slip brackets. The broad
# upward lens is above ALL local support surfaces; no buried top-face slivers.
features=[]
for side in (-1,1):
    for z in (-9,34):
        x=side*30
        plate('Worklight raised bracket '+str((side,z)),'dark',(3,4,4),(x,12,z))
        plate('Worklight ivory bezel '+str((side,z)),'trim',(5.6,1.3,5.6),(x,14.6,z))
        name='Worklight exposed lens '+str((side,z))
        plate(name,'lit',(4.4,.6,4.4),(x,15.65,z))
        features.append(dict(name=name,center=[x,15.95,z],normal=[0,1,0],broad_face=[4.4,4.4]))
# Aft auxiliary drives / station attitude hardware, tucked outside the open slip.
for x in (-20,20):
    annulus('Auxiliary graphite nozzle '+str(x),'dark',x,-3,[(-46,3.7,2.8),(-41,4,2.6)],12)
    annulus('Auxiliary ivory lip '+str(x),'trim',x,-3,[(-46.5,3.8,2.8),(-45.8,3.8,2.8)],12)
    cylinder('Auxiliary cyan emitter '+str(x),'cool',(x,-3,-44.8),2.5,.4,n=12)
export('alliance_shipyard','Anchorage: open slip, paired gantry rails, offset operations bridge',dict(worklights=features))
