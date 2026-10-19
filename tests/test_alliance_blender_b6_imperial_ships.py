"""S06 batch B6 guards - the Imperial ships, starting with the corvette.

Eleven Imperial bindings are ships (`art/manifests/handoffs/S06-B6-IMPERIAL-SHIPS.md`), and the first
row is `ship:imperial:corvette`: the legacy `needle` shape, 1,552 triangles of slender pointed
combat hull drawn today by `render/fleet_geometry.py::_ship_mesh`. The seed is script-authoritative
per the S03 source-authority policy (repeated modular hardware), so
`tools/art/build_b6_imperial_ships.py` is the recipe and `art/blender/imperial_corvette.blend` is a
derived artifact.

What these guards pin beyond the usual mesh contract:

* the seed is a **data table keyed by binding** (`ROWS`), so the ten rows after this one are rows and
  not copies, and the first row itself is data rather than a second copy-paste kit;
* the authored hull **reaches the legacy envelope per axis and per side**, because
  `render/ship_sizes.ship_size` derives the class scale, the drawn length and every review camera
  from the drawn length: a hull that fills less of the box would change the ship's size in game;
* every loader role is filled by real geometry, because the appearance review ablates roles;
* the manifest **re-derives from the mesh on disk** (same bytes, same bounds, same revision);
* the row is **served only in an explicit preview session** and selects nothing in stock; and it is
  registered only under separate S07 execution authority, with original approval receipts and no default activation.

Run:  PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b6_imperial_ships
"""

import ast
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SEED = 'tools/art/build_b6_imperial_ships.py'
GENERATOR = ROOT / 'tools/art/gen_export_wrappers.py'
WRAPPER = ROOT / 'tools/art/export_imperial_corvette.py'
PROBE = 'tools/art/probe_b6_servability.py'
MESH = ROOT / 'assets/models/imperial_corvette.mesh.json'
MANIFEST = ROOT / 'assets/models/manifests/imperial_corvette.json'
BLEND = 'art/blender/imperial_corvette.blend'

REGISTRY_KEY = 'imperial:corvette'  # the runtime key; `BINDING` is the inventory's canonical spelling
BINDING = 'ship:imperial:corvette'
SHIP_BINDING = 'imperial:corvette'
IDENTIFIER = 'imperial_corvette'
DATA_ID = 'imperial_corvette'
ASSET_ID = 'core:imperial/corvette'
LEGACY_SHAPE = 'needle'
# The row's scale envelope, read from art/manifests/model_inventory.json
# (`ShipData.radius=34.0; legacy shape 'needle' authored in model space at fixed extent`).
STATION_RADIUS = 34.0
# The legacy extent, measured from `render/fleet_geometry.py::ship_mesh('needle')` by
# `tools/art/probe_b6_scope.py`: envelope -16.000,-5.000,-43.601 .. 16.000,24.000,48.000 at
# 1,552 triangles and 858 vertices. The authored hull fills this box exactly.
ENVELOPE = ((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0))
LEGACY_TRIANGLES = 1552
LEGACY_VERTICES = 858
# Z span 91.601 minus 0.2, to one decimal - the house min_length for a hull.
MIN_LENGTH = 91.4
# The S06 ship floor and the standard ship caps an existing ship row carries.
FLOOR = 1800
MIN_TRIANGLES = 1900
ROLE_FLOOR = 120
CAPS = dict(triangles=11_888, vertices=9_450, bytes=2_000_000)
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
# The per-role ablation guard measures pixels changed by removing a role, so a role has to be a
# surface rather than a token: ~120 triangles is the floor this batch holds every role to.
DESIGN = ('Imperial grey combat corvette with a faceted needle hull, a dorsal armour spine and '
          'turret deck, outboard sponsons, a tall radiator fin, identification striping and two '
          'engine bells')
# What the row's own export wrapper declares, spelled the way the template renders it.
WRAPPER_TOKENS = ('ENVELOPE = ((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0))', 'MIN_LENGTH = 91.4',
                  'MAX_TRIANGLES = 11888', 'MAX_VERTICES = 9450', 'MAX_BYTES = 2_000_000')

# ---- the batch's last row: `ship:imperial:convoy` -------------------------------------------------
# A convoy is a *cluster* rather than one hull, and this row follows the three authored siblings
# (`rebel:convoy`, `confederacy:convoy`, `syndicate:convoy`) rather than inventing a convention of its
# own: the authored cluster reaches the binding's own declared box exactly in Z and stands a stated
# clearance inside it on X and Y. Z is the axis `render/ship_sizes.py::ship_size` divides the drawn
# length by (`scale = length / (hi[2] - lo[2])`), so reaching it exactly is what keeps the class scale,
# the drawn length, the collision radius and every review camera answering what they answered before.
# The three siblings carry the same relation in their own sidecars and meshes, and the guards below
# measure it there rather than restating it as a comment.
CONVOY_BINDING = 'ship:imperial:convoy'
CONVOY_REGISTRY_KEY = 'imperial:convoy'
CONVOY_IDENTIFIER = 'imperial_convoy'
CONVOY_DATA_ID = 'imperial_crew_transport'
CONVOY_ASSET_ID = 'core:imperial/convoy'
CONVOY_LEGACY_SHAPE = 'box'
CONVOY_LABEL = 'Imperial Convoy Barge'
CONVOY_MESH = ROOT / 'assets/models/imperial_convoy.mesh.json'
CONVOY_MANIFEST = ROOT / 'assets/models/manifests/imperial_convoy.json'
CONVOY_WRAPPER = ROOT / 'tools/art/export_imperial_convoy.py'
CONVOY_SIDECAR = ROOT / 'art/manifests/pending/S06-IMPERIAL-CONVOY.json'
CONVOY_BLEND = ROOT / 'art/blender/imperial_convoy.blend'
# The binding's own legacy `box` extent, from `art/manifests/model_inventory.json`, measured through
# `render/fleet_geometry.py::ship_mesh('box')` by `tools/art/probe_b6_scope.py`: this row's declared box
# and the box its wrapper declares, at 1,536 triangles and 840 vertices.
CONVOY_ENVELOPE = ((-20.0, 20.0), (-7.0, 26.5), (-24.6975, 24.35825))
CONVOY_LEGACY_TRIANGLES = 1536
CONVOY_LEGACY_VERTICES = 840
# Z span 49.05575 minus 0.2, the house min_length for a hull; the wrapper declares 48.9.
CONVOY_MIN_LENGTH = 48.85575
# The Imperial reading of the cluster: the siblings stand at 4,512 / 4,584 / 4,756 triangles.
CONVOY_TARGET = (4400, 4900)
# The clearance the cluster stands inside its own declared box - the seed's `CONVOY_CLEARANCE`.
CONVOY_CLEARANCE = dict(beam=0.5, keel=0.2, mast=0.7, module=0.7)
# The three authored siblings whose convention this row follows, by mesh identifier.
CONVOY_SIBLINGS = ('alliance_convoy', 'legion_convoy', 'syndicate_convoy')
# What this row's own wrapper declares, spelled the way the template renders it.
CONVOY_WRAPPER_TOKENS = ('ENVELOPE = ((-20.0, 20.0), (-7.0, 26.5), (-24.6975, 24.35825))',
                         'MIN_LENGTH = 48.9', 'MAX_TRIANGLES = 11888', 'MAX_VERTICES = 9450',
                         'MAX_BYTES = 2_000_000')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def seed_text():
    return (ROOT / SEED).read_text(encoding='utf-8')


def mesh():
    return load(MESH)


def revision_of(asset, sha):
    """The manifest revision recipe: sha256 of 'asset\\n' + 'lod:sha256' per file, sorted by lod."""
    return hashlib.sha256(f'{asset}\nmesh:{sha}'.encode()).hexdigest()


def _rows_table():
    """The seed's ROWS table, evaluated standalone.

    The table has to be plain literals for this to work - which is the property the batch wants
    anyway, because a later Imperial row is then a row and not a code path.
    """
    tree = ast.parse(seed_text())
    node = next((n for n in tree.body if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], 'id', '') == 'ROWS'), None)
    assert node is not None, 'the seed must declare a ROWS table keyed by binding'
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<seed>', 'exec'), namespace)
    return namespace['ROWS']


