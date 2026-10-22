"""Windowless C++/bgfx rendering, presented in the original pygame GL window.

The Python side only uploads/presents pixels; scene rendering remains C++/Metal or
D3D12. GPU→CPU→GL transfer has a cost; this is not a zero-copy performance claim.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import sys


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


class EmbeddedWindow:
    embedded = True

    def __init__(self, argv, *, root):
        # Validate before loading native code or allocating a readback buffer.
        width = int(argv[argv.index('--width') + 1]) if '--width' in argv else 1280
        height = int(argv[argv.index('--height') + 1]) if '--height' in argv else 800
        if not (320 <= width <= 7680 and 240 <= height <= 4320):
            raise ValueError('Invalid native drawable resolution')
        self.size = (width, height)
        bundle = getattr(sys, '_MEIPASS', None)
        name = 'armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib'
        candidates = [os.environ.get('STAR_ARMADA_CPP_LIBRARY')]
        if bundle:
            candidates.append(str(Path(bundle) / 'cpp' / name))
        candidates.append(str(Path(root) / 'render_cpp/build-w02' / name))
        library = next((p for p in candidates if p and Path(p).is_file()), None)
        if library is None:
            raise RuntimeError('Build the armada_embedded shared-library target first')
        self._lib = lib = ctypes.CDLL(library)
        lib.armada_abi_version.restype = ctypes.c_uint
        if lib.armada_abi_version() != 1:
            raise RuntimeError('Unsupported native renderer ABI')
        lib.armada_open.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        lib.armada_open.restype = ctypes.c_void_p
        lib.armada_frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        lib.armada_frame.restype = ctypes.c_int
        lib.armada_close.argtypes = [ctypes.c_void_p]
        lib.armada_close.restype = None
        lib.armada_poll.argtypes = [ctypes.c_void_p]
        lib.armada_poll.restype = ctypes.c_int
        lib.armada_error.argtypes = [ctypes.c_void_p]
        lib.armada_error.restype = ctypes.c_char_p
        self._pixels = (ctypes.c_ubyte * (self.size[0] * self.size[1] * 4))()
        self._texture = None
        # Empty optional streams are valid; do not ask a decoder to open a missing file.
        cleaned = [argv[0]]
        index = 1
        while index < len(argv):
            flag, value = argv[index:index + 2]
            if flag == '--input-ring' or (flag.endswith('-ring') and not Path(value).exists()):
                index += 2
                continue
            cleaned += [flag, value]
            index += 2
        encoded = (ctypes.c_char_p * len(cleaned))(*(os.fsencode(p) for p in cleaned))
        self._handle = lib.armada_open(len(cleaned), encoded)
        if not self._handle:
            raise RuntimeError('Could not initialize native renderer session')

    def poll(self):
        return None if self._handle and self._lib.armada_poll(self._handle) == 0 else 0

    def present(self):
        count = self._lib.armada_frame(self._handle, self._pixels, len(self._pixels))
        if count != len(self._pixels):
            reason = self._lib.armada_error(self._handle).decode('utf-8', errors='replace')
            raise RuntimeError(f'Native frame failed ({count}): {reason}')
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

    def terminate(self):
        if self._handle:
            self._lib.armada_close(self._handle)
            self._handle = None
        if self._texture is not None:
            from OpenGL.GL import glDeleteTextures
            glDeleteTextures([self._texture])
            self._texture = None

    def wait(self, timeout=None):
        self.terminate()
        return 0

    kill = terminate
