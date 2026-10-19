"""Session-bound content replacement, using real evaluated Blender hulls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import game.core
from game.data.store import DataStore
from render import asset_selection as selection

ROOT = Path(__file__).resolve().parents[1]


def write_update_pack(root, factor):
    """Disposable derivatives only; all approved files stay read-only inputs."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in ('frigate', 'shipyard'):
        payload = json.loads((ROOT / f'assets/models/alliance_{name}.mesh.json').read_text())
        payload.pop('schema', None)
        payload.update(contract='star-armada/mesh-export', contract_major=1,
                       asset=f's08fixture:alliance/{name}')
        payload['vertices'] = [[x * factor for x in point] for point in payload['vertices']]
        payload['bounds'] = [[min(p[i] for p in payload['vertices']) for i in range(3)],
                             [max(p[i] for p in payload['vertices']) for i in range(3)]]
        raw = json.dumps(payload, separators=(',', ':')).encode()
        (root / f'{name}.mesh.json').write_bytes(raw)
        manifest = json.loads((ROOT / f'assets/models/manifests/alliance_{name}.json').read_text())
        manifest.pop('approval', None)
        manifest.update(asset=payload['asset'], bounds=dict(zip(('min', 'max'), payload['bounds'])))
        manifest['export'].pop('legacy_schema_int', None)
        manifest['files'] = {'mesh': {'path': f'{name}.mesh.json', 'bytes': len(raw),
                                    'sha256': hashlib.sha256(raw).hexdigest()}}
        manifest['revision'] = hashlib.sha256((payload['asset'] + '\nmesh:' +
                                               manifest['files']['mesh']['sha256']).encode()).hexdigest()
        (root / f'{name}.json').write_text(json.dumps(manifest))
        entries.append({'binding': f'rebel:{name}', 'manifest': f'{name}.json'})
    pack = {'contract': 'star-armada/visual-pack', 'contract_major': 1,
            'id': 's08fixture:update', 'version': '1.0.0',
            'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
            'content': {'replaces': entries}}
    (root / 'visual-pack.json').write_text(json.dumps(pack))


class AssetUpdateFixture:
    def setUp(self):
        self.addCleanup(setattr, DataStore, '_instance', DataStore._instance)
        self.addCleanup(selection.configure, {})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        write_update_pack(self.root / 'update', .8)
        self.settings = {'model_preview': True, 'visual_packs': ['update']}

    def configure(self):
        result = selection.configure(self.settings, asset_root=ROOT, pack_root=self.root)
        self.assertTrue(result['pack_order'][0]['accepted'], result)
        return selection._resolver.resolve('rebel:frigate')

    def snapshot_helpers(self):
        from render import ship_sizes as sizes, camera_geometry as camera
        from render.planet_building_geometry import _station_local_bounds
        return (sizes._bounds('rebel:frigate'), sizes._ray_mesh('rebel:frigate'),
                sizes._station_ray_mesh('rebel', 'shipyard'), camera.station_bounds('shipyard', 'rebel'),
                camera.station_radius('shipyard', 'rebel'), _station_local_bounds('rebel', 'shipyard'))

