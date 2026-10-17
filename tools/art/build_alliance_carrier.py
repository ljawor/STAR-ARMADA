#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPE ONLY. Editable .blend is authoritative afterwards.

Original Alliance Independence-class fleet carrier: a flight-deck capital, not a scaled
battleship. One broad slab hull carries a flat armoured deck and two outboard flight-deck
wings; the command island is offset to starboard with a radar mast; six hollow drive
throats sit in two outboard banks either side of a deep ventral hangar spine. Its language
is horizontal and decked where the Liberty cruiser is a vertical spear, so the two never
read as the same hull at different sizes.

Authored inside the `rebel:supercapital` legacy envelope
[[-146.51,-30.5,-204.8],[146.51,57.0,190.0]] so `render/ship_sizes.ship_size` derives the
same class scale and drawn length as before, and the union-safe review cameras and the
unchanged collision radius still frame it. No proprietary geometry or textures.
Does not replace any production binding.
Refuses overwriting an existing editable master unless --replace-seed is explicit.
"""
import sys
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MASTER=ROOT/'art/blender/alliance_carrier.blend'
if MASTER.exists() and '--replace-seed' not in sys.argv:
    raise RuntimeError('Editable blend is master. Use export_alliance_carrier.py; --replace-seed destroys edits.')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from alliance_common import loft,plate,annulus,cylinder,weld_scene,bpy
from hull_detail import surface,deck_panel,deck_strake,flank_detail,louvre_bank,panel

# Broad slab hull: the flight deck is the ship, so the beam stays wide to the stern.
HULL=((-190,58,20,-22),(-158,78,24,-26),(-100,92,28,-28),(-20,96,30,-29),
      (60,88,28,-27),(130,70,24,-22),(180,36,14,-12))
# Flat armoured flight deck laid over the sheer, widest amidships.
DECK=((-160,66,26,20),(-92,76,29,24),(0,80,31,26),(80,72,28,24),(152,54,22,18))
# Ventral hangar spine: the ship's lowest point and its main ventral volume.
SPINE=((-150,10,-22,-30.5),(-60,12,-20,-30.5),(40,10,-18,-29.0))
# Command island, offset to starboard so the deck runs clear to port, and its radar mast.
ISLAND=((-42,16,38,26),(-20,20,46,26),(4,18,50,26),(28,13,42,26))
VISOR=[(-43,14,42,38),(-20,18,52,46),(6,16,54,48),(27,11,44,40)]
ROOF=[(-44,14.5,43,39),(-20,18.5,53,47),(6,16.5,55,49),(28,11.5,45,41)]
MAST=[(-2,3.2,52,47),(2,2.8,55,49),(6,2.2,57,51)]

loft('01 Fleet carrier pressure hull','base',HULL,.5)
loft('02 Broad flight deck','trim',DECK,.4)
loft('03 Ventral hangar spine','base',SPINE,.2)
loft('04 Command island','base',ISLAND,.35)
loft('05 Island bridge visor','dark',VISOR,.2)
loft('06 Island roof armor','trim',ROOF,0)
loft('07 Radar mast','trim',MAST,.1)
plate('08 Mast sensor array','lit',(5.0,1.4,4.0),(4,56.0,2))
plate('09 Mast IFF blade','dark',(1.0,6.0,9.0),(4,50.0,-4))
# Deck lighting and machinery that read from the tactical camera looking down.
for z in (-120,-88,-56,-24,8,40,72,104,136):
    deck_panel(DECK,'10 Deck machinery recess',z-14,z+14,.0,.5,'dark',1.3)
    for side in (-1,1):
        deck_panel(DECK,'11 Deck aircraft lift',z-9,z+9,side*.62,.2,'base',2.0)
        panel(f'12 Deck crossbrace {side} {z}','trim',(7.0,.8,2.6),(side*22,33.0,z))
for i in range(9):
    z=-134+i*34
    for side in (-1,1):
        panel(f'13 Deck edge mark {side} {i}','lit',(3.0,.6,9.0),(side*66,32.6,z))
for z in (-100,-30,40,110):
    w,top,_,_=surface(DECK,z)
    panel(f'14 Flight deck recognition stripe {z}','accent',(9.0,.5,26.0),(0,top+1.4,z))
# Bow: armoured prow and forward launch bay; the prow armour sets the z=190.0 extreme.
loft('15 Forward launch armour','trim',[(150,46,22,12),(168,34,18,6),(180,22,14,0)],.2)
loft('16 Prow ram','trim',[(176,14,10,-4),(184,10,7,-5),(190.0,6,5,-5)],0)
for side in (-1,1):
    plate(f'17 Prow launch rail {side}','dark',(2.4,2.0,34.0),(side*10,6.0,168))
plate('18 Forward catapult track','dark',(16.0,1.2,28.0),(0,27.0,168))
plate('19 Forward deck light cluster','lit',(10.0,.7,2.0),(0,30.5,152))
# Outboard flight-deck wings: the beam extreme is the wing outer face at x=+/-146.51.
WING=((-140,20.51,16,6),(-64,20.51,18,7),(36,20.51,18,7),(118,20.51,15,5))
for side in (-1,1):
    x=side*126.0
    loft(f'20 Outboard flight-deck wing {side}','base',WING,.3,(x,0,0))
    loft(f'21 Wing deck armour {side}','trim',[(-134,17,20,16),(-60,18,22,18),
                                               (34,18,22,18),(112,15,19,15)],.15,(x,0,0))
    for i,z in enumerate((-120,-86,-52,-18,16,50,84)):
        panel(f'22 Wing deck light {side} {i}','lit',(1.6,.6,11.0),(x+side*14.0,20.4,z))
        panel(f'23 Wing underside frame {side} {i}','dark',(2.0,1.4,12.0),(x,4.6,z))
    loft(f'24 Wing support pylon {side}','base',[(-96,30,7,-2),(-30,32,8,-2),(40,30,7,-2)],.2,(side*92,0,0))
    plate(f'25 Wing root fairing {side}','dark',(2.2,10.0,60.0),(side*88,10,0))
    for i,z in enumerate((-118,-76,-34,8,50)):
        panel(f'26 Hangar bay recess {side} {i}','dark',(5.0,12.0,30.0),(side*94,-20,z))
        panel(f'27 Hangar bay interior light {side} {i}','lit',(2.4,1.2,24.0),(side*92.5,-14.0,z))
        panel(f'28 Hangar bay door frame {side} {i}','trim',(3.0,1.2,32.0),(side*95,-26.0,z))
    flank_detail(HULL,'29 Layered flank armor',side,tuple((z,10.0,26.0,('trim' if i%2 else 'base'),3.0,.66)
                 for i,z in enumerate((-176,-140,-104,-68,-32,4,40,76,112,148))),x_limit=120.)
    for z in (-150,-118,-86,-54,-22,10,42,74,106):
        louvre_bank(HULL,'30 Flank vent bank',side,z,rows=4,pitch=2.4,tall=7.0,length=13.0,role='trim')
    flank_detail(SPINE,'31 Keel reinforcement',side,tuple((z,5.0,20.0,'trim',1.6,.45)
                 for z in (-120,-80,-40,0,40)))
# Two outboard drive banks either side of the ventral spine; hollow throats are the
# whole drive silhouette, so no solid casing sits behind the emitter discs.
for side in (-1,1):
    x=side*46.0
    loft(f'32 Drive bank casing {side}','base',[(-196,24,15,-16),(-186,30,18,-19),(-176,32,19,-20)],.3,(x,0,0))
    loft(f'33 Drive bank armour {side}','trim',[(-194,20,19,-18),(-184,26,22,-22),(-174,27,23,-23)],.15,(x,0,0))
    plate(f'34 Drive bank recognition band {side}','accent',(34.0,.8,4.0),(x,23.5,-180))
    for j,dx in enumerate((-16.0,0.0,16.0)):
        cx=x+dx
        annulus(f'35 Graphite engine throat {side} {j}','dark',cx,0,
                [(-204.4,7.4,5.8),(-199.0,7.8,6.0),(-194.0,7.0,5.4)],12)
        annulus(f'36 Polished aperture lip {side} {j}','trim',cx,0,
                [(-204.8,8.0,5.9),(-202.4,8.1,6.0)],12)
        cylinder(f'37 Recessed cyan emitter {side} {j}','cool',(cx,0,-199.0),5.4,.4,n=12)
        plate(f'38 Drive machinery gutter {side} {j}','dark',(9.0,1.2,40.0),(cx,22.5,-172))
# Dorsal and ventral machinery runs, plus the ship's service windows and accents.
for z in (-168,-136,-104,-72,-40,-8,24,56,88,120):
    w,_,bottom,_=surface(HULL,z)
    panel(f'39 Hull machinery cassette {z}','base',(26.0,2.4,20.0),(0,bottom+4.0,z))
for z in (-150,-110,-70,-30,10,50,90,130):
    plate(f'40 Ventral service window {z}','lit',(20.0,1.0,3.0),(0,-24.0,z))
    panel(f'41 Ventral crossbrace {z}','trim',(34.0,1.6,3.0),(0,-29.7,z))
for i,z in enumerate((-92,-28,36,100)):
    panel(f'42 Island window band {i}','lit',(1.2,2.2,22.0),(28.0,46.0,z))
for side in (-1,1):
    panel(f'43 Island glazing {side}','lit',(1.2,3.0,34.0),(40.0+side*9.0,40.0,-8))
for i,z in enumerate((-176,-132,-88,-44,0,44,88,132)):
    panel(f'44 Dorsal armour strake {i}','trim',(30.0,2.0,26.0),(0,31.0,z))
deck_strake(DECK,'45 Deck strake',(-1,1),-150,150,steps=11,role='dark',lift=.3,inset=2.0)
for z in (-70,10,90):
    w,top,_,_=surface(DECK,z)
    panel(f'46 Deck recognition flash {z}','accent',(5.0,.5,22.0),(0,top+2.4,z))

# Nothing floats: the hull panels are placed by formula, so their contact with the
# lofted hull is not implied. The pass grows a thin panel onto the surface it was
# meant to sit on, or braces a bulky part, and keeps the envelope.
weld_scene()
features=dict(authority='blend',approval='pending_owner_approval',binding='rebel:supercapital',
              data_id='rebel_supercapital',original_design=True,
              design='Independence-class Fleet Carrier: flight-deck capital with outboard deck wings, offset island and twin outboard drive banks',
              emitter_centers=[[s*46.0+d,0,-199.0] for s in (-1,1) for d in (-16.0,0.0,16.0)],
              seed_recipe='tools/art/build_alliance_carrier.py; initial authoring only, never rebuild hand edits',
              legacy_envelope=[[-146.51,-30.5,-204.8],[146.51,57.0,190.0]],
              provenance='Original geometry authored in Blender; no external mesh or texture dependencies')
bpy.context.scene['asset']='alliance_carrier'
bpy.context.scene['features_json']=json.dumps(features,sort_keys=True)
bpy.context.scene['authority']='blend'
bpy.context.scene['coordinates']='X beam; Y up; +Z forward'
bpy.context.preferences.filepaths.save_version=0
MASTER.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER),compress=True)
# Source has been seeded. The normal export path is a separate process/script.
