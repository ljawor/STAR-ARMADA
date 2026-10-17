#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPES ONLY. Each editable .blend is a derived artifact afterwards.

S06 batch B4 - the satellite and planet-installation rows, i.e. every `<faction>:<kind>` seat
that `assets/data/stations/stations.json` holds beside the station kinds:

  defense_satellite / attack_satellite
      x rebel, confederacy, syndicate, imperial                          =  8 rows
  planet_extractor / planet_trade_hub / planet_shield_generator / planet_pulsar_cannon
      x rebel, confederacy, syndicate, imperial                          = 16 rows

These rows are script-authoritative per the S03 source-authority policy (repeated modular
hardware), so this seed is the recipe and the `.blend` it writes is a derived artifact kept for
inspection. Every dimension is derived from the binding's own legacy extent (`frame`), and each
design carries four *reach* parts that land that extent exactly - a rail spanning the full depth,
a beam spanning the full width, a pad whose underside is the Y minimum and a cap whose top is the
Y maximum - because the review harness requires the authored footprint to *reach* the legacy one
per axis and per side, and the legacy hardware fills its declared box. `plate` carries no bevel,
so a declared box is the evaluated box.

`station_mesh` consults `mesh_for(f'{faction}:{data_id}')` ahead of every fallback, imperial
included, so no row here needs a renderer change; the imperial *ships* are the ones that need a
per-binding key minted in `render/faction_visuals.py::ship_visual_key`.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b4_hardware.py -- --all
    Blender --background --python-exit-code 1 --python tools/art/build_b4_hardware.py -- --asset rebel:defense_satellite
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# An extent error below this many world units is float noise, not a breach: `plate` is
# bevel-free, so the tolerance only absorbs float32 representation noise in the evaluated
# depsgraph, which the exporter's edge quantiser then snaps to the edge.
BREACH_TOLERANCE = 1e-3

# The legacy extents, measured by `tools/art/probe_b4_scope.py` from the live code. They are per
# kind, and identical across factions except where FACTION_Z_LOW records otherwise: the legacy
# hardware differs in ring side count, and the syndicate's five-sided ring is shorter at the rear.
LIMITS = {
    'defense_satellite': [[-41.1051, 41.1051], [-9.0, 19.5], [-34.0, 44.0]],
    'attack_satellite': [[-50.9795, 50.9795], [-9.0, 21.5], [-34.0, 58.0]],
    'planet_extractor': [[-34.0, 34.0], [0.0, 43.0], [-32.0, 32.0]],
    'planet_trade_hub': [[-34.0, 34.0], [0.0, 49.5], [-32.0, 32.0]],
    'planet_shield_generator': [[-34.0, 34.0], [0.0, 46.5], [-32.0, 32.0]],
    'planet_pulsar_cannon': [[-34.0, 34.0], [0.0, 42.4], [-32.0, 46.0]],
}
RADIUS = 45

# The legacy ring side count per faction is kept as the authored silhouette's base polygon, so a
# row still reads as the same family's hardware it replaces.
SIDES = {'imperial': 6, 'rebel': 12, 'confederacy': 8, 'syndicate': 5}
FACTION_PREFIX = {'rebel': 'alliance', 'confederacy': 'legion', 'syndicate': 'syndicate',
                  'imperial': 'imperial'}
