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
  unlanded: no `art/manifests/pipeline.json` entry, no approval, no approval receipt, no activation.

Run:  PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b6_imperial_ships
"""

import ast
import hashlib
import json
import math
import os
import re
import subprocess
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
    def test_no_manifest_exists_yet_because_a_manifest_is_the_landing_artifact(self):
        """A manifest for this row would be a landing, not a review: the mesh stands alone.

        Measured, and it cost five red guards to be sure of: the shared
        `test_no_pending_binding_is_registered_anywhere_in_production` guard reads the *set of manifest
        documents on disk* as the set of registered assets, and it is right to. The B5 precedent is the
        same - a pending row carries its mesh and no manifest - and a reviewer is shown the candidate by
        the batch review harness patching selection, never by writing a manifest early.
        """
        self.assertFalse(MANIFEST.exists(),
                         'a pending row may not carry a manifest: the manifest is the landing artifact')
        payload = json.loads(MESH.read_text(encoding='utf-8'))
        self.assertTrue(payload['asset'] == IDENTIFIER)
    def test_the_landing_manifest_would_carry_no_approval_of_its_own(self):
        """A manifest for this row would be a landing, not a review: the mesh stands alone.

        Measured, and it cost five red guards to be sure of: the shared
        `test_no_pending_binding_is_registered_anywhere_in_production` guard reads the *set of manifest
        documents on disk* as the set of registered assets, and it is right to. The B5 precedent is the
        same - a pending row carries its mesh and no manifest - and a reviewer is shown the candidate by
        the batch review harness patching selection, never by writing a manifest early.
        """
        self.assertFalse(MANIFEST.exists(),
                         'a pending row may not carry a manifest: the manifest is the landing artifact')
        payload = json.loads(MESH.read_text(encoding='utf-8'))
        self.assertTrue(payload['asset'] == IDENTIFIER)
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
        """The batch's acceptance test, run: stock keeps the legacy hull, a review session is served.

        The same technique the batch review harness uses - a preview session plus a patched selection -
        because registering the row to show a reviewer is exactly what "approval is not landing" means
        not to do.
        """
        probe = subprocess.run([str(ROOT / '.venv/bin/python'),
                                str(ROOT / 'tools/art/probe_b6_servability.py'), REGISTRY_KEY],
                               cwd=ROOT, capture_output=True, text=True,
                               env={'PYTHONPATH': 'tests', 'PATH': os.environ.get('PATH', ''),
                                    'HOME': os.environ.get('HOME', '')})
        self.assertIn('SERVING_OK', probe.stdout,
                      f'{probe.stdout.strip()} / {probe.stderr.strip()[-300:]}')
        self.assertEqual(probe.returncode, 0, 'the probe refuses a proof that did not happen')
        self.assertIn("stock      -> 'box'", probe.stdout)
        self.assertIn("review     -> 'imperial:corvette'", probe.stdout)
    def test_the_probe_measures_the_serving_it_claims(self):
        """A probe that describes a session without configuring one proves nothing."""
        text = (ROOT / 'tools/art/probe_b6_servability.py').read_text(encoding='utf-8')
        self.assertIn("sel.configure({'model_preview': True}, asset_root=str(ROOT))", text)
        self.assertIn('sel.selected_binding = lambda', text,
                      'the candidate is served by a reviewed patch, never by registration')
class NotLanded(unittest.TestCase):
    def test_the_row_is_absent_from_the_production_pipeline_and_from_every_approval(self):
        pipeline = load(ROOT / 'art/manifests/pipeline.json')
        approvals = json.dumps([e for e in load(ROOT / 'art/manifests/approvals.json')
                                ['approved_assets'] if isinstance(e, dict)])
        receipts = load(ROOT / 'assets/models/approval-receipts.json')['receipts']
        self.assertNotIn(REGISTRY_KEY, {a['binding'] for a in pipeline['assets']})
        self.assertNotIn(SHIP_BINDING, approvals)
        self.assertNotIn(IDENTIFIER, approvals)
        self.assertNotIn(ASSET_ID, receipts)
        for sidecar in (ROOT / 'art/manifests/pending').glob(f'S06-{IDENTIFIER.upper()}.json'):
            self.fail(f'{sidecar.name} claims a landing record for an unapproved row')

    def test_the_registry_row_is_what_the_flip_needs_and_carries_no_decision(self):
        """The row is *declared*, not registered: the manifest id is there, the decision is not.

        Measured, and it cost a red run to be sure of: an authored status on this row is what makes a
        preview session serve it at all, and it is also what the five
        `test_no_pending_binding_is_registered_anywhere_in_production` guards refuse. Registration is
        therefore the review harness's patch, not a registry edit, and this row stays pending.
        """
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
        row = next(b for b in registry['bindings'] if b['binding'] == REGISTRY_KEY)
        self.assertEqual(row['manifest'], 'core:imperial/corvette')
        self.assertIn(row.get('status'), ('procedural_legacy', 'authoring_pending'),
                      'a pending row must not carry an authored status: that is registration')
        for key in ('approval', 'owner_decision', 'envelope_decision', 'appearance_decision'):
            self.assertNotIn(key, row)
        pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text())
        self.assertNotIn(REGISTRY_KEY, {a['binding'] for a in pipeline['assets']})
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
