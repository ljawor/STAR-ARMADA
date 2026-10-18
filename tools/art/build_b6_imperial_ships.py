#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPE ONLY. The editable .blend is a derived artifact afterwards.

S06 batch B6 - the Imperial ships. Eleven Imperial bindings are ships
(`art/manifests/handoffs/S06-B6-IMPERIAL-SHIPS.md`); this seed is their recipe, and it carries the
batch's first three rows: `ship:imperial:corvette`, `ship:imperial:tie_squadron` and
`ship:imperial:tie_bomber_squadron`.

`ship:imperial:corvette` is the legacy `needle` archetype: a slender pointed combat hull, drawn
today by `render/fleet_geometry.py::_ship_mesh` at 1,552 triangles and 858 vertices inside the
measured envelope -16.000,-5.000,-43.601 .. 16.000,24.000,48.000 (`ShipData.radius=34.0`). The
Imperial corvette is that shape in grey: a faceted pressure hull with a dorsal armour run and
turret deck, a pair of outboard sponsons that carry the beam, a keel fin, two engine bells,
identification striping, and a tall radiator fin whose tip is the ship's highest point.

`ship:imperial:tie_squadron` and `ship:imperial:tie_bomber_squadron` are the legacy `wedge`
archetype: 1,456 triangles and 792 vertices of flat squadron wing inside the measured envelope
-31.250,-3.240,-28.996 .. 31.250,14.000,35.000 (`ShipData.radius=22.0` and `24.0`). A squadron row
is an Imperial TIE rather than a wedge: a faceted cockpit globe on a short pylon between two large
flat hexagonal wing panels. The panel's rim ring carries the whole measured box - its outer plane is
the beam extreme and its hexagonal rim walls carry the Y and Z extremes - the pod sits on the box
centreline, the engine bells sit at the pod's stern, and a forward sensor mast, a sensor ring and
wing vanes carry the cool role. The bomber is its own hull, not the fighter scaled: a heavier pod,
thicker pylons, a doubled wing rim and a pair of munition cylinders, all of it row data.

**Script-authoritative per the S03 source-authority policy** (repeated modular hardware): the recipe
is the master and the `.blend` is a derived artifact. Every dimension below is derived from the
binding's own legacy extent, because `render/ship_sizes.ship_size` derives the class scale, the
drawn length, the review cameras and the collision radius from the drawn length: a hull that filled
less of the box would change the ship's size in game.

**The rows are data.** `ROWS` is a table keyed by binding, `build(key)` authors one row, and the
eight Imperial rows after these are added as rows rather than as a second copy of this file.

`build(key)` returns `(verts, faces, role_of_face)` and `main()` groups the kit into one object per
loader role, as the B5 environment seed does, so the export's six material-role batches are authored
rather than derived. Each part is still made by `alliance_common`'s own primitives - the same ring,
chamfer and evaluated bevel as every other asset in the batch - and harvested back into data.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b6_imperial_ships.py \
        -- --asset ship:imperial:tie_squadron
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# An extent error below this many world units is float noise in the evaluated depsgraph, not a
# breach; the export wrapper's edge quantiser then snaps it onto the declared edge.
BREACH_TOLERANCE = 1e-3

