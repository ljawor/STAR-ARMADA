#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPES ONLY. Each editable .blend is authoritative afterwards.

S06 batch B3b, slice 1 - the three smallest station kinds across every faction that has a
`render.asset_selection.mesh_for` seam:

  <faction>:mining_station   radius 70   - an extraction and processing platform
  <faction>:sensor_station   radius 45   - a listening post
  <faction>:energy_relay     radius 55   - a power distribution hub

Nine meshes from one seed, three distinct designs per kind (alliance / legion / syndicate),
sharing a station kit of rings, members and block rows. Every dimension is derived from the
binding's own legacy extent (see `frame`), and each design carries keel, rail and mast parts
that land that extent exactly, because the review harness requires the authored footprint to
*reach* the legacy one - a station that merely fits inside it frames and collides differently.

Absent deliberately: the ten imperial stations (`render.fleet_geometry.station_mesh`
dispatches them straight to `_station_mesh(did)` with no seam), `rebel:shipyard` (already the
approved trio's `core` asset `alliance_shipyard`) and the six satellite / planet-installation
rows, which are not stations.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b3b_stations.py -- --all
    Blender --background --python-exit-code 1 --python tools/art/build_b3b_stations.py -- --asset rebel:mining_station
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# An extent error below this many world units is float noise, not a breach: the bevel
# evaluation lands a part a hair outside a 92.8-unit span (1.5e-06 measured on
# alliance_sensor_station's keel strake, 1.6e-08 relative) and the exporter's edge quantiser
# snaps it to the declared edge. The smallest *real* under-reach this batch fixed was 0.03
# units, thirty thousand times larger, so a tighter tolerance only prints false alarms - and a
# self-check that cries wolf is one nobody reads. The count is printed either way, so a clean
# extent states itself instead of being implied by silence.
BREACH_TOLERANCE = 1e-3


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


# kind -> {binding: (identifier, limits per axis, drawn length, treatment)}
SEEDS = {
    'rebel:mining_station': ('alliance_mining_station', 70,
                             [[-44.8, 44.8], [-15.6, 10.12], [-26.0, 22.8294]], 'alliance'),
    'confederacy:mining_station': ('legion_mining_station', 70,
                                   [[-40.6686, 40.6686], [-31.44, 11.08], [-29.36, 46.96]],
                                   'legion'),
    'syndicate:mining_station': ('syndicate_mining_station', 70,
                                 [[-33.9322, 42.4], [-32.4, 39.6], [-25.0848, 41.4431]],
                                 'syndicate'),
    'rebel:sensor_station': ('alliance_sensor_station', 45,
                             [[-46.4, 46.4], [-12.8, 30.48], [-24.8, 16.24]], 'alliance'),
    'confederacy:sensor_station': ('legion_sensor_station', 45,
                                   [[-36.1913, 36.1913], [-14.0, 38.4], [-28.2851, 34.8]],
                                   'legion'),
    'syndicate:sensor_station': ('syndicate_sensor_station', 45,
                                 [[-47.2, 26.3565], [-17.6, 43.857], [-31.137, 21.1423]],
                                 'syndicate'),
    'rebel:energy_relay': ('alliance_energy_relay', 55,
                           [[-50.4, 50.4], [-8.4078, 13.2078], [-29.36, 20.9846]], 'alliance'),
    'confederacy:energy_relay': ('legion_energy_relay', 55,
                                 [[-41.4372, 41.4372], [-16.0, 31.6], [-25.7713, 46.4]],
                                 'legion'),
    'syndicate:energy_relay': ('syndicate_energy_relay', 55,
                               [[-47.5594, 46.5284], [-11.2, 23.36], [-46.5402, 34.4011]],
                               'syndicate'),
}
KINDS = {'mining_station': 'Mining Station', 'sensor_station': 'Sensor Station',
         'energy_relay': 'Energy Relay'}
DATA_IDS = {'alliance': 'rebel', 'legion': 'confederacy', 'syndicate': 'syndicate'}
DESIGNS = {
    ('mining_station', 'alliance'): 'elliptical processing ring with a hopper drum and four drill booms',
    ('mining_station', 'legion'): 'twin-arm extractor on a long keel with an ore silo',
    ('mining_station', 'syndicate'): 'open truss drilling rig with lashed ore drums and a hab cab',
    ('sensor_station', 'alliance'): 'lattice disc carrying a mast and three dishes',
    ('sensor_station', 'legion'): 'blade spine with a stacked array and a forward dish',
    ('sensor_station', 'syndicate'): 'crooked scaffold of bolted dishes',
    ('energy_relay', 'alliance'): 'twin collector rings on a spine with radiator panels',
    ('energy_relay', 'legion'): 'stepped cell column with coolant fins',
    ('energy_relay', 'syndicate'): 'chain of power cells on a truss with cable runs',
}
_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_masters(argv):
    """Refuse before Blender is imported, and before any target is written.

    One seed authors nine masters; a half-run that dies on the fifth leaves the batch
    inconsistent, so pre-flight every target. An empty argument list is treated as "all"
    deliberately: the seed is only ever driven by Blender with an explicit `--`, so the
    no-argument case is the refusal guard's own path, not a silent author-everything.
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


# ---------------------------------------------------------------- station kit
# A station is radial structure, not a hull, so it needs rings on a vertical axis, members
# between arbitrary points and rows of small blocks. Copied from the B3a seed: the two
# batches are separate seeds (one refuses to overwrite the other's masters) and the shared
# vocabulary is deliberately duplicated rather than moved into a third module.

def torus(name, role, y, radius, tube, m=24, n=8, sx=1.0, sz=1.0, bevel=0, cx=0., cz=0.):
    """A band: a ring in the XZ plane, its axis vertical (Y).

    `sx`/`sz` make the centre line an ellipse and `cx`/`cz` offset it, which a station
    footprint needs: the binding's legacy extent is neither circular (the Alliance mining
    station is 89.6 wide and 48.8 deep) nor centred on the origin.
    """
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


def ring_blocks(name, role, count, cx, cz, y, rx, rz, size, phase=0.):
    """Blocks spaced around an ellipse: machinery bays on a ring, deck or spine."""
    for i in range(count):
        a = 2 * math.pi * (i / count + phase)
        plate(f'{name} {i}', role, size,
              (cx + rx * math.cos(a), y, cz + rz * math.sin(a)), .3)


def bays(limits, rx, rz, y, cz, phase=0.):
    """Detail layer every station carries: an inner concentric band and two rows of bays.

    Radii are 0.62 and 0.78 of the ring the caller names and the block size is capped, so the
    named ring stays the widest thing on the station and the binding's extent is still reached
    by real structure rather than by a greeble. The rows are deliberately role-separated:
    `dark` machinery and a `cool` vent row are what the review's per-role ablations measure on
    a small station, whose own parts are too few to move those numbers on their own.
    """
    lo, hi, c, span = frame(limits)
    torus('90 Inner band', 'trim', float(y), rx * .62, 1.5, m=44, n=12, sx=1.,
          sz=rz / rx, cz=cz)
    ring_blocks('91 Bay machinery', 'dark', 16, c[0] * .2, cz, float(y) + 1.9, rx * .78,
                rz * .78, (4.6, 3.0, 4.6), phase)
    ring_blocks('92 Bay vents', 'cool', 16, c[0] * .2, cz, float(y) + 3.7, rx * .74, rz * .74,
                (2.4, 1.4, 2.4), phase + .11)
    # `base` and `lit`: the production loader rejects any authored mesh with an empty material
    # role (`set(batches) == set(ROLES)` and every batch non-empty), and no design here used
    # either - so the detail layer supplies a plating ring and a beacon ring on every station.
    ring_blocks('93 Base plating', 'base', 12, c[0] * .2, cz, float(y) - 2.2, rx * .7, rz * .7,
                (6.0, 1.4, 4.2), phase + .05)
    # The lights used to sit at `y + 6.4`, which is 1.4 units of clear air above the vent row
    # (`y + 3.7` plus its 1.4 height) - seven pixels of daylight in a close capture, on all
    # nine stations. One light per vent, on the vent row's own radius and phase, so each is
    # bolted to the vent under it.
    ring_blocks('94 Marker lights', 'lit', 16, c[0] * .2, cz, float(y) + 5.0, rx * .74,
                rz * .74, (1.6, 1.2, 1.6), phase + .11)


def bank(name, role, count, size, start, step, bevel=.2):
    """A row of small blocks: machinery, vents, canisters, window bays."""
    for i in range(count):
        plate(f'{name} {i}', role, size,
              tuple(start[k] + step[k] * i for k in range(3)), bevel)


def frame(limits):
    """The binding's own legacy extent, split into lo/hi, centre and span per axis."""
    lo = [a[0] for a in limits]
    hi = [a[1] for a in limits]
    return lo, hi, [(lo[i] + hi[i]) / 2 for i in range(3)], [hi[i] - lo[i] for i in range(3)]


