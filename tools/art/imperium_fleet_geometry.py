"""Blender-only geometry for the remaining Imperium fleet; no approved helper imports.

World coordinates are X-beam/Y-up/+Z-forward. Material roles are the existing six
runtime roles, not a new shader or an offline-only material trick.
"""
import json
import math
import struct
from pathlib import Path
import bpy
import bmesh

ROLES=('base','dark','trim','accent','lit','cool')
COLORS={'base':(.32,.36,.40,1),'dark':(.065,.085,.11,1),
        'trim':(.56,.60,.63,1),'accent':(.65,.16,.055,1),
        'lit':(1,.65,.23,1),'cool':(.10,.78,1,1)}
MATS={}


def initialize():
    global MATS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    MATS={}
    for role in ROLES:
        material=bpy.data.materials.new(role)
        material.diffuse_color=COLORS[role]
        MATS[role]=material


def mesh(name,role,verts,faces,bevel=0.0):
    if role not in ROLES:raise ValueError(role)
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    obj['role']=role;data.materials.append(MATS[role])
    bm=bmesh.new();bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(data);bm.free()
    if bevel:
        mod=obj.modifiers.new('Broad armor chamfer','BEVEL');mod.width=bevel;mod.segments=1
    return obj


def loft(name,role,stations,x=0.0,bevel=0.0):
    verts=[]
    for z,w,t,b in stations:
        c=min((t-b)*.24,w*.3)
        verts.extend([(x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),(x+w,b+c,z),
                      (x+w-c,b,z),(x-w+c,b,z),(x-w,b+c,z),(x-w,t-c,z)])
    faces=[tuple(reversed(range(8))),tuple(range(len(verts)-8,len(verts)))]
    for k in range(len(stations)-1):
        for j in range(8):faces.append((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j))
    return mesh(name,role,verts,faces,bevel)


def box(name,role,loc,size,bevel=0.0):
    x,y,z=loc;a,b,c=(s/2 for s in size)
    vv=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in
        ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    return mesh(name,role,vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)],bevel)


def ring(name,role,x,y,stations,n=12):
    vv=[];ff=[]
    for z,outer,inner in stations:
        if not 0<inner<outer:raise ValueError('Ring must have an open bore')
        for r in (outer,inner):
            vv.extend((x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
    for k in range(len(stations)-1):
        for wall in (0,1):
            a=k*2*n+wall*n;b=(k+1)*2*n+wall*n
            ff.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
    for k in (0,len(stations)-1):
        a=k*2*n
        ff.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
    return mesh(name,role,vv,ff)


def disc(name,role,x,y,z,r,depth,n=12):
    vv=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+d*depth/2)
        for d in (-1,1) for j in range(n)]
    ff=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    ff.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    return mesh(name,role,vv,ff)


def export(root,kind,stem,limits,*,replace_own=False):
    """Quantize first, recompute normals, then save only this new model's paths."""
    root=Path(root)
    master=root/f'art/blender/imperium_{stem}_prototype.blend'
    target=root/f'visual_packs/imperium-fleet-prototypes/assets/models/{stem}.mesh.json'
    if not replace_own and (master.exists() or target.exists()):
        raise FileExistsError(f'Refusing existing fleet outputs: {master}, {target}')
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    verts=[];indices={};batches={r:[] for r in ROLES};parts=[];skipped=0
    objects=sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name)
    for obj in objects:
        role=obj['role'];ev=obj.evaluated_get(dg);data=ev.to_mesh();data.calc_loop_triangles();local=[]
        try:
            for vertex in data.vertices:
                q=tuple(round(struct.unpack('f',struct.pack('f',float(c)))[0],7) for c in ev.matrix_world@vertex.co)
                if q not in indices:indices[q]=len(verts);verts.append(list(q))
                local.append(indices[q])
            first=len(batches[role])
            for face in data.loop_triangles:
                ids=[local[k] for k in face.vertices];a,b,c=(verts[k] for k in ids)
                u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
                normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                area=math.sqrt(sum(c*c for c in normal))
                if area<=1e-9:skipped+=1;continue
                batches[role].append([round(c/area,15) for c in normal]+ids)
            parts.append({'name':obj.name,'role':role,'triangles':len(batches[role])-first,
                          'first_triangle':first})
        finally:ev.to_mesh_clear()
    bounds=[[min(v[i] for v in verts) for i in range(3)],
            [max(v[i] for v in verts) for i in range(3)]]
    total=sum(len(v) for v in batches.values())
    data={'contract':'star-armada/mesh-export','contract_major':1,
          'asset':'prototype:imperial/'+kind,'authoring':'Blender evaluated mesh',
          'coordinates':'X beam; Y up; +Z forward','vertices':verts,'batches':batches,
          'bounds':bounds,'parts':parts,'triangle_count':total}
    payload=json.dumps(data,separators=(',',':'))+'\n'
    report={'kind':kind,'triangles':total,'vertices':len(verts),'parts':len(parts),
            'bounds':bounds,'bytes':len(payload.encode()),'degenerate_skipped':skipped,
            'roles':{r:len(batches[r]) for r in ROLES}}
    print('FLEET_GEOMETRY '+json.dumps(report),flush=True)
    assert all(batches.values()) and 1800<total<=(6000 if kind=='bomber' else 11888)
    assert len(verts)<9500 and len(payload.encode())<2000000
    assert skipped==0,skipped
    for i,(low,high) in enumerate(limits):
        assert low<=bounds[0][i]<bounds[1][i]<=high,(kind,i,limits,bounds)
        assert abs((bounds[1][i]-bounds[0][i])/(high-low)-1)<.01,(kind,i,'footprint drift',bounds)
    master.parent.mkdir(parents=True,exist_ok=True);target.parent.mkdir(parents=True,exist_ok=True)
    bpy.context.scene['asset_status']='Pending owner appearance review; original remaining Imperium fleet'
    bpy.context.scene['source_authority']='tools/art/build_imperium_fleet.py and dedicated design modules'
    bpy.ops.wm.save_as_mainfile(filepath=str(master));target.write_text(payload,encoding='utf-8')
    return report
