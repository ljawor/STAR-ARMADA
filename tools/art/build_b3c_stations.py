#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPES ONLY. Each editable .blend is authoritative afterwards.

S06 batch B3c - the remaining seventeen faction station rows, i.e. every authorable
`<faction>:<kind>` seat that B3a (command stations) and B3b (mining / sensor / relay) did not
already deliver:

  research_station / defense_platform / trade_station / fighter_platform / repair_dock
      x rebel, confederacy, syndicate                                     = 15 rows
  shipyard x confederacy, syndicate                                       =  2 rows

`rebel:shipyard` is absent because it is already the approved trio's `core` asset
`alliance_shipyard`; the ten imperial station rows are absent because
`render.fleet_geometry.station_mesh` dispatches them straight to `_station_mesh(did)` with no
`mesh_for` seam, so authoring them is a renderer change and an owner decision, not an asset.

Every dimension is derived from the binding's own legacy extent (`frame`), and each design
carries four *reach* parts that land that extent exactly - a rail spanning the full depth, a
transverse beam spanning the full width, a keel part whose underside is the Y minimum and a
cap whose top is the Y maximum - because the review harness requires the authored footprint
to *reach* the legacy one per axis and per side, and the legacy procedural station fills its
declared box exactly. `plate` carries no bevel, so a declared box is the evaluated box.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b3c_stations.py -- --all
    Blender --background --python-exit-code 1 --python tools/art/build_b3c_stations.py -- --asset rebel:research_station
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# An extent error below this many world units is float noise, not a breach (see the B3b
# seed): `plate` is bevel-free, so the tolerance only absorbs float32 representation noise
# in the evaluated depsgraph, which the exporter's edge quantiser then snaps to the edge.
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


# binding -> (identifier, radius, limits per axis, treatment)
SEEDS = {
    'rebel:research_station': ('alliance_research_station', 85,
                               [[-40.0, 40.0], [-9.6, 39.28], [-25.6, 35.901]], 'alliance'),
    'confederacy:research_station': ('legion_research_station', 85,
                                     [[-46.3156, 46.3156], [-12.4, 13.88],
                                      [-33.48, 52.68]], 'legion'),
    'syndicate:research_station': ('syndicate_research_station', 85,
                                   [[-40.0, 36.4], [-7.2, 37.68], [-27.572, 32.8]],
                                   'syndicate'),
    'rebel:defense_platform': ('alliance_defense_platform', 60,
                               [[-45.92, 45.92], [-4.8, 11.166], [-44.32, 44.32]], 'alliance'),
    'confederacy:defense_platform': ('legion_defense_platform', 60,
                                     [[-50.2043, 50.2043], [-8.4, 16.544],
                                      [-31.2764, 55.68]], 'legion'),
    'syndicate:defense_platform': ('syndicate_defense_platform', 60,
                                   [[-45.9679, 30.3691], [-10.8, 22.1], [-28.5448, 28.0475]],
                                   'syndicate'),
    'rebel:trade_station': ('alliance_trade_station', 65,
                            [[-44.0, 44.0], [-5.948, 6.12], [-38.736, 39.36]], 'alliance'),
    'confederacy:trade_station': ('legion_trade_station', 65,
                                  [[-43.7668, 43.7668], [-6.552, 18.28],
                                   [-46.0532, 46.0532]], 'legion'),
    'syndicate:trade_station': ('syndicate_trade_station', 65,
                                [[-52.3122, 45.2571], [-8.8, 24.5], [-48.6483, 46.5606]],
                                'syndicate'),
    'rebel:fighter_platform': ('alliance_fighter_platform', 75,
                               [[-48.0, 48.0], [-9.2, 6.92], [-39.2, 39.2]], 'alliance'),
    'confederacy:fighter_platform': ('legion_fighter_platform', 75,
                                     [[-42.4021, 42.4021], [-8.8, 11.88], [-36.4, 36.0]],
                                     'legion'),
    'syndicate:fighter_platform': ('syndicate_fighter_platform', 75,
                                   [[-39.6, 32.1135], [-15.2, 30.8], [-39.2, 39.2]],
                                   'syndicate'),
    'rebel:repair_dock': ('alliance_repair_dock', 70,
                          [[-38.4, 38.4], [-12.8, 23.6], [-33.6, 39.6]], 'alliance'),
    'confederacy:repair_dock': ('legion_repair_dock', 70,
                                [[-40.1472, 40.1472], [-14.8, 26.4], [-36.4, 36.4]], 'legion'),
    'syndicate:repair_dock': ('syndicate_repair_dock', 70,
                              [[-37.4318, 39.7528], [-16.8, 34.8], [-38.931, 37.9495]],
                              'syndicate'),
    'confederacy:shipyard': ('legion_shipyard', 110,
                             [[-62.04, 62.04], [-5.6, 41.6], [-45.0564, 62.4]], 'legion'),
    'syndicate:shipyard': ('syndicate_shipyard', 110,
                           [[-52.1606, 46.9468], [-18.9928, 45.6], [-53.6606, 48.4056]],
                           'syndicate'),
}
KINDS = {'research_station': 'Research Station', 'defense_platform': 'Defense Platform',
         'trade_station': 'Trade Station', 'fighter_platform': 'Fighter Platform',
         'repair_dock': 'Repair Dock', 'shipyard': 'Shipyard'}
DESIGNS = {
    ('research_station', 'alliance'): 'elliptical habitat band around a lab core, dish mast',
    ('research_station', 'legion'): 'stepped array bastions under a forward dish tower',
    ('research_station', 'syndicate'): 'open truss rig carrying bolted dishes and a hab cab',
    ('defense_platform', 'alliance'): 'armoured disc with four battery hardpoints on its rim',
    ('defense_platform', 'legion'): 'stepped bastion with two battery decks and a fire tower',
    ('defense_platform', 'syndicate'): 'truss platform with bolted projector pods on outriggers',
    ('trade_station', 'alliance'): 'cargo band around a hub with cranes and stacked containers',
    ('trade_station', 'legion'): 'long keel with silos, gantry cranes and container racks',
    ('trade_station', 'syndicate'): 'open quay deck with lashed drums, cranes and a hab cab',
    ('fighter_platform', 'alliance'): 'flat deck with an open launch bay and stacked bays',
    ('fighter_platform', 'legion'): 'two-tier armoured bay block with launch rails',
    ('fighter_platform', 'syndicate'): 'open frame with launch cradles and booms',
    ('repair_dock', 'alliance'): 'open cradle band with gantry arms and service decks',
    ('repair_dock', 'legion'): 'twin towers bridged over a dry-dock well',
    ('repair_dock', 'syndicate'): 'scaffold frames with cross members and spare drums',
    ('shipyard', 'legion'): 'slipway rails under gantry frames and a build hall',
    ('shipyard', 'syndicate'): 'open slipway trusses with cranes and spare plating',
}
_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_masters(argv):
    """Refuse before Blender is imported, and before any target is written.

    One seed authors seventeen masters; a half-run that dies on the fifth leaves the batch
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


# ---------------------------------------------------------------- station kit
# A station is radial structure, not a hull: rings on a vertical axis, members between
# arbitrary points and rows of small blocks. Deliberately duplicated from the B3a/B3b seeds
# rather than moved into a shared module - each seed refuses to overwrite another batch's
# masters, and a shared module would make one batch's edit move another batch's rebuild.

def torus(name, role, y, radius, tube, m=24, n=8, sx=1.0, sz=1.0, bevel=0, cx=0., cz=0.):
    """A band: a ring in the XZ plane, its axis vertical (Y).

    `sx`/`sz` make the centre line an ellipse and `cx`/`cz` offset it, which a station
    footprint needs: the binding's legacy extent is neither circular nor centred on the
    origin.
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