class SeedContract(unittest.TestCase):
    def test_the_seed_is_script_authoritative_and_a_data_table_keyed_by_binding(self):
        text = seed_text()
        rows = _rows_table()
        self.assertIn(BINDING, rows, 'the batch seed must carry this row as data')
        row = rows[BINDING]
        self.assertEqual(row['identifier'], IDENTIFIER)
        self.assertEqual(row['data_id'], DATA_ID)
        self.assertEqual(row['legacy_shape'], LEGACY_SHAPE)
        self.assertEqual(tuple(tuple(a) for a in row['limits']), ENVELOPE)
        self.assertEqual(row['station_radius'], STATION_RADIUS)
        self.assertEqual(row['ship_kind'], 'corvette')
        self.assertEqual(row['faction'], 'imperial')
        # One seed authors every row of the batch, so the build path is driven by the table.
        self.assertEqual(text.count('def build('), 1)
        self.assertIn('ROWS[key]', text, 'the build must read the row rather than restate it')
        self.assertIn("authority='script'", text)
        for key in ('features_json', 'authority', 'design', 'binding', 'review', 'coordinates',
                    'runtime'):
            self.assertIn(f"bpy.context.scene['{key}']", text, f'the B5 seed sets {key}')
        self.assertIn('SEED_OK', text)
        self.assertIn('weld_scene(', text)
        self.assertIn('engine_material_role', text)
        self.assertIn('compress=True', text)

    def test_the_seed_refuses_to_overwrite_an_existing_master(self):
        text = seed_text()
        self.assertIn('is the editable master', text)
        self.assertIn("'--replace-seed' not in argv", text)
        self.assertLess(text.index('_refuse_existing_master(_ARGV)'), text.index('import bpy'))

    def test_the_seed_extent_check_catches_a_real_overrun_and_ignores_float_noise(self):
        tree = ast.parse(seed_text())
        const = next(n for n in tree.body if isinstance(n, ast.Assign)
                     and getattr(n.targets[0], 'id', '') == 'BREACH_TOLERANCE')
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'breach_lines')
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[const, fn], type_ignores=[])),
                     '<seed>', 'exec'), namespace)
        breach_lines = namespace['breach_lines']
        limits = [[-16.0, 16.0], [-5.0, 24.0], [-43.601, 48.0]]
        self.assertEqual(breach_lines('x', [-16.0, -5.0, -43.601], [16.0, 24.0, 48.0], limits,
                                      [['', '']] * 3), [])
        self.assertEqual(breach_lines('x', [-16.0001, -5.0, -43.601], [16.0, 24.0, 48.0], limits,
                                      [['', '']] * 3), [])
        over = breach_lines('x', [-16.06, -5.0, -43.601], [16.0, 24.0, 48.0], limits, [['', '']] * 3)
        self.assertEqual(len(over), 1)
        self.assertIn('X low', over[0])

    def test_the_seed_saves_a_blend_that_the_wrapper_exports_from(self):
        text = seed_text()
        self.assertIn(f"art/blender/{{identifier}}.blend", text.replace('ROOT / ', ''))
        self.assertIn('save_as_mainfile', text)


class MeshContract(unittest.TestCase):
    def test_the_mesh_reaches_the_declared_legacy_envelope_per_axis_and_per_side(self):
        """The authored hull fills the legacy box, so the class scale and drawn length are unchanged."""
        lo, hi = mesh()['bounds']
        for axis in range(3):
            low, high = ENVELOPE[axis]
            # The exporter snaps float32 representation noise onto the declared edge (5e-6), so
            # this is the exporter's own quantiser, not a widened fit.
            self.assertLessEqual(abs(lo[axis] - low), 1e-6, f'axis {axis} low {lo[axis]} != {low}')
            self.assertLessEqual(abs(hi[axis] - high), 1e-6, f'axis {axis} high {hi[axis]} != {high}')
        self.assertGreaterEqual(hi[2] - lo[2], MIN_LENGTH)

    def test_the_mesh_satisfies_the_loader_contract_and_the_ship_caps(self):
        data = mesh()
        self.assertEqual(data['asset'], IDENTIFIER)
        self.assertEqual(data['coordinates'], 'X beam; Y up; +Z forward')
        self.assertEqual(data['triangle_count'], sum(len(v) for v in data['batches'].values()))
        self.assertGreater(data['triangle_count'], FLOOR, 'the exporter refuses at or under 1,800')
        self.assertGreaterEqual(data['triangle_count'], MIN_TRIANGLES,
                                'the B6 target band starts at 1,900 triangles')
        self.assertLessEqual(data['triangle_count'], CAPS['triangles'])
        self.assertLessEqual(len(data['vertices']), CAPS['vertices'])
        self.assertLessEqual(MESH.stat().st_size, CAPS['bytes'])
        for role, rows in data['batches'].items():
            self.assertIn(role, ROLES)
            for row in rows:
                self.assertEqual(len(row), 6)
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in row[:3])), 1.0, places=9)
                for index in row[3:]:
                    self.assertLess(index, len(data['vertices']))

    def test_every_role_carries_real_geometry(self):
        """A later per-role ablation measures pixels changed by removing each role."""
        data = mesh()
        counts = {role: len(rows) for role, rows in data['batches'].items()}
        self.assertEqual({r for r, n in counts.items() if n}, set(ROLES),
                         'every loader role has to be filled by real geometry')
        for role in ROLES:
            self.assertGreaterEqual(counts[role], ROLE_FLOOR,
                                    f'{role} carries {counts[role]} triangles; the ablation needs a '
                                    f'surface, not a token')

    def test_the_authored_hull_is_not_the_legacy_mesh_restated(self):
        data = mesh()
        self.assertGreater(data['triangle_count'], LEGACY_TRIANGLES,
                           'the authored hull must add detail over the 1,552-triangle legacy shape')
        self.assertEqual(data['features']['legacy_shape'], LEGACY_SHAPE)
        self.assertEqual(data['features']['authority'], 'script')
        self.assertEqual(data['features']['binding'], BINDING)
        self.assertEqual(data['features']['approval'], 'pending_owner_approval')
        self.assertEqual(data['features']['seed_recipe'].split(';')[0], SEED)
        self.assertIn('no external mesh or texture dependencies', data['features']['provenance'])


class ManifestContract(unittest.TestCase):
    def test_manifest_exists_only_for_the_authorized_approved_revision(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [REGISTRY_KEY])
    def test_manifest_receipt_is_bound_to_the_original_appearance_decision(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [REGISTRY_KEY])
class PrevieFlip(unittest.TestCase):
    """The batch's acceptance test, driven here as well as in the probe.

    `ship_visual_key` asks `render.asset_selection.ship_binding` first, which builds
    `f'{faction}:{role}'` and returns `None` whenever no resolver is configured, so stock keeps the
    legacy shape. With a resolver configured the same call mints `imperial:corvette`, which is what
    makes this row servable without any change to `render/faction_visuals.py`.
    """

    def store(self):
        class _Ship:
            faction = 'imperial'
            category = 'corvette'
            crew_capacity = 0

        class _Store:
            ships = {DATA_ID: _Ship()}

            @staticmethod
            def ship_visual(_data_id):
                return {'shape': LEGACY_SHAPE}

        return _Store()

    def test_the_flip_serves_the_authored_corvette_in_preview_and_nothing_in_stock(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_preview_boundary
        assert_preview_boundary(self, ROOT, [REGISTRY_KEY])
    def test_real_ship_route_selects_registered_corvette_only_in_preview(self):
        from unittest.mock import patch
        from render import asset_selection as selection
        from render.faction_visuals import ship_visual_key
        with patch.multiple(selection, _selection={'model_preview': False, 'visual_packs': []},
                            _resolver=None, _generation=0, _renderer_owners=set()):
            selection.configure({})
            self.assertEqual(ship_visual_key(self.store(), DATA_ID), LEGACY_SHAPE)
            selection.configure({'model_preview': True}, asset_root=ROOT)
            self.assertEqual(ship_visual_key(self.store(), DATA_ID), REGISTRY_KEY)
            self.assertIsNotNone(selection.mesh_for(REGISTRY_KEY))
            selection.configure({})
            self.assertEqual(ship_visual_key(self.store(), DATA_ID), LEGACY_SHAPE)
class NotLanded(unittest.TestCase):
    def test_row_has_authorized_registration_and_original_approval_receipt(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [REGISTRY_KEY])

    def test_registry_row_names_the_approved_revision_not_a_new_approval(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [REGISTRY_KEY])
    def test_the_wrapper_carries_the_legacy_envelope_and_the_standard_ship_caps(self):
        text = GENERATOR.read_text(encoding='utf-8')
        entry = re.search(r"ASSETS\['imperial_corvette'\] = \((.*?)\)\n", text, re.S)
        self.assertTrue(entry, 'the wrapper table must carry the row')
        declaration = entry.group(1) if entry else ''
        for token in ('(-16.0, 16.0)', '(-5.0, 24.0)', '(-43.601, 48.0)', '91.4', '11888', '9450',
                      '2_000_000'):
            self.assertIn(token, declaration, token)
        wrapper = WRAPPER.read_text(encoding='utf-8')
        for token in WRAPPER_TOKENS:
            self.assertIn(token, wrapper, token)
        self.assertIn("open_mainfile", wrapper)
        self.assertIn('Never reconstructs or saves source', wrapper)

    def test_no_other_wrapper_moved(self):
        """Authoring a row must not rewrite any other row's wrapper.

        An approval record hashes the generated wrapper it names, so a batch that regenerates the
        world invalidates every earlier decision. The check is the generator's own: it either reports
        every wrapper up to date, or something moved that should not have. The one wrapper allowed to
        carry a floor of its own is the declared small prop from `s06-small-prop-class-2026-10-17`.
        """
        generator = subprocess.run([str(ROOT / '.venv/bin/python'),
                                    str(ROOT / 'tools/art/gen_export_wrappers.py'), '--check'],
                                   cwd=ROOT, capture_output=True, text=True)
        self.assertIn('0 written', generator.stdout,
                      f'the generator rewrote wrappers: {generator.stdout.strip()}')
        declared = []
        for path in sorted((ROOT / 'tools/art').glob('export_*.py')):
            match = re.search(r'^MIN_TRIANGLES = (\d+)$', path.read_text(encoding='utf-8'), re.M)
            if match:
                declared.append((path.name, int(match.group(1))))
        self.assertEqual(declared, [('export_shared_asteroid_field.py', 120)],
                         'only the declared small prop may carry a floor of its own')


# ------------------------------------------------------------------------------------- rows 2 and 3
# The two TIE squadron rows. They are the same batch as the corvette and are held to the same
# contract, plus the two things that are theirs alone: a hexagonal wing panel that fills the
# measured box, and a pair of rows that must not be a scaled copy of one another.
TIE_BINDING = 'ship:imperial:tie_squadron'
TIE_REGISTRY_KEY = 'imperial:fighter'      # the runtime key: `ship_binding` mints faction:category
TIE_IDENTIFIER = 'imperial_tie_squadron'
TIE_DATA_ID = 'imperial_tie_squadron'
TIE_ASSET_ID = 'core:imperial/fighter'
TIE_RADIUS = 22.0
TIE_MESH = ROOT / 'assets/models/imperial_tie_squadron.mesh.json'
TIE_WRAPPER = ROOT / 'tools/art/export_imperial_tie_squadron.py'
TIE_LABEL = 'Talon Interceptor Squadron'

BOMBER_BINDING = 'ship:imperial:tie_bomber_squadron'
BOMBER_REGISTRY_KEY = 'imperial:bomber'
BOMBER_IDENTIFIER = 'imperial_tie_bomber_squadron'
BOMBER_DATA_ID = 'imperial_tie_bomber_squadron'
BOMBER_ASSET_ID = 'core:imperial/bomber'
BOMBER_RADIUS = 24.0
BOMBER_MESH = ROOT / 'assets/models/imperial_tie_bomber_squadron.mesh.json'
BOMBER_WRAPPER = ROOT / 'tools/art/export_imperial_tie_bomber_squadron.py'
BOMBER_LABEL = 'Hammer Torpedo Squadron'

# The legacy `wedge` squadron extent, measured from `render/fleet_geometry.py::ship_mesh('wedge')`
# by `tools/art/probe_b6_scope.py`: -31.250,-3.240,-28.996 .. 31.250,14.000,35.000 at 1,456
# triangles and 792 vertices, for both rows. The authored TIE fills this box exactly.
SQUADRON_ENVELOPE = ((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0))
SQUADRON_LEGACY_SHAPE = 'wedge'
SQUADRON_LEGACY_TRIANGLES = 1456
# Z span 63.996 minus 0.2, to one decimal - the house min_length for a hull.
SQUADRON_MIN_LENGTH = 63.8
SQUADRON_TARGET = (1900, 2600)
# The seed's own extent tolerance: the authored hull may sit this far *inside* a box face and
# still count as reaching it; the exporter's quantiser snaps the face itself onto the edge.
REACH_TOLERANCE = 1e-3
# What each row's own export wrapper declares, spelled the way the template renders it.
SQUADRON_WRAPPER_TOKENS = ('ENVELOPE = ((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0))',
                           'MIN_LENGTH = 63.8', 'MAX_TRIANGLES = 11888', 'MAX_VERTICES = 9450',
                           'MAX_BYTES = 2_000_000')


def _pure_functions(*names):
    """Top-level `frame`/geometry functions from the seed, evaluated without Blender.

    The TIE panel's own frame is a pure function of the measured limits, so it can be driven
    here rather than asserted by matching text in the seed: a text match passes on a stale
    string and says nothing about the shape the seed actually authors.
    """
    wanted = {'frame', *names}
    tree = ast.parse(seed_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.Assign))
             and getattr(n, 'name', None) in wanted or
             (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') in wanted)]
    namespace = {'math': math}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 '<seed>', 'exec'), namespace)
    missing = wanted - set(namespace)
    assert not missing, f'the seed no longer defines {sorted(missing)}'
    return namespace


