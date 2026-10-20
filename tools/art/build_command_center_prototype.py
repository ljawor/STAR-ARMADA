#!/usr/bin/env python3
"""Original Imperium command fortress; standalone script-authoritative prototype.
Only writes its own editable master and six-role runtime mesh. No shared imports.
Blender --background --python-exit-code 1 --python this_file [-- --output-root REPO]
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector

ROLES=('base','dark','trim','accent','lit','cool')
COLORS={'base':(.32,.36,.40,1),'dark':(.065,.085,.11,1),
        'trim':(.56,.60,.63,1),'accent':(.65,.16,.055,1),
        'lit':(1,.65,.23,1),'cool':(.10,.78,1,1)}
p=argparse.ArgumentParser()
p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parents[2])
args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
ROOT=args.output_root.resolve()
MASTER=ROOT/'art/blender/imperium_command_prototype.blend'
EXPORT=ROOT/'visual_packs/imperium-command-prototype/assets/models/command.mesh.json'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version=0
MATS={}
for role in ROLES:
    m=bpy.data.materials.new(role); m.diffuse_color=COLORS[role]; m.use_nodes=True
    bsdf=m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=COLORS[role]
    bsdf.inputs['Metallic'].default_value=.5; bsdf.inputs['Roughness'].default_value=.4
    if role in ('lit','cool'):
        bsdf.inputs['Emission Color'].default_value=COLORS[role]
        bsdf.inputs['Emission Strength'].default_value=2.2
    MATS[role]=m

# Game uses Y up. Arm-local coordinates are rotated about Y as complete sectors.
sector=0

def place(v):
    x,y,z=v; a=sector*math.pi/2
    return (x*math.cos(a)+z*math.sin(a),y,-x*math.sin(a)+z*math.cos(a))

def mesh(name,role,verts,faces,bevel=0):
    data=bpy.data.meshes.new(name); data.from_pydata([place(v) for v in verts],[],faces); data.update()
    o=bpy.data.objects.new(f'{sector}: {name}',data); bpy.context.collection.objects.link(o)
    o['role']=role; data.materials.append(MATS[role])
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    if bevel:
        mod=o.modifiers.new('Manufactured broad-edge chamfer','BEVEL'); mod.width=bevel; mod.segments=1
    return o

def box(name,role,loc,size,bevel=0):
    x,y,z=loc; a,b,c=[v/2 for v in size]
    verts=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    # Tiny trim, vents and fittings stay flat-edged; bevel budget belongs to masses.
    dims=sorted(size)
    bevel=bevel if dims[0]>=2.4 and dims[1]*dims[2]>=110 else 0.0
    return mesh(name,role,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)

def octagon(w,d,c):
    return [(-w+c,-d),(w-c,-d),(w,-d+c),(w,d-c),(w-c,d),(-w+c,d),(-w,d-c),(-w,-d+c)]

def tier(name,role,levels,loc=(0,0),bevel=0):
    # Eight sided chamfered rectangular armored hull, independent cross sections.
    verts=[]
    for y,w,d,c in levels:
        verts.extend((x+loc[0],y,z+loc[1]) for x,z in octagon(w,d,c))
    faces=[tuple(reversed(range(8))),tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(levels)-1):
        for j in range(8): faces.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,verts,faces,bevel)

def beam(name,role,a,b,width,depth=None):
    a=Vector(a); b=Vector(b); direction=(b-a).normalized()
    side=direction.cross(Vector((0,1,0)))
    if side.length<.01: side=direction.cross(Vector((1,0,0)))
    side.normalize(); up=direction.cross(side).normalized()
    h=width/2; d=(depth or width)/2
    verts=[tuple(pt+side*s*h+up*t*d) for pt in (a,b) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return mesh(name,role,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)])

def cylinder(name,role,loc,r,height,n=12):
    verts=[(loc[0]+r*math.cos(j*2*math.pi/n),loc[1]+sy*height/2,loc[2]+r*math.sin(j*2*math.pi/n)) for sy in (-1,1) for j in range(n)]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,verts,faces)

# MAIN CITADEL: tapering octagonal pressure fortress with projecting glacis tiers.
tier('Citadel ventral octagonal keel','dark',[(-8,17,17,6),(-3,24,24,8),(7,24,24,8)],bevel=.45)
tier('Citadel lower sloped armored glacis','base',[(-3,25,25,8),(5,27,27,9),(16,24,24,8)],bevel=.65)
tier('Deep continuous service reveal','dark',[(15,24.1,24.1,8),(20,24.1,24.1,8)],bevel=.15)
tier('Overhanging upper command belt','trim',[(19,25.8,25.8,8),(21,25.8,25.8,8),(23,23,23,7)],bevel=.35)
tier('Command tier sloping armored walls','base',[(22,22.5,22.5,7),(30,19,19,6)],bevel=.5)
tier('Upper tier shadow separation','dark',[(29.5,19.3,19.3,6),(32.5,19.3,19.3,6)],bevel=.12)
tier('Bridge observation pressure house','base',[(32,17,15,5),(39,15.2,13.2,4)],loc=(0,-1),bevel=.4)
tier('Broad narrow-glazed observation visor','dark',[(36.8,17,14.1,4.8),(39.2,17,14.1,4.8)],loc=(0,-1),bevel=.15)
tier('Flying armored bridge brow','trim',[(39.1,18.2,15.1,5),(40.8,18.2,15.1,5),(42,16,13,4)],loc=(0,-1),bevel=.35)
# Low octagonal crown and asymmetrical sensor mast, not a fourth stacked cube.
tier('Armored signal crown','base',[(41.8,9,8,3),(44.2,7,6,2)],loc=(0,-3),bevel=.3)
box('Signals mast reinforced foot','dark',(-4,44.9,-4),(4.2,2.4,4.2),.25)
box('Slender command mast','trim',(-4,50,-4),(.8,10,1.0),.12)
box('Mast transverse directional array','dark',(-4,52,-4),(7.2,.6,1),.1)
box('Small exposed mast sensor','cool',(-4,55,-4),(1,.22,1.1))
box('Auxiliary communications blade','base',(7,46,-5),(.5,7,.8),.08)
box('Auxiliary short crossbar','dark',(7,48,-5),(3.2,.3,.45))

for sector in range(4):
    # Four articulated fortress arms: open diagonals preserve a readable silhouette.
    box('Arm graphite structural spine','dark',(0,6,30),(13,12,24),.5)
    box('Arm armored upper walkway','base',(0,13,31),(15,3,22),.45)
    for s in (-1,1):
        box('Arm longitudinal frame rail','trim',(s*6.8,9,31),(1.5,7,22),.2)
        for j,z in enumerate((23.5,29,34.5,40)):
            beam(f'Arm diagonal truss {s} {j}','base',(s*7.7,3,z-2.5),(s*7.7,11.5,z+2.5),1.2)
        box('Walkway inset service channel','dark',(s*4.5,14.62,30),(2,.25,15))
        for j in range(6):
            box('Walkway small service rib','trim',(s*4.5,14.85,24+j*2.4),(1.6,.24,.5))
    # Hangar bastion shell uses separate structural masses: genuinely open mouth.
    tier('Bastion heavy undercarriage','dark',[(-4,9.5,13,4),(0,13.5,16,4),(6,13.5,16,4)],loc=(0,45),bevel=.45)
    tier('Bastion bottom armored sill','base',[(1,13.7,16,4),(5,14,16,4)],loc=(0,45),bevel=.5)
    box('Hangar dark recessed back wall','dark',(0,11,40),(22,12,3),.3)
    box('Hangar exposed interior deck','dark',(0,5.4,49),(19,.6,21))
    for s in (-1,1):
        tier('Bastion massive hangar cheek','base',[(4,3.2,13,2),(18,3.2,13,2),(22,2.5,12,1.5)],loc=(s*10.7,47),bevel=.5)
        box('Hangar inner exposed rib','trim',(s*8.1,11,52),(.8,10,1.2),.12)
        box('Hangar inner second rib','base',(s*8.1,11,46),(.65,10,.9))
        box('Hangar portal upright armor','trim',(s*8.7,11.5,59.2),(1.5,11.5,1.7),.22)
        box('Hangar inner warm vertical marker','lit',(s*7.85,10,58.5),(.25,4,.18))
    box('Hangar projecting armored lintel','base',(0,18.9,54),(20.7,4.2,13),.5)
    box('Hangar inset exposed warm lintel','lit',(0,16.65,58.5),(13.6,.35,.35))
    box('Hangar upper dark opening fascia','dark',(0,17.1,60.65),(14,.9,.18))
    box('Hangar lower docking threshold','trim',(0,5.3,60.2),(15,.55,1.2),.1)
    # Roof has two armored shoulders around a deep graphite machinery trench.
    for s in (-1,1):
        box('Bastion grouped roof armor field','base',(s*7.2,22.1,47),(7.5,2.5,18),.5)
        box('Bastion shoulder trim panel','trim',(s*9.5,23.45,46),(2.5,.35,10),.1)
        box('Restrained owner identification bar','accent',(s*6.5,23.52,48),(2.5,.18,9),.06)
        box('Bastion outer flank dark vent cassette','dark',(s*14.03,11,46),(.25,6,10),.08)
        for j in range(7):
            box('Bastion flank grille grouped slat','base',(s*14.23,11,42+j*1.3),(.27,4.8,.48))
    box('Roof service trench deep bed','dark',(0,21.35,47),(5.4,.5,16))
    for j in range(3):
        box('Service trench machinery block','dark',(0,22.2,42+j*4.6),(3.6,1.4,3.2),.1)
        for k in range(4):
            box('Service trench exchanger slat','trim',(0,23,41+j*4.6+k*.65),(3,.22,.25))
    # Rear bastion gun emplacement, distinct from roof engineering.
    tier('Defence tower armored foundation','base',[(18,7,5,2),(26,6,4.5,1.5)],loc=(0,34),bevel=.35)
    cylinder('Defence turret rotation race','dark',(0,26.5,34),4.3,1.0,12)
    tier('Twin battery low armored mantlet','base',[(27,3.5,3,1),(30,3,2.5,.8)],loc=(0,34),bevel=.25)
    box('Turret roof cap','trim',(0,30.1,34),(4.3,.3,3.1),.1)
    for s in (-1,1):
        box('Twin battery barrel sleeve','dark',(s*1.4,28,39),(.9,1.0,6.4),.08)
        box('Twin battery exposed muzzle','trim',(s*1.4,28,42.9),(.72,.8,1.5),.06)
        box('Twin battery dark bore','dark',(s*1.4,28,43.67),(.42,.48,.05))
    # Central facade detail grouped in deliberate fields and exterior warm pinpricks.
    for x in (-13,-6.5,0,6.5,13):
        # Follow the glacis slope; a vertical decal-box here would be buried.
        plate=[]
        for offset in (0.12,0.65):
            for px,py in ((x-2.85,5),(x+2.85,5),(x+2.85,13),(x-2.85,13)):
                plate.append((px,py,27-(py-5)*3/11+offset))
        mesh('Citadel sloped grouped armor plate','base',plate,
             [(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)])
        box('Citadel shadow belt radiator','dark',(x,17.6,24.3),(5.2,2.2,.3))
        for k in range(3):
            box('Citadel belt radiator blade','trim',(x-1.5+k*1.5,17.6,24.5),(.45,1.65,.35))
    box('Upper citadel owner stripe','accent',(0,25,21.45),(10,1.0,.25))
    # Warm windows sit beyond the corresponding straight exterior visor planes.
    for j in range(7):
        box('Observation narrow warm window','lit',(-8.7+j*2.9,38.15,13.22),(1.45,.52,.16))
    box('Observation brow lower armor lip','base',(0,36.9,13.45),(22,.45,.55),.1)
    for s in (-1,1):
        box('Upper flank raised armor field','base',(s*14.8,27,15.7),(4.6,3,.6),.12)
        box('Citadel lower buttress','trim',(s*18,4.5,23),(2.5,8,4),.25)

# Functional asymmetric roof furniture keeps broad symmetry from becoming a kit.
sector=0
for x in (-11,11):
    box('Crown recessed thermal cassette','dark',(x,42.1,-2),(3.3,.5,10),.08)
    for j in range(7):
        box('Crown thermal louvre','trim',(x,42.47,-6+j*1.3),(2.8,.22,.5))
box('Rear signals processor','dark',(0,43,-8),(6,1.3,3),.15)
box('Rear signals processor armor','base',(0,43.8,-8),(5.3,.3,2.4),.08)
# Small one-sided communications wings and exposed tiny sensor aperture.
beam('Offset radar pedestal','trim',(11,42,-6),(13,47,-7),.65)
box('Offset radar graphite panel','dark',(13,47.8,-7),(5,2,.6),.12)
box('Small blue radar face','cool',(13,47.8,-6.66),(2,.55,.08))
for j in range(3):
    box('Rear command support housing','base',(-5+j*5,31,-19),(3.7,3.2,3.4),.25)
    box('Rear support dark vent','dark',(-5+j*5,32.8,-19),(2.8,.2,2.5))

# One final assembly fit only; keep proportions and editable independent parts.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get(); points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices); ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]; hi=[max(p[i] for p in points) for i in range(3)]
limits=((-61.999,61.999),(-7.999,54.999),(-61.999,61.999))
root=bpy.data.objects.new('IMPERIUM COMMAND FORTRESS — complete editable prototype',None); bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
# Fit the complete assembly per axis to retain the approved in-game envelope.
# This is a ~1.8% broadening of X/Z, not individual part distortion or scale drift.
scales=tuple((high-low)/(hi[i]-lo[i]) for i,(low,high) in enumerate(limits))
root.scale=scales
for i,(low,high) in enumerate(limits):
    root.location[i]=(low+high-(lo[i]+hi[i])*scales[i])/2

# Editable review camera and lighting, excluded from runtime export.
def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(152,133,174)); cam=bpy.context.object; cam.name='Fortress review three-quarter'
cam.data.type='ORTHO'; cam.data.ortho_scale=180; aim(cam,(0,15,0)); bpy.context.scene.camera=cam
for name,loc,power,size in [('Key',(20,160,80),280000,100),('Fill',(-130,75,20),190000,85),('Rim',(20,100,-130),220000,75)]:
    bpy.ops.object.light_add(type='AREA',location=loc); o=bpy.context.object; o.name=name; o.data.energy=power; o.data.size=size; aim(o,(0,15,0))
scene=bpy.context.scene; scene.world=bpy.data.worlds.new('Dark navy authoring world'); scene.world.color=(.045,.045,.045)
scene.render.engine='CYCLES'; scene.cycles.samples=24
scene.render.resolution_x=1400; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
scene['asset_status']='UNAPPROVED local prototype; standalone builder authoritative'
bpy.ops.object.select_all(action='DESELECT'); root.select_set(True); bpy.context.view_layer.objects.active=root
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
verts=[]; indices={}; batches={r:[] for r in ROLES}; parts=[]; skipped=0
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles(); local=[]
    for v in m.vertices:
        # Explicit float32 storage followed by stable decimal quantization.
        p=tuple(round(struct.unpack('f',struct.pack('f',float(c)))[0],7) for c in ev.matrix_world@v.co)
        if p not in indices: indices[p]=len(verts); verts.append(list(p))
        local.append(indices[p])
    count=0; role=o['role']
    for t in m.loop_triangles:
        ids=[local[k] for k in t.vertices]; a,b,c=(verts[k] for k in ids)
        u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]; length=math.sqrt(sum(q*q for q in n))
        if length<1e-12: skipped+=1; continue
        batches[role].append([round(q/length,15) for q in n]+ids); count+=1
    parts.append({'name':o.name,'role':role,'triangles':count}); ev.to_mesh_clear()
bounds=[[min(v[i] for v in verts) for i in range(3)],[max(v[i] for v in verts) for i in range(3)]]
total=sum(len(v) for v in batches.values())
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/command_station',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward','vertices':verts,
      'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
payload=json.dumps(data,separators=(',',':'))+'\n'
print('COMMAND_GEOMETRY '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}),flush=True)
assert total<=11888 and len(verts)<=9500,(total,len(verts))
assert len(payload.encode())<=2000000
for i,(low,high) in enumerate(((-62,62),(-8,55),(-62,62))):
    assert low<=bounds[0][i]<bounds[1][i]<=high,bounds
assert bounds[1][0]-bounds[0][0]>=121 and bounds[1][2]-bounds[0][2]>=121,bounds
assert bounds[1][1]-bounds[0][1]>=60,bounds
MASTER.parent.mkdir(parents=True,exist_ok=True); EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER)); EXPORT.write_text(payload)
print('MASTER '+str(MASTER),flush=True); print('MESH '+str(EXPORT),flush=True)
