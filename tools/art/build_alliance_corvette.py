#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPE ONLY. Editable .blend is authoritative afterwards.

Original Alliance Blockade Runner: a slender blockade-running courier built around one
continuous spine. Distinct language from the Liberty cruiser on purpose - no outrigger
spear and no broadside sponsons: a knife-edge pressure hull, a forward bridge bastion
carrying a tall comms mast, a deep ventral keel fin, and two outboard drive nacelles on
short pylons whose hollow throats are the ship's whole drive silhouette.

Authored inside the `rebel:corvette` legacy envelope [[-21.9,-6.0,-46.46],[21.9,15.3,45.0]]
so `render/ship_sizes.ship_size` derives the same class scale and drawn length as before;
the union-safe review cameras and the unchanged collision radius therefore still frame it.
No proprietary geometry or textures. Does not replace any production binding.
Refuses overwriting an existing editable master unless --replace-seed is explicit.
"""
import sys
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MASTER=ROOT/'art/blender/alliance_corvette.blend'
if MASTER.exists() and '--replace-seed' not in sys.argv:
    raise RuntimeError('Editable blend is master. Use export_alliance_corvette.py; --replace-seed destroys edits.')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import loft,plate,annulus,cylinder,bpy
from hull_detail import surface,deck_panel,deck_strake,flank_detail,louvre_bank,panel

# Pressure hull: knife-edge bow, flat sheer, deepest section just aft of amidships.
HULL=((-44,5.0,3.4,-3.6),(-36,7.4,4.4,-4.4),(-18,8.6,5.0,-4.8),
      (2,8.2,5.2,-4.6),(20,7.0,4.6,-3.8),(32,5.4,3.6,-3.0),(42,2.2,2.6,-2.4))
# Dorsal spine ridge: the raised armour run that makes the courier read as one beam.
CROWN=((-22,2.8,6.4,3.8),(-4,3.2,7.0,4.6),(14,2.6,6.2,4.0),(30,1.6,4.6,3.0))
# Deep ventral keel fin: the ship's lowest point, and its silhouette against the water.
KEEL=((-32,2.4,-3.0,-6.0),(-16,2.8,-3.4,-6.0),(2,2.2,-3.2,-5.2))
# Forward bridge bastion, one deck above the sheer, with the mast rising from its roof.
ISLAND=((-40,3.6,6.2,1.0),(-33,4.8,8.4,1.0),(-26,3.8,7.0,1.0))
VISOR=[(-42,3.0,7.4,6.6),(-33,4.2,9.6,8.6),(-26,3.2,8.2,7.4)]
ROOF=[(-43,3.1,7.6,7.2),(-33,4.3,10.6,9.8),(-26,3.3,8.4,7.9)]
MAST=[(-32,1.6,10.4,9.0),(-30,1.3,13.0,10.0),(-28.5,.9,15.3,11.0)]
# Outboard nacelle body. It stops at z=-38: everything aft of that is the open drive
# throat, so no solid casing sits behind the emitter discs.
NACELLE=((-38,2.8,2.4,-2.4),(-32,4.0,3.0,-3.0),(-24,4.0,3.0,-3.0),(-16,3.0,2.2,-2.2))

loft('01 Slender pressure hull','base',HULL,.35)
loft('02 Dorsal spine armor','trim',CROWN,.2)
loft('03 Deep ventral keel fin','base',KEEL,0)
loft('04 Forward bridge bastion','base',ISLAND,.3)
loft('05 Bridge graphite visor','dark',VISOR,.2)
loft('06 Bridge roof armor','trim',ROOF,0)
loft('07 Comms mast','trim',MAST,.12)
plate('08 Mast sensor head','lit',(1.8,.7,1.8),(0,14.95,-30))
# Forefoot ram and its sensor vanes; the ram sets the bow extreme at z=45.0.
loft('09 Prow ram armor','trim',[(40,2.6,2.8,-2.4),(42.5,2.2,2.4,-2.2),(45.0,1.4,1.6,-1.8)],0)
for side in (-1,1):
    plate(f'10 Prow sensor vane {side}','dark',(.5,1.6,4.4),(side*1.9,1.4,40.6))
plate('11 Forward docking collar','dark',(7.0,3.2,3.0),(0,1.2,30))
plate('12 Forward collar window band','lit',(5.2,.6,1.2),(0,2.9,29.4))
# Two separated drive nacelles on short pylons; the nacelle outer face is the beam extreme.
for side in (-1,1):
    x=side*17.9
    loft(f'13 Swept drive nacelle {side}','base',NACELLE,.3,(x,0,0))
    loft(f'14 Drive cowling armor {side}','trim',[(-36,2.2,3.6,2.4),(-30,3.2,4.4,3.0),
                                                  (-22,3.4,4.6,3.2),(-15,2.0,3.2,2.2)],.15,(x,0,0))
    loft(f'15 Nacelle pylon {side}','base',[(-30,4.0,1.4,-1.4),(-22,4.2,1.6,-1.6)],.1,(side*11.5,0,0))
    plate(f'16 Pylon root fairing {side}','dark',(1.2,3.0,7.0),(side*8.4,0,-26))
    # A 64-unit escort is shorter than the camera's 60-unit height floor, so the shipped
    # rear and close cameras look down the drive axis at 50 degrees and a deeply recessed
    # disc is shadowed by its own lip. Recess 0.76 units, aperture 2.55: the disc stays
    # ~90% visible at that elevation instead of a sliver.
    annulus(f'17 Graphite engine throat {side}','dark',x,0,[(-46.3,3.05,2.55),(-44.0,2.8,2.2),(-41.0,2.35,1.85)],10)
    annulus(f'18 Polished aperture lip {side}','trim',x,0,[(-46.46,3.12,2.55),(-45.9,3.15,2.55)],10)
    cylinder(f'19 Recessed cyan emitter {side}','cool',(x,0,-45.55),1.9,.3,n=10)
    plate(f'20 Nacelle recognition stripe {side}','accent',(2.6,.5,19),(x+side*2.2,3.2,-26))
    for i,z in enumerate((-34,-30,-26,-22)):
        panel(f'21 Nacelle machinery cassette {side} {i}','base',(3.0,1.2,3.2),(x,3.2,z))
        panel(f'22 Nacelle heat louvre {side} {i}','trim',(1.4,.4,2.0),(x+side*1.2,4.3,z))
    for z in (-38,-24,-10,4,18):
        louvre_bank(HULL,'23 Flank vent bank',side,z,rows=3,pitch=1.2,tall=2.6,length=6.5,role='trim')
    flank_detail(HULL,'24 Layered flank armor',side,tuple((z,3.4,7.5,('trim' if i%2 else 'base'),2.0,.62)
                 for i,z in enumerate((-40,-31,-22,-13,-4,5,14,23,32))),x_limit=12.)
    flank_detail(KEEL,'25 Keel reinforcement',side,tuple((z,2.0,6.5,'trim',1.0,.45)
                 for z in (-28,-19,-10,-1,8)))
# Open centreline equipment channel between the spine ridge and the vent banks.
for z in (-20,-9,2,13,24,33):
    deck_panel(HULL,'26 Deck machinery recess',z-3.5,z+3.5,0,.55,'dark',1.0)
    for side in (-1,1):
        deck_panel(HULL,'27 Deck equipment bank',z-2.6,z+2.6,side*.58,.16,'base',1.8)
        panel(f'28 Machinery crossbrace {side} {z}','trim',(3.2,.6,1.8),(side*5.2,7.0,z))
deck_strake(HULL,'29 Deck strake',(-1,1),-38,38,steps=9,role='dark',lift=.25,inset=.8)
for z in (-14,2,18,32):
    w,top,_,_=surface(CROWN,z)
    panel(f'30 Spine recognition flash {z}','accent',(2.4,.4,5.0),(0,top+1.15,z))
for z in (-38,-33,-28):
    plate(f'31 Aft service window {z}','lit',(4.4,.7,1.2),(0,5.0,z))
plate('32 Bridge window band','lit',(1.0,1.0,7.0),(0,8.0,-33))
loft('33 Bridge wing armor','trim',[(-39,4.4,7.2,5.6),(-33,5.6,8.8,6.6),(-27,4.6,7.6,6.0)],.1)

features=dict(authority='blend',approval='pending_owner_approval',binding='rebel:corvette',data_id='rebel_corvette',
              original_design=True,design='Blockade Runner: spine-hulled courier with forward bastion mast and twin outboard drive nacelles',
              emitter_centers=[[s*17.9,0,-45.55] for s in (-1,1)],
              seed_recipe='tools/art/build_alliance_corvette.py; initial authoring only, never rebuild hand edits',
              legacy_envelope=[[-21.9,-6.0,-46.46],[21.9,15.3,45.0]],
              provenance='Original geometry authored in Blender; no external mesh or texture dependencies')
bpy.context.scene['asset']='alliance_corvette'
bpy.context.scene['features_json']=json.dumps(features,sort_keys=True)
bpy.context.scene['authority']='blend'
bpy.context.scene['coordinates']='X beam; Y up; +Z forward'
bpy.context.preferences.filepaths.save_version=0
MASTER.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER),compress=True)
# Source has been seeded. The normal export path is a separate process/script.