def ringy(name, role, cx, cz, y, outer, inner, thickness, n=16, sx=1.0, sz=1.0):
    """A horizontal rim, collar or deck edge: an annulus whose axis is vertical.

    `sx`/`sz` make it elliptical for the same reason `torus` has them: a station footprint is
    never circular, so a circular collar sized for the wide axis overruns the short one.
    """
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


def z_rail(name, role, limits, half_w, height, y):
    """A rail spanning the binding's full depth: it sets both Z extremes, per side."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, (half_w * 2, height, span[2]), (c[0], y, c[2]))


def x_beam(name, role, limits, height, depth, y, cz=None):
    """A transverse beam spanning the full width: it sets both X extremes, per side."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, (span[0], height, depth),
                 (c[0], y, c[2] if cz is None else cz))


def keel_pad(name, role, limits, size, dx=0., dz=0., y=None):
    """A part whose underside is the binding's Y minimum."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, size, (c[0] + dx, (lo[1] + size[1] / 2) if y is None else y,
                                    c[2] + dz))


def top_cap(name, role, limits, size, dx=0., dz=0.):
    """A part whose top is the binding's Y maximum."""
    lo, hi, c, span = frame(limits)
    return plate(name, role, size, (c[0] + dx, hi[1] - size[1] / 2, c[2] + dz))


def bays(limits, rx, rz, y, cz, phase=0.):
    """Detail layer every station carries: an inner concentric band and two rows of bays.

    Radii are 0.62 and 0.78 of the ring the caller names and the block size is capped, so the
    named ring stays the widest thing on the station and the binding's extent is still reached
    by real structure rather than by a greeble. The rows are deliberately role-separated:
    `dark` machinery and a `cool` vent row are what the review's per-role ablations measure on
    a station, and `base`/`lit` are what the loader needs non-empty.
    """
    lo, hi, c, span = frame(limits)
    torus('90 Inner band', 'trim', float(y), rx * .62, 1.5, m=44, n=12, sx=1.,
          sz=rz / rx, cz=cz)
    ring_blocks('91 Bay machinery', 'dark', 16, c[0] * .2, cz, float(y) + 1.9, rx * .78,
                rz * .78, (4.6, 3.0, 4.6), phase)
    ring_blocks('92 Bay vents', 'cool', 16, c[0] * .2, cz, float(y) + 3.7, rx * .74, rz * .74,
                (2.4, 1.4, 2.4), phase + .11)
    ring_blocks('93 Base plating', 'base', 12, c[0] * .2, cz, float(y) - 2.2, rx * .7, rz * .7,
                (6.0, 1.4, 4.2), phase + .05)
    ring_blocks('94 Marker lights', 'lit', 16, c[0] * .2, cz, float(y) + 5.0, rx * .74,
                rz * .74, (1.6, 1.2, 1.6), phase + .11)


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
    # The export wrapper refuses at or under 1,800 triangles, so a master that cannot clear
    # the floor is a design that has not been authored yet, not a wrapper to be relaxed.
    print(f'TRIS {label} {tris} {"OK" if tris > 1800 else "LOW"}')
    print(f'BOUNDS {label} lo={[round(v, 2) for v in lo]} hi={[round(v, 2) for v in hi]}')
    breaches = breach_lines(label, lo, hi, limits, extreme)
    for line in breaches:
        print(line)
    print(f'SELFCHECK {label} breaches={len(breaches)} tolerance={BREACH_TOLERANCE}')


# ---------------------------------------------------------------- research station

