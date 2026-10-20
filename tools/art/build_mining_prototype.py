#!/usr/bin/env python3
"""Original industrial ore refinery/extractor. Script-authoritative local prototype.
Only this builder's editable blend and mesh are outputs; no shared builder imports.
Blender --background --python-exit-code 1 --python this_file
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
MASTER=ROOT/'art/blender/imperium_mining_prototype.blend'
EXPORT=ROOT/'visual_packs/imperium-mining-prototype/assets/models/mining.mesh.json'
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

def mesh(name,role,verts,faces,bevel=0):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    o=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(o)
    o['role']=role; data.materials.append(MATS[role])
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    if bevel:
        mod=o.modifiers.new('Broad manufactured armor chamfer','BEVEL'); mod.width=bevel; mod.segments=1
    return o

FACES=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)]
def box(name,role,loc,size,bevel=0):
    x,y,z=loc; a,b,c=[v/2 for v in size]
    verts=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    return mesh(name,role,verts,FACES,bevel)

def tier(name,role,levels,loc=(0,0),bevel=0):
    verts=[]
    for y,w,d,c in levels:
        verts.extend((x+loc[0],y,z+loc[1]) for x,z in ((-w+c,-d),(w-c,-d),(w,-d+c),(w,d-c),(w-c,d),(-w+c,d),(-w,d-c),(-w,-d+c)))
    faces=[tuple(reversed(range(8))),tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(levels)-1):
        for j in range(8): faces.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,verts,faces,bevel)

def beam(name,role,a,b,width,depth=None):
    a=Vector(a); b=Vector(b); direction=(b-a).normalized()
    side=direction.cross(Vector((0,1,0)))
    if side.length<.01: side=direction.cross(Vector((1,0,0)))
    side.normalize(); up=direction.cross(side).normalized()
    verts=[tuple(pt+side*s*width/2+up*t*(depth or width)/2) for pt in (a,b) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return mesh(name,role,verts,FACES)

def tube(name,role,a,b,r,n=12):
    a=Vector(a); b=Vector(b); dr=(b-a).normalized()
    side=dr.cross(Vector((0,1,0)))
    if side.length<.01: side=dr.cross(Vector((1,0,0)))
    side.normalize(); up=dr.cross(side).normalized()
    verts=[tuple(pt+r*(side*math.cos(j*2*math.pi/n)+up*math.sin(j*2*math.pi/n))) for pt in (a,b) for j in range(n)]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,verts,faces)

def vessel(name,role,x,z,levels,n=16):
    verts=[(x+r*math.cos(j*2*math.pi/n),y,z+r*math.sin(j*2*math.pi/n)) for y,r in levels for j in range(n)]
    faces=[tuple(reversed(range(n))),tuple(range(len(verts)-n,len(verts)))]
    for k in range(len(levels)-1):
        for j in range(n): faces.append((k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j))
    return mesh(name,role,verts,faces)

def collar(name,role,x,z,y,r,inside,height,n=16):
    verts=[(x+rad*math.cos(j*2*math.pi/n),yy,z+rad*math.sin(j*2*math.pi/n)) for yy in (y-height/2,y+height/2) for rad in (r,inside) for j in range(n)]
    faces=[]
    for j in range(n):
        k=(j+1)%n
        faces.extend(((j,k,2*n+k,2*n+j),(n+j,3*n+j,3*n+k,n+k),(j,n+j,n+k,k),(2*n+j,2*n+k,3*n+k,3*n+j)))
    return mesh(name,role,verts,faces)

# A stout offset refinery, not a symmetric command fortress or a ringed dock.
tier('01 refinery pressure spine','dark',[(-17,15,14,4),(-9,20,17,5),(14,20,17,5),(23,15,13,4)],loc=(-3,-1),bevel=.45)
tier('02 lower armored crusher transfer box','base',[(-23,12,12,3),(-17,17.5,15.5,4),(-8,18.5,16,4)],loc=(-3,0),bevel=.65)
tier('03 main sloping ore processing head','base',[(3,20,16,5),(18,20,16,5),(25,16,13,4)],loc=(-5,-2),bevel=.75)
tier('04 broad overhung processing brow','trim',[(22.5,18,14,4),(25,18,14,4),(27,15.5,12,3)],loc=(-5,-2),bevel=.3)
box('05 front deep vertical service bay','dark',(-5,7,14.35),(25,12,.7))
for x in (-15,-5,5):
    box('06 armored face segmented machinery shield','base',(x,8,15.15),(8.3,9,1.6),.4)
    box('07 face removable armor inset','trim',(x,8,16.02),(5.4,5,.3))
    box('08 functional short identification mark','accent',(x,11.1,16.12),(4,.65,.2))
    for s in (-1,1):
        box('09 face fastener','dark',(x+s*3,5,16.04),(.6,.6,.24))
# Raised asymmetric operations house: warm windows outside the actual visor planes.
tier('10 raised port operations armored cabin','base',[(25,8,7,2),(34,7,6,1.8)],loc=(-12,-3),bevel=.4)
box('11 observation visor graphite band','dark',(-12,32.6,3.1),(12.6,2.4,.8))
box('12 flying operations armored visor','trim',(-12,34.6,-2),(16,1.5,13.6),.3)
for x in (-16.8,-14.4,-12,-9.6,-7.2):
    box('13 warm narrow operations window','lit',(x,32.65,3.56),(1.6,.7,.18))
for z in (-6.4,-3.8,-1.2):
    box('14 warm side operations window','lit',(-19.05,32.1,z),(.18,.65,1.5))
box('15 operations roof armored pedestal','dark',(-14,36,-3),(3,1.5,3))
box('16 operations short heavy mast','trim',(-14,38.8,-3),(.65,4.4,.8))
box('17 tiny cyan survey instrument','cool',(-14,40.85,-2.95),(.9,.3,1))
box('18 cabin rear roof equipment','base',(-10,35.8,-6),(4,1.3,3),.15)
# Open ribbed receiving hopper protrudes forward, with actual cavity not a solid cap.
hopper=[(-13,-7,15),(9,-7,15),(9,-7,27),(-13,-7,27),(-17,7,13),(13,7,13),(13,7,34),(-17,7,34)]
# Each tapered wall is independent thick armor, leaving its mouth completely open.
for j in range(4):
    k=(j+1)%4
    a,b,c,d=hopper[j],hopper[k],hopper[k+4],hopper[j+4]
    normal=(Vector(b)-Vector(a)).cross(Vector(d)-Vector(a)).normalized()*.9
    verts=[a,b,c,d]+[tuple(Vector(v)+normal) for v in (a,b,c,d)]
    mesh('19 tapered open ore hopper wall','base',verts,FACES,.16)
box('20 deep ore hopper bed','dark',(-2,-6.6,21),(20,.8,10))
for x in (-15,11):
    beam('21 hopper heavy mouth rim','trim',(x,7,14),(x,7,33),1.4)
for z in (14,33):
    beam('22 hopper transverse mouth rim','trim',(-15,7,z),(11,7,z),1.4)
for j in range(7):
    z=15+j*2.7
    for x,s in ((-1,-1),(-1,1)):
        beam('23 hopper exterior structural rib','dark',(x+s*10,-6,z),(x+s*14.4,6.8,z),.85)
for j in range(6):
    box('24 hopper bed crusher grate','trim',(-10+j*3.3,-5.95,21),(.6,.35,10))
# Separated process vessels to starboard/rear. Visible gaps separate tanks and head.
for idx,(x,z,y,r,h) in enumerate(((22,-8,-3,6,32),(11,-20,0,4.8,28),(-3,-21,-2,4.2,22))):
    vessel('25 independent ore separation pressure vessel','base',x,z,[(y-h/2,2),(y-h/2+3,r),(y+h/2-3,r),(y+h/2,r*.65)],16)
    for yy in (y-h/2+4,y+h/2-4):
        vessel('26 pressure vessel broad coupling band','trim',x,z,[(yy-.65,r+.4),(yy+.65,r+.4)],16)
    vessel('27 vessel dark end machinery','dark',x,z,[(y+h/2,r*.5),(y+h/2+2,r*.5)],12)
    for s in (-1,1):
        beam('28 vessel load-bearing standoff','dark',(x+s*r*.65,y-h/2+4,z),(x+s*r*.65,-22,z),1.1)
    tube('29 vessel cross-transfer line','dark',(x,y+4,z),(x-6,y+4,z),1.0)
    for j in range(4):
        box('30 vessel front segmented pressure strap','dark',(x-2.7+j*1.8,y,z+r+.2),(.5,h*.56,.4))
    box('31 vessel inspection tag','accent',(x,y+5,z+r+.45),(2.2,2,.18))
# Large low rear thermal bank and left shoulder fins: broad silhouettes, cheap slats.
box('32 rear exchanger graphite manifold','dark',(-9,2,-23.5),(26,22,4),.3)
for j in range(12):
    x=-22+j*2.3
    box('33 rear deep vertical heat dissipation fin','base',(x,2,-26.0),(1.05,24,4.0))
    box('34 rear fin exposed bright edge','trim',(x,2,-28.05),(.65,20,.25))
box('35 port radiator thermal spine','dark',(-26,4,0),(4,25,23),.3)
for j in range(10):
    z=-10+j*2.45
    box('36 port broad radiator panel','base',(-31,3,z),(12,23,.9))
    box('37 radiator armored distal cap','trim',(-36.6,3,z),(1.3,19,1.05))
for y in (-7,14):
    box('38 radiator massive upper lower rail','dark',(-31,y,1),(14,1.2,25))
# Offset ore loading platform, solid useful deck plus exposed under-deck truss.
box('39 starboard conveyor trunk','dark',(24,-10,15),(28,7,9),.4)
box('40 offset cargo transfer armored deck','base',(30,-5.8,15),(18,2.2,16),.45)
box('41 inset loading pad','dark',(30,-4.55,15),(14,.35,12))
for x in (23,37):
    box('42 loading platform exposed rim','trim',(x,-4.2,15),(.8,.65,15))
    for z in (9,21):
        beam('43 docking capture bollard','base',(x,-4,z),(x,-1.8,z),.8)
for j in range(7):
    box('44 ore conveyor broad cross cleat','trim',(22+j*2,-4.25,15),(.5,.25,9))
for z in (10,20):
    beam('45 cargo arm underside diagonal brace','base',(10,-20,z),(37,-8,z),1.6)
    for j in range(4):
        beam('46 cargo open truss diagonal','trim',(14+j*5,-13,z),(18+j*5,-7,z),.8)
box('47 loading exposed warm worklight','lit',(38,-5,15),(.22,.7,5))
box('48 platform sparse ownership stripe','accent',(31,-4.05,22.7),(7,.2,.55))
# Massive articulated hanging intake: space between the machinery is deliberate.
vessel('49 central crusher power column','dark',-3,0,[(-41,6),(-35,8),(-24,8),(-19,10)],16)
for yy,r in ((-23,9.5),(-29,8.7),(-37,7.2)):
    collar('50 crusher heavy annular gearbox coupling','trim',-3,0,yy,r,r-1.2,1.6)
# Three independently braced jaw arms, a segmented rock-breaker rather than a toy screw.
for idx,ang in enumerate((0,2*math.pi/3,4*math.pi/3)):
    ux,uz=math.cos(ang),math.sin(ang)
    def radial(r,y): return (-3+ux*r,y,uz*r)
    beam('51 intake articulated suspension yoke','base',radial(15,-16),radial(15,-32),4.2,5)
    tube('52 intake exposed hinge barrel','trim',(-3+ux*15-uz*2.8,-31,uz*15+ux*2.8),(-3+ux*15+uz*2.8,-31,uz*15-ux*2.8),2.0,12)
    beam('53 intake diagonal crusher jaw housing','base',radial(15,-32),radial(9,-49),5,5.7)
    beam('54 intake replaceable breaking tooth','trim',radial(9,-46),radial(6.7,-53.8),3.4,3.8)
    beam('55 articulated exposed hydraulic barrel','dark',radial(19,-23),radial(15,-38),1.8)
    beam('56 hydraulic polished ram','trim',radial(15,-38),radial(12,-44),.9)
    for y in (-22,-27):
        beam('57 actuator protective shoulder hoop','trim',radial(14,y),radial(18,y),1.2,5.5)
    # Exterior linear guarded ribs, not bevelled individual small fittings.
    for j in range(4):
        rr=15-j*.9; yy=-34-j*3
        tangent=Vector((-uz,0,ux))*2.7; pt=Vector(radial(rr,yy))
        beam('58 jaw transverse wear ridge','dark',tuple(pt-tangent),tuple(pt+tangent),.7,1.2)
# Central faceted rock breaker stays recessed behind the three claw teeth.
vessel('59 central multi-stage rock breaker','base',-3,0,[(-48,2.3),(-44,5),(-41,6.4),(-38,6.4)],12)
for j in range(8):
    a=j*math.pi/4
    beam('60 central non-spiral cutting bit','trim',(-3+4.8*math.cos(a),-43,4.8*math.sin(a)),(-3+2.7*math.cos(a),-48.5,2.7*math.sin(a)),1.5)
# Exposed heavy transfer pipes and guarded couplings across the upper shoulders.
for idx,(z,x) in enumerate(((-11,-21),(-6,15),(6,15))):
    path=[(x,-12,z),(x,16,z),(x-3,20,z),(-6,20,z)]
    for j,(a,b) in enumerate(zip(path,path[1:])):
        tube('61 large transfer pipe segment','dark',a,b,1.35,12)
    for yy in (-9,-1,9,15):
        vessel('62 heavy pipe ring coupling','trim',x,z,[(yy-.55,1.8),(yy+.55,1.8)],12)
    box('63 armored pipe support block','base',(x,4,z),(4.2,3,4.2),.2)
# Process head roof: three grouped louvre cassettes, larger armor fields, service fittings.
for z in (-10,-3,4):
    box('64 roof recessed thermal cassette','dark',(0,26.8,z),(8,.8,5.5))
    for j in range(6):
        box('65 roof thermal louvre','trim',(-3+j*1.2,27.35,z),(.42,.4,4.5))
for x in (-22,12):
    box('66 refinery flank service void','dark',(x,10,-1),(.7,9,10))
    for j in range(7):
        box('67 flank vent slat','trim',(x+(-.45 if x<0 else .45),10,-5+j*1.3),(.35,7,.5))
for s in (-1,1):
    box('68 lower head structural armored rail','trim',(-3+s*15,-14,7),(2,9,15),.18)
    box('69 lower head worklight housing','dark',(-3+s*13,-16,15.8),(4,2,1))
    box('70 exposed downward worklight','lit',(-3+s*13,-16.6,16.4),(2.7,.45,.25))
    box('71 process head identification strip','accent',(-5+s*14,19,10),(.7,4,1))
# Three exposed feed cyclones under the hopper: readable separated process units,
# with a stepped pressure casting and open annular clamps rather than extra slats.
for x in (-12,-3,6):
    vessel('72 under-hopper dense media feed cyclone','base',x,21,
           [(-24,1.1),(-21,1.1),(-18,2.6),(-12,2.6),(-10,3.1),(-8.7,3.1),(-8,2.3)],12)
    for yy in (-11,-17):
        collar('73 cyclone exposed annular pressure clamp','trim',x,21,yy,3.05,2.55,.85,16)
    tube('74 cyclone horizontal outlet branch','dark',(x,-20,21),(x,-20,15),1.0,12)
    box('75 cyclone mounting saddle','dark',(x,-10,17.5),(4,5,1.6))
    tube('76 cyclone valve spindle','trim',(x,-13,23),(x,-13,25.3),.38,8)
    tube('77 cyclone valve actuator barrel','dark',(x,-13,25),(x,-13,26.4),1.0,12)
    box('78 cyclone small actuator cap','accent',(x,-13,26.5),(1.5,1.5,.25))
# Evaluate COMPLETE assembly then fit independently per axis/per side, 0.001 inward.
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get(); points=[]
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); points.extend(tuple(ev.matrix_world@v.co) for v in m.vertices); ev.to_mesh_clear()
lo=[min(p[i] for p in points) for i in range(3)]; hi=[max(p[i] for p in points) for i in range(3)]
# Extra 0.00002 absorbs float32 endpoint rounding while retaining >=0.001 margin.
limits=((-38.99898,38.99898),(-53.99898,40.99898),(-27.99898,35.50598))
root=bpy.data.objects.new('IMPERIUM ORE REFINERY — complete editable industrial assembly',None); bpy.context.collection.objects.link(root)
for o in objects: o.parent=root
for i,(low,high) in enumerate(limits):
    root.scale[i]=(high-low)/(hi[i]-lo[i]); root.location[i]=(low+high-(lo[i]+hi[i])*root.scale[i])/2
# Authoring camera and review lights only; no beauty render or game capture here.
def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(138,94,155)); cam=bpy.context.object; cam.name='Ore refinery review three-quarter'
cam.data.type='ORTHO'; cam.data.ortho_scale=137; aim(cam,(0,-6,2)); bpy.context.scene.camera=cam
for name,loc,power,size in [('Key',(20,140,100),230000,90),('Fill',(-120,45,40),170000,80),('Rim',(40,45,-120),190000,70)]:
    bpy.ops.object.light_add(type='AREA',location=loc); o=bpy.context.object; o.name=name; o.data.energy=power; o.data.size=size; aim(o,(0,-6,2))
scene=bpy.context.scene; scene.world=bpy.data.worlds.new('Dark neutral authoring world'); scene.world.color=(.045,.045,.045)
scene.render.engine='CYCLES'; scene.cycles.samples=24
scene.render.resolution_x=1400; scene.render.resolution_y=1200; scene.render.resolution_percentage=100
scene['asset_status']='UNAPPROVED local prototype; standalone mining builder authoritative'
bpy.ops.object.select_all(action='DESELECT'); root.select_set(True); bpy.context.view_layer.objects.active=root
bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
verts=[]; indices={}; batches={r:[] for r in ROLES}; parts=[]; skipped=0
for o in objects:
    ev=o.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles(); local=[]
    for v in m.vertices:
        # Retain exact float32 coordinates. Normals below use Python double arithmetic.
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
data={'contract':'star-armada/mesh-export','contract_major':1,'asset':'prototype:imperial/mining_station',
      'authoring':'Blender evaluated mesh','coordinates':'X beam; Y up; +Z forward','vertices':verts,
      'batches':batches,'bounds':bounds,'parts':parts,'triangle_count':total}
payload=json.dumps(data,separators=(',',':'))+'\n'
print('MINING_GEOMETRY '+json.dumps({'triangles':total,'vertices':len(verts),'parts':len(parts),'roles':{r:len(batches[r]) for r in ROLES},'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped}),flush=True)
assert total<=11888 and len(verts)<=9500,(total,len(verts))
assert len(payload.encode())<=2000000
for i,(low,high) in enumerate(((-39,39),(-54,41),(-28,35.507))):
    assert low+.001<=bounds[0][i]<bounds[1][i]<=high-.001,bounds
    assert abs(bounds[0][i]-low)<.01 and abs(bounds[1][i]-high)<.01,bounds
assert all(batches[r] for r in ROLES)
MASTER.parent.mkdir(parents=True,exist_ok=True); EXPORT.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(MASTER)); EXPORT.write_text(payload)
print('MASTER '+str(MASTER),flush=True); print('MESH '+str(EXPORT),flush=True)
