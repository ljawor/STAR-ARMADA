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


# One unbroken pressure vessel, broad aft machinery shoulder, narrow load-bearing
# waist, flared forward citadel and a visibly deep, upswept armored ram.
loft('01 Continuous pressure hull','base',[
    (-129,20,10,-12),(-111,29,16,-17),(-65,30,19,-20),(-25,23,16,-20),
    (8,15,10,-16),(31,27,12,-17),(58,36,15,-17),(91,30,17,-13),
    (115,19,18,-9),(135,5,15,-5)],.85)
loft('02 Stepped deep keel','base',[
    (-106,10,-10,-19),(-83,17,-13,-29),(-31,16,-12,-31),
    (16,10,-10,-25),(58,7,-9,-18),(111,3,-5,-11)],.7)
loft('03 Bow crown continuous armor','trim',[
    (32,19,13.2,9.5),(60,29,17,12.5),(91,24,19.2,15),
    (114,14,20.2,16),(132,3,17,12)],.55)
loft('04 Ram lower belt','dark',[(57,34,-7,-14),(91,29,-3,-11),
    (115,18,0,-7),(135,4,4,-3)],.3)
# Two large recessed deck wells; their outer armor is structure, not greeble stacks.
for side in (-1,1):
    s='Port' if side<0 else 'Starboard'
    loft(s+' aft pressure shoulder','base',[
        (-118,13,14,-12),(-92,16,17,-15),(-52,15,14,-14),(-34,5,5,-9)],.8,(side*53,-2,0))
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
loft('05 Integrated navigation island','base',[
    (-102,17,26,13),(-83,21,33,15),(-53,17,31,15),(-31,11,20,10)],.8)
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