def build_research_station(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .32
    bh = h * .34
    if treatment == 'alliance':
        z_rail('01 Keel rail', 'dark', limits, 4.2, 1.6, y0 + .8)
        x_beam('02 Cross beam', 'trim', limits, 1.4, 3.2, y0 + .7)
        plate('03 Spine trunk', 'dark', (rx * .22, h * .4, rz * .22), (c[0], y0 + h * .2, c[2]))
        torus('04 Habitat band', 'trim', y0 + h * .2, rx * .7, rx * .06, m=40, n=10,
              sz=(rz * .74) / (rx * .7), cz=c[2])
        ringy('05 Band rail', 'accent', c[0], c[2], y0 + h * .2, rx * .76, rx * .64, 1.5, n=30,
              sz=(rz * .74) / (rx * .7))
        plate('06 Lab core', 'dark', (rx * .3, bh, rz * .3), (c[0], by, c[2]))
        plate('07 Core drum', 'base', (rx * .36, 1.8, rz * .36), (c[0], y0 + h * .5, c[2]))
        bank('08 Lab modules', 'dark', 5, (5.6, 4.0, 6.2), (c[0] - 11.2, by, c[2] - 9.4),
             (5.4, 0., 4.7))
        bank('09 Module windows', 'lit', 5, (3.8, 1.0, 1.8), (c[0] - 11.2, by + 2.6, c[2] - 7.0),
             (5.4, 0., 4.7))
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'10 Frame rib {label}', 'trim', (side * rx * .94, y0 + h * .2, c[2]),
                  (side * rx * .1, by, c[2]), .8, .8, .2)
            plate(f'11 Rib foot {label}', 'base', (5.0, 4.6, 5.6),
                  (side * (rx - 3.0), y0 + h * .2, c[2]))
        plate('12 Mast', 'trim', (2.4, hi[1] - 1.8 - y0 - h * .46, 2.4),
              (c[0], (hi[1] - 1.8 + y0 + h * .46) / 2, c[2]))
        plate('13 Dish yoke', 'base', (6.4, 5.4, 6.4), (c[0], hi[1] - 4.4, c[2]))
        torus('14 Array dish', 'cool', hi[1] - 2.4, 3.4, 1.2, m=22, n=6, cz=c[2])
        plate('15 Beacon plate', 'lit', (6.6, 1.8, 6.6), (c[0], hi[1] - .9, c[2]))
        bank('16 Radiator louvre', 'cool', 4, (1.2, 6.0, 3.4), (rx - 2.8, by, c[2] + rz * .3),
             (0., 0., 3.2))
        bays(limits, rx * .3 / .62, rz * .3 / .62, by, c[2], .02)
    elif treatment == 'legion':
        z_rail('01 Spine rail', 'trim', limits, rx * .26, h * .16, y0 + h * .08)
        x_beam('02 Keel transom', 'dark', limits, 1.6, 4.2, y0 + .8)
        plate('03 Spine trunk', 'trim', (rx * .26, h * .42, rz * .26), (c[0], y0 + h * .24, c[2]))
        plate('04 Array block', 'dark', (rx * .8, bh, rz * .56), (c[0], by, c[2] - rz * .3))
        plate('05 Block louvre', 'cool', (rx * .62, 1.4, rz * .3), (c[0], y0 + h * .49, c[2] - rz * .3))
        for i in range(3):
            plate(f'06 Step bastion {i}', 'dark', (rx * .6 - i * 4.0, bh * .8, rz * .24),
                  (c[0], by - h * .02, c[2] + rz * .08 + i * rz * .28))
            plate(f'07 Step louvre {i}', 'cool', (rx * .44 - i * 4.0, 1.2, rz * .16),
                  (c[0], y0 + h * .45, c[2] + rz * .08 + i * rz * .28))
        plate('08 Tower base', 'trim', (7.6, h * .5, 7.6), (c[0], by, c[2] + rz * .62))
        plate('09 Tower mast', 'trim', (2.6, hi[1] - 3.4 - (y0 + h * .5), 2.6),
              (c[0], (hi[1] - 3.4 + y0 + h * .5) / 2, c[2] + rz * .62))
        torus('10 Forward dish', 'cool', hi[1] - 2.4, 3.4, 1.2, m=20, n=6, sz=.7,
              cz=c[2] + rz * .62)
        plate('11 Dish yoke', 'accent', (3.6, 3.8, 4.2), (c[0], hi[1] - 5.4, c[2] + rz * .62))
        top_cap('12 Tower cap', 'base', limits, (7.6, 2.2, 7.6), dz=rz * .62)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'13 Fin {label}', 'dark', (side * rx * .18, by, c[2] - rz * .2),
                  (side * rx * .88, by - h * .16, c[2] + rz * .5), .9, .9, .2)
            plate(f'14 Fin tip {label}', 'accent', (2.6, 4.2, 2.6),
                  (side * (rx - 2.4), by - h * .2, c[2] + rz * .54))
        plate('15 Keel plate', 'dark', (rx * .3, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bank('16 Coolant stack', 'cool', 4, (4.6, 2.6, 4.0), (c[0] - rx * .5, by - h * .1,
                                                              c[2] - rz * .66), (4.4, 0., 0.))
        bays(limits, rx * .26 / .62, rz * .26 / .62, by, c[2], .05)
    else:  # syndicate
        z_rail('01 Truss rail', 'trim', limits, 2.2, h * .16, y0 + h * .08)
        x_beam('02 Outrigger beam', 'trim', limits, 1.8, 3.0, y0 + h * .12)
        keel_pad('03 Keel skid', 'dark', limits, (span[0] * .44, 2.4, span[2] * .72))
        plate('04 Truss trunk', 'trim', (rx * .22, h * .46, rz * .22), (c[0], y0 + h * .26, c[2]))
        plate('05 Rig deck', 'base', (span[0] * .66, 2.0, span[2] * .58), (c[0], by, c[2]))
        for i in range(3):
            side = -1 if i % 2 else 1
            px = c[0] + side * rx * .34
            pz = c[2] - rz * .5 + i * rz * .44
            plate(f'06 Dish pad {i}', 'dark', (7.4, 2.6, 7.4), (px, by + h * .04, pz))
            torus(f'07 Bolted dish {i}', 'cool', by + h * .16, 3.4, .9, m=18, n=5, sz=.8, cz=pz)
            plate(f'08 Dish brace {i}', 'accent', (1.6, 4.4, 1.6), (px, by + h * .12, pz))
        plate('09 Mast', 'trim', (2.2, hi[1] - 3.4 - (y0 + h * .44), 2.2),
              (c[0], (hi[1] - 3.4 + y0 + h * .44) / 2, c[2] + rz * .58))
        top_cap('10 Mast head grid', 'lit', limits, (5.2, 3.4, 5.2), dz=rz * .58)
        plate('11 Hab cab', 'dark', (8.4, 6.4, 8.4), (c[0] + rx * .72, by + h * .1, c[2] - rz * .3))
        plate('12 Cab lights', 'lit', (4.2, 1.2, 1.6), (c[0] + rx * .72, by + h * .26,
                                                         c[2] - rz * .3))
        strut('13 Hab arm', 'trim', (c[0] + rx * .38, by + h * .06, c[2] - rz * .3),
              (c[0] + rx * .72, by + h * .1, c[2] - rz * .3), .7, .7, .2)
        bank('14 Cable run', 'cool', 4, (4.6, 1.2, 5.6), (c[0] - rx * .6, by + 1.2,
                                                          c[2] - rz * .7), (4.4, 0., 0.))
        plate('15 Keel spar', 'dark', (span[0] * .3, 1.6, span[2]), (c[0], y0 + .8, c[2]))
        bays(limits, rx * .22 / .62, rz * .22 / .62, by, c[2], .08)


# ---------------------------------------------------------------- defense platform

def build_defense_platform(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .34
    bh = h * .4
    if treatment == 'alliance':
        z_rail('01 Armour rail', 'dark', limits, 6.0, h * .14, y0 + h * .07)
        x_beam('02 Armour transom', 'trim', limits, h * .13, 4.0, y0 + h * .065)
        ringy('03 Armour disc', 'base', c[0], c[2], by - h * .1, rx * .78, rx * .16, h * .16,
              n=30, sz=rz * .86 / (rx * .78))
        ringy('04 Disc rail', 'accent', c[0], c[2], by - h * .1, rx * .84, rx * .68, 1.4, n=30,
              sz=rz * .9 / (rx * .78))
        plate('05 Core block', 'dark', (rx * .4, bh, rz * .4), (c[0], by, c[2]))
        torus('06 Core shroud', 'trim', by + h * .12, rx * .26, h * .1, m=26, n=8, cz=c[2])
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            px, pz = c[0] + rx * .6 * math.cos(a), c[2] + rz * .68 * math.sin(a)
            plate(f'07 Battery hardpoint {i}', 'dark', (7.4, h * .3, 7.4), (px, by, pz))
            plate(f'08 Hardpoint mantlet {i}', 'accent', (8.2, 1.4, 8.2), (px, by + h * .19, pz))
            plate(f'09 Hardpoint sight {i}', 'lit', (3.0, 1.0, 3.0), (px, by + h * .25, pz))
        plate('10 Fire tower', 'trim', (6.0, hi[1] - 2.2 - (y0 + h * .5), 6.0),
              (c[0], (hi[1] - 2.2 + y0 + h * .5) / 2, c[2] - rz * .5))
        top_cap('11 Tower cap', 'base', limits, (4.6, 2.2, 4.6), dz=-rz * .5)
        bank('12 Sensor rack', 'cool', 4, (4.8, 2.0, 1.0), (c[0] - 8.0, by + h * .1,
                                                            c[2] + rz * .3), (4.6, 0., 0.))
        plate('13 Keel block', 'dark', (span[0] * .3, 1.4, span[2] * .7), (c[0], y0 + .7, c[2]))
        bays(limits, rx * .4 / .62, rz * .4 / .62, by, c[2], .03)
    elif treatment == 'legion':
        z_rail('01 Bastion rail', 'trim', limits, rx * .3, h * .16, y0 + h * .08)
        x_beam('02 Keel transom', 'dark', limits, 1.6, 4.4, y0 + .8)
        plate('03 Lower deck', 'dark', (rx * .78, bh, rz * .82), (c[0], by, c[2]))
        plate('04 Deck louvre', 'cool', (rx * .6, 1.4, rz * .5), (c[0], y0 + h * .58, c[2]))
        plate('05 Upper deck', 'trim', (rx * .58, h * .3, rz * .56), (c[0], y0 + h * .66, c[2]))
        for i in range(4):
            side = -1 if i % 2 else 1
            pz = c[2] - rz * .42 + (i // 2) * rz * .84
            plate(f'06 Battery deck {i}', 'dark', (6.8, h * .3, 7.6), (c[0] + side * rx * .5,
                                                                     by + h * .04, pz))
            plate(f'07 Battery mantlet {i}', 'accent', (7.4, 1.4, 8.2), (c[0] + side * rx * .5,
                                                                        by + h * .2, pz))
            plate(f'08 Battery sight {i}', 'lit', (2.6, 1.0, 2.6), (c[0] + side * rx * .5,
                                                                    by + h * .26, pz))
        plate('09 Fire tower', 'trim', (7.4, hi[1] - 3.4 - (y0 + h * .56), 7.4),
              (c[0], (hi[1] - 3.4 + y0 + h * .56) / 2, c[2] + rz * .6))
        plate('10 Tower belt', 'accent', (8.2, 1.6, 8.2), (c[0], hi[1] - 4.6, c[2] + rz * .6))
        top_cap('11 Tower head', 'base', limits, (6.0, 2.4, 6.0), dz=rz * .6)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'12 Armour fin {label}', 'dark', (c[0] + side * rx * .16, by, c[2]),
                  (c[0] + side * rx * .86, by - h * .18, c[2] + rz * .4), .9, .9, .2)
            plate(f'13 Fin tip {label}', 'accent', (2.4, 4.2, 2.4),
                  (c[0] + side * (rx - 2.6), by - h * .22, c[2] + rz * .44))
        plate('14 Keel plate', 'dark', (rx * .28, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bank('15 Coolant bank', 'cool', 4, (4.6, 2.4, 4.2), (c[0] - rx * .44, by - h * .06,
                                                             c[2] + rz * .62), (4.4, 0., 0.))
        bays(limits, rx * .34 / .62, rz * .34 / .62, by, c[2], .06)
    else:  # syndicate
        z_rail('01 Truss rail', 'dark', limits, 2.4, h * .14, y0 + h * .07)
        x_beam('02 Outrigger beam', 'trim', limits, 1.8, 3.2, y0 + h * .1)
        keel_pad('03 Keel skid', 'dark', limits, (span[0] * .44, 2.6, span[2] * .72))
        plate('04 Truss trunk', 'trim', (rx * .2, h * .52, rz * .2), (c[0], y0 + h * .28, c[2]))
        plate('05 Platform deck', 'base', (span[0] * .7, 2.0, span[2] * .56), (c[0], by, c[2]))
        for i in range(4):
            side = -1 if i % 2 else 1
            px = c[0] + side * rx * .5
            pz = c[2] - rz * .56 + (i // 2) * rz * 1.12
            plate(f'06 Projector pod {i}', 'dark', (8.0, h * .34, 7.4), (px, by + h * .06, pz))
            plate(f'07 Pod mantlet {i}', 'accent', (8.8, 1.6, 8.2), (px, by + h * .26, pz))
            plate(f'08 Pod grid {i}', 'lit', (3.2, 1.0, 3.2), (px, by + h * .32, pz))
        plate('09 Control tower', 'trim', (7.0, hi[1] - 2.6 - (y0 + h * .48), 7.0),
              (c[0], (hi[1] - 2.6 + y0 + h * .48) / 2, c[2] + rz * .58))
        plate('10 Tower cab', 'dark', (8.4, h * .18, 8.4), (c[0], hi[1] - h * .12, c[2] + rz * .58))
        top_cap('11 Cab grid', 'lit', limits, (5.0, 2.0, 5.0), dz=rz * .58)
        plate('12 Hab cab', 'dark', (8.0, 6.0, 8.0), (c[0] - rx * .74, by + h * .1, c[2] - rz * .3))
        plate('13 Cab louvre', 'cool', (5.0, 1.2, 1.6), (c[0] - rx * .74, by + h * .26,
                                                         c[2] - rz * .3))
        strut('14 Cab arm', 'trim', (c[0] - rx * .4, by + h * .06, c[2] - rz * .3),
              (c[0] - rx * .74, by + h * .1, c[2] - rz * .3), .7, .7, .2)
        bank('15 Cable run', 'cool', 4, (4.4, 1.2, 5.4), (c[0] + rx * .1, by + 1.2,
                                                          c[2] - rz * .5), (4.2, 0., 0.))
        bays(limits, rx * .2 / .62, rz * .2 / .62, by, c[2], .04)


# ---------------------------------------------------------------- trade station

def build_trade_station(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .32
    bh = h * .34
    if treatment == 'alliance':
        z_rail('01 Quay rail', 'trim', limits, 4.6, h * .12, y0 + h * .06)
        x_beam('02 Quay transom', 'trim', limits, h * .11, 3.4, y0 + h * .055)
        plate('03 Keel trunk', 'dark', (rx * .38, h * .4, rz * .38), (c[0], y0 + h * .2, c[2]))
        ringy('04 Cargo deck', 'base', c[0], c[2], by, rx * .82, rx * .3, 2.0, n=30,
              sz=rz * .82 / (rx * .82))
        ringy('05 Deck rail', 'accent', c[0], c[2], by, rx * .88, rx * .72, 1.4, n=30,
              sz=rz * .88 / (rx * .82))
        plate('06 Hub drum', 'dark', (rx * .34, h * .6, rz * .34), (c[0], by + h * .06, c[2]))
        plate('07 Hub belt', 'trim', (rx * .38, 1.6, rz * .38), (c[0], y0 + h * .6, c[2]))
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            px, pz = c[0] + rx * .6 * math.cos(a), c[2] + rz * .6 * math.sin(a)
            plate(f'08 Container stack {i}', 'dark', (9.0, h * .4, 10.0), (px, by, pz))
            plate(f'09 Stack doors {i}', 'lit', (3.4, 1.2, 6.6), (px, by + h * .22, pz))
        bank('10 Cargo cells', 'dark', 4, (5.2, 3.4, 5.2), (c[0] - rx * .5, by, c[2] - rz * .3),
             (7.4, 0., 0.))
        plate('11 Crane mast', 'trim', (2.6, h * .74, 2.6), (c[0] + rx * .3, y0 + h * .5,
                                                             c[2] - rz * .5))
        plate('12 Crane jib', 'accent', (22.0, 1.8, 3.0), (c[0] + rx * .3 - 8.0, hi[1] - 2.2,
                                                           c[2] - rz * .5))
        plate('13 Jib head', 'base', (6.0, 2.0, 6.0), (c[0] + rx * .3 - 18.0, hi[1] - 1.0,
                                                        c[2] - rz * .5))
        plate('14 Cargo boom', 'dark', (span[0] * .3, 1.6, 4.0), (c[0], by + h * .1, hi[2] - 5.0))
        bank('15 Radiator louvre', 'cool', 4, (5.0, 2.0, 1.0), (c[0] - 9.0, by + h * .2,
                                                                hi[2] - 1.6), (4.8, 0., 0.))
        bays(limits, rx * .34 / .62, rz * .34 / .62, by, c[2], .01)
    elif treatment == 'legion':
        z_rail('01 Keel rail', 'trim', limits, rx * .3, h * .16, y0 + h * .08)
        x_beam('02 Keel transom', 'dark', limits, 1.6, 4.2, y0 + .8)
        plate('03 Silo deck', 'dark', (rx * .76, bh, rz * .84), (c[0], by, c[2]))
        for i in range(4):
            px = c[0] - rx * .5 + i * rx * .33
            plate(f'04 Silo drum {i}', 'dark', (9.4, h * .34, 8.4), (px, by + h * .1, c[2] - rz * .5))
            plate(f'05 Drum belt {i}', 'accent', (10.2, 1.4, 9.2), (px, by + h * .26,
                                                                    c[2] - rz * .5))
            plate(f'06 Drum hatch {i}', 'cool', (4.4, 1.0, 3.6), (px, by + h * .32, c[2] - rz * .5))
        plate('07 Container rack', 'dark', (rx * .6, h * .3, rz * .4), (c[0], by + h * .02,
                                                                        c[2] + rz * .56))
        bank('08 Rack cells', 'lit', 5, (5.2, 1.2, 5.4), (c[0] - rx * .5, by + h * .18,
                                                          c[2] + rz * .56), (4.8, 0., 0.))
        plate('09 Gantry mast', 'trim', (2.8, hi[1] - 2.4 - (y0 + h * .46), 2.8),
              (c[0], (hi[1] - 2.4 + y0 + h * .46) / 2, c[2] + rz * .1))
        plate('10 Gantry arm', 'accent', (span[0] * .48, 2.0, 3.0), (c[0], hi[1] - 3.0, c[2] + rz * .1))
        top_cap('11 Gantry head', 'base', limits, (7.0, 2.4, 7.0), dz=rz * .1)
        for side, label in ((-1, 'left'), (1, 'right')):
            strut(f'12 Berth arm {label}', 'trim', (c[0] + side * rx * .3, by, c[2] - rz * .6),
                  (c[0] + side * rx * .86, by - h * .16, c[2] - rz * .1), .8, .8, .2)
            plate(f'13 Berth pad {label}', 'dark', (3.2, 4.4, 4.0),
                  (c[0] + side * (rx - 2.6), by - h * .2, c[2] - rz * .1))
        plate('14 Keel plate', 'dark', (rx * .28, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bays(limits, rx * .3 / .62, rz * .3 / .62, by, c[2], .04)
    else:  # syndicate
        z_rail('01 Quay rail', 'trim', limits, 3.8, h * .14, y0 + h * .07)
        x_beam('02 Outrigger beam', 'trim', limits, 1.8, 3.2, y0 + h * .1)
        keel_pad('03 Keel skid', 'dark', limits, (span[0] * .48, 2.6, span[2] * .72))
        plate('04 Truss trunk', 'trim', (rx * .2, h * .5, rz * .2), (c[0], y0 + h * .28, c[2]))
        plate('05 Quay deck', 'base', (span[0] * .7, 2.0, span[2] * .6), (c[0], by, c[2]))
        # The Syndicate yard hauls its cargo forward and keeps its drums and crane aft - the
        # Legion quay does the opposite - so the two stations of this kind read as different
        # layouts rather than one body with two paint schemes. The batch's design guard measures
        # exactly that: where each design inside a shared footprint carries its mass.
        bank('06 Container stack', 'dark', 4, (9.0, h * .34, 10.0), (c[0] - rx * .52,
                                                                    by + h * .1, c[2] + rz * .44),
             (8.8, 0., 6.4))
        bank('07 Stack doors', 'lit', 4, (5.0, 1.2, 5.4), (c[0] - rx * .52, by + h * .28,
                                                           c[2] + rz * .44), (8.8, 0., 6.4))
        for i in range(3):
            px = c[0] + rx * .42
            pz = c[2] + rz * .5 - i * rz * .5
            plate(f'08 Lash drum {i}', 'dark', (7.4, h * .3, 7.4), (px, by + h * .1, pz))
            plate(f'09 Drum ring {i}', 'accent', (8.0, 1.4, 8.0), (px, by + h * .26, pz))
        plate('10 Crane leg', 'trim', (2.6, h * .7, 2.6), (c[0] - rx * .3, y0 + h * .46,
                                                           c[2] + rz * .1))
        plate('11 Crane arm', 'trim', (span[0] * .3, 2.0, 3.0), (c[0] - rx * .5, hi[1] - 2.6,
                                                                  c[2] + rz * .1))
        top_cap('12 Arm head', 'accent', limits, (6.6, 2.4, 6.6), dx=-rx * .66, dz=rz * .1)
        plate('13 Hab cab', 'dark', (9.0, 7.0, 9.0), (c[0] + rx * .66, by + h * .14,
                                                        c[2] - rz * .34))
        plate('14 Cab lights', 'lit', (5.0, 1.2, 1.6), (c[0] + rx * .66, by + h * .32,
                                                         c[2] - rz * .34))
        bank('15 Cable run', 'cool', 4, (4.8, 1.2, 5.6), (c[0] - rx * .6, by + 1.2,
                                                          c[2] - rz * .7), (4.6, 0., 0.))
        bays(limits, rx * .2 / .62, rz * .2 / .62, by, c[2], .07)


# ---------------------------------------------------------------- fighter platform

def build_fighter_platform(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .34
    bh = h * .4
    if treatment == 'alliance':
        z_rail('01 Deck rail', 'trim', limits, 6.0, h * .12, y0 + h * .06)
        x_beam('02 Deck transom', 'trim', limits, h * .11, 4.0, y0 + h * .055)
        ringy('03 Flight deck', 'base', c[0], c[2], by - h * .1, rx * .78, rx * .2, h * .16,
              n=30, sz=rz * .86 / (rx * .78))
        ringy('04 Deck edge', 'accent', c[0], c[2], by - h * .1, rx * .84, rx * .68, 1.4, n=30,
              sz=rz * .9 / (rx * .78))
        plate('05 Bay housing', 'dark', (rx * .42, bh, rz * .42), (c[0], by, c[2]))
        torus('06 Launch bay', 'cool', by + h * .12, rx * .3, h * .1, m=26, n=8, cz=c[2])
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            px, pz = c[0] + rx * .55 * math.cos(a), c[2] + rz * .7 * math.sin(a)
            plate(f'07 Bay block {i}', 'dark', (10.0, h * .34, 12.0), (px, by, pz))
            plate(f'08 Bay doors {i}', 'lit', (8.4, 1.4, 2.2), (px, by + h * .2, pz + 4.0))
            plate(f'09 Bay rail {i}', 'trim', (1.6, 1.2, 12.0), (px + 5.4, by - h * .12, pz))
        plate('10 Control tower', 'trim', (7.0, hi[1] - 2.2 - (y0 + h * .5), 7.0),
              (c[0], (hi[1] - 2.2 + y0 + h * .5) / 2, c[2] - rz * .58))
        top_cap('11 Tower head', 'base', limits, (6.0, 2.2, 6.0), dz=-rz * .58)
        plate('12 Fuel cell bank', 'dark', (span[0] * .26, h * .26, 6.0), (c[0], by + h * .1,
                                                                            c[2] + rz * .5))
        bank('13 Cell louvre', 'cool', 5, (4.0, 1.6, 1.0), (c[0] - 8.0, by + h * .26,
                                                            c[2] + rz * .68), (3.8, 0., 0.))
        bays(limits, rx * .42 / .62, rz * .42 / .62, by, c[2], .02)
    elif treatment == 'legion':
        z_rail('01 Keel rail', 'trim', limits, rx * .28, h * .16, y0 + h * .08)
        x_beam('02 Keel transom', 'dark', limits, 1.6, 4.2, y0 + .8)
        plate('03 Lower bay tier', 'dark', (rx * .8, bh, rz * .8), (c[0], by, c[2]))
        plate('04 Tier light', 'cool', (rx * .64, 1.4, rz * .62), (c[0], y0 + h * .56, c[2]))
        plate('05 Upper bay tier', 'trim', (rx * .56, h * .3, rz * .5), (c[0], y0 + h * .64, c[2]))
        for i in range(4):
            side = -1 if i % 2 else 1
            pz = c[2] - rz * .44 + (i // 2) * rz * .88
            plate(f'06 Launch cell {i}', 'dark', (7.4, h * .3, 9.0), (c[0] + side * rx * .5,
                                                                     by, pz))
            plate(f'07 Cell mouth {i}', 'cool', (5.6, 1.6, 1.6), (c[0] + side * rx * .5, by,
                                                                  pz + 5.0))
            plate(f'08 Launch rail {i}', 'accent', (1.6, 1.4, 11.0),
                  (c[0] + side * (rx * .5 + 4.0), by - h * .2, pz))
        plate('09 Tower column', 'trim', (7.0, hi[1] - 3.0 - (y0 + h * .52), 7.0),
              (c[0], (hi[1] - 3.0 + y0 + h * .52) / 2, c[2] + rz * .6))
        plate('10 Tower belt', 'accent', (7.8, 1.6, 7.8), (c[0], hi[1] - 4.2, c[2] + rz * .6))
        top_cap('11 Tower head', 'base', limits, (5.6, 2.4, 5.6), dz=rz * .6)
        bank('12 Fuel stack', 'dark', 4, (4.6, 3.0, 4.0), (c[0] - rx * .46, by - h * .06,
                                                           c[2] - rz * .6), (4.4, 0., 0.))
        bank('13 Stack louvre', 'cool', 4, (4.4, 1.2, 1.0), (c[0] - rx * .46, by + h * .12,
                                                             c[2] - rz * .6), (4.2, 0., 0.))
        plate('14 Keel plate', 'dark', (rx * .28, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bays(limits, rx * .3 / .62, rz * .3 / .62, by, c[2], .05)
    else:  # syndicate
        z_rail('01 Frame rail', 'trim', limits, 2.6, h * .14, y0 + h * .07)
        x_beam('02 Outrigger beam', 'trim', limits, 1.8, 3.2, y0 + h * .1)
        keel_pad('03 Keel skid', 'dark', limits, (span[0] * .44, 2.6, span[2] * .7))
        plate('04 Truss trunk', 'trim', (rx * .2, h * .5, rz * .2), (c[0], y0 + h * .28, c[2]))
        plate('05 Frame deck', 'base', (span[0] * .64, 2.0, span[2] * .56), (c[0], by, c[2]))
        for i in range(4):
            side = -1 if i % 2 else 1
            px = c[0] + side * rx * .5
            pz = c[2] + rz * .3 + (i // 2) * rz * .56
            plate(f'06 Cradle block {i}', 'dark', (9.0, h * .3, 8.0), (px, by + h * .06, pz))
            plate(f'07 Cradle mouth {i}', 'cool', (6.4, 1.4, 1.6), (px, by + h * .06, pz + 4.6))
            plate(f'08 Cradle arm {i}', 'accent', (1.6, 1.4, 8.0), (px + side * 5.0,
                                                                   by - h * .1, pz))
        # The Legion flight deck stacks its cells over the middle of the station and puts its
        # tower forward; this one flies from the forward half and works its control tower and
        # habitation out of the aft end, which is what the design guard's mass-centre check
        # measures across the kind's shared footprint.
        plate('09 Control tower', 'trim', (7.4, hi[1] - 2.8 - (y0 + h * .48), 7.4),
              (c[0], (hi[1] - 2.8 + y0 + h * .48) / 2, c[2] - rz * .58))
        plate('10 Tower cab', 'dark', (8.8, h * .18, 8.8), (c[0], hi[1] - h * .12, c[2] - rz * .58))
        top_cap('11 Cab grid', 'lit', limits, (5.4, 2.0, 5.4), dz=-rz * .58)
        plate('12 Hab cab', 'dark', (8.6, 6.4, 8.6), (c[0] - rx * .72, by + h * .12,
                                                      c[2] - rz * .34))
        plate('13 Cab light strip', 'lit', (4.6, 1.2, 1.6), (c[0] - rx * .72,
                                                             by + h * .12 + 3.9,
                                                             c[2] - rz * .34))
        strut('14 Hab arm', 'trim', (c[0] - rx * .4, by + h * .08, c[2] - rz * .34),
              (c[0] - rx * .72, by + h * .12, c[2] - rz * .34), .7, .7, .2)
        bank('15 Cable run', 'cool', 4, (4.6, 1.2, 5.8), (c[0] - rx * .1, by + 1.2,
                                                          c[2] - rz * .6), (4.4, 0., 0.))
        bays(limits, rx * .2 / .62, rz * .2 / .62, by, c[2], .07)


# ---------------------------------------------------------------- repair dock

def build_repair_dock(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .32
    bh = h * .34
    if treatment == 'alliance':
        z_rail('01 Dock rail', 'trim', limits, 5.4, h * .12, y0 + h * .06)
        x_beam('02 Dock transom', 'trim', limits, h * .11, 4.0, y0 + h * .055)
        plate('03 Keel trunk', 'dark', (rx * .34, h * .4, rz * .34), (c[0], y0 + h * .2, c[2]))
        torus('04 Cradle band', 'base', by, rx * .74, rx * .07, m=38, n=10,
              sz=rz * .76 / (rx * .74), cz=c[2])
        ringy('05 Cradle rim', 'accent', c[0], c[2], by, rx * .82, rx * .64, 1.6, n=30,
              sz=rz * .84 / (rx * .74))
        ringy('06 Service deck', 'dark', c[0], c[2], y0 + h * .12, rx * .6, rx * .3, 1.6, n=28,
              sz=rz * .62 / (rx * .6))
        plate('07 Dock hub', 'dark', (rx * .3, bh, rz * .3), (c[0], by, c[2]))
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            px, pz = c[0] + rx * .74 * math.cos(a), c[2] + rz * .76 * math.sin(a)
            strut(f'08 Gantry arm {i}', 'trim', (c[0] + rx * .16 * math.cos(a), by,
                                                 c[2] + rz * .16 * math.sin(a)),
                  (px, by + h * .04, pz), .8, .8, .2)
            plate(f'09 Service pod {i}', 'dark', (6.4, h * .3, 6.4), (px, by, pz))
            plate(f'10 Pod louvre {i}', 'cool', (4.4, 1.2, 1.6),
                  (px, by + h * .2, pz + (2.4 if pz > c[2] else -2.4)))
        plate('11 Crane mast', 'trim', (2.6, hi[1] - 2.2 - (y0 + h * .5), 2.6),
              (c[0], (hi[1] - 2.2 + y0 + h * .5) / 2, c[2] - rz * .4))
        plate('12 Crane jib', 'accent', (16.0, 2.0, 3.0), (c[0] - 5.0, hi[1] - 2.6, c[2] - rz * .4))
        top_cap('13 Jib head', 'base', limits, (6.0, 2.2, 6.0), dz=-rz * .4)
        bank('14 Spares rack', 'dark', 4, (5.0, h * .2, 5.4), (c[0] - rx * .3, by,
                                                               c[2] - rz * .5), (0., 0., 5.2))
        plate('15 Keel plate', 'dark', (span[0] * .28, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bays(limits, rx * .3 / .62, rz * .3 / .62, by, c[2], .03)
    elif treatment == 'legion':
        z_rail('01 Keel rail', 'trim', limits, rx * .28, h * .14, y0 + h * .07)
        x_beam('02 Keel transom', 'dark', limits, 1.6, 4.2, y0 + .8)
        plate('03 Dock floor', 'dark', (rx * .6, bh, rz * .84), (c[0], by, c[2]))
        for side, label in ((-1, 'left'), (1, 'right')):
            plate(f'04 Dock tower {label}', 'trim', (8.0, hi[1] - h * .06 - (y0 + h * .08), 9.0),
                  (c[0] + side * rx * .74, (hi[1] - h * .06 + y0 + h * .08) / 2, c[2] - rz * .1))
            plate(f'05 Tower belt {label}', 'accent', (8.8, 1.6, 9.8),
                  (c[0] + side * rx * .74, hi[1] - h * .1, c[2] - rz * .1))
            plate(f'06 Tower gantry {label}', 'dark', (2.4, h * .3, rz * 1.5),
                  (c[0] + side * rx * .74, by, c[2] - rz * .1))
            strut(f'07 Dock arm {label}', 'trim', (c[0] + side * rx * .3, by, c[2] - rz * .1),
                  (c[0] + side * rx * .74, by + h * .16, c[2] - rz * .1), .8, .8, .2)
        plate('08 Cross span', 'trim', (rx * 1.2, h * .16, 4.0), (c[0], hi[1] - h * .14,
                                                                  c[2] - rz * .1))
        plate('09 Span belt', 'accent', (rx * 1.1, 1.4, 4.6), (c[0], hi[1] - h * .07,
                                                                c[2] - rz * .1))
        top_cap('10 Span head', 'base', limits, (6.0, 2.0, 6.0), dz=-rz * .1)
        plate('11 Well crib', 'dark', (rx * .4, h * .24, rz * .6), (c[0], by + h * .04,
                                                                    c[2] + rz * .5))
        plate('12 Crib light', 'lit', (rx * .3, 1.2, rz * .4), (c[0], by + h * .18, c[2] + rz * .5))
        bank('13 Coolant bank', 'cool', 4, (4.6, 2.6, 4.0), (c[0] - rx * .5, by - h * .04,
                                                             c[2] + rz * .62), (4.4, 0., 0.))
        plate('14 Keel plate', 'dark', (rx * .28, 1.4, span[2]), (c[0], y0 + .7, c[2]))
        bays(limits, rx * .3 / .62, rz * .3 / .62, by, c[2], .05)
    else:  # syndicate
        z_rail('01 Scaffold rail', 'trim', limits, 3.0, h * .14, y0 + h * .07)
        x_beam('02 Outrigger beam', 'trim', limits, 1.8, 3.2, y0 + h * .1)
        keel_pad('03 Keel skid', 'dark', limits, (span[0] * .46, 2.6, span[2] * .72))
        plate('04 Truss trunk', 'trim', (rx * .2, h * .48, rz * .2), (c[0], y0 + h * .26, c[2]))
        plate('05 Rig deck', 'base', (span[0] * .68, 1.8, span[2] * .56), (c[0], by, c[2]))
        for side, label in ((-1, 'left'), (1, 'right')):
            plate(f'06 Frame post {label}', 'trim', (5.2, h * .52, 5.2),
                  (c[0] + side * rx * .58, y0 + h * .42, c[2] - rz * .3))
            plate(f'07 Frame cap {label}', 'accent', (6.0, 1.6, 6.0),
                  (c[0] + side * rx * .58, y0 + h * .66, c[2] - rz * .3))
            strut(f'08 Cross member {label}', 'trim', (c[0] + side * rx * .1, y0 + h * .52,
                                                       c[2] - rz * .3),
                  (c[0] + side * rx * .58, y0 + h * .58, c[2] - rz * .3), .7, .7, .2)
            plate(f'09 Cradle pad {label}', 'dark', (6.0, 4.4, 7.4),
                  (c[0] + side * rx * .4, by + h * .04, c[2] + rz * .5))
        for i in range(3):
            px = c[0] + rx * .74
            pz = c[2] - rz * .5 + i * rz * .48
            plate(f'10 Spare drum {i}', 'dark', (7.0, h * .26, 7.4), (px, by + h * .06, pz))
            plate(f'11 Drum ring {i}', 'accent', (7.6, 1.4, 8.0), (px, by + h * .2, pz))
        plate('12 Service cab', 'dark', (8.0, 6.0, 8.0), (c[0] - rx * .66, by + h * .08,
                                                          c[2] + rz * .2))
        plate('13 Cab light strip', 'lit', (4.2, 1.2, 1.6), (c[0] - rx * .66,
                                                             by + h * .08 + 3.4, c[2] + rz * .2))
        plate('14 Mast', 'trim', (2.2, hi[1] - 3.4 - (y0 + h * .46), 2.2),
              (c[0], (hi[1] - 3.4 + y0 + h * .46) / 2, c[2] - rz * .66))
        top_cap('15 Mast head', 'dark', limits, (5.4, 3.4, 5.4), dz=-rz * .66)
        bank('16 Cable run', 'cool', 4, (4.6, 1.2, 5.6), (c[0] - rx * .5, by + 1.2,
                                                          c[2] - rz * .7), (4.4, 0., 0.))
        bays(limits, rx * .2 / .62, rz * .2 / .62, by, c[2], .06)


# ---------------------------------------------------------------- shipyard

def build_shipyard(limits, treatment):
    lo, hi, c, span = frame(limits)
    rx, rz, h = span[0] / 2, span[2] / 2, span[1]
    y0, by = lo[1], lo[1] + h * .3
    bh = h * .34
    if treatment == 'legion':
        z_rail('01 Slipway rail left', 'trim', limits, rx * .14, h * .12, y0 + h * .06)
        plate('02 Slipway rail right', 'trim', (rx * .28, h * .12, span[2]),
              (c[0] + rx * .68, y0 + h * .06, c[2]))
        x_beam('03 Slipway transom', 'dark', limits, 1.8, 5.0, y0 + h * .09)
        # The keel bed is the wide structure the whole yard hangs off: the gantry frames,
        # the bastions and the hall all overlap it in Y as well as X, so the weld finds one
        # cluster instead of a hall floating aft of an isolated slipway.
        plate('04 Keel bed', 'dark', (span[0] * .78, h * .34, rz * .96), (c[0], by, c[2]))
        bank('05 Bed cradle', 'cool', 5, (rx * .5, 1.4, 4.0), (c[0] - rx * .4, by + h * .19,
                                                               c[2] - rz * .5), (0., 0., rz * .25))
        for i in range(3):
            pz = c[2] - rz * .6 + i * rz * .58
            plate(f'06 Gantry frame {i}', 'trim', (span[0] * .9, h * .18, 4.0),
                  (c[0], by + h * .16, pz))
            plate(f'07 Frame belt {i}', 'accent', (span[0] * .78, 1.6, 4.6),
                  (c[0], by + h * .27, pz))
            plate(f'08 Frame bay {i}', 'lit', (span[0] * .3, 1.2, 2.6),
                  (c[0], by + h * .16, pz + 6.0))
        plate('09 Build hall', 'dark', (rx * .8, hi[1] - 2.4 - by, rz * .5),
              (c[0], (hi[1] - 2.4 + by) / 2, c[2] + rz * .62))
        top_cap('10 Hall roof', 'base', limits, (rx * .84, 2.4, rz * .56), dz=rz * .62)
        plate('11 Hall light strip', 'lit', (rx * .7, 1.4, 1.2), (c[0], hi[1] - h * .16,
                                                                  c[2] + rz * .62))
        plate('12 Hall spine', 'trim', (span[0] * .94, h * .1, 3.0), (c[0], by + h * .2,
                                                                      c[2] + rz * .62))
        for side, label in ((-1, 'left'), (1, 'right')):
            plate(f'13 Yard bastion {label}', 'dark', (7.0, h * .3, 12.0),
                  (c[0] + side * (rx - 4.4), by + h * .12, c[2] - rz * .48))
            plate(f'14 Bastion belt {label}', 'accent', (7.4, 1.6, 12.8),
                  (c[0] + side * (rx - 4.4), by + h * .26, c[2] - rz * .48))
        bank('15 Coolant stack', 'cool', 4, (4.6, 2.8, 4.2), (c[0] - rx * .5, by + h * .14,
                                                              c[2] + rz * .1), (4.4, 0., 0.))
        # The cooling plant has to stand on the face the rear camera actually resolves: a
        # low-pitch rear eye is occluded by the keel bed's own aft face, so a `cool` bank on
        # top of the bed measured 0 changed pixels and its ablation proved nothing. A radiator
        # on the aft face itself is visible from the frame the ablation is measured in.
        plate('16 Aft radiator', 'cool', (span[0] * .5, h * .2, 3.0),
              (c[0], by + h * .02, c[2] - rz * .48 - 1.6))
        plate('17 Radiator cowl', 'dark', (span[0] * .56, h * .24, 1.0),
              (c[0], by + h * .02, c[2] - rz * .48 - 3.4))
        # The aft ends of the slipway rails are the only structure the low rear eye can see
        # without the keel bed's own aft face cutting in front of it, so the vent bank that
        # proves the `cool` role reaches pixels sits there, straddling the left rail.
        bank('18 Aft vent bank', 'cool', 5, (rx * .12, h * .18, 4.0),
             (c[0] - rx * .28, by - h * .1, c[2] - rz * .86), (rx * .12, 0., 0.))
        bays(limits, rx * .34 / .62, rz * .34 / .62, by, c[2], .04)
    else:  # syndicate
        z_rail('01 Slipway rail left', 'trim', limits, 2.6, h * .1, y0 + h * .05)
        plate('02 Slipway rail right', 'trim', (5.2, h * .1, span[2]),
              (c[0] + rx * .62, y0 + h * .05, c[2]))
        x_beam('03 Outrigger beam', 'dark', limits, 1.8, 3.4, y0 + h * .08)
        keel_pad('04 Keel skid', 'dark', limits, (span[0] * .48, 2.8, span[2] * .7))
        plate('05 Yard deck', 'base', (span[0] * .72, h * .26, span[2] * .72), (c[0], by, c[2]))
        for i in range(3):
            pz = c[2] - rz * .62 + i * rz * .5
            plate(f'06 Gantry truss {i}', 'trim', (span[0] * .84, h * .14, 3.6),
                  (c[0], by + h * .12, pz))
            plate(f'07 Truss ring {i}', 'accent', (span[0] * .7, 1.6, 4.2),
                  (c[0], by + h * .19, pz))
            plate(f'08 Truss light {i}', 'lit', (span[0] * .26, 1.2, 2.4),
                  (c[0] - span[0] * .3, by + h * .12, pz + 5.4))
        # The Syndicate yard builds its ships at the *aft* end of the slipway, where the Legion
        # yard's hall stands forward of its gantries: two stations of the same kind share a
        # footprint, so their difference has to be structural, and where the mass sits is what
        # the batch's own design guard measures.
        plate('09 Yard hall', 'dark', (span[0] * .46, hi[1] - 2.2 - by, rz * .5),
              (c[0], (hi[1] - 2.2 + by) / 2, c[2] - rz * .62))
        top_cap('10 Hall roof grid', 'base', limits, (span[0] * .4, 2.2, rz * .54), dz=-rz * .62)
        bank('11 Spare plating', 'dark', 4, (10.0, 1.8, 8.0), (c[0] - rx * .56, by + h * .12,
                                                               c[2] + rz * .58), (9.6, 0., 4.4))
        for i in range(3):
            px = c[0] + rx * .62
            pz = c[2] - rz * .5 + i * rz * .4
            plate(f'12 Yard drum {i}', 'dark', (7.4, h * .26, 7.4), (px, by + h * .08, pz))
            plate(f'13 Drum ring {i}', 'accent', (8.0, 1.4, 8.0), (px, by + h * .2, pz))
        plate('14 Yard cab', 'dark', (9.0, 7.0, 9.0), (c[0] - rx * .66, by + h * .1, c[2] + rz * .1))
        plate('15 Cab light strip', 'lit', (5.0, 1.2, 1.6), (c[0] - rx * .66, by + h * .1 + 3.9,
                                                              c[2] + rz * .1))
        bank('16 Cable run', 'cool', 4, (4.6, 1.2, 6.0), (c[0] - rx * .3, by + h * .2,
                                                          c[2] + rz * .5), (4.4, 0., 0.))
        # With the hall moved aft, the deck's own cooling is behind the build hall from the
        # rear camera - and the rear frame is where the `cool` ablation is measured. The aft
        # ends of the slipway rails are the structure that eye sees unobstructed, so a vent
        # bank straddles the left rail there, as the Legion yard's does.
        bank('17 Aft vent bank', 'cool', 5, (rx * .12, h * .18, 4.0),
             (c[0] - rx * .28, by - h * .1, c[2] - rz * .8), (rx * .12, 0., 0.))
        bays(limits, rx * .2 / .62, rz * .2 / .62, by, c[2], .05)


BUILDERS = {'research_station': build_research_station, 'defense_platform': build_defense_platform,
            'trade_station': build_trade_station, 'fighter_platform': build_fighter_platform,
            'repair_dock': build_repair_dock, 'shipyard': build_shipyard}


def build(key):
    identifier, radius, limits, treatment = SEEDS[key]
    master = ROOT / f'art/blender/{identifier}.blend'
    if master.exists() and '--replace-seed' not in sys.argv:
        raise RuntimeError(f'{master.name} is the editable master. Use export_{identifier}.py; '
                           f'--replace-seed destroys edits.')
    # A per-asset reset must not reload factory settings: alliance_common's import already
    # emptied the startup scene and built the role materials, and a factory reset takes those
    # materials with it (`ReferenceError: StructRNA of type Material has been removed`).
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
        seed_recipe='tools/art/build_b3c_stations.py; initial authoring only, never rebuild '
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
