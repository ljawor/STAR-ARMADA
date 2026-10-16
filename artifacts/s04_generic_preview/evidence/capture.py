#!/usr/bin/env python3
"""Reproduce the committed trio recipe through prototype, generic preview or legacy.

Run each variant in a fresh interpreter with its own source snapshot and output.
Normal production materials, fog and 4x MSAA; this is engineering parity evidence,
not S05's complete owner-colour/motion/combat approval matrix or a performance test.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', choices=('prototype', 'preview', 'legacy'), required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(source))
    os.chdir(source)
    assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')
    assert not os.environ.get('STAR_ARMADA_SKIP')
    spec = importlib.util.spec_from_file_location(
        'trio_recipe', source / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    import game.core
    import render
    assert Path(game.core.__file__).resolve().is_relative_to(source)
    assert Path(render.__file__).resolve().is_relative_to(source)
    from render import menus
    user = output / 'user'
    # Patch before constructing any menu/HUD/renderer helper.
    for key, path in {'USER_DIR': user, 'SAVES_DIR': user / 'saves',
                      'SETTINGS_PATH': user / 'saves/settings.json',
                      'CAMPAIGN_PATH': user / 'saves/campaign.json',
                      'BALANCE_PATH': user / 'saves/balance.json'}.items():
        setattr(menus, key, str(path))
    if args.selection != 'prototype':
        from render.asset_selection import configure
        configure({'model_preview': args.selection == 'preview'}, asset_root=source)
    import pygame
    import numpy as np
    from OpenGL import GL
    from render.renderer import Renderer
    from render.camera import Camera
    from game.benchmark import state_hash
    renderer = None
    report = {'selection': args.selection, 'source': str(source), 'captures': []}
    report['render_sources_sha256'] = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted((source / 'render').glob('*.py'))}
    report['mesh_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((source / 'assets/models').glob('*.mesh.json'))}
    try:
        pygame.display.init()
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        pygame.display.set_mode((1280, 800), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.event.pump()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glClearColor(.008, .012, .025, 1.)
        assert tuple(GL.glGetIntegerv(GL.GL_VIEWPORT)) == (0, 0, 1280, 800)
        assert int(GL.glGetIntegerv(GL.GL_SAMPLES)) == 4
        assert int(GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS)) == 1
        report['display'] = {'size': [1280, 800], 'samples': 4, 'sample_buffers': 1,
                             'driver': pygame.display.get_driver(),
                             **{key: GL.glGetString(value).decode() for key, value in
                                [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER),
                                 ('version', GL.GL_VERSION)]}}
        gm, ids, scene = recipe.build_scene()
        report['recipe'] = scene
        before = state_hash(gm.state)
        report['state_sha256'] = before
        camera = Camera(1280, 800)
        renderer = Renderer(gm.state, camera)
        assert renderer.materials.available, renderer.materials.error
        assert not renderer.skip
        renderer.diff_render, renderer.time = True, 3.
        for name in ('common-scale', 'capital-close', 'escort-close', 'yard-close',
                     'capital-rear', 'escort-rear', 'yard-rear', 'tactical'):
            recipe.configure(camera, recipe.VIEWS[name])
            for _ in range(3):
                renderer.draw(0., {ids['capital']})
            GL.glFinish()
            raw = bytes(GL.glReadPixels(0, 0, 1280, 800, GL.GL_RGB, GL.GL_UNSIGNED_BYTE))
            renderer.draw(0., {ids['capital']})
            GL.glFinish()
            repeat = bytes(GL.glReadPixels(0, 0, 1280, 800, GL.GL_RGB, GL.GL_UNSIGNED_BYTE))
            assert raw == repeat, f'{name}: unstable frozen frame'
            assert state_hash(gm.state) == before, f'{name}: rendering mutated simulation'
            assert GL.glGetError() == GL.GL_NO_ERROR
            pixels = np.frombuffer(raw, np.uint8).reshape(800, 1280, 3)[::-1].copy()
            image = output / (name + '.png')
            pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (1280, 800), 'RGB'), str(image))
            report['captures'].append({'name': name, 'view': recipe.VIEWS[name],
                                        'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                                        'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                                        'repeat_equal': True, 'state_unchanged': True})
        report['status'] = 'passed'
    finally:
        if renderer is not None:
            renderer.close()
        pygame.display.quit()
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'selection': args.selection, 'captures': len(report['captures']),
                      'state_sha256': report['state_sha256'], 'status': report['status']}))


if __name__ == '__main__':
    main()
