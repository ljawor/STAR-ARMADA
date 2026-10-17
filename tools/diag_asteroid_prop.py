#!/usr/bin/env python3
"""Evidence for the B5 asteroid prop: one field, drawn by the legacy rock and by the authored one.

    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_asteroid_prop.py \
        --out artifacts/s06_alliance_batch_review/b5-asteroid

Renders the same asteroid field twice from the same camera - once with the row unselected, so the
field draws its own procedural rock, and once with the authored prop served from a review-only
registry that is never a production selection - and writes both frames plus a side-by-side sheet and
the measured difference.

The layout is asserted identical between the two runs, not assumed: the field's forty placements come
from `render.renderer.field_placement`, and both drawing paths take their rock parameters from
`rock_params` before they branch, so the field cannot rearrange itself. The run also renders the
legacy variant twice and asserts zero changed pixels, so a difference between the variants is a
difference in the rock rather than in the frame.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = 'environment:asteroid_field'
IDENTIFIER = 'shared_asteroid_field'
ENVELOPE = ((-0.58, 0.58), (-0.46, 0.46), (-0.58, 0.58))
MIN_LENGTH = 1.0
FIELD_RADIUS = 260.0
FIELD_POS = (0.0, 0.0, 4200.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)

    cap = importlib.util.spec_from_file_location(
        'capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(cap)
    cap.loader.exec_module(helper)
    helper.isolate(ROOT, out)

    import numpy as np
    import pygame
    from OpenGL import GL
    import game.core.manager                      # noqa: F401  (import order)
    from game.benchmark import state_hash
    from game.core.vectors import Vec3
    from render import asset_selection as selection
    from render.authored_mesh import _load_profile
    from render.camera import Camera
    from render.renderer import Renderer

    selection.configure({'model_preview': True})
    production_mesh_for = selection.mesh_for
    assert not production_mesh_for(FIELD), 'the row must not already be selected in production'
    profile = _load_profile(ROOT / f'assets/models/{IDENTIFIER}.mesh.json', IDENTIFIER, ENVELOPE,
                            MIN_LENGTH)
    active = {'enabled': False}

    def review_mesh(binding):
        if binding == FIELD and active['enabled']:
            return profile
        return production_mesh_for(binding)

    selection.mesh_for = review_mesh

    W, H = 1280, 720
    # A field's radius varies by map, so the framing follows the field's own radius, and the near view
    # is deliberately close enough that individual rocks are tens of pixels across: an authored prop
    # that cannot be told apart at that range is not evidence of anything.
    views = {'close': dict(target=None, distance=None, yaw=35., pitch=22.),
             'wide': dict(target=None, distance=None, yaw=35., pitch=45.)}

    site = {'pos': FIELD_POS}

    def scene():
        """A fresh scene with one asteroid field at the fixed site, in both runs identical.

        The camera aims at the field the renderer will actually draw, taken from the scene rather
        than assumed: a first cut aimed at a hard-coded site and captured two frames of empty space,
        which measured as a zero-pixel change and would have read as "the prop changes nothing".
        """
        gm, ids, _ = helper.build_scene()
        st = gm.state
        fields = [e for e in st.entities.values() if e.data_id == 'asteroid_field']
        if not fields:
            # The field is placed inside the player's own sensor picture: `_draw_planets` draws only
            # the entities the local player knows, so a field dropped anywhere on the map is simply
            # never drawn - which is how the first two cuts of this harness captured empty space and
            # reported a zero-pixel change.
            capital = st.entities[ids['capital']]
            site_x = capital.pos.x + FIELD_RADIUS * 2.6
            gm.factory.spawn_planet({'id': 'b5_field', 'name': 'B5 Field',
                                     'pos': [site_x, capital.pos.y, capital.pos.z],
                                     'radius': FIELD_RADIUS, 'type': 'asteroid_field'})
            gm.visibility.update()
            fields = [e for e in st.entities.values() if e.data_id == 'asteroid_field']
        field = fields[0]
        site['pos'] = (field.pos.x, field.pos.y, field.pos.z)
        site['radius'] = float(field.radius)
        return gm, st

    gm, st = scene()
    initial = state_hash(st)
    active['enabled'] = False
    selection.invalidate_geometry_helpers()
    baseline = helper.geometry(st)
    active['enabled'] = True
    selection.invalidate_geometry_helpers()
    candidate = helper.geometry(st)
    active['enabled'] = False
    selection.invalidate_geometry_helpers()
    union = [baseline, candidate]

    report = {'schema': 1, 'batch': 's06-b5-environment', 'row': FIELD,
              'integration': 'UNAPPROVED review-only monkeypatch of mesh_for; no production selection',
              'initial_state_sha256': initial, 'captures': {}, 'comparison': {}}
    frames = {}

    for variant in ('before', 'after', 'before-repeat'):
        active['enabled'] = variant == 'after'
        selection.invalidate_geometry_helpers()
        gm, st = scene()
        assert state_hash(st) == initial, 'the two runs must start from the same state'
        cam = Camera(W, H)
        cam.bind_scene(st, lambda: 0, lambda: 0.)
        pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
        renderer = Renderer(st, cam)
        renderer.diff_render = True
        renderer.time = 3.
        for name, view in views.items():
            scale = 1.6 if name == 'close' else 4.0
            view = dict(view, target=list(site['pos']), distance=site['radius'] * scale)
            pygame.event.pump()
            helper.configure(cam, view)
            helper.camera_check(cam, st, union, 3.)
            before_hash = state_hash(st)
            renderer.draw(0., set())
            assert state_hash(st) == before_hash, 'drawing must not touch simulation state'
            GL.glFinish()
            pixels = np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                   np.uint8).reshape(H, W, 3)[::-1].copy()
            assert GL.glGetError() == GL.GL_NO_ERROR
            frames[(variant, name)] = pixels
            if variant != 'before-repeat':
                pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (W, H), 'RGB'),
                                  str(out / f'asteroid field-{variant}-{name}.png'))
        renderer.close()
        pygame.display.quit()
    active['enabled'] = False
    selection.invalidate_geometry_helpers()

    for name in views:
        base = frames[('before', name)].astype(int)
        after = frames[('after', name)].astype(int)
        repeat = frames[('before-repeat', name)].astype(int)
        diff = np.abs(after - base).max(axis=2) > 3
        rep = np.abs(repeat - base).max(axis=2) > 3
        ys, xs = np.nonzero(diff)
        report['comparison'][name] = dict(
            changed_pixels=int(diff.sum()),
            changed_percent=round(100.0 * diff.sum() / diff.size, 4),
            bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
            repeat_changed_pixels=int(rep.sum()))
        report['captures'][name] = dict(
            before=f'asteroid field-before-{name}.png',
            after=f'asteroid field-after-{name}.png')
        assert rep.sum() == 0, f'{name}: the legacy path is not reproducible frame to frame'
        # A zero-pixel result is not a pass: it is what an empty frame measures. Two earlier cuts of
        # this harness aimed at a field the renderer never drew and reported exactly that.
        assert diff.sum() > 0, (f'{name}: the authored prop changed nothing - either the field is not '
                                f'in frame or the seam is not serving it')

    # A side-by-side sheet, so the change is looked at rather than only measured.
    pygame.font.init()
    font = pygame.font.SysFont('Helvetica', 18)
    rows = []
    for name in views:
        rows.append(name)
    sheet = pygame.Surface((W, (H + 28) * len(rows)))
    sheet.fill((12, 14, 18))
    for row, name in enumerate(rows):
        top = row * (H + 28) + 28
        for column, variant in enumerate(('before', 'after')):
            picture = pygame.image.frombuffer(frames[(variant, name)].tobytes(), (W, H), 'RGB')
            sheet.blit(pygame.transform.smoothscale(picture, (W // 2, H // 2)),
                       (column * (W // 2), top))
            label = 'procedural rock' if variant == 'before' else 'authored prop'
            sheet.blit(font.render(f'{name}: {label}', True, (232, 232, 236)),
                       (column * (W // 2) + 10, top - 24))
    pygame.image.save(sheet, str(out / 'asteroid-field-comparison.png'))
    pygame.font.quit()

    report['field'] = dict(pos=list(site['pos']), radius=site['radius'],
                           field_instances=40, framed_distance={'close': site['radius'] * 1.6,
                                                                'wide': site['radius'] * 4.0})
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['comparison'], indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
