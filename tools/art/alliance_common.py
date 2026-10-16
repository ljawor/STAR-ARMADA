"""Shared editable Blender primitives and deterministic evaluated export for escort/yard."""
from pathlib import Path
import json
import math
import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
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



def export(identifier, design, features=None):
    BLEND = ROOT / f'art/blender/{identifier}.blend'
    EXPORT = ROOT / f'assets/models/{identifier}.mesh.json'
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    EXPORT.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene['asset'] = identifier
    bpy.context.scene['design'] = design
    bpy.context.scene['coordinates'] = 'X beam; Y up; +Z forward; nominal game model units'
    bpy.context.scene['runtime'] = 'immutable evaluated triangles; no runtime Blender'
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
    asset=dict(schema=1,asset=identifier,authoring='Blender evaluated bevel mesh',
               coordinates='X beam; Y up; +Z forward',vertices=vertices,batches=batches,
               bounds=[lo,hi],parts=parts,triangle_count=sum(map(len,batches.values())))
    # Authoring ceiling for a gameplay mesh. The hard limit is the runtime loader
    # (render/authored_mesh.py: MAX_TRIANGLES 12,000, MAX_VERTICES 10,000, 2,000,000 bytes);
    # a model over it is refused at load, so the build is wasted. The ceiling is a guard,
    # not a target, and it sits deliberately just under the loader. Raised from 9,000, and a
    # vertex ceiling added, by decision s07-detail-budget-2026-10-16 (art/manifests/
    # pipeline_policy.json): surface detail costs 12 triangles and 8 vertices per block, so
    # the old ceiling gave the shipyard roughly a quarter of the capital's detail.
    assert 1800 < asset['triangle_count'] < 11888, asset['triangle_count']
    assert len(asset['vertices']) < 9500, len(asset['vertices'])
    asset['features'] = features or {}
    EXPORT.write_text(json.dumps(asset,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
    print('GAME_EXPORT',json.dumps(dict(asset=identifier,vertices=len(vertices),triangles=asset['triangle_count'],bounds=asset['bounds'],roles={k:len(v) for k,v in batches.items()},blend=str(BLEND),mesh=str(EXPORT))))
