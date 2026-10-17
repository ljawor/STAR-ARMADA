#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPES ONLY. Each editable .blend is authoritative afterwards.

S06 batch B3a - the three faction command stations, the largest and most visible
station in each fleet:

  rebel:command_station        alliance_command_station   (radius 130, legacy  2,112 tri)
  confederacy:command_station  legion_command_station     (radius 130, legacy  1,616 tri)
  syndicate:command_station    syndicate_command_station  (radius 130, legacy  1,120 tri)

Each mesh is authored inside its binding's legacy procedural extents, so the station
contact/ray helpers that read `render.fleet_geometry.station_mesh` derive the same
footprint as the procedural layout it replaces and the unchanged gameplay radius in
`assets/data/stations/stations.json` still frames it. Three distinct designs - a ring
habitat, an angular citadel and a scaffolded redoubt - sharing a kit of station
primitives, not one body with different paint. No proprietary geometry or textures.
None of these replaces a production binding, and `rebel:shipyard` is deliberately absent:
that binding is already delivered as the approved trio's `core` asset `alliance_shipyard`.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b3_stations.py -- --all
    Blender --background --python-exit-code 1 --python tools/art/build_b3_stations.py -- --asset rebel:command_station
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDENTIFIERS = {
    'rebel:command_station': 'alliance_command_station',
    'confederacy:command_station': 'legion_command_station',
    'syndicate:command_station': 'syndicate_command_station',
}
_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_masters(argv):
    """Refuse before Blender is imported, and before any target is written.

    One seed authors all three masters; a half-run that dies on the second leaves the
    batch inconsistent, so pre-flight every target. An empty argument list is treated as
    "all" deliberately: the seed is only ever driven by Blender with an explicit `--`, so
    the no-argument case is the refusal guard's own path, not a silent author-everything.
    """
    if not argv or '--all' in argv:
        targets = list(IDENTIFIERS)
    elif '--asset' in argv:
        targets = [argv[argv.index('--asset') + 1]]
    else:
        targets = []
    for key in targets:
        master = ROOT / f'art/blender/{IDENTIFIERS[key]}.blend'
        if master.exists() and '--replace-seed' not in argv:
            raise RuntimeError(f'{master.name} is the editable master. Use '
                               f'export_{IDENTIFIERS[key]}.py; --replace-seed destroys edits.')


_refuse_existing_masters(_ARGV)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import mesh_object, loft, plate, annulus, cylinder  # noqa: E402
import bpy  # noqa: E402,F401


# ---------------------------------------------------------------- station kit
# The fleet kit is a hull vocabulary (transverse frames along Z). A station is not a hull:
# it is radial structure, so it needs rings on a vertical axis, members between arbitrary
# points, and rows of small blocks.

def torus(name, role, y, radius, tube, m=24, n=8, sx=1.0, sz=1.0, bevel=0):
    """A habitat band: a ring in the XZ plane, its axis vertical (Y).

    `sx`/`sz` make the centre line an ellipse, which is what a station footprint needs:
    the binding's legacy extent is nowhere near circular (the Alliance command station is
    96 wide and 59 deep). A ring *on* another band's outer surface is the same call with
    `sx + tube/radius` and `sz + tube/radius` - that offset is exact for a torus, so a
    stripe never sinks into the band it decorates.
    """
    verts = []
    for i in range(m):
        a = 2 * math.pi * i / m
        cx, cz = radius * sx * math.cos(a), radius * sz * math.sin(a)
        for j in range(n):
            b = 2 * math.pi * j / n
            verts.append((cx + tube * math.cos(a) * math.cos(b), y + tube * math.sin(b),
                          cz + tube * math.sin(a) * math.cos(b)))
    faces = []
    for i in range(m):
        i2 = (i + 1) % m
        for j in range(n):
            j2 = (j + 1) % n
            faces.append((i * n + j, i2 * n + j, i2 * n + j2, i * n + j2))
    return mesh_object(name, role, verts, faces, bevel)