KINDS = {
    'defense_satellite': 'Defense Satellite',
    'attack_satellite': 'Attack Satellite',
    'planet_extractor': 'Planet Extractor',
    'planet_trade_hub': 'Planet Trade Hub',
    'planet_shield_generator': 'Planet Shield Generator',
    'planet_pulsar_cannon': 'Planet Pulsar Cannon',
}
DESIGNS = {
    ('defense_satellite', 'rebel'): 'twelve-sided armoured ring with three shield masts',
    ('defense_satellite', 'confederacy'): 'eight-sided ring with three sloped defence pods',
    ('defense_satellite', 'syndicate'): 'five-sided bolted ring with three improvised pods',
    ('defense_satellite', 'imperial'): 'six-sided ring with three faceted defence towers',
    ('attack_satellite', 'rebel'): 'twelve-sided ring carrying three long beam cannon spines',
    ('attack_satellite', 'confederacy'): 'eight-sided ring carrying three stepped gun pods',
    ('attack_satellite', 'syndicate'): 'five-sided ring with three lashed projector rails',
    ('attack_satellite', 'imperial'): 'six-sided ring with three angular gun towers',
    ('planet_extractor', 'rebel'): 'clean slab mine head over a drill gantry and ore silos',
    ('planet_extractor', 'confederacy'): 'stepped armoured mine works with two drill towers',
    ('planet_extractor', 'syndicate'): 'open truss mine rig with bolted drums and a cab',
    ('planet_extractor', 'imperial'): 'faceted mine citadel with a drill spire',
    ('planet_trade_hub', 'rebel'): 'stacked container racks beside a clean control tower',
    ('planet_trade_hub', 'confederacy'): 'tiered store blocks under a tall market spire',
    ('planet_trade_hub', 'syndicate'): 'open quay frame with lashed crates and a hab cab',
    ('planet_trade_hub', 'imperial'): 'angular trade bastion with a tower and buttresses',
    ('planet_shield_generator', 'rebel'): 'wide emitter ring on four clean buttresses',
    ('planet_shield_generator', 'confederacy'): 'stepped emitter mound with four armour fins',
    ('planet_shield_generator', 'syndicate'): 'bolted emitter frame on four scaffold legs',
    ('planet_shield_generator', 'imperial'): 'faceted emitter pyramid on four towers',
    ('planet_pulsar_cannon', 'rebel'): 'long clean barrel over a breech block and turntable',
    ('planet_pulsar_cannon', 'confederacy'): 'stepped breech with a banded long barrel',
    ('planet_pulsar_cannon', 'syndicate'): 'scaffold breech with a lashed projector barrel',
    ('planet_pulsar_cannon', 'imperial'): 'angular breech tower with a faceted long barrel',
}
# Two rows are *not* faction-independent: the legacy satellite mesh is parameterised by the
# faction's ring side count, and the syndicate's five-sided ring stops its rear structure short of
# the other families' Z minimum. Measured by `tools/art/probe_b4_scope.py`; the harness compares each
# authored footprint against the legacy mesh it replaces, so a sheet that generalised here would be
# wrong about both rows.
FACTION_Z_LOW = {('syndicate', 'defense_satellite'): -27.5066,
                 ('syndicate', 'attack_satellite'): -30.299}
SEEDS = {}
for _faction, _prefix in FACTION_PREFIX.items():
    for _kind in KINDS:
        _limits = [list(a) for a in LIMITS[_kind]]
        if (_faction, _kind) in FACTION_Z_LOW:
            _limits[2][0] = FACTION_Z_LOW[(_faction, _kind)]
        SEEDS[f'{_faction}:{_kind}'] = (f'{_prefix}_{_kind}', RADIUS, _limits, _faction)

_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_masters(argv):
    """Refuse before Blender is imported, and before any target is written.

    One seed authors twenty-four masters; a half-run that dies on the fifth leaves the batch
    inconsistent, so pre-flight every target. An empty argument list is treated as "all"
    deliberately: the seed is only ever driven by Blender with an explicit `--`.
    """
    if not argv or '--all' in argv:
        targets = list(SEEDS)
    elif '--asset' in argv:
        targets = [argv[argv.index('--asset') + 1]]
    else:
        targets = []
    for key in targets:
        master = ROOT / f'art/blender/{SEEDS[key][0]}.blend'
        if master.exists() and '--replace-seed' not in argv:
            raise RuntimeError(f'{master.name} is the editable master. Use '
                               f'export_{SEEDS[key][0]}.py; --replace-seed destroys edits.')


_refuse_existing_masters(_ARGV)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import mesh_object, plate, weld_scene  # noqa: E402
import bpy  # noqa: E402,F401


# ---------------------------------------------------------------- hardware kit
# Deliberately duplicated from the B3a/B3b/B3c seeds rather than moved into a shared module: each
# seed refuses to overwrite another batch's masters, and a shared kit would make one batch's edit
# move another batch's rebuild.

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


def frame(limits):
    """The binding's own legacy extent, split into lo/hi, centre and span per axis."""
    lo = [a[0] for a in limits]
    hi = [a[1] for a in limits]
    return lo, hi, [(lo[i] + hi[i]) / 2 for i in range(3)], [hi[i] - lo[i] for i in range(3)]


