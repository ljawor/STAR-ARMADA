"""Focused S06 B2 batch guards for the pending, unapproved squadron/logistics hulls.

Cheap per-asset guards only: geometry/budget/envelope, export-only source safety, the
seed's refusal to overwrite a master, emitter metadata bound to real geometry, the
measured proof that every drive mouth is clear of its own host loft, and the proof that
nothing pending leaked into a production registry or an approval record.
The deep actual-renderer matrix is a batch-milestone check in
`tools/diag_alliance_batch_review.py`, not a per-hull test.

Two rules in here were paid for on this batch, so they are guards rather than comments:

* a closed loft ends in a flat cap, and a drive mouth placed at or inside that cap is
  invisible from every camera (`test_every_emitter_has_a_clear_aft_ray_and_a_buried_control`);
* `loft`/`plate` carry a bevel modifier, so the evaluated surface stands proud of the
  declared sections - size the extremes against the exported bounds, never the sections
  (`test_authored_mesh_keeps_the_binding_legacy_envelope_and_length`).
"""
import ast
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'art/manifests/pending/S06-BATCH-B2-SQUADRON-LOGISTICS.json'
BATCH = 's06-b2-squadron-logistics'
SEED = 'tools/art/build_b2_batch.py'
# Every binding this module guards, with the loader contract its export must satisfy.
# `envelope` is the binding's legacy extent as `(low, high)` per axis; the spec carries the
# same numbers transposed, and `test_batch_spec_lists_exactly_the_guarded_bindings` compares
# the two so neither can drift alone.
ASSETS = (
    dict(binding='rebel:fighter', identifier='alliance_interceptor',
         label='interceptor', data_id='rebel_x_squadron', class_='fighter_squadron',
         envelope=((-12.0, 12.0), (-3.0, 8.471), (-19.77, 18.0)), min_length=37.7,
         max_triangles=5000, max_vertices=3500, emitters=3,
         keywords=('pressure hull', 'boom', 'dorsal blade', 'canopy glazing', 'boom vent',
                   'boom drive emitter')),
    dict(binding='rebel:bomber', identifier='alliance_bomber',
         label='bomber', data_id='rebel_y_squadron', class_='fighter_squadron',
         envelope=((-16.0, 16.0), (-6.8, 6.55), (-25.37, 23.0)), min_length=48.3,
         max_triangles=5000, max_vertices=3500, emitters=4,
         keywords=('pressure hull', 'payload bay', 'torpedo drum', 'dorsal spine ridge',
                   'belly torpedo louvre', 'hull drive port emitter')),
    dict(binding='rebel:convoy', identifier='alliance_convoy',
         label='colony transport', data_id='rebel_crew_transport', class_='crew_transport',
         envelope=((-31.0, 31.0), (-9.0, 16.0), (-72.698, 59.5)), min_length=132.1,
         max_triangles=10000, max_vertices=7000, emitters=3,
         keywords=('convoy spine', 'bridge pod', 'freight drum', 'keel girder',
                   'convoy stripe', 'centre drive emitter')),
    dict(binding='confederacy:fighter', identifier='legion_vulture',
         label='vulture drone', data_id='confed_vulture_squadron', class_='fighter_squadron',
         envelope=((-12.831, 12.831), (-3.0, 7.6), (-15.07, 19.4)), min_length=34.4,
         max_triangles=5000, max_vertices=3500, emitters=4,
         keywords=('drone thorax', 'upper wing', 'mandible', 'wingtip thruster',
                   'main drive port emitter')),
    dict(binding='confederacy:bomber', identifier='legion_hyena',
         label='hyena strike wing', data_id='confed_bomber_squadron', class_='fighter_squadron',
         envelope=((-17.531, 17.531), (-7.0, 13.0), (-21.65, 26.12)), min_length=47.7,
         max_triangles=5000, max_vertices=3500, emitters=4,
         keywords=('strike thorax', 'mid wing', 'belly launch pod', 'dorsal crest',
                   'main drive port emitter')),
    dict(binding='confederacy:convoy', identifier='legion_convoy',
         label='legion hauler', data_id='confed_crew_transport', class_='crew_transport',
         envelope=((-36.5, 36.5), (-7.0, 29.5), (-65.698, 57.6)), min_length=123.2,
         max_triangles=10000, max_vertices=7000, emitters=4,
         keywords=('hauler spine', 'cargo sail', 'cargo pod', 'keel girder',
                   'sail thruster', 'main drive port emitter')),
    dict(binding='syndicate:fighter', identifier='syndicate_jackal',
         label='jackal raid wing', data_id='syndicate_raid_squadron', class_='fighter_squadron',
         envelope=((-7.892, 8.45), (-4.024, 12.0), (-17.258, 24.5)), min_length=41.7,
         max_triangles=5000, max_vertices=3500, emitters=3,
         keywords=('raider pressure hull', 'ram prow', 'dorsal blade', 'engine pod',
                   'sensor pod', 'centre drive emitter')),
    dict(binding='syndicate:convoy', identifier='syndicate_convoy',
         label='syndicate bulk hauler', data_id='syndicate_crew_transport',
         class_='crew_transport',
         envelope=((-27.786, 42.267), (-9.0, 36.5), (-76.912, 62.04)), min_length=138.9,
         max_triangles=10000, max_vertices=7000, emitters=3,
         keywords=('hauler spine', 'offset superstructure', 'tower crown', 'freight drum',
                   'raider stripe', 'pod drive 0 emitter')),
)
# Bindings this batch deliberately does not author: all four resolve to the shared legacy
# generic shapes, so modelling them is a shared-source change for the owner to scope.
OMITTED = ('imperial:fighter', 'imperial:bomber', 'imperial:convoy', 'imperial:supercapital')