def ringy(name, role, cx, cz, y, outer, inner, thickness, n=16):
    """A horizontal rim, collar or deck edge: an annulus whose axis is vertical."""
    verts = []
    for yy in (y - thickness / 2, y + thickness / 2):
        for r in (outer, inner):
            verts.extend((cx + r * math.cos(i * 2 * math.pi / n), yy,
                          cz + r * math.sin(i * 2 * math.pi / n)) for i in range(n))
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
    """A rectangular member between two points - trusses, booms, buttresses, cranes."""
    axis = [b[i] - a[i] for i in range(3)]
    length = math.sqrt(sum(v * v for v in axis))
    u = [v / length for v in axis]
    ref = [0., 1., 0.] if abs(u[1]) < .9 else [1., 0., 0.]
    v = [u[1] * ref[2] - u[2] * ref[1], u[2] * ref[0] - u[0] * ref[2], u[0] * ref[1] - u[1] * ref[0]]
    n = math.sqrt(sum(t * t for t in v))
    v = [t / n for t in v]
    w = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    verts = []
    for end in (a, b):
        for sw, sh in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(end[i] + v[i] * half_w * sw + w[i] * half_h * sh for i in range(3)))
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_object(name, role, verts, faces, bevel)


def bank(name, role, count, size, start, step, bevel=.2):
    """A row of small blocks: machinery, vents, container stacks, window bays."""
    for i in range(count):
        plate(f'{name} {i}', role, size,
              tuple(start[k] + step[k] * i for k in range(3)), bevel)