def torus(name, role, y, radius, tube, m=24, n=8, sx=1.0, sz=1.0, bevel=0, cx=0., cz=0.):
    """A band: a ring in the XZ plane, its axis vertical (Y)."""
    verts = []
    for i in range(m):
        a = 2 * math.pi * i / m
        px, pz = cx + radius * sx * math.cos(a), cz + radius * sz * math.sin(a)
        for j in range(n):
            b = 2 * math.pi * j / n
            verts.append((px + tube * math.cos(a) * math.cos(b), y + tube * math.sin(b),
                          pz + tube * math.sin(a) * math.cos(b)))
    faces = []
    for i in range(m):
        i2 = (i + 1) % m
        for j in range(n):
            j2 = (j + 1) % n
            faces.append((i * n + j, i2 * n + j, i2 * n + j2, i * n + j2))
    return mesh_object(name, role, verts, faces, bevel)


def ringy(name, role, cx, cz, y, outer, inner, thickness, n=16, sx=1.0, sz=1.0):
    """A horizontal rim, collar or deck edge: an annulus whose axis is vertical."""
    verts = []
    for yy in (y - thickness / 2, y + thickness / 2):
        for r in (outer, inner):
            verts.extend((cx + r * sx * math.cos(i * 2 * math.pi / n), yy,
                          cz + r * sz * math.sin(i * 2 * math.pi / n)) for i in range(n))
    faces = []
    for j in range(n):
        q = (j + 1) % n
        faces.append((j, q, 2 * n + q, 2 * n + j))
        faces.append((n + j, n + q, 3 * n + q, 3 * n + j))
    for base in (0, n):
        for j in range(n):
            q = (j + 1) % n
            faces.append((base + j, base + q, base + n + q, base + n + j))
    return mesh_object(name, role, verts, faces, 0)


def strut(name, role, a, b, half_w, half_h, bevel=0):
    """A rectangular member between two points - trusses, booms, buttresses, barrels."""
    axis = [b[i] - a[i] for i in range(3)]
    length = math.sqrt(sum(v * v for v in axis))
    u = [v / length for v in axis]
    ref = [0., 1., 0.] if abs(u[1]) < .9 else [1., 0., 0.]
    v = [u[1] * ref[2] - u[2] * ref[1], u[2] * ref[0] - u[0] * ref[2],
         u[0] * ref[1] - u[1] * ref[0]]
    n = math.sqrt(sum(t * t for t in v))
    v = [t / n for t in v]
    w = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    verts = []
    for end in (a, b):
        for sw, sh in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(end[i] + v[i] * half_w * sw + w[i] * half_h * sh
                                for i in range(3)))
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_object(name, role, verts, faces, bevel)


def ring_blocks(name, role, count, cx, cz, y, rx, rz, size, phase=0.):
    """Blocks spaced around an ellipse: pods on a ring, bays on a deck."""
    for i in range(count):
        a = 2 * math.pi * (i / count + phase)
        plate(f'{name} {i}', role, size,
              (cx + rx * math.cos(a), y, cz + rz * math.sin(a)), .3)


def bank(name, role, count, size, start, step, bevel=.2):
    """A row of small blocks: machinery, vents, canisters, crates.

    Rows step by less than one block width so the weld pass reads consecutive blocks as one
    cluster rather than a brace: a gap wider than `max_brace` is scaffold, not a weld.
    """
    for i in range(count):
        plate(f'{name} {i}', role, size,
              tuple(start[k] + step[k] * i for k in range(3)), bevel)


def z_rail(name, role, limits, half_w, height, y, cx=None):
    """A rail spanning the binding's full depth: it sets both Z extremes, per side."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, (half_w * 2, height, span[2]), (c[0] if cx is None else cx, y, c[2]))


def x_beam(name, role, limits, height, depth, y, cz=None):
    """A beam spanning the full width: it sets both X extremes, per side."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, (span[0], height, depth), (c[0], y, c[2] if cz is None else cz))


def keel_pad(name, role, limits, size, dx=0., dz=0.):
    """A part whose underside is the binding's Y minimum."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, size, (c[0] + dx, lo[1] + size[1] / 2, c[2] + dz))


def top_cap(name, role, limits, size, dx=0., dz=0.):
    """A part whose top is the binding's Y maximum."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, size, (c[0] + dx, hi[1] - size[1] / 2, c[2] + dz))


def column(name, role, limits, y0, y1, width, depth, dx=0., dz=0.):
    """A spine from the tallest body part up into the crown, so the crown is welded to structure.

    A building's top cap sets the Y maximum from the envelope, which puts it wherever the
    envelope says - 14 units above the roof the rest of the design built. A cap that near the
    envelope and that far from the body is a brace, not a weld, so every building carries this
    column: it starts inside the body and ends inside the cap.
    """
    lo, hi, c, span = frame(limits)
    return plate(name, role, (width, y1 - y0, depth), (c[0] + dx, (y0 + y1) / 2, c[2] + dz), .3)


