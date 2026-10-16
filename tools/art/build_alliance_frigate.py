#!/usr/bin/env python3
"""Original Alliance Tern escort. Blender --background --python-exit-code 1 --python <this>."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import *

# A continuous long prow and slender load-bearing waist. Wide negative-space
# drive slots distinguish this compact escort from the capital's deep citadel.
loft('01 Continuous sheer hull','base',[
    (-64,8,5,-6),(-48,12,7,-7),(-24,9,6,-7),(-4,6,4,-5),
    (17,10,6,-6),(39,16,8,-7),(57,13,9,-4),(73,1.6,7,-1)],.55)
loft('02 Swept bow crown','trim',[(12,7,6.6,4.6),(37,12,9.2,7),
    (55,8,10.3,8),(72,1,8.3,6)],.35)
loft('03 Needle keel','base',[(-46,5,-4,-10),(-12,4,-4,-10),
    (25,6,-4,-9),(59,3,-2,-6)],.3)
loft('04 Waist machinery saddle','dark',[(-25,6,7,4),(-5,4,6,3),(14,7,7,4)],.15)
for z in (-20,-15,-10,-5,0,5,10):
    plate('Recessed spine radiator '+str(z),'trim',(7,.7,1.3),(0,7.2,z))
# Staggered drives and broad but delicate saddles; the intervening space is empty.
for side,shift in ((-1,-7),(1,3)):
    x=side*26
    loft('Drive pressure casing '+str(side),'base',[(-65+shift,6,6,-6),
        (-52+shift,8,8,-7),(-27+shift,7,7,-6),(-12+shift,3,4,-3)],.5,(x,0,0))
    for z in (-49+shift,-15+shift):
        loft('Swept saddle '+str((side,z)),'base',[(-3,10,1,-3),(3,10,2,-2)],.25,(side*16,-1,z))
    loft('Drive dorsal cowling '+str(side),'trim',[(-61+shift,4.5,7,5),
        (-49+shift,6,9.4,7.4),(-28+shift,5,8.5,6.5),(-15+shift,1.5,5.4,3.4)],.25,(x,0,0))
    loft('Drive recognition stripe '+str(side),'accent',[(-60+shift,1.8,7.7,7),
        (-49+shift,2.1,10,9.4),(-30+shift,1.7,9.2,8.5)],.08,(x+side*3,0,0))
    annulus('Drive graphite throat '+str(side),'dark',x,0,[(-73+shift,5.8,4.6),(-68+shift,6.2,4.5),(-62+shift,5,3.5)],12)
    annulus('Drive polished lip '+str(side),'trim',x,0,[(-73.7+shift,5.9,4.6),(-72.3+shift,6.2,4.6)],12)
    cylinder('Recessed cyan ion emitter '+str(side),'cool',(x,0,-66.5+shift),3.45,.3,n=12)
    plate('Drive machinery inset '+str(side),'dark',(3,1,21),(x-side*3,8.6,-43+shift))
    for z in (-50,-45,-40,-35):
        plate('Heat exchanger '+str((side,z)),'base',(3.2,.5,1.1),(x-side*3,9.3,z+shift))
    # Integrated forward cheeks, not a miniature battleship's batteries.
    loft('Prow flank chine '+str(side),'base',[(24,2,2,-5),(41,2.6,5,-5),(59,1,6,-2)],.2,(side*12,0,0))
    for z in (31,44,55):
        plate('Flush flank seam '+str((side,z)),'dark',(.5,2,.7),(side*(14 if z<50 else 10),3,z))
# Set-back bridge with warm exterior glazing above its dark sloped housing.
loft('05 Navigation island','base',[(-49,8,12,5),(-39,9,17,6),(-27,7,15,5),(-19,4,9,4)],.45)
loft('06 Bridge black visor','dark',[(-41,6,20,14),(-33,7,22,15),(-26,5,18,12)],.3)
loft('07 Bridge roof armor','trim',[(-42,6.2,21,19),(-33,7.3,23.1,21),(-25,5,19.2,17.2)],.2)
for side in (-1,1):
    plate('Bridge exterior warm glazing '+str(side),'lit',(.6,1.7,8),(side*7.1,20,-33))
    for z in (-35,-31):plate('Bridge mullion '+str((side,z)),'dark',(.8,2,.45),(side*7.25,20,z))
plate('Forward bridge slit','lit',(6,1.2,.5),(0,17.4,-25.4))
loft('Offset swept sensor blade','base',[(-41,.7,21,17),(-38,.6,25.2,19),(-35,.4,23,18)],.1,(-3,0,0))
plate('Sensor ivory cap','trim',(1.3,.7,2),(-3,25,-38))
# One characteristic twin gunhouse and two light point-defense mounts.
cylinder('Forward battery barbette','dark',(0,10,36),4,1.5,axis='Y')
loft('Forward battery raked gunhouse','base',[(-4,3.7,3,0),(2,4.2,3.4,0),(5,2.5,2,0)],.25,(0,10.5,36))
plate('Battery owner pennant','accent',(5,.5,3),(0,14.2,35))
for x in (-1.6,1.6):
    cylinder('Twin escort barrel '+str(x),'trim',(x,12.5,44),.55,10,n=8)
    annulus('Twin escort muzzle '+str(x),'dark',x,12.5,[(49.5,.75,.35),(48.8,.75,.35)],8)
for side in (-1,1):
    cylinder('Defense mount '+str(side),'dark',(side*26,9,-50),2.3,1.2,'Y',8)
    plate('Defense cupola '+str(side),'base',(4,2.5,5),(side*26,10.6,-50))
    cylinder('Defense barrel '+str(side),'trim',(side*26,11,-46),.35,5,n=8)
loft('08 Long bow recognition paint','accent',[(16,1.8,7.2,6.5),(37,2.5,9.9,9.2),
    (55,1.6,11,10.3),(66,.7,9.7,9)],.06,(-4,0,0))
# Asymmetric starboard service umbilical and visible status strips.
plate('Service trunk','dark',(2,2,15),(10,7,-38))
for z in (-43,-38,-33):plate('Service collar '+str(z),'trim',(2.6,2.5,.7),(10,7,z))
plate('Service status lens','lit',(1.3,.5,2),(10,8.5,-30))
export('alliance_frigate','Tern: continuous needle prow, open waist, staggered twin drives')
