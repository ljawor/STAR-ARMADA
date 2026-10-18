#!/usr/bin/env python3
"""Evidence for the S06 B6 row `ship:imperial:corvette`: one camera, the legacy `needle` hull on
the left and the authored mesh on the right.

    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_imperial_corvette.py \
        --out artifacts/s06_alliance_batch_review/b6-corvette

The row is NOT registered - `assets/models/registry.json` keeps it at `procedural_legacy`, no
manifest exists for it, and nothing in production may select it - so a reviewer is shown the
candidate the way the S06 batch review does it: an explicit `model_preview` session plus a
monkeypatched selection for this one binding (`selected_binding` so the renderer's own ship path
mints `imperial:corvette`, and `mesh_for` so that binding resolves to the authored mesh JSON).
Both patches defer to the production functions for every other binding and are restored, with
`configure({})`, before this process exits.

Two views per variant from one camera - a close view at the batch's own near framing and a wider
tactical view - each captured twice (the saved frame plus an immediate second read-back) and the
legacy variant rendered a third time as a separate pass. The assertions are the point:

* every pass gets the same framebuffer: the sample count and viewport are asserted per pass, not
  once per process, because a context created after a `display.quit()` silently comes back with no
  multisampling and moves every hull edge by a sub-pixel (that mistake measured 8,781 pixels
  between two identical legacy passes);
* the legacy path is reproducible: legacy pass vs legacy-repeat pass is 0 changed pixels, and each
  variant's own second capture is identical to its first;
* the authored hull changes the frame: changed_pixels > 0, because a zero-pixel result is exactly
  what an empty frame measures;
* the subject is actually in frame: the entity's own box corners project into the viewport with a
  minimum on-screen extent, so "the camera missed the ship" cannot pass as evidence.

The camera is asserted identical between the two variants (same resolved eye, same matrices), which
is what makes the pair a look comparison rather than a framing comparison.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = 's06-b6-imperial-ships'
ROW = 'ship:imperial:corvette'                 # the inventory's canonical spelling
REGISTRY_KEY = 'imperial:corvette'             # the key the renderer's ship path resolves
IDENTIFIER = 'imperial_corvette'
DATA_ID = 'imperial_corvette'
MESH = 'assets/models/imperial_corvette.mesh.json'
ENVELOPE = ((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0))
MIN_LENGTH = 91.4
LABEL = 'imperial-corvette'
W, H = 1280, 800
# The batch's own framing for one hull: `views_for`'s near distance and its tactical distance.
VIEWS = {'close': dict(factor=1.37, yaw=48., pitch=35.),
         'wide': dict(factor=5.57, yaw=48., pitch=55.)}
# The row takes the 'capital' slot with the same fixed context group the batch review places, so
# this is the row in its review situation rather than the row in a scene built for it.
PLACEMENTS = [
    ('capital', 'ship', DATA_ID, 1, [-4200, 0, 2200], 0.),
    ('escort', 'ship', 'rebel_frigate', 0, [-4200, 0, 2900], 0.),
    ('battleship', 'ship', 'rebel_battleship', 0, [-4200, 0, 1500], 0.),
    ('enemy_a', 'ship', 'imperial_frigate', 1, [-3500, 0, 2200], -math.pi / 2),
    ('enemy_b', 'ship', 'imperial_frigate', 1, [-3500, 0, 2900], -math.pi / 2)]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    # The row's review directory may already exist (it holds the row's withdrawn landing-manifest
    # draft), so this refuses a second capture into the same directory without refusing the row's
    # own directory: no run overwrites another run's frames or report.
    out.mkdir(parents=True, exist_ok=True)
    for taken in ('report.json', 'imperial-corvette-comparison.png'):
        assert not (out / taken).exists(), f'{out / taken} already exists; choose a fresh directory'

    cap = importlib.util.spec_from_file_location(
        'capture_slice', ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper = importlib.util.module_from_spec(cap)
    cap.loader.exec_module(helper)

    # Registration state, read before anything is patched: the row is declared and not registered.
    registry = load(ROOT / 'assets/models/registry.json')
    row = next(b for b in registry['bindings'] if b['binding'] == REGISTRY_KEY)
    pipeline = load(ROOT / 'art/manifests/pipeline.json')
    manifest_path = ROOT / f'assets/models/manifests/{IDENTIFIER}.json'
    mesh_path = ROOT / MESH
    mesh_payload = load(mesh_path)
    registration = dict(
        registry_binding=row['binding'], registry_status=row['status'],
        registry_manifest=row.get('manifest'), manifest_exists=manifest_path.exists(),
        in_production_pipeline=REGISTRY_KEY in {a['binding'] for a in pipeline['assets']})
    assert row['status'] in ('procedural_legacy', 'authoring_pending'), registration
    assert not manifest_path.exists(), 'a manifest is a landing: a pending row may not carry one'
    assert not registration['in_production_pipeline'], registration

    helper.PLACEMENTS = list(PLACEMENTS)
    helper.isolate(ROOT, out)

    import numpy as np
    import pygame
    from OpenGL import GL
    import game.core.manager                      # noqa: F401  (import order)
    from game.benchmark import state_hash
    from game.data.store import DataStore
    from render import asset_selection as selection
    from render.authored_mesh import _load_profile
    from render.camera import Camera
    from render.fleet_geometry import ship_mesh
    from render.renderer import Renderer
    from render.ship_sizes import ship_size

    selection.configure({'model_preview': True}, asset_root=ROOT)
    production_mesh_for = selection.mesh_for
    production_selected_binding = selection.selected_binding
    assert not production_selected_binding(REGISTRY_KEY), 'the row must not be selected already'
    assert production_mesh_for(REGISTRY_KEY) is None, 'the row must not resolve in production'
    profile = _load_profile(mesh_path, IDENTIFIER, ENVELOPE, MIN_LENGTH)

    # The review-only seam. Both patches are inert while `enabled` is False, so the legacy variant
    # renders with nothing patched at all - not a different patch, no patch.
    active = {'enabled': False}

    def review_selected_binding(binding):
        if active['enabled'] and binding == REGISTRY_KEY:
            return True
        return production_selected_binding(binding)

    def review_mesh(binding):
        if active['enabled'] and binding == REGISTRY_KEY:
            return profile
        return production_mesh_for(binding)

    selection.selected_binding = review_selected_binding
    selection.mesh_for = review_mesh

    def scene():
        """A fresh, identical scene per pass, with the subject in the 'capital' slot."""
        gm, ids, _ = helper.build_scene()
        st = gm.state
        subject_id = ids['capital']
        assert st.can_see(0, subject_id), 'the local player must know the subject or it is not drawn'
        return gm, st, subject_id

    # Drawn size, measured either side of the seam: the class scale and the drawn length come from
    # `ship_size`, so a candidate that changed them would not be the same ship in game.
    active['enabled'] = False
    selection.invalidate_geometry_helpers()
    legacy_size = ship_size(DataStore.get(), DATA_ID, 'imperial')
    active['enabled'] = True
    selection.invalidate_geometry_helpers()
    candidate_size = ship_size(DataStore.get(), DATA_ID, 'imperial')
    active['enabled'] = False
    selection.invalidate_geometry_helpers()
    assert legacy_size.shape == 'needle', legacy_size
    assert candidate_size.shape == REGISTRY_KEY, candidate_size
    assert abs(candidate_size.length - legacy_size.length) <= legacy_size.length * .01, (
        legacy_size, candidate_size)
    length = legacy_size.length

    # The legacy hull actually drawn, measured in process rather than transcribed.
    legacy_mesh = ship_mesh('needle')
    legacy_geometry = dict(
        shape='needle', source='render/fleet_geometry.py::_ship_mesh',
        triangles=sum(len(v) for v in legacy_mesh.values()),
        vertices=len({p for mesh in legacy_mesh.values() for _, tri in mesh for p in tri}),
        drawn_length=legacy_size.length, drawn_scale=legacy_size.scale)

    gm, st, subject_id = scene()
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

    def corners(table):
        """The subject's own box corners in world space, from the measured geometry."""
        e = st.entities[subject_id]
        lo, hi = table[str(subject_id)]['lo'], table[str(subject_id)]['hi']
        ca, sa = math.cos(e.yaw), math.sin(e.yaw)
        return [(e.pos.x + x * ca + z * sa, e.pos.y + y, e.pos.z - x * sa + z * ca)
                for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]

    def framing(cam, table):
        """Project the subject's box: how much of the viewport the hull itself covers.

        `camera_check` proves the eye is outside every hull; this proves the subject is inside the
        frame, which is the failure an empty frame hides (it measures as a zero-pixel change).
        """
        points = [cam.world_to_screen(*p) for p in corners(table)]
        on_screen = [p for p in points if p is not None]
        if not on_screen:
            return dict(corners_on_screen=0, bbox=None, visible_px=[0, 0])
        xs = [p[0] for p in on_screen]
        ys = [p[1] for p in on_screen]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        x0, y0 = max(0.0, bbox[0]), max(0.0, bbox[1])
        x1, y1 = min(float(W), bbox[2]), min(float(H), bbox[3])
        return dict(corners_on_screen=len(on_screen), bbox=[round(v, 2) for v in bbox],
                    visible_px=[round(max(0.0, x1 - x0), 2), round(max(0.0, y1 - y0), 2)])

    target = st.entities[subject_id].pos.to_tuple()
    views = {name: dict(target=list(target), distance=length * spec['factor'],
                        yaw=spec['yaw'], pitch=spec['pitch'])
             for name, spec in VIEWS.items()}

    report = {
        'schema': 1, 'batch': BATCH, 'row': ROW, 'registry_key': REGISTRY_KEY,
        'identifier': IDENTIFIER, 'status': 'review_only_not_registered',
        'integration': ('UNAPPROVED review-only monkeypatch of render.asset_selection.'
                        'selected_binding and render.asset_selection.mesh_for for this one binding, '
                        'inside an explicit model_preview session. The registry row stays '
                        'procedural_legacy, no manifest exists for the row and nothing in '
                        'production selects it; both patches and the preview session are torn down '
                        'at the end of this run.'),
        'warning': ('Offline orbit captures from the real production draw path: not paced FPS, not '
                    'a battle-acceptance or native-Windows-graphics acceptance, and not an owner '
                    'appearance decision.'),
        'registration': registration, 'legacy': legacy_geometry,
        'authored': dict(path=MESH, sha256=sha256(mesh_path), bytes=mesh_path.stat().st_size,
                         triangles=mesh_payload['triangle_count'],
                         vertices=len(mesh_payload['vertices']),
                         bounds=mesh_payload['bounds'],
                         roles=sorted(mesh_payload['batches']),
                         authority=mesh_payload['features'].get('authority'),
                         approval=mesh_payload['features'].get('approval')),
        'envelope': [list(a) for a in ENVELOPE],
        'drawn_size': dict(legacy=dict(shape=legacy_size.shape, scale=legacy_size.scale,
                                       length=legacy_size.length),
                           candidate=dict(shape=candidate_size.shape, scale=candidate_size.scale,
                                          length=candidate_size.length)),
        'placement': [list(entry) for entry in helper.PLACEMENTS],
        'initial_state_sha256': initial, 'views': {}, 'captures': {}, 'comparison': {}}

    frames = {}
    checks = {}
    passes = ('legacy', 'authored', 'legacy-repeat')

    pygame.display.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    samples = int(GL.glGetIntegerv(GL.GL_SAMPLES))
    viewport = list(map(int, GL.glGetIntegerv(GL.GL_VIEWPORT)))
    assert viewport == [0, 0, W, H] and samples == 4, (viewport, samples)
    report['display'] = dict(samples=samples, viewport=viewport, per_pass={},
                             gl={k: GL.glGetString(v).decode() for k, v in
                                 [('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER),
                                  ('version', GL.GL_VERSION)]})
    try:
        for variant in passes:
            active['enabled'] = variant == 'authored'
            selection.invalidate_geometry_helpers()
            gm, st, subject_id = scene()
            assert state_hash(st) == initial, 'the passes must start from the same state'
            cam = Camera(W, H)
            cam.bind_scene(st, lambda: 0, lambda: 0.)
            # A fresh display per pass, so no pass inherits another pass's GL state - and the
            # attributes must be set before EVERY context, not once per process. A context that
            # silently comes back without multisampling renders every hull edge one sub-pixel
            # differently, which is why the sample count is asserted per pass rather than once.
            pygame.display.init()
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
            pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
            pass_samples = int(GL.glGetIntegerv(GL.GL_SAMPLES))
            pass_viewport = list(map(int, GL.glGetIntegerv(GL.GL_VIEWPORT)))
            report['display']['per_pass'][variant] = dict(samples=pass_samples,
                                                          viewport=pass_viewport)
            assert pass_samples == samples and pass_viewport == viewport, (
                f'{variant}: the pass did not get the same framebuffer as the first pass: '
                f'{pass_samples} samples {pass_viewport} vs {samples} {viewport}')
            renderer = Renderer(st, cam)
            renderer.diff_render = True
            renderer.time = 3.
            assert not renderer.skip, 'renderer skip passes must be empty'
            assert renderer.materials.available, 'production shaders must be available'
            for name, view in views.items():
                pygame.event.pump()
                helper.configure(cam, view)
                check = helper.camera_check(cam, st, union, 3.)
                print(f'  pass {variant}/{name} eye={check["resolved_eye"]} '
                      f'requested={check["requested_eye"]}')
                shot = {}
                for attempt in range(4):
                    before_hash = state_hash(st)
                    renderer.draw(0., set())
                    assert state_hash(st) == before_hash, 'drawing must not touch simulation state'
                    GL.glFinish()
                    pixels = np.frombuffer(
                        GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                        np.uint8).reshape(H, W, 3)[::-1].copy()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    if attempt == 0:
                        continue                      # warm-up: caches, LOD and fog settle
                    if attempt == 1:
                        frames[(variant, name)] = pixels
                        continue
                    # The variant's own second capture: the same camera, the same state.
                    delta = np.abs(frames[(variant, name)].astype(int) - pixels.astype(int))
                    shot['repeat_max_delta'] = int(delta.max())
                    shot['repeat_changed_pixels'] = int(np.any(delta != 0, axis=2).sum())
                    break
                shot['camera'] = check
                shot['state_sha256'] = state_hash(st)
                shot['framing'] = framing(cam, baseline)
                shot['authored_framing'] = framing(cam, candidate)
                checks[(variant, name)] = shot
                name_on_disk = f'{LABEL}-{variant}-{name}.png'
                pygame.image.save(
                    pygame.image.frombuffer(frames[(variant, name)].tobytes(), (W, H), 'RGB'),
                    str(out / name_on_disk))
                shot['image'] = name_on_disk
                shot['image_sha256'] = sha256(out / name_on_disk)
                shots = report['views'].setdefault(name, {})
                shots[variant] = shot
            renderer.close()
            pygame.display.quit()
        active['enabled'] = False
        selection.invalidate_geometry_helpers()
    finally:
        selection.mesh_for = production_mesh_for
        selection.selected_binding = production_selected_binding
        selection.configure({})
        pygame.display.quit()

    # The seam is gone: the same calls production makes now answer as production answers.
    assert production_mesh_for(REGISTRY_KEY) is None
    assert not production_selected_binding(REGISTRY_KEY)
    report['production_candidate_unselected_after_review'] = True

    first = passes[0]
    for name in views:
        base = frames[(first, name)].astype(int)
        per_pass = {first: dict(changed_pixels=0, changed_percent=0.0, max_delta=0, bbox=None)}
        for variant in passes[1:]:
            delta = np.abs(frames[(variant, name)].astype(int) - base)
            mask = delta.max(axis=2) > 3
            ys, xs = np.nonzero(mask)
            per_pass[variant] = dict(
                changed_pixels=int(mask.sum()),
                changed_percent=round(100.0 * mask.sum() / mask.size, 4),
                max_delta=int(delta.max()),
                bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None)
        in_pass = {variant: dict(changed_pixels=report['views'][name][variant]['repeat_changed_pixels'],
                                 max_delta=report['views'][name][variant]['repeat_max_delta'])
                   for variant in passes}
        print(f'{name}: vs {first}: ' + ' '.join(
            f'{v}={per_pass[v]["changed_pixels"]}' for v in passes))
        print(f'{name}: in-pass repeats: ' + ' '.join(
            f'{v}={in_pass[v]["changed_pixels"]}px/{in_pass[v]["max_delta"]}d' for v in passes))
        legacy = frames[('legacy', name)].astype(int)
        authored = frames[('authored', name)].astype(int)
        repeat = frames[('legacy-repeat', name)].astype(int)
        diff = np.abs(authored - legacy).max(axis=2) > 3
        rep = np.abs(repeat - legacy).max(axis=2) > 3
        rep_delta = int(np.abs(repeat - legacy).max())
        ys, xs = np.nonzero(diff)
        rys, rxs = np.nonzero(rep)
        # Where a repeat difference sits, if there ever is one: a coarse cell map names the element
        # that moved (a hull, a star, a planet band) instead of only counting pixels.
        cells = np.zeros((8, 8), dtype=int)
        for y, x in zip(rys, rxs):
            cells[y * 8 // H, x * 8 // W] += 1
        report['comparison'][name] = dict(
            changed_pixels=int(diff.sum()),
            changed_percent=round(100.0 * diff.sum() / diff.size, 4),
            bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
            repeat_changed_pixels=int(rep.sum()), repeat_max_delta=rep_delta,
            repeat_bbox=[int(rxs.min()), int(rys.min()), int(rxs.max()), int(rys.max())]
            if len(rxs) else None,
            repeat_cells=cells.tolist(),
            per_pass_vs_first=per_pass, in_pass_repeats=in_pass, first_variant=first,
            per_variant_repeat_changed_pixels={
                variant: report['views'][name][variant]['repeat_changed_pixels']
                for variant in ('legacy', 'authored')})
        report['captures'][name] = dict(
            legacy=report['views'][name]['legacy'].get('image'),
            authored=report['views'][name]['authored'].get('image'),
            legacy_repeat=report['views'][name]['legacy-repeat'].get('image'))
        print(f'{name:6s} changed_pixels={int(diff.sum())} '
              f'repeat_changed_pixels={int(rep.sum())} repeat_max_delta={rep_delta} '
              f'repeat_bbox={report["comparison"][name]["repeat_bbox"]}')
        if rep.sum():
            print('repeat cell map (8x8, top row first):')
            for row in cells:
                print('   ' + ' '.join(f'{v:5d}' for v in row))
        # The legacy path must be reproducible frame for frame, or a difference between the
        # variants is a difference in the frame rather than in the hull.
        assert rep.sum() == 0 and rep_delta == 0, (
            f'{name}: the legacy path is not reproducible ({int(rep.sum())} pixels, '
            f'max delta {rep_delta}, bbox {report["comparison"][name]["repeat_bbox"]}) - '
            f'recapture both variants with a revised shared plan')
        assert report['comparison'][name]['repeat_changed_pixels'] == 0
        for variant in ('legacy', 'authored'):
            shot = report['views'][name][variant]
            assert shot['repeat_changed_pixels'] == 0 and shot['repeat_max_delta'] == 0, (
                f'{name}/{variant}: the second capture differs from the first: {shot}')
        # A zero-pixel result is not a pass: it is what an empty frame measures.
        assert diff.sum() > 0, (
            f'{name}: the authored mesh changed nothing - either the subject is not in frame or '
            f'the seam is not serving it')
        # ...and the subject really is in frame, measured rather than assumed.
        for variant in ('legacy', 'authored'):
            shot = report['views'][name][variant]
            assert shot['framing']['corners_on_screen'] == 8, (name, variant, shot['framing'])
            assert min(shot['framing']['visible_px']) >= 20.0, (name, variant, shot['framing'])

    # The two variants must share one camera, or the pair compares framing rather than hulls.
    for name in views:
        a, b = report['views'][name]['legacy']['camera'], report['views'][name]['authored']['camera']
        for key in ('requested_eye', 'resolved_eye', 'target', 'distance', 'yaw', 'pitch',
                    'fov', 'near', 'far'):
            assert a[key] == b[key], f'{name}: the two variants were not drawn from one camera: {key}'
    report['one_camera_per_view'] = True

    # A side-by-side sheet, so the change is looked at rather than only measured.
    pygame.font.init()
    font = pygame.font.SysFont('Helvetica', 18)
    title = font.render(f'UNAPPROVED REVIEW ONLY - {ROW} - legacy {legacy_size.shape} hull vs '
                        f'authored mesh - same camera, same tick, 4MSAA / production shaders',
                        True, (198, 216, 234))
    panel_w, panel_h, band, header = W // 2, H // 2, 26, 34
    sheet = pygame.Surface((W, header + len(views) * (panel_h + band)))
    sheet.fill((10, 14, 20))
    sheet.blit(title, (12, 8))
    for row_index, name in enumerate(views):                    # close on top, wide below
        top = header + row_index * (panel_h + band)
        for column, variant in enumerate(('legacy', 'authored')):
            picture = pygame.image.frombuffer(frames[(variant, name)].tobytes(), (W, H), 'RGB')
            sheet.blit(pygame.transform.smoothscale(picture, (panel_w, panel_h)),
                       (column * panel_w, top + band))
            label = (f'{name}: legacy `needle` hull (procedural, {legacy_geometry["triangles"]} '
                     f'triangles)' if variant == 'legacy' else
                     f'{name}: authored mesh ({mesh_payload["triangle_count"]} triangles, '
                     f'{IDENTIFIER})')
            sheet.blit(font.render(label, True, (232, 232, 236)), (column * panel_w + 10, top + 4))
    sheet_path = out / 'imperial-corvette-comparison.png'
    pygame.image.save(sheet, str(sheet_path))
    pygame.font.quit()
    report['sheet'] = dict(image=sheet_path.name, bytes=sheet_path.stat().st_size,
                           sha256=sha256(sheet_path),
                           layout='top row the close pair, bottom row the wide pair, legacy left '
                                  'and authored right')

    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    for name in views:
        entry = report['comparison'][name]
        print(f'{name:6s} changed_pixels={entry["changed_pixels"]:>7d} '
              f'({entry["changed_percent"]:.4f}%) bbox={entry["bbox"]} '
              f'legacy_repeat_changed_pixels={entry["repeat_changed_pixels"]} '
              f'legacy_repeat_max_delta={entry["repeat_max_delta"]} '
              f'in_pass_repeats={entry["per_variant_repeat_changed_pixels"]} '
              f'framing_close_px={report["views"][name]["authored"]["framing"]["visible_px"]}')
    print(json.dumps(dict(variants_share_one_camera=report['one_camera_per_view'],
                          production_candidate_unselected=
                          report['production_candidate_unselected_after_review'],
                          row=ROW, registry_status=registration['registry_status'],
                          manifest_exists=registration['manifest_exists'],
                          in_production_pipeline=registration['in_production_pipeline']), indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
