"""Native argv must name real macOS bundle data, not Frameworks symlinks."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from render_bridge import cpp_window


class MacBundleAssetRootTests(unittest.TestCase):
    def test_frozen_macos_spawn_keeps_meshes_inside_native_asset_root(self):
        with tempfile.TemporaryDirectory() as directory:
            contents = Path(directory).resolve() / 'STAR ARMADA.app' / 'Contents'
            frameworks = contents / 'Frameworks'
            resources = contents / 'Resources'
            frameworks.mkdir(parents=True)
            (frameworks / 'cpp' / 'shaders').mkdir(parents=True)
            binary = str(frameworks / 'cpp' / 'armada_viewer')
            (resources / 'assets' / 'cpp').mkdir(parents=True)
            (resources / 'visual_packs').mkdir()
            (frameworks / 'assets').symlink_to('../Resources/assets', target_is_directory=True)
            (frameworks / 'visual_packs').symlink_to('../Resources/visual_packs', target_is_directory=True)
            snapshot = resources / 'assets' / 'cpp' / 'catalogue.snap'
            snapshot.write_bytes(b'fixture')
            paths = {key: Path(directory) / key for key in
                     ('frame', 'tables', 'overlay', 'emit', 'markers', 'fog',
                      'planets', 'input', 'camera', 'hardware')}
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '0'}), \
                    patch.object(cpp_window, 'find_binary', return_value=binary), \
                    patch('render_bridge.embedded.EmbeddedWindow') as window, \
                    patch('atexit.register'):
                cpp_window.spawn(paths, root=str(frameworks), snapshot=None, log=Mock())
            argv = window.call_args.args[0]
            root = Path(argv[argv.index('--assets') + 1]).resolve()
            # Same containment property as scene.hpp::load_mesh, for both mesh namespaces.
            for namespace in ('assets', 'visual_packs'):
                physical_mesh_parent = (frameworks / namespace).resolve()
                self.assertTrue(physical_mesh_parent.is_relative_to(root),
                                f'{namespace} resolves outside native asset root: {root}')
            self.assertEqual(root, resources)
            self.assertEqual(Path(window.call_args.kwargs['root']), resources)
            self.assertTrue(Path(argv[argv.index('--snapshot') + 1]).is_file())
            self.assertEqual(argv[argv.index('--shaders') + 1], str(frameworks / 'cpp' / 'shaders'))

    def test_flat_frozen_macos_keeps_existing_asset_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'assets' / 'cpp').mkdir(parents=True)
            snapshot = root / 'assets' / 'cpp' / 'catalogue.snap'
            snapshot.write_bytes(b'fixture')
            paths = {key: root / key for key in
                     ('frame', 'tables', 'overlay', 'emit', 'markers', 'fog',
                      'planets', 'input', 'camera', 'hardware')}
            with patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '0'}), \
                    patch.object(cpp_window, 'find_binary', return_value='/unused/armada_viewer'), \
                    patch('render_bridge.embedded.EmbeddedWindow') as window, \
                    patch('atexit.register'):
                cpp_window.spawn(paths, root=str(root), snapshot=None, log=Mock())
            argv = window.call_args.args[0]
            self.assertEqual(argv[argv.index('--assets') + 1], str(root))
            self.assertEqual(window.call_args.kwargs['root'], str(root))

    def test_source_and_windows_keep_the_requested_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            resources = root / 'resources'
            (resources / 'assets').mkdir(parents=True)
            (root / 'assets').symlink_to(resources / 'assets', target_is_directory=True)
            snapshot = resources / 'assets' / 'catalogue.snap'
            snapshot.write_bytes(b'fixture')
            paths = {key: root / key for key in
                     ('frame', 'tables', 'overlay', 'emit', 'markers', 'fog',
                      'planets', 'input', 'camera', 'hardware')}
            for frozen, platform in ((False, 'darwin'), (True, 'win32'), (False, 'linux')):
                with self.subTest(frozen=frozen, platform=platform), \
                        patch.object(sys, 'frozen', frozen, create=True), \
                        patch.object(sys, 'platform', platform), \
                        patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '0'}), \
                        patch.object(cpp_window, 'find_binary', return_value='/unused/armada_viewer'), \
                        patch('render_bridge.embedded.EmbeddedWindow') as window, \
                        patch('atexit.register'):
                    cpp_window.spawn(paths, root=str(root), snapshot=str(snapshot), log=Mock())
                    argv = window.call_args.args[0]
                    self.assertEqual(argv[argv.index('--assets') + 1], str(root))
                    self.assertEqual(window.call_args.kwargs['root'], str(root))


if __name__ == '__main__':
    unittest.main()
