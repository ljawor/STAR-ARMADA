"""Windows deletion policy tests plus mandatory real-kernel acceptance tests.

Portable tests exercise policy/resource ownership, not Windows syscall correctness.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class WindowsBackendDiscoveryTests(unittest.TestCase):
    def test_native_backend_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec('render.replay_delete_windows'))


class WindowsDispatchTests(unittest.TestCase):
    def test_selected_routes_to_native_handle_backend_without_posix_calls(self):
        from render.replay_library import delete_selected
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'replays')
            path = os.path.join(folder, 'keep.json')
            with patch('render.replay_library._WINDOWS', True, create=True), \
                    patch('render.replay_delete_windows.Folder') as native, \
                    patch('render.replay_library._open_folder', side_effect=AssertionError('POSIX used')):
                delete_selected(folder, path)
            native.assert_called_once_with(folder)
            native.return_value.__enter__.return_value.delete.assert_called_once_with('keep.json')

    def test_all_routes_to_native_and_preserves_result_contract(self):
        from render.replay_library import delete_all
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'replays')
            with patch('render.replay_library._WINDOWS', True, create=True), \
                    patch('render.replay_delete_windows.Folder') as native, \
                    patch('render.replay_library._open_folder', side_effect=AssertionError('POSIX used')):
                native.return_value.__enter__.return_value.delete_all.return_value = (7, 2, 'locked')
                self.assertEqual(delete_all(folder), (7, 2, 'locked'))
            native.assert_called_once_with(folder)


class WindowsPolicyTests(unittest.TestCase):
    def test_rejects_ambiguous_names_and_nonlocal_roots(self):
        from render.replay_delete_windows import _components, _child_name
        self.assertEqual(_components(r'C:\users\pilot\replays'), ('C:\\', ['users', 'pilot', 'replays']))
        self.assertEqual(_child_name('match-α.json'), 'match-α.json')
        for name in ('../x.json', r'..\x.json', 'x:stream.json', 'x.json ', 'x.json.', '', '.', '..', 'x\0.json'):
            with self.subTest(name=name), self.assertRaises(OSError):
                _child_name(name)
        for root in (r'\\server\share\replays', r'\\?\C:\replays', r'C:\alias.\replays', r'C:\alias \replays'):
            with self.subTest(root=root), self.assertRaises(OSError):
                _components(root)


class HandlePolicyTests(unittest.TestCase):
    class Api:
        def __init__(self):
            self.handles = []
            self.closed = []
            self.removed = []
            self.children = [('ok.json', 0), ('link.json', 0x400), ('dir.json', 0x10), ('keep.txt', 0)]
            self.fail_at: str | None = None
            self.fail_close: int | None = None
            self.child_regular = True

        def open_root(self, root):
            return self.open_dir(None, root)

        def open_dir(self, parent, name):
            if name == self.fail_at:
                raise OSError('directory open failed')
            handle = len(self.handles) + 1
            self.handles.append(handle)
            return handle

        def close(self, handle):
            self.closed.append(handle)
            if handle == self.fail_close:
                raise OSError('close failed')

        def entries(self, handle):
            yield from self.children

        def open_child(self, parent, name):
            if name == self.fail_at:
                raise OSError('child open failed')
            handle = len(self.handles) + 1
            self.handles.append(handle)
            return handle

        def regular(self, handle):
            return self.child_regular

        def dispose(self, handle):
            self.removed.append(handle)

    def test_selected_owns_and_releases_every_handle(self):
        from render import replay_delete_windows as backend
        self.assertTrue(hasattr(backend, 'Folder'), 'missing native folder ownership policy')
        api = self.Api()
        with backend.Folder(r'C:\users\pilot\replays', api=api) as folder:
            folder.delete('ok.json')
        self.assertEqual(api.removed, [5])
        self.assertEqual(api.closed, [5, 4, 3, 2, 1])

    def test_partial_directory_open_releases_acquired_handles(self):
        from render.replay_delete_windows import Folder
        api = self.Api()
        api.fail_at = 'pilot'
        with self.assertRaisesRegex(OSError, 'directory open failed'):
            with Folder(r'C:\users\pilot\replays', api=api):
                self.fail('unsafe directory opened')
        self.assertEqual(api.closed, [2, 1])

    def test_close_failure_does_not_skip_other_handles_or_mask_original(self):
        from render.replay_delete_windows import Folder
        api = self.Api()
        api.fail_close = 3
        with self.assertRaisesRegex(OSError, 'original'):
            with Folder(r'C:\users\pilot\replays', api=api):
                raise OSError('original')
        self.assertEqual(api.closed, [4, 3, 2, 1])

    def test_all_skips_unsafe_types_counts_partial_failure_and_bounds_error(self):
        from render.replay_delete_windows import Folder
        api = self.Api()
        api.children.append(('fail.json', 0))
        api.fail_at = 'fail.json'
        with Folder(r'C:\users\pilot\replays', api=api) as folder:
            self.assertEqual(folder.delete_all(), (1, 1, 'child open failed'))
        self.assertEqual(api.closed, [5, 4, 3, 2, 1])

    def test_child_changed_to_reparse_after_enumeration_is_not_disposed(self):
        from render.replay_delete_windows import Folder
        api = self.Api()
        api.child_regular = False
        with Folder(r'C:\users\pilot\replays', api=api) as folder:
            with self.assertRaises(OSError):
                folder.delete('ok.json')
            self.assertEqual(folder.delete_all()[:2], (0, 1))
        self.assertEqual(api.removed, [])
        self.assertEqual(set(api.handles), set(api.closed))


class ApiBindingTests(unittest.TestCase):
    def test_windows_abi_uses_fixed_width_fields_and_pointer_alignment(self):
        import ctypes
        from render import replay_delete_windows as backend
        self.assertTrue(hasattr(backend, '_UnicodeString'), 'missing native ABI declarations')
        pointer = ctypes.sizeof(ctypes.c_void_p)
        self.assertEqual(backend._UnicodeString.Buffer.offset, pointer)
        self.assertEqual(ctypes.sizeof(backend._UnicodeString), 2 * pointer)
        self.assertEqual(ctypes.sizeof(backend._ObjectAttributes), 6 * pointer)
        self.assertEqual(ctypes.sizeof(backend._IoStatusBlock), 2 * pointer)

    def test_native_open_requests_no_reparse_single_handle_policy(self):
        import ctypes
        from render import replay_delete_windows as backend
        api = backend._Api.__new__(backend._Api)  # native call boundary only; NOT a native acceptance run
        captured = {}
        def create(out, access, attrs_pointer, io, allocation, attributes,
                   sharing, disposition, options, ea, ea_size):
            attrs = ctypes.cast(attrs_pointer, ctypes.POINTER(backend._ObjectAttributes)).contents
            string = attrs.ObjectName.contents
            captured.update(access=access, parent=attrs.RootDirectory, flags=attrs.Attributes,
                            sharing=sharing, disposition=disposition, options=options,
                            name=ctypes.string_at(string.Buffer, string.Length).decode('utf-16-le'))
            ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p)).contents.value = 456
            return 0
        api.create = create
        self.assertEqual(api.open_child(123, 'match-α.json'), 456)
        self.assertEqual(captured, dict(access=0x110080, parent=123, flags=0x1040,
                                       sharing=1, disposition=1, options=0x200020, name='match-α.json'))

    def test_native_api_is_guarded_on_nonwindows_hosts(self):
        from render import replay_delete_windows as backend
        self.assertTrue(hasattr(backend, '_Api'), 'missing native Windows syscall implementation')
        if os.name != 'nt':
            with self.assertRaisesRegex(OSError, 'native Windows'):
                backend._Api()


class DirectoryBufferTests(unittest.TestCase):
    def test_parses_linked_utf16_records_with_fixed_windows_offsets(self):
        import struct
        from render import replay_delete_windows as backend
        self.assertTrue(hasattr(backend, '_directory_records'), 'missing directory buffer decoder')
        def record(name, attrs, following):
            encoded = name.encode('utf-16-le')
            size = (68 + len(encoded) + 7) & ~7
            data = bytearray(size)
            struct.pack_into('<I', data, 0, size if following else 0)
            struct.pack_into('<II', data, 56, attrs, len(encoded))
            data[68:68 + len(encoded)] = encoded
            return bytes(data)
        data = record('match-α.json', 0, True) + record('link.json', 0x400, False)
        self.assertEqual(list(backend._directory_records(data)), [('match-α.json', 0), ('link.json', 0x400)])
        for bad in (b'', b'\0' * 68, b'\xff' * 80):
            with self.subTest(bad=bad), self.assertRaises(OSError):
                list(backend._directory_records(bad))


@unittest.skipUnless(os.name == 'nt', 'native Windows kernel required; NOT accepted on macOS')
class NativeWindowsDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'replays'
        self.folder.mkdir()

    def test_selected_and_uncapped_all_delete_real_files(self):
        from render.replay_library import delete_selected, delete_all
        selected = self.folder / 'match-α.json'
        selected.write_text('{bad')
        delete_selected(str(self.folder), str(selected))
        self.assertFalse(selected.exists())
        for i in range(4101):
            (self.folder / f'{i}.json').write_text('{bad')
        (self.folder / 'keep.txt').write_text('preserve')
        (self.folder / 'nested.json').mkdir()
        (self.folder / 'nested.json' / 'keep.json').write_text('preserve')
        self.assertEqual(delete_all(str(self.folder)), (4101, 0, ''))
        self.assertEqual({p.name for p in self.folder.iterdir()}, {'keep.txt', 'nested.json'})

    def junction(self, link, target):
        # Junctions do not require Developer Mode / symbolic-link privileges.
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True,
                       capture_output=True, text=True)
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)

    def test_replay_user_and_ancestor_junctions_are_rejected(self):
        from render.replay_library import delete_selected, delete_all
        outside = self.root / 'outside'
        outside.mkdir()
        replay = outside / 'keep.json'
        replay.write_text('preserve')
        alias = self.root / 'alias'
        self.junction(alias, outside)
        (outside / 'replays').mkdir()
        (outside / 'replays' / 'keep.json').write_text('preserve')
        (outside / 'user' / 'replays').mkdir(parents=True)
        (outside / 'user' / 'replays' / 'keep.json').write_text('preserve')
        for folder in (alias, alias / 'replays', alias / 'user' / 'replays'):
            with self.subTest(folder=folder):
                with self.assertRaises(OSError):
                    delete_selected(str(folder), str(folder / 'keep.json'))
                with self.assertRaises(OSError):
                    delete_all(str(folder))
        self.assertEqual(replay.read_text(), 'preserve')
        self.assertEqual((outside / 'replays' / 'keep.json').read_text(), 'preserve')
        self.assertEqual((outside / 'user' / 'replays' / 'keep.json').read_text(), 'preserve')

    def test_child_junction_and_outside_selected_are_preserved(self):
        from render.replay_library import delete_selected, delete_all
        outside = self.root / 'outside'
        outside.mkdir()
        replay = outside / 'keep.json'
        replay.write_text('preserve')
        child = self.folder / 'link.json'
        self.junction(child, outside)
        with self.assertRaises(OSError):
            delete_selected(str(self.folder), str(child))
        with self.assertRaises(OSError):
            delete_selected(str(self.folder), str(replay))
        self.assertEqual(delete_all(str(self.folder)), (0, 0, ''))
        self.assertTrue(child.is_dir())
        self.assertEqual(replay.read_text(), 'preserve')

    def test_readonly_failure_is_reported_and_resources_are_released(self):
        from render.replay_library import delete_selected, delete_all
        replay = self.folder / 'locked.json'
        replay.write_text('preserve')
        os.chmod(replay, 0o444)
        self.addCleanup(lambda: os.chmod(replay, 0o666) if replay.exists() else None)
        with self.assertRaises(OSError):
            delete_selected(str(self.folder), str(replay))
        deleted, failed, error = delete_all(str(self.folder))
        self.assertEqual((deleted, failed), (0, 1))
        self.assertTrue(error)
        os.chmod(replay, 0o666)
        moved = self.root / 'moved'
        self.folder.rename(moved)  # leaked deny-delete directory handles make this fail
        moved.rename(self.folder)
        delete_selected(str(self.folder), str(replay))
        self.assertFalse(replay.exists())

    def test_open_handles_block_directory_and_child_replacement(self):
        from render.replay_delete_windows import Folder
        replay = self.folder / 'keep.json'
        replay.write_text('preserve')
        with Folder(str(self.folder)) as folder:
            with self.assertRaises(OSError):
                self.folder.rename(self.root / 'moved')
            with self.assertRaises(OSError):
                self.root.rename(self.root.with_name(self.root.name + '-moved'))
            handle = folder.api.open_child(folder.handle, replay.name)
            try:
                with self.assertRaises(OSError):
                    replay.rename(self.folder / 'moved.json')
            finally:
                folder.api.close(handle)
        replay.rename(self.folder / 'moved.json')
        self.folder.rename(self.root / 'moved')

    def test_file_symlink_is_never_deleted_or_followed(self):
        from render.replay_library import delete_selected, delete_all
        outside = self.root / 'outside.json'
        outside.write_text('preserve')
        link = self.folder / 'link.json'
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f'Windows symlink privilege unavailable: {exc}; junction gates still mandatory')
        with self.assertRaises(OSError):
            delete_selected(str(self.folder), str(link))
        self.assertEqual(delete_all(str(self.folder)), (0, 0, ''))
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_text(), 'preserve')