def hex_union(limits):
    """Every vertex the seed's panel authoring emits, from the seed's own pure functions.

    These are exactly the calls `build_imperial_tie` makes for one side's panel - no more: adding
    a full-size face to the union would keep the reach test green after the rim ring shrank.
    """
    ns = _pure_functions('hex_frame', 'hex_face_geometry', 'hex_ring_geometry')
    points = []
    for side in (-1, 1):
        for call in (lambda: ns['hex_ring_geometry'](limits, side, 1.0, 0.885, 0.7),
                     lambda: ns['hex_face_geometry'](limits, side, 0.90, 0.8, 0.10),
                     lambda: ns['hex_face_geometry'](limits, side, 0.86, 0.9, 0.18)):
            verts, _faces = call()
            points.extend(verts)
    return points


def normalised_vertices(path):
    """A mesh's vertices in its own bounds' unit cube, quantised - a shape fingerprint.

    Two rows that are a scaled copy of one another reduce to the same set; a difference in
    proportions, count or detail does not. Comparing raw coordinates would pass a uniform
    scale, which is exactly what "not a scaled copy" has to exclude.
    """
    data = load(path)
    lo, hi = data['bounds']
    span = [max(hi[i] - lo[i], 1e-9) for i in range(3)]
    return sorted({tuple(round((p[i] - lo[i]) / span[i], 3) for i in range(3))
                   for p in data['vertices']})


class SquadronSeedContract(unittest.TestCase):
    def test_the_seed_carries_both_squadron_rows_as_data(self):
        rows = _rows_table()
        for binding, identifier, data_id, radius, kind in (
                (TIE_BINDING, TIE_IDENTIFIER, TIE_DATA_ID, TIE_RADIUS, 'tie_squadron'),
                (BOMBER_BINDING, BOMBER_IDENTIFIER, BOMBER_DATA_ID, BOMBER_RADIUS,
                 'tie_bomber_squadron')):
            with self.subTest(binding=binding):
                self.assertIn(binding, rows, 'the batch seed must carry this row as data')
                row = rows[binding]
                self.assertEqual(row['identifier'], identifier)
                self.assertEqual(row['data_id'], data_id)
                self.assertEqual(row['legacy_shape'], SQUADRON_LEGACY_SHAPE)
                self.assertEqual(tuple(tuple(a) for a in row['limits']), SQUADRON_ENVELOPE)
                self.assertEqual(row['station_radius'], radius)
                self.assertEqual(row['ship_kind'], kind)
                self.assertEqual(row['faction'], 'imperial')
        # One seed authors every row of the batch, and a squadron row is not the corvette's
        # builder with a different constant: the two squadrons share a builder the corvette
        # does not, and the rows carry it as data.
        self.assertEqual(seed_text().count('def build('), 1)

    def test_the_tie_panel_pair_fills_the_legacy_box_per_axis_and_per_side(self):
        """The panel is the row's defining element, and the pair fills the measured extent.

        Behavioural: the seed's own geometry function is driven here, not grepped. The rim
        ring's outer plane is the beam extreme and its outer walls are the full hexagon, so
        all six faces of the legacy box are reached by geometry that is actually authored.
        """
        points = hex_union(SQUADRON_ENVELOPE)
        self.assertTrue(points)
        for axis in range(3):
            low, high = SQUADRON_ENVELOPE[axis]
            values = [p[axis] for p in points]
            self.assertLessEqual(max(values), high + 1e-9, f'axis {axis} exceeds the box')
            self.assertGreaterEqual(min(values), low - 1e-9, f'axis {axis} exceeds the box')
            self.assertLessEqual(abs(min(values) - low), REACH_TOLERANCE,
                                 f'axis {axis} low {min(values)} does not reach {low}')
            self.assertLessEqual(abs(max(values) - high), REACH_TOLERANCE,
                                 f'axis {axis} high {max(values)} does not reach {high}')

    def test_the_tie_pod_stays_inside_the_measured_box(self):
        """The cockpit globe is on the centreline and never carries the envelope itself."""
        ns = _pure_functions('tie_pod_sections')
        for binding, radius, rings in ((TIE_BINDING, 5.6, 9), (BOMBER_BINDING, 6.8, 13)):
            with self.subTest(binding=binding):
                sections = ns['tie_pod_sections'](SQUADRON_ENVELOPE, radius, rings)
                self.assertGreaterEqual(len(sections), 5)
                for z, w, top, bottom in sections:
                    self.assertLessEqual(top, SQUADRON_ENVELOPE[1][1] + 1e-9)
                    self.assertGreaterEqual(bottom, SQUADRON_ENVELOPE[1][0] - 1e-9)
                    self.assertLessEqual(z, SQUADRON_ENVELOPE[2][1] + 1e-9)
                    self.assertGreaterEqual(z, SQUADRON_ENVELOPE[2][0] - 1e-9)
                    self.assertLessEqual(w, 31.25 - 1.0, 'the pod must clear the panels')


