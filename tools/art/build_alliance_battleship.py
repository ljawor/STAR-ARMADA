#!/usr/bin/env python3
"""Original Alliance 'Pelagic' battleship, editable Blender source → game roles.

Run: /Applications/Blender.app/Contents/MacOS/Blender --background --python tools/art/build_alliance_battleship.py
No downloaded meshes/textures, no simulation or runtime Blender dependency.
Coordinates intentionally match the engine: X beam, Y up, +Z prow.
Bevel modifiers remain editable in the .blend; evaluated triangles are exported.
"""
from pathlib import Path
import json
import math
import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
BLEND = ROOT / 'art/blender/alliance_battleship.blend'
EXPORT = ROOT / 'assets/models/alliance_battleship.mesh.json'
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
COLORS = ((.42,.48,.55,1),(.065,.10,.14,1),(.72,.77,.79,1),
          (.16,.40,.74,1),(.66,.91,1,1),(.13,.70,1,1))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)
MATS = {}
for role, color in zip(ROLES, COLORS):
    mat = bpy.data.materials.new(role)
    mat.diffuse_color = color
    mat['engine_material_role'] = role
    MATS[role] = mat


def mesh_object(name, role, verts, faces, bevel=0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(MATS[role])
    obj['engine_material_role'] = role
    if bevel:
        mod = obj.modifiers.new('Manufactured edge radii', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(24)
    return obj


def loft(name, role, sections, bevel=.6, center=(0,0,0), chamfer=.25):
    # Sculpted transverse frames define coherent sheer, tumblehome and bow flare.
    verts = []
    for z,w,top,bottom in sections:
        c = min(w*chamfer, (top-bottom)*.28)
        ring = [(-w+c,top,z),(w-c,top,z),(w,top-c,z),(w,bottom+c,z),
                (w-c,bottom,z),(-w+c,bottom,z),(-w,bottom+c,z),(-w,top-c,z)]
        verts.extend(tuple(a+b for a,b in zip(p,center)) for p in ring)
    faces = [tuple(reversed(range(8))), tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(sections)-1):
        for i in range(8):
            j=(i+1)%8
            faces.append((k*8+i,k*8+j,(k+1)*8+j,(k+1)*8+i))
    return mesh_object(name,role,verts,faces,bevel)


def plate(name,role,size,center,bevel=.35):
    w,h,l=size
    # Small details already have chamfered frames; reserve evaluated bevels
    # for the large continuous armor surfaces instead of tessellating every seam.
    return loft(name,role,[(-l/2,w/2,h/2,-h/2),(l/2,w/2,h/2,-h/2)],0,center)


def annulus(name,role,x,y,frames,n=16):
    # Frames are (z,outer,inner); no solid cap across the aperture.
    verts=[]
    for z,outer,inner in frames:
        for r in (outer,inner):
            verts.extend((x+r*math.cos(i*2*math.pi/n),y+r*math.sin(i*2*math.pi/n),z) for i in range(n))
    faces=[]
    for k in range(len(frames)-1):
        for j in range(n):
            q=(j+1)%n
            for offset in (0,n):
                a=k*n*2+offset;b=(k+1)*n*2+offset
                faces.append((a+j,a+q,b+q,b+j))
    for k in (0,len(frames)-1):
        a=k*n*2
        for j in range(n):
            q=(j+1)%n
            faces.append((a+j,a+q,a+n+q,a+n+j))
    return mesh_object(name,role,verts,faces,0)


def cylinder(name,role,center,radius,depth,axis='Z',n=12):
    x,y,z=center
    verts=[]
    for end in (-depth/2,depth/2):
        for i in range(n):
            a=2*math.pi*i/n
            p=(radius*math.cos(a),radius*math.sin(a),end)
            if axis=='Y':p=(p[0],p[2],p[1])
            verts.append((p[0]+x,p[1]+y,p[2]+z))
    faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return mesh_object(name,role,verts,faces,0)


def surface(sections,z):
    """Half width, deck height, keel height and chamfer of a loft frame at z.

    The detail pass reads the same frames the hull is lofted from, so a new
    panel cannot float off the deck or sink into the flank when a frame moves.
    """
    if z<=sections[0][0]:k,t=0,0.
    elif z>=sections[-1][0]:k,t=len(sections)-2,1.
    else:
        k=next(i for i in range(len(sections)-1) if sections[i][0]<=z<sections[i+1][0])
        t=(z-sections[k][0])/(sections[k+1][0]-sections[k][0])
    z0,w0,t0,b0=sections[k];z1,w1,t1,b1=sections[k+1]
    at=lambda a,b:a+(b-a)*t
    w,top,bottom=at(w0,w1),at(t0,t1),at(b0,b1)
    return w,top,bottom,min(w*.25,(top-bottom)*.28)


def panel(name,role,size,center):
    """A plain raised block: 8 shared vertices, 12 triangles, no evaluated bevel.

    Surface detail is numerous and small, so it must be cheaper per element than
    the chamfered structural plates above, which carry the silhouette. The hard
    edge of the block is the tonal step the renderer can actually show.
    """
    w,h,l=size;x,y,z=center
    verts=[(x-w/2,y-h/2,z-l/2),(x+w/2,y-h/2,z-l/2),(x+w/2,y+h/2,z-l/2),(x-w/2,y+h/2,z-l/2),
           (x-w/2,y-h/2,z+l/2),(x+w/2,y-h/2,z+l/2),(x+w/2,y+h/2,z+l/2),(x-w/2,y+h/2,z+l/2)]
    faces=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    return mesh_object(name,role,verts,faces,0)


def deck_seam(sections,name,z,span=1.2,role='dark',lift=.3,inset=1.0):
    # A transverse panel line across the flat centre of a lofted deck.
    w,top,_,c=surface(sections,z)
    panel(f'{name} {z}',role,(max(2*(w-c)-2*inset,1.),.5,span),(0,top+lift,z))


def deck_strake(sections,name,lefts,z0,z1,steps=8,role='dark',lift=.3,inset=.9):
    # A longitudinal panel line that follows the deck taper as short runs.
    for i in range(steps):
        z=z0+(z1-z0)*(i+.5)/steps
        w,top,_,c=surface(sections,z)
        for left in lefts:
            panel(f'{name} {left} {round(z,2)}',role,(1.,.5,abs(z1-z0)/steps*.92),
                  (left*(w-c-inset),top+lift,z))


def deck_panel(sections,name,z0,z1,left,width,role='trim',lift=1.1,inset=1.2):
    # A raised armour panel; its own edge is the highlight line the eye reads.
    z=(z0+z1)/2
    w,top,_,c=surface(sections,z)
    panel(f'{name} {round(z,2)}',role,(max(2*width*(w-c-inset),1.),lift,abs(z0-z1)*.9),
          (left*(w-c-inset),top+lift/2,z))


def flank_detail(sections,name,side,spec):
    # spec = (z, height, length, role, out, yfrac): a block standing proud of the
    # flank, placed between the keel and deck chamfers so it cannot float off.
    for z,height,length,role,out,yfrac in spec:
        w,top,bottom,c=surface(sections,z)
        lo,hi=bottom+c,top-c
        y=lo+(hi-lo)*yfrac
        panel(f'{name} {side} {z}',role,(out,height,length),(side*(w+out*.5-.2),y,z))


def louvre_bank(sections,name,side,z,rows=5,pitch=2.0,tall=5.5,length=6.5,role='trim'):
    # Vent louvres: a dark recess with bright bars across it, as authored detail
    # that survives at tactical range without a texture stage.
    w,top,bottom,c=surface(sections,z)
    y=(top+bottom)/2
    panel(f'{name} recess {side} {z}','dark',(.55,tall+.8,length+1.2),(side*(w+.2),y,z))
    for i in range(rows):
        panel(f'{name} blade {side} {z} {i}',role,(.95,1.,length),
              (side*(w+.45),y-tall/2+i*pitch,z))


# One unbroken pressure vessel, broad aft machinery shoulder, narrow load-bearing
# waist, flared forward citadel and a visibly deep, upswept armored ram.
# The frames are named because the detail pass below reads the same numbers:
# a panel line or greeble bank is placed from the surface it sits on, never
# from a hand-copied height that goes stale when a frame is tuned.
HULL=((-129,20,10,-12),(-111,29,16,-17),(-65,30,19,-20),(-25,23,16,-20),
      (8,15,10,-16),(31,27,12,-17),(58,36,15,-17),(91,30,17,-13),
      (115,19,18,-9),(135,5,15,-5))
CROWN=((32,19,13.2,9.5),(60,29,17,12.5),(91,24,19.2,15),
       (114,14,20.2,16),(132,3,17,12))
SHOULDER=((-118,13,14,-12),(-92,16,17,-15),(-52,15,14,-14),(-34,5,5,-9))
RAM=((57,34,-7,-14),(91,29,-3,-11),(115,18,0,-7),(135,4,4,-3))
ISLAND=((-102,17,26,13),(-83,21,33,15),(-53,17,31,15),(-31,11,20,10))
loft('01 Continuous pressure hull','base',HULL,.85)
loft('02 Stepped deep keel','base',[
    (-106,10,-10,-19),(-83,17,-13,-29),(-31,16,-12,-31),
    (16,10,-10,-25),(58,7,-9,-18),(111,3,-5,-11)],.7)
loft('03 Bow crown continuous armor','trim',CROWN,.55)
loft('04 Ram lower belt','dark',RAM,.3)
# Two large recessed deck wells; their outer armor is structure, not greeble stacks.
for side in (-1,1):
    s='Port' if side<0 else 'Starboard'
    loft(s+' aft pressure shoulder','base',SHOULDER,.8,(side*53,-2,0))
    # Open background slots between hull and drive bodies persist at base-only LOD.
    for z in (-112,-43):
        plate(s+' sculpted drive saddle '+str(z),'base',(35,9,12),(side*36,-7,z),.8)
    annulus(s+' bell throat shroud','dark',side*53,-3,[(-143,10,8),(-137,12,7.6),(-126,10,5.8)])
    annulus(s+' bell polished lip','trim',side*53,-3,[(-143.5,10.3,8),(-141.5,10.7,8)])
    cylinder(s+' exposed ion emitter','cool',(side*53,-3,-128),5.75,.3)
    # Broad long dorsal plates with recessed dark machinery channel along inboard edge.
    loft(s+' drive armored cowl','trim',[(-119,10,16.5,13),(-94,13,19,15),
        (-57,11,16.5,13),(-38,3,7,4)],.4,(side*53,-2,0))
    plate(s+' drive recessed machinery trench','dark',(7,1,52),(side*50,17,-86),.15)
    for z in (-105,-97,-89,-81,-73,-65):
        plate(s+' sunken heat exchanger '+str(z),'base',(6,.65,2.4),(side*50,17.65,z),.12)
    # Large owner-color band, held clear of adjacent shell, remains readable at distance.
    loft(s+' naval recognition band','accent',[(-113,3,18,17),(-91,4,20.1,19),
        (-57,3,17.6,16.7)],.12,(side*59,-2,0))
    # Hull bilge strakes follow the continuous main armor without becoming boxes.
    loft(s+' forward bilge armor','base',[(35,3,4,-11),(62,4,7,-10),
        (88,3,9,-6),(111,1.5,8,-3)],.35,(side*29,0,0))
    # Small forward-facing service bay on the citadel side, physically open.
    x=side*43
    for dx in (-4.5,4.5):
        plate(s+' bay cheek '+str(dx),'base',(1.6,9,19),(x+dx,-8,49),.3)
    for y in (-12.5,-3.5):
        plate(s+' bay roof floor '+str(y),'base',(10,1.5,19),(x,y,49),.3)
    plate(s+' recessed bay darkness','dark',(8,7,.5),(x,-8,40),.1)
    for y in (-11.3,-4.7):
        plate(s+' exposed launch guide '+str(y),'cool',(6.8,.5,.35),(x,y,58.8),.08)
    plate(s+' bay attachment','base',(24,4,8),(side*32,-7,42),.4)
    # Segmented flush flank plating creates purposeful seams across broad armor.
    for z,w,y in ((-98,26,8),(-72,27,10),(-46,24,9),(48,31,4),(74,30,7),(97,23,10)):
        plate(s+' lateral armor seam '+str(z),'dark',(1.0,5,1.1),(side*w,y,z),.12)

# Set-back navigation island with raked foreface, bridge visor and armored brow.
loft('05 Integrated navigation island','base',ISLAND,.8)
loft('06 Swept bridge core','dark',[
    (-89,12,39,27),(-78,15,44,28),(-60,14,42,28),(-47,8,34,24)],.65)
loft('07 Bridge roof visor','trim',[
    (-90,12.4,41.5,39),(-78,16,46,43),(-59,15,44,41),(-46,8.4,36,33)],.4)
# Exposed window ribbon follows side faces rather than being buried in the roof.
for side in (-1,1):
    plate('Bridge side glazing '+str(side),'lit',(1.0,2.2,20),(side*15.2,40.0,-70),.18)
    for z in (-78,-72,-66):
        plate('Glazing mullion '+str((side,z)),'dark',(1.4,2.5,.65),(side*15.4,40,z),.08)
plate('Bridge forward observation slit','lit',(15,2.1,.5),(0,34.3,-46.4),.15)
# The island mast is offset; an opposite-side angled sensor fin is not mirrored.
loft('Port swept signal fin','base',[(-86,1.8,46,38),(-80,1.5,61,42),(-77,1.0,59,41)],.3,(-7,0,0))
plate('Signal fin white cap','trim',(2.1,2,3),(-7,60,-80),.25)
plate('Starboard sensor pedestal','dark',(5,7,5),(11,47,-82),.5)
plate('Starboard sensor crossbar','trim',(12,1.3,3),(14,51,-82),.25)
cylinder('Offset communications dish','trim',(17,52,-82),3.2,1.0,axis='Y',n=12)
# Hero deck recognition stripe follows the prow sweep; not noisy all-over paint.
loft('08 Port bow recognition stripe','accent',[(39,3.3,15.5,14.5),
    (65,4,18.6,17.4),(91,3.3,20.8,19.5),(112,2,21.5,20.2)],.12,(-10,0,0))


def turret(name,center,scale=1):
    x,y,z=center
    cylinder(name+' barbette','dark',(x,y,z),6*scale,2*scale,'Y')
    loft(name+' raked gunhouse','base',[(-5,4.6,4.5,0),(1,5.3,5,0),(6,3.3,2.7,0)],.45,
         (x,y+scale,z))
    plate(name+' rangefinder','accent',(6,1,3),(x,y+6.2,z-1),.15)
    for dx in (-2.0,2.0):
        cylinder(name+' long barrel '+str(dx),'trim',(x+dx,y+3.4,z+10),.9,15,n=8)
        annulus(name+' muzzle '+str(dx),'dark',x+dx,y+3.4,[(z+17.5,1.2,.65),(z+16,1.2,.65)],n=8)

for z,y in ((48,18.0),(82,20),(110,20)):
    turret('Dorsal main battery '+str(z),(0,y,z))
for side in (-1,1):
    for z in (-103,-65):
        turret('Aft defense '+str((side,z)),(side*59,17,z),.8)
# Recessed spine machinery between island and prow, minimal silhouette clutter.
loft('09 Recessed reactor spine','dark',[(-30,8,16,11),(-7,9,13,8),(23,10,13,9)],.3)
for z in (-23,-15,-7,1,9,17):
    plate('Spine inset radiator '+str(z),'trim',(12,.8,2),(0,14.2 if z<0 else 13.9,z),.12)
# One visible maintenance spine only on starboard island, with lamp at its end.
plate('Asymmetric service trunk','dark',(3.6,3,29),(23,12,-77),.3)
for z in (-88,-80,-72,-64):
    plate('Service trunk collar '+str(z),'trim',(4.4,3.4,1),(23,12,z),.2)
plate('Exposed service floodlight','lit',(2,.6,2),(23,14,-62),.14)

# ---------------------------------------------------------------------------
# 10-19 Hull surface detail. The sculpted surfaces above read as one continuous
# grey plate between the major features, which is what the owner sees once the
# hull fills a third of the screen. Detail that survives that framing is
# large-scale plating and machinery, not fine line work: a 12-triangle block is
# 4 pixels at the shipped close camera, so the pass below spends its triangles
# on bold steps, trenches and machinery banks instead of hairline seams.
# Everything is placed from the frame it sits on, adds no silhouette and touches
# no feature the owner has approved.

# Raised after deck with a trench either side, then banded armour plating down
# the bow crown: the deck edge is the strongest line an untextured hull has.
for z0,z1 in ((-46,-16),(-14,14),(16,30)):
    deck_panel(HULL,'10 Raised aft deck plating',z0,z1,0,.72,role='trim',lift=2.6,inset=1.4)
for z0,z1 in ((-124,-104),(-102,-84),(-82,-62),(-60,-42),(-40,-22),(-20,-2),(0,20)):
    for left in (-.86,.86):
        deck_panel(HULL,'11 Aft deck edge trench',z0,z1,left,.12,role='dark',lift=.9,inset=2.2)

for z0,z1,role in ((34,54,'trim'),(54,70,'base'),(70,86,'dark'),(86,104,'trim'),
                   (104,116,'base'),(116,128,'dark')):
    deck_panel(CROWN,'12 Bow crown armour band',z0,z1,0,.88,role=role,lift=2.2,inset=1.2)
for z0,z1 in ((38,66),(70,100),(102,126)):
    for left in (-.55,.55):
        deck_panel(CROWN,'13 Bow crown longitudinal strake',z0,z1,left,.2,role='dark',lift=1.4,inset=1.6)
# Two open machinery wells with a raised coaming, as structure rather than paint.
for z0,z1 in ((58,74),(96,110)):
    for left in (-.42,.42):
        deck_panel(CROWN,'14 Bow deck machinery well',z0,z1,left,.3,role='dark',lift=.7,inset=1.8)
        for edge in (-.6,.6):
            deck_panel(CROWN,'15 Well coaming',z0,z1,left+edge*.12,.06,role='trim',lift=1.8,inset=1.8)

# Flank armour belt: large raised plates with dark gaps, so the side reads as
# built plating rather than as a wall.
for side in (-1,1):
    flank_detail(HULL,'16 Flank armour belt',side,(
        (-118,9.,26.,'base',1.4,.9),(-92,12.,30.,'trim',1.8,.85),(-62,10.,28.,'base',1.5,.9),
        (-34,8.,24.,'trim',1.6,.86),(-10,11.,26.,'base',1.7,.9),(16,9.,22.,'trim',1.5,.88),
        (40,12.,26.,'base',1.8,.86),(66,10.,24.,'trim',1.6,.9),(92,8.,20.,'base',1.4,.88)))
    flank_detail(HULL,'17 Belt plate gap',side,(
        (-105,14.,4.,'dark',2.1,.88),(-77,15.,4.5,'dark',2.2,.87),(-48,13.,4.,'dark',2.0,.9),
        (-22,12.,4.,'dark',2.0,.88),(3,13.,4.5,'dark',2.1,.9),(28,12.,4.,'dark',2.0,.87),
        (53,14.,4.5,'dark',2.1,.88),(78,12.,4.,'dark',2.0,.9),(102,10.,4.,'dark',1.9,.88)))
    # Machinery banks: two or three stacked blocks each, at a scale that holds
    # an edge and a shadow at the close camera.
    flank_detail(HULL,'18 Flank machinery bank',side,(
        (-112,7.,14.,'base',2.2,.9),(-112,5.,8.,'trim',3.0,.9),(-112,4.,5.,'dark',3.6,.9),
        (-70,9.,16.,'base',2.4,.86),(-70,6.,9.,'dark',3.2,.86),(-70,4.,6.,'trim',3.9,.86),
        (-24,8.,14.,'trim',2.3,.88),(-24,5.,8.,'base',3.1,.88),(-24,3.,5.,'dark',3.7,.88),
        (24,10.,18.,'base',2.5,.86),(24,6.,10.,'trim',3.3,.86),(24,4.,6.,'dark',4.0,.86),
        (74,9.,16.,'trim',2.4,.88),(74,6.,9.,'dark',3.2,.88),(-46,6.,10.,'base',2.8,.6),
        (44,6.,10.,'dark',2.8,.6),(-90,5.,9.,'trim',2.6,.62),(66,5.,9.,'base',2.6,.62)))
    # Vent banks with real blades, standing well proud of the belt.
    for z in (-100,-52,6,60):
        louvre_bank(HULL,'19 Flank vent bank',side,z,rows=4,pitch=3.2,tall=9.,length=11.,role='trim')
    louvre_bank(CROWN,'20 Bow flank vent bank',side,80,rows=3,pitch=3.,tall=7.,length=8.,role='base')

# Island: a window band at the bridge base with a dark inset under it, and
# machinery ledges, replacing the single hairline glazing strip.
for side in (-1,1):
    for z,length in ((-92,16.),(-70,16.),(-48,14.)):
        w,top,bottom,c=surface(ISLAND,z)
        panel(f'21 Island bridge window band {side} {z}','lit',(.9,2.6,length),(side*(w+.3),top-3.2,z))
        panel(f'22 Island window inset {side} {z}','dark',(.7,3.4,length+3.),(side*(w+.1),top-5.4,z))
    for z,length in ((-86,20.),(-56,18.)):
        w,top,bottom,c=surface(ISLAND,z)
        panel(f'23 Island machinery ledge {side} {z}','trim',(1.6,2.2,length),(side*(w+.5),top-7.6,z))
        panel(f'24 Island ledge shadow {side} {z}','dark',(.9,1.6,length-.5),(side*(w+.1),top-9.2,z))

# Aft drive housings and shoulder machinery: big blocks over the cowls.
for side in (-1,1):
    for z,height,length,role in ((-100,7.5,18.,'base'),(-74,6.5,16.,'trim')):
        w,top,bottom,c=surface(SHOULDER,z)
        plate(f'25 Aft drive housing {side} {z}',role,(9.,height,length),
              (side*53,top+height/2-.5,z),.5)
        plate(f'26 Drive housing face {side} {z}','dark',(1.2,height*.7,length*.6),
              (side*(53+w+4.2),top+height/2-.5,z),.2)
    for j,z in enumerate((-112,-96,-84,-70,-56,-44)):
        w,top,bottom,c=surface(SHOULDER,z)
        panel(f'27 Aft shoulder machinery {side} {z}','base' if j%2 else 'dark',
              (max(2*(w-c)-2.4,1.)*.5,2.2,11.),(side*53,top+1.1,z))

# Ram belt ribs and the owner-colour prow chevron, so the bow reads as a marked
# naval hull rather than a bare wedge.
for side in (-1,1):
    flank_detail(RAM,'28 Ram belt rib',side,(
        (62,4.2,4.5,'base',1.2,.5),(76,4.6,5.,'dark',1.4,.5),(90,4.2,4.5,'trim',1.2,.5),
        (104,3.8,4.5,'base',1.1,.5),(118,3.4,4.,'dark',1.0,.5)))
for left in (-.5,.5):
    deck_panel(CROWN,'29 Prow chevron marking',112,130,left,.34,role='accent',lift=2.6,inset=1.2)
deck_strake(CROWN,'30 Bow deck centre stripe',(0,),34,126,steps=6,role='accent',lift=2.5,inset=1.4)

# Keep the authored scene editable and useful when opened interactively.
bpy.context.scene['asset']='alliance_battleship'
bpy.context.scene['design']='Pelagic: continuous naval pressure hull, armored ram, separated drives'
bpy.context.scene['coordinates']='X beam; Y up; +Z forward; game model units'
bpy.context.scene['runtime']='evaluated triangulated material-role batches; no Blender dependency'
for obj in bpy.context.scene.objects:
    obj.select_set(False)
BLEND.parent.mkdir(parents=True,exist_ok=True)
EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND),compress=True)