# --------------------------------------------------------------------------------------------- rows
# One entry per binding, plain literals so a guard can read the table without Blender and a later
# Imperial row is a row. `limits` is the binding's own legacy extent, measured from the live
# renderer by `tools/art/probe_b6_scope.py`; `station_radius` is the row's scale envelope from
# `art/manifests/model_inventory.json`. A legacy shape is *not* shared between rows: the frigate
# draws the same `needle` mesh today but is its own row with its own envelope and its own hull.
ROWS = {
    'ship:imperial:corvette': dict(
        identifier='imperial_corvette',
        data_id='imperial_corvette',
        label='Vigil Corvette',
        ship_kind='corvette',
        faction='imperial',
        legacy_shape='needle',
        limits=[[-16.0, 16.0], [-5.0, 24.0], [-43.601, 48.0]],
        legacy_triangles=1552,
        legacy_vertices=858,
        station_radius=34.0,
        design=('Imperial grey combat corvette: a faceted needle hull with a dorsal armour run and '
                'turret deck, outboard sponsons carrying the beam, twin engine bells, identification '
                'striping and a tall radiator fin'),
    ),
    'ship:imperial:tie_squadron': dict(
        identifier='imperial_tie_squadron',
        data_id='imperial_tie_squadron',
        label='Talon Interceptor Squadron',
        ship_kind='tie_squadron',
        faction='imperial',
        legacy_shape='wedge',
        limits=[[-31.25, 31.25], [-3.24, 14.0], [-28.996, 35.0]],
        legacy_triangles=1456,
        legacy_vertices=792,
        station_radius=22.0,
        pod_radius=5.6,
        pod_rings=9,
        spar_thickness=2.2,
        panel_thickness=0.9,
        panel_frames=2,
        ordnance=0,
        design=('Imperial TIE interceptor squadron: a faceted spherical cockpit pod on a short '
                'pylon between two large flat hexagonal wing panels, dark panel fields inside '
                'bright rim banding, a lit engine bank at the pod stern and a cool-toned forward '
                'sensor mast'),
    ),
    'ship:imperial:tie_bomber_squadron': dict(
        identifier='imperial_tie_bomber_squadron',
        data_id='imperial_tie_bomber_squadron',
        label='Hammer Torpedo Squadron',
        ship_kind='tie_bomber_squadron',
        faction='imperial',
        legacy_shape='wedge',
        limits=[[-31.25, 31.25], [-3.24, 14.0], [-28.996, 35.0]],
        legacy_triangles=1456,
        legacy_vertices=792,
        station_radius=24.0,
        pod_radius=6.8,
        pod_rings=13,
        spar_thickness=3.6,
        panel_thickness=1.3,
        panel_frames=4,
        ordnance=2,
        design=('Imperial TIE bomber squadron: a heavier faceted cockpit globe on thick pylons '
                'between two large flat hexagonal wing panels, two munition cylinders under the '
                'pylon, doubled bright rim banding, a lit engine bank and a cool-toned sensor ring'),
    ),
}

# The weld pass at this asset's scale. The station defaults (tolerance .25, grow up to 2.5 units,
# braces up to 10) are stated for hundred-unit hardware; this hull is 91 units long and its fitted
# details are one to three units deep, so the same rules are stated at about a third of that. The
# kit is authored so every part sits *inside* its host, so the pass reports what it joined rather
# than reshaping a panel onto a hull it never touched.
WELD = dict(tolerance=0.2, grow_max=1.0, min_half=0.25, max_half=0.8, overlap=0.05, max_brace=6.0)
SEED_RECIPE = ('tools/art/build_b6_imperial_ships.py; script-authoritative per the S03 '
               'source-authority policy for repeated modular hardware - the recipe is the master, '
               'the .blend is derived')
PROVENANCE = ('Original geometry generated by this recipe; no external mesh or texture '
              'dependencies')

_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_master(argv):
    """Refuse before Blender is imported, and before anything is written."""
    if not argv or '--all' in argv:
        keys = list(ROWS)
    elif '--asset' in argv:
        keys = [argv[argv.index('--asset') + 1]]
    else:
        keys = []
    for key in keys:
        if key not in ROWS:
            raise RuntimeError(f'unknown target {key}; the B6 batch authors {sorted(ROWS)}')
        master = ROOT / f"art/blender/{ROWS[key]['identifier']}.blend"
        if master.exists() and '--replace-seed' not in argv:
            raise RuntimeError(f'{master.name} is the editable master. Use '
                               f"export_{ROWS[key]['identifier']}.py; --replace-seed destroys edits.")


_refuse_existing_master(_ARGV)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import (ROLES, annulus, cylinder, loft, mesh_object,  # noqa: E402
                             plate, weld_scene)
import bpy  # noqa: E402,F401


# ---------------------------------------------------------------------------------------- geometry
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


# --------------------------------------------------------------- the TIE wing panel, as pure data
# The panel's frame is a pure function of the row's own measured extent, so a guard can drive it
# without Blender (`tests/test_alliance_blender_b6_imperial_ships.py`,
# `test_the_tie_panel_pair_fills_the_legacy_box_per_axis_and_per_side`) and a later squadron row is
# a row rather than a second kit. Both functions below are self-contained - no module constant, no
# helper - so that extraction really does evaluate the shape the seed authors.
def hex_frame(limits):
    """The TIE panel's hexagonal frame, divided out of the binding's own legacy extent.

    The panel is elongated along Z and its six vertices sit at 30/90/150/210/270/330 degrees. That
    puts the two Z extremes on corner vertices and the two Y extremes on the *vertical rim edges*
    between the 30/330 and 150/210 pairs, so both Y extremes are edges rather than corners and no
    chamfer can round them off; the flat faces carry the beam. Every number is derived, never
    transcribed.
    """
    lo, hi, centre, span = frame(limits)
    return {'centre': tuple(centre),
            'half_y': (hi[1] - lo[1]) / (2 * math.cos(math.pi / 6)),
            'half_z': (hi[2] - lo[2]) / 2,
            'lo': tuple(lo),
            'hi': tuple(hi)}