class SquadronMeshContract(unittest.TestCase):
    def contract(self, path, binding, identifier, legacy_vertices):
        data = load(path)
        self.assertEqual(data['asset'], identifier)
        self.assertEqual(data['coordinates'], 'X beam; Y up; +Z forward')
        self.assertEqual(data['triangle_count'], sum(len(v) for v in data['batches'].values()))
        self.assertGreater(data['triangle_count'], SQUADRON_LEGACY_TRIANGLES,
                           'the authored hull must add detail over the legacy wedge')
        self.assertGreaterEqual(data['triangle_count'], SQUADRON_TARGET[0])
        self.assertLessEqual(data['triangle_count'], SQUADRON_TARGET[1])
        self.assertLessEqual(len(data['vertices']), CAPS['vertices'])
        self.assertLessEqual(path.stat().st_size, CAPS['bytes'])
        lo, hi = data['bounds']
        for axis in range(3):
            low, high = SQUADRON_ENVELOPE[axis]
            self.assertGreaterEqual(lo[axis], low - 1e-6, f'axis {axis} lower breach')
            self.assertLessEqual(hi[axis], high + 1e-6, f'axis {axis} upper breach')
            self.assertLessEqual(abs(lo[axis] - low), REACH_TOLERANCE,
                                 f'axis {axis} low {lo[axis]} does not reach {low}')
            self.assertLessEqual(abs(hi[axis] - high), REACH_TOLERANCE,
                                 f'axis {axis} high {hi[axis]} does not reach {high}')
        self.assertGreaterEqual(hi[2] - lo[2], SQUADRON_MIN_LENGTH)
        counts = {role: len(rows) for role, rows in data['batches'].items()}
        self.assertEqual({r for r, n in counts.items() if n}, set(ROLES))
        for role in ROLES:
            self.assertGreaterEqual(counts[role], ROLE_FLOOR,
                                    f'{role} carries {counts[role]} triangles')
        for role, rows in data['batches'].items():
            for row in rows:
                self.assertEqual(len(row), 6)
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in row[:3])), 1.0, places=9)
                for index in row[3:]:
                    self.assertLess(index, len(data['vertices']))
        self.assertEqual(data['features']['legacy_shape'], SQUADRON_LEGACY_SHAPE)
        self.assertEqual(data['features']['authority'], 'script')
        self.assertEqual(data['features']['binding'], binding)
        self.assertEqual(data['features']['approval'], 'pending_owner_approval')
        self.assertEqual(data['features']['seed_recipe'].split(';')[0], SEED)
        self.assertIn('no external mesh or texture dependencies', data['features']['provenance'])
        self.assertEqual(data['features']['station_radius'], legacy_vertices)
        return data

    def test_the_authored_tie_is_not_the_legacy_wedge_restated(self):
        self.contract(TIE_MESH, TIE_BINDING, TIE_IDENTIFIER, TIE_RADIUS)

    def test_the_authored_tie_bomber_is_not_the_legacy_wedge_restated(self):
        self.contract(BOMBER_MESH, BOMBER_BINDING, BOMBER_IDENTIFIER, BOMBER_RADIUS)

    def test_neither_squadron_is_a_scaled_copy_of_the_other(self):
        """The two rows must differ in shape, not only in size.

        A scaled copy normalised into its own bounding box is the same point set; different
        proportions, part counts and detail are not. The seed also has to carry the bomber's
        heavier pod and thicker pylon as row data, because that is what makes them different.
        """
        rows = _rows_table()
        tie, bomber = rows[TIE_BINDING], rows[BOMBER_BINDING]
        self.assertGreater(bomber['pod_radius'], tie['pod_radius'],
                           'the bomber carries a heavier pod')
        self.assertGreater(bomber['spar_thickness'], tie['spar_thickness'],
                           'the bomber carries thicker pylons')
        self.assertNotEqual(tie['identifier'], bomber['identifier'])
        a, b = load(TIE_MESH), load(BOMBER_MESH)
        self.assertNotEqual(a['triangle_count'], b['triangle_count'])
        self.assertGreater(abs(a['triangle_count'] - b['triangle_count']), 40,
                           'the two hulls must not be one builder run twice')
        self.assertNotEqual(normalised_vertices(TIE_MESH), normalised_vertices(BOMBER_MESH),
                            'the two rows must not be a scaled copy of one another')
        self.assertNotEqual({r: len(v) for r, v in a['batches'].items()},
                            {r: len(v) for r, v in b['batches'].items()},
                            'the role distribution must differ too')


class SquadronWrappers(unittest.TestCase):
    def test_the_generator_declares_both_squadron_rows(self):
        text = GENERATOR.read_text(encoding='utf-8')
        for identifier, label in ((TIE_IDENTIFIER, TIE_LABEL),
                                  (BOMBER_IDENTIFIER, BOMBER_LABEL)):
            with self.subTest(identifier=identifier):
                entry = re.search(rf"ASSETS\['{identifier}'\] = \((.*?)\)\n", text, re.S)
                self.assertTrue(entry, f'the wrapper table must carry {identifier}')
                declaration = entry.group(1)
                self.assertIn(label, declaration)
                for token in ('(-31.25, 31.25)', '(-3.24, 14.0)', '(-28.996, 35.0)', '63.8',
                              '11888', '9450', '2_000_000'):
                    self.assertIn(token, declaration, token)
                wrapper = (ROOT / f'tools/art/export_{identifier}.py')
                self.assertTrue(wrapper.exists(), f'{wrapper.name} must be generated')
                body = wrapper.read_text(encoding='utf-8')
                for token in SQUADRON_WRAPPER_TOKENS:
                    self.assertIn(token, body, token)
                self.assertIn('open_mainfile', body)
                self.assertIn('Never reconstructs or saves source', body)

    def test_a_squadron_row_declares_no_floor_of_its_own(self):
        """Both squadrons are hulls: the 1,800 floor is the template's, not theirs."""
        for identifier in (TIE_IDENTIFIER, BOMBER_IDENTIFIER):
            path = ROOT / f'tools/art/export_{identifier}.py'
            self.assertNotIn('MIN_TRIANGLES =', path.read_text(encoding='utf-8'))


class SquadronNotLanded(unittest.TestCase):
    def test_squadrons_have_authorized_registration_and_original_receipts(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [TIE_REGISTRY_KEY, BOMBER_REGISTRY_KEY])

    def test_squadron_registry_rows_name_the_approved_revisions(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [TIE_REGISTRY_KEY, BOMBER_REGISTRY_KEY])


