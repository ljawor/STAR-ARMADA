"""Private, serialized native C ABI host. No SDL/Pygame imports here."""
from __future__ import annotations
import ctypes
from contextlib import contextmanager
import hmac
import json
import mmap
import os
from pathlib import Path
import socket
import sys
import threading
import time

MAX_MESSAGE = 4096
PARENT_DEATH_EXIT = 70


def process_creation_time(handle=None, *, kernel=None):
    """Read unsigned creation FILETIME without loading any renderer code."""
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    class FileTime(ctypes.Structure):
        _fields_ = [('dwLowDateTime', ctypes.c_uint32), ('dwHighDateTime', ctypes.c_uint32)]
    kernel = kernel if kernel is not None else ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FileTime)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    times = [FileTime() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess() if handle is None else handle,
                                 *(ctypes.byref(value) for value in times)):
        raise RuntimeError('cannot query native worker parent creation time')
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


@contextmanager
def parent_guard(expected, expected_creation=None):
    """Own parent identity independently of the serialized (possibly stuck) ABI.

    Never call renderer code or release its memory from this thread. On parent
    loss terminate the entire process, including a DLL stuck under loader lock.
    """
    if os.getppid() != expected:
        raise RuntimeError('native worker direct parent identity mismatch')
    if os.name != 'nt' and expected_creation is not None:
        raise ValueError('invalid parent_creation_time')
    stop = threading.Event()
    handle = kernel = None
    if os.name == 'nt':
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x100000 | 0x1000, False, expected)  # SYNCHRONIZE | QUERY_LIMITED
        if not handle:
            raise OSError(ctypes.get_last_error(), 'cannot monitor native worker parent')
    thread = None
    try:
        # The creator supplies its original timestamp before Popen. A held handle
        # alone cannot identify a PID already reused before OpenProcess.
        if handle and process_creation_time(handle, kernel=kernel) != expected_creation:
            raise RuntimeError('native worker parent creation time mismatch')
        # Check again with the handle held: PID reuse cannot retarget the wait.
        if os.getppid() != expected or (handle and kernel.WaitForSingleObject(handle, 0) != 258):
            raise RuntimeError('native worker parent is not alive')
        current = kernel.GetCurrentProcess() if handle else None

        def watch():
            while not stop.is_set():
                if handle:
                    status = kernel.WaitForSingleObject(handle, 100)
                    if status == 258:  # WAIT_TIMEOUT
                        continue
                    # Signaled parent (or failed monitor): fail closed. ExitProcess
                    # is unsafe here because a stuck DllMain may own loader lock.
                    kernel.TerminateProcess(current, PARENT_DEATH_EXIT)
                else:
                    if stop.wait(.1):
                        return
                    if os.getppid() == expected:
                        continue
                    os._exit(PARENT_DEATH_EXIT)

        thread = threading.Thread(target=watch, name='native-parent-guard', daemon=True)
        thread.start()
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        if handle:
            kernel.CloseHandle(handle)


def receive(connection, deadline):
    """Bound both total bytes and total time, including partial-line dribbles."""
    data = bytearray()
    while len(data) < MAX_MESSAGE:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('native protocol deadline exceeded')
        connection.settimeout(remaining)
        part = connection.recv(1)
        if not part:
            raise EOFError('native worker disconnected')
        if part == b'\n':
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError('native protocol requires an object')
            return value
        data.extend(part)
    raise ValueError('native protocol message exceeds 4096 bytes')


def send(connection, value, deadline):
    data = json.dumps(value, separators=(',', ':')).encode() + b'\n'
    if len(data) > MAX_MESSAGE:
        raise ValueError('native protocol message exceeds 4096 bytes')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('native protocol deadline exceeded')
    connection.settimeout(remaining)
    connection.sendall(data)


def find_library(root):
    name = 'armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib'
    candidates = [os.environ.get('STAR_ARMADA_CPP_LIBRARY')]
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        candidates.append(str(Path(bundle) / 'cpp' / name))
    candidates.append(str(Path(root) / 'render_cpp' / 'build-w02' / name))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('Build the armada_embedded shared-library target first')


def load_library(path):
    # ctypes.CDLL(path)'s constructor holds the GIL during dlopen/LoadLibrary.
    # Call the system loader through a ctypes foreign function (which releases
    # the GIL), or a stuck DLL initializer would also freeze the parent guard.
    if os.name == 'nt':
        from ctypes import wintypes
        loader = ctypes.WinDLL('kernel32', use_last_error=True)
        loader.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
        loader.LoadLibraryExW.restype = wintypes.HMODULE
        handle = loader.LoadLibraryExW(str(Path(path).resolve()), None, 0x1100)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        loader = ctypes.CDLL(None)
        loader.dlopen.argtypes = [ctypes.c_char_p, ctypes.c_int]
        loader.dlopen.restype = ctypes.c_void_p
        loader.dlerror.argtypes = []
        loader.dlerror.restype = ctypes.c_char_p
        handle = loader.dlopen(os.fsencode(path), os.RTLD_NOW | os.RTLD_LOCAL)
        if not handle:
            raise OSError((loader.dlerror() or b'native library load failed').decode(errors='replace'))
    lib = ctypes.CDLL(path, handle=handle)
    lib.armada_abi_version.argtypes = []
    lib.armada_abi_version.restype = ctypes.c_uint
    if lib.armada_abi_version() != 1:
        raise RuntimeError('Unsupported native renderer ABI')
    for name, args, result in (
        ('open', [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)], ctypes.c_void_p),
        ('frame', [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t], ctypes.c_int),
        ('close', [ctypes.c_void_p], None),
        ('poll', [ctypes.c_void_p], ctypes.c_int),
        ('error', [ctypes.c_void_p], ctypes.c_char_p),
    ):
        function = getattr(lib, 'armada_' + name)
        function.argtypes, function.restype = args, result
    return lib