def core_hull(limits, faction, span_x=.62, span_z=.62, y=None):
    """The one continuous member every piece of a satellite is welded to: the armoured ring.

    A satellite is a ring with three pods; a planet building is a plinth with a superstructure.
    Both need one member that spans most of the footprint, so no part depends on a brace longer
    than the weld pass accepts. Returns the ring radius used, for the callers' placement.
    """
    lo, hi, c, span = frame(limits)
    ry = (lo[1] + 0.22 * span[1]) if y is None else y
    rx, rz = span[0] * span_x / 2, span[2] * span_z / 2
    sides = SIDES[faction]
    torus('01 Core ring', 'base', ry, 1.0, 1.0, m=sides, n=6, sx=rx, sz=rz, bevel=0)
    ringy('02 Ring collar', 'trim', c[0], c[2], ry + 2.6, rx * 1.02, rx * .86, 1.6, n=sides,
          sx=1., sz=rz / rx)
    ringy('03 Ring underside', 'dark', c[0], c[2], ry - 2.6, rx * .96, rx * .78, 1.8, n=sides,
          sx=1., sz=rz / rx)
    return rx, rz, ry


def detail_layer(limits, faction, rx, rz, y, cz, phase=0.):
    """Detail every row carries: two concentric bands and four role-separated block rows.

    The rows are what the review's per-role ablations measure: `dark` machinery, `cool` vents,
    `base` plating and `lit` markers, with `accent` left to the design's own pods.
    """
    lo, hi, c, span = frame(limits)
    sides = SIDES[faction]
    torus('90 Inner band', 'trim', float(y), rx * .58, 1.4, m=max(12, sides * 2), n=8, sx=1.,
          sz=rz / rx, cz=cz)
    ring_blocks('91 Machinery', 'dark', 12, c[0] * .2, cz, float(y) + 1.6, rx * .74, rz * .74,
                (4.4, 2.8, 4.4), phase)
    ring_blocks('92 Vents', 'cool', 12, c[0] * .2, cz, float(y) + 3.1, rx * .70, rz * .70,
                (2.2, 1.3, 2.2), phase + .13)
    ring_blocks('93 Plating', 'base', 10, c[0] * .2, cz, float(y) - 1.5, rx * .66, rz * .66,
                (5.6, 1.3, 3.8), phase + .07)
    ring_blocks('94 Markers', 'lit', 12, c[0] * .2, cz, float(y) + 4.2, rx * .70, rz * .70,
                (1.5, 1.1, 1.5), phase + .13)


def report_bounds(limits, label):
    """Print the evaluated extents and every breach, so one build names them all."""
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
    print(f'TRIS {label} {tris} {"OK" if tris > 1800 else "LOW"}')
    print(f'BOUNDS {label} lo={[round(v, 2) for v in lo]} hi={[round(v, 2) for v in hi]}')
    breaches = breach_lines(label, lo, hi, limits, extreme)
    for line in breaches:
        print(line)
    print(f'SELFCHECK {label} breaches={len(breaches)} tolerance={BREACH_TOLERANCE}')


# ---------------------------------------------------------------- the three satellite pods

PODS = {'rebel': (13.0, 9.0, 22.0), 'confederacy': (12.0, 10.0, 24.0),
        'syndicate': (10.5, 8.0, 21.0), 'imperial': (11.0, 10.5, 23.0)}