class SquadronFlip(unittest.TestCase):
    """The batch's acceptance test for both squadron rows, run through the real probe."""

    def probe(self, binding):
        return subprocess.run([str(ROOT / '.venv/bin/python'),
                               str(ROOT / 'tools/art/probe_b6_servability.py'), binding],
                              cwd=ROOT, capture_output=True, text=True,
                              env={'PYTHONPATH': 'tests', 'PATH': os.environ.get('PATH', ''),
                                   'HOME': os.environ.get('HOME', '')})

    def test_the_flip_serves_both_squadrons_in_preview_and_nothing_in_stock(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_preview_boundary
        assert_preview_boundary(self, ROOT, [TIE_REGISTRY_KEY, BOMBER_REGISTRY_KEY])

# ----------------------------------------------------------------------------------- rows 4 to 7
# The two dagger capitals, the cruiser and the frigate. They are the same batch as the corvette and
# the TIE squadrons and are held to the same contract, plus the things that are theirs alone:
#
# * the two dagger rows draw the *same* legacy shape at the same measured extent, so the seed has to
#   author them as two hulls rather than one hull at two scales. The supercapital's deeper, wider
#   pressure hull and its extra superstructure tier are row data, and the two shape fingerprints
#   differ even once each is normalised into the box it fills.
# * the frigate shares the corvette's `needle` box and has to be its own heavier hull.
# * every row lands inside the stated B6 triangle band (1,900-2,600), the two daggers are the
#   heaviest pair, and the supercapital is the heavier of the two.
#
# Two things are *measured here rather than transcribed*: each row's declared `limits` is compared
# against the live renderer's own `ship_mesh` for that row's shape string, and "not the legacy mesh
# restated" is a shape fingerprint of the authored mesh against that same live legacy mesh - a
# count comparison cannot say it for a row whose legacy hull is larger than the stated band.
CAPITAL_TARGET = (1900, 2600)      # the batch's stated band for these four rows
CAPITAL_ROWS = (
    dict(binding='ship:imperial:battleship', registry_key='imperial:battleship',
         identifier='imperial_battleship', label='Executor-class Dreadnought',
         legacy_shape='dagger', ship_kind='capital', station_radius=150.0,
         envelope=((-38.45, 38.45), (-10.0, 39.5), (-80.183, 108.0)),
         legacy_triangles=3296, legacy_vertices=1814, min_length=188.0),
    dict(binding='ship:imperial:supercapital', registry_key='imperial:supercapital',
         identifier='imperial_supercapital', label='Sovereign-class Star Dreadnought',
         legacy_shape='dagger', ship_kind='capital', station_radius=260.0,
         envelope=((-38.45, 38.45), (-10.0, 39.5), (-80.183, 108.0)),
         legacy_triangles=3296, legacy_vertices=1814, min_length=188.0),
    dict(binding='ship:imperial:cruiser', registry_key='imperial:cruiser',
         identifier='imperial_cruiser', label='Gladiator Cruiser',
         legacy_shape='cruiser', ship_kind='capital', station_radius=90.0,
         envelope=((-29.45, 29.45), (-7.0, 31.5), (-62.94, 78.0)),
         legacy_triangles=2800, legacy_vertices=1542, min_length=140.7),
    dict(binding='ship:imperial:frigate', registry_key='imperial:frigate',
         identifier='imperial_frigate', label='Lancer Frigate',
         legacy_shape='needle', ship_kind='frigate', station_radius=55.0,
         envelope=((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0)),
         legacy_triangles=1552, legacy_vertices=858, min_length=91.4),
)
for _row in CAPITAL_ROWS:
    _row['mesh'] = ROOT / f'assets/models/{_row["identifier"]}.mesh.json'
    _row['manifest'] = ROOT / f'assets/models/manifests/{_row["identifier"]}.json'
    _row['wrapper'] = ROOT / f'tools/art/export_{_row["identifier"]}.py'
CAPITAL_ASSET_IDS = {row['identifier']: f'core:imperial/{row["registry_key"].split(":", 1)[1]}'
                     for row in CAPITAL_ROWS}


def legacy_geometry(shape):
    """The legacy mesh this row draws today, through the renderer's own public `ship_mesh`.

    `ship_mesh('imperial:cruiser')` normalises an unknown key to `box`, so the row's *shape string*
    from the inventory is what gets measured - the shape `ship_visual_key` actually resolves and
    passes down. Batches are role -> triangles, each triangle `(normal, (a, b, c))`.
    """
    sys.path.insert(0, str(ROOT))
    from render import fleet_geometry as fg
    mesh = fg.ship_mesh(shape)
    points = [corner for role in mesh.values() for _normal, corners in role for corner in corners]
    triangles = sum(len(role) for role in mesh.values())
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi, points, triangles


def fingerprint(points, lo, hi):
    """A point set in its own bounds' unit cube, quantised - a shape fingerprint.

    A scaled copy normalised into its own box is the same set; a difference in proportions, part
    count or detail is not. Comparing raw coordinates would pass a uniform scale, which is exactly
    what "not a scaled copy" has to exclude.
    """
    span = [max(hi[i] - lo[i], 1e-9) for i in range(3)]
    return sorted({tuple(round((p[i] - lo[i]) / span[i], 3) for i in range(3)) for p in points})


def authored_mesh(row):
    return load(row['mesh'])


def authored_fingerprint(row):
    data = authored_mesh(row)
    lo, hi = data['bounds']
    return fingerprint(data['vertices'], lo, hi)


class CapitalSeedContract(unittest.TestCase):
    def test_the_seed_carries_the_four_rows_as_data(self):
        rows = _rows_table()
        for row in CAPITAL_ROWS:
            with self.subTest(binding=row['binding']):
                self.assertIn(row['binding'], rows,
                              'the batch seed must carry this row as data')
                seed_row = rows[row['binding']]
                self.assertEqual(seed_row['identifier'], row['identifier'])
                self.assertEqual(seed_row['data_id'], row['identifier'])
                self.assertEqual(seed_row['label'], row['label'])
                self.assertEqual(seed_row['legacy_shape'], row['legacy_shape'])
                self.assertEqual(tuple(tuple(a) for a in seed_row['limits']), row['envelope'])
                self.assertEqual(seed_row['station_radius'], row['station_radius'])
                self.assertEqual(seed_row['ship_kind'], row['ship_kind'])
                self.assertEqual(seed_row['faction'], 'imperial')
                self.assertEqual(seed_row['legacy_triangles'], row['legacy_triangles'])
                self.assertEqual(seed_row['legacy_vertices'], row['legacy_vertices'])
                # The shape itself is data: a later Imperial capital is a row, not a second kit.
                for key in ('hull_sections', 'sponson', 'keel', 'skirt', 'turrets', 'engines'):
                    self.assertIn(key, seed_row, f'{row["binding"]} must carry its {key} as data')
        text = seed_text()
        self.assertEqual(text.count('def build('), 1)
        self.assertIn('def build_imperial_capital', text)
        self.assertIn('def build_imperial_frigate', text)
        self.assertIn("'capital': build_imperial_capital", text)
        self.assertIn("'frigate': build_imperial_frigate", text)

    def test_the_declared_envelopes_are_what_the_live_renderer_measures(self):
        """The envelope is measured, not transcribed: the renderer's own mesh is the reference.

        This is the property the whole batch turns on - `render/ship_sizes.ship_size` derives the
        class scale and every review camera from the drawn length - so a row whose declared box is
        not the box the renderer draws would silently resize the ship in game.
        """
        for row in CAPITAL_ROWS:
            with self.subTest(binding=row['binding']):
                lo, hi, points, triangles = legacy_geometry(row['legacy_shape'])
                self.assertTrue(points)
                self.assertEqual(triangles, row['legacy_triangles'])
                self.assertEqual(len(set(points)), row['legacy_vertices'])
                for axis in range(3):
                    for measured, declared in ((lo[axis], row['envelope'][axis][0]),
                                               (hi[axis], row['envelope'][axis][1])):
                        # The inventory states these boxes to three decimals; the renderer carries
                        # the unrounded float. Anything past that rounding is a different ship.
                        self.assertLessEqual(abs(measured - declared), 1e-3,
                                             f'axis {axis}: the renderer draws {measured}, the row '
                                             f'declares {declared}')

    def test_the_dagger_pair_is_two_hulls_and_not_one_mesh_at_two_scales(self):
        """Both daggers draw one legacy shape at one extent, so the *seed* has to split them."""
        rows = _rows_table()
        battle, heavy = rows[CAPITAL_ROWS[0]['binding']], rows[CAPITAL_ROWS[1]['binding']]
        self.assertEqual(tuple(tuple(a) for a in battle['limits']),
                         tuple(tuple(a) for a in heavy['limits']),
                         'the two dagger rows share one measured legacy box')
        self.assertEqual(battle['legacy_shape'], heavy['legacy_shape'])
        keel_b = min(s[3] for s in battle['hull_sections'])
        keel_h = min(s[3] for s in heavy['hull_sections'])
        self.assertEqual(keel_h, keel_b,
                         'both fill the same legacy box, so their keels reach the same floor')
        # "Deeper" here is depth over the *length*: the supercapital runs its hull along the keel
        # for four frames where the battleship only touches it amidships.
        self.assertGreaterEqual(sum(1 for s in heavy['hull_sections'] if s[3] == keel_h), 4,
                                'the supercapital bottoms on its keel across four frames')
        self.assertLess(sum(1 for s in battle['hull_sections'] if s[3] == keel_b), 4,
                        'where the battleship only meets it over part of its length')
        profile = lambda sections: sum(s[1] * (s[2] - s[3]) for s in sections)
        self.assertGreater(profile(heavy['hull_sections']), profile(battle['hull_sections']) * 1.1,
                           'and it displaces a materially bigger pressure hull')
        self.assertGreater(max(s[1] for s in heavy['hull_sections']),
                           max(s[1] for s in battle['hull_sections']),
                           'and it is the wider hull')
        self.assertEqual(len(heavy['tiers']), len(battle['tiers']) + 1,
                         'and it carries one more superstructure tier')
        self.assertNotEqual(battle['identifier'], heavy['identifier'])
        self.assertNotEqual(battle['station_radius'], heavy['station_radius'])


class CapitalMeshContract(unittest.TestCase):
    def contract(self, row):
        data = authored_mesh(row)
        self.assertEqual(data['asset'], row['identifier'])
        self.assertEqual(data['coordinates'], 'X beam; Y up; +Z forward')
        self.assertEqual(data['triangle_count'], sum(len(v) for v in data['batches'].values()))
        # The loader contract and the stated B6 band for these rows.
        self.assertGreater(data['triangle_count'], FLOOR, 'the exporter refuses at or under 1,800')
        self.assertGreaterEqual(data['triangle_count'], CAPITAL_TARGET[0])
        self.assertLessEqual(data['triangle_count'], CAPITAL_TARGET[1])
        self.assertLessEqual(data['triangle_count'], CAPS['triangles'])
        self.assertLessEqual(len(data['vertices']), CAPS['vertices'])
        self.assertLessEqual(row['mesh'].stat().st_size, CAPS['bytes'])
        # Envelope per axis and per side: the authored hull fills the legacy box exactly.
        lo, hi = data['bounds']
        for axis in range(3):
            low, high = row['envelope'][axis]
            self.assertLessEqual(abs(lo[axis] - low), 1e-6, f'axis {axis} low {lo[axis]} != {low}')
            self.assertLessEqual(abs(hi[axis] - high), 1e-6,
                                 f'axis {axis} high {hi[axis]} != {high}')
        self.assertGreaterEqual(hi[2] - lo[2], row['min_length'])
        # Every loader role is a surface, not a token: the appearance review ablates roles.
        counts = {role: len(rows) for role, rows in data['batches'].items()}
        self.assertEqual({role for role, n in counts.items() if n}, set(ROLES),
                         'every loader role has to be filled by real geometry')
        for role in ROLES:
            self.assertGreaterEqual(counts[role], ROLE_FLOOR,
                                    f'{role} carries {counts[role]} triangles; the ablation needs '
                                    f'a surface, not a token')
        for role, rows in data['batches'].items():
            self.assertIn(role, ROLES)
            for triangle in rows:
                self.assertEqual(len(triangle), 6)
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in triangle[:3])), 1.0, places=9)
                for index in triangle[3:]:
                    self.assertLess(index, len(data['vertices']))
        self.assertEqual(data['features']['legacy_shape'], row['legacy_shape'])
        self.assertEqual(data['features']['authority'], 'script')
        self.assertEqual(data['features']['binding'], row['binding'])
        self.assertEqual(data['features']['station_radius'], row['station_radius'])
        self.assertEqual(data['features']['approval'], 'pending_owner_approval')
        self.assertEqual(data['features']['seed_recipe'].split(';')[0], SEED)
        self.assertIn('no external mesh or texture dependencies', data['features']['provenance'])
        return data

    def test_each_authored_hull_is_not_the_legacy_mesh_restated(self):
        """Behavioural: the authored shape is fingerprinted against the live legacy mesh.

        A count comparison is what the corvette's guard used, and it cannot say this for a row whose
        legacy hull (3,296 and 2,800 triangles) is larger than the stated 1,900-2,600 band. The
        fingerprint can: a restated legacy mesh reduces to the legacy set.
        """
        for row in CAPITAL_ROWS:
            with self.subTest(binding=row['binding']):
                data = self.contract(row)
                lo, hi, points, _triangles = legacy_geometry(row['legacy_shape'])
                self.assertNotEqual(authored_fingerprint(row), fingerprint(points, lo, hi),
                                    'the authored hull must not be the legacy shape restated')
                self.assertNotEqual(data['triangle_count'], row['legacy_triangles'])
                self.assertNotEqual(len(data['vertices']), row['legacy_vertices'])

    def test_neither_dagger_is_a_scaled_copy_of_the_other(self):
        """The pair shares a legacy box, so a scaled copy is exactly the failure mode to exclude."""
        battle, heavy = CAPITAL_ROWS[0], CAPITAL_ROWS[1]
        a, b = self.contract(battle), self.contract(heavy)
        self.assertGreater(b['triangle_count'], a['triangle_count'],
                           'the supercapital is the heavier hull of the pair')
        self.assertGreater(abs(a['triangle_count'] - b['triangle_count']), 40,
                           'the two hulls must not be one builder run twice')
        self.assertNotEqual(authored_fingerprint(battle), authored_fingerprint(heavy),
                            'the two rows must not be a scaled copy of one another')
        self.assertNotEqual({r: len(v) for r, v in a['batches'].items()},
                            {r: len(v) for r, v in b['batches'].items()},
                            'the role distribution must differ too')

    def test_the_frigate_is_a_heavier_hull_than_the_corvette_it_shares_a_box_with(self):
        """Both draw the legacy `needle` mesh today; the authored frigate has to be its own hull."""
        frigate = CAPITAL_ROWS[3]
        rows = _rows_table()
        self.assertEqual(tuple(tuple(x) for x in rows[frigate['binding']]['limits']),
                         tuple(tuple(x) for x in ENVELOPE),
                         "the frigate shares the corvette's measured legacy box")
        self.assertEqual(frigate['legacy_triangles'], LEGACY_TRIANGLES)
        mine, theirs = self.contract(frigate), mesh()
        self.assertGreater(mine['triangle_count'], theirs['triangle_count'],
                           'the frigate must be the heavier hull of the two needle ships')
        self.assertGreater(len(rows[frigate['binding']]['turrets']), 2,
                           "the frigate carries more gun turrets than the corvette's pair")
        self.assertGreater(len(mine['batches']['trim']), len(theirs['batches']['trim']),
                           'and more gun on the trim role the loader draws them from')
        lo, hi, points, _ = legacy_geometry('needle')
        self.assertNotEqual(authored_fingerprint(frigate), fingerprint(points, lo, hi),
                            'the frigate is its own hull, not the legacy needle restated')