def configuration(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('invalid native worker configuration path')
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or set(config) != {'port', 'nonce', 'library', 'argv', 'frame', 'width', 'height', 'parent_pid', 'parent_creation_time'}:
        raise ValueError('invalid native worker configuration fields')
    if type(config['parent_pid']) is not int or not 1 <= config['parent_pid'] <= 0xffffffff:
        raise ValueError('invalid parent_pid')
    creation = config['parent_creation_time']
    if (os.name == 'nt' and (type(creation) is not int or not 1 <= creation <= 0xffffffffffffffff)
            or os.name != 'nt' and creation is not None):
        raise ValueError('invalid parent_creation_time')
    if type(config['port']) is not int or not 1 <= config['port'] <= 65535:
        raise ValueError('invalid port')
    if not isinstance(config['nonce'], str) or len(config['nonce']) != 64:
        raise ValueError('invalid nonce')
    for key, low, high in (('width', 320, 7680), ('height', 240, 4320)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError('invalid dimensions')
    argv = config['argv']
    if not isinstance(argv, list) or not 1 <= len(argv) <= 255 or len(argv) % 2 != 1 or any(
            not isinstance(v, str) or '\0' in v or len(v) > 4096 for v in argv):
        raise ValueError('invalid argv')
    for flag, key, default in (('--width', 'width', 1280), ('--height', 'height', 800)):
        values = [argv[i + 1] for i in range(1, len(argv), 2) if argv[i] == flag]
        try:
            if len(values) > 1 or int(values[0] if values else default) != config[key]:
                raise ValueError('inconsistent dimensions')
        except ValueError as exc:
            raise ValueError('inconsistent dimensions') from exc
    for key in ('frame', 'library'):
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute() or not Path(value).is_file():
            raise ValueError('invalid ' + key + ' path')
    frame = Path(config['frame'])
    if frame.is_symlink() or frame.resolve().parent != path.resolve().parent:
        raise ValueError('frame must belong to configuration directory')
    if frame.stat().st_size != config['width'] * config['height'] * 4:
        raise ValueError('invalid frame buffer size')
    return config


def run(path):
    config = configuration(path)
    with parent_guard(config['parent_pid'], config['parent_creation_time']), socket.create_connection(
            ('127.0.0.1', config['port']), timeout=20) as connection:
        send(connection, {'nonce': config['nonce']}, time.monotonic() + 20)
        # Authentication is checked by both peers before touching native state.
        reply = receive(connection, time.monotonic() + 20)
        if not hmac.compare_digest(str(reply.get('nonce', '')), config['nonce']):
            raise ValueError('native worker authentication failed')
        with open(config['frame'], 'r+b') as stream, mmap.mmap(stream.fileno(), 0) as mapping:
            pixels = (ctypes.c_ubyte * len(mapping)).from_buffer(mapping)
            handle = None
            try:
                lib = load_library(config['library'])
                argv = config['argv']
                cleaned = [argv[0]]
                for flag, value in zip(argv[1::2], argv[2::2]):
                    if flag == '--input-ring' or (flag.endswith('-ring') and not Path(value).exists()):
                        continue
                    cleaned.extend((flag, value))
                encoded = (ctypes.c_char_p * len(cleaned))(*(os.fsencode(v) for v in cleaned))
                handle = lib.armada_open(len(cleaned), encoded)
                if not handle:
                    raise RuntimeError('Could not initialize native renderer session')
                send(connection, {'ready': True}, time.monotonic() + 20)
                while True:
                    # An idle parent's EOF ends the worker; no native calls run concurrently.
                    connection.settimeout(None)
                    if not connection.recv(1, socket.MSG_PEEK):
                        break
                    command = receive(connection, time.monotonic() + 20).get('command')
                    if command == 'close':
                        break
                    if command == 'poll':
                        result = {'status': lib.armada_poll(handle)}
                    elif command == 'frame':
                        count = lib.armada_frame(handle, pixels, len(pixels))
                        result = {'count': count}
                        if count != len(pixels):
                            error = lib.armada_error(handle) or b'Unknown native error'
                            result['error'] = error.decode('utf-8', errors='replace')[:512]
                            send(connection, result, time.monotonic() + 2)
                            break  # report BEFORE potentially unbounded native close
                    else:
                        raise ValueError('unknown native command')
                    send(connection, result, time.monotonic() + 20)
            finally:
                if handle:
                    lib.armada_close(handle)
                del pixels


def cli(argv):
    """Early frozen dispatch, or source-module entry. Invalid args never start game."""
    try:
        if len(argv) == 3 and argv[:2] == ['--probe', '--output']:
            library = find_library(Path(__file__).resolve().parents[1])
            load_library(library)
            from game import __version__
            Path(argv[2]).write_text(json.dumps(dict(status='ok', abi=1, version=__version__,
                frozen=bool(getattr(sys, 'frozen', False)), native_library=library)), encoding='utf-8')
        elif len(argv) == 1 and not argv[0].startswith('-'):
            run(argv[0])
        else:
            raise ValueError('expected CONFIG or --probe --output PATH')
    except Exception as exc:
        print(f'Native worker: {exc}', file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    return 0


if __name__ == '__main__':
    raise SystemExit(cli(sys.argv[1:]))