def satellite_pods(limits, faction, rx, rz, ry, gun=False):
    """Three pods on the core ring, at 120 degrees, plus the reach parts for X and Z.

    The pods sit *on* the ring (`rx`/`rz` are the ring's radii) so the weld pass joins them to
    continuous structure, and the reach parts - a full-width beam and a full-depth rail - are
    welded through the pod line rather than floating beside it.
    """
    lo, hi, c, span = frame(limits)
    pod_w, pod_h, pod_d = PODS[faction]
    angles = (0, 120, 240)
    for i, angle in enumerate(angles):
        a = math.radians(angle)
        x, z = math.sin(a) * rx * .86, math.cos(a) * rz * .86
        plate(f'10 Pod body {i}', 'base', (pod_w, pod_h, pod_d), (x, ry + 3.0, z), .35)
        plate(f'11 Pod cap {i}', 'accent', (pod_w * .9, 3.0, pod_d * .9),
              (x, ry + 3.0 + pod_h / 2 + .6, z), .3)
        plate(f'12 Pod vent {i}', 'cool', (pod_w * .5, 1.4, pod_d * .5),
              (x * .92, ry + 6.4, z * .92), .2)
        strut(f'13 Pod strut {i}', 'dark', (x * .55, ry, z * .55), (x, ry + 2.2, z), .9, .9)
        if gun:
            plate(f'14 Gun body {i}', 'base', (9.0, 10.5, pod_d * 1.5), (x, ry + 4.0, z), .3)
            # The gun rail is a barrel, not a reach part: the batch's Z extremes are set by
            # the full-depth spine rail below, and a rail sized for one pod's angle left the
            # 120-degree pod's muzzle 5.7 units outside the legacy envelope.
            plate(f'15 Gun rail {i}', 'trim', (3.2, 3.2, pod_d * 1.15), (x, ry + 8.0, z), 0)
            plate(f'16 Gun muzzle {i}', 'accent', (5.0, 5.0, 3.0),
                  (x, ry + 11.0, z), .3)
    # Reach parts: one transverse beam sets both X extremes and one rail sets both Z extremes.
    x_beam('20 Spine beam', 'base', limits, 7.0, 16.0, ry + 1.0)
    z_rail('21 Long spine', 'dark', limits, 5.0, 6.5, ry + 6.5)
    keel_pad('22 Keel block', 'dark', limits, (span[0] * .30, 6.0, span[2] * .26))
    top_cap('23 Crown', 'accent', limits, (span[0] * .22, 4.0, span[2] * .20))


def build_defense_satellite(limits, faction):
    rx, rz, ry = core_hull(limits, faction, span_x=.66, span_z=.68)
    satellite_pods(limits, faction, rx, rz, ry, gun=False)
    # The detail layer's plating row hangs 2.15 units under the band it sits on, so it is placed
    # from the Y minimum the keel pad sets rather than from the ring: a ring-relative drop put it
    # 1.88 units below the legacy envelope.
    detail_layer(limits, faction, rx, rz, limits[1][0] + 2.4, 0.0)


def build_attack_satellite(limits, faction):
    rx, rz, ry = core_hull(limits, faction, span_x=.60, span_z=.56)
    satellite_pods(limits, faction, rx, rz, ry, gun=True)
    detail_layer(limits, faction, rx, rz, limits[1][0] + 2.4, 0.0)


# ---------------------------------------------------------------- the four planet buildings

def plinth(limits, faction, span_x=.94, span_z=.90, height=None):
    """The continuous ground structure every planet building stands on."""
    lo, hi, c, span = frame(limits)
    body_h = (0.14 * span[1]) if height is None else height
    plate('01 Plinth', 'base', (span[0] * span_x, body_h, span[2] * span_z),
          (c[0], lo[1] + body_h / 2 + 1.0, c[2]))
    ringy('02 Plinth rim', 'trim', c[0], c[2], lo[1] + body_h + 1.0,
          span[0] * span_x / 2 * 1.02, span[0] * span_x / 2 * .8, 1.6, n=max(8, SIDES[faction] * 2),
          sx=1., sz=span_z / span_x)
    keel_pad('03 Footing', 'dark', limits, (span[0] * .78, 3.0, span[2] * .74))
    return body_h


