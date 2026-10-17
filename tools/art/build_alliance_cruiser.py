#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPE ONLY. Editable .blend is authoritative afterwards.

Original Alliance Liberty: bifurcated outriggers around a tapered armored spear,
low bridge bastion, exposed transverse machinery and four recessed ion throats.
No proprietary geometry or textures. Does not replace any production binding.
Refuses overwriting an existing editable master unless --replace-seed is explicit.
"""
import sys
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MASTER=ROOT/'art/blender/alliance_cruiser.blend'
if MASTER.exists() and '--replace-seed' not in sys.argv:
    raise RuntimeError('Editable blend is master. Use export_alliance_cruiser.py; --replace-seed destroys edits.')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import loft,plate,annulus,cylinder,bpy
from hull_detail import surface,deck_panel,deck_strake,flank_detail,louvre_bank,panel

HULL=((-82,19,6,-6),(-64,24,9,-9),(-35,23,8,-10),(0,19,7,-10),
      (28,25,7,-8),(58,23,9,-6),(82,13,8,-3),(97.5,3,5,-1))
CROWN=((-12,12,9,5),(25,17,11,6),(56,16,12,8),(78,9,11,7),(94,2.4,6,4))
KEEL=((-70,10,-5,-10),(-25,11,-6,-11.265),(30,13,-5,-11.265),(76,5,-2,-8))
ISLAND=((-68,12,9,5),(-57,14,14,5),(-39,12,16,6),(-22,8,13,7))
CASING=((-91,9,7,-7),(-78,11,9,-8),(-55,11,8,-8),(-30,8,6,-7),(-16,3,3,-3))
loft('01 Layered sheer pressure hull','base',HULL,.5)
loft('02 Spearhead crown armor','trim',CROWN,.3)
loft('03 Deep load bearing keel','base',KEEL,0)
loft('04 Low bridge bastion','base',ISLAND,.35)
loft('05 Bridge graphite visor','dark',[(-59,10,16,12),(-45,11,18,13),(-28,7,16,11)],.2)
loft('06 Bridge roof armor','trim',[(-60,10,17,15),(-45,11,19.3,17),(-28,7,17,15)],0)
# Four separated drive outlets on two long nacelles. Emitters sit AFT of the
# pressure casing cap; hollow lips do not hide a solid cylinder behind the discs.
for side in (-1,1):
    x=side*48
    loft(f'07 Swept drive nacelle {side}','base',CASING,.4,(x,0,0))
    loft(f'08 Drive cowling armor {side}','trim',[(-88,6,8,6),(-72,8,10,8),(-48,7,9,7),(-24,2,5,3)],.2,(x,0,0))
    for z in (-68,-35):
        loft(f'09 Angled outrigger yoke {side} {z}','base',[(-5,17,2,-4),(4,15,4,-3)],.25,(side*31,-1,z))
        plate(f'10 Yoke recognition paint {side} {z}','accent',(21,.8,3),(side*32,3,z))
    for j,dx in enumerate((-4.7,4.7)):
        cx=x+dx
        annulus(f'11 Graphite engine throat {side} {j}','dark',cx,0,[(-99.2,4.5,3.6),(-95,4.7,3.7),(-91.2,4.2,3.3)],12)
        annulus(f'12 Polished aperture lip {side} {j}','trim',cx,0,[(-99.925,4.55,3.65),(-98.8,4.7,3.65)],12)
        cylinder(f'13 Recessed cyan emitter {side} {j}','cool',(cx,0,-94.5),3.25,.25,n=12)
    # Deep machinery gutter and visible alternating structural cassettes.
    plate(f'14 Drive machinery gutter {side}','dark',(6,1,42),(x,10,-62))
    for i,z in enumerate((-80,-71,-62,-53,-44)):
        plate(f'15 Drive machinery cassette {side} {i}','base',(5,1.6,5.5),(x,10.8,z))
        panel(f'16 Drive heat radiator {side} {i}','trim',(3,.5,2),(x,11.8,z))
    loft(f'17 Long nacelle recognition stripe {side}','accent',[(-84,1.6,9,8),(-72,2,11.1,10),(-49,1.8,10.1,9),(-30,.9,7,6)],0,(x+side*4,0,0))
    # Broad shoulder rather than tiny barrels: cruiser's two armored flank batteries.
    loft(f'18 Broadside battery sponson {side}','base',[(3,6,4,-3),(24,8,6,-4),(49,5,6,-3),(65,1.5,4,0)],.25,(side*28,0,0))
    for z in (14,30,45):
        plate(f'19 Broadside inset {side} {z}','dark',(1.1,3.5,6),(side*35,2,z))
        cylinder(f'20 Battery barrel {side} {z}','trim',(side*34,3,z+4),.7,5,n=8)
    for z in (-53,-44,-35):
        w,top,bottom,c=surface(ISLAND,z)
        panel(f'21 Bridge window band {side} {z}','lit',(.7,1.4,5.5),(side*(w+.2),top-1.6,z))
    for z in (-48,-15,22,51):
        louvre_bank(HULL,'22 Flank vent bank',side,z,rows=3,pitch=1.5,tall=4,length=8,role='trim')
    flank_detail(HULL,'23 Layered flank armor',side,tuple((z,5.5,10,('trim' if i%2 else 'base'),2.2,.62) for i,z in enumerate((-66,-48,-30,-12,6,24,42,60,76))))
    flank_detail(KEEL,'24 Keel reinforcement',side,tuple((z,2.8,8,'trim',1.1,.45) for z in (-55,-32,-9,14,37,60)))
# The open mid-deck equipment channel is deliberate; foredeck armor plates
# alternate side-to-side in broad nonrectangular lofts, not a hatch texture.
for i,(z0,z1) in enumerate(((0,17),(19,36),(38,55),(57,73),(75,87))):
    for side in (-1,1):
        w0,t0,_,_=surface(CROWN,z0); w1,t1,_,_=surface(CROWN,z1)
        loft(f'25 Stepped crown armor {i} {side}',('base' if i%2 else 'trim'),
             [(z0,w0*.37,t0+1.2,t0),(z1,w1*.37,t1+1.2,t1)],0,(side*w0*.44,0,0))
for z in (-66,-54,-42,-30,-18):
    deck_panel(HULL,'26 Deck machinery recess',z-4,z+4,0,.62,'dark',1.2)
    for side in (-1,1):
        deck_panel(HULL,'27 Deck equipment bank',z-3,z+3,side*.6,.18,'base',2)
        panel(f'28 Machinery crossbrace {side} {z}','trim',(4,.7,2),(side*6,10,z))
for z in (8,24,40,56,72):
    w,top,_,c=surface(CROWN,z)
    panel(f'29 Centerline recognition flash {z}','accent',(4,.5,9),(0,top+1.55,z))
for z in (-72,-64,-56):
    plate(f'30 Aft service window {z}','lit',(6,.8,1.4),(0,10,z))
plate('31 Forward bridge window','lit',(9,1,.7),(0,14,-25.5))
# Outer radiator paddles bound the original 132-wide envelope without widening it.
for side in (-1,1):
    loft(f'32 Swept external radiator {side}','dark',[(-76,3,4,-2),(-57,7,4,-2),(-37,2,2,-2)],0,(side*59,0,0))
    for z in (-69,-61,-53,-45):
        plate(f'33 Radiator bright rib {side} {z}','trim',(8,.6,1.8),(side*58,4.4,z))

features=dict(authority='blend',approval='pending_owner_approval',binding='rebel:cruiser',data_id='rebel_cruiser',
              original_design=True,design='Liberty / Kestrel: split outrigger cruiser with armored spear and low bastion',
              emitter_centers=[[s*48+d,0,-94.5] for s in (-1,1) for d in (-4.7,4.7)],
              seed_recipe='tools/art/build_alliance_cruiser.py; initial authoring only, never rebuild hand edits',
              provenance='Original geometry authored in Blender; no external mesh or texture dependencies')
bpy.context.scene['asset']='alliance_cruiser'
bpy.context.scene['features_json']=json.dumps(features,sort_keys=True)
bpy.context.scene['authority']='blend'
bpy.context.scene['coordinates']='X beam; Y up; +Z forward'
bpy.context.preferences.filepaths.save_version=0
MASTER.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER),compress=True)
# Source has been seeded. The normal export path is a separate process/script.
