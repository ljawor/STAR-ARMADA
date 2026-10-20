#!/usr/bin/env python3
"""Script-authoritative original Vigil gun-corvette. Local UNAPPROVED prototype.
Run with Blender --background --python-exit-code 1 --python this_file --
--output-root REPO. Only the editable master and six-role JSON are written.
No shared authoring helper or approved source is imported or changed.
"""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector

ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
COLORS = {'base':(.32,.36,.40,1), 'dark':(.065,.085,.11,1),
          'trim':(.56,.60,.63,1), 'accent':(.65,.16,.055,1),
          'lit':(1,.65,.23,1), 'cool':(.10,.78,1,1)}
parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parents[2])
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
ROOT = args.output_root.resolve()
MASTER = ROOT/'art/blender/vigil_prototype.blend'
EXPORT = ROOT/'visual_packs/vigil-prototype/assets/models/vigil.mesh.json'
# A fresh self-contained scene; no imported helper can delete shared authoring data.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
MATS = {}
for role in ROLES:
    m = bpy.data.materials.new(role)
    m.diffuse_color = COLORS[role]
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = COLORS[role]
    p.inputs['Metallic'].default_value = .5
    p.inputs['Roughness'].default_value = .37
    if role in ('lit','cool'):
        p.inputs['Emission Color'].default_value = COLORS[role]
        p.inputs['Emission Strength'].default_value = 2.2
    MATS[role] = m


def finish(obj, name, role, bevel=0.0):
    obj.name = name
    obj['role'] = role
    obj.data.materials.append(MATS[role])
    # Recalculate connected closed components, including inward engine throat walls.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    if bevel:
        mod = obj.modifiers.new('Broad manufactured edge chamfer', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.affect = 'EDGES'
    return obj


def mesh(name, role, vertices, faces, bevel=0.0):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, role, bevel)


def box(name, role, loc, size, bevel=0.0, angle=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.rotation_euler[1] = angle
    return finish(o,name,role,bevel)


def loft(name, role, stations, bevel=0.0, x=0.0):
    # (z, half beam, top, bottom), chamfered octagonal cross sections.
    verts=[]
    for z,w,t,b in stations:
        c=min((t-b)*.22,w*.22)
        verts.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),
                      (x+w,b+c,z),(x+w-c,b,z),(x-w+c,b,z),
                      (x-w,b+c,z),(x-w,t-c,z)])
    faces=[tuple(reversed(range(8))), tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(stations)-1):
        for j in range(8):
            faces.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,verts,faces,bevel)


def cyl(name,role,loc,r,depth,axis='Z',vertices=12,bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=r, depth=depth, location=loc)
    o=bpy.context.object
    if axis=='Y': o.rotation_euler[0]=math.pi/2
    return finish(o,name,role,bevel)