def hex_face_geometry(limits, side, scale, depth, offset=0.0, shift=(0.0, 0.0)):
    """A flat hexagonal face on one wing panel, as `(verts, faces)` in the row's own frame.

    `side` is -1 (port) or +1 (starboard). The outermost plane is exactly `offset` inside that
    side's beam extreme - never outside it, because a detail that protruded would breach the legacy
    box the row is measured against - and the face extends `depth` further in. `scale` shrinks the
    hexagon inside the panel's own hexagon; `shift` moves it in (y, z).
    """
    hx = hex_frame(limits)
    _, cy, cz = hx['centre']
    cy, cz = cy + shift[0], cz + shift[1]
    face = hx['hi'][0] if side > 0 else hx['lo'][0]
    xs = (face - side * offset, face - side * (offset + depth))
    profile = [(cy + scale * hx['half_y'] * math.cos(math.pi * (0.5 + i / 3.0)),
                cz + scale * hx['half_z'] * math.sin(math.pi * (0.5 + i / 3.0))) for i in range(6)]
    verts = [(x, y, z) for x in xs for (y, z) in profile]
    faces = [tuple(range(6)), tuple(reversed(range(6, 12)))]
    faces.extend((i, (i + 1) % 6, 6 + (i + 1) % 6, 6 + i) for i in range(6))
    return verts, faces


def hex_ring_geometry(limits, side, outer, inner, depth, offset=0.0, shift=(0.0, 0.0)):
    """A flat hexagonal frame on one wing panel, as `(verts, faces)` in the row's own frame.

    This is the panel's rim: `outer` is the panel's whole hexagon, so the ring's outer walls carry
    the four Y/Z extremes, and its outermost plane carries the beam extreme on that side. `inner`
    cuts the aperture the dark field shows through.
    """
    hx = hex_frame(limits)
    _, cy, cz = hx['centre']
    cy, cz = cy + shift[0], cz + shift[1]
    face = hx['hi'][0] if side > 0 else hx['lo'][0]
    xs = (face - side * offset, face - side * (offset + depth))
    profile = []
    for scale in (outer, inner):
        profile.extend((cy + scale * hx['half_y'] * math.cos(math.pi * (0.5 + i / 3.0)),
                        cz + scale * hx['half_z'] * math.sin(math.pi * (0.5 + i / 3.0)))
                       for i in range(6))
    verts = [(x, y, z) for x in xs for (y, z) in profile]
    faces = []
    for i in range(6):
        j = (i + 1) % 6
        faces.append((i, j, 6 + j, 6 + i))                    # outer wall
        faces.append((12 + i, 12 + j, 18 + j, 18 + i))        # inner wall
        faces.append((i, 12 + i, 12 + j, j))                  # rim at the outermost plane
        faces.append((6 + i, 18 + i, 18 + j, 6 + j))          # rim at the inner plane
    return verts, faces


def tie_pod_sections(limits, radius, rings):
    """The cockpit globe's loft frames, as `(z, w, top, bottom)` in the row's own frame.

    `radius` and `rings` are row data, so the bomber's heavier pod is a row and not a second
    builder. The globe is placed on the box centreline and its half-height is at most `radius`, so
    it never carries the envelope - the wing panels do - and it clears the panels' inner faces.
    """
    lo, hi, centre, span = frame(limits)
    _, cy, cz = centre
    sections = []
    for k in range(rings):
        angle = math.pi * ((k + 0.5) / rings - 0.5)          # just inside -pi/2 .. +pi/2
        r = radius * math.cos(angle)
        sections.append((cz + radius * math.sin(angle), r, cy + r, cy - r))
    return tuple(sections)


# ------------------------------------------------------- the same panel and globe as scene objects
def hex_face(name, role, limits, side, scale, depth, offset=0.0, shift=(0.0, 0.0), bevel=0.0):
    verts, faces = hex_face_geometry(limits, side, scale, depth, offset, shift)
    return mesh_object(name, role, verts, faces, bevel)


def hex_ring(name, role, limits, side, outer, inner, depth, offset=0.0, shift=(0.0, 0.0),
             bevel=0.0):
    verts, faces = hex_ring_geometry(limits, side, outer, inner, depth, offset, shift)
    return mesh_object(name, role, verts, faces, bevel)