def build_planet_extractor(limits, faction):
    lo, hi, c, span = frame(limits)
    plinth(limits, faction)
    # Drill towers and ore silos step off the plinth's top: each tower's base sits inside the
    # previous one's footprint, so the weld chain never spans a gap wider than a block.
    for i, dx in enumerate((-.26, .26)):
        plate(f'10 Drill tower {i}', 'base', (span[0] * .20, span[1] * .40, span[2] * .20),
              (c[0] + dx * span[0], lo[1] + span[1] * .36, c[2] - span[2] * .12), .35)
        plate(f'11 Drill head {i}', 'dark', (span[0] * .10, span[1] * .22, span[2] * .10),
              (c[0] + dx * span[0], lo[1] + span[1] * .30, c[2] + span[2] * .18), .3)
        plate(f'12 Drill crown {i}', 'accent', (span[0] * .08, 3.0, span[2] * .08),
              (c[0] + dx * span[0], lo[1] + span[1] * .62, c[2] - span[2] * .12), .3)
        bank(f'13 Silo {i}', 'trim', 3, (span[0] * .09, span[1] * .16, span[2] * .09),
             (c[0] + dx * span[0] - span[0] * .12, lo[1] + span[1] * .16, c[2] + span[2] * .22),
             (span[0] * .12, 0, 0))
        bank(f'14 Silo louvre {i}', 'cool', 3, (span[0] * .05, span[1] * .05, span[2] * .05),
             (c[0] + dx * span[0] - span[0] * .11, lo[1] + span[1] * .27, c[2] + span[2] * .22),
             (span[0] * .11, 0, 0))
    plate('15 Gantry deck', 'trim', (span[0] * .72, 3.4, span[2] * .30),
          (c[0], lo[1] + span[1] * .62, c[2] + span[2] * .10), .3)
    for i in range(5):
        plate(f'16 Gantry rail {i}', 'dark', (span[0] * .05, 2.6, span[2] * .26),
              (c[0] - span[0] * .28 + i * span[0] * .14, lo[1] + span[1] * .70,
               c[2] + span[2] * .10), .2)
    x_beam('20 Cross works', 'base', limits, 5.0, span[2] * .22, lo[1] + span[1] * .30)
    z_rail('21 Haul rail', 'dark', limits, 4.0, 4.0, lo[1] + span[1] * .08)
    column('22 Spine', 'trim', limits, lo[1] + span[1] * .30, hi[1] - 2.4,
           span[0] * .11, span[2] * .11)
    top_cap('23 Head mast', 'accent', limits, (span[0] * .18, 4.5, span[2] * .16))
    bank('24 Marker lights', 'lit', 3, (2.2, 1.6, 2.2),
         (c[0] - span[0] * .28, lo[1] + span[1] * .74, c[2] + span[2] * .10),
         (span[0] * .14, 0, 0))
    detail_layer(limits, faction, span[0] * .40, span[2] * .38, lo[1] + span[1] * .20, 0.0)


def build_planet_trade_hub(limits, faction):
    lo, hi, c, span = frame(limits)
    plinth(limits, faction)
    plate('10 Store block', 'base', (span[0] * .52, span[1] * .30, span[2] * .52),
          (c[0] - span[0] * .14, lo[1] + span[1] * .26, c[2] - span[2] * .10), .35)
    plate('11 Store tier', 'trim', (span[0] * .44, span[1] * .16, span[2] * .44),
          (c[0] - span[0] * .14, lo[1] + span[1] * .49, c[2] - span[2] * .10), .3)
    plate('12 Control tower', 'base', (span[0] * .22, span[1] * .34, span[2] * .22),
          (c[0] + span[0] * .24, lo[1] + span[1] * .34, c[2] + span[2] * .14), .35)
    plate('13 Tower gallery', 'accent', (span[0] * .26, 3.0, span[2] * .26),
          (c[0] + span[0] * .24, lo[1] + span[1] * .52, c[2] + span[2] * .14), .3)
    plate('14 Tower head', 'dark', (span[0] * .14, span[1] * .12, span[2] * .14),
          (c[0] + span[0] * .24, lo[1] + span[1] * .63, c[2] + span[2] * .14), .3)
    bank('15 Container rack', 'base', 4, (span[0] * .10, span[1] * .09, span[2] * .18),
         (c[0] - span[0] * .36, lo[1] + span[1] * .16, c[2] + span[2] * .18),
         (span[0] * .11, 0, 0))
    bank('16 Rack trim', 'trim', 4, (span[0] * .06, span[1] * .06, span[2] * .16),
         (c[0] - span[0] * .35, lo[1] + span[1] * .30, c[2] + span[2] * .18),
         (span[0] * .11, 0, 0))
    bank('17 Rack vents', 'cool', 4, (span[0] * .05, span[1] * .04, span[2] * .10),
         (c[0] - span[0] * .34, lo[1] + span[1] * .39, c[2] + span[2] * .18),
         (span[0] * .10, 0, 0))
    x_beam('20 Market span', 'base', limits, 5.0, span[2] * .22, lo[1] + span[1] * .55)
    z_rail('21 Quay rail', 'dark', limits, 4.0, 4.0, lo[1] + span[1] * .10)
    column('22 Mast spine', 'trim', limits, lo[1] + span[1] * .58, hi[1] - 2.2,
           span[0] * .10, span[2] * .10)
    top_cap('23 Beacon mast', 'accent', limits, (span[0] * .16, 4.0, span[2] * .14))
    plate('24 Mast collar', 'lit', (span[0] * .10, 1.6, span[2] * .10),
          (c[0], hi[1] - 9.0, c[2]), .2)
    detail_layer(limits, faction, span[0] * .42, span[2] * .40, lo[1] + span[1] * .16, 0.0)


