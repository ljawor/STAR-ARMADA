"""GL-free adversarial optional-pack tests; all mutations stay in scratch fixtures."""
import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from render.asset_registry import AssetResolver

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT.parent


def save(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


def pin(manifest):
    body = '\n'.join(f"{key}:{manifest['files'][key]['sha256']}" for key in sorted(manifest['files']))
    manifest['revision'] = hashlib.sha256(f"{manifest['asset']}\n{body}".encode()).hexdigest()


class PackSafetyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='s08-pack-safety-', dir=SCRATCH)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def pack(self, name, binding='rebel:frigate', *, asset=None, adds=False):
        root = self.root / f'{name}_{len(list(self.root.iterdir()))}'
        root.mkdir()
        asset = asset or f'test:fixture/{name}'
        payload = {'contract': 'star-armada/mesh-export', 'contract_major': 1,
                   'asset': asset, 'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 1]],
                   'batches': {'base': [[0, -math.sqrt(.5), math.sqrt(.5), 0, 1, 2]]},
                   'triangle_count': 1, 'bounds': [[0, 0, 0], [1, 1, 1]]}
        save(root / 'mesh.json', payload)
        manifest = json.loads((ROOT / 'assets/models/manifests/alliance_frigate.json').read_text())
        manifest.update(asset=asset, roles=['base'], bounds={'min': [0, 0, 0], 'max': [1, 1, 1]})
        manifest.pop('approval', None)
        manifest['export'].pop('legacy_schema_int', None)
        manifest['files'] = {'mesh': self.file_entry(root / 'mesh.json')}
        pin(manifest)
        save(root / 'manifest.json', manifest)
        entry = {'binding': binding, 'manifest': 'manifest.json'}
        pack = {'contract': 'star-armada/visual-pack', 'contract_major': 1,
                'id': f'test:{name}', 'version': '1.0.0',
                'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
                'content': {'adds' if adds else 'replaces': [entry]}}
        if adds:
            pack['requires']['gameplay_mod'] = 'gameplay:test'
            entry['entity_source'] = 'gameplay:test'
        save(root / 'visual-pack.json', pack)
        return root / 'visual-pack.json'

    def file_entry(self, path):
        raw = path.read_bytes()
        return {'path': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def edit(self, path, mutate):
        data = json.loads(path.read_text())
        mutate(data)
        save(path, data)
        return data

    def assert_rejected_between_valid(self, bad, code, *, fixtures=None):
        first = self.pack('first')
        later = self.pack('later', 'rebel:battleship')
        resolver = AssetResolver(ROOT)
        accepted = resolver.activate_packs([first, bad, later], gameplay_entities=fixtures)
        self.assertEqual(accepted, ('test:first', 'test:later'))
        self.assertEqual([item['accepted'] for item in resolver.active_order], [True, False, True])
        self.assertEqual(resolver.active_order[1]['code'], code)
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
        self.assertEqual(resolver.resolve('rebel:battleship').pack_id, 'test:later')
        self.assertIsNone(resolver.resolve('rebel:shipyard').pack_id, 'no staged entry may leak')
        return resolver

    def test_distinct_bindings_cannot_hide_duplicate_asset_ids(self):
        bad = self.pack('bad', 'rebel:shipyard')
        # Distinct manifest paths and distinct bindings, but duplicate visual identity.
        duplicate = json.loads((bad.parent / 'manifest.json').read_text())
        duplicate['display_name'] = 'Conflicting declaration'
        save(bad.parent / 'duplicate.json', duplicate)
        self.edit(bad, lambda d: d['content']['replaces'].append(
            {'binding': 'rebel:frigate', 'manifest': 'duplicate.json'}))
        self.assert_rejected_between_valid(bad, 'E_DUPLICATE_ID')

    def test_addition_asset_identity_cannot_collide_with_active_pack(self):
        first = self.pack('first', 'raiders:scout', adds=True, asset='raiders:fixture/shared')
        bad = self.pack('bad', 'raiders:carrier', adds=True, asset='raiders:fixture/shared')
        later = self.pack('later', 'rebel:battleship')
        resolver = AssetResolver(ROOT)
        fixtures = {'gameplay:test': {'raiders:scout', 'raiders:carrier'}}
        self.assertEqual(resolver.activate_packs([first, bad, later], gameplay_entities=fixtures),
                         ('test:first', 'test:later'))
        self.assertEqual(resolver.active_order[1]['code'], 'E_ASSET_COLLISION')
        self.assertEqual(resolver.resolve('raiders:scout').pack_id, 'test:first')
        self.assertFalse(resolver.has_binding('raiders:carrier'))
        self.assertEqual(resolver.resolve('rebel:battleship').pack_id, 'test:later')

    def test_rejected_pack_does_not_reserve_identity_for_later_valid_pack(self):
        first = self.pack('first')
        bad = self.pack('bad', 'rebel:shipyard')
        later = self.pack('later', 'rebel:battleship')
        self.edit(bad, lambda d: d.update(id='test:later'))
        # Parse/schema succeed, then a missing resource aborts the transaction.
        (bad.parent / 'mesh.json').unlink()
        resolver = AssetResolver(ROOT)
        self.assertEqual(resolver.activate_packs([first, bad, later]), ('test:first', 'test:later'))
        self.assertEqual(resolver.active_order[1]['code'], 'E_FILE_MISSING')
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:first')
        self.assertEqual(resolver.resolve('rebel:battleship').pack_id, 'test:later')
        self.assertIsNone(resolver.resolve('rebel:shipyard').pack_id)

    def test_symlink_loops_reject_without_aborting_following_packs(self):
        for location in ('unused', 'manifest', 'mesh', 'pack'):
            with self.subTest(location=location):
                bad = self.pack('bad', 'rebel:shipyard')
                target = {'unused': bad.parent / 'loop.json',
                          'manifest': bad.parent / 'manifest.json',
                          'mesh': bad.parent / 'mesh.json', 'pack': bad}[location]
                target.unlink(missing_ok=True)
                target.symlink_to(target.name)
                self.assert_rejected_between_valid(bad, 'E_UNSAFE_PATH')

    def test_session_uses_complete_validated_snapshot_after_disk_corruption(self):
        from unittest.mock import patch
        from render import asset_registry as module
        pack = self.pack('snapshot')
        other = self.pack('other', 'rebel:shipyard')
        (pack.parent / 'extra-mesh.json').write_bytes((other.parent / 'mesh.json').read_bytes())
        manifest = json.loads((other.parent / 'manifest.json').read_text())
        manifest['files']['mesh']['path'] = 'extra-mesh.json'
        manifest['files']['lod1'] = copy.deepcopy(manifest['files']['mesh'])
        pin(manifest)
        save(pack.parent / 'extra.json', manifest)
        self.edit(pack, lambda d: d['content']['replaces'].append(
            {'binding': 'rebel:shipyard', 'manifest': 'extra.json'}))
        for cache_limit in (0, 1):
            with self.subTest(cache_limit=cache_limit):
                # Restore valid bytes at each session boundary.
                resource = pack.parent / 'extra-mesh.json'
                resource.unlink(missing_ok=True)
                resource.write_bytes((other.parent / 'mesh.json').read_bytes())
                resolver = AssetResolver(ROOT, max_cache_entries=cache_limit)
                self.assertEqual(resolver.activate_packs([pack]), ('test:snapshot',))
                first = resolver.resolve('rebel:frigate')
                self.assertIsNotNone(first)
                # A formerly validated but still uncached entry becomes corrupt on disk.
                resource.unlink()
                resource.symlink_to(resource.name)
                resolver.cache_clear()
                with patch.object(module, '_read', side_effect=AssertionError('session reread pack disk')):
                    for lod in ('mesh', 'lod1'):
                        second = resolver.resolve('rebel:shipyard', lod=lod)
                        self.assertIsNotNone(second, 'one broken disk entry must not split a session pack')
                        self.assertEqual(second.pack_revision, first.pack_revision)
                        self.assertEqual(second.revision, manifest['revision'])
                        self.assertEqual(second.lod, lod)
                    self.assertEqual(resolver.resolve('rebel:frigate').revision, first.revision)
                # A NEW session must reject the corrupt whole pack, not reuse snapshots.
                self.assertEqual(resolver.activate_packs([pack]), ())
                self.assertIsNone(resolver.resolve('rebel:frigate').pack_id)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires POSIX FIFO fixtures')
    def test_unused_fifo_is_not_a_data_only_pack_resource(self):
        bad = self.pack('bad', 'rebel:shipyard')
        os.mkfifo(bad.parent / 'unused.json')
        self.assert_rejected_between_valid(bad, 'E_FILE_TYPE')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires POSIX FIFO fixtures')
    def test_fifo_pack_descriptor_rejects_without_blocking(self):
        first, bad = self.pack('first'), self.pack('bad')
        later = self.pack('later', 'rebel:battleship')
        bad.unlink()
        os.mkfifo(bad)
        script = ('from render.asset_registry import AssetResolver; '
                  f'r=AssetResolver({str(ROOT)!r}); '
                  f'assert r.activate_packs({[str(first), str(bad), str(later)]!r}) == '
                  "('test:first', 'test:later'); "
                  "assert r.active_order[1]['code'] == 'E_FILE_TYPE'; print('safe rejection')")
        try:
            result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                    capture_output=True, text=True, timeout=3)
        except subprocess.TimeoutExpired:
            self.fail('optional FIFO descriptor blocked startup (child killed at 3s deadline)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('safe rejection', result.stdout)

    def test_malformed_additive_asset_identity_is_schema_rejection_not_typeerror(self):
        for identity in ([], {}, None, 42):
            with self.subTest(identity=identity):
                bad = self.pack('bad', 'raiders:scout', adds=True)
                self.edit(bad.parent / 'manifest.json', lambda d: d.update(asset=identity))
                self.assert_rejected_between_valid(bad, 'E_SCHEMA',
                    fixtures={'gameplay:test': {'raiders:scout'}})

    def test_unreadable_subtree_is_rejected_not_silently_skipped(self):
        from unittest.mock import patch
        bad = self.pack('bad', 'rebel:shipyard')
        hidden = bad.parent / 'hidden'
        hidden.mkdir()
        (hidden / 'startup.py').write_text('not executed', encoding='utf-8')
        real_scandir = os.scandir

        def scandir(path):
            if Path(path) == hidden:
                raise PermissionError('injected unreadable pack subtree')
            return real_scandir(path)

        with patch.object(os, 'scandir', side_effect=scandir):
            self.assert_rejected_between_valid(bad, 'E_FILE_MISSING')

    def test_retained_session_snapshots_have_aggregate_geometry_ceiling(self):
        from unittest.mock import patch
        bad = self.pack('bad', 'rebel:shipyard')
        def extra_lod(d):
            d['files']['lod1'] = copy.deepcopy(d['files']['mesh'])
            pin(d)
        self.edit(bad.parent / 'manifest.json', extra_lod)
        # Real small meshes, a lowered ceiling: no huge allocations in the test.
        with patch('render.asset_registry.MAX_PACK_SNAPSHOT_TRIANGLES', 2, create=True):
            self.assert_rejected_between_valid(bad, 'E_PACK_RESOURCE')

    def test_effective_pack_origins_and_only_committed_conflicts_are_reported(self):
        from unittest.mock import patch
        first, bad, second = self.pack('first'), self.pack('bad'), self.pack('second')
        (bad.parent / 'mesh.json').unlink()
        resolver = AssetResolver(ROOT)
        self.assertEqual(resolver.activate_packs([first, bad, second]), ('test:first', 'test:second'))
        with patch.object(resolver, '_load', side_effect=AssertionError('diagnostics loaded core catalogue')):
            origins = resolver.pack_bindings()
        self.assertEqual(len(origins), 1)
        origin = origins[0]
        self.assertEqual(origin['binding'], 'rebel:frigate')
        self.assertEqual(origin['asset'], 'test:fixture/second')
        self.assertEqual(origin['pack_id'], 'test:second')
        self.assertEqual(origin['source'], str(second.parent))
        self.assertEqual(origin['pack_revision'], resolver.active_order[2]['revision'])
        conflicts = [d for d in resolver.diagnostics if d['code'] == 'I_BINDING_OVERRIDE']
        self.assertEqual(len(conflicts), 1, 'rejected packs must not report committed conflicts')
        self.assertEqual(conflicts[0]['binding'], 'rebel:frigate')
        self.assertEqual(conflicts[0]['previous_pack_id'], 'test:first')
        self.assertEqual(conflicts[0]['pack_id'], 'test:second')
        origin['pack_id'] = 'caller mutation'
        self.assertEqual(resolver.pack_bindings()[0]['pack_id'], 'test:second')
        resolver.activate_packs([])
        self.assertEqual(resolver.pack_bindings(), [])

    def stage_shipyard(self, pack):
        other = self.pack('staged', 'rebel:shipyard')
        (pack.parent / 'staged-mesh.json').write_bytes((other.parent / 'mesh.json').read_bytes())
        manifest = json.loads((other.parent / 'manifest.json').read_text())
        manifest['files']['mesh']['path'] = 'staged-mesh.json'
        save(pack.parent / 'staged.json', manifest)
        self.edit(pack, lambda d: d['content'].setdefault('replaces', []).insert(0,
            {'binding': 'rebel:shipyard', 'manifest': 'staged.json'}))

    def test_unsafe_manifest_and_mesh_paths_roll_back_whole_pack(self):
        paths = ('../outside.json', '/outside.json', 'C:/outside.json',
                 'C:\\outside.json', 'assets/../mesh.json', './mesh.json',
                 'assets//mesh.json', 'assets/./mesh.json', '', 'a' * 182)
        for location in ('manifest', 'mesh'):
            for path in paths:
                with self.subTest(location=location, path=path):
                    bad = self.pack('bad')
                    self.stage_shipyard(bad)
                    if location == 'manifest':
                        self.edit(bad, lambda d: d['content']['replaces'][1].update(manifest=path))
                    else:
                        self.edit(bad.parent / 'manifest.json',
                                  lambda d: d['files']['mesh'].update(path=path))
                    self.assert_rejected_between_valid(bad, 'E_UNSAFE_PATH')

    def test_symlink_escapes_in_any_pack_resource_roll_back(self):
        outside = self.root / 'outside.json'
        outside.write_text('{}', encoding='utf-8')
        for location in ('unused', 'manifest', 'mesh', 'directory', 'pack'):
            with self.subTest(location=location):
                bad = self.pack('bad')
                self.stage_shipyard(bad)
                target = {'unused': bad.parent / 'unused.json',
                          'manifest': bad.parent / 'manifest.json', 'mesh': bad.parent / 'mesh.json',
                          'directory': bad.parent / 'escape', 'pack': bad}[location]
                target.unlink(missing_ok=True)
                target.symlink_to(self.root if location == 'directory' else outside,
                                  target_is_directory=location == 'directory')
                self.assert_rejected_between_valid(bad, 'E_SYMLINK_ESCAPE')

    def test_invalid_or_missing_declared_lods_roll_back_other_entries(self):
        for problem, code in (('missing_mesh', 'E_SCHEMA'), ('unknown_lod', 'E_SCHEMA'),
                              ('missing_lod', 'E_FILE_MISSING'), ('invalid_lod', 'E_EXPORT_SHAPE')):
            with self.subTest(problem=problem):
                bad = self.pack('bad')
                self.stage_shipyard(bad)
                manifest_path = bad.parent / 'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                entry = copy.deepcopy(manifest['files']['mesh'])
                if problem == 'missing_mesh':
                    manifest['files'] = {'lod1': entry}
                elif problem == 'unknown_lod':
                    manifest['files']['lod9'] = entry
                else:
                    entry['path'] = 'lod1.json'
                    if problem == 'invalid_lod':
                        payload = json.loads((bad.parent / 'mesh.json').read_text())
                        payload['batches']['base'][0][3:] = [0, 2, 1]
                        save(bad.parent / 'lod1.json', payload)
                        entry = self.file_entry(bad.parent / 'lod1.json')
                    manifest['files']['lod1'] = entry
                pin(manifest)
                save(manifest_path, manifest)
                self.assert_rejected_between_valid(bad, code)

    def test_undeclared_lod_is_safe_query_fallback_not_pack_invalidation(self):
        pack = self.pack('single')
        resolver = AssetResolver(ROOT)
        resolver.activate_packs([pack])
        self.assertIsNone(resolver.resolve('rebel:frigate', lod='lod1'))
        self.assertEqual(resolver.diagnostics[-1]['code'], 'E_LOD')
        self.assertEqual(resolver.resolve('rebel:frigate').pack_id, 'test:single')

    def test_hash_correct_geometry_limits_and_bounds_reject_transactionally(self):
        cases = (
            ('vertices', lambda p: p.update(vertices=p['vertices'] + [[0, 0, 0]] * 10000), 'E_EXPORT_SHAPE'),
            ('triangles', lambda p: (p['batches'].update(base=p['batches']['base'] * 12001),
                                     p.update(triangle_count=12001)), 'E_EXPORT_SHAPE'),
            ('bounds', lambda p: p.update(bounds=[[0, 0, 0], [2, 1, 1]]), 'E_EXPORT_SHAPE'),
            ('nonfinite', lambda p: p['vertices'][0].__setitem__(0, float('nan')), 'E_NON_FINITE'),
            ('index', lambda p: p['batches']['base'][0].__setitem__(3, 99), 'E_EXPORT_SHAPE'),
        )
        for name, mutate, code in cases:
            with self.subTest(problem=name):
                bad = self.pack('bad')
                self.stage_shipyard(bad)
                mesh_path = bad.parent / 'mesh.json'
                self.edit(mesh_path, mutate)
                def repin(d):
                    d['files']['mesh'] = self.file_entry(mesh_path)
                    pin(d)
                self.edit(bad.parent / 'manifest.json', repin)
                self.assert_rejected_between_valid(bad, code)
        for field, value, code in (('bounds', {'min': [2, 0, 0], 'max': [1, 1, 1]}, 'E_BOUNDS_DEGENERATE'),
                                   ('bounds', {'min': [0, 0, 0], 'max': [.5, 1, 1]}, 'E_BOUNDS_MISMATCH')):
            with self.subTest(manifest=code):
                bad = self.pack('bad')
                self.stage_shipyard(bad)
                self.edit(bad.parent / 'manifest.json', lambda d: d.update({field: value}))
                self.assert_rejected_between_valid(bad, code)

    def test_malformed_incompatible_and_unsupported_optional_packs_reject(self):
        cases = (
            ('content', lambda d: d.update(content=None), 'E_SCHEMA'),
            ('major', lambda d: d.update(contract_major=2), 'E_UNKNOWN_CONTRACT'),
            ('contract', lambda d: d['requires'].update(contracts=['star-armada/mesh-export/v2']), 'E_UNKNOWN_CONTRACT'),
            ('engine', lambda d: d['requires'].update(min_engine='999.0.0'), 'E_ENGINE_VERSION'),
            ('material', lambda d: d['content'].update(material_profiles=['test:fixture/material']), 'E_MATERIAL_PROFILE'),
            ('texture', lambda d: d['content'].update(textures=['missing.png']), 'E_SCHEMA'),
            ('replace_of', lambda d: d['content']['replaces'][0].update(replace_of='core:wrong/model'), 'E_ASSET_COLLISION'),
        )
        for name, mutate, code in cases:
            with self.subTest(problem=name):
                bad = self.pack('bad')
                self.edit(bad, mutate)
                self.assert_rejected_between_valid(bad, code)
        for raw, code in ((b'{', 'E_PARSE'), (b'[]', 'E_SCHEMA'), (b'\xff', 'E_PARSE'),
                          (b'{"id":"a","id":"b"}', 'E_PARSE'),
                          (b'{"x":NaN}', 'E_NON_FINITE'), (b' ' * 2000001, 'E_FILE_SIZE')):
            with self.subTest(raw=raw[:30], code=code):
                bad = self.pack('bad')
                bad.write_bytes(raw)
                self.assert_rejected_between_valid(bad, code)
        bad = self.pack('bad')
        bad.unlink()
        self.assert_rejected_between_valid(bad, 'E_FILE_MISSING')

    def test_file_and_entry_resource_limits_reject_without_hiding_later_pack(self):
        for target in ('manifest.json', 'mesh.json'):
            with self.subTest(target=target):
                bad = self.pack('bad')
                self.stage_shipyard(bad)
                (bad.parent / target).write_bytes(b' ' * 2000001)
                self.assert_rejected_between_valid(bad, 'E_FILE_SIZE')
        bad = self.pack('bad')
        for i in range(4097):
            (bad.parent / f'extra-{i}.json').touch()
        self.assert_rejected_between_valid(bad, 'E_FILE_SIZE')
        bad = self.pack('bad')
        self.edit(bad, lambda d: d['content'].update(replaces=d['content']['replaces'] * 513))
        self.assert_rejected_between_valid(bad, 'E_SCHEMA')

    def test_texture_file_fields_and_executable_content_are_not_v1_support(self):
        bad = self.pack('bad')
        self.edit(bad.parent / 'manifest.json', lambda d: d['files'].update(
            texture={'path': 'missing.png', 'bytes': 1, 'sha256': '0' * 64}))
        self.assert_rejected_between_valid(bad, 'E_SCHEMA')
        for suffix in ('.py', '.BLEND', '.pkl', '.vert', '.dll', '.js'):
            with self.subTest(suffix=suffix):
                bad = self.pack('bad')
                (bad.parent / ('unused' + suffix)).write_text('never executed', encoding='utf-8')
                self.assert_rejected_between_valid(bad, 'E_EXECUTABLE_CONTENT')

    def test_binary_reads_keep_platform_binary_flag(self):
        from unittest.mock import patch
        from render import asset_registry as module
        path = self.root / 'binary.json'
        raw = b'\r\n\x1a'
        path.write_bytes(raw)
        real_open = os.open
        binary_flag = 1 << 25  # simulated Windows flag, stripped before POSIX open
        seen_flags = []

        def open_binary(path, flags):
            seen_flags.append(flags)
            return real_open(path, flags & ~binary_flag)

        with patch.object(os, 'O_BINARY', binary_flag, create=True), \
                patch.object(os, 'open', side_effect=open_binary):
            self.assertEqual(module._read(path), raw)
        self.assertTrue(seen_flags[0] & binary_flag, 'os.open must preserve rb semantics on Windows')

    def test_retained_snapshot_metadata_and_encoded_payloads_have_byte_ceiling(self):
        from unittest.mock import patch
        small = self.pack('tiny')
        manifest = json.loads((small.parent / 'manifest.json').read_text())
        small_cost = len(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
        small_cost += sum(entry['bytes'] for entry in manifest['files'].values())
        bad = self.pack('bad', 'rebel:shipyard', asset='test:fixture/' + 'x' * 5000)
        with patch('render.asset_registry.MAX_PACK_SNAPSHOT_BYTES', small_cost * 2 + 100, create=True):
            self.assert_rejected_between_valid(bad, 'E_PACK_RESOURCE')
