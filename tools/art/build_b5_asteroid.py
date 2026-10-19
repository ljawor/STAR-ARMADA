#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPE ONLY. The editable .blend is a derived artifact afterwards.

S06 batch B5 - the one environment row that is geometry rather than effect or texture:
`environment:asteroid_field`, the shared asteroid prop.

The row is the only B5 row that needs no new asset class. `render/renderer.py::_draw_asteroid_field`
draws forty rocks per field, each two to four lumpy sub-rocks of 24 triangles, generated per instance
from a seeded RNG; the owner's S01 scope answer chose the reading for it explicitly - asked whether
per-instance procedural asteroid props should stay procedural or become a shared authored prop, he
answered "in scope - bring into the catalogue". This seed authors that shared prop.

**It is a unit prop.** The field keeps its own count (40), placement, per-instance scale (12-46
units), tumble and seeding; the prop replaces only the *shape* drawn inside `_draw_rock`, which the
field scales. So the envelope here is the extent the legacy rock can reach at scale 1.0, worst case
over its jitter: x and z within +-0.90, y within +-0.70 - a vertex at each of those limits, so the
prop neither outgrows nor hides inside the rock it replaces.

**The triangle count multiplies by forty.** The legacy rock is 48-96 triangles and a field is roughly
two to four thousand; the exporter refuses a mesh at or under 1,800, so this prop starts near two
thousand and a field costs roughly eighty thousand triangles across forty display-list calls. That is
stated in the batch sheet and the handoff rather than discovered later.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b5_asteroid.py -- --all
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BREACH_TOLERANCE = 1e-3
# This asset is a declared small prop (owner decision `s06-small-prop-class-2026-10-17`): the renderer
# draws it forty times per field, so it is built with the surface density of the thing it replaces
# rather than of a station, and its own floor is the class's 120 triangles.
MIN_TRIANGLES = 120

IDENTIFIER = 'shared_asteroid_field'
BINDING = 'environment:asteroid_field'
RADIUS = 45          # the row's catalogue radius, read from assets/data/stations/stations.json
# What the prop is fitted to, and the ceiling it must never cross. The first revision fitted the
# *worst* case the legacy jitter can reach, and the field then read as heavy and dense: every
# instance was systematically bigger than a typical legacy rock. The fit is the mean rock; the
# ceiling is the worst case, asserted rather than reached.
LIMITS = [[-0.58, 0.58], [-0.46, 0.46], [-0.58, 0.58]]
CEILING = [[-0.90, 0.90], [-0.70, 0.70], [-0.90, 0.90]]
DESIGN = ('four overlapping jittered lumps with a rugged silhouette, a lit upper crust, a dark '
          'underside, a few mineral veins, glinting facets and two icy patches')
# Deterministic, so the recipe reproduces the same rock: the legacy look rhymes with it, and a
# per-instance variant is what the field's own rotation, scale and tumble already provide.
JITTER = (0.37, 0.61, 0.83, 1.19, 1.31, 1.57, 1.73, 1.91)

_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_master(argv):
    """Refuse before Blender is imported, and before anything is written."""
    if not argv or '--all' in argv:
        targets = [IDENTIFIER]
    elif '--asset' in argv:
        targets = [argv[argv.index('--asset') + 1]]
    else:
        targets = []
    for target in targets:
        if target not in (IDENTIFIER, BINDING):
            raise RuntimeError(f'unknown target {target}; the B5 batch authors {BINDING}')
    master = ROOT / f'art/blender/{IDENTIFIER}.blend'
    if master.exists() and '--replace-seed' not in argv:
        raise RuntimeError(f'{master.name} is the editable master. Use export_{IDENTIFIER}.py; '
                           f'--replace-seed destroys edits.')


_refuse_existing_master(_ARGV)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import weld_scene  # noqa: E402
import bpy  # noqa: E402,F401


def breach_lines(label, lo, hi, limits, extreme, tolerance=BREACH_TOLERANCE):
    """The extent self-check as a pure function, so a guard can drive it without Blender."""
    out = []
    for i, axis in enumerate('XYZ'):
        if lo[i] < limits[i][0] - tolerance:
            out.append(f'  BREACH {label} {axis} low {lo[i]:.7f} < {limits[i][0]} '
                       f'from {extreme[i][0]}')
        if hi[i] > limits[i][1] + tolerance:
            out.append(f'  BREACH {label} {axis} high {hi[i]:.7f} > {limits[i][1]} '
                       f'from {extreme[i][1]}')
    return out


def _hash(*parts):
    """A deterministic [0,1) value from integers: the recipe's own noise, no RNG state."""
    value = 0
    for part in parts:
        value = (value * 1103515245 + int(part) * 12345 + 7919) & 0x7fffffff
    return (value % 100000) / 100000.