def ring(name,role,x,y,stations):
    # Truly hollow shell: outer and inner walls, with annular end faces.
    n=12; v=[]; f=[]
    for z,outer,inner in stations:
        for r in (outer,inner):
            v.extend((x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
    for k in range(len(stations)-1):
        for wall in (0,1):
            a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
            for j in range(n): f.append((a+j,a+(j+1)%n,b+(j+1)%n,b+j))
    for k in (0,len(stations)-1):
        a=k*2*n
        for j in range(n): f.append((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n))
    return mesh(name,role,v,f)

# Continuous dark pressure spine, not a featureless needle: broad chamfered bow.
loft('01 graphite load-bearing pressure hull','dark',[
    (-37,6.8,5.0,-3.8),(-25,9.0,6.2,-4.7),(-7,10.1,6.4,-4.9),
    (13,9.0,5.9,-3.9),(33,6.8,4.2,-2.8),(48,3.8,2.3,-1.9)],.32)
loft('02 ventral armored keel','base',[(-32,4.6,-1.8,-4.95),(-12,5.1,-2.5,-4.95),(19,4.0,-1.9,-4.2),(43,2.8,-1.2,-2.5)],.25)
# Bow consists of substantial separate armored cheeks, not one triangular slab.
for s in (-1,1):
    loft(f'03 {s} forward jaw armor','base',[(8,3.7,7.5,-1.3),(27,3.0,6.1,-1.8),(44,2.0,3.8,-1.7),(47.3,1.8,2.8,-1.5)],.35,x=s*4.0)
    loft(f'04 {s} midship shoulder block','base',[(-21,4.5,7.2,-2.5),(-6,5.0,7.8,-2.1),(9,4.0,6.6,-1.7),(17,3.0,5.8,-1.7)],.5,x=s*8.4)
    loft(f'05 {s} drive side sponson','base',[(-36.6,4.5,5.7,-2.0),(-28,5.3,6.1,-2.4),(-13,5.1,5.9,-2.0),(-5,3.9,4.3,-1.0)],.45,x=s*10.2)
    # Exposed inboard mechanical recess, visibly bounded by thick armor shoulders.
    box(f'06 {s} recessed service trench','dark',(s*7.5,7.35,-4),(2.25,.4,29),.1)
    for bank,z in enumerate((-14,-3,8)):
        box(f'07 {s} trench vent cassette {bank}','dark',(s*7.5,7.63,z),(1.8,.45,7.2))
        for j in range(5):
            box(f'08 {s} cassette {bank} louvre {j}','trim',(s*7.5,7.87,z-2.6+j*1.22),(1.5,.22,.46))
    # Grouped panels with deliberate unequal spans: large fields, narrow seams.
    for j,(z,length) in enumerate(((-23,7.5),(-12.2,10.0),(.6,10.9),(10.2,5.5))):
        box(f'09 {s} shoulder armor field {j}','trim' if j in (0,3) else 'base',
            (s*10.5,7.45 if j in (1,2) else 6.4,z),(3.1,.55,length),.16)
    box(f'10 {s} owner identification sweep','accent',(s*11.45,7.79,-10.5),(2.4,.22,12.7),.08)
    box(f'11 {s} owner short bow marking','accent',(s*4.6,6.24,26),(2.5,.2,3.0),.04)
    # Outboard lower machinery banks remain attached to the sponson side.
    for j,z in enumerate((-29,-22,-15)):
        box(f'12 {s} flank vent well {j}','dark',(s*15.25,1.9,z),(.45,3.6,5.7),.12)
        for k in range(4):
            box(f'13 {s} flank grille {j} {k}','base',(s*15.52,1.9,z-1.9+k*1.22),(.2,2.85,.36))
    # Thrust structure: the solid cap is forward of both emitter and open nozzle.
    cyl(f'14 {s} capped drive core','dark',(s*10.3,1.8,-35.3),3.7,4.1,bevel=.2)
    ring(f'15 {s} flared hollow exhaust','dark',s*10.3,1.8,[(-37.2,3.8,2.8),(-40.9,4.3,3.2),(-43.60095,4.45,3.45)])
    ring(f'16 {s} bright nozzle rim','trim',s*10.3,1.8,[(-42.7,4.49,3.45),(-43.60095,4.49,3.45)])
    cyl(f'17 {s} exposed cyan ion emitter','cool',(s*10.3,1.8,-42.25),3.35,.16)
    cyl(f'18 {s} central emitter hub','dark',(s*10.3,1.8,-42.37),.63,.18)
    for a in range(4):
        ang=a*math.pi/2
        box(f'19 {s} nozzle exterior fastener {a}','base',
            (s*10.3+4.1*math.cos(ang),1.8+4.1*math.sin(ang),-40.4),(.6,.6,2.3),.12)
    loft(f'20 {s} drive roof cowling','trim',[(-35,2.6,7.0,5.0),(-24,3.3,7.2,5.0),(-17,2.9,6.5,4.9)],.25,x=s*10.2)
    box(f'21 {s} drive owner band','accent',(s*10.2,7.35,-28.6),(5.0,.2,2.7),.06)
# Stepped command island, swept broad bases and narrow bridge visor bands.
loft('22 armored dorsal citadel','base',[(-29,5.4,9.5,4),(-23,5.7,12.8,4.8),(-9,4.2,12.8,5),(0,2.8,8.3,5)],.45)
loft('23 recessed bridge glazing surround','dark',[(-25,4.9,12.6,10),(-21,4.8,14.2,10.5),(-12,3.8,14.2,10.5),(-8.5,3.1,12.6,10)],.18)
loft('24 bridge armored floating brow','trim',[(-25.8,5.1,13.2,12.5),(-21,4.9,14.8,14.1),(-12,3.9,14.8,14.1),(-7.6,3.0,13.0,12.3)],.2)
for s in (-1,1):
    for j in range(4):
        box(f'25 {s} small bridge window {j}','lit',(s*(4.65-j*.22),13.17,-21+j*2.2),(.16,.48,1.22))
    box(f'26 {s} command side paint','accent',(s*5.6,10.1,-22),(.16,1.0,6.8))
    box(f'27 {s} rear island service plate','base',(s*3.2,13.19,-24),(2.0,.3,3.1),.09)
box('28 mast reinforced foot','dark',(0,15.0,-20),(2.5,1.6,3.5),.2)
box('29 fine non-emissive comms mast','trim',(0,19.8,-20),(.46,8.4,.65),.06)
box('30 mast horizontal aerial','dark',(0,21.3,-20),(3.4,.25,.3),.04)
box('31 tiny mast sensor','cool',(0,23.6,-20),(.60,.22,.7),.03)
box('32 rear short antenna','base',(2.7,16.2,-24),(.24,4.0,.3))
# Two functional gun turrets and two small point-defence stations.
for idx,z,y,r in ((0,18,7.0,2.9),(1,-3,8.3,2.5)):
    cyl(f'33 gun {idx} rotation race','dark',(0,y,z),r+.35,.8,'Y',16,.12)
    box(f'34 gun {idx} armored mantlet','base',(0,y+1.2,z),(r*1.8,1.9,3.8),.3)
    box(f'35 gun {idx} roof plate','trim',(0,y+2.18,z-.4),(r*1.4,.28,2.5),.08)
    for s in (-1,1):
        box(f'36 gun {idx} barrel sleeve {s}','dark',(s*.9,y+1.15,z+3.1),(.78,.8,4.2),.1)
        box(f'37 gun {idx} muzzle {s}','trim',(s*.9,y+1.15,z+5.5),(.62,.64,1.3),.08)
        box(f'38 gun {idx} bore {s}','dark',(s*.9,y+1.15,z+6.17),(.37,.36,.03))
for s in (-1,1):
    cyl(f'39 {s} PD race','dark',(s*11,7.7,-19),1.4,.6,'Y',12,.1)
    box(f'40 {s} PD head','base',(s*11,8.35,-19),(2.1,1.0,2.5),.22)
    for a in (-.4,.4):
        box(f'41 {s} PD barrel {a}','dark',(s*11+a,8.35,-17.1),(.32,.35,2.0),.05)
# Forward axial rail recess and inset armor fields follow the sloping deck.
for j,(z,y,length,width) in enumerate(((33,4.56,6.0,4.0),(40,3.66,5.0,3.3),(45,2.9,3.0,2.8))):
    box(f'42 bow axial dark bed {j}','dark',(0,y,z),(width,.18,length),.04)
    for s in (-1,1):
        box(f'43 {s} bow rail {j}','trim',(s*(width/2+.25),y+.2,z),(.52,.45,length),.09)
for s in (-1,1):
    box(f'44 {s} nose inset sensor','dark',(s*2.5,2.2,47.5),(1.1,1.0,.3),.06)
    box(f'45 {s} tiny blue rangefinder','cool',(s*2.5,2.2,47.69),(.55,.35,.08))
# Compact service furniture, grouped rather than scattered noise.
loft('46 aft machinery armored foundation','dark',[(-35,4.8,7.6,3),(-29,5.2,8.9,4),(-21,4.8,9.8,4)],.22)
for s in (-1,1):
    for j,z in enumerate((-30,-26,-22)):
        box(f'46 {s} aft heat exchanger {j}','dark',(s*3.8,8.55,z),(1.7,.9,2.2))
        for k in range(3):
            box(f'47 {s} exchanger top {j} {k}','trim',(s*3.8,9.05,z-.7+k*.7),(1.4,.16,.23))
    for j,z in enumerate((7,1,-6)):
        box(f'48 {s} trench manifold {j}','dark',(s*5.6,7.45,z),(1.25,.65,3.0),.14)
        cyl(f'49 {s} manifold cap {j}','base',(s*5.6,7.8,z),.43,.25,'Y',10,.04)
# Fit evaluated assembly inward of float32 envelope limits, never independently fit parts.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get()
points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh()
    points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices)
    ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]