def build_planet_shield_generator(limits, faction):
    lo, hi, c, span = frame(limits)
    plinth(limits, faction)
    rx, rz = span[0] * .40, span[2] * .40
    torus('10 Emitter ring', 'base', lo[1] + span[1] * .30, 1.0, 1.0, m=max(10, SIDES[faction] * 2),
          n=8, sx=rx, sz=rz)
    ringy('11 Emitter lip', 'trim', c[0], c[2], lo[1] + span[1] * .38, rx * 1.06, rx * .82, 2.0,
          n=max(10, SIDES[faction] * 2), sx=1., sz=rz / rx)
    ring_blocks('12 Emitter pods', 'accent', 6, c[0], c[2], lo[1] + span[1] * .34, rx * .92,
                rz * .92, (span[0] * .09, span[1] * .07, span[2] * .09), .05)
    plate('13 Emitter hub', 'dark', (span[0] * .26, span[1] * .22, span[2] * .26),
          (c[0], lo[1] + span[1] * .34, c[2]), .35)
    for i, (dx, dz) in enumerate(((-.34, -.30), (.34, -.30), (.34, .30), (-.34, .30))):
        strut(f'14 Buttress {i}', 'dark', (c[0] + dx * span[0] * .5, lo[1] + 2.0,
                                           c[2] + dz * span[2] * .5),
              (c[0] + dx * span[0] * .34, lo[1] + span[1] * .30, c[2] + dz * span[2] * .34),
              2.2, 2.2)
        plate(f'15 Buttress pad {i}', 'base', (span[0] * .10, 4.0, span[2] * .10),
              (c[0] + dx * span[0] * .48, lo[1] + 3.0, c[2] + dz * span[2] * .48), .3)
    x_beam('20 Cross span', 'base', limits, 5.0, span[2] * .20, lo[1] + span[1] * .55)
    z_rail('21 Service rail', 'dark', limits, 4.0, 4.0, lo[1] + span[1] * .12)
    column('22 Spire spine', 'trim', limits, lo[1] + span[1] * .28, hi[1] - 2.4,
           span[0] * .10, span[2] * .10)
    top_cap('23 Emitter spire', 'accent', limits, (span[0] * .16, 4.5, span[2] * .16))
    plate('24 Spire collar', 'lit', (span[0] * .10, 1.6, span[2] * .10),
          (c[0], hi[1] - 10.0, c[2]), .2)
    detail_layer(limits, faction, span[0] * .40, span[2] * .38, lo[1] + span[1] * .18, 0.0)


