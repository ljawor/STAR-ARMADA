#!/usr/bin/env python3
"""Original Alliance Anchorage open construction cradle; editable industrial hardware."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import *

# Two full-length structural rails; nothing fills the central construction slip.
# The rear service crosshead and two LOW under-keel ties leave an open +Z mouth.
for side in (-1,1):
    x=side*33
    loft('01 Long cradle pressure rail '+str(side),'base',[(-43,5,5,-10),
        (-33,8,7,-12),(25,8,7,-12),(47,6,4,-8),(51,2,1,-5)],.45,(x,0,0))
    loft('02 Ivory rail crown '+str(side),'trim',[(-39,4,8,6),(-29,5,9,7),
        (28,5,9,7),(46,3,6,4)],.22,(x,0,0))
    loft('Rail owner recognition band '+str(side),'accent',[(-36,1.8,9,8.2),
        (-26,2,10,9.2),(24,2,10,9.2),(42,1.3,7.5,6.8)],.05,(x+side*2,0,0))
    plate('Recessed rail machinery '+str(side),'dark',(3,1.4,53),(x-side*3,9.4,1))
    for z in range(-23,27,5):
        plate('Rail coolant rib '+str((side,z)),'base',(3.4,.8,1.4),(x-side*3,10.4,z))
    # Outboard service modules hang below the rails, never bridge the launch gap.
    for z in (-23,17):
        loft('Outboard machine housing '+str((side,z)),'base',[(-9,4,4,-5),
            (-6,7,6,-7),(6,7,6,-7),(9,4,4,-5)],.35,(side*45,-5,z))
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
loft('03 Rear service crosshead','base',[(-44,28,4,-8),(-39,36,9,-10),
    (-30,31,7,-9),(-26,25,3,-6)],.55)
plate('Crosshead recessed machinery','dark',(39,1.2,5),(0,9.8,-35))
for x in range(-16,17,4):plate('Crosshead radiator '+str(x),'trim',(1.5,.8,4),(x,10.8,-35))
for z in (-18,30):
    plate('Under keel transverse tie '+str(z),'base',(68,4,6),(0,-15,z))
    plate('Tie center registration '+str(z),'accent',(10,.5,4),(0,-12.7,z))
# Offset starboard administration/habitat assembly with exposed warm glazing.
loft('04 Offset starboard operations tower','base',[(-41,6,17,-5),(-34,8,28,-5),
    (-23,7,32,1),(-18,4,20,5)],.45,(43,0,0))
loft('Operations dark visor','dark',[(-35,6,31,24),(-27,7,34,26),(-20,4,28,21)],.28,(43,0,0))
loft('Operations roof armor','trim',[(-36,6.4,32,30),(-27,7.5,35.3,33.3),(-19,4.3,29.3,27.3)],.2,(43,0,0))
for side in (-1,1):
    plate('Operations exterior warm glazing '+str(side),'lit',(.7,1.8,7),(43+side*7.1,31.8,-27))
    for z in (-29,-25):plate('Operations glazing mullion '+str((side,z)),'dark',(1,2.1,.5),(43+side*7.25,31.8,z))
plate('Forward operations glazing','lit',(5.8,1.4,.6),(43,27.6,-19.8))
plate('Offset communications pedestal','base',(2.5,5,2.5),(46,36,-30))
cylinder('Communications dish','trim',(46,39,-30),3.2,.8,'Y',12)
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
