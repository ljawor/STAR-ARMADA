#!/usr/bin/env python3
"""Production embedded GPU pixel acceptance; deliberately NOT ordinary-main evidence.

Usage (parent/owner runs GPU gate after rebuilding armada_embedded):
  .venv/bin/python tools/render/probe_native_vector_hud.py --out "$TMPDIR/vector-pixels"
  Add --width 1920 --height 1080 (defaults: 2560 x 1440).
  Add --vector-only for the standalone --hud-only PIPELINE FIXTURE regression:
  no --top-hud-ring, direct production C ABI, shared shader/sampler + app alpha.
  Use a separate empty --out directory for each mode/resolution.

Based on probe_native_top_hud.py: real GameManager -> HUD -> LiveSession rings ->
production EmbeddedWindow.armada_frame -> actual, unretouched BGRA readback PNGs.
Only pygame.font is initialized; no SDL display, GL presentation, main loop, input
injection, simulation stepping, settings, saves, installation or build is performed.
A catalogue camera aimed at verified empty space is a KNOWN-VOID backdrop control,
not a fabricated game state. LiveSession still publishes the real skirmish HUD.

Contract: complete vector v1 snapshots, explicit clips, side transform .75 about
logical y=44, minimap [W-222,H-222,210,210], inset fog 202x202; row zero is -z.
Native top and vector layers are both below the Python/application overlay. See
native-side-hud-contract.md (implementation handoff), docs/NATIVE_TOP_HUD.md and
artifacts/native-top-hud/README.md for the distinction between embedded pipeline,
actual-main, physical input, frozen application and platform acceptance. Those
README evidence boundaries apply here: this probe proves none of the latter gates.
Synthetic primitives below are explicitly PIPELINE FIXTURES, never game evidence.
They test alpha/clips/fog classes absent from the unmodified match, not invented
contacts. Failure receipts remain passed=false; a black frame is never a pass.

This single-resolution gate does not establish resize, all-control interaction,
whole-game FPS, complete glyph repertoire, Windows/frozen-app or owner approval.
Run each desired drawable size separately under an external process deadline.
--help and Python compilation are CPU-only and import no renderer dependencies.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
LOGICAL = (1280, 800)
MINIMAP = (1058, 578, 210, 210)
FOG_RECT = (1062, 582, 202, 202)
VOID_FOCUS = '1000000,1000000,1000000'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8', errors='strict')


def text_aa_ramp_pixels(foreground, background, color):
    """Count color-consistent, strictly intermediate text coverage (CPU-only)."""
    import numpy as np

    fg = np.asarray(foreground, dtype=float)
    bg = np.asarray(background, dtype=float)
    vector = np.asarray(color[:3]) - bg
    denom = (vector*vector).sum(axis=2)
    coverage = ((fg-bg)*vector).sum(axis=2)/np.maximum(denom, 1)
    predicted = bg+coverage[...,None]*vector
    return int(((denom > 100) & (coverage > .05) & (coverage < .95)
                & (np.abs(fg-predicted).max(axis=2) <= 8)).sum())


def pipeline_fixture():
    """Synthetic display primitives ONLY; no game/world/contact data."""
    def rect(box, color, clip=(0, 0, 1280, 800)):
        return dict(kind='rect', clip=list(clip), rect=list(box), color=list(color),
                    stroke=0, radius=0)
    ops = [rect((0, 0, 1280, 800), (31, 53, 79, 255)),
           rect((80, 100, 180, 120), (210, 67, 33, 255), (110, 130, 90, 60)),
           rect((280, 120, 120, 100), (231, 41, 99, 128)),
           # Empty clip must produce no geometry at all, despite full-screen rect.
           rect((0, 0, 1280, 800), (255, 255, 0, 255), (440, 150, 0, 100)),
           dict(kind='ellipse', clip=[0, 0, 1280, 800], rect=[80, 300, 100, 70],
                color=[41, 211, 131, 255], stroke=0),
           dict(kind='circle', clip=[0, 0, 1280, 800], center=[260, 335], radius=28,
                color=[41, 131, 211, 255], stroke=0),
           dict(kind='line', clip=[0, 0, 1280, 800], points=[[340, 335], [420, 335]],
                color=[211, 131, 41, 255], stroke=8),
           dict(kind='polygon', clip=[0, 0, 1280, 800],
                points=[[470, 300], [520, 370], [420, 370]],
                color=[131, 41, 211, 255], stroke=0),
           dict(kind='fog', clip=[600, 100, 300, 300], rect=[600, 100, 300, 300])]
    return dict(version=1, active=True, logical_size=list(LOGICAL), ops=ops,
                fog=dict(cells=3, states='012201120'))


def malformed_candidates(good):
    """Whole candidates, with a visible leading op to detect partial application."""
    marker = pipeline_fixture()['ops'][0]
    marker['color'] = [255, 0, 255, 255]
    base = copy.deepcopy(good)
    base['ops'].insert(0, marker)
    variants = {}
    def changed(name, mutate):
        model = copy.deepcopy(base)
        mutate(model)
        variants[name] = json_bytes(model)
    changed('version', lambda m: m.update(version=2))
    changed('unknown_snapshot_key', lambda m: m.update(unexpected=1))
    changed('wrong_active_type', lambda m: m.update(active=1))
    changed('late_unknown_op_key', lambda m: m['ops'][-1].update(unexpected=True))
    changed('late_negative_clip', lambda m: m['ops'][-1].update(clip=[0, 0, -1, 20]))
    changed('bad_fog_length', lambda m: m.update(fog={'cells': 2, 'states': '012'}))
    changed('bad_fog_class', lambda m: m.update(fog={'cells': 2, 'states': '012x'}))
    changed('bad_color', lambda m: m['ops'][0].update(color=[256, 0, 0, 255]))
    changed('operation_budget', lambda m: m.update(ops=[marker] * 4097))
    circle = dict(kind='circle', clip=[0,0,1280,800], center=[640,400], radius=350,
                  color=[255,0,255,255], stroke=1)
    # Valid decode, rejected layout: exercise all-or-nothing geometry budgets too.
    changed('layout_vertex_budget', lambda m: m.update(ops=[marker]+[circle]*4095))
    text_op = dict(kind='text', clip=[0,0,1280,800], pos=[40,100], size=18,
                   text='\u0000', color=[255,0,255,255], bounds=[40,100,300,30], fit='shrink')
    changed('escaped_control_text', lambda m: m['ops'].append(text_op))
    payload = json_bytes(base)
    variants.update(raw_nul=payload + b'\0', raw_nul_junk=payload + b'\0junk',
                    raw_nul_invalid_utf8=payload + b'\0\xff', invalid_utf8=b'\xff' + payload,
                    truncated=payload[:-1], duplicate_key=payload.replace(
                        b'"version":1', b'"version":1,"version":1', 1),
                    nonfinite=payload.replace(b'"stroke":0', b'"stroke":NaN', 1),
                    payload_budget=b' ' * (5 * 1024 * 1024 + 1))
    return variants


def open_vector_only(argv):
    """Same production C ABI, with a valueless flag EmbeddedWindow cannot parse.

    EmbeddedWindow.__init__ currently slices all arguments in pairs, so passing
    --hud-only through it raises before C++ runs. Do not remove that flag or add
    a top ring: bind the exact same library/ABI and return its normal readback/
    terminate owner, without calling its GL-presenting method.
    """
    import ctypes
    import os
    from render_bridge.embedded import EmbeddedWindow
    name = 'armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib'
    candidates = [os.environ.get('STAR_ARMADA_CPP_LIBRARY')]
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        candidates.append(str(Path(bundle) / 'cpp' / name))
    candidates.append(str(ROOT / 'render_cpp/build-w02' / name))
    library = next((p for p in candidates if p and Path(p).is_file()), None)
    if library is None:
        raise RuntimeError('Build the armada_embedded shared-library target first')
    window = EmbeddedWindow.__new__(EmbeddedWindow)
    width, height = (int(argv[argv.index(flag)+1]) for flag in ('--width','--height'))
    window.size = (width,height)
    window._texture = None
    window._handle = None
    window._pixels = (ctypes.c_ubyte * (width*height*4))()
    window._lib = lib = ctypes.CDLL(library)
    lib.armada_abi_version.restype = ctypes.c_uint
    if lib.armada_abi_version() != 1:
        raise RuntimeError('Unsupported native renderer ABI')
    lib.armada_open.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
    lib.armada_open.restype = ctypes.c_void_p
    lib.armada_frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    lib.armada_frame.restype = ctypes.c_int
    lib.armada_error.argtypes = [ctypes.c_void_p]
    lib.armada_error.restype = ctypes.c_char_p
    lib.armada_close.argtypes = [ctypes.c_void_p]
    lib.armada_close.restype = None
    encoded = (ctypes.c_char_p * len(argv))(*(os.fsencode(p) for p in argv))
    window._handle = lib.armada_open(len(argv), encoded)
    if not window._handle:
        raise RuntimeError('Could not initialize vector-only production native renderer session')
    return window


def run(args, report):
    # Deliberately lazy: --help and compile cannot create a GPU/SDL context.
    import numpy as np
    import pygame
    from PIL import Image
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from game.net.replay import state_checksum
    from render import i18n
    from render.fog import FogMask, known_entities
    from render.hud import HUD
    from render_bridge import overlay, top_hud, vector_hud
    from render_bridge.live import LiveSession
    from render_bridge.embedded import EmbeddedWindow

    def check(name, condition, **details):
        row = dict(check=name, passed=bool(condition), **details)
        report['checks'].append(row)
        if not condition:
            raise AssertionError(f'{name}: {json.dumps(details, ensure_ascii=False)}')

    def box(rect):
        x, y, w, h = rect
        return (round(x * args.width / 1280), round(y * args.height / 800),
                round((x + w) * args.width / 1280), round((y + h) * args.height / 800))

    def region(image, rect):
        return np.asarray(image.crop(box(rect)).convert('RGB')).astype(np.int16)

    def identical(name, a, b, rect=None):
        aa = region(a, rect) if rect else np.asarray(a.convert('RGB'))
        bb = region(b, rect) if rect else np.asarray(b.convert('RGB'))
        check(name, np.array_equal(aa, bb), changed_pixels=int(np.any(aa != bb, axis=2).sum()))

    def expect_color(name, image, rect, expected, tolerance=3):
        pixels = region(image, rect)
        error = np.abs(pixels - np.asarray(expected)).max(axis=2)
        check(name, pixels.size > 0 and bool((error <= tolerance).all()),
              expected=list(expected), max_channel_error=int(error.max()) if error.size else None,
              sample_logical=list(rect))

    def rgb_alpha(source, background):
        c = np.asarray(source, dtype=float)
        return np.rint(c[:3] * c[3] / 255 + np.asarray(background) * (1 - c[3] / 255)).astype(int).tolist()

    session = window = hud = None
    language = i18n.language()
    pygame.font.init()  # No pygame.init(), display.set_mode(), present(), or draw_gl().
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    state = gm.state
    original_checksum = state_checksum(state)
    report['state_checksum_before'] = original_checksum
    # Snapshot actual persistent files, without creating any save/settings directories.
    protected = [ROOT / 'saves' / f'{name}.json' for name in ('settings', 'campaign', 'balance')]
    def protected_hashes():
        return {str(p): digest(p.read_bytes()) if p.exists() else None for p in protected}
    original_files = protected_hashes()
    report['protected_before'] = original_files
    try:
        check('no_pygame_display', pygame.display.get_surface() is None)
        hud = HUD(*LOGICAL, state)
        check('source_hud_inactive_before_session', hud.native_panels is False)
        session = LiveSession(state, gm.ds, directory=args.out / 'rings', size=LOGICAL,
                              hud=hud, overlay_keyframe=0.00001)
        check('default_session_native_panels', hud.native_panels is True)
        check('default_session_native_top', hud.native_top_bar is True)
        visible = {e.id for e in state.entities.values() if e.alive and state.can_see(0, e.id)}
        stations = [e for e in state.entities.values() if e.id in visible and e.owner == 0 and e.is_station]
        check('real_own_station_available', bool(stations))
        selected = {next((e for e in stations if 'command' in e.data_id), stations[0]).id}
        report.update(selected_ids=sorted(selected), visible_ids=sorted(visible),
                      known_ids=sorted(e.id for e in known_entities(state, 0)))
        i18n.set_language('en')
        session.publish(state, selection=selected, visible_ids=visible, paused=False, fps=0)
        model = hud.native_vector_model()
        check('complete_default_model', model['active'] and bool(model['ops']) and model['fog'] is not None)
        check('minimap_logical_unchanged', tuple(hud.minimap_rect) == MINIMAP,
              actual=list(hud.minimap_rect), expected=list(MINIMAP))
        for x in (10, 1030):
            check(f'compact_panel_{x}', any(r.x == x and r.y == 44 and r.width == 240
                                          for r in hud.blocked_rects))
        for panel in ('left', 'right'):
            buttons = [b for b in hud.buttons if b.get('panel') == panel]
            check(f'compact_{panel}_controls_exist', bool(buttons))
            limits = pygame.Rect(10 if panel == 'left' else 1030, 44, 240, 567)
            check(f'compact_{panel}_controls_inside_scope', all(limits.contains(b['rect']) for b in buttons))
        report['controls'] = [dict(kind=b['kind'], rect=list(b['rect']), panel=b.get('panel')) for b in hud.buttons]
        fog_ops = [o for o in model['ops'] if o['kind'] == 'fog']
        check('one_unchanged_minimap_fog_bounds', len(fog_ops) == 1 and tuple(fog_ops[0]['rect']) == FOG_RECT,
              fog_ops=fog_ops)
        report['real_model_sha256'] = digest(vector_hud.encode(model))
        # Deliberately no --ring: this isolates the native HUD exactly like the proven
        # top-HUD helper. The catalogue backdrop is aimed at empty space, NOT a match.
        argv = ['viewer', '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
                '--assets', str(ROOT), '--width', str(args.width), '--height', str(args.height),
                '--overlay-ring', str(session.paths['overlay']),
                '--vector-hud-ring', str(session.paths['vector_hud']),
                '--focus', VOID_FOCUS, '--distance', '1000', '--seconds', '0']
        if args.vector_only:
            # This is intentionally NOT worked around by attaching an unused top
            # ring. It must create its own shared shader/sampler and preserve alpha.
            argv.append('--hud-only')
            report['mode'] = 'vector-only production embedded GPU PIPELINE FIXTURE; no top ring; --hud-only'
        else:
            argv += ['--top-hud-ring', str(session.paths['top_hud'])]
        report['viewer_argv'] = argv
        window = open_vector_only(argv) if args.vector_only else EmbeddedWindow(argv, root=ROOT)
        check('actual_drawable_size', tuple(window.size) == (args.width, args.height))
        library_path = Path(window._lib._name).resolve()
        report['native_library'] = dict(path=str(library_path), sha256=digest(library_path.read_bytes()))
        report['probe_sha256'] = digest(Path(__file__).read_bytes())

        def draw(name):
            # Readback view 4 is asynchronous; flush the same candidate three frames.
            for _ in range(3):
                count = window._lib.armada_frame(window._handle, window._pixels, len(window._pixels))
                raw_error = window._lib.armada_error(window._handle)
                error = raw_error.decode('utf-8', errors='strict') if raw_error else ''
                check(f'{name}_readback_{_}', count == len(window._pixels) and not error,
                      returned=count, expected=len(window._pixels), native_error=error)
            image = Image.frombytes('RGBA', window.size, bytes(window._pixels), 'raw', 'BGRA')
            image.save(args.out / f'{name}.png')
            report['images'][name] = dict(file=f'{name}.png', rgba_sha256=digest(image.tobytes()),
                                         png_sha256=digest((args.out / f'{name}.png').read_bytes()))
            return image

        def publish_vector(candidate):
            session._vector_hud.publish(vector_hud.encode(candidate))

        def publish_malformed(payload):
            if len(payload) <= vector_hud.MAX_PAYLOAD:
                session._vector_hud.publish(payload)
                return
            # Exercise the ordinary transport limit, without enlarging its ring.
            from render_bridge.ring import RingError
            try:
                session._vector_hud.publish(payload)
            except RingError:
                check('oversize_payload_rejected_by_transport', True, bytes=len(payload))
            else:
                check('oversize_payload_rejected_by_transport', False, bytes=len(payload))

        def transparent_overlay():
            session._overlay.publish(overlay.encode(*LOGICAL, full=bytes(1280 * 800 * 4)))

        def top(active):
            session._top_hud.publish(top_hud.encode(top_hud.build(state, 0, active=active, fps=0)))

        inactive = dict(version=1, active=False, logical_size=list(LOGICAL), ops=[], fog=None)
        if args.vector_only:
            check('vector_only_has_no_top_ring', '--top-hud-ring' not in argv and '--hud-only' in argv)
            transparent_overlay()
            fixture = pipeline_fixture()
            publish_vector(fixture)
            actual = draw('VECTOR-ONLY-PIPELINE-FIXTURE-transparent-overlay')
            expect_color('vector_only_shared_program_sampler_draws_with_transparent_app', actual,
                         (940,440,100,100), (31,53,79))
            expect_color('vector_only_geometry_alpha', actual, (300,140,60,50),
                         rgb_alpha((231,41,99,128),(31,53,79)))
            # Partial app alpha must composite over native geometry, not replace it
            # unblended merely because --hud-only was specified without a top ring.
            translucent = pygame.Surface(LOGICAL, pygame.SRCALPHA)
            translucent.fill((64,128,192,128))
            session._overlay.publish(overlay.encode_surface_full(translucent))
            half = draw('VECTOR-ONLY-PIPELINE-FIXTURE-half-alpha-app')
            expect_color('vector_only_hud_only_app_alpha_blends', half, (940,440,100,100),
                         rgb_alpha((64,128,192,128),(31,53,79)))
            transparent_overlay()
            identical('vector_only_transparent_overlay_restores_native', actual,
                      draw('VECTOR-ONLY-PIPELINE-FIXTURE-restored'))
            for name, payload in malformed_candidates(fixture).items():
                publish_malformed(payload)
                identical(f'vector_only_malformed_{name}_retains_good', actual,
                          draw(f'VECTOR-ONLY-malformed-{name}'))
            publish_vector(inactive)
            cleared = draw('VECTOR-ONLY-PIPELINE-FIXTURE-inactive')
            check('vector_only_inactive_clears', not np.array_equal(
                  region(actual,(940,440,100,100)),region(cleared,(940,440,100,100))))
            identical('vector_only_inactive_repeatable', cleared,
                      draw('VECTOR-ONLY-PIPELINE-FIXTURE-inactive-repeat'))
            publish_vector(fixture)
            identical('vector_only_reactivate_repeatable', actual,
                      draw('VECTOR-ONLY-PIPELINE-FIXTURE-reactivated'))
            report['pipeline_fixture'] = fixture
            report['boundaries'].append('vector-only mode tests standalone shader/alpha pipeline, not language/minimap game acceptance')
            check('simulation_checksum_unchanged', state_checksum(state) == original_checksum)
            check('persistent_files_unchanged', protected_hashes() == original_files)
            return
        default = draw('default-production-panels')
        transparent_overlay()
        publish_vector(inactive)
        top(False)
        void = draw('inactive-transparent-known-void')
        identical('known_void_repeatability', void, draw('known-void-repeat'))
        # Ordinary viewer clear = 0x080e1bff, plus static additive stars. Require
        # a predominantly known-clear void, not merely a nonblack picture. Never
        # assume a whole rectangle is star-free or compare HUD pixels to black.
        void_pixels = np.asarray(void.convert('RGB')).astype(int)
        known_clear = np.all(void_pixels == (8, 14, 27), axis=2)
        check('known_void_clear_color', float(known_clear.mean()) >= .90,
              expected_rgb=[8,14,27], exact_clear_fraction=float(known_clear.mean()))
        report['known_void_rgba_sha256'] = digest(void.tobytes())
        publish_vector(model)
        active = draw('active-transparent-overlay')
        for name, scope in (('left', (10, 44, 240, 400)),
                            ('right', (1030, 44, 240, 400)), ('minimap', MINIMAP)):
            delta = np.any(region(active, scope) != region(void, scope), axis=2)
            check(f'{name}_native_active_vs_inactive', int(delta.sum()) >= 20,
                  changed_pixels=int(delta.sum()))
        identical('production_vector_repeatability', active, draw('active-repeat'))
        # Nothing may leak outside union of the production's explicit clips.
        clip_mask = np.zeros((args.height, args.width), dtype=bool)
        for op in model['ops']:
            x0, y0, x1, y1 = box(op['clip'])
            clip_mask[max(0, y0-1):min(args.height, y1+1), max(0, x0-1):min(args.width, x1+1)] = True
        changed = np.any(np.asarray(active.convert('RGB')) != np.asarray(void.convert('RGB')), axis=2)
        check('real_model_pixels_within_owned_clips', not bool((changed & ~clip_mask).any()))

        # Independent semantic oracle uses production FogMask's actual colours and
        # authoritative spheres/exploration, not the vector producer's cell answers.
        mask_surface = FogMask().surface(state, 0)
        oracle_rgb = pygame.surfarray.array3d(mask_surface).transpose(1, 0, 2)
        oracle_alpha = pygame.surfarray.array_alpha(mask_surface).T
        oracle_states = np.where(oracle_alpha == 0, '2', np.where(oracle_alpha == 155, '1', '0'))
        n = model['fog']['cells']
        check('real_fog_classification_and_negative_z_row_order',
              oracle_states.shape == (n, n) and ''.join(oracle_states.ravel()) == model['fog']['states'],
              cells=n, classes={str(c): int((oracle_states == c).sum()) for c in '012'})
        # Markers sit above fog. Exclude them (and a two-pixel margin) when sampling
        # cell centres, so a real contact cannot be mistaken for a fog colour error.
        miniops = [o for o in model['ops'] if o['clip'] == list(MINIMAP)]
        markers = [o for o in miniops if o['kind'] != 'fog'
                   and o.get('rect') != list(MINIMAP)]
        def marker_near(x, y):
            for op in markers:
                if op['kind'] == 'circle':
                    if abs(x-op['center'][0]) <= op['radius']+3 and abs(y-op['center'][1]) <= op['radius']+3:
                        return True
                elif 'rect' in op:
                    a, b, w, h = op['rect']
                    if a-3 <= x <= a+w+3 and b-3 <= y <= b+h+3:
                        return True
                elif 'points' in op:
                    xs, ys = zip(*op['points'])
                    if min(xs)-3 <= x <= max(xs)+3 and min(ys)-3 <= y <= max(ys)+3:
                        return True
            return False
        samples = {c: [] for c in '012'}
        active_pixels = np.asarray(active.convert('RGB')).astype(int)
        for row in range(n):
            for col in range(n):
                cls = str(oracle_states[row, col])
                if len(samples[cls]) >= 16:
                    continue
                lx, ly = 1062 + (col+.5)*202/n, 582 + (row+.5)*202/n
                if marker_near(lx, ly):
                    continue
                px, py = int(lx*args.width/1280), int(ly*args.height/800)
                # Skip ambiguous nearest-neighbour texel edges at low drawables.
                u, v = (px+.5)*1280/args.width, (py+.5)*800/args.height
                if int((u-1062)*n/202) != col or int((v-582)*n/202) != row:
                    continue
                rgba = list(oracle_rgb[row, col]) + [int(oracle_alpha[row, col])]
                background = rgb_alpha((8,10,16,225), void_pixels[py,px])
                expected = rgb_alpha(rgba, background)
                actual = active_pixels[py, px].tolist()
                samples[cls].append(dict(row=row, col=col, pixel=[px, py], expected=expected, actual=actual))
                check(f'real_fog_{row}_{col}_pixel', max(abs(a-b) for a,b in zip(actual, expected)) <= 4,
                      semantic_class=cls, pixel=[px, py], actual=actual, expected=expected)
        for cls in '012':
            if bool((oracle_states == cls).any()):
                check(f'real_fog_class_{cls}_sampled', bool(samples[cls]))
        report['real_fog_samples'] = samples
        report['absent_real_fog_classes_tested_only_by_pipeline_fixture'] = [c for c in '012' if not bool((oracle_states == c).any())]

        # Visible-contact projection and colour derive from actual game contacts.
        contacts = []
        for e in known_entities(state, 0):
            if e.id not in visible or e.is_planet or e.owner < 0:
                continue
            cx = int(1163 + e.pos.x / (state.map_info.bounds/2) * 101)
            cy = int(683 + e.pos.z / (state.map_info.bounds/2) * 101)
            color = list(hud._owner_rgb(e.owner))
            candidates = [o for o in miniops if o.get('color', [])[:3] == color and (
                o.get('center') == [cx, cy] or o.get('rect') == [cx-2, cy-2, 4, 4]
                or o.get('points') == [[cx-2, cy], [cx+2, cy]])]
            check(f'real_contact_{e.id}_projection', bool(candidates), entity_id=e.id,
                  logical_center=[cx, cy], expected_rgb=color)
            patch = region(active, (cx-2, cy-2, 4, 4))
            # A one-logical-pixel contact need not contain any fully opaque
            # MSAA pixel. Compare against the SAME scene without that marker,
            # measuring its actual source-over color ramp, not endpoint RGB.
            no_contact = copy.deepcopy(model)
            no_contact['ops'] = [op for op in no_contact['ops'] if op not in candidates]
            publish_vector(no_contact)
            control = draw(f'display-control-no-contact-{e.id}')
            background = region(control, (cx-2, cy-2, 4, 4)).astype(float)
            vector = np.asarray(color, dtype=float) - background
            denom = (vector * vector).sum(axis=2)
            coverage = ((patch - background) * vector).sum(axis=2) / np.maximum(denom, 1)
            predicted = background + coverage[..., None] * vector
            hits = int(((denom > 100) & (coverage >= .2) & (coverage <= 1.05)
                        & (np.abs(patch - predicted).max(axis=2) <= 6)).sum())
            publish_vector(model)
            # A selected white ring may border the marker, but must not erase it.
            check(f'real_contact_{e.id}_gpu_color', hits >= 1, color_pixels=hits)
            contacts.append(dict(id=e.id, logical_center=[cx, cy], color=color, color_pixels=hits))
        check('real_visible_contacts_exercised', bool(contacts))
        report['visible_contacts'] = contacts
        # Last-good means last APPLIED record. Settle the final restoration
        # before a newer malformed record can replace it in the latest reader.
        identical('contact_controls_restore_full_snapshot', active, draw('contacts-restored'))
        from game.systems.collection_points import collection_capable
        known = list(known_entities(state, 0))
        expected_markers = sum(e.is_planet or e.owner != -1 for e in known)
        expected_markers += sum(state.known_entity(0,eid) is not None for eid in selected)
        expected_markers += 2*sum(getattr(e,'collection_point',None) is not None
                                  and collection_capable(e) and e.owner == 0 and e.id in selected
                                  for e in known)
        check('minimap_exact_known_contact_marker_inventory', len(markers) == expected_markers,
              actual=len(markers), expected=expected_markers,
              unknown_ids=sorted(eid for eid in state.entities if state.known_entity(0,eid) is None))

        # Complete invalid candidates must not partially replace last-good geometry.
        for name, payload in malformed_candidates(model).items():
            publish_malformed(payload)
            rejected = draw(f'malformed-{name}')
            identical(f'malformed_{name}_retains_last_good', active, rejected)
        publish_vector(inactive)
        cleared = draw('inactive-cleared')
        identical('inactive_removes_previous_geometry', void, cleared)
        publish_vector(model)
        identical('reactivation_restores_snapshot', active, draw('reactivated'))

        # Each language comes through the real HUD producer. Text-suppression is a
        # labelled display-only negative control, not a hand-authored translation.
        language_pixels = {}
        for code in ('en', 'de', 'pl', 'ru'):
            check(f'{code}_language_pack_loaded', i18n.set_language(code) == code)
            session.publish(state, selection=selected, visible_ids=visible, fps=0)
            current = hud.native_vector_model()
            transparent_overlay()
            top(False)
            translated = draw(f'production-language-{code}')
            no_text = copy.deepcopy(current)
            no_text['ops'] = [op for op in current['ops'] if op['kind'] != 'text']
            publish_vector(no_text)
            control = draw(f'display-control-no-text-{code}')
            fg_all = np.asarray(translated.convert('RGB'))
            bg_all = np.asarray(control.convert('RGB'))
            pixels = np.any(fg_all != bg_all, axis=2)
            check(f'{code}_native_text_present', int(pixels.sum()) >= 8,
                  glyph_pixels=int(pixels.sum()), text_ops=sum(op['kind']=='text' for op in current['ops']))
            # AA needs strictly intermediate coverage against local no-text
            # backgrounds; opaque glyph interiors are not evidence of smoothing.
            ramp_hits = 0
            for op in current['ops']:
                if op['kind'] != 'text':
                    continue
                x0, y0, x1, y1 = box(op['bounds'])
                if x1 <= x0 or y1 <= y0:
                    continue
                fg = fg_all[y0:y1,x0:x1]
                bg = bg_all[y0:y1,x0:x1]
                ramp_hits += text_aa_ramp_pixels(fg, bg, op['color'])
            check(f'{code}_antialiased_text_color_ramps', ramp_hits >= 8, ramp_pixels=ramp_hits)
            language_pixels[code] = digest(pixels.tobytes())
            report['languages'].append(dict(language=code, model_sha256=digest(vector_hud.encode(current)),
                model_bytes=len(vector_hud.encode(current)), glyph_pixels=int(pixels.sum()),
                aa_ramp_pixels=ramp_hits, text_mask_sha256=language_pixels[code],
                texts=[op['text'] for op in current['ops'] if op['kind']=='text']))
        for code in ('de', 'pl', 'ru'):
            check(f'{code}_glyph_mask_differs_from_english', language_pixels[code] != language_pixels['en'])

        # Both native streams must survive transparent app overlays independently;
        # the real vector model must leave the existing top strip untouched.
        i18n.set_language('en')
        session.publish(state, selection=selected, visible_ids=visible, fps=0)
        transparent_overlay()
        publish_vector(inactive)
        top(True)
        top_only = draw('top-only-transparent-overlay')
        publish_vector(model)
        both = draw('top-and-vector-transparent-overlay')
        identical('vector_does_not_damage_top_strip', top_only, both, (0, 0, 1280, 34))
        check('top_strip_active_vs_inactive', not np.array_equal(region(top_only,(0,0,1280,34)),region(void,(0,0,1280,34))))
        cover = pygame.Surface(LOGICAL, pygame.SRCALPHA)
        cover.fill((251, 17, 83, 255))
        session.publish(state, selection=selected, visible_ids=visible, overlay_layers=[cover], fps=0)
        covered = draw('opaque-app-overlay-covers-all-native-layers')
        expect_color('opaque_application_overlay_over_top_and_vector', covered, (0,0,1280,800), (251,17,83), 0)

        # Synthetic PIPELINE fixture: a deterministic opaque ground makes alpha,
        # nearest fog sampling/orientation and clip leakage directly measurable.
        transparent_overlay()
        top(False)
        fixture = pipeline_fixture()
        publish_vector(fixture)
        image = draw('PIPELINE-FIXTURE-primitives-alpha-clips-fog')
        for name, rect, color in (
            ('clipped_inside', (120,140,60,30), (210,67,33)),
            ('clipped_outside', (85,105,15,15), (31,53,79)),
            ('empty_clip', (440,155,20,20), (31,53,79)),
            ('alpha', (300,140,60,50), rgb_alpha((231,41,99,128),(31,53,79))),
            ('ellipse', (115,325,20,20), (41,211,131)),
            ('circle', (250,325,20,20), (41,131,211)),
            ('line', (355,333,40,4), (211,131,41)),
            ('polygon', (460,340,20,10), (131,41,211))):
            expect_color(f'pipeline_fixture_{name}', image, rect, color)
        fog_colors = {'0': (3,6,13,255), '1': (12,22,38,155), '2': (12,22,38,0)}
        for row in range(3):
            for col in range(3):
                cls = fixture['fog']['states'][row*3+col]
                expect_color(f'pipeline_fixture_fog_row_{row}_col_{col}_class_{cls}', image,
                             (620+col*100,120+row*100,40,40), rgb_alpha(fog_colors[cls],(31,53,79)))
        identical('pipeline_fixture_repeatability', image, draw('PIPELINE-FIXTURE-repeat'))
        publish_vector(inactive)
        identical('pipeline_fixture_inactive_clears', void, draw('PIPELINE-FIXTURE-inactive'))
        report['pipeline_fixture'] = fixture
        report['default_capture'] = 'default-production-panels.png'
        check('simulation_checksum_unchanged', state_checksum(state) == original_checksum,
              before=original_checksum, after=state_checksum(state))
        check('persistent_files_unchanged', protected_hashes() == original_files)
        check('still_no_pygame_display', pygame.display.get_surface() is None)
    finally:
        # Cleanup errors are failures too; do not silently turn a failed teardown green.
        cleanup_errors = []
        for obj in (window, session, hud):
            if obj is not None:
                try:
                    obj.terminate() if obj is window else obj.close()
                except Exception as exc:
                    cleanup_errors.append(f'{type(obj).__name__}: {exc}')
        i18n.set_language(language)
        report['state_checksum_after'] = state_checksum(state)
        report['protected_after'] = protected_hashes()
        if cleanup_errors:
            report['cleanup_errors'] = cleanup_errors
            raise RuntimeError('; '.join(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True, type=Path, help='new output directory for actual GPU PNGs and metrics.json')
    parser.add_argument('--width', type=int, default=2560)
    parser.add_argument('--height', type=int, default=1440)
    parser.add_argument('--vector-only', action='store_true',
                        help='standalone PIPELINE FIXTURE: --hud-only with no top ring; direct production C ABI')
    args = parser.parse_args()
    if not (320 <= args.width <= 7680 and 240 <= args.height <= 4320):
        parser.error('drawable bounds: width 320..7680, height 240..4320')
    args.out = args.out.expanduser().resolve()
    # Never mix a failed partial rerun with a previous passing receipt/PNG set.
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('--out must be empty or nonexistent; retain earlier evidence separately')
    # User-data output locations are not allowed, even if currently empty.
    for forbidden in (ROOT/'saves', ROOT/'replays', ROOT/'assets', ROOT/'render_cpp'):
        if args.out == forbidden or forbidden in args.out.parents:
            parser.error(f'output must not be inside {forbidden}')
    args.out.mkdir(parents=True, exist_ok=True)
    report = dict(passed=False, drawable=[args.width,args.height], logical_size=list(LOGICAL),
                  mode='production embedded GPU; real skirmish HUD; catalogue known-void backdrop',
                  capture='unretouched BGRA armada_frame readback; no GL/SDL display',
                  checks=[], images={}, languages=[],
                  boundaries=['not ordinary-main gameplay or physical input acceptance',
                              'not resize/performance/frozen-app/Windows acceptance',
                              'synthetic primitives are separately labelled PIPELINE FIXTURES',
                              'absent real fog classes are covered by fixtures only'])
    try:
        run(args, report)
        report['passed'] = True
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n'
        (args.out/'metrics.json').write_text(text, encoding='utf-8', errors='strict', newline='\n')
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
