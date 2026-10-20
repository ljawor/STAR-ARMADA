#!/usr/bin/env python3
"""Original Imperium open construction drydock; standalone script-authoritative prototype.
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
MASTER=ROOT/'art/blender/imperium_shipyard_prototype.blend'
EXPORT=ROOT/'visual_packs/imperium-shipyard-prototype/assets/models/shipyard.mesh.json'
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

def mesh(name,role,verts,faces,bevel=0.0):
    data=bpy.data.meshes.new(name); data.from_pydata([place(v) for v in verts],[],faces); data.update()
    o=bpy.data.objects.new(f'{sector}: {name}',data); bpy.context.collection.objects.link(o)
    o['role']=role; data.materials.append(MATS[role])
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    if bevel:
        mod=o.modifiers.new('Manufactured broad-edge chamfer','BEVEL'); mod.width=bevel; mod.segments=1
    return o

def box(name,role,loc,size,bevel=0.0):
    x,y,z=loc; a,b,c=[v/2 for v in size]
    verts=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    # Tiny trim, vents and fittings stay flat-edged; bevel budget belongs to masses.
    dims=sorted(size)
    bevel=bevel if dims[0]>=2.4 and dims[1]*dims[2]>=110 else 0.0
    return mesh(name,role,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)

def octagon(w,d,c):
    return [(-w+c,-d),(w-c,-d),(w,-d+c),(w,d-c),(w-c,d),(-w+c,d),(-w,d-c),(-w,-d+c)]

def tier(name,role,levels,loc=(0,0),bevel=0.0):
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


def axle(name,role,loc,r,length,n=8):
    # Horizontal hinge drums, axis along Z; polygonal mechanical manufacture.
    x,y,z=loc
    v=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+s*length/2) for s in (-1,1) for j in range(n)]
    f=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    f.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,v,f)

# An open U-shaped ship construction dock: the void is the hero, not a citadel.
box('Continuous ventral construction keel','dark',(0,-6,12),(9,8,85),.7)
box('Keel armored spine crown','base',(0,-1.6,11),(7.5,2.8,86),.45)
for j,z in enumerate((-19,-3,13,29,45)):
    box('Transverse heavy cradle foundation','dark',(0,-3.8,z),(53,6,6),.5)
    box('Exposed cradle center saddle','trim',(0,.5,z),(8,1.2,4.5))
    for s in (-1,1):
        beam('Ventral cradle rising shoulder','base',(s*4,-3,z),(s*24,1,z),4,4)
        box('Cradle hydraulic shoe','dark',(s*15,1.3,z),(5,2.6,5))
        box('Cradle bare bearing plate','trim',(s*15,2.8,z),(4.5,.5,4))

# Paired long thick logistics decks remain outboard of a completely open bay.
for s in (-1,1):
    box('Longitudinal graphite dock girder','dark',(s*26,-1,9),(10,8,91),.65)
    box('Armored continuous logistics deck','base',(s*27,3,9),(13,3.8,92),.55)
    box('Outer deck edge bright armor','trim',(s*33.3,3.3,9),(1.1,3.5,91))
    box('Inner recessed crane travel race','dark',(s*23.4,5.05,9),(1.9,.3,87))
    box('Bare inner crane rail','trim',(s*23.4,5.38,9),(.65,.4,86))
    for j,z in enumerate((-28,-13,2,17,32,47)):
        box('Unequal layered deck armor field','base',(s*29,5.05,z),(5.8,.45,11.8))
        box('Deck service shadow channel','dark',(s*31.8,5.32,z),(.6,.22,9))
        box('Deck ownership small painted stripe','accent',(s*27,5.36,z),(1.1,.18,5))
        box('Warm outboard deck work beacon','lit',(s*33.95,3.7,z),(.18,.55,1.1))
        box('Inner bay exposed work lamp','lit',(s*20.9,3.8,z),(.16,.6,1.4))
        # Substantial lower flange rib, not a fine wire scaffold.
        beam('Lower angled dock web','base',(s*29,-4,z-4),(s*29,1,z+4),1.4,2)
    # A procession of tall, articulated half-gantries, never bridging the top.
    for j,z in enumerate((-18,-2,14,30,46)):
        tag=f'{s} gantry {j}'
        tier(tag+' massive traveling pedestal','base',[(4.7,4.2,4,1),(8,4.2,4,1),(10,3,3.2,.8)],loc=(s*26,z))
        beam(tag+' tapered rising backbone','dark',(s*26,8,z),(s*24.5,24,z),4.6,4.8)
        beam(tag+' external armored face','base',(s*28,9,z),(s*26,23,z),2.8,4.9)
        axle(tag+' shoulder main bearing','dark',(s*24.5,24,z),3.05,5.2)
        axle(tag+' exposed shoulder bearing cap','trim',(s*24.5,24,z+2.75),2.05,.45)
        axle(tag+' bearing center','base',(s*24.5,24,z+3.02),.85,.18,10)
        beam(tag+' cantilever handling arm','base',(s*24.3,25,z),(s*15.5,30,z),3.8,4.3)
        beam(tag+' lower cantilever reinforcement','dark',(s*23,22,z),(s*16.5,27.8,z),1.7,2.4)
        beam(tag+' hydraulic actuator cylinder','trim',(s*27,14,z+2.4),(s*23,24,z+2.4),1.15)
        beam(tag+' hydraulic ram','dark',(s*23,24,z+2.4),(s*18.5,28,z+2.4),.68)
        axle(tag+' end tool joint','dark',(s*15.5,29.3,z),1.9,4.6)
        box(tag+' suspended gripping head','trim',(s*15.2,27.4,z),(3.6,3,4.8),.2)
        box(tag+' inboard graphite tool face','dark',(s*13.35,27,z),(.3,2.1,3.5))
        box(tag+' external warm tool light','lit',(s*13.14,27.5,z),(.14,.35,1.6))
        box(tag+' ownership shoulder marking','accent',(s*26.7,20,z+2.52),(1.6,3.2,.16))
        for k in range(3):
            box(tag+' reinforced ankle pressure coupling','dark',(s*(25+k*.85),9,z+3.48),(.55,1.6,.55))
        box(tag+' narrow service ladder bed','dark',(s*28.1,14,z),( .3,8,1.2))
        for k in range(4):
            box(tag+' ladder rung','trim',(s*28.32,11+k*1.35,z),(.2,.2,1.1))

# Rear armored manufacturing halls seal only the aft end, not the useful bay.
tier('Aft factory ventral armored pressure hull','dark',[(-8,28,11,4),(-3,34,12,4),(6,34,12,4)],loc=(0,-32),bevel=.5)
tier('Broad chamfered fabrication hall','base',[(2,33,11,4),(14,32,11,4),(18,29,9,3)],loc=(0,-32),bevel=.65)
box('Forward factory graphite service facade','dark',(0,10,-20.7),(48,10,.7))
box('Factory bay armored lintel','trim',(0,15.5,-19.8),(49,2.2,2.8))
for x in (-18,-9,0,9,18):
    box('Factory pressure door inset','dark',(x,8.4,-20),(6.7,7,.45))
    box('Factory pressure door lower panel','base',(x,7.4,-19.7),(5.8,4.8,.25))
    box('Warm factory door overhead work strip','lit',(x,12.5,-19.4),(4.4,.4,.2))
    for k in range(3):
        box('Factory forward upper windows','lit',(x-2+k*2,14,-19.25),(.9,.45,.2))
    box('Factory top thermal well','dark',(x,18.1,-32),(6.7,.4,10))
    for k in range(6):
        box('Factory roof exchanger blade','trim',(x,18.48,-36+k*1.55),(5.5,.28,.65))
# Deliberately offset low control tower has an observation visor, not a citadel.
tier('Port operations offset armored base','base',[(16,8,8,2),(25,7,7,2)],loc=(-20,-31),bevel=.4)
tier('Operations dark observation belt','dark',[(24,7.4,7.4,2),(28,7.4,7.4,2)],loc=(-20,-31))
tier('Operations floating armored brow','trim',[(27.8,8,8,2),(29.7,8,8,2),(31,6.5,6.5,2)],loc=(-20,-31),bevel=.25)
for j in range(5):
    box('Operations forward warm observation window','lit',(-24+j*2,26.3,-23.48),(1.15,.65,.18))
    box('Operations outer warm observation window','lit',(-27.48,26.3,-35+j*2),(.18,.65,1.15))
box('Short comms foot','dark',(-20,31.5,-33),(3,1,3))
box('Compact traffic director mast','trim',(-20,32.5,-33),(.6,3,.65))
box('Tiny cyan traffic sensor','cool',(-20,34,-33),(1,.25,.9))

# Lateral fabrication sponsons: grouped tanks, equipment, heat banks, stout crane.
for s in (-1,1):
    for j,z in enumerate((-12,12,36)):
        tier('Outboard fabrication machinery raft','base',[(-2,6.7,8,2),(3,6.7,8,2),(5,5.3,6.5,1.5)],loc=(s*37,z))
        box('Machine raft recessed equipment bed','dark',(s*37,5.15,z),(9,.4,9))
        for k in (-1,1):
            cylinder('Pressure accumulator tank','dark',(s*37+k*2,7,z-1),1.55,3.5,8)
            cylinder('Accumulator armored upper dome','base',(s*37+k*2,8.9,z-1),1.67,.8,8)
            cylinder('Accumulator bare neck','trim',(s*37+k*2,9.5,z-1),.65,.6,8)
            box('Tank restraint shoulder','trim',(s*37+k*2,6.6,z+.55),(2.6,.5,.45))
        box('Equipment bank armored cap','base',(s*37,6,z+4),(8,1.5,3))
        box('Equipment bank radiator recess','dark',(s*37,6.9,z+4),(7,.35,2.4))
        for k in range(8):
            box('Machinery grouped thermal vane','trim',(s*37-3+k*.85,7.2,z+4),(.34,.35,2))
        box('Tiny machine cyan diagnostic','cool',(s*40.2,7.45,z+4),(.35,.18,.45))
        for k in range(4):
            box('Outboard armored flank vent recess','dark',(s*43.45,.5,z-4.5+k*3),(.22,2,2.2))
            box('Outboard warm service pin','lit',(s*43.6,1.1,z-4.5+k*3),(.12,.28,.7))
    # Thick articulated asymmetric loading boom, folded outside central bay.
    cylinder('Cargo crane stout rotation turntable','dark',(s*36,7,-12),3,2,16)
    box('Cargo crane armored power pack','base',(s*36,9,-12),(5,3,5),.3)
    beam('Cargo crane substantial lower boom','base',(s*36,10,-12),(s*39,17,-7),2.4,3)
    axle('Cargo crane hinge drum','trim',(s*39,17,-7),1.7,3.4)
    beam('Cargo crane folded upper boom','dark',(s*39,17,-7),(s*35,15,2),1.8,2.3)
    beam('Cargo crane polished stout actuator','trim',(s*38,12,-10),(s*38,16,-3),.65)
    box('Cargo crane handling coupler','base',(s*35,14.5,2),(3,2.4,3))
    for z in (-34,-28):
        box('Aft thick logistics trunk','dark',(s*34,6,z),(5,5,4))
        box('Aft bare trunk clasp','trim',(s*34,8.6,z),(4,.4,2))

# A few grouped crate/fabrication cassettes articulate scale on broad decks.
for s in (-1,1):
    for j,z in enumerate((-22,-8,7,23,40)):
        box('Deck grouped tooling cassette','dark',(s*29,6.3,z),(3.7,2,4))
        box('Deck tooling armored lid','base',(s*29,7.45,z),(3.9,.4,4.1))
        for k in (-1,1):
            box('Tool cassette bare clasp','trim',(s*29+k*1.2,7.7,z),(.35,.2,3.6))
        box('Cassette exterior warm status','lit',(s*29,6.7,z+2.05),(.6,.3,.1))

# One final assembly fit only; keep proportions and editable independent parts.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get(); points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices); ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]; hi=[max(p[i] for p in points) for i in range(3)]
limits=((-43.6489,43.6489),(-9.9989,34.2239),(-44.9989,55.5059))
root=bpy.data.objects.new('IMPERIUM OPEN CONSTRUCTION SHIPYARD — complete editable prototype',None); bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
# Fit the complete assembly per axis to retain the approved in-game envelope.
# This is a ~1.8% broadening of X/Z, not individual part distortion or scale drift.
scales=tuple((high-low)/(hi[i]-lo[i]) for i,(low,high) in enumerate(limits))
root.scale=scales
for i,(low,high) in enumerate(limits):
    root.location[i]=(low+high-(lo[i]+hi[i])*scales[i])/2

# Editable review camera and lighting, excluded from runtime export.
def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(133,112,166)); cam=bpy.context.object; cam.name='Shipyard review open fore bay'
cam.data.type='ORTHO'; cam.data.ortho_scale=143; aim(cam,(0,15,0)); bpy.context.scene.camera=cam
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
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/shipyard',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward','vertices':verts,
      'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
payload=json.dumps(data,separators=(',',':'))+'\n'
print('SHIPYARD_GEOMETRY '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}),flush=True)
assert total<=11888 and len(verts)<=9500,(total,len(verts))
assert len(payload.encode())<=2000000
for i,(low,high) in enumerate(((-43.65,43.65),(-10,34.225),(-45,55.507))):
    assert low<=bounds[0][i]<bounds[1][i]<=high,bounds
for i,(low,high) in enumerate(((-43.65,43.65),(-10,34.225),(-45,55.507))):
    assert bounds[0][i]>=low+.001 and bounds[1][i]<=high-.001,bounds
    assert abs(bounds[0][i]-low)<.01 and abs(bounds[1][i]-high)<.01,bounds
assert total>=8500,total
assert skipped==0,skipped
MASTER.parent.mkdir(parents=True,exist_ok=True); EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER)); EXPORT.write_text(payload)
print('MASTER '+str(MASTER),flush=True); print('MESH '+str(EXPORT),flush=True)
