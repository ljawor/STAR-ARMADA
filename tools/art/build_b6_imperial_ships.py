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
    # ---- rows 4 to 7: the two dagger capitals, the cruiser and the frigate ----
    # The two dagger rows are the same legacy shape (`dagger`) at the same measured extent, so their
    # *shape* tables are row data: the supercapital declares a deeper hull (`hull_sections` bottoms on
    # the keel across four frames and is wider) and one more superstructure tier, which is what keeps
    # the pair from being one mesh scaled. Every reach is a row value: the hull carries the bow (Z max)
    # and the keel (Y min), the outboard hangar sponsons the beam (both X extremes), the dorsal comm
    # mast the ship's highest point (Y max) and the engine bells the stern (Z min).
    'ship:imperial:battleship': dict(
        identifier='imperial_battleship',
        data_id='imperial_battleship',
        label='Executor-class Dreadnought',
        ship_kind='capital',
        faction='imperial',
        legacy_shape='dagger',
        limits=[[-38.45, 38.45], [-10.0, 39.5], [-80.183, 108.0]],
        legacy_triangles=3296,
        legacy_vertices=1814,
        station_radius=150.0,
        hull_sections=((-78, 15.0, 6.0, -6.0), (-58, 21.0, 9.0, -10.0),
                       (-24, 25.0, 10.0, -10.0), (16, 24.0, 10.0, -9.0),
                       (62, 15.0, 8.0, -8.0), (108, 1.3, 3.0, -3.0)),
        hull_bevel=0.9,
        tiers=((((-60, 12.0, 16.0, 9.0), (-28, 13.0, 18.0, 9.0), (-4, 8.0, 12.0, 9.0)), 0.5),),
        tower=(((-34, 6.5, 33.0, 16.0), (-22, 6.5, 33.0, 16.0), (-15, 4.0, 26.0, 16.0)), 0.35),
        mast=(6.0, 1.4, -30.0, 4.5),
        sponson=((-72, 5.0, 5.0, -6.0), (-52, 6.0, 6.0, -6.5), (-30, 7.0, 6.5, -7.0),
                 (-6, 6.0, 6.0, -7.0), (8, 4.0, 4.5, -5.0)),
        sponson_bevel=0.6,
        keel=((-58, 3.2, -5.0, -10.0), (-40, 3.6, -5.0, -10.0), (-18, 2.8, -5.0, -9.0)),
        keel_bevel=0.3,
        skirt=((-79, 8.0, 4.0, -4.0), (-74, 12.0, 6.0, -5.0), (-68, 15.0, 8.0, -6.0)),
        skirt_bevel=0.4,
        prow=(5.0, 3.0, 10.0),
        deck_top=10.0,
        turrets=(-50.0, -8.0, 44.0),
        turret_scale=1.5,
        engines=(-16.0, -5.5, 5.5, 16.0),
        engine_radius=3.4,
        engine_depth=6.0,
        engine_y=-1.0,
        design=('Imperial grey dagger dreadnought: a broad armoured pressure hull with outboard '
                'hangar sponsons carrying the beam, a tiered bridge superstructure under a dorsal '
                'comm mast, triple gun turrets, recessed dark hangar mouths and panels, bright trim '
                'banding, red identification striping, a bank of lit engine bells and cool '
                'radiator fins'),
    ),
    'ship:imperial:supercapital': dict(
        identifier='imperial_supercapital',
        data_id='imperial_supercapital',
        label='Sovereign-class Star Dreadnought',
        ship_kind='capital',
        faction='imperial',
        legacy_shape='dagger',
        limits=[[-38.45, 38.45], [-10.0, 39.5], [-80.183, 108.0]],
        legacy_triangles=3296,
        legacy_vertices=1814,
        station_radius=260.0,
        # Heavier than the battleship: a deeper, wider pressure hull and an extra superstructure tier.
        hull_sections=((-79, 17.0, 8.0, -10.0), (-60, 24.0, 10.0, -10.0),
                       (-26, 28.0, 11.0, -10.0), (12, 28.0, 11.0, -10.0),
                       (58, 18.0, 9.0, -9.0), (108, 1.5, 3.0, -3.0)),
        hull_bevel=1.0,
        tiers=((((-62, 14.0, 20.0, 10.0), (-28, 15.0, 22.0, 10.0), (-2, 9.0, 15.0, 10.0)), 0.5),
               (((-54, 11.0, 30.0, 20.0), (-30, 11.0, 30.0, 20.0), (-16, 7.0, 24.0, 20.0)), 0.45)),
        tower=(((-34, 6.0, 34.0, 28.0), (-22, 6.0, 34.0, 28.0), (-15, 3.5, 27.0, 28.0)), 0.3),
        mast=(6.0, 1.6, -30.0, 5.0),
        sponson=((-74, 5.5, 6.0, -7.0), (-54, 6.5, 7.0, -7.5), (-32, 7.5, 7.5, -8.0),
                 (-6, 6.5, 7.0, -8.0), (10, 4.5, 5.0, -6.0)),
        sponson_bevel=0.6,
        keel=((-58, 3.6, -5.0, -10.0), (-40, 4.0, -5.0, -10.0), (-18, 3.0, -5.0, -10.0)),
        keel_bevel=0.3,
        skirt=((-79, 9.0, 5.0, -5.0), (-74, 13.0, 7.0, -6.0), (-68, 16.0, 9.0, -7.0)),
        skirt_bevel=0.4,
        prow=(5.5, 3.5, 11.0),
        deck_top=11.0,
        turrets=(-52.0, -10.0, 48.0),
        turret_scale=1.7,
        engines=(-18.0, -6.0, 6.0, 18.0),
        engine_radius=3.8,
        engine_depth=6.5,
        engine_y=-1.5,
        design=('Imperial grey star dreadnought: a deep broad armoured hull with outboard hangar '
                'sponsons carrying the beam, a two-tier bridge superstructure under a dorsal comm '
                'mast, three heavy gun turrets, recessed dark hangar mouths and panels, bright trim '
                'banding, red identification striping, a bank of lit engine bells and cool radiator '
                'fins'),
    ),
    'ship:imperial:cruiser': dict(
        identifier='imperial_cruiser',
        data_id='imperial_cruiser',
        label='Gladiator Cruiser',
        ship_kind='capital',
        faction='imperial',
        legacy_shape='cruiser',
        limits=[[-29.45, 29.45], [-7.0, 31.5], [-62.94, 78.0]],
        legacy_triangles=2800,
        legacy_vertices=1542,
        station_radius=90.0,
        hull_sections=((-61, 12.0, 5.0, -5.0), (-46, 15.0, 6.0, -7.0), (-20, 17.0, 7.0, -7.0),
                       (6, 16.0, 7.0, -6.0), (78, 1.2, 2.5, -2.5)),
        hull_bevel=0.75,
        tiers=((((-50, 9.0, 13.0, 7.0), (-22, 10.0, 14.0, 7.0), (-4, 6.0, 10.0, 7.0)), 0.45),),
        tower=(((-28, 5.0, 27.0, 12.0), (-18, 5.0, 27.0, 12.0), (-12, 3.0, 22.0, 12.0)), 0.3),
        mast=(5.0, 1.3, -24.0, 3.5),
        sponson=((-58, 4.0, 4.0, -5.0), (-44, 4.6, 5.0, -5.5), (-26, 5.5, 5.5, -6.0),
                 (-6, 4.8, 5.0, -6.0), (6, 3.4, 3.6, -4.5)),
        sponson_bevel=0.5,
        keel=((-44, 2.6, -4.0, -7.0), (-30, 3.0, -4.0, -7.0), (-14, 2.2, -4.0, -6.5)),
        keel_bevel=0.25,
        skirt=((-61, 6.5, 3.5, -3.5), (-57, 9.5, 5.0, -4.5), (-52, 12.0, 6.5, -5.5)),
        skirt_bevel=0.35,
        prow=(4.0, 2.6, 8.0),
        deck_top=7.0,
        turrets=(-36.0, 0.0, 38.0),
        turret_scale=1.1,
        engines=(-11.0, 0.0, 11.0),
        engine_radius=2.8,
        engine_depth=5.0,
        engine_y=-0.5,
        design=('Imperial grey cruiser: an armoured hull with outboard hangar sponsons carrying the '
                'beam, a two-tier bridge superstructure under a dorsal comm mast, three gun turrets, '
                'recessed dark hangar mouths and panels, bright trim banding, red identification '
                'striping, a bank of lit engine bells and cool radiator fins'),
    ),
    'ship:imperial:frigate': dict(
        identifier='imperial_frigate',
        data_id='imperial_frigate',
        label='Lancer Frigate',
        ship_kind='frigate',
        faction='imperial',
        legacy_shape='needle',
        limits=[[-16.0, 16.0], [-5.0, 24.0], [-43.601, 48.0]],
        legacy_triangles=1552,
        legacy_vertices=858,
        station_radius=55.0,
        # The corvette's legacy shape and box, but its own heavier hull: a fuller pressure hull and a
        # deeper sponson pair than the corvette's, a raised battery deck, six gun turrets rather than
        # the corvette's two and a four-bell engine bank.
        hull_sections=((-41, 8.0, 6.0, -4.6), (-34, 10.4, 7.0, -5.0), (-12, 12.2, 7.6, -4.8),
                       (0, 11.4, 7.4, -4.6), (14, 9.4, 7.0, -4.2), (48, 1.2, 2.2, -1.3)),
        hull_bevel=0.5,
        house=(((-36, 6.0, 13.0, 6.6), (-20, 7.0, 14.4, 6.6), (-4, 4.0, 10.0, 6.6)), 0.4),
        sponson=((-30, 4.0, 4.4, -4.4), (-24, 5.4, 5.0, -5.0), (8, 3.0, 3.4, -3.6)),
        sponson_bevel=0.4,
        keel=((-28, 2.4, -3.0, -5.0), (-20, 2.6, -3.2, -5.0), (-8, 2.0, -3.0, -4.6)),
        keel_bevel=0.25,
        skirt=((-42.5, 6.5, 3.4, -3.2), (-39, 8.4, 4.4, -4.0), (-34, 9.6, 5.2, -4.4)),
        skirt_bevel=0.3,
        prow=(4.6, 2.4, 9.0),
        deck_top=7.0,
        turrets=(-30.0, -16.0, -2.0, 22.0, 34.0),
        turret_scale=0.8,
        engines=(-7.0, -2.5, 2.5, 7.0),
        engine_radius=2.2,
        engine_depth=5.601,
        engine_y=-0.5,
        fin=(6.5, 0.5, -20.0, 10.0),
        design=('Imperial grey needle frigate: a fuller pressure hull with a raised battery deck '
                'and outboard hangar sponsons carrying the beam, six gun turrets, recessed dark '
                'hangar mouths and panels, bright trim banding, red identification striping, a '
                'four-bell lit engine bank and a tall cool dorsal radiator fin'),
    ),
    # ---- the last row of the batch: the convoy, the cluster the owner settled follows the siblings
    # `imperial:convoy` is the one Imperial binding whose hull could not be reached at all: both
    # convoy branches of the ship path gated on `FACTIONS[1:]`, so the one faction that needed the
    # branch was the one it excluded (finding in `art/manifests/pipeline_policy.json`,
    # `s06-imperial-convoy-parity-2026-10-18`, and the seam that now admits it is guarded by
    # `tests/test_imperial_convoy_gate.py`). The owner settled at the same time that the row
    # *follows the other three factions* rather than being authored as a hull of its own: a cluster
    # at roughly twice a single-hull row's triangles, in the binding's own legacy box.
    #
    # The envelope is measured, not chosen: the binding draws the legacy `box` today
    # (`ship_mesh('box')` = -20.000,-7.000,-24.697 .. 20.000,26.500,24.358 at 1,536 triangles), and
    # `render/ship_sizes.ship_size` derives the class scale from the drawn shape's *Z span*, so the
    # authored mesh fills that box's Z extent and is authored a little inside it in X and Y, which
    # is exactly the convention the three sibling sidecars carry: `rebel:convoy` declares
    # [-31,-9,-72.698]..[31,16,59.5] around mesh bounds of [-30.3,-6,-72.698]..[30.3,14.776,59.5] -
    # larger on X and Y, the same in Z.
    'ship:imperial:convoy': dict(
        identifier='imperial_convoy',
        data_id='imperial_crew_transport',
        label='Imperial Convoy Barge',
        ship_kind='convoy',
        faction='imperial',
        legacy_shape='box',
        limits=[[-20.0, 20.0], [-7.0, 26.5], [-24.6975, 24.35825]],
        legacy_triangles=1536,
        legacy_vertices=840,
        station_radius=32.0,
        # The cluster's own counts, as row data: the two freight rows, each as
        # `(host, outboard centre, radius, count)` - the drums are spread across the deck their own
        # host carries, so a row of freight never overhangs the hull it is lashed to - and the
        # four-bell engine bank, whose mouths are the stern. The Imperial reading of the siblings'
        # clusters is authored from this rather than from a second copy of the kit.
        drum_length=10.6,
        drum_rows=(('spine', 4.8, 3.0, 4), ('module', 13.0, 3.0, 3)),
        engines=(-8.6, -2.9, 2.9, 8.6),
        engine_radius=2.8,
        engine_depth=5.0,
        design=('Imperial grey convoy barge: a broad armoured freight spine with outboard cargo '
                'hulls carrying the beam, two rows of armoured freight drums per side clamped under '
                'dark cargo gantries, a tiered bridge superstructure under a dorsal comm mast, a '
                'forward sensor prow, recessed dark hangar mouths and panels, bright trim banding, '
                'red identification striping, a four-bell lit engine bank and a cool radiator fit'),
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


def hull_at(sections, z):
    """The loft's own frame at `z`: `(half-width, top, bottom)`, linearly interpolated.

    A detail placed from a hand-copied height floats off a tapered deck or sinks into a flank; this
    reads the same section list the loft is built from, so a flank panel lands on the hull the row
    actually authors. A pure function of the sections, so a guard can drive it without Blender.
    """
    if z <= sections[0][0]:
        return sections[0][1], sections[0][2], sections[0][3]
    for (z0, w0, t0, b0), (z1, w1, t1, b1) in zip(sections, sections[1:]):
        if z <= z1:
            f = (z - z0) / (z1 - z0)
            return (w0 + f * (w1 - w0), t0 + f * (t1 - t0), b0 + f * (b1 - b0))
    return sections[-1][1], sections[-1][2], sections[-1][3]


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


def build_imperial_capital(kit, row):
    """The dagger/cruiser capital hull: grey plating, recessed dark panels, bright trim banding, red
    identification striping, a lit engine bank and a cool sensor/radiator fit.

    Every reach is stated against the row's own extent: the pressure hull is the bow (Z max) and the
    keel (Y min), the outboard hangar sponsons are the beam (both X extremes), the dorsal comm mast
    is the ship's highest point (Y max) and the engine bells are the stern (Z min). The hull, the
    tiers, the tower and the sponsons are row data, which is what makes the supercapital a deeper
    hull with an extra tier rather than the battleship scaled. Detail is placed from the loft it
    sits on (`hull_at`), never from a hand-copied height, so it lands on a tapered deck or flank.
    """
    lo, hi, centre, span = frame(row['limits'])
    deck = row['deck_top']
    scale = row['turret_scale']
    hull = row['hull_sections']
    sp_z0 = min(s[0] for s in row['sponson'])
    sp_z1 = max(s[0] for s in row['sponson'])
    sp_mid = (sp_z0 + sp_z1) / 2.0
    sp_len = sp_z1 - sp_z0
    sw = max(s[1] for s in row['sponson'])
    spon_x = hi[0] - sw                       # the sponson's outer plane IS the beam extreme
    mid_w, mid_t = hull_at(hull, sp_mid)[0], hull_at(hull, sp_mid)[1]

    # 01-05  The hull and the block above it: the hull is the bow and the keel, the sponsons the
    # beam, the tiers and the tower the superstructure.
    kit.loft('01 Pressure hull', 'base', hull, row['hull_bevel'])
    for i, (sections, bevel) in enumerate(row['tiers']):
        kit.loft(f'02 Superstructure tier {i}', 'base', sections, bevel)
    kit.loft('03 Bridge tower', 'base', row['tower'][0], row['tower'][1])
    for side in (-1, 1):
        kit.loft(f'04 Hangar sponson {side}', 'base', row['sponson'], row['sponson_bevel'],
                 (side * spon_x, 0, 0))
    kit.loft('05 Ventral keel fin', 'base', row['keel'], row['keel_bevel'])
    kit.loft('06 Aft hull skirt', 'base', row['skirt'], row['skirt_bevel'])
    pw, ph, pl = row['prow']
    kit.plate('07 Bow prow plate', 'base', (pw, ph, pl), (0, lo[1] + ph * 0.5, hi[2] - pl / 2))

    # Recessed dark panels: the hangar mouths on the broadside, panels in the shadow of the plating.
    kit.plate('10 Ventral recess panel', 'dark', (sw * 2.0, 1.0, sp_len * 0.55),
              (0, lo[1] + 0.5, sp_mid - 6.0))
    kit.plate('11 Engine housing recess', 'dark', (sw * 2.4, 4.4, 6.0), (0, 0.6, lo[2] + 4.5))
    pz = hi[2] - 14.0
    kit.plate('12 Prow sensor housing', 'dark', (4.6, 2.6, 7.0),
              (0, hull_at(hull, pz)[1] - 0.3, pz))
    kit.plate('13 Dorsal cable run', 'dark', (2.6, 0.9, sp_len * 0.5), (0, deck + 0.4, sp_mid + 8.0))
    for side in (-1, 1):
        kit.plate(f'14 Hangar mouth {side}', 'dark', (1.2, 6.0, sp_len * 0.55),
                  (side * (hi[0] - 0.6), -0.5, sp_mid - 2.0))
        az = max(sp_z0 - 10.0, hull[0][0] + 7.0)   # the recess stays inside the hull's own stern
        kit.plate(f'15 Aft flank recess {side}', 'dark', (1.4, 4.0, 12.0),
                  (side * hull_at(hull, az)[0], 0.0, az))

    # Bright trim: the sheer banding, the gun battery, the bow collar and the comm mast (Y max).
    for side in (-1, 1):
        kit.plate(f'20 Sheer edge band {side}', 'trim', (1.4, 1.2, sp_len * 0.85),
                  (side * mid_w, mid_t - 0.8, sp_mid))
    for k, z in enumerate(row['turrets']):
        top = hull_at(hull, z)[1]
        kit.cylinder(f'22 Turret body {k}', 'trim', (0, top + 0.2 * scale, z), 1.2 * scale,
                     2.6 * scale, 'Y', 12)
        kit.plate(f'23 Turret barbette {k}', 'trim', (4.6 * scale, 1.6, 5.0 * scale),
                  (0, top - 0.1, z))
        kit.plate(f'24 Turret barrels {k}', 'trim', (2.6 * scale, 0.9 * scale, 9.0 * scale),
                  (0, top + 0.2 * scale, z + 4.5 * scale))
    kit.plate('26 Bow collar', 'trim', (pw * 1.1, 1.4, 3.0),
              (0, hull_at(hull, hi[2] - 16.0)[1], hi[2] - 16.0))
    mh, mw, mz, mz1 = row['mast']
    kit.plate('28 Dorsal comm mast', 'trim', (mw * 2.0, mh * 2.0, mz1 * 2.0),
              (0, hi[1] - mh, mz))

    # Red identification striping, raised so the review cameras read it.
    for side in (-1, 1):
        fz = sp_z1 + 20.0
        kit.plate(f'30 Flank stripe {side}', 'accent', (1.0, 2.6, 16.0),
                  (side * hull_at(hull, fz)[0], 3.0, fz))
        kit.plate(f'32 Sponson stripe {side}', 'accent', (1.0, 2.0, 6.0),
                  (side * (hi[0] - 0.5), -2.0, sp_mid + 6.0))
    cz = hi[2] - 22.0
    kit.plate('34 Prow chevron', 'accent', (2.4, 2.0, 7.0), (0, hull_at(hull, cz)[1] - 0.5, cz))

    # The drive and the ship's lighting.
    e_r, e_d, e_y = row['engine_radius'], row['engine_depth'], row['engine_y']
    for k, x in enumerate(row['engines']):
        kit.cylinder(f'40 Engine bell {k}', 'lit', (x, e_y, lo[2] + e_d / 2.0), e_r, e_d, 'Z', 14)
    kit.plate('41 Stern lamp band', 'lit', (sw * 1.8, 1.0, 1.2), (0, 1.0, lo[2] + 1.5))
    kit.plate('43 Bridge visor slit', 'lit', (3.0, 0.8, 5.0), (0, hi[1] - 9.0, sp_mid + 6.0))
    for side in (-1, 1):
        kit.plate(f'45 Hangar glow {side}', 'lit', (1.0, 4.6, sp_len * 0.5),
                  (side * (hi[0] - 0.5), -0.5, sp_mid + 2.0))

    # Cool sensor and radiator fit; the dorsal fin reaches the ship's highest point.
    kit.plate('50 Dorsal radiator fin', 'cool', (1.2, 12.0, 18.0), (0, hi[1] - 12.0, sp_mid - 4.0))
    for side in (-1, 1):
        sz = sp_mid - 14.0
        kit.plate(f'51 Side radiator fin {side}', 'cool', (1.0, 5.0, 11.0),
                  (side * (hull_at(hull, sz)[0] * 0.6), hull_at(hull, sz)[1], sz))
        pvz = hi[2] - 8.0
        kit.plate(f'52 Prow sensor vane {side}', 'cool', (0.9, 3.6, 8.0),
                  (side * max(hull_at(hull, pvz)[0] * 0.6, 0.9), hull_at(hull, pvz)[1], pvz))
    kit.plate('54 Ventral radiator plate', 'cool', (sw * 1.4, 1.0, 12.0),
              (0, lo[1] + 1.3, sp_mid + 8.0))
    for side in (-1, 1):
        sz = sp_mid + 34.0
        kit.cylinder(f'55 Sensor array {side}', 'cool', (side * 4.4, hull_at(hull, sz)[1], sz),
                     1.2, 3.6, 'Z', 10)


def build_imperial_frigate(kit, row):
    """The Lancer frigate: a heavier needle hull than the corvette, and more heavily armed.

    It shares the legacy `needle` box with the corvette - both draw the same legacy mesh today - but
    is its own hull: a fuller pressure hull with a raised battery deck, deeper outboard sponsons and
    five gun turrets against the corvette's two, on a four-bell engine bank. The envelope carriers
    are stated against the row's own extent: the hull is the bow (Z max) and the keel (Y min), the
    sponsons the beam (both X extremes), the dorsal radiator fin the ship's highest point (Y max)
    and the engine bells the stern (Z min).
    """
    lo, hi, centre, span = frame(row['limits'])
    hull = row['hull_sections']
    scale = row['turret_scale']
    sp_z0 = min(s[0] for s in row['sponson'])
    sp_z1 = max(s[0] for s in row['sponson'])
    sp_mid = (sp_z0 + sp_z1) / 2.0
    sp_len = sp_z1 - sp_z0
    sw = max(s[1] for s in row['sponson'])
    spon_x = hi[0] - sw

    kit.loft('01 Pressure hull', 'base', hull, row['hull_bevel'])
    kit.loft('02 Dorsal battery deck', 'base', row['house'][0], row['house'][1])
    kit.loft('03 Aft hull skirt', 'base', row['skirt'], row['skirt_bevel'])
    for side in (-1, 1):
        kit.loft(f'04 Hangar sponson {side}', 'base', row['sponson'], row['sponson_bevel'],
                 (side * spon_x, 0, 0))
    kit.loft('05 Ventral keel fin', 'base', row['keel'], row['keel_bevel'])
    pw, ph, pl = row['prow']
    kit.plate('06 Bow prow plate', 'base', (pw, ph, pl), (0, lo[1] + ph * 0.5, hi[2] - pl / 2))
    kit.plate('07 Forward deck housing', 'base', (5.0, 2.4, 9.0), (0, hull_at(hull, 26.0)[1], 26.0))

    # Recessed dark panels.
    kit.plate('10 Ventral recess panel', 'dark', (sw * 2.0, 1.0, 20.0), (0, lo[1] + 0.5, -18.0))
    kit.plate('11 Engine housing recess', 'dark', (sw * 2.2, 4.0, 5.0), (0, 0.4, lo[2] + 4.0))
    pz = hi[2] - 14.0
    kit.plate('12 Prow sensor housing', 'dark', (3.4, 2.2, 5.0),
              (0, hull_at(hull, pz)[1] - 0.3, pz))
    kit.plate('13 Dorsal cable run', 'dark', (2.4, 0.8, 16.0), (0, hull_at(hull, 6.0)[1], 6.0))
    for side in (-1, 1):
        kit.plate(f'14 Hangar mouth {side}', 'dark', (1.2, 5.0, sp_len * 0.5),
                  (side * (hi[0] - 0.6), -0.8, sp_mid - 2.0))
        az = max(sp_z0 - 8.0, hull[0][0] + 5.0)
        kit.plate(f'15 Aft flank recess {side}', 'dark', (1.2, 3.2, 9.0),
                  (side * hull_at(hull, az)[0], 0.0, az))

    # Bright trim: sheer banding, the five-gun battery and the collars.
    for side in (-1, 1):
        kit.plate(f'20 Sheer edge band {side}', 'trim', (1.2, 1.0, sp_len * 0.8),
                  (side * hull_at(hull, sp_mid)[0], hull_at(hull, sp_mid)[1] - 0.8, sp_mid))
    for k, z in enumerate(row['turrets']):
        top = hull_at(hull, z)[1]
        kit.cylinder(f'22 Turret body {k}', 'trim', (0, top + 0.2 * scale, z), 1.2 * scale,
                     2.6 * scale, 'Y', 12)
        kit.plate(f'23 Turret barbette {k}', 'trim', (4.0 * scale, 1.4, 4.4 * scale),
                  (0, top - 0.1, z))
        kit.plate(f'24 Turret barrels {k}', 'trim', (2.4 * scale, 0.8 * scale, 8.0 * scale),
                  (0, top + 0.2 * scale, z + 4.0 * scale))
    kit.plate('25 Dorsal spine collar', 'trim', (4.4, 1.4, 2.6), (0, hull_at(hull, -2.0)[1], -2.0))
    kit.plate('26 Bow collar', 'trim', (pw * 1.1, 1.2, 2.6),
              (0, hull_at(hull, hi[2] - 14.0)[1], hi[2] - 14.0))
    kit.plate('27 Stern transom band', 'trim', (sw * 2.0, 1.4, 1.8), (0, 2.4, lo[2] + 2.0))

    # Red identification striping.
    for side in (-1, 1):
        kit.plate(f'30 Flank stripe {side}', 'accent', (1.0, 2.2, 12.0),
                  (side * hull_at(hull, 24.0)[0], 2.6, 24.0))
        kit.plate(f'32 Sponson stripe {side}', 'accent', (1.0, 1.6, 5.0),
                  (side * (hi[0] - 0.5), -1.6, sp_mid + 4.0))
    kit.plate('34 Prow chevron', 'accent', (2.2, 1.8, 6.0),
              (0, hull_at(hull, 38.0)[1] - 0.6, 38.0))

    # The drive and the ship's lighting.
    e_r, e_d, e_y = row['engine_radius'], row['engine_depth'], row['engine_y']
    for k, x in enumerate(row['engines']):
        kit.cylinder(f'40 Engine bell {k}', 'lit', (x, e_y, lo[2] + e_d / 2.0), e_r, e_d, 'Z', 14)
    kit.plate('41 Stern lamp band', 'lit', (sw * 1.6, 0.9, 1.1), (0, 0.8, lo[2] + 1.4))
    for side in (-1, 1):
        kit.plate(f'45 Hangar glow {side}', 'lit', (0.9, 4.0, sp_len * 0.45),
                  (side * (hi[0] - 0.5), -0.8, sp_mid + 2.0))

    # Cool sensor and radiator fit; the dorsal fin reaches the ship's highest point (Y max).
    fh, fw, fz2, fz3 = row['fin']
    kit.plate('50 Dorsal radiator fin', 'cool', (fw * 2.0, fh * 2.0, fz3 * 2.0),
              (0, hi[1] - fh, fz2))
    for side in (-1, 1):
        kit.plate(f'51 Side radiator vane {side}', 'cool', (0.9, 4.2, 9.0),
                  (side * (hull_at(hull, -20.0)[0] * 0.7), hull_at(hull, -20.0)[1], -20.0))
        kit.plate(f'52 Prow sensor vane {side}', 'cool', (0.8, 3.2, 7.0),
                  (side * 2.6, hull_at(hull, 30.0)[1], 30.0))
        kit.plate(f'53 Ventral radiator vane {side}', 'cool', (0.9, 2.4, 6.0),
                  (side * (sw * 1.4), lo[1] + 1.6, sp_mid))
    kit.plate('54 Ventral radiator plate', 'cool', (sw * 1.2, 0.9, 10.0), (0, lo[1] + 1.2, 6.0))


# --------------------------------------------------------------- the convoy cluster, as pure data
# The cluster's own reaches are a pure function of the row's measured extent, so a guard can drive
# them without Blender (`tests/test_alliance_blender_b6_imperial_ships.py`) and a second convoy row
# is a row rather than a second kit - the same shape the corvette and frigate rows carry.
#
# The convention is the three siblings': the authored mesh fills the declared box in Z *exactly* and
# stands inside it on the other two axes, by a stated clearance, because Z is the axis
# `render/ship_sizes.ship_size` derives the class scale from. `rebel:convoy` declares
# [-31,-9,-72.698]..[31,16,59.5] around mesh bounds of [-30.3,-6,-72.698]..[30.3,14.776,59.5]:
# 0.7 larger on X, 2.0 and 1.224 on Y, identical on Z. So this row reaches its bow and its stern
# exactly and stands `CONVOY_CLEARANCE` inside the declared beam, keel and mast.
CONVOY_CLEARANCE = dict(beam=0.5, keel=0.2, mast=0.7, module=0.7)
# The outboard cargo hulls' centreline, inside the declared beam by `CONVOY_CLEARANCE['module']`:
# their outer faces carry the beam, and the raised stripes on them are the mesh's own X extreme.
CONVOY_MODULE_X = 13.4
# The convoy's own transverse frames, as `(z, half-width, top, bottom)` - the same shape
# `alliance_common.loft` takes - so a detail is placed on the deck the row actually authors
# (`hull_at`) rather than on a hand-copied height: the freight spine that carries the whole cluster,
# and the outboard cargo hull. Every Z is stated inside the declared box.
CONVOY_SPINE = ((-20.6, 5.4, 5.6, -4.8), (-13.0, 7.0, 7.0, -5.8), (-1.0, 8.0, 7.8, -6.2),
                (10.0, 7.4, 7.4, -5.8), (19.0, 5.4, 5.8, -4.6), (22.4, 2.6, 3.4, -2.8))
CONVOY_MODULE = ((-16.6, 4.6, 5.6, -4.2), (-9.0, 5.9, 6.8, -5.0), (5.0, 5.9, 6.8, -5.0),
                 (15.4, 4.6, 5.6, -4.2))


def convoy_anchors(row) -> dict:
    """The convoy's own reach numbers, divided out of the binding's own legacy box.

    `bow`, `stern`, `beam`, `keel` and `mast` are the numbers the row's envelope is stated in, and
    every one of them is derived from the box rather than transcribed; the freight drums are placed
    on the deck the spine's own sections carry at their own Z, so a tapered deck does not leave a
    drum standing off it. A pure function of `row`, so the guard drives the same numbers.
    """
    lo, hi, centre, span = frame(row['limits'])
    half = row['drum_length'] / 2.0
    drums, gantry = [], []
    for host, x, radius, count in row['drum_rows']:
        sections = CONVOY_SPINE if host == 'spine' else CONVOY_MODULE
        # The drums are spread across the deck their own host carries, a stated margin in from each
        # end, so a row of freight sits on the hull rather than overhanging it.
        z0 = sections[0][0] + half + .8
        z1 = sections[-1][0] - half - .8
        pitch = (z1 - z0) / (count - 1) if count > 1 else 0.0
        for k in range(count):
            z = z0 + k * pitch
            y = hull_at(sections, z)[1] + radius * .5
            drums.extend(((side * x), y, z, radius) for side in (-1, 1))
            if host == 'spine':
                gantry.append((y, z, radius, x))
    return dict(lo=tuple(lo), hi=tuple(hi), centre=tuple(centre), span=tuple(span),
                bow=hi[2], stern=lo[2],
                beam=hi[0] - CONVOY_CLEARANCE['beam'],
                keel=lo[1] + CONVOY_CLEARANCE['keel'],
                mast=hi[1] - CONVOY_CLEARANCE['mast'],
                module=hi[0] - CONVOY_CLEARANCE['module'],
                module_x=CONVOY_MODULE_X, spine=CONVOY_SPINE, hull=CONVOY_MODULE,
                drums=tuple(sorted(drums)), gantry=tuple(gantry))


def build_imperial_convoy(kit, row):
    """The last row of the batch: the Imperial convoy, authored in the three siblings' convention.

    A cluster rather than a single hull, which is what the siblings are and what the owner settled
    this row follows: a broad armoured freight spine carrying two rows of armoured freight drums per
    side over outboard cargo hulls, under a tiered bridge block with a dorsal comm mast, over a
    four-bell stern engine bank - in the Imperial fleet's language, so Imperial grey plating, dark
    recessed panels and cargo gantries, bright trim banding, red identification striping, lit drives
    and a cool radiator fit.

    Every reach is stated against the row's own extent: the bridge pod's forward cap is the bow
    (Z max, and the axis the class scale is derived from), the engine bells' mouths the stern
    (Z min), the striped outboard cargo hulls the beam (both X extremes), the keel girders the
    Y minimum and the comm mast the ship's highest point (Y max) - each a stated `CONVOY_CLEARANCE`
    inside the declared box, exactly as the siblings are.
    """
    a = convoy_anchors(row)
    bow, stern = a['bow'], a['stern']
    mast, keel = a['mast'], a['keel']
    mx = a['module_x']
    mw = a['module'] - mx
    drums = a['drums']

    # ---- the hull, in Imperial grey: the freight spine, the forward bridge block it carries, the
    # outboard cargo hulls that carry the beam, and the stern engine housing.
    kit.loft('01 Armoured freight spine', 'base', a['spine'], .34)
    kit.loft('02 Forward bridge pod', 'base',
             ((19.4, 3.6, 11.2, 4.2), (21.8, 4.8, 14.4, 4.2), (bow, 2.4, 10.4, 3.8)), .26)
    kit.loft('03 Bridge command tier', 'base',
             ((20.2, 3.0, 17.4, 13.8), (22.0, 3.8, 19.6, 14.0), (bow - .5, 2.0, 15.8, 13.6)), .22)
    kit.loft('04 Bridge tower', 'base',
             ((20.6, 2.6, 22.2, 19.2), (22.2, 3.2, 23.4, 19.4), (23.2, 1.8, 20.8, 19.2)), .2)
    # The comm mast's tip is the ship's highest point (Y max), inside the declared mast clearance.
    kit.loft('05 Dorsal comm mast', 'base',
             ((21.4, .9, 25.0, 23.2), (22.6, 1.1, mast, 23.2), (23.6, .7, 24.2, 23.0)), .16)
    for side in (-1, 1):
        # w = the module's own half-width at its deepest frame, so its outer face is the beam.
        kit.loft(f'06 Outboard freight hull {side}', 'base', a['hull'], .28, (side * mx, 0, 0))
    kit.loft('07 Stern engine housing', 'base',
             ((-20.6, 9.4, 6.4, -4.6), (-17.6, 10.2, 7.0, -5.0), (-14.4, 8.8, 6.2, -4.4)), .28)
    kit.plate('08 Forward deck block', 'base', (7.0, 3.6, 9.0), (0, 7.8, 16.0))
    for side in (-1, 1):
        # The keel girders' undersides are the ship's lowest point (Y min).
        kit.plate(f'09 Ventral keel girder {side}', 'base', (1.4, 1.2, 38.0),
                  (side * 4.4, keel + .6, -1.0))
        kit.plate(f'10 Deck cargo rail {side}', 'base', (1.6, 1.0, 30.0), (side * 16.4, 6.8, 1.0))
        kit.loft(f'11 Ventral cargo pod {side}', 'base',
                 ((-9.0, 4.0, -4.6, -6.2), (2.0, 4.6, -4.8, -6.6), (12.0, 4.0, -4.6, -6.2)),
                 .24, (side * mx, 0, 0))
        kit.loft(f'12 Aft cargo platform {side}', 'base',
                 ((15.0, 4.4, 8.6, 4.4), (19.0, 5.0, 9.2, 4.8), (22.0, 3.4, 7.4, 3.6)),
                 .22, (side * mx, 0, 0))
    # The freight itself: two rows of armoured drums per side, each seated on the deck the spine
    # (or the outboard cargo hull) authors at its own Z.
    for k, (x, y, z, radius) in enumerate(a['drums']):
        kit.cylinder(f'13 Freight drum {k}', 'base', (x, y, z), radius, row['drum_length'], 'Z', 14)

    # ---- recessed dark panels, and the cargo gantries clamped over the drums.
    kit.plate('20 Ventral recess panel', 'dark', (7.4, 1.2, 24.0), (0, keel + 1.2, -2.0))
    kit.plate('21 Engine housing recess', 'dark', (11.2, 4.0, 5.0), (0, .6, stern + 4.0))
    kit.plate('22 Prow sensor housing', 'dark', (3.4, 2.2, 5.0), (0, 12.4, 20.0))
    kit.plate('23 Dorsal cable run', 'dark', (2.4, .8, 16.0), (0, 7.6, 4.0))
    for side in (-1, 1):
        # The hangar mouth is recessed into the cargo hull's flank, a stated clearance inside the
        # beam rather than on it, because the raised stripe is what carries the beam.
        kit.plate(f'24 Hangar mouth {side}', 'dark', (1.2, 4.0, 12.0), (side * (a['beam'] - .7), -1.4, 1.0))
        kit.plate(f'25 Aft flank recess {side}', 'dark', (1.2, 3.2, 9.0), (side * 6.4, .0, -17.0))
        kit.plate(f'26 Cargo hatch {side}', 'dark', (3.6, 1.0, 5.0), (side * 2.6, 7.6, -8.0))
    # The gantries are clamped over the spine's own drums, from the drums' own seats, so a gantry
    # is never a beam hung over a deck it misses.
    for k, (y, z, radius, x) in enumerate(a['gantry']):
        kit.plate(f'27 Cargo gantry {k}', 'dark', (2 * (x + radius) + 3.0, 1.0, 1.6),
                  (0, y + radius - .3, z))

    # ---- bright trim banding: the sheer bands, the collars, the drum straps and the drum hoops.
    for side in (-1, 1):
        kit.plate(f'30 Sheer edge band {side}', 'trim', (1.2, 1.0, 30.0), (side * 7.4, 7.2, -2.0))
        kit.plate(f'31 Cargo rail collar {side}', 'trim', (1.0, 1.4, 3.0), (side * 16.4, 7.2, -10.0))
    for k, (y, z, radius, x) in enumerate(a['gantry'][::2]):
        kit.plate(f'32 Drum hoop {k}', 'trim', (2 * (x + radius) + 4.0, 1.0, 1.4),
                  (0, y + radius - .1, z))
    for k, (x, y, z, radius) in enumerate(a['drums']):
        kit.plate(f'33 Drum strap {k}', 'trim', (radius * 2.3, 1.2, 1.6), (x, y + radius - .4, z))
    kit.plate('34 Mast cap', 'trim', (1.6, 1.2, 1.6), (0, mast - .7, 22.6))
    kit.plate('35 Stern transom band', 'trim', (15.0, 1.4, 1.8), (0, 2.0, stern + 3.4))
    kit.plate('36 Bow collar', 'trim', (6.0, 1.2, 2.6), (0, 15.4, 21.4))

    # ---- identification striping: raised bands the ablation guard can see from any camera. The
    # outboard stripes are the mesh's own X extreme, a stated clearance inside the declared beam.
    for side in (-1, 1):
        kit.plate(f'40 Flank stripe {side}', 'accent', (1.0, 2.2, 12.0), (side * 7.2, 2.6, 8.0))
        kit.plate(f'41 Outboard stripe {side}', 'accent', (.8, 2.0, 12.0),
                  (side * (a['beam'] - .4), .4, 1.0))
        kit.plate(f'42 Keel stripe {side}', 'accent', (.8, 1.0, 6.0), (side * 4.4, keel + 1.0, -14.0))
        kit.plate(f'43 Sponson stripe {side}', 'accent', (7.0, 1.4, 3.0), (side * mx, 6.4, -12.0))
        kit.plate(f'44 Aft flank stripe {side}', 'accent', (1.0, 1.6, 8.0), (side * 8.0, 1.0, -16.0))
    kit.plate('45 Prow chevron', 'accent', (2.2, 1.8, 1.6), (0, 7.2, bow - 1.4))

    # ---- the drive, and the ship's lighting. The bells' mouths are the stern (Z min).
    for k, x in enumerate(row['engines']):
        kit.cylinder(f'50 Engine bell {k}', 'lit', (x, -1.2, stern + row['engine_depth'] / 2.0),
                     row['engine_radius'], row['engine_depth'], 'Z', 14)
    kit.plate('51 Stern lamp band', 'lit', (15.0, 1.4, 1.1), (0, 2.2, stern + 2.0))
    for side in (-1, 1):
        kit.plate(f'52 Marker light {side}', 'lit', (.7, 1.6, .7), (side * 3.4, 22.0, 21.8))
        kit.plate(f'53 Hangar glow {side}', 'lit', (1.0, 3.4, 10.0), (side * (a['beam'] - .6), -1.4, 1.0))
        kit.plate(f'54 Deck luminaire {side}', 'lit', (3.0, 1.0, 3.0), (side * 9.0, 11.4, -16.0))
    kit.plate('55 Bridge visor slit', 'lit', (2.6, .6, 1.6), (0, 16.4, 23.4))

    # ---- cool sensor and radiator fit. The dorsal fin stands on the spine's deck and its tip is
    # just under the mast, which is the ship's highest point.
    kit.plate('60 Dorsal radiator fin', 'cool', (.9, 18.8, 14.0), (0, 15.4, -14.0))
    for side in (-1, 1):
        kit.plate(f'61 Side radiator vane {side}', 'cool', (.9, 3.4, 7.0), (side * 7.0, 8.4, -17.0))
        kit.plate(f'62 Prow sensor vane {side}', 'cool', (.8, 3.2, 7.0), (side * 2.6, 12.0, 20.0))
        kit.plate(f'63 Aft radiator vane {side}', 'cool', (.9, 2.6, 6.0), (side * 10.4, 5.0, -18.0))
        kit.plate(f'64 Mast sensor array {side}', 'cool', (.7, 2.0, 3.0), (side * 1.8, 24.0, 22.6))
    kit.plate('65 Ventral radiator plate', 'cool', (5.0, .9, 10.0), (0, keel + 1.4, 6.0))


BUILDERS = {'corvette': build_imperial_corvette,
            'tie_squadron': build_imperial_tie,
            'tie_bomber_squadron': build_imperial_tie,
            'capital': build_imperial_capital,
            'frigate': build_imperial_frigate,
            'convoy': build_imperial_convoy}
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