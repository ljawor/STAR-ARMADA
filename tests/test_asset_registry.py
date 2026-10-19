"""GL-free runtime asset contract; fixtures never write approved mesh files."""
import json
import hashlib
import math
from pathlib import Path
import unittest
import shutil
import tempfile


def isolated_assets(case):
    tmp = tempfile.TemporaryDirectory(prefix='s04-registry-', dir=ROOT.parent)
    case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    shutil.copytree(ROOT / 'assets/models', root / 'assets/models')
    return root


def save_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def edit_manifest(root, name, edit):
    path = root / f'assets/models/manifests/alliance_{name}.json'
    data = json.loads(path.read_text())
    edit(data)
    save_json(path, data)


ROOT = Path(__file__).resolve().parents[1]


class CoreResolutionTests(unittest.TestCase):
    def test_approved_mesh_matches_legacy_structure_and_bytes(self):
        from render.asset_registry import AssetResolver
        from render.authored_mesh import load_frigate
        resolved = AssetResolver(ROOT).resolve('rebel:frigate')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.mesh, load_frigate(ROOT / 'assets/models/alliance_frigate.mesh.json'))
        example = json.loads((ROOT / 'art/schemas/examples/manifests/alliance_frigate.json').read_text())
        self.assertEqual(resolved.revision, example['revision'])
        self.assertEqual(resolved.asset, example['asset'])
        self.assertEqual(resolved.material_profile, 'core:fleet/standard')
        self.assertEqual(resolved.source, 'core')
        with self.assertRaises(TypeError):
            resolved.mesh['base'] = ()
        with self.assertRaises(AttributeError):
            resolved.revision = 'changed'

    def test_core_hash_failure_is_loud_fallback_not_coverage(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        path = root / 'assets/models/alliance_frigate.mesh.json'
        path.write_bytes(path.read_bytes().replace(b'0.0', b'0.1', 1))
        resolver = AssetResolver(root)
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_FILE_HASH')
        report = resolver.coverage()
        self.assertFalse(report['ok'])
        self.assertEqual(report['required_core_failures'], ('rebel:frigate',))
        self.assertNotIn('imperial:battleship', report['required_core_failures'])

    def test_invalid_manifest_metadata_refuses_core_with_specific_codes(self):
        from render.asset_registry import AssetResolver
        cases = [
            ('contract', lambda d: d.update(contract_major=2), 'E_UNKNOWN_CONTRACT'),
            ('bool_major', lambda d: d.update(contract_major=True), 'E_UNKNOWN_CONTRACT'),
            ('extra', lambda d: d.update(shader='execute'), 'E_SCHEMA'),
            ('revision', lambda d: d.update(revision='0' * 64), 'E_REVISION_MISMATCH'),
            ('size', lambda d: d['files']['mesh'].update(bytes=1), 'E_FILE_SIZE'),
            ('traversal', lambda d: d['files']['mesh'].update(path='../escape'), 'E_UNSAFE_PATH'),
            ('absolute', lambda d: d['files']['mesh'].update(path='/etc/passwd'), 'E_UNSAFE_PATH'),
            ('bounds', lambda d: d['bounds']['min'].__setitem__(0, 999), 'E_BOUNDS_DEGENERATE'),
            ('approval', lambda d: d['approval'].update(reviewed_revision='0' * 64), 'E_APPROVAL_STALE'),
            ('profile', lambda d: d['requires'].update(material_profile='core:unknown/profile'), 'E_MATERIAL_PROFILE'),
            ('engine', lambda d: d['requires'].update(min_engine='999.0.0'), 'E_ENGINE_VERSION'),
            ('budget', lambda d: d['budgets'].update(triangles=1), 'E_MEASUREMENT_STALE'),
            ('export', lambda d: d['export'].update(contract_major=2), 'E_UNKNOWN_CONTRACT'),
        ]
        for name, edit, code in cases:
            with self.subTest(name=name):
                root = isolated_assets(self)
                edit_manifest(root, 'frigate', edit)
                resolver = AssetResolver(root)
                self.assertIsNone(resolver.resolve('rebel:frigate'))
                self.assertEqual(resolver.diagnostics[-1]['code'], code)

    def test_symlink_export_escape_refuses_core(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        path = root / 'assets/models/alliance_frigate.mesh.json'
        path.unlink()
        path.symlink_to(ROOT / 'assets/models/alliance_frigate.mesh.json')
        resolver = AssetResolver(root)
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_SYMLINK_ESCAPE')


class GenericGeometryTests(unittest.TestCase):
    def fixture(self, mutate=None):
        root = isolated_assets(self)
        payload = {'contract': 'star-armada/mesh-export', 'contract_major': 1,
                   'asset': 'test:generic/hull',
                   'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 1]],
                   'batches': {'base': [[0, -math.sqrt(.5), math.sqrt(.5), 0, 1, 2]]},
                   'triangle_count': 1, 'bounds': [[0, 0, 0], [1, 1, 1]]}
        if mutate:
            mutate(payload)
        path = root / 'assets/models/generic.json'
        save_json(path, payload)
        manifest_path = root / 'assets/models/manifests/alliance_frigate.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.update(asset='test:generic/hull', roles=['base'],
                        bounds={'min': [0, 0, 0], 'max': [1, 1, 1]})
        manifest.pop('approval', None)
        manifest['export'].pop('legacy_schema_int', None)
        manifest['files'] = {'mesh': {'path': 'assets/models/generic.json', 'bytes': path.stat().st_size,
                                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
        manifest['revision'] = hashlib.sha256(
            (manifest['asset'] + '\nmesh:' + manifest['files']['mesh']['sha256']).encode()).hexdigest()
        save_json(manifest_path, manifest)
        registry_path = root / 'assets/models/registry.json'
        registry = json.loads(registry_path.read_text())
        row = next(r for r in registry['bindings'] if r['binding'] == 'rebel:frigate')
        row['manifest'] = manifest['asset']
        save_json(registry_path, registry)
        return root

    def test_generic_modern_geometry_does_not_require_specimen_identity_or_all_roles(self):
        from render.asset_registry import AssetResolver
        resolved = AssetResolver(self.fixture()).resolve('rebel:frigate')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.asset, 'test:generic/hull')
        self.assertEqual(resolved.mesh['base'][0][1], ((0, 0, 0), (1, 0, 0), (0, 1, 1)))
        self.assertEqual(resolved.mesh['cool'], ())

    def test_bad_geometry_is_refused_after_valid_hashes(self):
        from render.asset_registry import AssetResolver
        cases = [
            ('normal', lambda p: p['batches']['base'][0].__setitem__(0, 3)),
            ('reversed', lambda p: p['batches']['base'][0].__setitem__(slice(3, 6), [0, 2, 1])),
            ('degenerate', lambda p: p['batches']['base'][0].__setitem__(slice(3, 6), [0, 0, 1])),
            ('index', lambda p: p['batches']['base'][0].__setitem__(3, 3)),
            ('bool_index', lambda p: p['batches']['base'][0].__setitem__(3, True)),
            ('count', lambda p: p.update(triangle_count=True)),
            ('bounds', lambda p: p.update(bounds=[[0, 0, 0], [2, 2, 2]])),
            ('vertices', lambda p: p.update(vertices=[[]])),
            ('batches', lambda p: p.update(batches=[])),
            ('version', lambda p: p.update(contract_major=99)),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                resolver = AssetResolver(self.fixture(mutate))
                self.assertIsNone(resolver.resolve('rebel:frigate'))
                self.assertEqual(resolver.diagnostics[-1]['code'], 'E_EXPORT_SHAPE')


class RegistryDiscoveryTests(unittest.TestCase):
    def test_catalogue_pending_aliases_unknown_and_frozen_discovery(self):
        from render.asset_registry import AssetResolver, AssetError
        from unittest.mock import patch
        resolver = AssetResolver(ROOT)
        self.assertEqual(resolver.resolve('alliance_frigate').revision,
                         resolver.resolve('rebel:frigate').revision)
        for key in ('rebel:corvette', 'imperial:shipyard',
                    'rebel:attack_satellite', 'rebel:planet_extractor',
                    'shared:construction_scaffold'):
            with self.subTest(approved_binding=key):
                self.assertIsNotNone(resolver.resolve(key))
        for key in ('syndicate:bomber',
                    'environment:temperate', 'menu:cinematic_backdrop'):
            with self.subTest(binding=key):
                self.assertIsNone(resolver.resolve(key))
        with self.assertRaises(AssetError) as caught:
            resolver.resolve('nobody:unknown')
        self.assertEqual(caught.exception.code, 'E_UNKNOWN_BINDING')
        root = isolated_assets(self)
        with patch('sys._MEIPASS', str(root), create=True):
            self.assertEqual(AssetResolver().root, root)
            self.assertIsNotNone(AssetResolver().resolve('rebel:frigate'))
        for name in ('alliance_frigate', 'alliance_shipyard', 'alliance_battleship'):
            self.assertEqual((ROOT / f'assets/models/manifests/{name}.json').read_bytes(),
                             (ROOT / f'art/schemas/examples/manifests/{name}.json').read_bytes())
        self.assertTrue(resolver.coverage()['ok'])
        coverage = resolver.coverage()
        self.assertEqual(len(coverage['authored']), 103)
        self.assertEqual(len(coverage['procedural']), 16)

    def test_registry_duplicate_bindings_are_not_silently_overwritten(self):
        from render.asset_registry import AssetResolver, AssetError
        root = isolated_assets(self)
        path = root / 'assets/models/registry.json'
        data = json.loads(path.read_text())
        data['bindings'].append(data['bindings'][0])
        save_json(path, data)
        with self.assertRaises(AssetError) as caught:
            AssetResolver(root)
        self.assertEqual(caught.exception.code, 'E_DUPLICATE_BINDING')


class CacheTests(unittest.TestCase):
    def test_pack_list_and_diagnostics_have_hard_bounds(self):
        from render.asset_registry import AssetResolver, AssetError
        resolver = AssetResolver(ROOT)
        with self.assertRaises(AssetError) as caught:
            resolver.activate_packs(['missing/visual-pack.json'] * 33)
        self.assertEqual(caught.exception.code, 'E_PACK_LIMIT')
        for _ in range(300):
            resolver.activate_packs(['missing/visual-pack.json'])
        self.assertLessEqual(len(resolver.diagnostics), 256)

    def test_core_failure_is_cached_until_session_invalidation(self):
        from render import asset_registry as module
        from unittest.mock import patch
        root = isolated_assets(self)
        (root / 'assets/models/alliance_frigate.mesh.json').unlink()
        resolver = module.AssetResolver(root)
        with patch.object(module, '_read', wraps=module._read) as reads:
            for _ in range(100):
                self.assertIsNone(resolver.resolve('rebel:frigate'))
            self.assertEqual(reads.call_count, 1, 'corrupt asset retried per material/frame')
        self.assertEqual(len(resolver.diagnostics), 1)
        resolver.cache_clear()
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(len(resolver.diagnostics), 2)

    def test_lru_is_bounded_clearable_and_content_keyed(self):
        from render.asset_registry import AssetResolver, AssetError
        resolver = AssetResolver(ROOT, max_cache_entries=1)
        a = resolver.resolve('rebel:frigate')
        self.assertIs(a, resolver.resolve('rebel:frigate'))
        self.assertTrue(resolver.is_authored('rebel:frigate'))
        self.assertFalse(resolver.is_authored('syndicate:bomber'))
        self.assertEqual(resolver.cache_info().currsize, 1)
        self.assertGreater(resolver.cache_info().hits, 0)
        self.assertEqual(resolver.cache_key('rebel:frigate'),
                         (a.revision, a.pack_revision, a.material_profile, 'mesh'))
        resolver.resolve('rebel:battleship')
        self.assertEqual(resolver.cache_info().currsize, 1)
        self.assertIsNot(a, resolver.resolve('rebel:frigate'))
        resolver.cache_clear()
        self.assertEqual(resolver.cache_info().currsize, 0)
        self.assertEqual(resolver.cache_info().hits, 0)
        self.assertIsNone(resolver.cache_key('syndicate:bomber'))
        self.assertIsNone(resolver.resolve('rebel:frigate', lod='lod1'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_LOD')
        for count in (-1, True, 1.5, 4097):
            with self.subTest(count=count), self.assertRaises(AssetError):
                AssetResolver(ROOT, max_cache_entries=count)
        disabled = AssetResolver(ROOT, max_cache_entries=0)
        self.assertIsNotNone(disabled.resolve('rebel:frigate'))
        self.assertEqual(disabled.cache_info().currsize, 0)


class PackTests(unittest.TestCase):
    def pack(self, identifier='test:first', binding='rebel:frigate', *, adds=False):
        root = GenericGeometryTests.fixture(self)
        path = root / 'visual-pack.json'
        entry = {'binding': binding, 'manifest': 'assets/models/manifests/alliance_frigate.json'}
        pack = {'contract': 'star-armada/visual-pack', 'contract_major': 1,
                'id': identifier, 'version': '1.0.0',
                'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
                'content': {'adds' if adds else 'replaces': [entry]}}
        if adds:
            pack['requires']['gameplay_mod'] = 'gameplay:raiders'
            entry['entity_source'] = 'gameplay:raiders'
        save_json(path, pack)
        return path

    def test_oversized_geometry_integers_reject_pack_and_continue_in_order(self):
        from render.asset_registry import AssetResolver
        for field in ('vertex', 'normal'):
            with self.subTest(field=field):
                first, bad = self.pack(), self.pack('test:bad')
                later = self.pack('test:later', binding='rebel:battleship')
                payload_path = bad.parent / 'assets/models/generic.json'
                payload = json.loads(payload_path.read_text())
                vector = payload['vertices'][0] if field == 'vertex' else payload['batches']['base'][0]
                vector[0] = 10 ** 400
                save_json(payload_path, payload)
                manifest_path = bad.parent / 'assets/models/manifests/alliance_frigate.json'
                manifest = json.loads(manifest_path.read_text())
                manifest['files']['mesh'].update(bytes=payload_path.stat().st_size,
                                                sha256=hashlib.sha256(payload_path.read_bytes()).hexdigest())
                manifest['revision'] = hashlib.sha256((manifest['asset'] + '\nmesh:' +
                                         manifest['files']['mesh']['sha256']).encode()).hexdigest()
                save_json(manifest_path, manifest)
                resolver = AssetResolver(ROOT)
                self.assertEqual(resolver.activate_packs([first, bad, later]), ('test:first', 'test:later'))
                self.assertEqual(resolver.active_order[1]['code'], 'E_EXPORT_SHAPE')
                self.assertFalse(resolver.active_order[1]['accepted'])
                self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
                self.assertEqual(resolver.resolve('rebel:battleship').pack_id, 'test:later')

    def test_oversized_engine_version_component_rejects_pack_and_continues(self):
        from render.asset_registry import AssetResolver, AssetError
        version = '9' * 5000 + '.0.0'
        with self.assertRaises(AssetError) as caught:
            AssetResolver(ROOT, engine_version=version)
        self.assertEqual(caught.exception.code, 'E_ENGINE_VERSION')
        for location in ('pack', 'manifest'):
            with self.subTest(location=location):
                first, bad = self.pack(), self.pack('test:bad')
                later = self.pack('test:later', binding='rebel:battleship')
                path = bad if location == 'pack' else bad.parent / 'assets/models/manifests/alliance_frigate.json'
                data = json.loads(path.read_text())
                data['requires']['min_engine'] = version
                save_json(path, data)
                resolver = AssetResolver(ROOT)
                self.assertEqual(resolver.activate_packs([first, bad, later]), ('test:first', 'test:later'))
                self.assertEqual(resolver.active_order[1]['code'], 'E_ENGINE_VERSION')
                self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
                self.assertEqual(resolver.resolve('rebel:battleship').pack_id, 'test:later')

    def test_explicit_order_reset_duplicates_and_transactional_envelope_rejection(self):
        from render.asset_registry import AssetResolver
        resolver = AssetResolver(ROOT)
        first, second, bad = self.pack(), self.pack('test:second'), self.pack('test:bad')
        # First valid replacement is inside the binding's approved envelope.
        resolver.activate_packs([first])
        first_asset = resolver.resolve('rebel:frigate')
        self.assertEqual(first_asset.pack_id, 'test:first')
        self.assertEqual(first_asset.source, str(first.parent))
        self.assertNotEqual(first_asset.pack_revision, '')
        resolver.activate_packs([first, second])
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:second')
        resolver.activate_packs([second, first])
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
        # One valid replacement followed by one that exceeds another target's
        # explicit approved envelope; none of this pack's entries may activate.
        payload_path = bad.parent / 'assets/models/generic.json'
        payload = json.loads(payload_path.read_text())
        payload['vertices'][1][0] = 1000
        payload['bounds'][1][0] = 1000
        save_json(payload_path, payload)
        manifest_path = bad.parent / 'assets/models/manifests/alliance_frigate.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['bounds']['max'][0] = 1000
        manifest['files']['mesh']['bytes'] = payload_path.stat().st_size
        manifest['files']['mesh']['sha256'] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
        manifest['revision'] = hashlib.sha256((manifest['asset'] + '\nmesh:' + manifest['files']['mesh']['sha256']).encode()).hexdigest()
        save_json(manifest_path, manifest)
        data = json.loads(bad.read_text())
        data['content']['replaces'].insert(0, {'binding': 'rebel:shipyard', 'manifest': 'assets/models/manifests/alliance_shipyard.json'})
        save_json(bad, data)
        resolver.activate_packs([first, bad])
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
        self.assertIsNone(resolver.resolve('rebel:shipyard').pack_id)
        self.assertEqual(resolver.active_order[-1]['code'], 'E_EXTENT_DRIFT')
        self.assertFalse(resolver.active_order[-1]['accepted'])
        self.assertEqual(resolver.diagnostics[-1]['active_order'], resolver.active_order)
        duplicate_id = self.pack('test:first')
        resolver.activate_packs([first, first, duplicate_id])
        self.assertEqual([item['accepted'] for item in resolver.active_order], [True, False, False])
        self.assertEqual([item['code'] for item in resolver.active_order[1:]], ['E_DUPLICATE_ID', 'E_DUPLICATE_ID'])
        resolver.activate_packs([])
        self.assertIsNone(resolver.resolve('rebel:frigate').pack_id)


    def test_replacement_and_addition_work_with_real_export_geometry(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        pack = root / 'visual-pack.json'
        data = {'contract': 'star-armada/visual-pack', 'contract_major': 1,
                'id': 'test:real_export', 'version': '1.0.0',
                'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
                'content': {'replaces': [{'binding': 'rebel:frigate',
                                         'manifest': 'assets/models/manifests/alliance_frigate.json'}]}}
        save_json(pack, data)
        resolver = AssetResolver(ROOT)
        self.assertEqual(resolver.activate_packs([pack]), ('test:real_export',))
        self.assertEqual(resolver.resolve('rebel:frigate').mesh,
                         AssetResolver(ROOT).resolve('rebel:frigate').mesh)
        # An actual evaluated frigate is rebound only inside this disposable test
        # fixture; production bytes and approval records stay immutable.
        payload_path = root / 'assets/models/alliance_frigate.mesh.json'
        payload = json.loads(payload_path.read_text())
        payload.pop('schema')
        payload.update(contract='star-armada/mesh-export', contract_major=1,
                       asset='raiders:fixture/scout')
        save_json(payload_path, payload)
        manifest_path = root / 'assets/models/manifests/alliance_frigate.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.pop('approval')
        manifest['asset'] = payload['asset']
        manifest['export'].pop('legacy_schema_int')
        manifest['files']['mesh'].update(bytes=payload_path.stat().st_size,
                                        sha256=hashlib.sha256(payload_path.read_bytes()).hexdigest())
        manifest['revision'] = hashlib.sha256((manifest['asset'] + '\nmesh:' +
                                 manifest['files']['mesh']['sha256']).encode()).hexdigest()
        save_json(manifest_path, manifest)
        data['requires']['gameplay_mod'] = 'gameplay:raiders'
        data['content'] = {'adds': [{'binding': 'raiders:scout', 'entity_source': 'gameplay:raiders',
                                    'manifest': 'assets/models/manifests/alliance_frigate.json'}]}
        save_json(pack, data)
        resolver.activate_packs([pack], gameplay_entities={'gameplay:raiders': {'raiders:scout'}})
        addition = resolver.resolve('raiders:scout')
        self.assertIsNotNone(addition)
        self.assertEqual(sum(map(len, addition.mesh.values())), payload['triangle_count'])
        self.assertEqual(addition.asset, 'raiders:fixture/scout')

    def test_additions_require_actual_entity_fixture_not_just_mod_name(self):
        from render.asset_registry import AssetResolver, AssetError
        path = self.pack('test:addon', 'raiders:scout', adds=True)
        resolver = AssetResolver(ROOT)
        resolver.activate_packs([path])
        self.assertFalse(resolver.active_order[0]['accepted'])
        resolver.activate_packs([path], gameplay_entities={'gameplay:raiders': {'raiders:other'}})
        self.assertEqual(resolver.active_order[0]['code'], 'E_GAMEPLAY_ENTITY')
        resolver.activate_packs([path], gameplay_entities={'gameplay:raiders': {'raiders:scout'}})
        self.assertTrue(resolver.active_order[0]['accepted'])
        self.assertEqual(resolver.resolve('raiders:scout').pack_id, 'test:addon')
        self.assertTrue(AssetResolver(ROOT, gameplay_entities={'gameplay:raiders': {'raiders:scout'}})
                        .activate_packs([path]))
        resolver.activate_packs([])
        with self.assertRaises(AssetError):
            resolver.resolve('raiders:scout')

    def test_pack_negative_controls_preserve_previous_valid_source(self):
        from render.asset_registry import AssetResolver
        cases = [
            ('unknown_contract', lambda p: p['requires'].update(contracts=['star-armada/nope/v1']), 'E_UNKNOWN_CONTRACT'),
            ('engine', lambda p: p['requires'].update(min_engine='999.0.0'), 'E_ENGINE_VERSION'),
            ('unknown_binding', lambda p: p['content']['replaces'][0].update(binding='missing:hull'), 'E_UNKNOWN_BINDING'),
            ('duplicate', lambda p: p['content']['replaces'].append(p['content']['replaces'][0]), 'E_DUPLICATE_ID'),
            ('traversal', lambda p: p['content']['replaces'][0].update(manifest='../escape.json'), 'E_UNSAFE_PATH'),
            ('replace_of', lambda p: p['content']['replaces'][0].update(replace_of='core:wrong/model'), 'E_ASSET_COLLISION'),
            ('core_addition', lambda p: p['content'].update(adds=p['content'].pop('replaces')), 'E_ASSET_COLLISION'),
        ]
        for name, mutate, code in cases:
            with self.subTest(name=name):
                good, bad = self.pack(), self.pack('test:bad')
                data = json.loads(bad.read_text())
                mutate(data)
                save_json(bad, data)
                resolver = AssetResolver(ROOT)
                resolver.activate_packs([good, bad])
                self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
                self.assertEqual(resolver.active_order[1]['code'], code)
        executable = self.pack('test:executable')
        (executable.parent / 'startup.py').write_text('raise Exception()')
        resolver = AssetResolver(ROOT)
        resolver.activate_packs([executable])
        self.assertEqual(resolver.active_order[0]['code'], 'E_EXECUTABLE_CONTENT')


class ApprovalReceiptTests(unittest.TestCase):
    def test_packaged_receipts_replace_source_evidence_without_weakening_approval(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        # No art/, tools/, or artifact evidence exists in this runtime-only copy.
        self.assertIsNotNone(AssetResolver(root).resolve('rebel:frigate'))
        receipts_path = root / 'assets/models/approval-receipts.json'
        self.assertTrue(receipts_path.is_file())
        receipts = json.loads(receipts_path.read_text())
        for name in ('alliance_battleship', 'alliance_frigate', 'alliance_shipyard'):
            manifest_path = ROOT / f'assets/models/manifests/{name}.json'
            manifest = json.loads(manifest_path.read_text())
            receipt = receipts['receipts'][manifest['asset']]
            canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
            self.assertEqual(receipt['manifest_sha256'], hashlib.sha256(canonical).hexdigest())
            for rel, digest in receipt['evidence_sha256'].items():
                self.assertEqual(digest, hashlib.sha256((ROOT / rel).read_bytes()).hexdigest())
        receipts['receipts'].pop('core:alliance/frigate')
        save_json(receipts_path, receipts)
        resolver = AssetResolver(root)
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_EVIDENCE_MISSING')

    def test_approval_cannot_survive_tool_metadata_change_or_missing_review_fields(self):
        from render.asset_registry import AssetResolver
        for edit, code in [
            (lambda d: d['provenance'].update(tool_version='unreviewed exporter'), 'E_APPROVAL_STALE'),
            (lambda d: d['approval'].pop('decision_id'), 'E_EVIDENCE_MISSING'),
            (lambda d: d['approval'].update(reviewed_evidence=[]), 'E_EVIDENCE_MISSING'),
            (lambda d: d['approval'].update(decided_on='not-a-date'), 'E_APPROVAL_STALE'),
        ]:
            with self.subTest(code=code):
                root = isolated_assets(self)
                edit_manifest(root, 'frigate', edit)
                resolver = AssetResolver(root)
                self.assertIsNone(resolver.resolve('rebel:frigate'))
                self.assertEqual(resolver.diagnostics[-1]['code'], code)


class BoundaryRobustnessTests(unittest.TestCase):
    def test_oversized_binding_envelope_integer_is_rejected_before_float_arithmetic(self):
        from render.asset_registry import AssetResolver, AssetError
        root = isolated_assets(self)
        path = root / 'assets/models/registry.json'
        data = json.loads(path.read_text())
        row = next(r for r in data['bindings'] if r['binding'] == 'rebel:frigate')
        row['envelope']['max'][0] = 10 ** 400
        save_json(path, data)
        with self.assertRaises(AssetError) as caught:
            resolver = AssetResolver(root)
            resolver.resolve('rebel:frigate')
        self.assertEqual(caught.exception.code, 'E_SCHEMA')

    def test_malformed_pack_containers_are_rejected_without_crashing(self):
        from render.asset_registry import AssetResolver
        for content in (None, [], 'oops', 9):
            with self.subTest(content=content):
                path = PackTests.pack(self)
                data = json.loads(path.read_text())
                data['content'] = content
                save_json(path, data)
                resolver = AssetResolver(ROOT)
                resolver.activate_packs([path])
                self.assertFalse(resolver.active_order[0]['accepted'])
                self.assertEqual(resolver.active_order[0]['code'], 'E_SCHEMA')

    def test_malformed_or_oversized_manifest_is_diagnostic_not_keyerror(self):
        from render.asset_registry import AssetResolver
        for raw, code in [
            ('{}', 'E_SCHEMA'),
            ('{"contract":"star-armada/model-manifest"}', 'E_UNKNOWN_CONTRACT'),
            ('{"asset":"core:alliance/frigate","revision":null}', 'E_UNKNOWN_CONTRACT'),
            ('{"asset":"core:alliance/frigate","x":NaN}', 'E_NON_FINITE'),
            ('{"asset":"core:alliance/frigate","x":1e9999}', 'E_NON_FINITE'),
            ('{"asset":"a","asset":"b"}', 'E_PARSE'),
            (' ' * 2_000_001, 'E_FILE_SIZE'),
        ]:
            with self.subTest(code=code):
                root = isolated_assets(self)
                (root / 'assets/models/manifests/alliance_frigate.json').write_text(raw)
                resolver = AssetResolver(root)
                self.assertIsNone(resolver.resolve('rebel:frigate'))
                self.assertTrue(any(d['code'] == code for d in resolver.diagnostics))

    def test_registry_path_cannot_escape_or_alias_ambiguous_core_ids(self):
        from render.asset_registry import AssetResolver, AssetError
        root = isolated_assets(self)
        with self.assertRaises(AssetError) as caught:
            AssetResolver(root, registry_path=ROOT / 'assets/models/registry.json')
        self.assertEqual(caught.exception.code, 'E_UNSAFE_PATH')
        duplicate = root / 'assets/models/manifests/duplicate.json'
        duplicate.write_bytes((root / 'assets/models/manifests/alliance_frigate.json').read_bytes())
        with self.assertRaises(AssetError) as caught:
            AssetResolver(root)
        self.assertEqual(caught.exception.code, 'E_DUPLICATE_ID')

    def test_core_coverage_failure_is_not_hidden_by_a_valid_pack(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        (root / 'assets/models/alliance_frigate.mesh.json').unlink()
        resolver = AssetResolver(root)
        pack = PackTests.pack(self)
        resolver.activate_packs([pack])
        self.assertIsNotNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.coverage()['required_core_failures'], ('rebel:frigate',))

    def test_payload_identifier_and_binding_envelope_metadata_are_enforced(self):
        from render.asset_registry import AssetResolver
        root = isolated_assets(self)
        # An export remains hash-correct but is falsely declared to be another
        # asset; legacy acceptance must still require the registry alias.
        path = root / 'assets/models/alliance_frigate.mesh.json'
        payload = json.loads(path.read_text())
        payload['asset'] = 'someone_else'
        save_json(path, payload)
        manifest_path = root / 'assets/models/manifests/alliance_frigate.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files']['mesh'].update(bytes=path.stat().st_size,
                                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest['revision'] = hashlib.sha256((manifest['asset'] + '\nmesh:' + manifest['files']['mesh']['sha256']).encode()).hexdigest()
        manifest.pop('approval')
        save_json(manifest_path, manifest)
        resolver = AssetResolver(root)
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_EXPORT_SHAPE')
        root = isolated_assets(self)
        registry = root / 'assets/models/registry.json'
        data = json.loads(registry.read_text())
        next(r for r in data['bindings'] if r['binding'] == 'rebel:frigate')['envelope_decision'] = 'wrong-decision'
        save_json(registry, data)
        resolver = AssetResolver(root)
        self.assertIsNone(resolver.resolve('rebel:frigate'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_EXTENT_DRIFT')