hi=[max(p[i] for p in points) for i in range(3)]
limits=((-15.9999,15.9999),(-4.9999,23.9999),(-43.6009,47.9999))
root=bpy.data.objects.new('VIGIL complete editable assembly — UNAPPROVED',None)
bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
for i,(low,high) in enumerate(limits):
    scale=min(1.0,(high-low)/(hi[i]-lo[i]))
    root.scale[i]=scale
    root.location[i]=min(max(0.0,low-lo[i]*scale),high-hi[i]*scale)
# Review camera and lights are authoring conveniences, excluded from export.
def aim(obj,point): obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(110,105,140))
cam=bpy.context.object; cam.name='Review camera bow three-quarter'; aim(cam,(0,3,0))
cam.data.type='ORTHO'; cam.data.ortho_scale=112; bpy.context.scene.camera=cam
for name,loc,power,size in [('Key',(35,90,45),180000,65),('Rim',(-60,45,-40),140000,50),('Fill',(50,-15,-30),80000,40)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    o=bpy.context.object; o.name=name; o.data.energy=power; o.data.shape='DISK'; o.data.size=size; aim(o,(0,0,0))
scene=bpy.context.scene
scene.world=bpy.data.worlds.new('Deep navy authoring world'); scene.world.color=(.045,.045,.045)
scene.render.engine='CYCLES'; scene.cycles.samples=24
scene.render.resolution_x=1400; scene.render.resolution_y=1000; scene.render.resolution_percentage=100
scene['asset_status']='UNAPPROVED local visual prototype; script authoritative'
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True); bpy.context.view_layer.objects.active=root
MASTER.parent.mkdir(parents=True,exist_ok=True)
EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER))
# Export evaluated beveled triangles; calculate geometric normals after quantization
# with Python doubles, never mathutils float32 cross products.
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
verts=[]; indices={}; batches={r:[] for r in ROLES}; parts=[]; skipped=0
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles()
    local=[]
    for v in m.vertices:
        p=tuple(round(float(c),7) for c in ev.matrix_world@v.co)
        if p not in indices: indices[p]=len(verts); verts.append(list(p))
        local.append(indices[p])
    count=0; role=o['role']
    for t in m.loop_triangles:
        ids=[local[k] for k in t.vertices]
        a,b,c=(verts[k] for k in ids)
        u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(q*q for q in n))
        if length<1e-12: skipped+=1; continue
        batches[role].append([round(q/length,15) for q in n]+ids); count+=1
    parts.append({'name':o.name,'role':role,'triangles':count}); ev.to_mesh_clear()
bounds=[[min(v[i] for v in verts) for i in range(3)],[max(v[i] for v in verts) for i in range(3)]]
total=sum(len(b) for b in batches.values())
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/vigil',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward',
      'vertices':verts,'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
assert total<=11888 and len(verts)<9500,(total,len(verts))
assert bounds[1][2]-bounds[0][2]>=91.4,bounds
for i,(low,high) in enumerate(((-16,16),(-5,24),(-43.601,48))):
    assert low<=bounds[0][i]<=bounds[1][i]<=high,bounds
payload=json.dumps(data,separators=(',',':'))+'\n'
assert len(payload.encode())<2000000
EXPORT.write_text(payload)
print('VIGIL_EXPORT '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),
      'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}))
print('MASTER '+str(MASTER))
print('MESH '+str(EXPORT))
