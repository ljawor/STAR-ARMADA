"""Prove native drawing retains the existing pygame window without a viewer process."""
from pathlib import Path
import argparse
import json
import os
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def window_identity():
    import ctypes
    import pygame
    get_name = ctypes.pythonapi.PyCapsule_GetName
    get_name.argtypes = [ctypes.py_object]
    get_name.restype = ctypes.c_char_p
    get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    get_pointer.restype = ctypes.c_void_p
    return {key: (value if isinstance(value, int) else get_pointer(value, get_name(value)))
            for key, value in pygame.display.get_wm_info().items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        os.environ['SDL_VIDEODRIVER'] = 'cocoa'
    import pygame
    from render_bridge import cpp_window, packed, ring
    pygame.init()
    pygame.display.set_mode((960, 600), pygame.OPENGL | pygame.DOUBLEBUF)
    identity = window_identity()
    tables = packed.Tables.build([], [])
    (out / 'frame.tables').write_bytes(tables.encode())
    writer = ring.Ring.create(out / 'frame.ring', slots=4, slot_bytes=1024)
    writer.publish(packed.pack_frame(bytearray(packed.frame_size(0, 0)),
        tick=0, frame_index=0, tables=tables, instances=[], effects=[]))
    paths = {name: out / (name + '.ring') for name in
             ['overlay', 'emit', 'markers', 'fog', 'planets', 'input', 'camera', 'hardware']}
    # Optional streams remain absent; their absence is handled by the embedded launcher.
    paths.update(frame=out / 'frame.ring', tables=out / 'frame.tables')
    window = None
    samples = []
    try:
        window = cpp_window.spawn(paths, root=str(ROOT), snapshot=None)
        assert getattr(window, 'embedded', False), 'Match still launches an external native window/process'
        assert window.poll() is None
        for index in range(12):
            pygame.event.pump()
            start = time.monotonic()
            window.present()
            samples.append((time.monotonic() - start) * 1000)
            assert window_identity() == identity, 'Native window was replaced'
        from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
        from PIL import Image
        data = glReadPixels(0, 0, 960, 600, GL_RGB, GL_UNSIGNED_BYTE)
        Image.frombytes('RGB', (960, 600), data).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(out / 'same-window.png')
    finally:
        cpp_window.stop(window)
        writer.close()
    assert window_identity() == identity, 'Menu-return window identity changed'
    # The original GL context must remain useful, not just its window object.
    from OpenGL.GL import glClearColor, glClear, GL_COLOR_BUFFER_BIT, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
    glClearColor(.2, .4, .6, 1.)
    glClear(GL_COLOR_BUFFER_BIT)
    pixel = bytes(glReadPixels(100, 100, 1, 1, GL_RGB, GL_UNSIGNED_BYTE))
    assert all(abs(a - b) <= 2 for a, b in zip(pixel, (51, 102, 153))), pixel
    report = dict(embedded=True, original_window=identity, final_window=window_identity(),
                  native_frame_ms=samples, gl_context_survived=True)
    (out / 'verification.json').write_text(json.dumps(report, indent=2))
    pygame.quit()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