class Kit:
    """One hull's parts, as `(verts, faces, role_of_face)`.

    `alliance_common`'s primitives build scene objects and this seed is a data recipe, so each part
    is made by the shared primitive, harvested from the evaluated mesh (which is what bakes a
    large armour surface's bevel) and removed again. The alternative - restating the ring, the
    chamfer and the cap here - would put a second definition of the house hull in the tree.
    """

    def __init__(self):
        self.verts = []
        self.faces = []
        self.roles = []
        self.parts = {}

    def add(self, builder, name, role, *args, **kwargs):
        obj = builder(name, role, *args, **kwargs)
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        base = len(self.verts)
        matrix = obj.matrix_world
        points = [tuple(float(c) for c in matrix @ vertex.co) for vertex in mesh.vertices]
        self.verts.extend(points)
        # The part's own box, kept beside the triangles: the contact check below needs the part
        # names, and grouping the kit into role objects is what takes them away.
        self.parts[name] = (tuple(min(p[i] for p in points) for i in range(3)),
                            tuple(max(p[i] for p in points) for i in range(3)))
        for triangle in mesh.loop_triangles:
            self.faces.append(tuple(base + i for i in triangle.vertices))
            self.roles.append(role)
        evaluated.to_mesh_clear()
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(data)
        return self

    def loft(self, name, role, sections, bevel=0.0, centre=(0, 0, 0), chamfer=0.25):
        return self.add(loft, name, role, sections, bevel, centre, chamfer)

    def plate(self, name, role, size, centre):
        return self.add(plate, name, role, size, centre)

    def cylinder(self, name, role, centre, radius, depth, axis='Z', n=12):
        return self.add(cylinder, name, role, centre, radius, depth, axis, n)

    def annulus(self, name, role, x, y, frames, n=16):
        return self.add(annulus, name, role, x, y, frames, n)


