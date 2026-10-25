"""Windowless C++/bgfx rendering, presented in the original pygame GL window.

The Python side only uploads/presents pixels; scene rendering remains C++/Metal or
D3D12. GPU→CPU→GL transfer has a cost; this is not a zero-copy performance claim.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import sys
import json
import mmap
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import hmac
from .native_worker import find_library, receive, send

STARTUP_TIMEOUT = 20.0
FRAME_TIMEOUT = 15.0
SHUTDOWN_GRACE = 2.0
REAP_TIMEOUT = 2.0
# Windows reports a file still held by a closing handle, or by a scanner, as
# WinError 5 during cleanup. The child is already reaped and our mapping is
# closed at that point, so a short bounded retry separates that race from a
# genuine leak, which keeps raising.
CLEANUP_ATTEMPTS = 5
CLEANUP_RETRY_DELAY = 0.05


def worker_command(config):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--native-render-worker', str(config)]
    return [sys.executable, '-u', '-m', 'render_bridge.native_worker', str(config)]


def map_pointer_event(event, source_size, target_size):
    """Map the existing host window to the fixed-resolution native HUD, once."""
    import pygame
    if getattr(event, 'remote', False) or event.type not in (
            pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
        return event
    sx, sy = (target_size[i] / max(1, source_size[i]) for i in range(2))
    attrs = dict(event.dict)
    pos = attrs.get('pos')
    if pos is None:
        pos = pygame.mouse.get_pos()
    attrs['pos'] = (round(pos[0] * sx), round(pos[1] * sy))
    if 'rel' in attrs:
        attrs['rel'] = (round(attrs['rel'][0] * sx), round(attrs['rel'][1] * sy))
    attrs['remote'] = True
    return pygame.event.Event(event.type, attrs)


def _cleanup_temporary(temporary, attempts=CLEANUP_ATTEMPTS, delay=CLEANUP_RETRY_DELAY):
    """Delete the worker's shared storage, retrying only a transient sharing violation.

    By the time this runs the writer has been reaped and every mapping of ours is
    closed, so an OSError here is either a handle that has not finished closing or
    a scanner reading the file. A genuine leak exhausts the budget and still raises,
    which the fatal path turns into reported evidence rather than silence.
    """
    name = getattr(temporary, 'name', None)
    if not isinstance(name, (str, bytes, os.PathLike)):
        name = None        # no verifiable path: trust the call, as before
    for remaining in range(attempts, 0, -1):
        try:
            temporary.cleanup()
        except OSError:
            if remaining == 1:
                raise
            time.sleep(delay)
            continue
        # cleanup() is neither documented as re-entrant nor required to report that it
        # removed anything, so a silent no-op must not read as success.
        if name is None or not os.path.exists(name):
            return
        if remaining == 1:
            raise OSError(f'worker storage survived cleanup: {name}')
        time.sleep(delay)


class EmbeddedWindow:
    embedded = True

    def __init__(self, argv, *, root):
        # Validate before loading native code or allocating a readback buffer.
        width = int(argv[argv.index('--width') + 1]) if '--width' in argv else 1280
        height = int(argv[argv.index('--height') + 1]) if '--height' in argv else 800
        if not (320 <= width <= 7680 and 240 <= height <= 4320):
            raise ValueError('Invalid native drawable resolution')
        self.size = (width, height)
        self._owner = threading.get_ident()
        self._process = self._connection = self._listener = None
        self._mapping = self._temporary = None
        self._texture = None
        self._terminal = False
        self._tail = bytearray()
        self._log_thread = None
        try:
            library = find_library(root)
            directory = None
            if '--ring' in argv:
                directory = str(Path(argv[argv.index('--ring') + 1]).resolve().parent)
            self._temporary = tempfile.TemporaryDirectory(prefix='armada-worker-',
                dir=directory or os.environ.get('TMPDIR'))
            base = Path(self._temporary.name)
            frame = base / 'frame.bgra'
            length = width * height * 4
            with frame.open('w+b') as stream:
                stream.truncate(length)
                self._mapping = mmap.mmap(stream.fileno(), length)
            self._pixels = (ctypes.c_ubyte * length).from_buffer(self._mapping)
            self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listener.bind(('127.0.0.1', 0))
            self._listener.listen(1)
            nonce = secrets.token_hex(32)
            config = base / 'config.json'
            from .native_worker import process_creation_time
            config.write_text(json.dumps(dict(port=self._listener.getsockname()[1], nonce=nonce,
                library=library, argv=list(argv), frame=str(frame), width=width, height=height,
                parent_pid=os.getpid(), parent_creation_time=process_creation_time())),
                encoding='utf-8')
            options = dict(cwd=str(Path(root).resolve()), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            else:
                options['start_new_session'] = True
            deadline = time.monotonic() + STARTUP_TIMEOUT
            self._process = subprocess.Popen(worker_command(config), **options)
            self._log_thread = threading.Thread(target=self._drain_log,
                args=(base / 'diagnostic.log',), daemon=True)
            self._log_thread.start()
            self._listener.settimeout(max(0.001, deadline - time.monotonic()))
            self._connection, _ = self._listener.accept()
            hello = receive(self._connection, deadline)
            if not isinstance(hello.get('nonce'), str) or not hmac.compare_digest(hello['nonce'], nonce):
                raise RuntimeError('Native worker authentication failed')
            send(self._connection, {'nonce': nonce}, deadline)
            if receive(self._connection, deadline) != {'ready': True}:
                raise RuntimeError('Native worker did not become ready')
            self._listener.close()
            self._listener = None
        except Exception as exc:
            self._abort(exc)

    def _check_thread(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError('Native renderer requires its creator thread')

    def _drain_log(self, path):
        # Always drain stdout/stderr; retain only the most recent 8 KiB on disk/in memory.
        try:
            while True:
                data = os.read(self._process.stdout.fileno(), 4096)
                if not data:
                    break
                self._tail.extend(data)
                del self._tail[:-8192]
                try:
                    path.write_bytes(self._tail)
                except OSError:
                    pass  # optional disk diagnostics must never stop draining the pipe
        except (OSError, ValueError):
            pass

    def _abort(self, reason):
        self._terminal = True
        cleanup_failure = ''
        try:
            self._stop(hard=True)
        except Exception as exc:
            # A cleanup failure is evidence, not a replacement for the native fault.
            cleanup_failure = f'; cleanup failed: {type(exc).__name__}: {exc}'
        code = self._process.returncode if self._process else None
        tail = bytes(self._tail).decode('utf-8', errors='replace')
        raise RuntimeError(f'Native renderer failed: {reason}; exitcode={code}'
                           f'{cleanup_failure}\n{tail}') from reason

    def _request(self, command):
        self._check_thread()
        if self._terminal:
            raise RuntimeError('Native renderer session is terminal')
        try:
            deadline = time.monotonic() + FRAME_TIMEOUT
            send(self._connection, {'command': command}, deadline)
            result = receive(self._connection, deadline)
            if 'error' in result:
                raise RuntimeError(result['error'])
            if command == 'frame' and result.get('count') != len(self._pixels):
                raise RuntimeError('Invalid native frame byte count')
            if command == 'poll' and type(result.get('status')) is not int:
                raise RuntimeError('Invalid native poll status')
            return result
        except Exception as exc:
            self._abort(exc)

    def poll(self):
        self._check_thread()
        if self._terminal:
            return self._process.poll() if self._process else 0
        if self._request('poll')['status'] == 0:
            return None
        self.terminate()
        return self._process.returncode

    def present(self):
        self._check_thread()
        self._request('frame')
        import pygame
        from OpenGL.GL import (glGenTextures, glPushAttrib, glPopAttrib, glViewport,
            glMatrixMode, glPushMatrix, glPopMatrix, glLoadIdentity, glOrtho,
            glDisable, glEnable, glBindTexture, glTexParameteri, glTexImage2D,
            glTexSubImage2D, glColor4f, glBegin, glEnd, glTexCoord2f, glVertex2f,
            GL_ALL_ATTRIB_BITS, GL_PROJECTION, GL_MODELVIEW, GL_DEPTH_TEST,
            GL_LIGHTING, GL_BLEND, GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
            GL_TEXTURE_MAG_FILTER, GL_LINEAR, GL_RGBA, GL_BGRA, GL_UNSIGNED_BYTE,
            GL_QUADS, GL_CULL_FACE, GL_SCISSOR_TEST)
        width, height = pygame.display.get_surface().get_size()
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        try:
            for state in (GL_DEPTH_TEST, GL_LIGHTING, GL_BLEND, GL_CULL_FACE, GL_SCISSOR_TEST):
                glDisable(state)
            glEnable(GL_TEXTURE_2D)
            if self._texture is None:
                self._texture = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, self._texture)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, *self.size, 0,
                             GL_BGRA, GL_UNSIGNED_BYTE, self._pixels)
            else:
                glBindTexture(GL_TEXTURE_2D, self._texture)
                glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, *self.size,
                                GL_BGRA, GL_UNSIGNED_BYTE, self._pixels)
            glColor4f(1, 1, 1, 1)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(0, 0)
            glTexCoord2f(1, 0); glVertex2f(width, 0)
            glTexCoord2f(1, 1); glVertex2f(width, height)
            glTexCoord2f(0, 1); glVertex2f(0, height)
            glEnd()
        finally:
            glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix()
            glMatrixMode(GL_MODELVIEW); glPopAttrib()
        pygame.display.flip()

    def _stop(self, *, hard=False):
        self._terminal = True
        process = self._process
        if process is not None:
            if process.poll() is None and not hard and self._connection is not None:
                try:
                    deadline = time.monotonic() + SHUTDOWN_GRACE
                    send(self._connection, {'command': 'close'}, deadline)
                    process.wait(timeout=max(0, deadline - time.monotonic()))
                except (OSError, TimeoutError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                process.kill()
            # Never release shared storage until the writer has actually been reaped.
            process.wait(timeout=REAP_TIMEOUT)
        for name in ('_connection', '_listener'):
            connection = getattr(self, name)
            if connection is not None:
                connection.close()
                setattr(self, name, None)
        if self._log_thread is not None:
            self._log_thread.join(timeout=REAP_TIMEOUT)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if hasattr(self, '_pixels'):
            del self._pixels
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._temporary is not None:
            _cleanup_temporary(self._temporary)
            self._temporary = None
        if self._texture is not None:
            from OpenGL.GL import glDeleteTextures
            glDeleteTextures([self._texture])
            self._texture = None

    def terminate(self):
        self._check_thread()
        self._stop()

    def wait(self, timeout=None):
        self._check_thread()
        # Popen semantics: waiting is not a request to close the renderer.
        return self._process.wait(timeout=timeout) if self._process else 0

    def kill(self):
        self._check_thread()
        self._stop(hard=True)
