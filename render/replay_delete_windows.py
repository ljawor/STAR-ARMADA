"""Native Windows replay deletion (stdlib only; no pathname-based deletion).

Windows 8+ local drive paths only. NtCreateFile opens ONE component relative to
an owned parent handle with FILE_OPEN_REPARSE_POINT, then attributes are checked.
All ancestors stay open without write/delete sharing until the operation ends.
Handle-relative enumeration and disposition never resolve the path again.
"""
import ctypes as _ct
import ntpath
import os
import re

# Never use c_long / wintypes.DWORD: their width differs on non-Windows hosts.
_U32 = _ct.c_uint32
_HANDLE = _ct.c_void_p


class _UnicodeString(_ct.Structure):
    _fields_ = [('Length', _ct.c_uint16), ('MaximumLength', _ct.c_uint16),
                ('Buffer', _HANDLE)]


class _ObjectAttributes(_ct.Structure):
    _fields_ = [('Length', _U32), ('RootDirectory', _HANDLE),
                ('ObjectName', _ct.POINTER(_UnicodeString)), ('Attributes', _U32),
                ('SecurityDescriptor', _HANDLE), ('SecurityQualityOfService', _HANDLE)]


class _IoStatusBlock(_ct.Structure):
    # The first field is a union of NTSTATUS (32 bits) and a pointer.
    _fields_ = [('StatusOrPointer', _HANDLE), ('Information', _ct.c_size_t)]


