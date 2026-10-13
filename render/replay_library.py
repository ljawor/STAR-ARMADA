"""Bounded, presentation-only replay metadata. Never reconstruct game state."""
from datetime import datetime, timezone
import json
import os

HEADER_BYTES = 65536
_WINDOWS = os.name == 'nt'


def _open_folder(folder):
    """Pin both user directory and replay directory without following either link."""
    folder = os.path.abspath(folder)
    if os.open not in os.supports_dir_fd or not all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW')):
        raise OSError('Safe replay deletion unavailable on this platform (directory handles required)')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(os.path.dirname(folder), flags)
    try:
        return os.open(os.path.basename(folder), flags, dir_fd=parent)
    finally:
        os.close(parent)


def delete_selected(folder, path):
    """Delete only a direct regular JSON child through no-follow owned handles."""
    import stat
    folder = os.path.abspath(folder)
    if not isinstance(path, str) or os.path.dirname(os.path.abspath(path)) != folder:
        raise OSError('Replay is outside the replay directory')
    name = os.path.basename(path)
    if not name.endswith('.json'):
        raise OSError('Not a replay JSON file')
    if _WINDOWS:
        from .replay_delete_windows import Folder
        with Folder(folder) as native:
            native.delete(name)
        return
    fd = _open_folder(folder)
    try:
        if not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
            raise OSError('Refusing symlink or non-regular replay')
        os.unlink(name, dir_fd=fd)
    finally:
        os.close(fd)


def delete_all(folder):
    """Stream every direct regular JSON child, independent of browser caps."""
    import stat
    if _WINDOWS:
        from .replay_delete_windows import Folder
        with Folder(os.path.abspath(folder)) as native:
            return native.delete_all()
    deleted, failed, first_error = 0, 0, ''
    fd = _open_folder(folder)
    try:
        with os.scandir(fd) as entries:
            for entry in entries:
                if not entry.name.endswith('.json'):
                    continue
                try:
                    if not stat.S_ISREG(os.stat(entry.name, dir_fd=fd, follow_symlinks=False).st_mode):
                        continue
                    os.unlink(entry.name, dir_fd=fd)
                    deleted += 1
                except OSError as exc:
                    failed += 1
                    if not first_error:
                        first_error = str(exc)[:120]
    finally:
        os.close(fd)
    return deleted, failed, first_error


def metadata(path):
    """Read a bounded JSON prefix; retain complete top-level fields before corruption."""
    info = {}
    import stat
    file_stat = os.stat(path, follow_symlinks=False)
    stamp = file_stat.st_mtime
    source = 'file time'
    try:
        if not stat.S_ISREG(file_stat.st_mode):
            raise OSError('Refusing non-regular metadata source')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            prefix = stream.read(HEADER_BYTES).decode('utf-8', errors='replace')
        decoder = json.JSONDecoder()
        pos = len(prefix) - len(prefix.lstrip())
        if prefix[pos:pos + 1] != '{':
            raise ValueError('Not a JSON object')
        pos += 1
        for _ in range(64):
            while pos < len(prefix) and prefix[pos].isspace():
                pos += 1
            if prefix[pos:pos + 1] == '}':
                break
            key, pos = decoder.raw_decode(prefix, pos)
            while pos < len(prefix) and prefix[pos].isspace():
                pos += 1
            if prefix[pos:pos + 1] != ':':
                break
            pos += 1
            while pos < len(prefix) and prefix[pos].isspace():
                pos += 1
            value, pos = decoder.raw_decode(prefix, pos)
            if (key in ('created_utc', 'mode', 'game_version') and isinstance(value, str)
                    and len(value) <= 128) or (key == 'version' and type(value) is int
                                             and 0 <= value <= 9999):
                info[key] = value
            while pos < len(prefix) and prefix[pos].isspace():
                pos += 1
            if prefix[pos:pos + 1] != ',':
                break
            pos += 1
    except (OSError, ValueError, RecursionError):
        pass
    try:
        created = datetime.fromisoformat(info['created_utc'].replace('Z', '+00:00'))
        if created.tzinfo is not None:
            stamp = created.timestamp()
            source = 'recorded'
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        pass
    try:
        label = datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except (ValueError, OSError, OverflowError):
        label = 'Unknown time'
    return stamp, f'{label} / {source}', info
