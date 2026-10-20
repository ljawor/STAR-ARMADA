#!/usr/bin/env python3
"""Original Engineering Corps working tug. Standalone editable prototype builder.
Blender --background --python-exit-code 1 --python tools/art/build_engineer_prototype.py
Only this builder's .blend and mesh JSON are written. No shared builder imports.
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
COLORS={'base':(.32,.36,.40,1),'dark':(.065,.085,.11,1),'trim':(.56,.60,.63,1),
        'accent':(.65,.16,.055,1),'lit':(1,.65,.23,1),'cool':(.10,.78,1,1)}
p=argparse.ArgumentParser()
p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parents[2])
args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
ROOT=args.output_root.resolve()
MASTER=ROOT/'art/blender/imperium_engineer_prototype.blend'
EXPORT=ROOT/'visual_packs/imperium-engineer-prototype/assets/models/engineer.mesh.json'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version=0
MATS={}
for role in ROLES:
    m=bpy.data.materials.new(role); m.diffuse_color=COLORS[role]; m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=COLORS[role]
    bs.inputs['Metallic'].default_value=.5; bs.inputs['Roughness'].default_value=.4
    if role in ('lit','cool'):
        bs.inputs['Emission Color'].default_value=COLORS[role]
        bs.inputs['Emission Strength'].default_value=2.2
    MATS[role]=m

def mesh(name,role,verts,faces,bevel=0.0):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    o=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(o)
    o['role']=role; data.materials.append(MATS[role])
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    if bevel:
        mod=o.modifiers.new('Broad manufactured chamfer','BEVEL'); mod.width=bevel; mod.segments=1
    return o

FACES=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)]
def box(name,role,loc,size,bevel=0.0):
    x,y,z=loc; a,b,c=[v/2 for v in size]
    vs=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    return mesh(name,role,vs,FACES,bevel)

def loft(name,role,stations,x=0.0,bevel=0.0):
    vs=[]
    for z,w,t,b in stations:
        c=min((t-b)*.22,w*.22)
        vs.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),(x+w,b+c,z),
                   (x+w-c,b,z),(x-w+c,b,z),(x-w,b+c,z),(x-w,t-c,z)])
    fs=[tuple(reversed(range(8))),tuple(range(len(vs)-8,len(vs)))]
    for k in range(len(stations)-1):
        for j in range(8): fs.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,vs,fs,bevel)

def frame(a,b):
    a=Vector(a); b=Vector(b); dr=(b-a).normalized()
    side=dr.cross(Vector((0,1,0)))
    if side.length<.01: side=dr.cross(Vector((1,0,0)))
    side.normalize(); up=dr.cross(side).normalized()
    return a,b,side,up

def beam(name,role,a,b,width,depth=None):
    a,b,side,up=frame(a,b)
    vs=[tuple(pt+side*s*width/2+up*t*(depth or width)/2) for pt in (a,b) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return mesh(name,role,vs,FACES)

def tube(name,role,a,b,r,n=12):
    a,b,side,up=frame(a,b)
    vs=[tuple(pt+r*(side*math.cos(j*2*math.pi/n)+up*math.sin(j*2*math.pi/n))) for pt in (a,b) for j in range(n)]
    fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    fs.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,vs,fs)

def ring(name,role,x,y,stations,n=16):
    vs=[]; fs=[]
    for z,outer,inner in stations:
        for r in (outer,inner):
            vs.extend((x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
    for k in range(len(stations)-1):
        for wall in (0,1):
            a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
            for j in range(n): fs.append((a+j,a+(j+1)%n,b+(j+1)%n,b+j))
    for k in (0,len(stations)-1):
        a=k*2*n
        for j in range(n): fs.append((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n))
    return mesh(name,role,vs,fs)

# Short workboat pressure hull stops at the cradle bulkhead, never filling its opening.
loft('01 load bearing short tug pressure hull','dark',[(-19,10,7,-5),(-12,13,9,-6),(1,12,9,-6),(7,8,7,-4)],bevel=.4)
loft('02 deep layered belly keel','base',[(-17,8,-2,-7),(-4,10,-2,-7),(7,6,-1,-5)],bevel=.35)
loft('03 rear drive armored housing','base',[(-20,13,8,-4),(-15,14,10,-5),(-8,12,10,-4)],bevel=.5)
box('04 engineering deck armor','base',(0,9,-3),(21,2,15),.45)
box('05 front cradle root transverse bulkhead','base',(0,3,6),(19,7,3),.4)
box('06 cradle root machinery recess','dark',(0,4,7.6),(10,3,.45))
for x in (-3.6,-1.2,1.2,3.6):
    box('07 root mounted component socket','trim',(x,4,7.9),(1.3,1.8,.3))
# Offset raised cabin is a broad tiered inhabited workshop control house, not a mast.
loft('08 offset operations house lower plinth','base',[(-9,5.2,16,8),(0,5.2,16,8),(3,4,14,8)],x=-5,bevel=.35)
loft('09 offset high operations cabin','base',[(-8,4.5,24,14),(-1,4.5,25,14),(2,3.5,23,14)],x=-5,bevel=.35)
box('10 forward observation dark visor','dark',(-5,21,2.15),(6.7,2.7,.55))
for x in (-7.5,-5.8,-4.1,-2.4):
    box('11 exposed forward warm operations window','lit',(x,21.3,2.47),(1.05,.8,.12))
box('12 cabin heavy overhung brow','trim',(-5,23.05,1.8),(8.5,1.0,2.5),.17)
for z in (-6.7,-4.4,-2.1):
    box('13 cabin port dark visor','dark',(-9.55,21,z),(.4,2.2,1.9))
    box('14 cabin port warm glazing','lit',(-9.78,21.2,z),(.12,.7,1.3))
box('15 low roof survey housing','dark',(-5.5,25.65,-4),(4.2,1.7,4),.18)
box('16 small flush survey aperture','cool',(-5.5,25.9,-1.95),(1.3,.35,.12))
box('17 cabin roof access armor','trim',(-3.3,25.2,-6.7),(2,.35,2.3))
box('18 cabin owner stripe','accent',(-9.7,17,-4),(.18,.7,5))
# Main bilateral systems: side workshop racks, load carriers, guarded cooling cassettes.
for s in (-1,1):
    loft('19 side workshop pressure pod','base',[(-13,4.3,8,-3),(-5,4.7,9,-3),(5,4.1,8,-2)],x=s*14.5,bevel=.35)
    box('20 side graphite workshop recess','dark',(s*19,3,-4),(.7,7,13))
    for z in (-8,-3,2):
        box('21 pod removable service door','base',(s*19.45,3,z),(.45,5.4,4),.12)
        box('22 door recessed handhold','dark',(s*19.72,4.6,z),(.12,.5,1.4))
        box('23 door safety marking','accent',(s*19.73,1.5,z),(.12,.4,1.7))
    box('24 cargo rack dark tray','dark',(s*14,9.3,-2),(7,.7,16))
    for x in (s*11,s*17):
        box('25 carrier thick longitudinal frame','trim',(x,10.1,-2),(.7,1.1,16))
    for z in (-8,-2,4):
        box('26 strapped removable component module','base',(s*14,10.9,z),(4.5,2.4,3.6),.18)
        box('27 carrier component recess','dark',(s*14,12.15,z),(3.4,.18,2.5))
        for xx in (-1.6,1.6):
            box('28 carrier structural tie strap','trim',(s*14+xx,12.35,z),(.35,.4,3.9))
        box('29 carrier component serial paint','accent',(s*14,12.3,z),(1.4,.13,.5))
    box('30 rear thermal cassette dark foundation','dark',(s*10,10.2,-14),(6,1,8))
    for j in range(9):
        box('31 broad drive roof heat fin','trim',(s*10,11,-17.4+j*.83),(5.1,.8,.38))
    box('32 outboard radiator plenum','dark',(s*17.5,1,-14),(3,9,6),.18)
    for j in range(7):
        box('33 exposed flank radiator bank','base',(s*19,1,-16.5+j*.8),(1.4,7,.32))
    box('34 drive cowling owner strip','accent',(s*9,11.5,-18),(4,.18,1.2))
    # True annular nozzles: emitter is aft of the core cap, visible down an open bore.
    tube('35 capped drive core','dark',(s*8,1,-16),(s*8,1,-20),3.7,16)
    ring('36 hollow flared engine throat','dark',s*8,1,[(-19.6,3.9,2.8),(-22,4.4,3.2),(-24.6975,4.6,3.55)])
    ring('37 thick exposed nozzle lip','trim',s*8,1,[(-23.7,4.65,3.55),(-24.6975,4.65,3.55)])
    tube('38 visible small cool thrust emitter','cool',(s*8,1,-22.7),(s*8,1,-22.9),2.8,16)
    tube('39 dark emitter central service hub','dark',(s*8,1,-22.92),(s*8,1,-23.05),.7,12)
    for j in range(6):
        a=j*math.pi/3
        beam('40 nozzle external longitudinal reinforcement','base',(s*8+4.35*math.cos(a),1+4.35*math.sin(a),-20.5),(s*8+4.55*math.cos(a),1+4.55*math.sin(a),-23.5),.45)
    # Stout articulated arms with thick rotary joints and paired exterior ram cylinders.
    shoulder=(s*11,3,6); elbow=(s*14,2,14); wrist=(s*10,2,21)
    beam('41 main boxed construction arm','base',shoulder,elbow,4.8,5.1)
    beam('42 forward articulated arm housing','base',elbow,wrist,4.1,4.4)
    beam('43 arm graphite reinforcement panel','dark',(s*11,5.65,7),(s*13.5,4.65,13),2.6,.35)
    beam('44 forearm bright replaceable shield','trim',(s*13.6,4.4,15),(s*10.3,4.4,20),2.8,.4)
    for xx,yy,zz in (shoulder,elbow,wrist):
        tube('45 heavy horizontal hinge barrel','dark',(xx-3,yy,zz),(xx+3,yy,zz),2.7,16)
        for sign in (-1,1):
            tube('46 hinge exposed end casting','trim',(xx+sign*2.9,yy,zz),(xx+sign*3.25,yy,zz),2.1,16)
            tube('47 hinge dark axle bolt','dark',(xx+sign*3.25,yy,zz),(xx+sign*3.4,yy,zz),.8,8)
    for dy in (-1.8,1.8):
        tube('48 exposed hydraulic main barrel','dark',(s*14.2,3+dy,7),(s*16.2,2+dy,12),.72,12)
        tube('49 polished telescopic piston','trim',(s*16.2,2+dy,12),(s*13,2+dy,17),.38,12)
        tube('50 hydraulic cylinder collar','trim',(s*14.2,3+dy,7),(s*14.5,2.85+dy,7.7),.9,12)
    # Inward angled forks and vertical gripping pads; deliberately do not close center gap.
    beam('51 blunt inward grapple finger','base',wrist,(s*6.8,2,24),3,3.4)
    box('52 replaceable grapple contact shoe','trim',(s*6.2,2,23),(1.1,4.8,2.8))
    for yy in (.4,1.5,2.6,3.7):
        box('53 graphite grapple friction tooth','dark',(s*5.6,yy,23),(.45,.5,2.3))
    box('54 arm warning owner field','accent',(s*12,4.65,18),(1.8,.16,1.5))
    box('55 exposed cradle task light housing','dark',(s*9,6.6,7.8),(2.8,1.4,1.5))
    box('56 warm cradle task light','lit',(s*9,6.65,8.6),(1.9,.65,.15))
    # Short flat construction coupler, not a muzzle or gun barrel.
    box('57 flat build tool socket enclosure','dark',(s*9.1,1.2,20),(1.8,2,2.5))
    box('58 trim construction coupling face','trim',(s*8.1,1.2,20),(.3,1.8,2.1))
    box('59 small cool welding coupler face','cool',(s*7.9,1.2,20),(.12,.65,.85))
# Low cradle bed has no forward wall or roof; the central working space remains open.
box('60 cradle rear low receiving tray','dark',(0,-3.8,10),(10,1.1,5.2))
for s in (-1,1):
    beam('61 low cradle longitudinal guide','trim',(s*4.4,-3,8),(s*4.4,-3,16),.7,1.1)
    box('62 cradle captive roller casing','base',(s*4.5,-2.6,13),(1.6,1.5,2.2))
    tube('63 cradle exposed load roller','trim',(s*4.5,-2,12.4),(s*4.5,-2,13.6),.75,12)
# Clustered engineering plumbing and service cassettes instead of scattered jewelry.
for x in (1.5,4.2,6.9):
    box('64 starboard deck machinery cassette','dark',(x,11,-2),(2.1,2,9),.15)
    for j in range(7):
        box('65 cassette removable cooling slat','trim',(x,12.1,-5.5+j*1.1),(1.65,.22,.45))
    tube('66 deck hydraulic accumulator','base',(x,10.3,4),(x,13,4),.8,12)
    tube('67 accumulator dark pressure cap','dark',(x,13,4),(x,13.45,4),.6,12)
for s in (-1,1):
    for z in (-12,-8,-4,0):
        box('68 ventral replaceable armor tile','base',(s*5,-5.6,z),(6.5,1.4,3.4),.14)
    for z in (-10,-4,2):
        beam('69 workshop load bearing underside brace','dark',(s*8,-4,z),(s*17,-1,z),1.25,1.6)
    for z in (-11,-5,1):
        tube('70 outboard guarded service pipe','dark',(s*16,6,z),(s*16,6,z+3.6),.45,10)
        for zz in (z+.3,z+3):
            tube('71 pipe heavy ring coupling','trim',(s*16,6,zz),(s*16,6,zz+.35),.65,10)
    for z in (-8,-3,2):
        box('72 workshop exposed worklight','lit',(s*18,8.5,z),(.8,.25,1.4))
    box('73 rear drive service plate','base',(s*4,8.7,-17),(4,.5,3),.12)
    for x in (-1,1):
        box('74 service plate captive fastener','dark',(s*4+x*1.3,9,-17),(.4,.18,.4))
# Fit the COMPLETE evaluated assembly separately on every axis and side.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get(); points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices); ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]; hi=[max(p[i] for p in points) for i in range(3)]
limits=((-19.99898,19.99898),(-6.99898,26.49898),(-24.69648,24.35723))
root=bpy.data.objects.new('ENGINEERING CORPS — complete original editable tug assembly',None); bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
for i,(low,high) in enumerate(limits):
    root.scale[i]=(high-low)/(hi[i]-lo[i]); root.location[i]=(low+high-(lo[i]+hi[i])*root.scale[i])/2

def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(85,65,100)); cam=bpy.context.object; cam.name='Engineering workboat review three quarter'
cam.data.type='ORTHO'; cam.data.ortho_scale=78; aim(cam,(0,7,0)); bpy.context.scene.camera=cam
for name,loc,power,size in [('Key',(20,100,70),130000,65),('Fill',(-90,45,30),100000,60),('Rim',(40,40,-80),110000,55)]:
    bpy.ops.object.light_add(type='AREA',location=loc); o=bpy.context.object; o.name=name; o.data.energy=power; o.data.size=size; aim(o,(0,5,0))
scene=bpy.context.scene; scene.world=bpy.data.worlds.new('Dark neutral authoring world'); scene.world.color=(.045,.045,.045)
scene.render.engine='CYCLES'; scene.cycles.samples=24
scene.render.resolution_x=1400; scene.render.resolution_y=1200; scene.render.resolution_percentage=100
scene['asset_status']='UNAPPROVED local prototype; standalone engineer builder authoritative'
scene['binding']='imperial:constructor'; scene['design']='Original noncombat Engineering Corps Corvette; open cradle, hydraulic grapple arms, offset control cabin, workshop racks, hollow stern drives'
bpy.ops.object.select_all(action='DESELECT'); root.select_set(True); bpy.context.view_layer.objects.active=root
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
verts=[]; indices={}; batches={r:[] for r in ROLES}; parts=[]; skipped=0
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles(); local=[]
    for v in m.vertices:
        pt=tuple(struct.unpack('f',struct.pack('f',float(c)))[0] for c in ev.matrix_world@v.co)
        if pt not in indices: indices[pt]=len(verts); verts.append(list(pt))
        local.append(indices[pt])
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
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/constructor',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward','vertices':verts,
      'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
payload=json.dumps(data,separators=(',',':'))+'\n'
print('ENGINEER_GEOMETRY '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}),flush=True)
assert total<=11888 and len(verts)<=9500,(total,len(verts))
assert len(payload.encode())<=2000000
for i,(low,high) in enumerate(((-20,20),(-7,26.5),(-24.6975,24.35825))):
    assert low+.001<=bounds[0][i]<bounds[1][i]<=high-.001,bounds
    assert abs(bounds[0][i]-low)<.01 and abs(bounds[1][i]-high)<.01,bounds
assert all(batches[r] for r in ROLES)
MASTER.parent.mkdir(parents=True,exist_ok=True); EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER)); EXPORT.write_text(payload)
print('MASTER '+str(MASTER),flush=True); print('MESH '+str(EXPORT),flush=True)
