"""Blender-only geometry for the Rim Syndicate rework; no approved helper imports.

World coordinates are X-beam / Y-up / +Z-forward, the same contract the runtime
loader and the approved Imperium batch use. Material roles are the six existing
runtime roles, so a Syndicate hull costs nothing new in the renderer.

The Syndicate reads as an *industrial* fleet: welded plate belts over a dark
pressure hull, exposed lattice outriggers, reactor drums in external cradles,
one offset command tower and a blunt salvage prow. Nothing here is a copy of a
proprietary design; the vocabulary is plate belts, drums, lattice, ram jaws and
open nozzle throats.
"""
import json
import math
import struct
from pathlib import Path

import bpy
import bmesh

ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
# Weathered steel hull, deep seams, ochre ownership band, warm interior light.
COLORS = {'base': (.30, .33, .36, 1), 'dark': (.055, .070, .085, 1),
          'trim': (.50, .47, .41, 1), 'accent': (.62, .34, .09, 1),
          'lit': (1, .62, .24, 1), 'cool': (.22, .84, .96, 1)}
MATS = {}


def initialize():
    global MATS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    MATS = {}
    for role in ROLES:
        material = bpy.data.materials.new(role)
        material.diffuse_color = COLORS[role]
        MATS[role] = material


def mesh(name, role, verts, faces, bevel=0.0):
    if role not in ROLES:
        raise ValueError(role)
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj['role'] = role
    data.materials.append(MATS[role])
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    if bevel:
        mod = obj.modifiers.new('Broad armor chamfer', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
    return obj


def loft(name, role, stations, x=0.0, bevel=0.0):
    """Eight-sided pressure hull; stations are (z, half_x, top, bottom)."""
    verts = []
    for z, w, t, b in stations:
        c = min((t - b) * .24, w * .3)
        verts.extend([(x - w + c, t, z), (x + w - c, t, z), (x + w, t - c, z),
                      (x + w, b + c, z), (x + w - c, b, z), (x - w + c, b, z),
                      (x - w, b + c, z), (x - w, t - c, z)])
    faces = [tuple(reversed(range(8))), tuple(range(len(verts) - 8, len(verts)))]
    for k in range(len(stations) - 1):
        for j in range(8):
            faces.append((k * 8 + j, k * 8 + (j + 1) % 8,
                          (k + 1) * 8 + (j + 1) % 8, (k + 1) * 8 + j))
    return mesh(name, role, verts, faces, bevel)


def box(name, role, loc, size, bevel=0.0):
    x, y, z = loc
    a, b, c = (s / 2 for s in size)
    vv = [(x + sx * a, y + sy * b, z + sz * c) for sx, sy, sz in
          ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
           (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
    return mesh(name, role, vv,
                [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)], bevel)


def prism(name, role, y_low, y_high, outline_xy_xz):
    """Extrude a convex X/Z outline into a slab between two heights.

    The outline is given as (x, z) pairs; heights are absolute Y. Used for the
    overlapping plate belts that give the Syndicate hull its welded read.
    """
    n = len(outline_xy_xz)
    verts = [(x, y, z) for y in (y_low, y_high) for x, z in outline_xy_xz]
    faces = [tuple(range(n)), tuple(reversed(range(n, 2 * n)))]
    for j in range(n):
        faces.append((j, (j + 1) % n, (j + 1) % n + n, j + n))
    return mesh(name, role, verts, faces)


def ring(name, role, x, y, stations, n=12):
    """Annular tube: stations are (z, outer_radius, inner_radius).

    Used for open nozzle throats, drum collars and the load clamps that hold the
    reactor drums in their cradles, so no emitter is buried behind a solid cap.
    """
    vv = []
    ff = []
    for z, outer, inner in stations:
        if not 0 < inner < outer:
            raise ValueError('Ring must have an open bore')
        for r in (outer, inner):
            vv.extend((x + r * math.cos(j * 2 * math.pi / n),
                       y + r * math.sin(j * 2 * math.pi / n), z) for j in range(n))
    for k in range(len(stations) - 1):
        for wall in (0, 1):
            a = k * 2 * n + wall * n
            b = (k + 1) * 2 * n + wall * n
            ff.extend((a + j, a + (j + 1) % n, b + (j + 1) % n, b + j) for j in range(n))
    for k in (0, len(stations) - 1):
        a = k * 2 * n
        ff.extend((a + j, a + n + j, a + n + (j + 1) % n, a + (j + 1) % n) for j in range(n))
    return mesh(name, role, vv, ff)


def disc(name, role, x, y, z, r, depth, n=12):
    vv = [(x + r * math.cos(j * 2 * math.pi / n),
           y + r * math.sin(j * 2 * math.pi / n), z + d * depth / 2)
          for d in (-1, 1) for j in range(n)]
    ff = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    ff.extend((j, (j + 1) % n, (j + 1) % n + n, j + n) for j in range(n))
    return mesh(name, role, vv, ff)


def drum(name, role, centre, radius, length, sides=12):
    """Exposed cylinder along Z: the Syndicate's external reactor/fuel drum."""
    x, y, z = centre
    vv = []
    for d in (-1, 1):
        for j in range(sides):
            a = j * 2 * math.pi / sides
            vv.append((x + radius * math.cos(a), y + radius * math.sin(a),
                       z + d * length / 2))
    ff = [tuple(reversed(range(sides))), tuple(range(sides, 2 * sides))]
    for j in range(sides):
        k = (j + 1) % sides
        ff.append((j, k, k + sides, j + sides))
    return mesh(name, role, vv, ff)


def strut(name, role, start, end, thickness):
    """Square-section member between two points: lattice, gantries and yokes."""
    ax, ay, az = start
    bx, by, bz = end
    dx, dy, dz = bx - ax, by - ay, bz - az
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        raise ValueError('strut has no length')
    fx, fy, fz = dx / length, dy / length, dz / length
    # Any stable perpendicular pair is enough for a square section.
    ux, uy, uz = (0., 0., 1.) if abs(fz) < .9 else (1., 0., 0.)
    px, py, pz = fy * uz - fz * uy, fz * ux - fx * uz, fx * uy - fy * ux
    norm = math.sqrt(px * px + py * py + pz * pz)
    px, py, pz = px / norm, py / norm, pz / norm
    qx, qy, qz = fy * pz - fz * py, fz * px - fx * pz, fx * py - fy * px
    t = thickness / 2
    vv = []
    for ox, oy, oz in ((0, 0, 0), (dx, dy, dz)):
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vv.append((ax + ox + sx * t * px + sy * t * qx,
                       ay + oy + sx * t * py + sy * t * qy,
                       az + oz + sx * t * pz + sy * t * qz))
    ff = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
          (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    return mesh(name, role, vv, ff)


def lattice(name, role, a, b, bays, thickness, width=.0):
    """Four rails plus cross bracing between two points: an exposed truss.

    ``width`` spreads the rails sideways so the truss reads as an open frame
    rather than a bundle of bars; the bracing gives it visible depth.
    """
    ax, ay, az = a
    bx, by, bz = b
    w = width or thickness * 3
    corners = ((-w / 2, -w / 2), (w / 2, -w / 2), (w / 2, w / 2), (-w / 2, w / 2))
    for k, (ox, oy) in enumerate(corners):
        strut(f'{name} rail {k}', role, (ax + ox, ay + oy, az), (bx + ox, by + oy, bz), thickness)
    for j in range(bays):
        t0 = j / bays
        t1 = (j + 1) / bays
        for k in range(4):
            k2 = (k + 1) % 4
            o0 = corners[k]
            o1 = corners[k2]
            start = (ax + (bx - ax) * t0 + o0[0], ay + (by - ay) * t0 + o0[1], az + (bz - az) * t0)
            end = (ax + (bx - ax) * t1 + o1[0], ay + (by - ay) * t1 + o1[1], az + (bz - az) * t1)
            strut(f'{name} brace {j} {k}', role, start, end, thickness * .72)


def part_report():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    boxes = []
    for obj in sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'),
                      key=lambda o: o.name):
        ev = obj.evaluated_get(dg)
        data = ev.to_mesh()
        try:
            pts = [ev.matrix_world @ v.co for v in data.vertices]
        finally:
            ev.to_mesh_clear()
        boxes.append((obj.name, obj['role'],
                      [min(p[i] for p in pts) for i in range(3)],
                      [max(p[i] for p in pts) for i in range(3)]))
    return boxes


def assert_contact(boxes, slack=.6):
    """Every part must touch another part; a greeble in mid-air is a defect."""
    floating = []
    for i, (name, _, lo, hi) in enumerate(boxes):
        hit = False
        for j, (_, _, lo2, hi2) in enumerate(boxes):
            if i == j:
                continue
            if all(lo[k] - slack <= hi2[k] and lo2[k] - slack <= hi[k] for k in range(3)):
                hit = True
                break
        if not hit:
            floating.append(name)
    return floating


def export(root, kind, stem, limits, *, replace_own=False, fit_tolerance=.01,
           part_dump=False):
    """Quantize, refit inside the approved box, then save master + runtime mesh."""
    root = Path(root)
    master = root / f'art/blender/syndicate_{stem}.blend'
    target = (root / 'visual_packs/syndicate-imperium-prototypes/assets/models'
              / f'syndicate_{stem}.mesh.json')
    if not replace_own and (master.exists() or target.exists()):
        raise FileExistsError(f'Refusing existing Syndicate outputs: {master}, {target}')
    boxes = part_report()
    if part_dump:
        for name, role, lo, hi in boxes:
            print('PART', role, name,
                  'x[%.2f,%.2f]' % (lo[0], hi[0]), 'y[%.2f,%.2f]' % (lo[1], hi[1]),
                  'z[%.2f,%.2f]' % (lo[2], hi[2]), flush=True)
    floating = assert_contact(boxes)
    # A part that only touches through a 0.6-unit expansion is still attached to
    # the welded structure at station scale; anything further out is a defect.
    assert not floating, f'FLOATING {floating}'

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    raw = []
    for obj in sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'),
                      key=lambda o: o.name):
        ev = obj.evaluated_get(dg)
        data = ev.to_mesh()
        try:
            for v in data.vertices:
                raw.append(tuple(ev.matrix_world @ v.co))
        finally:
            ev.to_mesh_clear()
    lo = [min(p[i] for p in raw) for i in range(3)]
    hi = [max(p[i] for p in raw) for i in range(3)]
    # Fit per axis and per side: a design that overhangs one side is compressed
    # on that side only, and the printed scale says so instead of hiding it.
    scale, offset = [], []
    for axis, (low, high) in enumerate(limits):
        span = hi[axis] - lo[axis]
        # Half a thousandth of the span of slack per side: the vertices are
        # quantized to float32 for the runtime, and a min that rounds 6e-7 below
        # the approved box fails the containment assert for no design reason.
        inset = (high - low) * .0005
        want = (high - low) * .999
        s = want / span if span else 1.
        assert .98 <= s <= 1.06, (kind, 'fit scale out of range', axis, s)
        scale.append(s)
        offset.append((low + inset) - lo[axis] * s)
    print('FIT', json.dumps({'kind': kind, 'scale': [round(s, 6) for s in scale],
                             'raw_span': [round(hi[i] - lo[i], 4) for i in range(3)],
                             'target_span': [round(limits[i][1] - limits[i][0], 4)
                                             for i in range(3)]}), flush=True)

    def fitted(p):
        return tuple(offset[i] + p[i] * scale[i] for i in range(3))

    verts = []
    indices = {}
    batches = {r: [] for r in ROLES}
    parts = []
    skipped = 0
    for obj in sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'),
                      key=lambda o: o.name):
        role = obj['role']
        ev = obj.evaluated_get(dg)
        data = ev.to_mesh()
        data.calc_loop_triangles()
        local = []
        try:
            for vertex in data.vertices:
                world = fitted(ev.matrix_world @ vertex.co)
                q = tuple(round(struct.unpack('f', struct.pack('f', float(c)))[0], 7)
                          for c in world)
                if q not in indices:
                    indices[q] = len(verts)
                    verts.append(list(q))
                local.append(indices[q])
            first = len(batches[role])
            for face in data.loop_triangles:
                ids = [local[k] for k in face.vertices]
                a, b, c = (verts[k] for k in ids)
                u = [b[i] - a[i] for i in range(3)]
                v = [c[i] - a[i] for i in range(3)]
                normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                          u[0] * v[1] - u[1] * v[0]]
                area = math.sqrt(sum(c2 * c2 for c2 in normal))
                if area <= 1e-9:
                    skipped += 1
                    continue
                batches[role].append([round(c2 / area, 15) for c2 in normal] + ids)
            parts.append({'name': obj.name, 'role': role,
                          'triangles': len(batches[role]) - first, 'first_triangle': first})
        finally:
            ev.to_mesh_clear()
    bounds = [[min(v[i] for v in verts) for i in range(3)],
              [max(v[i] for v in verts) for i in range(3)]]
    total = sum(len(v) for v in batches.values())
    payload = {'contract': 'star-armada/mesh-export', 'contract_major': 1,
               'asset': f'prototype:syndicate/{kind}', 'authoring': 'Blender evaluated mesh',
               'coordinates': 'X beam; Y up; +Z forward', 'vertices': verts,
               'batches': batches, 'bounds': bounds, 'parts': parts,
               'triangle_count': total}
    text = json.dumps(payload, separators=(',', ':')) + '\n'
    report = {'kind': kind, 'triangles': total, 'vertices': len(verts),
              'parts': len(parts), 'bounds': bounds, 'bytes': len(text.encode()),
              'degenerate_skipped': skipped, 'fit_scale': scale,
              'roles': {r: len(batches[r]) for r in ROLES}}
    print('SYNDICATE_GEOMETRY ' + json.dumps(report), flush=True)
    assert all(batches.values()) and 1800 < total <= 11888, total
    assert len(verts) < 9500, len(verts)
    assert skipped == 0, skipped
    assert len(text.encode()) < 2000000
    for i, (low, high) in enumerate(limits):
        assert low <= bounds[0][i] < bounds[1][i] <= high, (kind, i, limits, bounds)
        assert abs((bounds[1][i] - bounds[0][i]) / (high - low) - 1) < fit_tolerance, \
            (kind, i, 'footprint drift', bounds)
    master.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene['asset_status'] = ('Pending owner appearance review; original '
                                         'Rim Syndicate rework batch')
    bpy.context.scene['source_authority'] = ('tools/art/build_syndicate_imperium.py and '
                                             'syndicate_imperium_designs.py')
    bpy.ops.wm.save_as_mainfile(filepath=str(master))
    target.write_text(text, encoding='utf-8')
    return report