def asset_mesh(asset):
    return ROOT / f"assets/models/{asset['identifier']}.mesh.json"


def load(asset, path=None):
    from render.authored_mesh import _load_profile
    return _load_profile(path or asset_mesh(asset), asset['identifier'], asset['envelope'],
                         asset['min_length'])


def legacy_span(asset):
    """The legacy procedural Z extent the authored mesh must keep, without a DataStore."""
    from render import asset_selection
    from render.faction_ships import _ship_mesh
    from render.faction_visuals import normalize_ship_key
    assert asset_selection.mesh_for(asset['binding']) is None, (
        f"{asset['binding']} must not be selectable in production")
    faction, role = normalize_ship_key(asset['binding']).split(':')
    points = [p for mesh in _ship_mesh(faction, role).values() for _, tri in mesh for p in tri]
    return min(p[2] for p in points), max(p[2] for p in points)


def is_emitter(part):
    """An emitter disc's part name, with Blender's `.001` duplicate suffix stripped."""
    return re.sub(r'\.\d+$', '', part['name'].lower()).endswith('emitter')


def emitter_spans(asset):
    """Exported emitter part spans, resolved through the asset's own parts table."""
    payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
    offsets = {role: 0 for role in payload['batches']}
    for part in payload['parts']:
        role = part['role']
        start = offsets[role]
        end = start + part['triangles']
        offsets[role] = end
        if not is_emitter(part):
            continue
        assert role == 'cool', part
        assert part['triangles'] > 0, 'an emitter part with no geometry is not an emitter'
        yield part, payload['batches'][role][start:end]


def measured_emitters(asset):
    """Each emitter's measured centre, radius and aft face, straight off the export."""
    payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
    for part, triangles in emitter_spans(asset):
        points = [payload['vertices'][i] for tri in triangles for i in tri[3:]]
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        yield part['name'], [(a + b) / 2 for a, b in zip(lo, hi)], \
            min(hi[0] - lo[0], hi[1] - lo[1]) / 2, lo[2]


def assert_emitter_centers_match_export(test, asset):
    payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
    centers = payload['features']['emitter_centers']
    test.assertEqual(len(centers), len({tuple(c) for c in centers}),
                     'emitter centers must be distinct')
    test.assertTrue(centers, 'the drive contract needs declared emitter centers')
    measured = [centre for _n, centre, _r, _z in measured_emitters(asset)]
    test.assertEqual(len(measured), len(centers), 'declared emitter centers must be exported')
    for declared, actual in zip(sorted(centers), sorted(measured)):
        for a, b in zip(declared, actual):
            test.assertAlmostEqual(a, b, places=5)