class CapitalWrappers(unittest.TestCase):
    def test_the_generator_declares_the_four_rows_and_their_wrappers(self):
        text = GENERATOR.read_text(encoding='utf-8')
        for row in CAPITAL_ROWS:
            with self.subTest(identifier=row['identifier']):
                entry = re.search(rf"ASSETS\['{row['identifier']}'\] = \((.*?)\)\n", text, re.S)
                self.assertTrue(entry, f'the wrapper table must carry {row["identifier"]}')
                declaration = entry.group(1)
                self.assertIn(row['label'], declaration)
                (x0, x1), (y0, y1), (z0, z1) = row['envelope']
                for token in (f'({x0}, {x1})', f'({y0}, {y1})', f'({z0}, {z1})',
                              repr(row['min_length']), '11888', '9450', '2_000_000'):
                    self.assertIn(token, declaration, f'{row["identifier"]}: {token}')
                self.assertTrue(row['wrapper'].exists(),
                                f'{row["wrapper"].name} must be generated')
                body = row['wrapper'].read_text(encoding='utf-8')
                for token in (f'ENVELOPE = {row["envelope"]!r}',
                              f'MIN_LENGTH = {row["min_length"]}',
                              'MAX_TRIANGLES = 11888', 'MAX_VERTICES = 9450',
                              'MAX_BYTES = 2_000_000'):
                    self.assertIn(token, body, token)
                self.assertIn('open_mainfile', body)
                self.assertIn('Never reconstructs or saves source', body)

    def test_each_capital_row_declares_no_floor_of_its_own(self):
        """These are hulls: the 1,800 floor is the template's, not theirs."""
        for row in CAPITAL_ROWS:
            self.assertNotIn('MIN_TRIANGLES =', row['wrapper'].read_text(encoding='utf-8'))

    def test_the_four_new_wrappers_are_the_only_ones_that_moved(self):
        """Regenerating must not rewrite any other row's wrapper: an approval hashes it."""
        generator = subprocess.run([str(ROOT / '.venv/bin/python'),
                                    str(ROOT / 'tools/art/gen_export_wrappers.py'), '--check'],
                                   cwd=ROOT, capture_output=True, text=True)
        self.assertIn('0 written', generator.stdout,
                      f'the generator rewrote wrappers: {generator.stdout.strip()}')


class CapitalNotLanded(unittest.TestCase):
    def test_capitals_have_authorized_registration_and_original_receipts(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [row['registry_key'] for row in CAPITAL_ROWS])

    def test_capital_manifests_are_bound_to_authorized_approved_revisions(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [row['registry_key'] for row in CAPITAL_ROWS])

    def test_capital_registry_rows_name_the_approved_revisions(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [row['registry_key'] for row in CAPITAL_ROWS])


