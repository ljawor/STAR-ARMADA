"""Start and stop the native window as a child process of the game.

`main.py --renderer cpp` runs the match here and the display there: this module launches
`render_cpp/build-w02/armada_viewer` against the rings a `LiveSession` publishes, and stops it
when the game exits. The window is a *display*: it reads rings and writes an input ring, and it is
killed with the game rather than outliving it.

The window insists on an offline snapshot even in live mode, because that is where its mesh
catalogue comes from (an asset list, not a scene). `STAR_ARMADA_CPP_SNAPSHOT` names one; without it
the session still publishes, and the message says so rather than pretending a window is up.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import time

DEFAULT_BINARY = os.path.join(
    'render_cpp', 'build-w02', 'armada_viewer.exe' if os.name == 'nt' else 'armada_viewer')
SNAPSHOT_NAME = 'catalogue.snap'


def ensure_snapshot(root: str, directory: str, log=print) -> str | None:
    """A snapshot for the window's mesh catalogue, made once if the user has not supplied one.

    The window loads mesh bindings from an offline snapshot even in live mode: the rings carry
    transforms and a binding id, not geometry. Asking a player to export one by hand before the
    renderer will draw was the wrong shape of requirement - so the catalogue is built here from the
    approved assets, once, and reused while the asset registry is older than it.
    """
    supplied = os.environ.get('STAR_ARMADA_CPP_SNAPSHOT')
    if supplied and os.path.isfile(supplied):
        return supplied

    # The catalogue that ships with the game: the approved meshes, so a player never has to export
    # anything before the renderer will draw.
    shipped = os.path.join(root, 'assets', 'cpp', SNAPSHOT_NAME)
    if os.path.isfile(shipped):
        return shipped

    path = os.path.join(directory, SNAPSHOT_NAME)
    registry = os.path.join(root, 'assets', 'models', 'registry.json')
    try:
        fresh = (os.path.isfile(path) and os.path.isfile(registry)
                 and os.path.getmtime(path) >= os.path.getmtime(registry))
    except OSError:
        fresh = False
    if fresh:
        return path

    started = time.perf_counter()
    try:
        # In a child process, not in-process: building the catalogue changes the model selection, and
        # this game already has a session open ("Model selection changes require a session boundary
        # with renderers closed").
        import subprocess
        import sys
        script = os.path.join(root, 'tools', 'render', 'dump_snapshot.py')
        result = subprocess.run([sys.executable, script, '--fixture', 'four-player-combat-v1',
                                 '--catalogue', '--out', path],
                                cwd=root, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip().splitlines()[-1][:200])
    except Exception as exc:                      # a missing build or a broken asset tree
        log(f'cpp window: could not build the mesh catalogue ({exc}); the window was not started')
        return None
    log(f'cpp window: mesh catalogue built in {(time.perf_counter() - started) * 1000:.0f} ms '
        f'-> {path}')
    return path if os.path.isfile(path) else None


def find_binary(root: str) -> str | None:
    """The viewer, if this build has one. A missing viewer is not an error: the game runs.

    A frozen bundle (`star_armada.spec`) ships the binary and its shaders under `cpp/` inside the
    archive, so `root` alone is not enough there: the bundle's own directory is searched first,
    then the source tree's build directory. `STAR_ARMADA_CPP_VIEWER` still wins over both.
    """
    import sys
    candidates = [os.environ.get('STAR_ARMADA_CPP_VIEWER')]
    bundle = getattr(sys, '_MEIPASS', None)
    filename = 'armada_viewer.exe' if sys.platform == 'win32' else 'armada_viewer'
    if bundle:
        candidates.append(os.path.join(bundle, 'cpp', filename))
    candidates.append(os.path.join(root, os.path.dirname(DEFAULT_BINARY), filename))
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def spawn(paths: dict, *, root: str, snapshot: str | None, size=(1280, 800), log=print):
    """Launch the viewer against a live session's rings. Returns the process, or None."""
    import sys
    if getattr(sys, 'frozen', False) and sys.platform == 'darwin':
        # PyInstaller macOS bundles expose data under Frameworks through symlinks
        # into Resources. The native mesh loader canonicalizes every file and
        # rejects anything outside --assets, so Frameworks cannot be that root.
        # Resolve the data directory, not merely its unsymlinked parent. Keep
        # the native containment check intact; source/Windows roots are unchanged.
        assets = os.path.join(root, 'assets')
        if os.path.isdir(assets):
            root = os.path.dirname(os.path.realpath(assets))
    binary = find_binary(root)
    if binary is None:
        log('cpp window: no armada_viewer built (render_cpp/build-w02); the match is running '
            'headless and the rings are being published')
        return None
    if not snapshot:
        snapshot = ensure_snapshot(root, os.path.dirname(str(paths['frame'])), log=log)
    if not snapshot or not os.path.isfile(snapshot):
        log('cpp window: no mesh catalogue, so the window was not started; the match is running '
            'here instead (this fallback draws with the legacy renderer)')
        return None

    argv = [
        binary,
        '--width', str(size[0]),
        '--height', str(size[1]),
        '--snapshot', snapshot,
        '--assets', root,
        '--ring', str(paths['frame']),
        '--tables', str(paths['tables']),
        '--overlay-ring', str(paths['overlay']),
        '--emit-ring', str(paths['emit']),
        '--marker-ring', str(paths['markers']),
        '--fog-ring', str(paths['fog']),
        '--planet-ring', str(paths['planets']),
        '--input-ring', str(paths['input']),
        '--camera-ring', str(paths['camera']),
        '--mesh-ring', str(paths['hardware']),
        '--seconds', '0',
    ]
    if paths.get('top_hud') is not None:
        argv += ['--top-hud-ring', str(paths['top_hud'])]
    if paths.get('vector_hud') is not None:
        argv += ['--vector-hud-ring', str(paths['vector_hud'])]
    # A frozen bundle carries the shaders beside the binary; the build-time default points into the
    # source build tree, which a player does not have.
    for extra in (os.path.join(os.path.dirname(binary), 'shaders'),):
        if os.path.isdir(extra):
            argv += ['--shaders', extra]
    if os.environ.get('STAR_ARMADA_CPP_EXTERNAL') != '1':
        from .embedded import EmbeddedWindow
        try:
            window = EmbeddedWindow(argv, root=root)
        except Exception as exc:
            log(f'cpp embedded renderer unavailable ({exc}); retaining this window')
            return None
        atexit.register(stop, window)
        log('cpp renderer: isolated bgfx worker, original pygame window retained')
        return window
    # Separate-window mode is diagnostic-only, never the normal game launch.
    player = shutil.which(binary) or binary
    process = subprocess.Popen([player] + argv[1:], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(stop, process)
    log(f'cpp window: {os.path.basename(binary)} pid {process.pid}, rings in '
        f'{os.path.dirname(str(paths["frame"]))}')
    return process


def stop(process) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
