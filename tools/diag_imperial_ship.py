#!/usr/bin/env python3
"""Evidence for one S06 B6 Imperial ship row: one camera, the legacy hull on the left and the
authored mesh on the right.

    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_imperial_ship.py --row imperial:corvette
    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_imperial_ship.py --row imperial:tie_squadron
    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_imperial_ship.py --row imperial:tie_bomber_squadron

`--row` takes the inventory's binding with or without its `ship:` prefix (the canonical inventory
spelling is `ship:imperial:tie_squadron`), the mesh identifier, the runtime registry key or the
row's label; it defaults to the Imperial corvette, the batch's first row. `--out` defaults to the
row's own review directory under `artifacts/s06_alliance_batch_review/`.

**A row is a row.** `ROWS` is a table: the inventory spelling, the runtime registry key the
renderer's ship path resolves, the mesh identifier and data id, the legacy shape, the binding's
measured legacy envelope and the minimum authored length, the label, the review directory. Nothing
below the table is written for one binding, and the legacy leg is measured from *this row's* legacy
shape in process (`ship_mesh(legacy_shape)`), so the two squadron rows sharing one legacy `wedge`
mesh is a property of the data rather than a special case here.

**The key is measured, not transcribed.** A squadron row is not a warship row: the renderer's ship
path does not read the binding's own suffix. `render.faction_visuals.ship_visual_key` calls
`render.asset_selection.ship_binding`, which maps the *data row's* category through the
fighter/bomber (and colonizer/constructor, convoy) role mapping and returns
`faction:role` only when `selected_binding` says it is served - so `ship:imperial:tie_squadron`
is served as `imperial:fighter` and `ship:imperial:tie_bomber_squadron` as `imperial:bomber`. The
harness therefore *measures* the key the ship path builds (a permissive `selected_binding` probe,
taken before any seam exists and thrown away) and asserts it equals the row's declared key before
patching that key and nothing else. Patching a plausible-looking key would draw the legacy hull on
both sides and be caught by the zero-pixel assertion; the probe names the failure instead.

The row is NOT registered - `assets/models/registry.json` keeps it at `procedural_legacy`, no
manifest exists for it, and nothing in production may select it - so a reviewer is shown the
candidate the way the S06 batch review does it: an explicit `model_preview` session plus a
monkeypatched selection for this one binding (`selected_binding` so the renderer's own ship path
mints the runtime key, and `mesh_for` so that binding resolves to the authored mesh JSON). Both
patches defer to the production functions for every other binding and are restored, with
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
W, H = 1280, 800
# The batch's own framing for one hull: `views_for`'s near distance and its tactical distance, as a
# factor on the row's own drawn length. A row that needs a floor states one (see `views_for`'s
# `close_floor` for why a small hull's near eye has to be kept clear of a hull box).
VIEWS = {'close': dict(factor=1.37, yaw=48., pitch=35.),
         'wide': dict(factor=5.57, yaw=48., pitch=55.)}
SUBJECT_SLOT = 'capital'
REVIEW_ROOT = ('artifacts', 's06_alliance_batch_review')


def placements(subject_data_id):
    """The row in its review situation: the subject in the batch's `capital` slot, drawn with the
    same fixed context group the batch review places for every row, so this is the row in the scene
    it will be looked at in rather than a scene built for it."""
    return [
        (SUBJECT_SLOT, 'ship', subject_data_id, 1, [-4200, 0, 2200], 0.),
        ('escort', 'ship', 'rebel_frigate', 0, [-4200, 0, 2900], 0.),
        ('battleship', 'ship', 'rebel_battleship', 0, [-4200, 0, 1500], 0.),
        ('enemy_a', 'ship', 'imperial_frigate', 1, [-3500, 0, 2200], -math.pi / 2),
        ('enemy_b', 'ship', 'imperial_frigate', 1, [-3500, 0, 2900], -math.pi / 2)]


# ------------------------------------------------------------------------------------------------ rows
# Keyed by the `--row` spelling. `row` is the inventory's canonical name; `registry_key` is the
# binding the renderer's ship path resolves for the data row (asserted against a measurement, see
# `runtime_key`); `envelope` is the binding's own legacy extent, as measured by
# `tools/art/probe_b6_scope.py` and recorded in the authoring seed's `ROWS` table; `min_length` is
# that envelope's Z extent less the seed's 0.2 world-unit float-noise allowance, the floor
# `render.authored_mesh._load_profile` is given; `directory` is where the review pictures land.
ROWS = {
    'imperial:corvette': dict(
        row='ship:imperial:corvette', registry_key='imperial:corvette',
        identifier='imperial_corvette', data_id='imperial_corvette',
        legacy_shape='needle', mesh='assets/models/imperial_corvette.mesh.json',
        envelope=((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0)), min_length=91.4,
        label='imperial-corvette', directory='b6-corvette'),
    'imperial:tie_squadron': dict(
        row='ship:imperial:tie_squadron', registry_key='imperial:fighter',
        identifier='imperial_tie_squadron', data_id='imperial_tie_squadron',
        legacy_shape='wedge', mesh='assets/models/imperial_tie_squadron.mesh.json',
        envelope=((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0)), min_length=63.796,
        label='imperial-tie-squadron', directory='b6-tie-squadron'),
    'imperial:tie_bomber_squadron': dict(
        row='ship:imperial:tie_bomber_squadron', registry_key='imperial:bomber',
        identifier='imperial_tie_bomber_squadron', data_id='imperial_tie_bomber_squadron',
        legacy_shape='wedge', mesh='assets/models/imperial_tie_bomber_squadron.mesh.json',
        envelope=((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0)), min_length=63.796,
        label='imperial-tie-bomber-squadron', directory='b6-tie-bomber-squadron'),
    # ---- rows 4 to 7: the two dagger capitals, the cruiser and the frigate ----
    # These are warship rows: the ship path reads the data row's own category, so the runtime key is
    # `imperial:<role>` directly (still *measured* below, not transcribed). The two dagger rows share
    # one legacy `dagger` mesh at one measured extent and the frigate shares the corvette's `needle`
    # box, which is why each row carries its own envelope and hull rather than a shape alias.
    'imperial:battleship': dict(
        row='ship:imperial:battleship', registry_key='imperial:battleship',
        identifier='imperial_battleship', data_id='imperial_battleship',
        legacy_shape='dagger', mesh='assets/models/imperial_battleship.mesh.json',
        envelope=((-38.45, 38.45), (-10.0, 39.5), (-80.183, 108.0)), min_length=188.0,
        label='imperial-battleship', directory='b6-battleship'),
    'imperial:supercapital': dict(
        row='ship:imperial:supercapital', registry_key='imperial:supercapital',
        identifier='imperial_supercapital', data_id='imperial_supercapital',
        legacy_shape='dagger', mesh='assets/models/imperial_supercapital.mesh.json',
        envelope=((-38.45, 38.45), (-10.0, 39.5), (-80.183, 108.0)), min_length=188.0,
        label='imperial-supercapital', directory='b6-supercapital'),
    'imperial:cruiser': dict(
        row='ship:imperial:cruiser', registry_key='imperial:cruiser',
        identifier='imperial_cruiser', data_id='imperial_cruiser',
        legacy_shape='cruiser', mesh='assets/models/imperial_cruiser.mesh.json',
        envelope=((-29.45, 29.45), (-7.0, 31.5), (-62.94, 78.0)), min_length=140.7,
        label='imperial-cruiser', directory='b6-cruiser'),
    'imperial:frigate': dict(
        row='ship:imperial:frigate', registry_key='imperial:frigate',
        identifier='imperial_frigate', data_id='imperial_frigate',
        legacy_shape='needle', mesh='assets/models/imperial_frigate.mesh.json',
        envelope=((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0)), min_length=91.4,
        label='imperial-frigate', directory='b6-frigate'),
    # ---- the last row of the batch: the convoy, the cluster the owner settled follows the siblings
    # It is the one row whose *legacy* visual key is a convoy key: `faction_visuals.ship_visual_key`
    # admits Imperial in the convoy branches, so with nothing patched the facade answers
    # `imperial:convoy` and `fleet_geometry.ship_mesh` normalises it back to the legacy `box` this row
    # draws today. So the legacy frame below is the legacy crate, and the row's `min_length` is that
    # crate's own Z extent less the seed's 0.2 world-unit float-noise allowance.
    'imperial:convoy': dict(
        row='ship:imperial:convoy', registry_key='imperial:convoy',
        identifier='imperial_convoy', data_id='imperial_crew_transport',
        legacy_shape='box', mesh='assets/models/imperial_convoy.mesh.json',
        envelope=((-20.0, 20.0), (-7.0, 26.5), (-24.6975, 24.35825)), min_length=48.85575,
        label='imperial-convoy', directory='b6-convoy'),
}

# A row answers to its own spelling, the inventory spelling, its mesh identifier and its runtime
# key. Two rows sharing a legacy shape must not share an alias, or `--row` would be ambiguous.
def _alias_table():
    table = {}
    for key, row in ROWS.items():
        for alias in (key, row['row'], row['identifier'], row['registry_key'], row['label']):
            owner = table.setdefault(alias, key)
            assert owner == key, f'--row alias {alias!r} is claimed by {owner} and {key}'
    return table


ALIASES = _alias_table()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--row', default='imperial:corvette',
                        help='the ship row to capture, e.g. imperial:tie_squadron or '
                             'ship:imperial:tie_squadron (default: imperial:corvette)')
    parser.add_argument('--out', type=Path,
                        help='output directory (default: the row\u2019s own review directory under '
                             f'{"".join(p + "/" for p in REVIEW_ROOT)})')
    args = parser.parse_args(argv)
    wanted = args.row.strip()
    if wanted not in ALIASES:
        parser.error(f'unknown row {args.row!r}; this harness authors {sorted(ROWS)} '
                     f'(canonical inventory spellings {"|".join(r["row"] for r in ROWS.values())})')
    key = ALIASES[wanted]
    row = ROWS[key]
    out = args.out.resolve() if args.out else ROOT.joinpath(*REVIEW_ROOT, row['directory'])
    return key, row, out


def main(argv=None):
    row_key, ROW, out = parse_args(argv)
    REGISTRY_KEY = ROW['registry_key']
    IDENTIFIER = ROW['identifier']
    DATA_ID = ROW['data_id']
    LEGACY_SHAPE = ROW['legacy_shape']
    MESH = ROW['mesh']
    ENVELOPE = ROW['envelope']
    MIN_LENGTH = ROW['min_length']
    LABEL = ROW['label']
    PLACEMENTS = placements(DATA_ID)
    # The row's review directory may already exist (it holds the row's withdrawn landing-manifest
    # draft), so this refuses a second capture into the same directory without refusing the row's
    # own directory: no run overwrites another run's frames or report.
    out.mkdir(parents=True, exist_ok=True)
    for taken in ('report.json', f'{LABEL}-comparison.png'):
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
    # Where the registry rows carry an envelope it is the binding's own legacy extent, so a row
    # whose declared extent drifted from the registry is refused rather than captured.
    if 'envelope' in row:
        declared = ((row['envelope']['min'][0], row['envelope']['max'][0]),
                    (row['envelope']['min'][1], row['envelope']['max'][1]),
                    (row['envelope']['min'][2], row['envelope']['max'][2]))
        assert declared == tuple(ENVELOPE), (declared, ENVELOPE)
    registration['registry_envelope_present'] = 'envelope' in row

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
    from render.faction_visuals import normalize_ship_key, ship_visual_key
    from render.fleet_geometry import ship_mesh
    from render.renderer import Renderer
    from render.ship_sizes import ship_size

    selection.configure({'model_preview': True}, asset_root=ROOT)
    production_mesh_for = selection.mesh_for
    production_selected_binding = selection.selected_binding
    assert not production_selected_binding(REGISTRY_KEY), 'the row must not be selected already'
    assert production_mesh_for(REGISTRY_KEY) is None, 'the row must not resolve in production'
    profile = _load_profile(mesh_path, IDENTIFIER, ENVELOPE, MIN_LENGTH)

    # The legacy shape is the data row's own, not the table's word for it: `ship_size` and the
    # renderer both read the shape out of the row, so a table entry that drifted from the data
    # would capture a hull the game does not draw.
    declared_shape = DataStore.get().ship_visual(DATA_ID)['shape']
    assert declared_shape == LEGACY_SHAPE, (declared_shape, LEGACY_SHAPE)

    # Which binding does the renderer's own ship path build for this row? Measured, not transcribed.
    # `ship_binding` maps the data row's category through the role mapping and returns the key only
    # when `selected_binding` says it is served, so a permissive probe answers with the key the ship
    # path would read. The probe is taken before the seam exists, is restored immediately, and
    # changes nothing that is drawn; a mismatch here means the seam below would patch a key nothing
    # reads, and the zero-pixel assertion would be the only thing left to say so.
    permissive = selection.selected_binding
    selection.selected_binding = lambda candidate: True
    try:
        derived_key = selection.ship_binding(DataStore.get(), DATA_ID, 'imperial')
    finally:
        selection.selected_binding = permissive
    assert derived_key == REGISTRY_KEY, (
        f'{ROW["row"]} is served as {derived_key!r}, not the declared runtime key '
        f'{REGISTRY_KEY!r}; the seam must patch the key the ship path reads')

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

    # The facade the renderer's fleet path actually asks, either side of the seam: with nothing
    # patched it must answer the legacy shape and select nothing, and inside the review session it
    # must answer the runtime key. This is the batch's servability measurement, taken in process.
    stock_visual_key = ship_visual_key(DataStore.get(), DATA_ID, 'imperial')
    active['enabled'] = True
    review_visual_key = ship_visual_key(DataStore.get(), DATA_ID, 'imperial')
    active['enabled'] = False
    # The legacy frame draws whatever the mesh path reads out of the facade's answer, and for a row
    # whose legacy branch is the convoy gate that answer is a convoy *key* rather than a shape string:
    # `<faction>:convoy` has no Imperial entry outside a preview session, so
    # `fleet_geometry.ship_mesh` normalises it back to the legacy shape the row draws today. The
    # normalised comparison is the same statement for every other row of the batch and a stronger one
    # for this row than comparing the strings would be, because it measures what is drawn rather than
    # what is named.
    stock_shape = normalize_ship_key(stock_visual_key)
    assert stock_shape == LEGACY_SHAPE, (stock_visual_key, stock_shape, LEGACY_SHAPE)
    assert review_visual_key == REGISTRY_KEY, (review_visual_key, REGISTRY_KEY)

    def scene():
        """A fresh, identical scene per pass, with the subject in the 'capital' slot."""
        gm, ids, _ = helper.build_scene()
        st = gm.state
        subject_id = ids[SUBJECT_SLOT]
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
    assert normalize_ship_key(legacy_size.shape) == LEGACY_SHAPE, legacy_size
    assert candidate_size.shape == REGISTRY_KEY, candidate_size
    assert abs(candidate_size.length - legacy_size.length) <= legacy_size.length * .01, (
        legacy_size, candidate_size)
    length = legacy_size.length

    # The legacy hull actually drawn, measured in process rather than transcribed.
    legacy_mesh = ship_mesh(LEGACY_SHAPE)
    legacy_geometry = dict(
        shape=LEGACY_SHAPE, source='render/fleet_geometry.py::_ship_mesh',
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
        'schema': 1, 'batch': BATCH, 'row': ROW['row'], 'row_argument': row_key,
        'registry_key': REGISTRY_KEY,
        'identifier': IDENTIFIER, 'status': 'review_only_not_registered',
        'integration': (f'UNAPPROVED review-only monkeypatch of render.asset_selection.'
                        f'selected_binding and render.asset_selection.mesh_for for this one binding, '
                        f'inside an explicit model_preview session. The renderer\'s ship path serves '
                        f'{ROW["row"]} as {REGISTRY_KEY} (measured: the data row\'s category goes '
                        f'through the fighter/bomber role mapping), so that measured key - and only '
                        f'that key - is patched. The registry row stays procedural_legacy, no '
                        f'manifest exists for the row and nothing in production selects it; both '
                        f'patches and the preview session are torn down at the end of this run.'),
        'warning': ('Offline orbit captures from the real production draw path: not paced FPS, not '
                    'a battle-acceptance or native-Windows-graphics acceptance, and not an owner '
                    'appearance decision.'),
        'registration': registration, 'legacy': legacy_geometry,
        'serving': dict(declared_runtime_key=REGISTRY_KEY, measured_runtime_key=derived_key,
                        legacy_shape_from_data=declared_shape,
                        stock_visual_key=stock_visual_key, review_visual_key=review_visual_key,
                        selected_binding_in_production=False, mesh_in_production=None,
                        note=('stock = the preview session with nothing patched; review = the same '
                              'session with this row\'s measured runtime key served')),
        'authored': dict(path=MESH, sha256=sha256(mesh_path), bytes=mesh_path.stat().st_size,
                         triangles=mesh_payload['triangle_count'],
                         vertices=len(mesh_payload['vertices']),
                         bounds=mesh_payload['bounds'],
                         roles=sorted(mesh_payload['batches']),
                         authority=mesh_payload['features'].get('authority'),
                         approval=mesh_payload['features'].get('approval')),
        'envelope': [list(a) for a in ENVELOPE],
        'min_authored_length': MIN_LENGTH,
        'drawn_size': dict(legacy=dict(shape=legacy_size.shape, scale=legacy_size.scale,
                                       length=legacy_size.length, radius=legacy_size.radius),
                           candidate=dict(shape=candidate_size.shape, scale=candidate_size.scale,
                                          length=candidate_size.length, radius=candidate_size.radius)),
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

    # A side-by-side sheet, so the change is looked at rather than only measured. The band names
    # the row and the runtime key it is served as, and says what the picture is not.
    pygame.font.init()
    font = pygame.font.SysFont('Helvetica', 18)
    band_lines = [
        f'UNAPPROVED REVIEW ONLY - {ROW["row"]} - legacy `{LEGACY_SHAPE}` hull vs authored mesh',
        f'served as runtime key {REGISTRY_KEY} - one camera, same tick, 4MSAA / production shaders '
        f'- drawn length {length:.2f}']
    panel_w, panel_h, band = W // 2, H // 2, 26
    header = 8 + 20 * len(band_lines) + 6
    sheet = pygame.Surface((W, header + len(views) * (panel_h + band)))
    sheet.fill((10, 14, 20))
    for line_index, line in enumerate(band_lines):
        sheet.blit(font.render(line, True, (198, 216, 234)), (12, 8 + line_index * 20))
    for row_index, name in enumerate(views):                    # close on top, wide below
        top = header + row_index * (panel_h + band)
        for column, variant in enumerate(('legacy', 'authored')):
            picture = pygame.image.frombuffer(frames[(variant, name)].tobytes(), (W, H), 'RGB')
            sheet.blit(pygame.transform.smoothscale(picture, (panel_w, panel_h)),
                       (column * panel_w, top + band))
            label = (f'{name}: legacy `{LEGACY_SHAPE}` hull (procedural, '
                     f'{legacy_geometry["triangles"]} triangles)' if variant == 'legacy' else
                     f'{name}: authored mesh ({mesh_payload["triangle_count"]} triangles, '
                     f'{IDENTIFIER})')
            sheet.blit(font.render(label, True, (232, 232, 236)), (column * panel_w + 10, top + 4))
    sheet_path = out / f'{LABEL}-comparison.png'
    pygame.image.save(sheet, str(sheet_path))
    pygame.font.quit()
    report['sheet'] = dict(image=sheet_path.name, bytes=sheet_path.stat().st_size,
                           sha256=sha256(sheet_path), row=ROW['row'], runtime_key=REGISTRY_KEY,
                           label_band=band_lines,
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
                          row=ROW['row'], serving=report['serving'],
                          registry_status=registration['registry_status'],
                          manifest_exists=registration['manifest_exists'],
                          in_production_pipeline=registration['in_production_pipeline']), indent=1))
    print('wrote', out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
