"""Fail-closed managed-save namespace; no simulation reconstruction while browsing."""
from datetime import datetime, timezone
import json
import os
import re
import stat

from .replay_library import _open_folder

HEADER_BYTES = 65536
MAX_SAVE_BYTES = 64 * 1024 * 1024
BROWSE_CAP = 1000
SCAN_CAP = 4096
_WINDOWS = os.name == 'nt'
_NAMESPACE = re.compile(r'(?:quicksave|autosave|autosave_[0-9]+)\.json', re.ASCII)


def managed_name(name):
    """Only exact production save names; unknown/manual/protected JSON is excluded."""
    return isinstance(name, str) and _NAMESPACE.fullmatch(name) is not None


def browse(folder):
    """Bounded metadata only; corrupt managed files remain visible and removable."""
    folder = os.path.abspath(folder)
    found = []
    notice = ''
    try:
        # Pin no-follow directory components even for read-only browsing.
        if _WINDOWS:
            from .replay_delete_windows import Folder
            with Folder(folder) as native:
                for index, (name, attrs) in enumerate(native.api.entries(native.handle)):
                    if index >= SCAN_CAP:
                        notice = 'Scan limit: first 4096 entries; Delete ALL still covers every managed save.'
                        break
                    if managed_name(name) and not attrs & (0x10 | 0x400):
                        try:
                            with open_selected(folder, os.path.join(folder, name)) as stream:
                                info = stream_metadata(stream, name)
                        except OSError as exc:
                            info = _label(name, 0, 'Metadata unavailable; Load retries safely.')
                            notice = 'Some metadata unavailable: ' + str(exc)[:140]
                        found.append((name, info))
        else:
            fd = _open_folder(folder)
            try:
                with os.scandir(fd) as entries:
                    for index, entry in enumerate(entries):
                        if index >= SCAN_CAP:
                            notice = 'Scan limit: first 4096 entries; Delete ALL still covers every managed save.'
                            break
                        if managed_name(entry.name) and entry.is_file(follow_symlinks=False):
                            try:
                                info = metadata(fd, entry.name)
                            except OSError as exc:
                                info = _label(entry.name, entry.stat(follow_symlinks=False).st_mtime,
                                              'Metadata unavailable; Load retries safely.')
                                notice = 'Some metadata unavailable: ' + str(exc)[:140]
                            found.append((entry.name, info))
            finally:
                os.close(fd)
        rows = {}
        for name, info in found:
            path = os.path.join(folder, name)
            rows[path] = info
        paths = sorted(rows, key=lambda p: (-rows[p][0], os.path.basename(p)))[:BROWSE_CAP]
        if len(rows) > BROWSE_CAP and not notice:
            notice = 'Browser limit: newest 1000 saves; Delete ALL still covers every managed save.'
        return {p: rows[p] for p in paths}, notice
    except FileNotFoundError:
        return {}, ''
    except OSError as exc:
        return {}, 'Cannot browse saves: ' + str(exc)[:180]


def selected_name(folder, path):
    folder = os.path.abspath(folder)
    if (not isinstance(path, str) or os.path.dirname(os.path.abspath(path)) != folder
            or not managed_name(os.path.basename(path))):
        raise OSError('Not a direct managed saved game')
    return os.path.basename(path)


def open_selected(folder, path):
    """Return a read-only regular-file stream through pinned no-follow handles."""
    name = selected_name(folder, path)
    if _WINDOWS:
        import msvcrt
        from .replay_delete_windows import Folder
        with Folder(os.path.abspath(folder)) as native:
            handle = native.api._open(native.handle, name, 0x100081)
            try:
                if not native.api.regular(handle):
                    raise OSError('Refusing reparse point or non-regular save')
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
                handle = None  # descriptor owns the native handle now
            finally:
                if handle is not None:
                    native.api.close(handle)
            # The child handle denies write/delete sharing; keep it for the read.
            return os.fdopen(fd, 'rb')
    folder_fd = _open_folder(folder)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder_fd)
    finally:
        os.close(folder_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('Refusing non-regular save')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def delete_selected(folder, path):
    """Revalidate root and exact namespace before delegating pinned single deletion."""
    from .replay_library import delete_selected as safe_delete
    if not isinstance(path, str) or not managed_name(os.path.basename(path)):
        raise OSError('Not a managed saved game')
    safe_delete(folder, path)


def delete_all(folder):
    """Stream the entire pinned directory, not the capped browser snapshot."""
    deleted, failed, error = 0, 0, ''
    if _WINDOWS:
        from .replay_delete_windows import Folder
        with Folder(os.path.abspath(folder)) as native:
            for name, attrs in native.api.entries(native.handle):
                if not managed_name(name) or attrs & (0x10 | 0x400):
                    continue
                try:
                    native.delete(name)
                    deleted += 1
                except OSError as exc:
                    failed += 1
                    error = error or str(exc)[:120]
    else:
        fd = _open_folder(folder)
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    if not managed_name(entry.name):
                        continue
                    try:
                        if not stat.S_ISREG(os.stat(entry.name, dir_fd=fd, follow_symlinks=False).st_mode):
                            continue
                        os.unlink(entry.name, dir_fd=fd)
                        deleted += 1
                    except OSError as exc:
                        failed += 1
                        error = error or str(exc)[:120]
        finally:
            os.close(fd)
    return deleted, failed, error


def _label(name, stamp, detail):
    kind = 'Quick' if name == 'quicksave.json' else 'Autosave'
    try:
        label = datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except (ValueError, OSError, OverflowError):
        label = 'Unknown time UTC'
    return stamp, label + ' / ' + kind, kind + ' / ' + detail


def metadata(folder_fd, name):
    """Read at most 64 KiB via pinned directory; never decode an unbounded row."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder_fd)
    with os.fdopen(fd, 'rb') as stream:
        return stream_metadata(stream, name)


def stream_metadata(stream, name):
    file_stat = os.fstat(stream.fileno())
    if not stat.S_ISREG(file_stat.st_mode):
        raise OSError('Refusing non-regular save')
    stamp = file_stat.st_mtime
    detail = 'State validated only when Load is pressed.'
    prefix = stream.read(HEADER_BYTES)
    if len(prefix) < HEADER_BYTES:
        try:
            data = json.loads(prefix)
            if not isinstance(data, dict) or not isinstance(data.get('players'), (list, dict)):
                detail = 'Corrupt or unsupported save; Load will report the error.'
            else:
                detail = 'Canonical runtime state' if 'runtime_state' in data else 'Legacy save: future-state may be unavailable.'
        except (ValueError, RecursionError, UnicodeError):
            detail = 'Corrupt JSON; still removable.'
    return _label(name, stamp, detail)