class CapitalFlip(unittest.TestCase):
    """The batch's acceptance test for the four rows, run through the real probe."""

    def probe(self, binding):
        return subprocess.run([str(ROOT / '.venv/bin/python'),
                               str(ROOT / 'tools/art/probe_b6_servability.py'), binding],
                              cwd=ROOT, capture_output=True, text=True,
                              env={'PYTHONPATH': 'tests', 'PATH': os.environ.get('PATH', ''),
                                   'HOME': os.environ.get('HOME', '')})

    def test_the_flip_serves_all_four_in_preview_and_nothing_in_stock(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_preview_boundary
        assert_preview_boundary(self, ROOT, [row['registry_key'] for row in CAPITAL_ROWS])


# ==================================================================================================
# The batch's last row: `ship:imperial:convoy`. The convention is the three siblings' - the cluster
# reaches the binding's own declared box exactly in Z and stands a stated clearance inside it on X and
# Y - and it is *measured* here: the reach numbers are driven out of the seed's own pure function, the
# siblings' relation is read out of their committed sidecars and meshes, and the class scale the
# renderer derives is compared against the live legacy `box` through the renderer's own `ship_mesh`.


def convoy_row():
    rows = _rows_table()
    assert CONVOY_BINDING in rows, 'the batch seed must carry the convoy row as data'
    return rows[CONVOY_BINDING]


def convoy_anchors(row=None):
    """The row's reach numbers, driven out of the seed's pure function rather than text-matched.

    A text match passes on a stale string and says nothing about the cluster the seed authors, so the
    functions are evaluated here - `convoy_anchors` and the two pure helpers it divides its numbers out
    of: the box splitter and the loft's own frame at a Z.
    """
    namespace = _pure_functions('convoy_anchors', 'hull_at', 'CONVOY_CLEARANCE', 'CONVOY_SPINE',
                                'CONVOY_MODULE', 'CONVOY_MODULE_X')
    return namespace['convoy_anchors'](convoy_row() if row is None else row)


def convoy_mesh():
    return load(CONVOY_MESH)


class ConvoySeedContract(unittest.TestCase):
    """The row is one row of the batch's own table, and its cluster is a function of that row."""

    def test_the_row_is_one_row_of_the_batch_table(self):
        row = convoy_row()
        self.assertEqual(row['identifier'], CONVOY_IDENTIFIER)
        self.assertEqual(row['data_id'], CONVOY_DATA_ID)
        self.assertEqual(row['label'], CONVOY_LABEL)
        self.assertEqual(row['legacy_shape'], CONVOY_LEGACY_SHAPE)
        self.assertEqual(tuple(tuple(a) for a in row['limits']), CONVOY_ENVELOPE)
        self.assertEqual(row['ship_kind'], 'convoy')
        self.assertEqual(row['faction'], 'imperial')
        self.assertEqual(row['station_radius'], 32.0)
        text = seed_text()
        self.assertEqual(text.count('def build('), 1, 'one kit, and the batch table drives it')
        self.assertIn("'convoy': build_imperial_convoy", text,
                      'the table has to dispatch this row to its own builder')
        self.assertIn('ROWS[key]', text, 'the build must read the row rather than restate it')

    def test_the_reach_numbers_are_divided_out_of_the_rows_own_declared_box(self):
        anchor = convoy_anchors()
        box = CONVOY_ENVELOPE
        self.assertEqual(anchor['bow'], box[2][1])
        self.assertEqual(anchor['stern'], box[2][0])
        self.assertAlmostEqual(anchor['beam'], box[0][1] - CONVOY_CLEARANCE['beam'], places=9)
        self.assertAlmostEqual(anchor['module'], box[0][1] - CONVOY_CLEARANCE['module'], places=9)
        self.assertAlmostEqual(anchor['keel'], box[1][0] + CONVOY_CLEARANCE['keel'], places=9)
        self.assertAlmostEqual(anchor['mast'], box[1][1] - CONVOY_CLEARANCE['mast'], places=9)
        self.assertLess(anchor['module_x'], anchor['beam'],
                        'the outboard cargo hulls sit inside the beam their own stripes carry')
        for z, _half_width, top, bottom in anchor['spine']:
            self.assertTrue(box[2][0] <= z <= box[2][1], 'a spine frame is stated inside the box')
            self.assertLess(bottom, top)

    def test_the_freight_drums_are_spread_on_the_deck_their_own_host_carries(self):
        """A drum placed from a hand-copied height floats off a tapered deck or sinks into the flank."""
        anchor = convoy_anchors()
        row = convoy_row()
        hull_at = _pure_functions('hull_at')['hull_at']
        half = row['drum_length'] / 2.0
        self.assertEqual(len(anchor['drums']),
                         2 * sum(count for _host, _x, _radius, count in row['drum_rows']),
                         'both sides of every freight row are laid down')
        hosts = {'spine': anchor['spine'], 'module': anchor['hull']}
        for host, x, _radius, count in row['drum_rows']:
            sections = hosts[host]
            placed = [d for d in anchor['drums'] if abs(abs(d[0]) - x) < 1e-12]
            self.assertEqual(len(placed), 2 * count, f'the {host} rows carry {count} drums per side')
            self.assertEqual(len({d[2] for d in placed}), count, 'a drum row sits at its own stations')
            self.assertGreaterEqual(min(d[2] for d in placed), sections[0][0] + half + .8 - 1e-9)
            self.assertLessEqual(max(d[2] for d in placed), sections[-1][0] - half - .8 + 1e-9)
            for _x, y, z, radius in placed:
                self.assertAlmostEqual(y, hull_at(sections, z)[1] + radius * .5, places=9,
                                       msg='the drum is seated on the deck its own host carries')
        for x, y, z, radius in anchor['drums']:
            self.assertTrue(anchor['stern'] <= z <= anchor['bow'], 'a drum is inside the box in Z')
            self.assertLessEqual(abs(x) + radius, anchor['beam'] + 1e-9,
                                 'a drum row carries the beam but does not pass it')
            self.assertLessEqual(y + radius, anchor['mast'] + 1e-9,
                                 'a drum row is clamped under the mast line')

    def test_a_second_convoy_row_would_be_a_row_and_not_a_second_kit(self):
        """Driven with a box that is not this row's: the placement is a function of the row."""
        wider = dict(convoy_row())
        wider['limits'] = [[-24.0, 24.0], [-8.0, 30.0], [-30.0, 30.0]]
        anchor = convoy_anchors(wider)
        self.assertEqual(anchor['bow'], 30.0)
        self.assertEqual(anchor['stern'], -30.0)
        self.assertAlmostEqual(anchor['beam'], 24.0 - CONVOY_CLEARANCE['beam'], places=9)
        self.assertAlmostEqual(anchor['keel'], -8.0 + CONVOY_CLEARANCE['keel'], places=9)
        self.assertAlmostEqual(anchor['mast'], 30.0 - CONVOY_CLEARANCE['mast'], places=9)
        self.assertEqual(len(anchor['drums']), len(convoy_anchors()['drums']))


class ConvoyMeshContract(unittest.TestCase):
    """The authored cluster against the box it declares, and against the crate the row draws today."""

    def test_the_cluster_reaches_the_box_in_z_and_stands_inside_it_on_x_and_y(self):
        lo, hi = convoy_mesh()['bounds']
        anchor = convoy_anchors()
        box = CONVOY_ENVELOPE
        for axis in range(3):
            self.assertGreaterEqual(lo[axis], box[axis][0] - 1e-6)
            self.assertLessEqual(hi[axis], box[axis][1] + 1e-6)
        self.assertAlmostEqual(lo[2], box[2][0], places=6, msg='the stern reaches the box')
        self.assertAlmostEqual(hi[2], box[2][1], places=6, msg='the bow reaches the box')
        self.assertAlmostEqual(hi[0], anchor['beam'], places=6)
        self.assertAlmostEqual(lo[0], -anchor['beam'], places=6)
        self.assertAlmostEqual(lo[1], anchor['keel'], places=6)
        self.assertLessEqual(hi[1], anchor['mast'] + 1e-9)
        self.assertGreater(hi[1], anchor['mast'] - 0.1,
                           'the mast is authored on the mast line and bevelled, not cut short')
        self.assertGreaterEqual(hi[2] - lo[2], CONVOY_MIN_LENGTH)

    def test_the_class_scale_the_renderer_derives_is_unchanged(self):
        """`scale = length / (hi[2] - lo[2])`, so the authored span has to be the legacy span.

        Both sides are measured: the live legacy crate through the renderer's own `ship_mesh`, the
        candidate through the mesh the exporter wrote. Equal spans mean equal class scale, drawn length,
        collision radius and camera framing - which is the whole reason the cluster reaches the box in Z
        exactly and stands inside it on the other two axes.
        """
        legacy_lo, legacy_hi, _points, _triangles = legacy_geometry(CONVOY_LEGACY_SHAPE)
        mesh_lo, mesh_hi = convoy_mesh()['bounds']
        self.assertAlmostEqual(mesh_lo[2], legacy_lo[2], places=5)
        self.assertAlmostEqual(mesh_hi[2], legacy_hi[2], places=5)
        self.assertAlmostEqual(mesh_hi[2] - mesh_lo[2], legacy_hi[2] - legacy_lo[2], places=5,
                               msg='a different Z span would resize every class scale this row is in')

    def test_the_three_siblings_carry_the_same_convention_in_their_own_files(self):
        """Read out of the approved siblings' sidecars and meshes, not restated here."""
        for identifier in CONVOY_SIBLINGS:
            with self.subTest(sibling=identifier):
                name = identifier.replace('_', '-').upper()
                sidecar = load(ROOT / 'art/manifests/pending' / f'S06-{name}.json')
                data = load(ROOT / f'assets/models/{identifier}.mesh.json')
                slo, shi = sidecar['envelope']
                blo, bhi = data['bounds']
                for axis in range(3):
                    self.assertGreaterEqual(blo[axis], slo[axis] - 1e-6)
                    self.assertLessEqual(bhi[axis], shi[axis] + 1e-6)
                self.assertAlmostEqual(blo[2], slo[2], places=6, msg='the stern reaches the box')
                self.assertAlmostEqual(bhi[2], shi[2], places=6, msg='the bow reaches the box')
                for axis in (0, 1):
                    self.assertTrue(blo[axis] > slo[axis] or bhi[axis] < shi[axis],
                                    f'{identifier} stands inside the declared box on axis {axis}')
                self.assertEqual(sidecar['runtime']['triangles'], data['triangle_count'])

    def test_this_rows_sidecar_carries_the_same_relation_as_its_siblings(self):
        doc = load(CONVOY_SIDECAR)
        mesh = convoy_mesh()
        lo = [axis[0] for axis in CONVOY_ENVELOPE]
        hi = [axis[1] for axis in CONVOY_ENVELOPE]
        self.assertEqual(doc['envelope'], [lo, hi])
        self.assertEqual(doc['bounds'], mesh['bounds'])
        self.assertEqual(doc['runtime']['triangles'], mesh['triangle_count'])
        self.assertEqual(doc['runtime']['vertices'], len(mesh['vertices']))
        self.assertEqual(doc['runtime']['roles'], sorted(ROLES))

    def test_the_cluster_is_the_loader_contract_in_the_ship_caps_and_the_convoys_band(self):
        data = convoy_mesh()
        self.assertEqual(data['asset'], CONVOY_IDENTIFIER)
        self.assertEqual(data['coordinates'], 'X beam; Y up; +Z forward')
        self.assertEqual(data['triangle_count'], sum(len(v) for v in data['batches'].values()))
        self.assertGreaterEqual(data['triangle_count'], CONVOY_TARGET[0],
                                'the Imperial reading of the cluster is a capital-ship hull')
        self.assertLessEqual(data['triangle_count'], CONVOY_TARGET[1])
        self.assertGreater(data['triangle_count'], CONVOY_LEGACY_TRIANGLES,
                           'the cluster adds detail over the 1,536-triangle crate it replaces')
        self.assertLessEqual(data['triangle_count'], CAPS['triangles'])
        self.assertLessEqual(len(data['vertices']), CAPS['vertices'])
        self.assertLessEqual(CONVOY_MESH.stat().st_size, CAPS['bytes'])
        for role, rows in data['batches'].items():
            self.assertIn(role, ROLES)
            for row in rows:
                self.assertEqual(len(row), 6)
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in row[:3])), 1.0, places=9)
                for index in row[3:]:
                    self.assertLess(index, len(data['vertices']))

    def test_every_role_carries_real_geometry(self):
        """A later per-role ablation measures pixels changed by removing each role."""
        data = convoy_mesh()
        counts = {role: len(rows) for role, rows in data['batches'].items()}
        self.assertEqual({r for r, n in counts.items() if n}, set(ROLES),
                         'every loader role has to be filled by real geometry')
        for role in ROLES:
            self.assertGreaterEqual(counts[role], ROLE_FLOOR,
                                    f'{role} carries {counts[role]} triangles; the ablation needs a '
                                    f'surface, not a token')

    def test_the_cluster_is_not_the_legacy_crate_restated(self):
        """A count comparison is not enough on its own, so the shapes are fingerprinted.

        The crate is 1,536 triangles and the cluster 4,745, but a restated legacy mesh in a larger batch
        would pass a count. Normalised into its own bounds the cluster has to reduce to a different set.
        """
        data = convoy_mesh()
        self.assertEqual(data['features']['legacy_shape'], CONVOY_LEGACY_SHAPE)
        self.assertEqual(data['features']['ship_kind'], 'convoy')
        self.assertEqual(data['features']['station_radius'], 32.0)
        self.assertEqual(data['features']['authority'], 'script')
        self.assertEqual(data['features']['binding'], CONVOY_BINDING)
        self.assertEqual(data['features']['data_id'], CONVOY_DATA_ID)
        self.assertEqual(data['features']['approval'], 'pending_owner_approval')
        self.assertEqual(data['features']['seed_recipe'].split(';')[0], SEED)
        self.assertEqual(data['features']['legacy_envelope'],
                         [list(axis) for axis in CONVOY_ENVELOPE])
        self.assertIn('no external mesh or texture dependencies', data['features']['provenance'])
        # Measured against the live legacy crate, not against a transcribed vertex list. The corner
        # count is the probe's own convention (`len(set(verts))` over the raw corners, not rounded):
        # four of the crate's corners differ only below the exporter's 5e-6 quantiser.
        lo, hi, points, triangles = legacy_geometry(CONVOY_LEGACY_SHAPE)
        self.assertEqual(triangles, CONVOY_LEGACY_TRIANGLES)
        self.assertEqual(len({tuple(p) for p in points}), CONVOY_LEGACY_VERTICES)
        self.assertNotEqual(authored_fingerprint(dict(mesh=CONVOY_MESH)), fingerprint(points, lo, hi),
                            'a restated legacy hull reduces to the legacy shape set')