def build_imperial_corvette(kit, row):
    """The needle corvette: hull plating, recessed panels, edge banding, striping, glow and fins.

    Every reach is stated against the row's own extent: the pressure hull carries the bow (Z max)
    and the Y minimum, the sponsons carry the beam (X extremes), the radiator fin carries the Y
    maximum, and the engine bells carry the stern (Z min).
    """
    lo, hi, centre, span = frame(row['limits'])
    # A slender pointed combat hull: deepest section just aft of amidships, knife bow at Z max.
    kit.loft('01 Needle pressure hull', 'base',
             ((-40, 6.6, 5.0, -4.0), (-33, 8.6, 5.6, -4.6), (-30, 9.6, 6.0, -5.0),
              (-14, 10.6, 6.4, -4.6), (-2, 9.6, 6.2, -4.2), (12, 7.8, 6.0, -4.0),
              (30, 4.6, 4.0, -2.6), (48, 1.1, 2.0, -1.2)), .35)
    # Dorsal armour run: the raised plate that makes the hull read as one beam.
    kit.loft('02 Dorsal armour run', 'base',
             ((-34, 5.2, 12.4, 4.6), (-24, 5.4, 13.6, 5.4), (-12, 4.4, 12.0, 5.4),
              (-6, 3.0, 9.0, 5.4)), .3)
    # Aft hull skirt: the stern block the engine bells are seated in.
    kit.loft('03 Aft hull skirt', 'base',
             ((-43, 7.4, 3.6, -3.4), (-39, 9.0, 4.6, -4.2), (-34, 10.4, 5.4, -4.6)), .25)
    for side in (-1, 1):
        # Outboard sponsons: w=4.0 at x=+-12 puts the outer face exactly on the beam extreme, and
        # the deepest frame's underside exactly on the Y minimum.
        kit.loft(f'04 Outboard sponson {side}', 'base',
                 ((-26, 4.0, 4.0, -4.0), (-20, 4.0, 4.0, -4.0), (-4, 4.0, 4.0, -4.0),
                  (8, 2.4, 3.0, -3.0), (14, 1.2, 2.2, -2.2)), .3, (side * 12, -1, 0))
    # Deep ventral keel fin: the ship's lowest point, and its silhouette from below.
    kit.loft('05 Ventral keel fin', 'base',
             ((-30, 2.6, -3.0, -5.0), (-22, 3.0, -3.4, -5.0), (-10, 2.4, -3.0, -4.6)), .2)
    kit.plate('06 Ventral prow plow', 'base', (5.0, 2.4, 9.0), (0, -2.6, 34))
    kit.plate('07 Dorsal deck housing', 'base', (6.6, 2.6, 10.0), (0, 12.4, -29))

    # Recessed panels and undersides, in shadow under the plating above them.
    kit.plate('10 Ventral recessed panel', 'dark', (7.4, 1.2, 26.0), (0, -4.0, -2))
    kit.plate('11 Engine housing recess', 'dark', (11.0, 6.0, 6.0), (0, 0.8, -40.5))
    kit.plate('12 Prow sensor housing', 'dark', (3.4, 2.0, 5.0), (0, 4.6, 33))
    for side in (-1, 1):
        kit.plate(f'13 Aft flank recess {side}', 'dark', (1.0, 3.0, 9.0), (side * 9.6, 0.6, -24))
        kit.plate(f'14 Sponson underside recess {side}', 'dark', (1.8, 1.6, 11.0),
                  (side * 12, -3.4, -10))

    # Bright edge banding and the turret bodies that go with it.
    for side in (-1, 1):
        # The sheer band sits on the hull's chamfered upper edge, which is where (w-c, top) lands,
        # and stops where the hull is still wider than the band's inner face.
        kit.plate(f'20 Sheer edge band {side}', 'trim', (1.2, 1.0, 30.0), (side * 8.0, 5.4, -10))
        kit.cylinder(f'21 Turret body {side}', 'trim', (side * 4.0, 13.4, -18), .9, 2.6, 'Y', 12)
        kit.plate(f'22 Turret barrel {side}', 'trim', (0.7, 0.7, 7.0), (side * 4.0, 13.4, -16))
    kit.plate('23 Dorsal spine collar', 'trim', (5.6, 1.2, 2.4), (0, 13.6, -25))
    kit.plate('24 Bow collar', 'trim', (4.4, 1.0, 2.4), (0, 8.4, -6))
    kit.plate('25 Stern transom band', 'trim', (9.6, 1.2, 1.6), (0, 4.2, -42))

    # Identification striping: raised bands the ablation guard can see from any camera.
    for side in (-1, 1):
        kit.plate(f'30 Flank stripe {side}', 'accent', (0.8, 1.8, 5.0), (side * 10.2, 3.0, -24))
        kit.plate(f'31 Aft flank stripe {side}', 'accent', (0.8, 1.4, 4.0), (side * 9.0, 1.0, -31))
        kit.plate(f'32 Sponson stripe {side}', 'accent', (7.0, 1.4, 3.0), (side * 12.4, 3.0, -8))
        kit.plate(f'33 Keel stripe {side}', 'accent', (0.8, 1.2, 6.0), (side * 2.6, -3.4, -16))
    kit.plate('34 Prow chevron', 'accent', (1.8, 1.6, 6.0), (0, 3.4, 28))

    # The drive: two engine bells whose mouths are the stern extreme, plus running lights.
    for side in (-1, 1):
        kit.cylinder(f'40 Engine bell {side}', 'lit', (side * 5.2, 0.4, -41.0), 3.2, 5.202, 'Z', 14)
        kit.plate(f'41 Marker light {side}', 'lit', (0.7, 1.6, 0.7), (side * 7.6, 5.2, -32))
        kit.plate(f'42 Flank vent {side}', 'lit', (0.6, 2.0, 6.0), (side * 10.4, 0.6, -20))
    kit.plate('43 Bridge visor slit', 'lit', (2.6, 0.6, 4.0), (0, 4.6, 26))
    kit.plate('44 Deck luminaire', 'lit', (3.0, 1.0, 3.0), (0, 12.8, -32))

    # Sensor and radiator fins. The dorsal fin's tip is the ship's Y maximum.
    kit.plate('50 Dorsal radiator fin', 'cool', (0.9, 12.0, 16.0), (0, 18.0, -22))
    for side in (-1, 1):
        kit.plate(f'51 Side radiator fin {side}', 'cool', (0.8, 5.0, 9.0), (side * 8.6, 6.0, -12))
        kit.plate(f'52 Prow sensor vane {side}', 'cool', (0.6, 3.0, 7.0), (side * 2.4, 4.4, 33))
        kit.plate(f'53 Aft radiator vane {side}', 'cool', (0.7, 3.4, 5.0), (side * 5.6, 4.0, -37))
    kit.plate('54 Ventral radiator plate', 'cool', (5.0, 1.0, 10.0), (0, -4.4, -22))