def build_planet_pulsar_cannon(limits, faction):
    lo, hi, c, span = frame(limits)
    plinth(limits, faction)
    plate('10 Breech block', 'base', (span[0] * .42, span[1] * .40, span[2] * .40),
          (c[0], lo[1] + span[1] * .34, c[2] - span[2] * .16), .35)
    plate('11 Breech collar', 'trim', (span[0] * .46, 3.2, span[2] * .44),
          (c[0], lo[1] + span[1] * .55, c[2] - span[2] * .16), .3)
    plate('12 Turntable', 'dark', (span[0] * .30, span[1] * .10, span[2] * .30),
          (c[0], lo[1] + span[1] * .16, c[2] + span[2] * .06), .3)
    # The barrel runs from the breech to the +Z extreme: it is the reach part that sets both Z
    # sides with the breech, and its base overlaps the turntable so the weld chain is continuous.
    barrel_z0, barrel_z1 = c[2] + span[2] * .10, hi[2]
    barrel_len = barrel_z1 - barrel_z0
    strut('13 Barrel', 'base', (c[0], lo[1] + span[1] * .30, barrel_z0),
          (c[0], lo[1] + span[1] * .30, barrel_z1),
          span[0] * .15, span[1] * .13, .4)
    # Bands step along the barrel's own length, so the last one cannot march off its end and
    # leave a brace-length gap to the barrel it is supposed to collar.
    for i in range(4):
        plate(f'14 Barrel band {i}', 'trim', (span[0] * .34, span[1] * .30, span[2] * .04),
              (c[0], lo[1] + span[1] * .30, barrel_z0 + barrel_len * (.14 + .20 * i)), .3)
    plate('15 Muzzle', 'accent', (span[0] * .30, span[1] * .26, span[2] * .05),
          (c[0], lo[1] + span[1] * .30, hi[2] - span[2] * .03), .3)
    bank('16 Breech machinery', 'dark', 3, (span[0] * .10, span[1] * .08, span[2] * .10),
         (c[0] - span[0] * .22, lo[1] + span[1] * .20, c[2] - span[2] * .30),
         (span[0] * .11, 0, 0))
    bank('17 Breech vents', 'cool', 3, (span[0] * .05, span[1] * .04, span[2] * .05),
         (c[0] - span[0] * .21, lo[1] + span[1] * .30, c[2] - span[2] * .30),
         (span[0] * .10, 0, 0))
    x_beam('20 Breech span', 'base', limits, 5.0, span[2] * .22, lo[1] + span[1] * .40)
    z_rail('21 Recoil rail', 'dark', limits, 4.0, 4.0, lo[1] + span[1] * .08)
    column('22 Sight spine', 'trim', limits, lo[1] + span[1] * .26, hi[1] - 2.4,
           span[0] * .10, span[2] * .10)
    top_cap('23 Sight mast', 'accent', limits, (span[0] * .16, 4.5, span[2] * .14))
    bank('24 Marker lights', 'lit', 3, (2.2, 1.6, 2.2),
         (c[0] - span[0] * .20, hi[1] - 8.0, c[2] - span[2] * .26), (span[0] * .10, 0, 0))
    # The detail ring is centred near the breech and kept small: at 0.74 of a radius taken from
    # the *whole* depth and centred on the breech it put a machinery block 3.1 units below the
    # envelope's rear face.
    detail_layer(limits, faction, span[0] * .34, span[2] * .26, lo[1] + span[1] * .16,
                 -span[2] * .06)


BUILDERS = {
    'defense_satellite': build_defense_satellite,
    'attack_satellite': build_attack_satellite,
    'planet_extractor': build_planet_extractor,
    'planet_trade_hub': build_planet_trade_hub,
    'planet_shield_generator': build_planet_shield_generator,
    'planet_pulsar_cannon': build_planet_pulsar_cannon,
}


def build(key):
    identifier, radius, limits, faction = SEEDS[key]
    master = ROOT / f'art/blender/{identifier}.blend'
    if master.exists() and '--replace-seed' not in sys.argv:
        raise RuntimeError(f'{master.name} is the editable master. Use export_{identifier}.py; '
                           f'--replace-seed destroys edits.')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    kind = key.split(':')[1]
    BUILDERS[kind](limits, faction)
    # Nothing floats: a kit is authored by centre and by reach, so contact is not implied. The
    # pass reports what it joined, and the extent self-check still runs after it.
    weld_scene()
    report_bounds(limits, identifier)
    features = dict(
        authority='script', approval='pending_owner_approval', binding=key,
        data_id=kind, original_design=True,
        design=DESIGNS[(kind, faction)],
        legacy_envelope=[list(a) for a in limits],
        seed_recipe='tools/art/build_b4_hardware.py; script-authoritative per the S03 '
                    'source-authority policy for modular hardware - the recipe is the master, '
                    'the .blend is derived',
        station_kind=kind, station_radius=radius, faction=faction,
        provenance='Original geometry generated by this recipe; no external mesh or texture '
                   'dependencies')
    bpy.context.scene['asset'] = identifier
    bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
    bpy.context.scene['authority'] = 'script'
    bpy.context.scene['design'] = DESIGNS[(kind, faction)]
    bpy.context.scene['binding'] = key
    bpy.context.scene['review'] = 'pending owner approval - not a production binding'
    bpy.context.scene['coordinates'] = 'X beam; Y up; +Z forward'
    bpy.context.scene['runtime'] = 'immutable evaluated triangles; no runtime Blender'
    bpy.context.preferences.filepaths.save_version = 0
    master.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
    print(f'SEED_OK {key} -> {master.name}')


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--all' in argv:
        keys = list(SEEDS)
    elif '--asset' in argv:
        keys = [argv[argv.index('--asset') + 1]]
    else:
        raise SystemExit('usage: --all | --asset <faction:kind>')
    for key in keys:
        if key not in SEEDS:
            raise SystemExit(f'unknown binding {key}; known: {sorted(SEEDS)}')
        build(key)


main()
