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



def _world_box(obj):
    """One part's world-space box, from its own vertices; a bevel adds a hair, not a gap."""
    corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return (tuple(min(c[i] for c in corners) for i in range(3)),
            tuple(max(c[i] for c in corners) for i in range(3)))


def _box_gap(a, b):  # noqa: D401
    """How far apart two boxes are; negative as soon as they overlap on every axis."""
    return max(max(a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3))


def weld_scene(tolerance=.25, role='trim', grow_max=2.5, min_half=.3, max_half=.9,
               overlap=.05, max_members=90, max_brace=10.0):
    """Weld every part of the scene into one piece, so nothing floats in space.

    A kit is authored part by part, by centre and by reach, and nothing in that process
    guarantees contact. Without this pass the S06 batch shipped a sensor-station dish 23.75
    units clear of its body - 120 px of daylight in its own capture - and a marker-light ring
    1.4 units above the deck on all nine stations. `tolerance` is the largest daylight a part
    may stand from its neighbour and still count as fitted.

    A gap of at most `grow_max` is closed by growing the part: the face that looks at its
    neighbour is pushed out until the two overlap, which thickens a panel onto the hull it was
    always meant to sit on. A larger gap is closed with a member run between the two nearest
 centres, because thickening a part by many times its own size is a different shape rather
 than a fit - a sensor dish 2 units off its mast wants a short bracket, not a fatter dish.
 A pair of parts whose centres are further apart than `max_brace` is a *design* fault, not a
 fitting one: the first cut of this pass braced `legion_sensor_station`'s forward dish, which
 had been authored at the station's origin while its mast sits 31 units forward, with three
 long booms that read in the capture as an extra grey panel welded across the hull. Scaffold
 is not a weld, so that case now refuses with the pair named, and the part gets placed where
 it belongs instead. `max_brace` is 10 units of *clear space* - about a ninth of the smallest
 of these stations - so a bracket across a small fit is fine and a hole you could see is not.
 Either way
    the asset's extent is kept, because the face that moves is the one facing the neighbour,
    never the one that set the envelope - so the build's extent self-check stays a check on the
    design rather than on this pass. Every joint is reported; the caller asserts the count, so
    a silent no-op cannot pass for a weld.
    """
    parts = {o.name: _world_box(o) for o in bpy.context.scene.objects
             if o.type == 'MESH' and o.data.vertices}
    order = sorted(parts)
    group = {name: name for name in order}

    def find(name):
        while group[name] != name:
            group[name] = group[group[name]]
            name = group[name]
        return name

    def join(names):
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if _box_gap(parts[a], parts[b]) <= tolerance:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        group[ra] = rb

    def clusters():
        out = {}
        for name in list(parts):
            out.setdefault(find(name), []).append(name)
        return out

    join(list(parts))
    joints = []
    while len(clusters()) > 1 and len(joints) < max_members:
        groups = clusters()
        body = max(groups.values(), key=len)
        fixed = False
        for names in (g for g in groups.values() if g is not body):
            _, x, y = min((_box_gap(parts[a], parts[b]), a, b) for a in names for b in body)
            bx, by = parts[x], parts[y]
            axes = [i for i in range(3) if bx[0][i] > by[1][i] or by[0][i] > bx[1][i]]
            if axes and _box_gap(bx, by) <= grow_max:
                obj = bpy.context.scene.objects[x]
                inverse = obj.matrix_world.inverted()
                limit = {i: ((by[0][i] + overlap) if bx[1][i] < by[0][i] else (by[1][i] - overlap))
                         for i in axes}
                moved = 0
                for vert in obj.data.vertices:
                    point = obj.matrix_world @ vert.co
                    # Only the axes this vertex actually sits on move: pushing a whole vertex on
                    # an axis it does not lie on drags that cross-section out to the host's face
                    # and resizes the part (measured: it took 0.045 off the carrier's Y extent).
                    facing = [i for i in axes
                              if abs(point[i] - (bx[1][i] if bx[1][i] < by[0][i] else bx[0][i]))
                              < 1e-6]
                    if facing:
                        point = [limit[i] if i in facing else point[i] for i in range(3)]
                        vert.co = inverse @ Vector(point)
                        moved += 1
                obj.data.update()
                parts[x] = _world_box(obj)
                joints.append((round(_box_gap(bx, by), 2), x, y, f'grew {moved} verts'))
            else:
                gap = _box_gap(bx, by)
                if gap > max_brace:
                    raise RuntimeError(
                        f'{x} and {y} are one cluster with {gap:.2f} units of clear space '
                        f'between them. A brace that long is scaffold, not a weld: place one of '
                        f'them so it touches, or raise max_brace deliberately.')
                smaller = min(bx, by, key=lambda box: min(box[1][i] - box[0][i] for i in range(3)))
                half = min(max(.35 * min(smaller[1][i] - smaller[0][i] for i in range(3)),
                               min_half), max_half)
                # The member spans the *gap*, from one part's facing face to the other's, never
                # from centre to centre: two long parts that almost touch would otherwise get a
                # member as long as the parts themselves, which is how the first cut of this pass
                # drew three booms across legion_sensor_station that read as an added hull panel.
                lo, hi = [], []
                for i in range(3):
                    if bx[1][i] < by[0][i]:
                        lo.append(bx[1][i] - overlap)
                        hi.append(by[0][i] + overlap)
                    elif by[1][i] < bx[0][i]:
                        lo.append(by[1][i] - overlap)
                        hi.append(bx[0][i] + overlap)
                    else:
                        mid = (max(bx[0][i], by[0][i]) + min(bx[1][i], by[1][i])) / 2
                        lo.append(mid - half)
                        hi.append(mid + half)
                verts = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]),
                         (lo[0], hi[1], lo[2]), (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]),
                         (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
                faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2),
                         (2, 6, 7, 3), (3, 7, 4, 0)]
                member = mesh_object(f'95 Weld {len(joints) + 1}', role, verts, faces, 0)
                parts[member.name] = (tuple(lo), tuple(hi))
                group[member.name] = member.name
                joints.append((round(_box_gap(bx, by), 2), x, y, f'braced with {member.name}'))
            join(list(parts))
            fixed = True
        if not fixed:
            break
    for gap, x, y, how in joints:
        print(f'WELD {x} ({gap} clear) -> {y}: {how}')
    left = len(clusters())
    print(f'WELD_TOTAL joints={len(joints)} tolerance={tolerance} clusters_left={left}')
    assert left == 1, f'{left} clusters still floating; raise max_members'
    return joints



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