def build_imperial_tie(kit, row):
    """The TIE squadron row: a cockpit globe on a pylon between two hexagonal wing panels.

    Every reach is stated against the row's own extent. The two wing panels carry the whole measured
    box - the rim ring's outer plane is the beam extreme and its outer walls are the panel's whole
    hexagon, so the Y and Z extremes ride on rim *edges* a chamfer cannot round - while the pod, the
    pylon, the engine bank, the viewscreen and the sensor array all sit strictly inside. The row's
    own numbers - pod radius, ring count, pylon thickness, panel thickness, rim count and payload -
    are what make the bomber a heavier hull rather than a scaled fighter.
    """
    lo, hi, centre, span = frame(row['limits'])
    cx, cy, cz = centre
    pod_r = row['pod_radius']
    rings = row['pod_rings']
    spar_t = row['spar_thickness']
    panel_t = row['panel_thickness']
    frames = row['panel_frames']
    # The pylon's outer end reaches into both panels (the panel stack starts 0.55 in from the beam
    # extreme) but never through the beam extreme itself.
    half_x = abs(hi[0]) - 0.4

    # 01-09  The wing panels. The rim ring carries the whole measured box; the field, the body and
    # every fitting sit strictly inside it, so the envelope is authored rather than approached.
    for side in (-1, 1):
        kit.add(hex_ring, f'01 Wing rim {side}', 'trim', row['limits'], side, 1.0, 0.885, 0.7)
        kit.add(hex_face, f'02 Wing field {side}', 'dark', row['limits'], side, 0.90, 0.8, 0.10)
        kit.add(hex_face, f'03 Wing body {side}', 'base', row['limits'], side, 0.86, panel_t, 0.18)
        kit.add(hex_face, f'04 Wing hub {side}', 'trim', row['limits'], side, 0.30, 0.45, 0.06)
        kit.add(hex_face, f'05 Wing marking {side}', 'accent', row['limits'], side, 0.34, 0.3,
                0.06, (0.0, 10.0))
        kit.add(hex_face, f'06 Wing sensor boss {side}', 'cool', row['limits'], side, 0.20, 0.35,
                0.06, (0.0, -9.0))
        kit.add(hex_face, f'07 Wing lamp {side}', 'lit', row['limits'], side, 0.12, 0.25, 0.06,
                (0.0, -16.0))
        # The rim count is row data: the bomber's wing carries a doubled inner frame.
        for k in range(1, frames):
            kit.add(hex_ring, f'08 Wing inner rim {k} {side}', 'trim', row['limits'], side,
                    0.84 - 0.06 * k, 0.74 - 0.06 * k, 0.5, 0.12)

    # 10-11  The cockpit globe, on the box centreline, and the pylon that joins it to both wings.
    kit.loft('10 Cockpit pod', 'base', tie_pod_sections(row['limits'], pod_r, rings), .25)
    kit.loft('11 Wing pylon', 'base',
             ((cz - spar_t / 2, half_x, cy + spar_t / 2, cy - spar_t / 2),
              (cz + spar_t / 2, half_x, cy + spar_t / 2, cy - spar_t / 2)), .2)

    # 15-19  The pod's banding: the collars and the sensor ring that break up the globe.
    kit.annulus('15 Pod collar', 'trim', cx, cy,
                ((cz - 0.55, pod_r + 0.30, pod_r - 0.50),
                 (cz + 0.55, pod_r + 0.30, pod_r - 0.50)), 16)
    kit.annulus('16 Pod shadow band', 'dark', cx, cy,
                ((cz + 1.00, pod_r + 0.22, pod_r - 0.70),
                 (cz + 1.90, pod_r + 0.22, pod_r - 0.70)), 16)
    kit.annulus('17 Pod aft collar', 'trim', cx, cy,
                ((cz - 1.90, pod_r + 0.30, pod_r - 0.50),
                 (cz - 1.00, pod_r + 0.30, pod_r - 0.50)), 16)
    kit.annulus('18 Pod accent band', 'accent', cx, cy,
                ((cz + 2.40, pod_r + 0.20, pod_r - 0.80),
                 (cz + 3.10, pod_r + 0.20, pod_r - 0.80)), 16)
    kit.annulus('19 Pod sensor ring', 'cool', cx, cy,
                ((cz + 3.60, pod_r + 0.25, pod_r - 0.90),
                 (cz + 4.20, pod_r + 0.25, pod_r - 0.90)), 12)

    # 20-25  The viewscreen, the dorsal hatch and the engine bank at the pod's stern.
    kit.plate('20 Viewscreen frame', 'dark', (3.4, 2.2, 1.3), (0, cy + 1.5, cz + pod_r * 0.80))
    kit.plate('21 Viewscreen pane', 'lit', (2.4, 1.4, 1.3), (0, cy + 1.5, cz + pod_r * 0.84))
    kit.plate('22 Dorsal hatch', 'trim', (2.6, 1.2, 3.0), (0, cy + pod_r * 0.86, cz - 0.6))
    for side in (-1, 1):
        kit.cylinder(f'23 Engine bell {side}', 'lit', (side * 2.6, cy, cz - pod_r * 0.86 - 2.4),
                     1.9, 5.0, 'Z', 14)
        kit.plate(f'24 Marker light {side}', 'lit', (0.7, 1.4, 0.7),
                  (side * (pod_r + 0.20), cy + 1.2, cz - 1.0))
    kit.plate('25 Ventral pylon plate', 'dark', (18.0, 0.8, spar_t + 0.5), (0, cy - spar_t / 2, cz))

    # 26-29  The pylon's own fittings: bands, lamps, shadows and the bomber's payload.
    for side in (-1, 1):
        kit.plate(f'26 Pylon band {side}', 'trim', (1.2, spar_t + 0.7, spar_t + 0.7),
                  (side * 17.0, cy, cz))
        kit.plate(f'27 Pylon shadow {side}', 'dark', (1.2, spar_t + 0.4, spar_t + 0.4),
                  (side * 24.0, cy, cz))
        kit.plate(f'28 Pylon lamp {side}', 'lit', (1.0, 0.8, 1.0),
                  (side * 22.0, cy + spar_t / 2, cz))
    for k in range(row['ordnance']):
        side = -1 if k == 0 else 1
        kit.cylinder(f'29 Ordnance {k}', 'accent', (side * 8.0, cy - pod_r * 0.45, cz - 2.0),
                     1.7, 11.0, 'Z', 10)
        kit.plate(f'29 Ordnance band {k}', 'trim', (2.2, 2.2, 1.4),
                  (side * 8.0, cy - pod_r * 0.45, cz - 2.0))

    # 40-43  The sensor and radiator fit: a forward mast, wing vanes and a pod radiator pair.
    kit.loft('40 Forward sensor mast', 'cool',
             ((cz + pod_r * 0.55, 1.5, cy + 1.5, cy - 1.5),
              (cz + pod_r * 0.95 + 3.0, 1.1, cy + 1.0, cy - 1.0),
              (cz + pod_r * 0.95 + 6.0, 0.5, cy + 0.5, cy - 0.5)), .2)
    for side in (-1, 1):
        kit.plate(f'41 Pod radiator vane {side}', 'cool', (0.7, 3.4, 7.0),
                  (side * (pod_r * 0.55), cy + pod_r * 0.55, cz - 3.0))
        kit.plate(f'42 Pod keel vane {side}', 'cool', (0.7, 2.6, 5.0),
                  (side * (pod_r * 0.45), cy - pod_r * 0.55, cz + 1.0))
    kit.plate('43 Pod dorsal fin', 'cool', (0.8, 5.0, 6.0), (0, cy + pod_r * 0.72, cz - 2.0))