def lump(name, centre, radii, grid=None, phase=0):
    """One lump, built the way the renderer's own rock is built: eight jittered corners and six face
    bulges, each face fanned through its bulge into four triangles with a flat normal.

    No grid and no per-vertex noise, on purpose. The legacy rock reads as stone because each of its
    facets is huge relative to the rock - two to four lumps of twenty-four triangles - and a finer
    surface reads as noise at this size. That is why this asset needed the owner's small-prop class
    (`s06-small-prop-class-2026-10-17`) instead of a surface dense enough for a station.
    """
    cx, cy, cz = centre
    rx, ry, rz = radii
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                k = len(corners)
                j = 0.82 + 0.36 * _hash(phase, k, 1)
                corners.append((sx * 0.72 * j, sy * 0.60 * j, sz * 0.72 * j))
    bulges = []
    for k, (dx, dy, dz) in enumerate(((0, 0, 1), (0, 0, -1), (0, 1, 0),
                                      (0, -1, 0), (1, 0, 0), (-1, 0, 0))):
        j = 0.88 + 0.42 * _hash(phase, k, 2)
        bulges.append((dx * j, dy * 0.80 * j, dz * j))
    faces = [((1, 3, 7, 5), 0), ((2, 6, 4, 0), 1), ((2, 3, 7, 6), 2),
             ((0, 4, 5, 1), 3), ((3, 1, 5, 7), 4), ((0, 2, 6, 4), 5)]
    verts, faces_out = [], []

    def point(p):
        return (min(max(p[0] * rx + cx, LIMITS[0][0]), LIMITS[0][1]),
                min(max(p[1] * ry + cy, LIMITS[1][0]), LIMITS[1][1]),
                min(max(p[2] * rz + cz, LIMITS[2][0]), LIMITS[2][1]))

    for quad, bulge in faces:
        a_, b_, c_, d_ = (point(corners[i]) for i in quad)
        centre_point = point(bulges[bulge])
        base = len(verts)
        verts.extend((a_, b_, c_, d_, centre_point))
        for tri in ((0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)):
            faces_out.append((base + tri[0], base + tri[1], base + tri[2]))
    return verts, faces_out


def role_of(verts, tri, centre):
    """Which material role a triangle carries, from its own facing and height.

    The loader's six roles have to be filled by real geometry, not by a painted band: the upper crust
    is `trim`, the underside `dark`, the body `base`, and the accents are placed deliberately below.
    """
    a, b, c = (verts[i] for i in tri)
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(t * t for t in n)) or 1.0
    ny = n[1] / length
    height = sum(p[1] for p in (a, b, c)) / 3 - centre[1]
    cx_, cz_ = sum(p[0] for p in (a, b, c)) / 3, sum(p[2] for p in (a, b, c)) / 3
    radial = math.sqrt((cx_ - centre[0]) ** 2 + (cz_ - centre[2]) ** 2)
    if height > 0.24 and ny > 0.15:
        return 'trim'
    if height < -0.20 or ny < -0.30:
        return 'dark'
    if height > 0.10 and radial > 0.52:
        return 'lit'
    return 'base'


def build():
    """Four overlapping lumps, the reach vertices, then the accent, glint and ice patches."""
    centre = (0.0, 0.0, 0.0)
    # Seven overlapping lumps, each carrying flat plates: the vocabulary the legacy rock uses (a lump
    # is eight jittered corners and six bulges) at the size the field's own scale reads as the rock it
    # replaces, and enough of them to clear the exporter's floor without a finer surface.
    # Four overlapping lumps the size of the legacy rock's own, plus three raised patches. An authored
    # instance has to read as *one* rock, so the lumps are few and the facets on them are large.
    lumps = (((-.10, .02, .08), (.58, .42, .54), 5, 3),
             ((.17, -.04, -.12), (.50, .37, .46), 5, 11),
             ((.02, .10, .18), (.40, .29, .36), 4, 19),
             ((-.24, -.05, -.20), (.30, .22, .28), 4, 29))
    verts, faces, role_of_face = [], [], []
    for k, (c, r, grid, phase) in enumerate(lumps):
        lv, lf = lump(f'10 Lump {k}', c, r, grid=grid, phase=phase)
        base = len(verts)
        verts.extend(lv)
        for a, b, c_ in lf:
            faces.append((a + base, b + base, c_ + base))
            role_of_face.append(None)      # classified below, from the face's own facing
    # Accent veins, glint facets and two icy patches: raised slabs on the crust, still inside the box.
    patches = (('20 Vein', 'accent', (0.30, 0.30, 0.26), 0.34, 6),
               ('21 Vein', 'accent', (-0.30, 0.22, -0.24), 0.30, 10),
               ('30 Glint', 'lit', (0.16, 0.40, -0.30), 0.26, 14),
               ('40 Ice patch', 'cool', (-0.34, 0.26, 0.22), 0.28, 18),
               ('41 Ice patch', 'cool', (0.34, 0.24, 0.30), 0.24, 22))
    for name, role, c, grid_step, phase in patches:
        lv, lf = lump(name, c, (grid_step, grid_step * 0.7, grid_step), grid=4, phase=phase)
        base = len(verts)
        verts.extend(lv)
        for a, b, c_ in lf:
            faces.append((a + base, b + base, c_ + base))
            role_of_face.append(role)      # the vein, glint and ice patches carry their own role
    verts = fit(verts)
    for index, role in enumerate(role_of_face):
        if role is None:
            role_of_face[index] = role_of(verts, faces[index], (0.0, 0.0, 0.0))
    return verts, faces, role_of_face