def report_bounds(limits, label):
    """Print the evaluated extents and every breach, so one build names them all.

    Iterating through the exporter instead costs a full build per axis; this reports the
    whole set on the run that authors the master, measured after the bevel modifiers.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo = [1e9] * 3
    hi = [-1e9] * 3
    extreme = [['', ''] for _ in range(3)]
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
        evaluated.to_mesh_clear()
    print(f'BOUNDS {label} lo={[round(v, 2) for v in lo]} hi={[round(v, 2) for v in hi]}')
    for i, axis in enumerate('XYZ'):
        if lo[i] < limits[i][0] - 1e-6:
            print(f'  BREACH {label} {axis} low {lo[i]:.2f} < {limits[i][0]} '
                  f'from {extreme[i][0]}')
        if hi[i] > limits[i][1] + 1e-6:
            print(f'  BREACH {label} {axis} high {hi[i]:.2f} > {limits[i][1]} '
                  f'from {extreme[i][1]}')


def collar(name, role, cx, cz, y, outer, inner, thickness, n=16):
    """A hollow rim around a vertical axis - a docking collar never caps its own aperture."""
    ringy(name, role, cx, cz, y, outer, inner, thickness, n)


# ------------------------------------------------------- rebel: command station
def build_alliance_command_station():
    """Ring habitat: an elliptical band, an inboard deck, an armoured hub and a crown.

    The binding's extent is 96 wide and only 59 deep, so the rings are ellipses - the same
    shape decision the legacy `_ellipse` layout made. Every stripe is a thin ring centred on
    the band's own outer surface (`sx + tube/radius`), so it never sinks into the band.
    """
    torus('01 Habitat band', 'base', 1.5, 34.0, 5.5, 24, 8, 1.250, .7088)
    torus('02 Inboard deck', 'trim', 0.5, 20.0, 4.0, 24, 8, 1.085, .480)
    torus('03 Accent band', 'accent', 4.2, 34.0, .85, 24, 4, 1.3865, .8455)
    torus('04 Guide band', 'cool', -2.6, 34.0, .70, 24, 4, 1.391, .850)
    for i in range(12):
        a = math.radians(i * 30)
        ca, sa = math.cos(a), math.sin(a)
        strut(f'05 Spoke brace {i}', 'trim', (20.0 * ca, 0.5, 9.0 * sa),
              (37.9 * ca, 1.5, 18.6 * sa), 1.2, 2.1)
        if i % 4 == 1:
            strut(f'06 Lateral stay {i}', 'dark', (24.0 * ca, -3.0, 13.0 * sa),
                  (30.0 * ca, 5.5, 15.0 * sa), .9, 1.4)
    # Armoured hub, command tower and its lit crown; nothing above the binding's ceiling.
    cylinder('07 Hub drum', 'base', (0, 6.5, 0), 12.0, 18.0, axis='Y', n=16)
    cylinder('08 Hub belt', 'dark', (0, 6.0, 0), 13.0, 4.0, axis='Y', n=16)
    cylinder('09 Command tower', 'base', (0, 19.0, 0), 7.0, 8.0, axis='Y', n=12)
    cylinder('10 Tower crown', 'lit', (0, 24.0, 0), 5.4, 2.0, axis='Y', n=12)
    ringy('11 Crown rim', 'cool', 0, 0, 23.4, 6.6, 5.7, 1.0, 12)
    cylinder('12 Mast', 'dark', (0, 25.68, 0), 1.3, 1.6, axis='Y', n=8)
    # Habitats and machinery around the inboard deck, which is where the crew actually is.
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        ca, sa = math.cos(a), math.sin(a)
        plate(f'13 Habitation module {i}', 'dark', (7, 5, 8), (24.0 * ca, 3.6, 13.0 * sa), .5)
        plate(f'14 Module lamps {i}', 'lit', (4, .6, 5), (24.0 * ca, 6.3, 13.0 * sa), .2)
    bank('15 Machinery bank', 'dark', 5, (4.6, 3.0, 4.6), (-9.0, 16.6, -4.0), (4.6, 0, 0), .3)
    bank('16 Vent bank', 'trim', 4, (4.0, 2.4, 4.0), (-7.5, 16.5, 5.5), (5.0, 0, 0), .3)
    for cx, cz in ((38.0, 0.0), (-38.0, 0.0), (0.0, 21.0), (0.0, -21.0)):
        collar(f'17 Ring collar {cx:.0f} {cz:.0f}', 'trim', cx, cz, 1.5, 7.5, 5.5, 3.0, 12)
    for cx, cz in ((6.0, 6.0), (-6.0, 6.0), (6.0, -6.0), (-6.0, -6.0)):
        collar(f'21 Docking port {cx:.0f} {cz:.0f}', 'base', cx, cz, 17.0, 5.0, 3.4, 3.0, 10)
    plate('18 Keel plate', 'dark', (76, 1.8, 52), (0, -5.2, 0), .4)
    plate('19 Keel strake', 'cool', (68, .8, 46), (0, -6.4, 0), .2)
    for i in range(4):
        a = math.radians(i * 90 + 45)
        strut(f'20 Keel brace {i}', 'base', (13.8 * math.cos(a), -4.6, 7.9 * math.sin(a)),
              (42.5 * math.cos(a), -4.4, 24.1 * math.sin(a)), 1.3, 1.6)
    report_bounds(SEEDS['rebel:command_station']['limits'], 'alliance_command_station')


# -------------------------------------------------- confederacy: command station
def build_legion_command_station():
    """Angular citadel: a hex platform carrying a wedge keep, buttresses, booms and a mast."""
    ringy('01 Hex platform', 'base', 0, 0, -1.0, 32.0, 26.0, 5.0, 6)
    ringy('02 Platform rim', 'accent', 0, 0, 1.9, 32.4, 30.0, 1.2, 6)
    ringy('03 Platform guide', 'cool', 0, 0, -3.9, 30.0, 27.0, 1.0, 6)
    loft('04 Keep', 'base',
         ((-38.0, 7.0, 15.0, 2.0), (-24.0, 18.0, 30.0, -4.0), (-4.0, 22.0, 40.0, -5.0),
          (20.0, 20.0, 36.0, -4.0), (42.0, 12.0, 24.0, 2.0), (60.0, 4.5, 13.0, 8.0)), .5)
    loft('05 Keep crest', 'dark',
         ((-30.0, 3.4, 33.0, 26.0), (-8.0, 4.6, 40.2, 36.0), (24.0, 3.0, 38.0, 30.0)), .3)
    loft('06 Keep accent', 'accent',
         ((-26.0, 1.0, 30.6, 28.0), (22.0, 1.0, 36.6, 34.0)), .2)
    # Flank plating and window bands stand proud of the keep, whose half width is 15 / 21.7 /
    # 20.3 / 12.4 at these z - measured off the section list above, not guessed.
    for z, hw, role, tall in ((-30.0, 15.0, 'lit', 2.0), (-6.0, 21.7, 'trim', 9.0),
                              (18.0, 20.3, 'lit', 2.0), (40.0, 12.4, 'trim', 7.0)):
        for side in (-1, 1):
            plate(f'07 Flank panel {z:.0f} {side}', role, (1.4, tall, 12.0),
                  (side * (hw + .6), 14.0, z), .2)
    for z, hw in ((-32.0, 13.0), (4.0, 22.0), (30.0, 17.0)):
        for side in (-1, 1):
            plate(f'08 Flank armour {z:.0f} {side}', 'base', (2.0, 5.0, 10.0),
                  (side * (hw + .7), 6.0, z), .3)
    for s in (-1, 1):
        strut(f'09 Buttress {s}', 'base', (s * 28.0, -4.0, 6.0), (s * 16.0, 24.0, -2.0), 1.6, 2.2)
        strut(f'10 Lower stay {s}', 'dark', (s * 30.0, -4.0, 20.0), (s * 17.0, 8.0, 24.0), 1.0, 1.4)
        strut(f'11 Work boom {s}', 'trim', (s * 20.0, 8.0, -14.0), (s * 47.0, 14.0, -30.0), 1.5, 1.9)
        cylinder(f'12 Boom pod {s}', 'base', (s * 47.4, 14.0, -32.0), 6.4, 12.0, axis='X', n=12)
        cylinder(f'13 Pod sleeve {s}', 'lit', (s * 47.2, 14.0, -32.0), 6.55, 3.0, axis='X', n=12)
        plate(f'14 Pod accent {s}', 'accent', (9.0, 1.0, 3.2), (s * 47.4, 20.8, -32.0), .2)
        strut(f'15 Outrigger mount {s}', 'trim', (s * 18.0, 4.0, 22.0), (s * 28.0, 4.0, 22.0), 1.4, 2.0)
        cylinder(f'16 Outrigger {s}', 'trim', (s * 30.0, 4.0, 22.0), 5.0, 10.0, axis='X', n=10)
    cylinder('17 Mast spine', 'base', (0, 33.0, 30.0), 3.0, 10.0, axis='Y', n=8)
    cylinder('18 Sensor dish', 'trim', (0, 38.6, 30.0), 7.0, 2.0, axis='Y', n=12)
    ringy('19 Dish rim', 'cool', 0, 30.0, 39.2, 7.4, 6.2, 1.0, 12)
    collar('20 Bow collar', 'base', 0.0, 52.9, 9.0, 7.0, 5.6, 3.0, 12)
    for s in (-1, 1):
        collar(f'24 Platform port {s}', 'base', s * 26.0, 0.0, 3.0, 6.0, 4.0, 3.0, 10)
    plate('23 Base plate', 'dark', (64, 1.6, 84), (0, -5.2, 10.0), .4)
    for s in (-1, 1):
        bank(f'21 Platform machinery {s}', 'trim', 4, (5.0, 2.4, 6.0), (s * 27.0, 2.0, -20.0),
             (0, 0, 8.0), .3)
    for i, (y, z) in enumerate(((37.4, -18.0), (40.3, -2.0), (39.2, 14.0))):
        plate(f'22 Crest fin {i}', 'dark', (1.6, 2.6, 8.0), (0, y, z), .2)
    report_bounds(SEEDS['confederacy:command_station']['limits'], 'legion_command_station')


# --------------------------------------------------- syndicate: command station
def build_syndicate_command_station():
    """Scaffolded redoubt: an offset tower, a bolted wreck belt, booms and gantries."""
    cylinder('01 Tower base', 'base', (-7.0, 0.0, 5.0), 17.0, 9.0, axis='Y', n=14)
    cylinder('02 Tower belt', 'dark', (-7.0, 6.0, 5.0), 15.0, 3.0, axis='Y', n=14)
    cylinder('03 Tower mid', 'base', (-7.0, 13.0, 5.0), 12.0, 10.0, axis='Y', n=14)
    cylinder('04 Tower accent', 'accent', (-7.0, 15.5, 5.0), 12.7, 1.6, axis='Y', n=14)
    cylinder('05 Tower head', 'trim', (-7.0, 24.0, 5.0), 8.0, 10.0, axis='Y', n=12)
    cylinder('06 Head lights', 'lit', (-7.0, 29.5, 5.0), 7.0, 2.6, axis='Y', n=12)
    cylinder('07 Mast', 'dark', (-7.0, 38.4, 5.0), 1.6, 12.8, axis='Y', n=8)
    cylinder('08 Mast cap', 'cool', (-7.0, 45.0, 5.0), 2.6, 1.2, axis='Y', n=8)
    # Wreck belt: scrapped sections bolted round the tower at mixed heights and angles, kept
    # inside the binding's asymmetric extent (48 to starboard, -52.16 to port).
    scrap = ((-39.16, -2.0, -22.0, 26.0, 22.0), (-24.0, 9.0, -44.66, 26.0, 18.0),
             (-38.0, 14.0, 6.0, 22.0, 16.0), (-30.0, -9.0, 26.0, 28.0, 12.0),
             (-16.0, 20.0, -30.0, 20.0, 8.0), (24.0, 6.0, -36.0, 24.0, 16.0),
             (18.0, -9.0, -18.0, 30.0, 24.0), (32.0, 17.0, -8.0, 20.0, 9.0),
             (26.0, -6.0, 22.0, 26.0, 14.0), (12.0, 12.0, 26.0, 22.0, 12.0),
             (-8.0, -9.0, 26.0, 24.0, 10.0), (-30.0, 26.0, 22.0, 18.0, 8.0))
    for i, (x, y, z, w, l) in enumerate(scrap):
        loft(f'09 Wreck section {i}', 'dark' if i % 3 else 'base',
             ((-l / 2, w / 2, 4.0, -4.0), (0, w * .275, 5.0, -5.0), (l / 2, w / 2, 4.0, -4.0)), .3,
             (x, y, z), .3)
        plate(f'10 Section bolt {i}', 'trim', (3.0, 1.4, l * .4), (x, y + 5.4, z), .2)
    strut('11 Gantry leg left', 'base', (-46.0, -12.0, 26.0), (-10.0, 28.0, 4.0), 1.8, 2.4)
    strut('12 Gantry leg starboard', 'base', (30.0, -12.0, 26.0), (-4.0, 28.0, 4.0), 1.8, 2.4)
    strut('13 Gantry beam', 'trim', (-46.0, -12.0, 26.0), (30.0, -12.0, 26.0), 1.4, 1.8)
    strut('14 Starboard boom', 'trim', (-4.0, 16.0, 6.0), (40.0, 10.0, -22.0), 1.6, 2.0)
    strut('15 Left spur', 'trim', (-8.0, 12.0, 4.0), (-46.0, 6.0, 12.0), 1.6, 2.0)
    cylinder('16 Salvage cab', 'base', (42.0, 10.0, -24.0), 5.4, 12.0, axis='X', n=10)
    plate('17 Cab lights', 'lit', (12.0, 1.2, 3.0), (42.0, 14.6, -24.0), .2)
    cylinder('18 Left cab', 'base', (-44.0, 6.0, 14.0), 5.0, 10.0, axis='X', n=10)
    plate('19 Left cab lights', 'lit', (11.0, 1.2, 2.8), (-44.0, 10.2, 14.0), .2)
    strut('20 Crane mast', 'dark', (18.0, 5.0, -40.0), (18.0, 26.0, -40.0), 1.2, 1.6)
    strut('21 Crane jib', 'dark', (18.0, 26.0, -40.0), (2.0, 22.0, -34.0), 1.0, 1.2)
    plate('22 Crane block', 'trim', (3.6, 3.0, 3.0), (2.0, 18.6, -34.0), .2)
    collar('23 Collar aft', 'base', -28.0, -38.0, 2.0, 10.0, 7.4, 3.4, 12)
    collar('24 Collar fore', 'base', 20.0, 31.0, 12.0, 7.4, 5.2, 3.0, 12)
    collar('29 Mast port', 'base', -7.0, 5.0, 30.9, 5.0, 3.6, 3.0, 10)
    collar('30 Cab port', 'base', 42.0, -24.0, 16.4, 5.0, 3.6, 3.0, 10)
    for i, (x, z, l) in enumerate(((-30.0, -18.0, 42.0), (10.0, -26.0, 40.0), (24.0, 16.0, 30.0))):
        strut(f'25 Scaffold rail {i}', 'dark', (x - l / 2, -11.0, z), (x + l / 2, -11.0, z), 1.0, 1.2)
        strut(f'26 Scaffold post {i}', 'dark', (x, -11.0, z), (x, 2.0, z), 1.0, 1.2)
    plate('27 Keel deck', 'base', (74.0, 1.8, 40.0), (-6.0, -14.3, -6.0), .4)
    plate('28 Keel strake', 'cool', (66.0, .8, 1.4), (-6.0, -14.4, 2.0), .2)
    report_bounds(SEEDS['syndicate:command_station']['limits'], 'syndicate_command_station')


SEEDS = {
    'rebel:command_station': dict(
        identifier='alliance_command_station', data_id='command_station',
        builder=build_alliance_command_station,
        design='Alliance command station - twin habitat bands on twelve trusses, armoured '
               'hub with a lit crown and four docking collars',
        limits=((-48.0, 48.0), (-6.8, 26.48), (-29.6, 29.6)), min_length=59.0,
        mesh_cap=(11500, 8000)),
    'confederacy:command_station': dict(
        identifier='legion_command_station', data_id='command_station',
        builder=build_legion_command_station,
        design='Legion command station - hex platform carrying an angular citadel with '
               'buttresses, twin work booms, a dorsal mast and a forward collar',
        limits=((-53.8231, 53.8231), (-6.0, 41.6), (-38.4, 60.0)), min_length=98.0,
        mesh_cap=(11500, 8000)),
    'syndicate:command_station': dict(
        identifier='syndicate_command_station', data_id='command_station',
        builder=build_syndicate_command_station,
        design='Syndicate command station - offset scaffold tower inside a bolted wreck '
               'belt, gantry frame, salvage booms and an underside scaffold',
        limits=((-52.1606, 48.0), (-15.2, 45.6), (-53.6606, 38.4883)), min_length=91.8,
        mesh_cap=(11500, 8000)),
}


def build(key):
    spec = SEEDS[key]
    master = ROOT / f'art/blender/{spec["identifier"]}.blend'
    if master.exists() and '--replace-seed' not in sys.argv:
        raise RuntimeError(
            f'{master.name} is the editable master. Use export_{spec["identifier"]}.py; '
            f'--replace-seed destroys edits.')
    # alliance_common's import already emptied the startup scene and built the role
    # materials; a per-asset reset must not reload factory settings or those materials go
    # with it (`ReferenceError: StructRNA of type Material has been removed`).
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    spec['builder']()
    features = dict(
        authority='blend', approval='pending_owner_approval', binding=key,
        data_id=spec['data_id'], original_design=True, design=spec['design'],
        legacy_envelope=[list(a) for a in spec['limits']],
        seed_recipe='tools/art/build_b3_stations.py; initial authoring only, never rebuild hand edits',
        station_kind=spec['data_id'],
        provenance='Original geometry authored in Blender; no external mesh or texture dependencies')
    bpy.context.scene['asset'] = spec['identifier']
    bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
    bpy.context.scene['authority'] = 'blend'
    bpy.context.scene['design'] = spec['design']
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
        raise SystemExit('usage: --all | --asset <faction:command_station>')
    for key in keys:
        if key not in SEEDS:
            raise SystemExit(f'unknown binding {key}; known: {sorted(SEEDS)}')
        build(key)


main()
