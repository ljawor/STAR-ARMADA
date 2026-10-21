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

DEFAULT_BINARY = os.path.join('render_cpp', 'build-w02', 'armada_viewer')


def find_binary(root: str) -> str | None:
    """The viewer, if this checkout has been built. A missing build is not an error: the game runs."""
    path = os.environ.get('STAR_ARMADA_CPP_VIEWER') or os.path.join(root, DEFAULT_BINARY)
    return path if os.path.isfile(path) and os.access(path, os.X_OK) else None


def spawn(paths: dict, *, root: str, snapshot: str | None, log=print):
    """Launch the viewer against a live session's rings. Returns the process, or None."""
    binary = find_binary(root)
    if binary is None:
        log('cpp window: no armada_viewer built (render_cpp/build-w02); the match is running '
            'headless and the rings are being published')
        return None
    if not snapshot or not os.path.isfile(snapshot):
        log('cpp window: STAR_ARMADA_CPP_SNAPSHOT is not set to an existing snapshot; the window '
            'needs one for its mesh catalogue, so it was not started')
        return None

    argv = [
        binary,
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
        '--seconds', '0',
    ]
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
