"""Capture S08's shipped replacement through the real production renderer.

No injected geometry, no persistence writes, no simulation ticks, no art approval.
Run in a fresh native macOS process; --out must not already exist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    import game.core
    import pygame
    import numpy as np
    from OpenGL import GL
    from game.benchmark import state_hash
    from render import asset_selection as selection
    from render.camera import Camera
    from render.renderer import Renderer
    from tools.diag_alliance_batch_review import build_row_scene
    gm, st = build_row_scene(SimpleNamespace(VERSION='S08 visual pack demonstration'),
                            [('subject', 'ship', 'rebel_frigate', 0, [0., 0., 0.], 0.)],
                            factions=('rebel',))
    initial = state_hash(st)
    W, H = 960, 640
    pygame.display.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    display = pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    assert display.get_size() == (W, H)
    GL.glViewport(0, 0, W, H)
    report = {'renderer_sha256': sha(ROOT / 'render/renderer.py'),
              'selection_sha256': sha(ROOT / 'render/asset_selection.py'),
              'resolver_sha256': sha(ROOT / 'render/asset_registry.py'),
              'harness_sha256': sha(__file__), 'initial_state_sha256': initial,
              'gl': {k: GL.glGetString(v).decode() for k, v in
                     [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER), ('version', GL.GL_VERSION)]},
              'samples': int(GL.glGetIntegerv(GL.GL_SAMPLES)), 'captures': []}
    assert report['samples'] == 4
    images = {}
    renderer = None
    try:
        for packs, label in (([], 'core'), (['core-frigate'], 'pack'), ([], 'disabled')):
            selection.configure({'model_preview': True, 'visual_packs': packs}, asset_root=ROOT,
                                pack_root=ROOT / 'examples/visual_packs')
            resolved = selection._resolver.resolve('rebel:frigate')
            assert resolved is not None
            assert (resolved.pack_id is not None) == bool(packs), selection.diagnostics()
            cam = Camera(W, H)
            cam.bind_scene(st, lambda: 0, lambda: 3.)
            cam.target = [0., 0., 0.]
            cam.yaw, cam.pitch = 48., 35.
            renderer = Renderer(st, cam)
            renderer.local_player = 0
            renderer.diff_render = True
            renderer.time = 3.
            assert renderer.materials.available, renderer.materials.error
            for view, distance in (('close', 185.), ('tactical', 700.)):
                cam.distance = distance
                renderer._reset_frame_cache()
                frames = []
                for _ in range(5):
                    pygame.event.pump()
                    cam.apply(W, H)
                    renderer.draw(0., set())
                    GL.glFinish()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert state_hash(st) == initial
                    frames.append(np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                                np.uint8).reshape(H, W, 3)[::-1].copy())
                assert np.array_equal(frames[-1], frames[-2]), (label, view, 'unstable frozen repeat')
                name = f'{label}-{view}.png'
                pygame.image.save(pygame.image.frombuffer(frames[-1].tobytes(), (W, H), 'RGB'), out / name)
                images[(label, view)] = frames[-1]
                report['captures'].append({'file': name, 'sha256': sha(out / name), 'view': view,
                                           'distance': distance, 'yaw': cam.yaw, 'pitch': cam.pitch,
                                           'asset': resolved.asset, 'revision': resolved.revision,
                                           'pack_revision': resolved.pack_revision, 'pack_id': resolved.pack_id,
                                           'repeat_equal': True, 'state_sha256': initial})
            renderer.close()
            renderer = None
        report['comparisons'] = {}
        for view in ('close', 'tactical'):
            changed = int(np.any(np.abs(images[('core', view)].astype(int) -
                                        images[('pack', view)].astype(int)) > 3, axis=2).sum())
            assert changed > 0, (view, 'replacement not visible')
            disabled_equal = np.array_equal(images[('core', view)], images[('disabled', view)])
            assert disabled_equal, (view, 'disable did not restore core')
            report['comparisons'][view] = {'changed_pixels_gt3': changed, 'disabled_equal': bool(disabled_equal)}
        report['ok'] = True
    finally:
        if renderer is not None:
            renderer.close()
        selection.configure({})
        pygame.display.quit()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['comparisons']))


if __name__ == '__main__':
    main()
