"""Focused S06 B1 batch guards for the pending, unapproved Alliance combat hulls.

Cheap per-asset guards only: geometry/budget/envelope, export-only source safety, the
seed's refusal to overwrite a master, emitter metadata bound to real geometry, and the
proof that nothing pending leaked into a production registry or an approval record.
The deep actual-renderer matrix is a batch-milestone check in
`tools/diag_alliance_batch_review.py`, not a per-hull test.
"""
import ast
import copy
import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'art/manifests/pending/S06-BATCH-B1-ALLIANCE-COMBAT.json'
BATCH = 's06-b1-alliance-combat'
# Every binding this module guards, with the loader contract its export must satisfy.
ASSETS = (
    dict(binding='rebel:corvette', identifier='alliance_corvette', data_id='rebel_corvette',
         exporter='tools/art/export_alliance_corvette.py', seed='tools/art/build_alliance_corvette.py',
         envelope=((-21.9, 21.9), (-6.0, 15.3), (-46.46, 45.0)), min_length=91.4,
         max_triangles=8000, max_vertices=6000,
         keywords=('bridge', 'keel', 'machinery', 'vent', 'armor', 'window', 'emitter', 'recognition'),
         blocked_probe_offset=10.),
    dict(binding='rebel:supercapital', identifier='alliance_carrier', data_id='rebel_supercapital',
         exporter='tools/art/export_alliance_carrier.py', seed='tools/art/build_alliance_carrier.py',
         envelope=((-146.51, 146.51), (-30.5, 57.0), (-204.8, 190.0)), min_length=394.0,
         max_triangles=11888, max_vertices=9450,
         keywords=('deck', 'island', 'hangar', 'machinery', 'vent', 'armor', 'keel', 'bridge',
                   'window', 'emitter', 'recognition'),
         blocked_probe_offset=10.),
)


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


def emitter_spans(asset):
    """Exported emitter part spans, resolved through the asset's own parts table."""
    payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
    offsets = {role: 0 for role in payload['batches']}
    for part in payload['parts']:
        role = part['role']
        start = offsets[role]
        end = start + part['triangles']
        offsets[role] = end
        if 'Recessed cyan emitter' not in part['name']:
            continue
        assert role == 'cool', part
        assert part['triangles'] > 0, 'an emitter part with no geometry is not an emitter'
        yield part, payload['batches'][role][start:end]


def assert_emitter_centers_match_export(test, asset):
    payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
    centers = payload['features']['emitter_centers']
    test.assertEqual(len(centers), len({tuple(c) for c in centers}),
                     'emitter centers must be distinct')
    test.assertTrue(centers, 'the drive contract needs declared emitter centers')
    measured = []
    for _part, triangles in emitter_spans(asset):
        points = [payload['vertices'][i] for tri in triangles for i in tri[3:]]
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        measured.append([(a + b) / 2 for a, b in zip(lo, hi)])
    test.assertEqual(len(measured), len(centers), 'declared emitter centers must be exported')
    for declared, actual in zip(sorted(centers), sorted(measured)):
        for a, b in zip(declared, actual):
            test.assertAlmostEqual(a, b, places=5)