class ConvoyWrapperContract(unittest.TestCase):
    def test_the_generator_declares_the_row_and_its_own_wrapper_carries_it(self):
        text = GENERATOR.read_text(encoding='utf-8')
        entry = re.search(r"ASSETS\['imperial_convoy'\] = \((.*?)\)\n", text, re.S)
        self.assertTrue(entry, 'the wrapper table must carry the row')
        block = entry.group(1)
        self.assertIn(CONVOY_LABEL, block)
        self.assertIn('48.9', block)
        for token in ('((-20.0, 20.0), (-7.0, 26.5), (-24.6975, 24.35825))', '11888', '9450',
                      '2_000_000'):
            self.assertIn(token, block, f'the generated entry declares {token}')
        written = CONVOY_WRAPPER.read_text(encoding='utf-8')
        for token in CONVOY_WRAPPER_TOKENS:
            self.assertIn(token, written, token)

    def test_the_row_declares_no_floor_of_its_own(self):
        """The row is above the 1,800 hull floor, so it carries the standard ship caps and no floor."""
        self.assertNotIn('MIN_TRIANGLES =', CONVOY_WRAPPER.read_text(encoding='utf-8'))

    def test_regenerating_the_wrappers_writes_nothing(self):
        """Regenerating must not rewrite any other row's wrapper: an approval hashes it."""
        generator = subprocess.run([str(ROOT / '.venv/bin/python'),
                                    str(ROOT / 'tools/art/gen_export_wrappers.py'), '--check'],
                                   cwd=ROOT, capture_output=True, text=True)
        self.assertIn('0 written', generator.stdout,
                      f'the generator rewrote wrappers: {generator.stdout.strip()}')


class ConvoyNotLanded(unittest.TestCase):
    def test_convoy_manifest_is_bound_to_the_authorized_approved_revision(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [CONVOY_REGISTRY_KEY])

    def test_convoy_has_authorized_registration_and_original_receipt(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [CONVOY_REGISTRY_KEY])

    def test_convoy_registry_row_names_the_approved_revision(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_opt_in_registration
        assert_opt_in_registration(self, ROOT, [CONVOY_REGISTRY_KEY])

    def test_the_sidecar_matches_the_siblings_shape_and_the_decision(self):
        """The three siblings' sidecars *are* approvals; this one is too now, and that difference is
        exactly one key and one status. Which of the two shapes is correct is not a matter of taste: it
        follows the decision that names this row, so the guard reads the decision rather than a date.
        """
        doc = load(CONVOY_SIDECAR)
        sibling = load(ROOT / 'art/manifests/pending/S06-ALLIANCE-CONVOY.json')
        decisions = [d for d in load(ROOT / 'art/manifests/approvals.json')['decision_log']
                     if d.get('approval_kind') == 'appearance-batch-revisions'
                     and any(a.get('gameplay_binding') == CONVOY_REGISTRY_KEY
                             for a in d['revision']['assets'])]
        self.assertEqual(sibling['status'], 'appearance_approved_pending_landing')
        self.assertIn('appearance_decision', sibling)
        self.assertEqual(doc['binding'], CONVOY_REGISTRY_KEY)
        self.assertEqual(doc['canonical_binding'], CONVOY_BINDING)
        self.assertEqual(doc['batch'], 's06-b6-imperial-ships')
        self.assertEqual(doc['gameplay_entity'], CONVOY_DATA_ID)
        self.assertIsNone(doc['owner_decision'])
        self.assertIs(doc['activation'], False)
        if decisions:
            # Approved: the siblings' shape exactly, plus the one key that records the approval.
            self.assertEqual(len(decisions), 1, 'one decision names this row, not two')
            self.assertEqual(list(doc), list(sibling), "the siblings' shape, approval included")
            self.assertEqual(doc['status'], 'appearance_approved_pending_landing')
            self.assertEqual(doc['appearance_decision'], decisions[0]['id'])
        else:
            # Pending: the siblings' shape minus that one key, and nothing else different.
            self.assertEqual(list(doc), [key for key in sibling if key != 'appearance_decision'],
                             "the sidecar is the siblings' shape, minus the approval")
            self.assertEqual(doc['status'], 'authored_pending_owner_appearance_approval')
            self.assertNotIn('appearance_decision', doc)

    def test_the_sidecar_re_derives_from_the_files_on_disk(self):
        """A sidecar that transcribes is a second source of truth; these are re-derived here."""
        doc = load(CONVOY_SIDECAR)
        for key, path in (('source', CONVOY_BLEND), ('initial_seed', ROOT / SEED),
                          ('export_script', CONVOY_WRAPPER), ('runtime', CONVOY_MESH)):
            with self.subTest(field=key):
                payload = Path(path).read_bytes()
                self.assertEqual(doc[key]['sha256'], hashlib.sha256(payload).hexdigest())
                self.assertEqual(doc[key]['bytes'], len(payload))

    def test_the_evidence_is_the_picture_the_owner_is_asked_to_judge(self):
        """The review record points at the capture, and the capture carries its own measurements."""
        doc = load(CONVOY_SIDECAR)
        picture = ROOT / doc['evidence']
        self.assertTrue(picture.exists(), f'{doc["evidence"]} is what this row is reviewed from')
        report = load(picture.parent / 'report.json')
        self.assertEqual(report['row'], CONVOY_BINDING)
        self.assertEqual(report['registry_key'], CONVOY_REGISTRY_KEY)
        self.assertEqual(report['sheet']['image'], picture.name)
        self.assertEqual(report['sheet']['sha256'], hashlib.sha256(picture.read_bytes()).hexdigest())
        self.assertTrue(report['one_camera_per_view'])
        self.assertTrue(report['production_candidate_unselected_after_review'])
        self.assertEqual(report['legacy']['triangles'], CONVOY_LEGACY_TRIANGLES)
        self.assertAlmostEqual(report['drawn_size']['legacy']['scale'],
                               report['drawn_size']['candidate']['scale'], places=9,
                               msg='the class scale is the same on both sides of the flip')
        for view in ('close', 'wide'):
            with self.subTest(view=view):
                entry = report['comparison'][view]
                self.assertGreater(entry['changed_pixels'], 0, 'the pair has to differ')
                self.assertEqual(entry['repeat_changed_pixels'], 0,
                                 'the legacy variant has to be repeatable, or the pair is not one tick')
                self.assertEqual(entry['repeat_max_delta'], 0)
                for variant in ('legacy', 'authored', 'legacy-repeat'):
                    self.assertEqual(report['display']['per_pass'][variant]['samples'], 4,
                                     'every pass is 4x MSAA')
                    shot = report['views'][view][variant]
                    self.assertEqual(shot['framing']['corners_on_screen'], 8)
                    self.assertGreaterEqual(min(shot['framing']['visible_px']), 20)
                    self.assertEqual(shot['state_sha256'], report['initial_state_sha256'],
                                     'every variant of a view is the same tick')
        band = report['sheet']['label_band']
        self.assertTrue(band and all(CONVOY_REGISTRY_KEY in line or 'legacy' in line for line in band))


class ConvoyGate(unittest.TestCase):
    """The row reached through the seam this batch needed, and nothing served without a session.

    `ship_visual_key` is the facade the review capture goes through, and its two convoy branches are the
    only place an Imperial convoy row can name `imperial:convoy` at all - the seam and its own regression
    guard are `tests/test_imperial_convoy_gate.py`, and this class measures it from this row's side.
    """

    def facade(self):
        sys.path.insert(0, str(ROOT))
        import game.core  # noqa: F401  (initialises the data layer the store reads)
        from game.data.store import DataStore
        from render import asset_selection as selection
        from render import faction_visuals as visuals
        return DataStore.get(), selection, visuals

    def test_an_imperial_trade_convoy_row_reaches_this_rows_key(self):
        ds, _selection, visuals = self.facade()
        self.assertEqual(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial'),
                         CONVOY_REGISTRY_KEY)

    def test_an_imperial_crew_transport_with_crew_space_reaches_the_same_key(self):
        ds, _selection, visuals = self.facade()
        data = ds.ships[CONVOY_DATA_ID]
        self.assertEqual(data.category, 'crew_transport')
        self.assertGreater(data.crew_capacity, 0)
        self.assertEqual(visuals.ship_visual_key(ds, CONVOY_DATA_ID), CONVOY_REGISTRY_KEY)

    def test_nothing_at_all_is_served_without_a_preview_session(self):
        """The key is minted in production as well; what is not is a selection, a mesh, or a new hull.

        Measured, not asserted: with no resolver configured the row's binding is not selected, there is
        no mesh for it, and the renderer's own mesh path still hands back the legacy crate - which is
        what the legacy half of the review picture shows.
        """
        ds, selection, visuals = self.facade()
        from render.fleet_geometry import ship_mesh
        selection.configure({})
        self.addCleanup(selection.configure, {})
        self.assertIsNone(selection.ship_binding(ds, 'trade_convoy', 'imperial'))
        self.assertFalse(selection.selected_binding(CONVOY_REGISTRY_KEY))
        self.assertIsNone(selection.mesh_for(CONVOY_REGISTRY_KEY))
        self.assertEqual(visuals.normalize_ship_key(CONVOY_REGISTRY_KEY), CONVOY_LEGACY_SHAPE)
        self.assertEqual(ship_mesh(CONVOY_REGISTRY_KEY), ship_mesh(CONVOY_LEGACY_SHAPE),
                         'with nothing served the row still draws the crate it draws today')

    def test_real_resolver_serves_it_in_preview_and_nothing_in_stock(self):
        """S07 publication preserves the original approval and explicit preview boundary."""
        from s07_registration_assertions import assert_preview_boundary
        assert_preview_boundary(self, ROOT, [CONVOY_REGISTRY_KEY])