def obstruction_tester(asset, direction):
    """Ray/mesh occlusion along `direction`, over the opaque roles (emitters are 'cool').

    The pair of these is the guard: the disc sees aft (-Z) and is enclosed fore (+Z). A
    disc that is not visible from aft fails the first, and an emitter floating clear of its
    host body fails the second, so neither can pass vacuously.
    """
    import numpy as np
    mesh = load(asset)
    triangles = np.array([tri for role in ('base', 'dark', 'trim', 'accent')
                          for _, tri in mesh[role]])
    a = triangles[:, 0]
    e1 = triangles[:, 1] - a
    e2 = triangles[:, 2] - a
    direction = np.array(direction, dtype=float)
    p = np.cross(direction, e2)
    det = np.einsum('ij,ij->i', e1, p)
    inv = np.divide(1., det, out=np.zeros_like(det), where=abs(det) > 1e-9)

    def obstructed(origin):
        t = np.array(origin) - a
        u = np.einsum('ij,ij->i', t, p) * inv
        q = np.cross(t, e1)
        v = np.einsum('j,ij->i', direction, q) * inv
        distance = np.einsum('ij,ij->i', e2, q) * inv
        return bool(np.any((abs(det) > 1e-9) & (u >= 0) & (v >= 0) & (u + v <= 1)
                            & (distance > 1e-5)))

    return obstructed


