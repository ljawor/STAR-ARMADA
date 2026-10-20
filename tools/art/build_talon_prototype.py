#!/usr/bin/env python3
"""Original Talon interceptor: ONE representative craft, never a six-ship assembly.
Standalone/script-authoritative; writes only its own blend and runtime JSON.
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
MASTER=ROOT/'art/blender/imperium_talon_prototype.blend'
EXPORT=ROOT/'visual_packs/imperium-talon-prototype/assets/models/talon.mesh.json'
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


def mesh(name,role,verts,faces,bevel=0.0):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    o=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(o)
    o['role']=role; data.materials.append(MATS[role])
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    if bevel:
        mod=o.modifiers.new('Broad armor edge chamfer','BEVEL'); mod.width=bevel; mod.segments=1
    return o


def loft(name,role,stations,x=0.0,bevel=0.0):
    verts=[]
    for z,w,t,b in stations:
        c=min((t-b)*.24,w*.3)
        verts.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),(x+w,b+c,z),
                      (x+w-c,b,z),(x-w+c,b,z),(x-w,b+c,z),(x-w,t-c,z)])
    faces=[tuple(reversed(range(8))),tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(stations)-1):
        for j in range(8): faces.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,verts,faces,bevel)


def plate(name,role,outline,top,bottom,bevel=0.0):
    # Arbitrary clipped delta outline, genuinely thick root-to-tip sections.
    n=len(outline)
    vv=[(x,bottom(x,z),z) for x,z in outline]+[(x,top(x,z),z) for x,z in outline]
    ff=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    ff.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,vv,ff,bevel)


def box(name,role,loc,size,bevel=0.0):
    x,y,z=loc; a,b,c=(s/2 for s in size)
    vv=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    return mesh(name,role,vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)


def ring(name,role,x,y,stations,n=12):
    vv=[]; ff=[]
    for z,outer,inner in stations:
        for r in (outer,inner): vv.extend((x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
    for k in range(len(stations)-1):
        for wall in (0,1):
            a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
            ff.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
    for k in (0,len(stations)-1):
        a=k*2*n
        ff.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
    return mesh(name,role,vv,ff)


def disc(name,role,x,y,z,r,depth,n=12):
    vv=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+d*depth/2) for d in (-1,1) for j in range(n)]
    ff=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    ff.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,vv,ff)


# A tapered armored spear, not a ball/panel fighter and not a miniature destroyer.
loft('01 continuous graphite monocoque','dark',[(-23,6.9,4.7,-2.5),(-12,8,5.4,-3.24),(2,6.8,5.5,-2.5),(19,3.7,3.5,-1.8),(35,.35,.8,-.7)],bevel=.17)
loft('02 ventral spear armor','base',[(-21,4.5,-.9,-3),(-7,5.5,-.7,-3.15),(17,3,-.3,-2),(34,.32,.5,-.7)],bevel=.16)
for s in (-1,1):
    # Broad clipped delta wing. A single thick load path, with swept layered plates.
    outline=[(s*6,15),(s*28,-10),(s*31.25,-17),(s*30,-22),(s*21,-23),(s*7,-14)]
    top=lambda x,z: 4.1-abs(x)*.075
    bottom=lambda x,z: -.9+abs(x)*.025
    plate(f'03 {s} thick swept clipped delta wing','base',outline,top,bottom,.22)
    inset=[(s*10,9),(s*25,-8),(s*28,-16),(s*23,-18),(s*11,-11)]
    plate(f'04 {s} graphite recessed wing service field','dark',inset,lambda x,z:top(x,z)+.14,lambda x,z:top(x,z)-.15)
    outer=[(s*14,2),(s*26,-10),(s*28,-16),(s*23.8,-16.9),(s*17,-9)]
    plate(f'05 {s} raised swept wing armor field','base',outer,lambda x,z:top(x,z)+.65,lambda x,z:top(x,z)+.12,.12)
    aft=[(s*9,-12),(s*20,-20),(s*27.5,-20.5),(s*22.4,-17.5),(s*12,-9)]
    plate(f'06 {s} broad trailing edge armor','trim',aft,lambda x,z:top(x,z)+.4,lambda x,z:top(x,z)+.02)
    paint=[(s*16,-.2),(s*17,-1.3),(s*25.3,-11),(s*24.7,-12.5)]
    plate(f'07 {s} narrow swept ownership slash','accent',paint,lambda x,z:top(x,z)+.81,lambda x,z:top(x,z)+.68)
    # Outboard weapon claws point forward of the swept wing, stout not fine barrels.
    loft(f'08 {s} outboard weapon pod armored claw','base',[(-16,2.7,4.8,.0),(-7,3.3,5.3,-.3),(5,2.4,4.8,.3),(14,1.55,3.6,.7)],x=s*23,bevel=.2)
    loft(f'09 {s} weapon dorsal layered plate','trim',[(-13,1.8,5.5,4.4),(-5,2,5.8,4.8),(5,1.3,5.1,4.2)],x=s*23,bevel=.12)
    loft(f'10 {s} forward cannon graphite jacket','dark',[(10,1.3,3.2,1),(18,1.1,3,1.1)],x=s*23,bevel=.1)
    ring(f'11 {s} open gun muzzle','trim',s*23,2.05,[(17.6,1.17,.69),(19.1,1.08,.68)],n=8)
    disc(f'12 {s} recessed black gun bore','dark',s*23,2.05,17.8,.66,.05,n=8)
    box(f'13 {s} weapon service paint','accent',(s*23,5.91,-6.8),(2.4,.15,2.5))
    # Root nacelles have large visible forward intake mouths, graphite ducts.
    loft(f'14 {s} thick drive root armored shoulder','base',[(-23,3.8,6.8,-1.7),(-12,4.7,7.6,-1.8),(1,3.8,6.3,-1),(9,2.7,4.9,-.2)],x=s*8.4,bevel=.24)
    ring(f'15 {s} angular large intake lip','trim',s*8.7,3.45,[(9.3,2.68,2.02),(11.4,2.52,1.98)],n=8)
    disc(f'16 {s} deep graphite intake face','dark',s*8.7,3.45,9.5,1.95,.1,n=8)
    for j in (-1,0,1):
        box(f'17 {s} intake vane {j}','dark',(s*8.7+j*.9,3.45,10.8),(.24,3,.55))
    loft(f'18 {s} nacelle roof shingle','base',[(-21,2.65,7.2,6),(-13,3.1,8.1,6.7),(-5,2.2,7.6,6.4)],x=s*8.4,bevel=.14)
    box(f'19 {s} nacelle ownership band','accent',(s*8.4,8.13,-13.5),(4,.14,1.8))
    # Dark service well is exposed aft of the roof. Few large vanes, no fine clutter.
    box(f'20 {s} aft thermal well','dark',(s*8.4,7.3,-21),(3.7,.5,3.3))
    for j in range(3): box(f'21 {s} thermal vane {j}','trim',(s*8.4,7.68,-22+j),(3.1,.26,.35))
    # Caps terminate at -23; emitter at -27 is outside those hull caps.
    ring(f'22 {s} hollow drive throat','dark',s*8.4,2.8,[(-22.8,3.55,2.55),(-25.6,3.85,2.8),(-28.996,4.05,3.15)])
    ring(f'23 {s} nozzle bright annular lip','trim',s*8.4,2.8,[(-28.3,4.07,3.15),(-28.996,4.07,3.15)])
    disc(f'24 {s} small exposed ion emitter','cool',s*8.4,2.8,-27.5,1.65,.1)
    disc(f'25 {s} emitter dark center hub','dark',s*8.4,2.8,-27.59,.65,.12)
    # Warm maintenance lights at actual service locations, never cockpit windows.
    box(f'26 {s} intake service lamp','lit',(s*11,5.25,6.5),(.4,.45,.65))
    box(f'27 {s} weapon safety indicator','lit',(s*25.95,3.7,-5),(.16,.45,.8))
    # Low swept twin stabilizers: broad angular blades, no wire aerial forest.
    vv=[(s*7.1,6,-22),(s*7.1,11.5,-23),(s*7.1,10.3,-17),(s*7.1,6,-11)]
    vv+= [(x+s*.8,y,z) for x,y,z in vv]
    mesh(f'28 {s} swept rear stabilizer','base',vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],.1)

# Raised angular canopy with graphite glazing, bright armored sill and swept brow.
loft('29 cockpit armored foundation','trim',[(-9,3.7,7,4.3),(-3,4.3,8,4.5),(8,3,6.7,3.2),(14,1.6,4.8,2.7)],bevel=.2)
loft('30 graphite faceted cockpit canopy','dark',[(-7,2.65,8.9,6.7),(-2,3.3,12.2,7.1),(5,2.7,10.6,6),(10,1.15,6.1,4.5)],bevel=.08)
loft('31 canopy armored central brow','base',[(-7.3,.75,9.4,8.4),(-2,.85,12.65,11.7),(4.8,.68,11.05,10.2),(10.3,.3,6.5,5.8)],bevel=.07)
loft('32 dorsal armored backbone','base',[(-22,2.6,7.3,3.8),(-13,2.9,9.8,5),(-7,2.7,9.7,6),(-3,1.6,8.3,6)],bevel=.22)
loft('33 short swept spine crest','trim',[(-21,.55,9,7),(-15,.65,14,8.5),(-10,.5,11.5,8.3)],bevel=.08)
loft('34 upper nose armored spear cap','base',[(9,3.4,5.1,2.3),(21,2.6,3.7,1.1),(35,.35,.95,-.5)],bevel=.12)
loft('35 nose central inset sensor bed','dark',[(19,.8,3.85,3.4),(28,.6,2.38,2.1),(31,.35,1.87,1.65)])
box('36 tiny nose optical sensor','cool',(0,2.89,26),(.45,.13,.7))

# Fit the entire evaluated assembly, never independently distort individual parts.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get(); points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices); ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]; hi=[max(p[i] for p in points) for i in range(3)]
NOMINAL=((-31.25,31.25),(-3.24,14),(-28.996,35))
limits=tuple((low+.0012,high-.0012) for low,high in NOMINAL)
root=bpy.data.objects.new('TALON INTERCEPTOR — one representative craft — editable prototype',None)
bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
for i,(low,high) in enumerate(limits):
    root.scale[i]=(high-low)/(hi[i]-lo[i])
    root.location[i]=(low+high-(lo[i]+hi[i])*root.scale[i])/2


def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(85,83,113)); cam=bpy.context.object; cam.name='Talon review bow three-quarter'
cam.data.type='ORTHO'; cam.data.ortho_scale=91; aim(cam,(0,3,0)); bpy.context.scene.camera=cam
for name,loc,power,size in [('Key',(25,90,65),160000,65),('Fill',(-70,40,20),110000,50),('Rim',(20,60,-80),140000,45)]:
    bpy.ops.object.light_add(type='AREA',location=loc); o=bpy.context.object; o.name=name; o.data.energy=power; o.data.size=size; aim(o,(0,3,0))
scene=bpy.context.scene; scene.world=bpy.data.worlds.new('Dark navy authoring world'); scene.world.color=(.045,.045,.045)
scene.render.engine='CYCLES'; scene.cycles.samples=24
scene.render.resolution_x=1400; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
scene['asset_status']='UNAPPROVED original local prototype; script authoritative; one craft represents squadron'
bpy.ops.object.select_all(action='DESELECT'); root.select_set(True); bpy.context.view_layer.objects.active=root
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
verts=[]; indices={}; batches={r:[] for r in ROLES}; parts=[]; skipped=0
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles(); local=[]
    for v in m.vertices:
        q=tuple(round(struct.unpack('f',struct.pack('f',float(c)))[0],7) for c in ev.matrix_world@v.co)
        if q not in indices: indices[q]=len(verts); verts.append(list(q))
        local.append(indices[q])
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
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/fighter',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward','vertices':verts,
      'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
payload=json.dumps(data,separators=(',',':'))+'\n'
print('TALON_GEOMETRY '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}),flush=True)
assert total<=6000 and len(verts)<=9500,(total,len(verts))
assert len(payload.encode())<=2000000
assert all(batches[r] for r in ROLES)
for i,(low,high) in enumerate(NOMINAL):
    assert low+.001<=bounds[0][i]<bounds[1][i]<=high-.001,bounds
    assert abs(bounds[0][i]-low)<.01 and abs(bounds[1][i]-high)<.01,bounds
assert skipped==0,skipped
MASTER.parent.mkdir(parents=True,exist_ok=True); EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER)); EXPORT.write_text(payload)
print('MASTER '+str(MASTER),flush=True); print('MESH '+str(EXPORT),flush=True)