# Indexed shared vertices and explicit face normals, six engine material-role batches.
# All vertices are evaluated AFTER Blender bevel modifiers; no primitive proxy export.
vertices=[]; lookup={}; batches={role:[] for role in ROLES}; parts=[]
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in sorted(bpy.context.scene.objects,key=lambda o:o.name):
    if obj.type!='MESH':continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    role=obj['engine_material_role']
    count=0
    for tri in mesh.loop_triangles:
        points=[tuple(round(float(c),6) for c in obj.matrix_world @ mesh.vertices[i].co) for i in tri.vertices]
        normal=(Vector(points[1])-Vector(points[0])).cross(Vector(points[2])-Vector(points[0]))
        if normal.length_squared<1e-12:continue
        # Python double-precision cross product over quantized vertices ensures
        # strict immutable geometry tests don't inherit mathutils float32 rounding.
        a,b,c=points;u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        length=math.sqrt(sum(t*t for t in n));n=[round(t/length,15) for t in n]
        indices=[]
        for p in points:
            if p not in lookup:lookup[p]=len(vertices);vertices.append(p)
            indices.append(lookup[p])
        batches[role].append(n+indices);count+=1
    parts.append(dict(name=obj.name,role=role,triangles=count))
    evaluated.to_mesh_clear()
lo=[min(p[i] for p in vertices) for i in range(3)]
hi=[max(p[i] for p in vertices) for i in range(3)]
asset=dict(schema=1,asset='alliance_battleship',authoring='Blender evaluated bevel mesh',
           coordinates='X beam; Y up; +Z forward',vertices=vertices,batches=batches,
           bounds=[lo,hi],parts=parts,triangle_count=sum(map(len,batches.values())))
assert 4400<asset['triangle_count']<11888,asset['triangle_count']
EXPORT.write_text(json.dumps(asset,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
print('GAME_EXPORT',json.dumps(dict(vertices=len(vertices),triangles=asset['triangle_count'],bounds=asset['bounds'],roles={k:len(v) for k,v in batches.items()},blend=str(BLEND),mesh=str(EXPORT))))