BUILDERS = {'corvette': build_imperial_corvette,
            'tie_squadron': build_imperial_tie,
            'tie_bomber_squadron': build_imperial_tie}
# The kit's per-part boxes, published by `build()` so `main()` can run the contact check before the
# parts are grouped into role objects and lose their names.
PART_BOXES = {}


# ------------------------------------------------------------------------------------------- build
def build(key):
    """One row's authored parts, plus the role each of its triangles carries."""
    kit = Kit()
    BUILDERS[ROWS[key]['ship_kind']](kit, ROWS[key])
    PART_BOXES.clear()
    PART_BOXES.update(kit.parts)
    return kit.verts, kit.faces, kit.roles


def gap(a, b):
    """How far apart two boxes are; negative as soon as they overlap on every axis."""
    return max(max(a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3))


def contact_report(parts):
    """The parts that stand clear of every other part.

    A kit is authored by centre and by reach and neither implies contact, so a hull can be authored
    as a constellation of panels that all look right on their own. This is the check the review
    harness makes on an exported hull (`floating_parts` in the B1 guard), made here, where the part
    names still exist - the weld pass only ever sees one box per material role.
    """
    floating = []
    for name, box in sorted(parts.items()):
        nearest = min((gap(box, other), other_name) for other_name, other in parts.items()
                      if other_name != name)
        if nearest[0] > 0:
            floating.append((name, round(nearest[0], 3), nearest[1]))
    print(f'CONTACT {len(parts)} parts, floating={len(floating)}')
    for name, clearance, other in floating:
        print(f'  FLOATS {name} ({clearance} clear of the nearest part, {other})')
    return floating