def fit(verts):
    """Map the built rock onto the legacy rock's worst-case box, per axis and per side.

    The lumps are authored by eye, so their extremes land wherever they land. This maps each side of
    each axis onto its limit - a mild, stated distortion (worst case 0.85x on one side, 1.0x on the
    others here) that buys the property the batch is about: the prop reaches what the legacy rock
    could at scale 1.0 and exceeds it nowhere, so the field's silhouette size is unchanged.
    """
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    scale = []
    for axis in range(3):
        neg = LIMITS[axis][0] / lo[axis] if lo[axis] < 0 else 1.0
        pos = LIMITS[axis][1] / hi[axis] if hi[axis] > 0 else 1.0
        scale.append((neg, pos))
    out = []
    for v in verts:
        out.append(tuple(v[axis] * (scale[axis][0] if v[axis] < 0 else scale[axis][1])
                         for axis in range(3)))
    return out


def report_bounds(label):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo = [1e9] * 3
    hi = [-1e9] * 3
    extreme = [['', ''] for _ in range(3)]
    tris = 0
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        for v in mesh.vertices:
            point = obj.matrix_world @ v.co
            for i in range(3):
                if point[i] < lo[i]:
                    lo[i], extreme[i][0] = point[i], obj.name
                if point[i] > hi[i]:
                    hi[i], extreme[i][1] = point[i], obj.name
        mesh.calc_loop_triangles()
        tris += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
    print(f'TRIS {label} {tris} {"OK" if tris > MIN_TRIANGLES else "LOW"}')
    print(f'BOUNDS {label} lo={[round(v, 3) for v in lo]} hi={[round(v, 3) for v in hi]}')
    breaches = breach_lines(label, lo, hi, LIMITS, extreme)
    # The ceiling is asserted separately: fitting to the mean rock is the point, but the prop must
    # still never be larger than the legacy jitter can reach, or the field's outermost rocks grow.
    breaches += breach_lines(label + ' ceiling', lo, hi, CEILING, extreme)
    for line in breaches:
        print(line)
    print(f'SELFCHECK {label} breaches={len(breaches)} tolerance={BREACH_TOLERANCE}')
    return tris


def main():
    master = ROOT / f'art/blender/{IDENTIFIER}.blend'
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    verts, faces, role_of_face = build()
    roles = {}
    for tri, role in zip(faces, role_of_face):
        roles.setdefault(role, []).append(tri)
    for role, tris in sorted(roles.items()):
        mesh = bpy.data.meshes.new(f'{role} rock')
        mesh.from_pydata([verts[i] for tri in tris for i in tri], [],
                         [(3 * n, 3 * n + 1, 3 * n + 2) for n in range(len(tris))])
        mesh.validate()
        obj = bpy.data.objects.new(f'{role} rock', mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj['engine_material_role'] = role
        obj.select_set(True)
    bpy.context.view_layer.objects.active = bpy.context.scene.objects[0]
    # Unit-scale prop: the weld pass's station-sized defaults (tolerance .25, grow up to 2.5 units)
    # would swallow a 1.8-unit rock whole, so the same rules are stated at this asset's scale - about
    # a fiftieth of the station numbers, which is the same fraction of the object either way.
    joints = weld_scene(tolerance=0.02, grow_max=0.04, min_half=0.004, max_half=0.02,
                        overlap=0.01, max_brace=0.22)
    print(f'WELD {IDENTIFIER} joints={joints if not isinstance(joints, dict) else len(joints)}')
    tris = report_bounds(IDENTIFIER)
    features = dict(authority='script', approval='pending_owner_approval', binding=BINDING,
                    data_id='asteroid_field', original_design=True, design=DESIGN,
                    legacy_envelope=[list(a) for a in LIMITS],
                    seed_recipe='tools/art/build_b5_asteroid.py; script-authoritative per the S03 '
                                'source-authority policy for repeated modular hardware',
                    environment_kind='asteroid_field', station_radius=RADIUS, shared_prop=True,
                    field_instances=40, field_scale_range=[12, 46],
                    min_triangles=MIN_TRIANGLES,
                    provenance='Original geometry generated by this recipe; no external mesh or '
                               'texture dependencies')
    bpy.context.scene['asset'] = IDENTIFIER
    bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
    bpy.context.scene['authority'] = 'script'
    bpy.context.scene['design'] = DESIGN
    bpy.context.scene['binding'] = BINDING
    bpy.context.scene['review'] = 'pending owner approval - not a production binding'
    bpy.context.scene['coordinates'] = 'X beam; Y up; +Z forward'
    bpy.context.scene['runtime'] = 'immutable evaluated triangles; no runtime Blender'
    bpy.context.preferences.filepaths.save_version = 0
    master.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
    print(f'SEED_OK {BINDING} -> {master.name}')


main()