class GeometryContract(unittest.TestCase):
    def test_each_pending_asset_satisfies_the_loader_contract(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                path = asset_mesh(asset)
                self.assertTrue(path.is_file(), f'{path.name} has not been authored')
                mesh = load(asset)
                self.assertEqual(set(mesh), {'base', 'dark', 'trim', 'accent', 'lit', 'cool'})
                payload = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(payload['schema'], 1)
                self.assertEqual(payload['asset'], asset['identifier'])
                self.assertLessEqual(payload['triangle_count'], asset['max_triangles'])
                self.assertLessEqual(len(payload['vertices']), asset['max_vertices'])
                self.assertLess(path.stat().st_size, 2_000_000)
                self.assertEqual(sum(p['triangles'] for p in payload['parts']),
                                 payload['triangle_count'])
                self.assertEqual(payload['features']['authority'], 'blend')
                self.assertEqual(payload['features']['approval'], 'pending_owner_approval')
                self.assertEqual(payload['features']['data_id'], asset['data_id'])

    def test_authored_mesh_keeps_the_binding_legacy_envelope_and_length(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                lo, hi = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))['bounds']
                for axis, (low, high) in enumerate(asset['envelope']):
                    self.assertGreaterEqual(lo[axis], low - 1e-6)
                    self.assertLessEqual(hi[axis], high + 1e-6)
                legacy_lo, legacy_hi = legacy_span(asset)
                span = hi[2] - lo[2]
                # ship_size derives scale = drawn length / authored Z span, so a mesh that
                # does not fill the legacy extent would silently change the drawn length.
                self.assertLess(abs(span - (legacy_hi - legacy_lo)), (legacy_hi - legacy_lo) * .01,
                                asset['binding'])

    def test_every_declared_feature_is_a_real_named_part(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                parts = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))['parts']
                names = ' '.join(p['name'].lower() for p in parts)
                for keyword in asset['keywords']:
                    self.assertIn(keyword, names, keyword)

    def test_emitter_centers_correspond_to_exported_emitter_geometry(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                assert_emitter_centers_match_export(self, asset)

    def test_emitter_contract_rejects_vacuous_or_unlinked_metadata(self):
        for asset in ASSETS:
            payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
            for defect in ('empty', 'duplicate', 'moved', 'missing_part', 'empty_geometry'):
                bad = copy.deepcopy(payload)
                if defect == 'empty':
                    bad['features']['emitter_centers'] = []
                if defect == 'duplicate':
                    bad['features']['emitter_centers'][0] = bad['features']['emitter_centers'][1]
                if defect == 'moved':
                    bad['features']['emitter_centers'][0][0] += 10
                emitter = next(p for p in bad['parts']
                               if p['name'].lower().endswith('emitter'))
                if defect == 'missing_part':
                    bad['parts'].remove(emitter)
                if defect == 'empty_geometry':
                    emitter['triangles'] = 0
                with self.subTest(binding=asset['binding'], defect=defect):
                    with patch.object(Path, 'read_text', return_value=json.dumps(bad)):
                        with self.assertRaises(AssertionError):
                            assert_emitter_centers_match_export(self, asset)

    def test_every_emitter_sees_aft_and_is_enclosed_by_its_host(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                aft = obstruction_tester(asset, (0., 0., -1.))
                fore = obstruction_tester(asset, (0., 0., 1.))
                emitters = list(measured_emitters(asset))
                self.assertEqual(len(emitters), asset['emitters'])
                for name, (x, y, z), radius, face_z in emitters:
                    with self.subTest(binding=asset['binding'], emitter=name):
                        self.assertGreater(radius, .5, 'a drive aperture too small to read')
                        # Nothing may stand between the disc and a viewer aft of the hull:
                        # a host loft, a crossbeam or a capped bell ending flush with the
                        # mouth covers these, and the disc then renders as a plugged socket.
                        step = radius * .5
                        for dx, dy in ((0, 0), (-step, 0), (step, 0), (0, -step), (0, step)):
                            self.assertFalse(aft((x + dx, y + dy, face_z - .01)),
                                             f'{name} is occluded from aft at {(dx, dy)}')
                        # ...and the mouth is a mouth, not an emitter floating in space.
                        self.assertTrue(fore((x, y, z)),
                                        f'{name} is not enclosed by a host body fore of it')

    def test_corruption_is_rejected_by_production_loader(self):
        evidence = ROOT / 'artifacts/s06_alliance_batch_review'
        evidence.mkdir(parents=True, exist_ok=True)
        for asset in ASSETS:
            original = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory(dir=evidence) as tmp:
                for defect in ('normal', 'index', 'winding', 'bounds', 'count'):
                    data = copy.deepcopy(original)
                    if defect == 'normal':
                        data['batches']['base'][0][0] = 9
                    if defect == 'index':
                        data['batches']['base'][0][3] = 999999
                    if defect == 'winding':
                        data['batches']['base'][0][3:] = list(reversed(data['batches']['base'][0][3:]))
                    if defect == 'bounds':
                        data['vertices'][0][0] = asset['envelope'][0][0] - .1
                    if defect == 'count':
                        data['triangle_count'] += 1
                    target = Path(tmp) / 'bad.mesh.json'
                    target.write_text(json.dumps(data), encoding='utf-8')
                    with self.subTest(binding=asset['binding'], defect=defect):
                        with self.assertRaises(ValueError):
                            load(asset, target)


class SourceSafety(unittest.TestCase):
    def load_exporter(self, asset, output, blend):
        spec = importlib.util.spec_from_file_location('export_' + asset['identifier'],
                                                      ROOT / f"tools/art/export_{asset['identifier']}.py")
        exporter = importlib.util.module_from_spec(spec)
        stub = SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(
            open_mainfile=Mock(side_effect=RuntimeError('master opened before refusal')))))
        with patch.dict(sys.modules, {'bpy': stub}):
            spec.loader.exec_module(exporter)
            with patch.object(sys, 'argv', ['exporter', '--', '--blend', str(blend),
                                           '--output', str(output)]):
                with self.assertRaisesRegex(ValueError, 'master|source|input'):
                    exporter.main()
        return stub.ops.wm.open_mainfile

    def test_export_refuses_every_master_alias_before_open(self):
        for asset in ASSETS:
            for alias in ('same', 'relative', 'symlink', 'hardlink'):
                with self.subTest(binding=asset['binding'], alias=alias), \
                        tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    master = root / 'master.blend'
                    master.write_bytes(b'protected master')
                    output = master
                    if alias == 'relative':
                        (root / 'child').mkdir()
                        output = root / 'child/../master.blend'
                    elif alias == 'symlink':
                        output = root / 'alias.blend'
                        output.symlink_to(master)
                    elif alias == 'hardlink':
                        output = root / 'alias.blend'
                        os.link(master, output)
                    opened = self.load_exporter(asset, output, master)
                    opened.assert_not_called()
                    self.assertEqual(master.read_bytes(), b'protected master')
                    self.assertEqual(output.read_bytes(), b'protected master')

    def test_exporters_open_the_declared_master_and_never_save_it(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                exporter = ROOT / f"tools/art/export_{asset['identifier']}.py"
                text = exporter.read_text(encoding='utf-8')
                tree = ast.parse(text)
                self.assertIn('open_mainfile', text)
                self.assertFalse(any(isinstance(n, ast.Attribute)
                                     and n.attr in ('save_as_mainfile', 'save_mainfile')
                                     for n in ast.walk(tree)))
                self.assertTrue((ROOT / f"art/blender/{asset['identifier']}.blend").is_file())
                payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
                self.assertEqual(payload['features']['authority'], 'blend')

    def test_the_batch_seed_refuses_to_overwrite_an_existing_master(self):
        """The eight masters come from one seed, so one refusal guards all of them."""
        masters = [ROOT / f"art/blender/{a['identifier']}.blend" for a in ASSETS]
        for master in masters:
            self.assertTrue(master.is_file(), 'the editable master must be committed')
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn('--replace-seed', text)
        spec = importlib.util.spec_from_file_location('seed_b2_batch', ROOT / SEED)
        module = importlib.util.module_from_spec(spec)
        # The refusal sits above the Blender import, so this runs with no Blender runtime.
        with self.assertRaisesRegex(RuntimeError, 'replace-seed|master'):
            with patch.object(sys, 'argv', ['seed']):
                spec.loader.exec_module(module)
        for master in masters:
            self.assertGreater(master.stat().st_size, 0, 'a refusal must not truncate a master')

    def test_the_generated_export_wrappers_match_their_template(self):
        """One template renders all eight wrappers; a hand edit would drift silently."""
        script = ROOT / 'tools/art/gen_export_wrappers.py'
        self.assertTrue((ROOT / 'tools/art/templates/export_wrapper.tmpl').is_file())
        check = subprocess.run([sys.executable, str(script), '--check'], cwd=ROOT,
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        for asset in ASSETS:
            wrapper = ROOT / f"tools/art/export_{asset['identifier']}.py"
            self.assertTrue(wrapper.is_file(), wrapper.name)


class PendingRecords(unittest.TestCase):
    def batch_spec(self):
        return json.loads(SPEC.read_text(encoding='utf-8'))

    def test_batch_spec_lists_exactly_the_guarded_bindings(self):
        spec = self.batch_spec()
        self.assertEqual(spec['batch'], BATCH)
        self.assertEqual([a['binding'] for a in spec['assets']],
                         [a['binding'] for a in ASSETS])
        self.assertEqual(spec['status'], 'pending_owner_appearance_approval')
        self.assertIn('not an approval record', spec['note'])
        rows = {a['binding']: a for a in spec['assets']}
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                row = rows[asset['binding']]
                self.assertEqual(row['identifier'], asset['identifier'])
                self.assertEqual(row['data_id'], asset['data_id'])
                self.assertEqual(row['class'], asset['class_'])
                self.assertEqual(row['mesh'], f"assets/models/{asset['identifier']}.mesh.json")
                self.assertEqual(tuple(zip(*row['envelope'])), asset['envelope'])
                self.assertAlmostEqual(row['min_length'], asset['min_length'], places=1)

    def test_the_omitted_imperial_rows_are_named_by_the_spec(self):
        """A silent omission reads as an oversight; the spec must say why it is absent."""
        spec = self.batch_spec()
        bindings = {a['binding'] for a in spec['assets']}
        for binding in OMITTED:
            self.assertNotIn(binding, bindings)
        self.assertIn('imperial', spec['note'])
        self.assertIn('shared legacy generic shapes', spec['note'])
        self.assertIn('trade_convoy', spec['note'])

    def test_no_pending_binding_is_registered_anywhere_in_production(self):
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
        status = {b['binding']: b['status'] for b in registry['bindings']}
        pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text(encoding='utf-8'))
        registered = {a['binding']: a for a in pipeline['assets']}
        approvals = json.dumps(json.loads((ROOT / 'art/manifests/approvals.json')
                                          .read_text(encoding='utf-8')))
        manifests = sorted(p.name for p in (ROOT / 'assets/models/manifests').glob('*.json'))
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertEqual(status[asset['binding']], 'procedural_legacy',
                                 'a pending specimen must not be selectable')
                self.assertNotIn(asset['binding'], registered)
                self.assertNotIn(asset['identifier'], approvals)
                self.assertNotIn(asset['binding'], approvals)
        self.assertEqual(manifests, ['alliance_battleship.json', 'alliance_frigate.json',
                                     'alliance_shipyard.json'],
                         'the approved runtime manifests are the only registered ones')

    def test_the_batch_sheet_is_labelled_unreviewed(self):
        text = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn('UNAPPROVED REVIEW ONLY', text)
        self.assertIn('pending_owner_approval', text)


if __name__ == '__main__':
    unittest.main()