class _Api:
    """Small, typed native boundary. Missing APIs/errors never fall back to unlink."""
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Safe replay deletion requires native Windows')
        try:
            self.kernel = _ct.WinDLL('kernel32', use_last_error=True)
            self.ntdll = _ct.WinDLL('ntdll', use_last_error=True)
            self.create = self.ntdll.NtCreateFile
            self.create.argtypes = [_ct.POINTER(_HANDLE), _U32,
                                    _ct.POINTER(_ObjectAttributes), _ct.POINTER(_IoStatusBlock),
                                    _HANDLE, _U32, _U32, _U32, _U32, _HANDLE, _U32]
            self.create.restype = _ct.c_int32
            self.to_error = self.ntdll.RtlNtStatusToDosError
            self.to_error.argtypes = [_ct.c_int32]
            self.to_error.restype = _U32
            self.get_info = self.kernel.GetFileInformationByHandleEx
            self.get_info.argtypes = [_HANDLE, _ct.c_int32, _HANDLE, _U32]
            self.get_info.restype = _ct.c_int32
            self.set_info = self.kernel.SetFileInformationByHandle
            self.set_info.argtypes = [_HANDLE, _ct.c_int32, _HANDLE, _U32]
            self.set_info.restype = _ct.c_int32
            self.file_type = self.kernel.GetFileType
            self.file_type.argtypes = [_HANDLE]
            self.file_type.restype = _U32
            self.final_path = self.kernel.GetFinalPathNameByHandleW
            self.final_path.argtypes = [_HANDLE, _ct.c_wchar_p, _U32, _U32]
            self.final_path.restype = _U32
            self.close_handle = self.kernel.CloseHandle
            self.close_handle.argtypes = [_HANDLE]
            self.close_handle.restype = _ct.c_int32
        except (AttributeError, OSError) as exc:
            raise OSError('Safe replay deletion unavailable: native Windows handle APIs required') from exc

    def close(self, handle):
        if not self.close_handle(handle):
            raise _ct.WinError(_ct.get_last_error())

    def _open(self, parent, name, access):
        encoded = name.encode('utf-16-le', errors='surrogatepass')
        if len(encoded) > 65532:
            raise OSError('Windows replay name too long')
        buffer = _ct.create_string_buffer(encoded + b'\0\0')
        string = _UnicodeString(len(encoded), len(encoded) + 2, _ct.addressof(buffer))
        # OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE: fail on any name-parse reparse,
        # including a DOS drive mapping which itself resolves through a junction.
        attrs = _ObjectAttributes(_ct.sizeof(_ObjectAttributes), parent,
                                  _ct.pointer(string), 0x1040, None, None)
        handle, status_block = _HANDLE(), _IoStatusBlock()
        # FILE_OPEN only; FILE_SHARE_READ only (deny write/delete/replacement).
        # FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT, no delete-on-close.
        status = self.create(_ct.byref(handle), access, _ct.byref(attrs),
                             _ct.byref(status_block), None, 0, 1, 1, 0x200020, None, 0)
        if status != 0:
            # Synchronous handles never require waiting for STATUS_PENDING.
            if handle.value:
                _close_handles(self, [handle.value], suppress=True)
            raise _ct.WinError(self.to_error(status))
        if not handle.value:
            raise OSError('Windows returned an invalid replay handle')
        return handle.value

    def _attrs(self, handle):
        # FILE_ATTRIBUTE_TAG_INFO: DWORD FileAttributes, DWORD ReparseTag.
        info = (_U32 * 2)()
        if not self.get_info(handle, 9, _ct.byref(info), _ct.sizeof(info)):
            raise _ct.WinError(_ct.get_last_error())
        if self.file_type(handle) != 1:  # FILE_TYPE_DISK, not pipe/device/unknown
            raise OSError('Refusing non-disk replay object')
        return info[0]

    def _directory(self, handle):
        try:
            attrs = self._attrs(handle)
            if not attrs & 0x10 or attrs & 0x400:
                raise OSError('Refusing reparse point or non-directory replay ancestor')
            return handle
        except BaseException:
            _close_handles(self, [handle], suppress=True)
            raise

    def open_root(self, root):
        # Only the drive root is absolute. Every subsequent name is relative to
        # an already checked handle; no unvalidated multi-component traversal.
        handle = self._directory(self._open(None, '\\??\\' + root, 0x100081))
        try:
            buffer = _ct.create_unicode_buffer(128)
            count = self.final_path(handle, buffer, len(buffer), 1)  # VOLUME_NAME_GUID
            if count == 0:
                raise _ct.WinError(_ct.get_last_error())
            if count >= len(buffer) or not re.fullmatch(r'\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\', buffer.value):
                raise OSError('Safe replay deletion requires a real local volume root (no mapped/SUBST drive)')
            return handle
        except BaseException:
            _close_handles(self, [handle], suppress=True)
            raise

    def open_dir(self, parent, name):
        return self._directory(self._open(parent, _child_name(name), 0x100081))

    def open_child(self, parent, name):
        # SYNCHRONIZE | DELETE | FILE_READ_ATTRIBUTES; never read JSON payloads.
        return self._open(parent, _child_name(name), 0x110080)

    def regular(self, handle):
        return not self._attrs(handle) & (0x10 | 0x400)

    def dispose(self, handle):
        delete_file = _ct.c_ubyte(1)  # FILE_DISPOSITION_INFO uses BOOLEAN, NOT BOOL.
        if not self.set_info(handle, 4, _ct.byref(delete_file), _ct.sizeof(delete_file)):
            raise _ct.WinError(_ct.get_last_error())

    def entries(self, handle):
        first = True
        while True:
            buffer = _ct.create_string_buffer(65536)
            info_class = 15 if first else 14  # FileFullDirectory[Restart]Info
            if not self.get_info(handle, info_class, buffer, len(buffer)):
                error = _ct.get_last_error()
                if error == 18:  # ERROR_NO_MORE_FILES
                    return
                raise _ct.WinError(error)
            first = False
            yield from _directory_records(buffer.raw)


def _child_name(name):
    if (not isinstance(name, str) or not name or name in ('.', '..')
            or any(char in name for char in '\\/:\0') or name.endswith((' ', '.'))):
        raise OSError('Refusing ambiguous or non-direct replay name')
    return name


def _components(path):
    if not isinstance(path, str) or '\0' in path:
        raise OSError('Refusing invalid replay directory')
    drive, tail = ntpath.splitdrive(path)
    if (len(drive) != 2 or not drive[0].isalpha() or drive[1] != ':'
            or not tail.startswith('\\')):
        raise OSError('Safe replay deletion requires a local absolute drive path')
    names = tail[1:].split('\\')
    return drive + '\\', [_child_name(name) for name in names]


def _close_handles(api, handles, suppress=False):
    error = None
    while handles:
        handle = handles.pop()
        try:
            api.close(handle)
        except OSError as exc:
            if error is None:
                error = exc
    if error is not None and not suppress:
        raise error


class Folder:
    """Own every directory handle, keeping the complete ancestor chain pinned."""
    def __init__(self, path, api=None):
        self.root, self.names = _components(path)
        self.api = api if api is not None else _Api()
        self.handles = []
        self.handle = None

    def __enter__(self):
        try:
            self.handles.append(self.api.open_root(self.root))
            for name in self.names:
                self.handles.append(self.api.open_dir(self.handles[-1], name))
            self.handle = self.handles[-1]
            return self
        except BaseException:
            _close_handles(self.api, self.handles, suppress=True)
            raise

    def __exit__(self, exc_type, exc, traceback):
        self.handle = None
        _close_handles(self.api, self.handles, suppress=exc_type is not None)

    def delete_all(self):
        if self.handle is None:
            raise OSError('Replay folder is closed')
        deleted, failed, first_error = 0, 0, ''
        for name, attrs in self.api.entries(self.handle):
            if not name.endswith('.json') or attrs & (0x10 | 0x400):
                continue
            try:
                self.delete(name)
                deleted += 1
            except OSError as exc:
                failed += 1
                if not first_error:
                    first_error = str(exc)[:120]
        return deleted, failed, first_error

    def delete(self, name):
        import sys
        name = _child_name(name)
        if not name.endswith('.json') or self.handle is None:
            raise OSError('Not a replay JSON file or folder is closed')
        handle = self.api.open_child(self.handle, name)
        try:
            if not self.api.regular(handle):
                raise OSError('Refusing reparse point or non-regular replay')
            self.api.dispose(handle)
        finally:
            _close_handles(self.api, [handle], suppress=sys.exc_info()[0] is not None)


def _directory_records(data):
    """Decode FILE_FULL_DIR_INFO (fixed Windows widths, 8-byte record alignment)."""
    import struct
    offset = 0
    while True:
        if len(data) - offset < 68:
            raise OSError('Invalid Windows directory information')
        following = struct.unpack_from('<I', data, offset)[0]
        attrs, length = struct.unpack_from('<II', data, offset + 56)
        end = offset + 68 + length
        if not length or length % 2 or end > len(data):
            raise OSError('Invalid Windows directory filename')
        if following and (following % 8 or following < 68 + length
                          or offset + following + 68 > len(data)):
            raise OSError('Invalid Windows directory record offset')
        try:
            name = data[offset + 68:end].decode('utf-16-le', errors='surrogatepass')
        except UnicodeError as exc:
            raise OSError('Invalid Windows directory filename') from exc
        yield name, attrs
        if not following:
            return
        offset += following