def report_bounds(limits, label):
    """Print the evaluated extents and every breach, so one build names them all."""
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
    tris = 0
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        tris += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
    # The export wrapper refuses under 1,800 triangles, so a master that cannot clear the
    # floor is a design that has not been authored yet, not a wrapper to be relaxed.
    print(f'TRIS {label} {tris} {"OK" if tris > 1800 else "LOW"}')
    print(f'BOUNDS {label} lo={[round(v, 2) for v in lo]} hi={[round(v, 2) for v in hi]}')
    breaches = breach_lines(label, lo, hi, limits, extreme)
    for line in breaches:
        print(line)
    # Print the count so a clean extent states itself; seven decimals keep a number that is
    # still reported legible against the declared limit it missed by.
    print(f'SELFCHECK {label} breaches={len(breaches)} tolerance={BREACH_TOLERANCE}')


# ---------------------------------------------------------------- mining station

def build_mining_station(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz = span[0] / 2, span[2] / 2
    if treatment == 'alliance':
        radius = min(rx, rz) * .74
        torus('01 Processing band', 'trim', .0, radius, 3.1, sx=1.0,
              sz=(span[2] / 2 - 3.1) / radius, cz=c[2], bevel=.3)
        ringy('02 Band rail', 'accent', 0, c[2], .0, radius + 3.05, radius - 1.2, 1.5, n=28)
        ringy('03 Deck', 'trim', 0, 0, -2.2, radius - 3.4, 0, 1.2, n=24)
        torus('04 Deploy ring', 'accent', float(lo[1] + 1.1), radius * .58,
              .75, m=20, n=6)
        plate('05 Hopper drum', 'dark', (11.0, 9.0, 9.0), (0., hi[1] - 6.2, -.5), .9)
        plate('06 Drum cap', 'accent', (12.4, 1.4, 10.4), (0., hi[1] - 1.5, -.5), .4)
        plate('07 Drum throat', 'cool', (7.0, 1.0, 5.6), (0., hi[1] - 1.1, -.5), .3)
        bank('08 Hopper cells', 'dark', 6, (5.6, 3.0, 5.6), (-13.2, -3.4, -13.0),
             (5.3, 0., 5.2))
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'09 Drill boom {label}', 'trim', (side * radius * .5, -1.4, rz * .3),
                  (side * (rx * .8), -3.6, rz * .72), .75, .75, .2)
            plate(f'10 Drill head {label}', 'dark', (2.6, 5.6, 2.6),
                  (side * (rx - 1.35), -6.4, rz * .72), .5)
            plate(f'11 Drill bit {label}', 'cool', (1.1, 2.2, 1.1),
                  (side * (rx - 1.35), -9.9, rz * .72), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'12 Ore chute {label}', 'trim', (side * 4.2, -2.6, -rz * .3),
                  (side * 12.4, -6.6, -rz * .66), .6, .6, .2)
            plate(f'13 Chute mouth {label}', 'dark', (3.4, 3.4, 3.0),
                  (side * 13.4, -6.6, -rz * .66), .4)
        plate('14 Keel strake', 'dark', (span[0] * .34, .9, span[2]), (0., lo[1] + .45, c[2]), .2)
        plate('15 Keel blade', 'trim', (1.2, 1.6, span[2]), (0., lo[1] + 1.3, c[2]), .2)
        bank('16 Radiator vent', 'cool', 5, (7.4, 2.4, 1.0), (-16.0, 2.6, rz * .52),
             (8.0, 0., 0.))
        plate('17 Mast', 'trim', (1.5, span[1] * .5, 1.5),
              (0., lo[1] + span[1] * .25 + 7.0, -rz * .34), .3)
        plate('18 Mast head', 'lit', (2.6, 1.6, 2.6), (0., hi[1] - 1.0, -rz * .34), .3)
        bays(limits, radius, span[2] / 2 - 3.1, .0, c[2])
    elif treatment == 'legion':
        torus('01 Keel hull', 'dark', float(lo[1] + 4.5), rz * .52, 4.4,
              sx=rx * .42 / (rz * .52), sz=1.0, cz=c[2], bevel=.4)
        # The deck reaches the ram's rear face, in the keel's own frame.
        plate('02 Spine deck', 'trim', (rx * 1.06, 1.6, span[2] * .9), (0., -.6, c[2]), .3)
        plate('03 Ore silo', 'dark', (13.0, span[1] * .44, 15.0),
              (0., lo[1] + 4.0 + span[1] * .22, -rz * .1), 1.0)
        plate('04 Silo belt', 'accent', (14.0, 1.6, 16.0),
              (0., lo[1] + 7.6 + span[1] * .22, -rz * .1), .4)
        plate('05 Silo hatch', 'cool', (6.0, 1.0, 7.0), (0., lo[1] + 4.4 + span[1] * .22,
                                                         -rz * .1), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'06 Drill arm {label}', 'trim', (side * 3.4, -1.0, rz * .34),
                  (side * (rx * .88), 1.6, rz * .78), .85, .85, .2)
            strut(f'07 Arm brace {label}', 'dark', (side * 5.0, -2.2, rz * .1),
                  (side * (rx * .78), -.2, rz * .66), .5, .5, .2)
            plate(f'08 Drill housing {label}', 'dark', (3.4, 6.2, 3.4),
                  (side * (rx - 2.2), -.6, rz * .8), .6)
            plate(f'09 Drill clamp {label}', 'accent', (3.9, 1.2, 3.9),
                  (side * (rx - 2.2), 2.6, rz * .8), .4)
        plate('10 Forward ram', 'trim', (7.4, 6.0, 4.4), (0., 1.4, hi[2] - 2.2), .6)
        plate('11 Ram lip', 'cool', (5.6, 1.2, 1.2), (0., 3.6, hi[2] - .7), .3)
        bank('12 Vent bank', 'cool', 4, (6.4, 2.2, 1.2), (-10.4, 3.0, 4.0), (6.9, 0., 0.))
        bank('13 Container rack', 'dark', 5, (4.6, 4.0, 3.4), (-9.6, 1.4, -rz * .5),
             (4.9, 0., -1.9))
        plate('14 Keel plate', 'dark', (rx * .5, 1.2, span[2]), (0., lo[1] + .6, c[2]), .2)
        plate('15 Aft pylon', 'trim', (2.0, span[1], 2.4), (0., (lo[1] + hi[1]) / 2, -rz * .7),
              .3)
        bays(limits, rx * .5, rz * .6, .0, c[2], .04)
    else:  # syndicate
        # The rig deck and its hardware sit on the keel rail, not at world Y=0.
        rig_y = lo[1] + 5.0
        plate('01 Rig deck', 'trim', (span[0] * .78, 1.8, span[2] * .8), (c[0] * .2, rig_y, c[2]),
              .3)
        plate('02 Deck plate', 'dark', (span[0] * .5, 1.2, span[2] * .46),
              (c[0] * .2, rig_y - 1.3, -2.0), .2)
        # The lateral outrigger is what reaches the footprint's wide axis: this legacy extent
        # is asymmetric (-33.93 .. 42.40), so it is centred on c[0], not on the origin.
        plate('02 Outrigger beam', 'trim', (span[0], 1.6, span[2] * .22), (c[0], lo[1] + 1.0, c[2]),
              .2)
        for side, label in ((-1, 'left'), (1, 'right')):
            plate(f'02 Beam pad {label}', 'dark', (3.6, 3.4, 3.6),
                  (c[0] + side * (span[0] / 2 - 1.9), lo[1] + 1.7, c[2]), .4)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'03 Derrick leg {label}', 'trim', (side * 6.0, rig_y + 1.0, -rz * .3),
                  (side * 9.6, hi[1] - 2.6, rz * .3), .9, .9, .2)
        plate('04 Derrick head', 'dark', (21.0, 3.0, 3.4), (0., hi[1] - 1.5, rz * .3), .5)
        plate('05 Drill string', 'trim', (1.6, 8.4, 1.6), (0., hi[1] - 11.0, rz * .3), .3)
        plate('06 Drill head', 'accent', (3.4, 2.6, 3.4), (0., hi[1] - 16.4, rz * .3), .4)
        plate('07 Drill tip', 'cool', (1.4, 2.0, 1.4), (0., hi[1] - 19.6, rz * .3), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            plate(f'08 Ore drum {label}', 'dark', (7.0, 7.0, 8.6),
                  (side * (span[0] * .3), rig_y + 2.6, lo[2] + 5.4), .8)
            ringy(f'09 Drum band {label}', 'accent', side * (span[0] * .3), lo[2] + 5.4,
                  rig_y + 5.6, 3.9, 3.0, 1.2, n=12)
        strut('10 Hab arm', 'trim', (6.0, rig_y + 2.0, -rz * .5), (rx - .8, rig_y + 4.0, -rz * .62), .7, .7, .2)
        plate('11 Hab cab', 'dark', (6.6, 5.0, 6.6), (rx - 1.6, rig_y + 3.4, -rz * .62), .6)
        plate('12 Cab lights', 'lit', (3.4, 1.2, 1.4), (rx - 1.6, rig_y + 6.1, -rz * .62), .3)
        bank('13 Cable run', 'cool', 5, (1.2, 1.2, 6.4), (-9.0, rig_y + 2.4, -rz * .6), (4.6, 0., 0.))
        plate('14 Scaffold rail', 'trim', (span[0] * .34, .8, span[2]),
              (c[0] * .2, lo[1] + .5, c[2]), .2)
        for i in range(4):
            plate(f'15 Rail post {i}', 'trim', (.8, 4.4, .8),
                  (c[0] * .2 - 6.0 + i * 4.0, lo[1] + 2.8, c[2] - rz * .82), .2)
        bays(limits, span[0] * .34, span[2] * .34, rig_y, c[2], .07)


# ---------------------------------------------------------------- sensor station

def build_sensor_station(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz = span[0] / 2, span[2] / 2
    if treatment == 'alliance':
        radius = min(rx, rz) * .82
        ringy('01 Lattice disc', 'trim', c[0] * .2, c[2], -1.4, radius, radius * .22, 2.0, n=26)
        ringy('02 Disc rim', 'accent', c[0] * .2, c[2], -1.4, radius + 1.0, radius - 2.2, 1.3,
              n=26)
        torus('03 Feed band', 'dark', 3.4, radius * .66, 1.5, m=22, n=6, cz=c[2])
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'04 Frame rib {label}', 'trim', (side * radius * .96, -1.4, 0.),
                  (c[0] * .2, 6.4, 0.), .55, .55, .2)
            plate(f'05 Dish mount {label}', 'dark', (4.4, 4.4, 2.2),
                  (side * radius * .56, 8.6, 0.), .4)
            torus(f'06 Dish {label}', 'cool', 11.4, 3.2, .8, m=18, n=5,
                  sx=1.0, sz=1.0)
        plate('07 Mast', 'trim', (1.8, hi[1] - 3.2, 1.8), (c[0] * .2, (hi[1] - 3.2) / 2 - 1.0,
                                                           -rz * .5), .3)
        plate('08 Mast array', 'dark', (5.4, 4.4, 5.4), (c[0] * .2, hi[1] - 3.2, -rz * .5), .5)
        plate('09 Array face', 'lit', (4.0, 1.0, 4.0), (c[0] * .2, hi[1] - .5, -rz * .5), .3)
        plate('10 Keel strake', 'dark', (span[0], 1.0, 3.4), (c[0] * .2, lo[1] + .5, 0.), .2)
        plate('11 Keel rib', 'trim', (1.4, 2.4, span[2]), (c[0] * .2, lo[1] + 1.5, c[2]), .2)
        bank('12 Instrument vent', 'cool', 4, (5.0, 2.0, 1.0), (c[0] * .2 - 9.6, 4.6, rz * .5),
             (6.4, 0., 0.))
        bays(limits, radius, radius * .78, -1.4, c[2], .03)
    elif treatment == 'legion':
        plate('01 Spine', 'trim', (rx * .46, 5.4, span[2]), (c[0] * .2, .0, c[2]), .5)
        plate('02 Spine ridge', 'dark', (rx * .2, 3.0, span[2] * .86), (c[0] * .2, 3.4, 0.), .3)
        for i in range(3):
            plate(f'03 Array step {i}', 'dark', (rx * .78 - i * 2.4, 3.6, 5.4),
                  (c[0] * .2, 5.6 + i * 2.2, -rz * .5 + i * rz * .42), .4)
            plate(f'04 Step window {i}', 'cool', (rx * .6 - i * 2.4, 1.2, 3.4),
                  (c[0] * .2, 7.6 + i * 2.2, -rz * .5 + i * rz * .42), .3)
        plate('05 Mast', 'trim', (2.2, hi[1] - 7.0, 2.2), (c[0] * .2, (hi[1] - 7.0) / 2 + 2.0,
                                                           hi[2] - 3.6), .3)
        # The dish belongs on the hub at the head of the mast: authored at the station origin it
        # floated 23.75 units - 120 px of daylight in its own capture - and only a scaffold boom
        # could have reached it. It keeps its height, which is what sets the legacy extent.
        torus('06 Forward dish', 'cool', hi[1] - 1.1, 5.4, 1.1, m=20, n=6, sz=.7,
              cx=c[0] * .2, cz=hi[2] - 5.0)
        # The hub sits at the mast head and the dish sits on the hub, so the three parts are one
        # piece by placement rather than by a brace; the dish keeps the height that sets the extent.
        plate('07 Dish hub', 'accent', (2.6, 2.6, 3.0), (c[0] * .2, hi[1] - 3.7, hi[2] - 5.0),
              .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'08 Fin {label}', 'dark', (side * rx * .2, 0., rz * .3),
                  (side * (rx * .92), -4.0, rz * .74), .8, .8, .2)
            plate(f'09 Fin tip {label}', 'accent', (2.0, 3.6, 2.0),
                  (side * (rx - 1.05), -5.6, rz * .78), .3)
        plate('10 Keel fin', 'dark', (rx * .3, 5.0, span[2] * .8), (c[0] * .2, lo[1] + 2.5, 0.),
              .3)
        bank('11 Coolant stack', 'cool', 4, (4.2, 2.4, 4.2), (c[0] * .2 - 7.0, 1.0, -rz * .82),
             (4.6, 0., 0.))
        bays(limits, rx * .5, span[2] * .32, .0, c[2], .06)
    else:  # syndicate
        plate('01 Spine truss', 'trim', (span[0] * .62, 1.8, 3.0), (c[0] * .2, .0, .0), .2)
        plate('02 Boom rail', 'trim', (1.8, 1.8, span[2]), (c[0] * .2, .0, c[2]), .2)
        for i in range(3):
            side = -1 if i % 2 else 1
            plate(f'03 Dish pad {i}', 'dark', (7.4, 2.6, 7.4),
                  (c[0] * .2 + side * (3.0 + i * 3.6), 2.8 + i * 2.6, -rz * .5 + i * rz * .46),
                  .5)
            torus(f'04 Bolted dish {i}', 'cool', 6.6 + i * 2.6, 3.4, .9, m=18, n=5, sz=.8)
            plate(f'05 Dish brace {i}', 'accent', (1.6, 4.4, 1.6),
                  (c[0] * .2 + side * (3.0 + i * 3.6), 8.4 + i * 1.4, -rz * .5 + i * rz * .46),
                  .3)
        # One mast runs from its keel seat to the underside of its own head.
        # The former origin-based mast stopped below the detached head cluster.
        mast_bottom, mast_top = lo[1] + 1.6, hi[1] - 4.4
        plate('06 Mast', 'trim', (1.8, mast_top - mast_bottom, 1.8),
              (c[0] * .2, (mast_top + mast_bottom) / 2, hi[2] - 2.6), .3)
        plate('07 Mast head', 'dark', (4.6, 3.6, 4.6), (c[0] * .2, hi[1] - 2.6, hi[2] - 2.6), .5)
        plate('08 Head grid', 'lit', (3.2, 1.0, 3.2), (c[0] * .2, hi[1] - .8, hi[2] - 2.6), .3)
        plate('09 Keel spar', 'dark', (span[0] * .3, 1.6, span[2]), (c[0] * .2, lo[1] + .8, c[2]),
              .2)
        bank('10 Cable bank', 'cool', 4, (1.2, 1.2, 5.6), (c[0] * .2 - 6.0, 1.6, -rz * .8),
             (4.0, 0., 0.))
        strut('11 Outrigger', 'trim', (lo[0] + 2.0, 1.0, rz * .4),
              (hi[0] - 2.0, 3.0, -rz * .4), .7, .7, .2)
        plate('11 Outrigger beam', 'trim', (span[0], 1.4, 3.0), (c[0], .6, c[2]), .2)
        bays(limits, span[0] * .32, span[2] * .28, .0, c[2], .09)


# ---------------------------------------------------------------- energy relay

def build_energy_relay(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz = span[0] / 2, span[2] / 2
    if treatment == 'alliance':
        torus('01 Collector band', 'trim', .0, rz * .74, 3.2, sx=(rx - 3.3) / (rz * .74), sz=1.0,
              cz=c[2], bevel=.3)
        ringy('02 Band rim', 'accent', 0, c[2], .0, rz * .74 + 3.2, rz * .74 - 3.4, 1.4, n=26)
        torus('03 Inner band', 'dark', -3.4, rz * .46, 1.4, m=22, n=6, sx=rx * .8 / (rz * .46))
        plate('04 Core spine', 'trim', (span[0] * .3, 3.0, span[2]), (0., .0, c[2]), .3)
        plate('05 Core cell', 'dark', (9.0, span[1], 11.0), (0., (lo[1] + hi[1]) / 2, -1.0), .7)
        plate('06 Cell belt', 'accent', (10.0, 1.6, 12.0), (0., lo[1] + 4.6 + span[1] * .25,
                                                            -1.0), .4)
        plate('07 Cell throat', 'cool', (6.6, 1.0, 8.0), (0., hi[1] - .5, -1.0), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'08 Truss {label}', 'trim', (side * 4.0, -1.0, -rz * .4),
                  (side * (rx - .9), .0, rz * .7), .7, .7, .2)
            plate(f'09 Radiator panel {label}', 'dark', (1.0, 6.0, span[2] * .34),
                  (side * (rx - .6), 1.0, -rz * .2), .2)
            plate(f'10 Panel face {label}', 'cool', (.8, 4.6, span[2] * .28),
                  (side * (rx - .5), 2.2, -rz * .2 + c[2] * .2), .2)
            plate(f'11 Relay pod {label}', 'dark', (5.0, 4.4, 5.0),
                  (side * (rx * .74), -4.4, rz * .72 + c[2] * .4), .5)
        plate('12 Keel strake', 'dark', (span[0] * .4, 1.0, span[2]), (0., lo[1] + .5, c[2]), .2)
        plate('13 Aft grid', 'cool', (span[0] * .5, 1.4, 1.0), (0., 1.4, hi[2] - .6), .3)
        bays(limits, rx - 3.3, rz * .74, .0, c[2], .02)
    elif treatment == 'legion':
        plate('01 Spine column', 'trim', (span[0] * .34, span[1] * .84, span[2] * .3),
              (c[0] * .3, (lo[1] + hi[1]) / 2, -rz * .2), .5)
        plate('02 Column belt', 'accent', (span[0] * .38, 1.6, span[2] * .34),
              (c[0] * .3, hi[1] - .8, -rz * .2), .4)
        plate('03 Column cap', 'dark', (span[0] * .28, 2.4, span[2] * .24),
              (c[0] * .3, hi[1] - 2.8, -rz * .2), .4)
        plate('04 Cap louvre', 'cool', (span[0] * .2, 1.0, span[2] * .16),
              (c[0] * .3, hi[1] - 4.6, -rz * .2), .3)
        for i in range(4):
            plate(f'05 Cell step {i}', 'dark', (span[0] * .8 - i * 3.4, 3.4, 6.4),
                  (c[0] * .3, lo[1] + 3.0 + i * 6.4, -rz * .2 + (i - 1.5) * 5.6), .4)
            plate(f'06 Step vent {i}', 'cool', (span[0] * .6 - i * 3.4, 1.2, 4.4),
                  (c[0] * .3, lo[1] + 5.2 + i * 6.4, -rz * .2 + (i - 1.5) * 5.6), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'07 Coolant fin {label}', 'trim', (side * span[0] * .16, 0., rz * .5),
                  (side * (rx * .88), -2.0, rz * .86), .9, .9, .2)
            plate(f'08 Fin plate {label}', 'dark', (1.2, 5.0, span[2] * .3),
                  (side * (rx - .75), -.6, rz * .5 + c[2] * .4), .2)
        plate('09 Forward boom', 'trim', (2.4, 2.4, span[2] * .4),
              (c[0] * .3, 1.4, hi[2] - span[2] * .2 - .2), .3)
        plate('10 Boom head', 'accent', (4.4, 4.4, 3.0), (c[0] * .3, 1.4, hi[2] - 1.6), .4)
        plate('11 Keel plate', 'dark', (span[0] * .3, 1.2, span[2] - .2),
              (c[0] * .3, lo[1] + .6, c[2]), .2)
        bank('12 Relay boxes', 'dark', 4, (5.0, 3.6, 3.2), (c[0] * .3 - 8.4, 1.4, -rz * .62),
             (5.4, 0., 0.))
        bays(limits, rx * .5, span[2] * .3, .0, c[2], .05)
    else:  # syndicate
        for i in range(4):
            plate(f'01 Power cell {i}', 'dark', (11.0, 9.0, 8.6),
                  (c[0] * .2 + (i - 1.5) * 9.6, 2.4 + (i % 2) * 3.2, -rz * .4 + (i % 2) * rz * .8),
                  .8)
            ringy(f'02 Cell band {i}', 'accent', c[0] * .2 + (i - 1.5) * 9.6,
                  -rz * .4 + (i % 2) * rz * .8, 2.4 + (i % 2) * 3.2, 6.4, 4.8, 1.2, n=12)
        plate('03 Truss spine', 'trim', (span[0], 1.6, 2.6), (c[0], 1.2, .0), .2)
        plate('04 Spine plate', 'trim', (1.6, 1.6, span[2]), (c[0] * .2, 1.2, c[2]), .2)
        plate('05 Head cell', 'dark', (8.4, 9.0, 7.4), (c[0] * .2, hi[1] - 4.5, -rz * .1), .6)
        plate('06 Head belt', 'accent', (9.2, 1.4, 8.2), (c[0] * .2, hi[1] - 1.8, -rz * .1), .4)
        plate('07 Head vent', 'cool', (5.6, 1.0, 4.6), (c[0] * .2, hi[1] - 8.6, -rz * .1), .3)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'08 Cable run {label}', 'cool', (side * 5.0, -1.0, -rz * .6),
                  (side * 5.0, 3.0, rz * .6), .6, .6, .2)
            plate(f'09 Relay pod {label}', 'dark', (5.4, 4.6, 5.4),
                  # Pods bolt under the transverse truss, whose centreline is Z=0.
                  (side * (rx - 3.6), 1.2 - 1.6 / 2 - 4.6 / 2, 0.), .5)
            plate(f'10 Pod grid {label}', 'lit', (3.6, 1.0, 3.6),
                  (side * (rx - 3.6), 1.2 - 1.6 / 2 - 4.6 - .5, 0.), .3)
        plate('11 Keel spar', 'dark', (span[0] * .5, 1.4, span[2]), (c[0] * .2, lo[1] + .7, c[2]),
              .2)
        bank('12 Coolant drums', 'cool', 3, (4.6, 4.4, 4.6),
             (c[0] * .2 - 12.0, 1.6, -rz * .86), (5.0, 0., 0.))
        bays(limits, span[0] * .32, span[2] * .28, .0, c[2], .08)


BUILDERS = {'mining_station': build_mining_station, 'sensor_station': build_sensor_station,
            'energy_relay': build_energy_relay}


def build(key):
    identifier, radius, limits, treatment = SEEDS[key]
    master = ROOT / f'art/blender/{identifier}.blend'
    if master.exists() and '--replace-seed' not in sys.argv:
        raise RuntimeError(f'{master.name} is the editable master. Use export_{identifier}.py; '
                           f'--replace-seed destroys edits.')
    # A per-asset reset must not reload factory settings: alliance_common's import already
    # emptied the startup scene and built the role materials, and a factory reset takes
    # those materials with it (`ReferenceError: StructRNA of type Material has been removed`).
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    kind = key.split(':')[1]
    BUILDERS[kind](limits, treatment)
    # Nothing floats: a kit is authored by centre and by reach, so contact is not implied.
    # The pass reports what it joined, and the extent self-check still runs after it.
    weld_scene()
    report_bounds(limits, identifier)
    features = dict(
        authority='blend', approval='pending_owner_approval', binding=key,
        data_id=kind, original_design=True,
        design=DESIGNS[(kind, treatment)],
        legacy_envelope=[list(a) for a in limits],
        seed_recipe='tools/art/build_b3b_stations.py; initial authoring only, never rebuild '
                    'hand edits',
        station_kind=kind, station_radius=radius,
        provenance='Original geometry authored in Blender; no external mesh or texture '
                   'dependencies')
    bpy.context.scene['asset'] = identifier
    bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
    bpy.context.scene['authority'] = 'blend'
    bpy.context.scene['design'] = DESIGNS[(kind, treatment)]
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