class SessionAssetUpdates(AssetUpdateFixture, unittest.TestCase):
    def test_same_path_revision_update_invalidates_all_bounds_and_contact_helpers(self):
        before = self.configure()
        resolver = selection._resolver
        a = self.snapshot_helpers()
        key = selection.gpu_cache_key('rebel:frigate', 'base', 'legacy')
        # The same files/pack id/version, but honest new mesh/manifest revisions.
        write_update_pack(self.root / 'update', .6)
        after = self.configure()
        b = self.snapshot_helpers()
        self.assertNotEqual(before.revision, after.revision)
        self.assertNotEqual(before.pack_revision, after.pack_revision)
        self.assertNotEqual(before.mesh, after.mesh)
        self.assertNotEqual(key, selection.gpu_cache_key('rebel:frigate', 'base', 'legacy'))
        self.assertEqual(resolver.cache_info().currsize, 0)
        self.assertNotEqual(a[0], b[0])
        self.assertIsNot(a[1], b[1])
        self.assertIsNot(a[2], b[2])
        self.assertFalse((a[1][0] == b[1][0]).all())
        self.assertFalse((a[2][0] == b[2][0]).all())
        for i in (3, 4, 5):
            self.assertNotEqual(a[i], b[i], i)
        selection.configure({})
        legacy = self.snapshot_helpers()
        self.assertNotEqual(b[0], legacy[0])
        self.assertIsNone(selection.mesh_for('rebel:frigate'))

    def test_partial_update_at_boundary_falls_back_as_whole_pack(self):
        self.configure()
        # A new valid first entry followed by a missing second payload must not
        # activate even the first entry of the optional pack.
        write_update_pack(self.root / 'update', .6)
        (self.root / 'update/shipyard.mesh.json').unlink()
        result = selection.configure(self.settings, asset_root=ROOT, pack_root=self.root)
        self.assertFalse(result['pack_order'][0]['accepted'])
        self.assertEqual(result['pack_order'][0]['code'], 'E_FILE_MISSING')
        for binding in ('rebel:frigate', 'rebel:shipyard'):
            self.assertIsNone(selection._resolver.resolve(binding).pack_id)


class NativeSessionAssetUpdates(AssetUpdateFixture, unittest.TestCase):

    def test_native_lists_are_deleted_and_recompiled_after_update_and_context_recreation(self):
        import pygame
        from OpenGL import GL
        from game.core.manager import GameManager
        from render.renderer import Renderer
        from render.camera import Camera
        self.assertFalse(pygame.display.get_init(), 'Run native S08 lifecycle in its own process')
        self.assertFalse(selection._renderer_owners)
        renderer = None
        pygame.display.init()
        try:
            surface = pygame.display.set_mode((480, 320), pygame.OPENGL | pygame.DOUBLEBUF)
            self.assertEqual(surface.get_size(), (480, 320))
            gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
            first_asset = self.configure()
            renderer = Renderer(gm.state, Camera(480, 320))
            self.assertTrue(renderer.materials.available, renderer.materials.error)
            first_list = renderer._ship_display_list('rebel:frigate')
            renderer._station_detail_list('shipyard', 'base', 'rebel')
            lists = set(renderer.ship_lists.values())
            self.assertTrue(lists)
            self.assertTrue(GL.glIsList(first_list))
            keys = set(renderer.ship_lists)
            self.assertTrue(any(first_asset.revision in k for k in keys if isinstance(k, tuple)))
            with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                self.configure()
            renderer.close()
            renderer = None
            self.assertFalse(any(GL.glIsList(value) for value in lists))
            write_update_pack(self.root / 'update', .6)
            updated = self.configure()
            self.assertNotEqual(first_asset.revision, updated.revision)
            # Explicit teardown/recreation. GL may reuse numeric names.
            pygame.display.quit()
            pygame.display.init()
            surface = pygame.display.set_mode((480, 320), pygame.OPENGL | pygame.DOUBLEBUF)
            self.assertEqual(surface.get_size(), (480, 320))
            renderer = Renderer(gm.state, Camera(480, 320))
            from unittest.mock import patch
            with patch.object(renderer, '_emit_detail_mesh', wraps=renderer._emit_detail_mesh) as emit:
                compiled = renderer._ship_display_list('rebel:frigate')
                self.assertEqual(len(emit.call_args_list), 6)
                self.assertEqual(sum(len(call.args[0]) for call in emit.call_args_list),
                                 sum(map(len, updated.mesh.values())))
            self.assertTrue(GL.glIsList(compiled))
            self.assertTrue(any(updated.revision in k for k in renderer.ship_lists if isinstance(k, tuple)))
            self.assertFalse(any(first_asset.revision in k for k in renderer.ship_lists if isinstance(k, tuple)))
            self.assertEqual(GL.glGetError(), GL.GL_NO_ERROR)
        finally:
            if renderer is not None:
                renderer.close()
            pygame.display.quit()


if __name__ == '__main__':
    unittest.main()
