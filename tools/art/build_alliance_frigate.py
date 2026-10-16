#!/usr/bin/env python3
"""Original Alliance Tern escort. Blender --background --python-exit-code 1 --python <this>."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import *
from hull_detail import *

# A continuous long prow and slender load-bearing waist. Wide negative-space
# drive slots distinguish this compact escort from the capital's deep citadel.
# Frames are named because the surface-detail pass below reads the same numbers,
# so a panel line cannot drift off the hull it belongs to.
HULL=((-64,8,5,-6),(-48,12,7,-7),(-24,9,6,-7),(-4,6,4,-5),
      (17,10,6,-6),(39,16,8,-7),(57,13,9,-4),(73,1.6,7,-1))
CROWN=((12,7,6.6,4.6),(37,12,9.2,7),(55,8,10.3,8),(72,1,8.3,6))
KEEL=((-46,5,-4,-10),(-12,4,-4,-10),(25,6,-4,-9),(59,3,-2,-6))
ISLAND=((-49,8,12,5),(-39,9,17,6),(-27,7,15,5),(-19,4,9,4))
CASING=((-65,6,6,-6),(-52,8,8,-7),(-27,7,7,-6),(-12,3,4,-3))
loft('01 Continuous sheer hull','base',HULL,.55)
loft('02 Swept bow crown','trim',CROWN,.35)
loft('03 Needle keel','base',KEEL,.3)
loft('04 Waist machinery saddle','dark',[(-25,6,7,4),(-5,4,6,3),(14,7,7,4)],.15)
for z in (-20,-15,-10,-5,0,5,10):
    plate('Recessed spine radiator '+str(z),'trim',(7,.7,1.3),(0,7.2,z))
# Staggered drives and broad but delicate saddles; the intervening space is empty.
for side,shift in ((-1,-7),(1,3)):
    x=side*26
    loft('Drive pressure casing '+str(side),'base',
         [(z+shift,w,t,b) for z,w,t,b in CASING],.5,(x,0,0))
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
loft('05 Navigation island','base',ISLAND,.45)
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

# ---------------------------------------------------------------------------
# 09 Surface detail. The hull is sculpted but between its features it is one
# continuous grey plate, and at the shipped close camera that is all the player
# sees. Everything below is surface detail: placed from the frame it sits on,
# standing 0.4 to 4 units proud, adding no silhouette and touching no feature.
# Elements are sized against the shipped camera (155 units), where one world
# unit is about 1.5 screen pixels: a plate has to be units deep to be a plate
# rather than a hairline, so the deck carries bold bands rather than fine lines.

# Deck: alternating transverse bands that read as frames, with longitudinal
# strakes, then the bow crown's armour bands. The deck is the surface seen most
# at this camera's pitch, so it takes the boldest steps.
for i,z in enumerate((-58,-48,-38,-28,-18,-8,2,12,22,32,42,52,62)):
    deck_seam(HULL,'09 Aft deck frame band',z,span=2.,role=('dark','trim')[i%2],lift=.5)
deck_strake(HULL,'10 Aft deck strake',(-.5,.5),-60,10,steps=6,role='trim',lift=.5,inset=1.)
deck_strake(CROWN,'11 Bow crown strake',(-.5,.5),16,68,steps=7,role='base',lift=.6,inset=1.)
for z0,z1,role in ((16,30,'trim'),(30,44,'base'),(44,56,'dark'),(56,68,'trim')):
    deck_panel(CROWN,'12 Bow crown armour band',z0,z1,0,.8,role=role,lift=2.,inset=1.)
for z0,z1 in ((20,30),(38,48)):
    deck_panel(HULL,'13 Aft deck machinery well',z0,z1,0,.4,role='dark',lift=.8,inset=1.1)

# Flank: an armour belt with dark inter-plate trenches, a second lower belt row
# for a second tonal step, machinery banks and vent louvres. The drive casings
# at x = +/-34 are the widest thing on this ship, so their detail is clipped to
# that beam: the owner approved the form, and a bounding box is a scale, not a
# surface.
for side in (-1,1):
    for i in range(14):
        z=-58+i*9.5
        w,top,_,c=surface(HULL,z)
        panel(f'14 Deck edge rail post {side} {i}','trim',(1.1,1.6,1.6),(side*(w-c-.7),top+.8,z))
        if i%2==0:
            panel(f'15 Deck edge rail base {side} {i}','dark',(1.6,1.,3.),(side*(w-c-1.1),top+.5,z))
    flank_detail(HULL,'16 Flank armour belt',side,(
        (-58,4.6,10.,'base',1.6,.9),(-44,5.6,11.,'trim',2.2,.84),(-28,5.,10.,'base',1.8,.88),
        (-12,6.,11.,'trim',2.4,.82),(4,4.4,9.,'base',1.6,.88),(20,5.4,10.,'trim',2.2,.84),
        (36,4.6,9.,'base',1.6,.86),(52,3.8,8.,'trim',1.4,.88)))
    flank_detail(HULL,'17 Belt plate trench',side,(
        (-51,7.2,3.2,'dark',3.,.86),(-36,7.6,3.4,'dark',3.2,.85),(-20,7.2,3.2,'dark',3.,.86),
        (-4,7.6,3.4,'dark',3.2,.85),(12,6.8,3.2,'dark',3.,.86),(28,7.2,3.2,'dark',3.,.85),
        (44,6.2,3.2,'dark',2.8,.86)))
    flank_detail(HULL,'18 Lower flank belt',side,(
        (-56,3.2,7.,'trim',1.6,.46),(-38,3.8,8.,'base',1.8,.42),(-20,3.4,7.,'dark',1.7,.46),
        (-2,3.8,8.,'trim',1.8,.42),(16,3.6,7.,'base',1.7,.44)))
    flank_detail(HULL,'19 Hull machinery bank',side,(
        (-54,4.6,6.,'base',2.2,.9),(-54,3.2,4.,'trim',3.,.9),(-30,5.2,6.5,'base',2.4,.86),
        (-30,3.4,4.4,'dark',3.,.86),(-6,4.4,5.5,'trim',2.2,.88),(-6,3.,3.6,'base',3.,.88),
        (30,5.,6.,'base',2.4,.87),(30,3.2,4.,'dark',3.,.87),(46,3.6,4.6,'trim',2.,.62)))
    flank_detail(KEEL,'20 Keel frame rib',side,(
        (-40,2.4,3.2,'base',.9,.5),(-22,3.,3.6,'dark',1.,.5),(-4,2.6,3.4,'trim',.9,.5),
        (16,3.,3.6,'base',1.,.5),(34,2.6,3.4,'dark',.9,.5),(50,2.2,3.,'trim',.85,.5)))
    for z in (-46,-16,26):
        louvre_bank(HULL,'21 Hull vent bank',side,z,rows=4,pitch=1.8,tall=4.4,length=5.5,role='trim')
    louvre_bank(CROWN,'22 Bow vent bank',side,44,rows=3,pitch=1.6,tall=3.4,length=4.6,role='base')
    flank_detail([(z+shift,w,t,b) for z,w,t,b in CASING],'23 Drive casing machinery',side,(
        (-56+(-7 if side<0 else 3),3.4,5.,'trim',1.5,.7),
        (-44+(-7 if side<0 else 3),4.2,6.,'dark',1.9,.55),
        (-33+(-7 if side<0 else 3),3.4,5.,'base',1.5,.7)),x_offset=side*26,x_limit=34.)

# Island window band at the bridge base, with a dark inset under it, and prow markings.
for side in (-1,1):
    for z in (-44,-34,-26):
        w,top,bottom,c=surface(ISLAND,z)
        panel(f'24 Island window band {side} {z}','lit',(.8,2.,5.),(side*(w+.3),top-2.2,z))
        panel(f'25 Island window inset {side} {z}','dark',(.6,2.6,6.),(side*(w+.05),top-4.2,z))
for left in (-.5,.5):
    deck_panel(CROWN,'26 Prow chevron marking',50,66,left,.3,role='accent',lift=2.,inset=.8)

export('alliance_frigate','Tern: continuous needle prow, open waist, staggered twin drives')