def floating_parts(payload, tolerance=.25):
    """Groups of welded parts that stand clear of every other group, with their daylight.

    The exporter indexes vertices by quantised position, so parts that touch share vertices and
    fall into one group; a group that is nowhere near another one is a part - or a cluster of
    parts - floating in space. The S06 batch shipped a sensor-station dish 23.75 units clear of
    its body and a marker-light ring 1.4 units above the deck of every station, and both read as
    detached hardware in their own captures. This measures that without opening Blender, which
    is what lets it be a gate instead of a habit.
    """
    parent = {}

    def find(index):
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    for role in payload['batches'].values():
        for triangle in role:
            for a, b in ((triangle[3], triangle[4]), (triangle[4], triangle[5])):
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    groups = {}
    for index in list(parent):
        groups.setdefault(find(index), []).append(index)
    entries = []
    for members in groups.values():
        points = [payload['vertices'][i] for i in members]
        entries.append((len(members),
                        [min(p[i] for p in points) for i in range(3)],
                        [max(p[i] for p in points) for i in range(3)]))
    floating = []
    for index, (count, lo, hi) in enumerate(entries):
        nearest = min((max(max(lo[k] - other_hi[k], other_lo[k] - hi[k]) for k in range(3))
                       for other, (_, other_lo, other_hi) in enumerate(entries) if other != index),
                      default=0.0)
        if nearest > tolerance:
            floating.append((round(nearest, 2), count,
                             [round((lo[k] + hi[k]) / 2, 2) for k in range(3)]))
    return floating


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
                emitter = next(p for p in bad['parts'] if 'Recessed cyan emitter' in p['name'])
                if defect == 'missing_part':
                    bad['parts'].remove(emitter)
                if defect == 'empty_geometry':
                    emitter['triangles'] = 0
                with self.subTest(binding=asset['binding'], defect=defect):
                    with patch.object(Path, 'read_text', return_value=json.dumps(bad)):
                        with self.assertRaises(AssertionError):
                            assert_emitter_centers_match_export(self, asset)

    def test_every_emitter_has_a_clear_aft_ray_and_a_buried_control(self):
        import numpy as np
        for asset in ASSETS:
            payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
            mesh = load(asset)
            triangles = np.array([tri for role in ('base', 'dark', 'trim', 'accent')
                                  for _, tri in mesh[role]])
            a = triangles[:, 0]
            e1 = triangles[:, 1] - a
            e2 = triangles[:, 2] - a
            direction = np.array([0., 0., -1.])
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

            assert_emitter_centers_match_export(self, asset)
            for x, y, z in payload['features']['emitter_centers']:
                with self.subTest(binding=asset['binding'], emitter=(x, y, z)):
                    for dx, dy in ((0, 0), (-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5)):
                        self.assertFalse(obstructed((x + dx, y + dy, z - .13)), (dx, dy))
                    # Discriminating buried control: the solid casing sits fore of the disc.
                    self.assertTrue(obstructed((x, y, z + asset['blocked_probe_offset'])))

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
                                                      ROOT / asset['exporter'])
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
                text = (ROOT / asset['exporter']).read_text(encoding='utf-8')
                tree = ast.parse(text)
                self.assertIn('open_mainfile', text)
                self.assertFalse(any(isinstance(n, ast.Attribute)
                                     and n.attr in ('save_as_mainfile', 'save_mainfile')
                                     for n in ast.walk(tree)))
                self.assertTrue((ROOT / f"art/blender/{asset['identifier']}.blend").is_file())
                payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
                self.assertEqual(payload['features']['authority'], 'blend')

    def test_initial_seed_refuses_to_overwrite_the_existing_master(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                master = ROOT / f"art/blender/{asset['identifier']}.blend"
                self.assertTrue(master.is_file(), 'the editable master must be committed')
                spec = importlib.util.spec_from_file_location('seed_' + asset['identifier'],
                                                             ROOT / asset['seed'])
                module = importlib.util.module_from_spec(spec)
                with self.assertRaisesRegex(RuntimeError, 'replace-seed|master'):
                    spec.loader.exec_module(module)
                self.assertIn('--replace-seed', (ROOT / asset['seed']).read_text(encoding='utf-8'))


class PendingRecords(unittest.TestCase):
    def batch_spec(self):
        return json.loads(SPEC.read_text(encoding='utf-8'))

    def test_batch_spec_lists_exactly_the_guarded_bindings(self):
        spec = self.batch_spec()
        self.assertEqual(spec['batch'], BATCH)
        self.assertEqual({a['binding'] for a in spec['assets']},
                         {a['binding'] for a in ASSETS})
        self.assertEqual(spec['status'], 'pending_owner_appearance_approval')
        self.assertIn('not an approval record', spec['note'])

    def test_no_pending_binding_is_registered_anywhere_in_production(self):
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
        status = {b['binding']: b['status'] for b in registry['bindings']}
        pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text(encoding='utf-8'))
        registered = {a['binding']: a for a in pipeline['assets']}
        approvals = json.loads((ROOT / 'art/manifests/approvals.json').read_text(encoding='utf-8'))
        approved = json.dumps(approvals)
        manifests = sorted(p.name for p in (ROOT / 'assets/models/manifests').glob('*.json'))
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertEqual(status[asset['binding']], 'procedural_legacy',
                                 'a pending specimen must not be selectable')
                self.assertNotIn(asset['binding'], registered)
                self.assertNotIn(asset['identifier'], approved)
                self.assertNotIn(asset['binding'], approved)
        self.assertEqual(manifests, ['alliance_battleship.json', 'alliance_frigate.json',
                                     'alliance_shipyard.json'],
                         'the approved runtime manifests are the only registered ones')

    def test_the_batch_sheet_is_labelled_unreviewed(self):
        text = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn('UNAPPROVED REVIEW ONLY', text)
        self.assertIn('pending_owner_approval', (ROOT / 'tools/diag_alliance_batch_review.py')
                      .read_text(encoding='utf-8'))

    def test_no_part_of_either_hull_floats_clear_of_the_rest(self):
        """A hull is one piece of hardware, not a constellation.

        The carrier first shipped 38 parts standing clear of everything else and the corvette 4,
        because a kit is authored by centre and by reach and contact is not implied. The seeds
        weld the scene; this measures the exported meshes.
        """
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = json.loads(asset_mesh(asset).read_text(encoding='utf-8'))
                floating = floating_parts(payload)
                self.assertEqual(
                    floating, [],
                    f"{asset['identifier']} carries parts floating clear of their neighbours: "
                    f"{floating}")

    def test_both_ship_seeds_weld_the_scene_before_they_declare_the_asset(self):
        """The order is the guarantee: a joint made after the export is an unmeasured one."""
        for name in ('build_alliance_corvette.py', 'build_alliance_carrier.py'):
            seed = (ROOT / 'tools/art' / name).read_text(encoding='utf-8')
            self.assertIn('weld_scene()', seed)
            self.assertLess(seed.index('weld_scene()'), seed.index('features=dict('),
                            f'{name} welds after it declares the asset features')

    def test_every_evidence_path_the_sheet_points_at_exists(self):
        """A pointer to a file that is not there is worse than no pointer.

        The sheet is what the owner opens to judge the specimens, so every path in its
        `evidence` block is resolved here. This batch had the defect: the corvette row claimed
        `corvette-after-motion.mp4` while the only run had been given `--motion rebel:supercapital`,
        so the file was never written; the harness now takes every claimed row as a comma
        separated list, and the claim is checked rather than trusted.
        """
        spec = self.batch_spec()
        evidence = spec['evidence']
        self.assertEqual({row['binding'] for row in spec['assets']}, set(evidence),
                         'every row needs an evidence entry of its own')
        clips = [b for b, entry in evidence.items() if 'motion' in entry]
        self.assertEqual(clips, ['rebel:corvette', 'rebel:supercapital'],
                         'both B1 specimens claim a paired clip, so both must be produced')
        for binding, entry in evidence.items():
            for kind, value in entry.items():
                for path in ([value] if isinstance(value, str) else value):
                    with self.subTest(binding=binding, kind=kind, path=path):
                        self.assertTrue((ROOT / path).is_file(), f'missing evidence file: {path}')


if __name__ == '__main__':
    unittest.main()