def cleared():
    """An empty scene: the seed is re-run on whichever file Blender happened to start from."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def role_objects(verts, faces, roles):
    """One object per loader role, each carrying its own `engine_material_role`."""
    groups = {}
    for triangle, role in zip(faces, roles):
        groups.setdefault(role, []).append(triangle)
    objects = []
    for role in ROLES:
        triangles = groups.get(role, [])
        mesh = bpy.data.meshes.new(f'{role} hull')
        # The export re-indexes shared vertices, so the authoring mesh is a flat triangle list and
        # each role object stands on its own.
        mesh.from_pydata([verts[i] for triangle in triangles for i in triangle], [],
                         [(3 * n, 3 * n + 1, 3 * n + 2) for n in range(len(triangles))])
        mesh.validate()
        obj = bpy.data.objects.new(f'{role} hull', mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj['engine_material_role'] = role
        obj.select_set(True)
        objects.append(obj)
    bpy.context.view_layer.objects.active = objects[0]
    return objects


def evaluated(label):
    """The scene's evaluated geometry: the same numbers the export wrapper will write."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo, hi = [1e9] * 3, [-1e9] * 3
    extreme = [['', ''] for _ in range(3)]
    per_role = {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        evaluated_obj = obj.evaluated_get(depsgraph)
        mesh = evaluated_obj.to_mesh()
        for vertex in mesh.vertices:
            point = obj.matrix_world @ vertex.co
            for i in range(3):
                if point[i] < lo[i]:
                    lo[i], extreme[i][0] = point[i], obj.name
                if point[i] > hi[i]:
                    hi[i], extreme[i][1] = point[i], obj.name
        mesh.calc_loop_triangles()
        per_role[obj['engine_material_role']] = len(mesh.loop_triangles)
        evaluated_obj.to_mesh_clear()
    return lo, hi, extreme, per_role


def report(label, limits):
    lo, hi, extreme, per_role = evaluated(label)
    total = sum(per_role.values())
    print(f'TRIS {label} {total} ' + ' '.join(f'{role}={per_role.get(role, 0)}'
                                              for role in ROLES))
    print(f'BOUNDS {label} lo={[round(v, 3) for v in lo]} hi={[round(v, 3) for v in hi]}')
    breaches = breach_lines(label, lo, hi, limits, extreme)
    for line in breaches:
        print(line)
    print(f'SELFCHECK {label} breaches={len(breaches)} tolerance={BREACH_TOLERANCE}')
    return total, per_role


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    keys = list(ROWS) if ('--all' in argv or not argv) else [argv[argv.index('--asset') + 1]]
    for key in keys:
        row = ROWS[key]
        identifier, limits = row['identifier'], row['limits']
        master = ROOT / f'art/blender/{identifier}.blend'
        cleared()
        verts, faces, role_of_face = build(key)
        role_objects(verts, faces, role_of_face)
        floating = contact_report(PART_BOXES)
        # The hull is welded before it is declared, so nothing floats: a kit is authored by centre
        # and by reach, and contact is not implied by either. What the pass joined is printed, and
        # the extent self-check runs after it rather than before.
        joints = weld_scene(**WELD)
        print(f'WELD {identifier} joints={len(joints)}')
        report(identifier, limits)
        assert not floating, (f'{identifier} carries parts standing clear of every other part; a '
                              f'panel that touches nothing is drawn as a constellation, not as a '
                              f'hull: {floating}')
        features = dict(authority='script', approval='pending_owner_approval', binding=key,
                        data_id=row['data_id'], original_design=True, design=row['design'],
                        legacy_envelope=[list(a) for a in limits],
                        seed_recipe=SEED_RECIPE, ship_kind=row['ship_kind'],
                        faction=row['faction'], legacy_shape=row['legacy_shape'],
                        station_radius=row['station_radius'], label=row['label'],
                        provenance=PROVENANCE)
        bpy.context.scene['asset'] = identifier
        bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
        bpy.context.scene['authority'] = 'script'
        bpy.context.scene['design'] = row['design']
        bpy.context.scene['binding'] = key
        bpy.context.scene['review'] = 'pending owner approval - not a production binding'
        bpy.context.scene['coordinates'] = 'X beam; Y up; +Z forward'
        bpy.context.scene['runtime'] = 'immutable evaluated triangles; no runtime Blender'
        bpy.context.preferences.filepaths.save_version = 0
        master.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
        print(f'SEED_OK {key} -> {master.name}')


main()
