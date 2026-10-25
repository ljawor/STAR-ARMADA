"""Native campaign briefing: C++ vector ops only, complete content, safe state.

The campaign intro used to be composed as two raster strips into `hud.ring`. These
tests pin the replacement contract: `CampaignCinematic.native_model()` is a complete
`render_bridge.vector_hud` snapshot (text + geometry, no glyph atlas blits), the card
stays bounded and centred below the native resource strip at every size the game can
be asked to draw, and pagination never drops briefing or objective text.
"""
import copy

import pygame
import pytest

from render import mission_briefing
from render.camera import Camera
from render.cinematics import CampaignCinematic
from render_bridge import vector_hud

VIEWPORTS = ((640, 480), (1280, 800), (2560, 1440))
SKIP_LABEL = 'Enter / Space / Esc / click to skip'
OUTCOMES = (('MISSION COMPLETE', 'Objectives secured. Return to fleet command.'),
            ('MISSION FAILED', 'The operation has ended. Regroup and try again.'))

MISSION = {
    'id': 'briefing-test',
    'name': 'First Fleet',
    'briefing': 'Establish a foothold in the Orion Reach.\nHold the relay until the convoy clears.',
    'objectives': [
        {'text': 'Build a command station.'},
        {'description': 'Escort the supply convoy to the relay.'},
    ],
}


def movie(mission=None, **kwargs):
    pygame.font.init()
    return CampaignCinematic(copy.deepcopy(mission or MISSION), Camera(1280, 800),
                             reduced_motion=True, **kwargs)


def texts(model):
    return [op for op in model['ops'] if op['kind'] == 'text']


def card_rect(model):
    """The filled rounded card, the only filled rect that carries a corner radius."""
    cards = [op for op in model['ops']
             if op['kind'] == 'rect' and op['stroke'] == 0 and op.get('radius', 0) > 0]
    assert len(cards) == 1, f'expected one native briefing card, got {len(cards)}'
    return pygame.Rect(cards[0]['rect'])


def body_texts(model, layout):
    return [op['text'] for op in model['ops'] if op['kind'] == 'text'
            and layout['body_top'] <= op['pos'][1] < layout['body_bottom']]


def build(width, height, *, mission=None, outcome=None, elapsed=0.0):
    source = mission or MISSION
    return mission_briefing.build(
        width, height, title=source['name'], briefing=source['briefing'],
        objectives=[o.get('text', o.get('description', '')) for o in source['objectives']],
        outcome=outcome, elapsed=elapsed)


@pytest.mark.parametrize('width,height', VIEWPORTS)
def test_native_model_is_a_valid_bounded_card_below_the_strip(width, height):
    model = movie().native_model(width, height)
    vector_hud.encode(model)  # must be publishable without a second validation pass
    assert set(model) == {'version', 'active', 'logical_size', 'ops', 'fog'}
    assert model['active'] is True and model['fog'] is None
    assert model['logical_size'] == [width, height]
    assert model['ops'], 'native briefing emitted nothing'
    # One identity scope for the whole screen: no per-panel transforms to undo.
    assert all(op['clip'] == [0, 0, width, height] for op in model['ops'])

    dim, card = model['ops'][0], card_rect(model)
    assert dim['kind'] == 'rect' and pygame.Rect(dim['rect']) == pygame.Rect(0, 0, width, height)
    assert 80 <= dim['color'][3] <= 200, 'the world must stay visible behind the briefing'
    assert card.width <= 900, 'briefing card grew into a full-width banner'
    assert card.width <= width * .8
    assert abs(card.centerx - width // 2) <= 1, 'card is not horizontally centred'
    assert card.top >= 44, 'card overlaps the native resource strip'
    assert card.bottom <= height and card.left >= 0 and card.right <= width

    for op in model['ops']:
        if op['kind'] in ('rect', 'ellipse'):
            rect = pygame.Rect(op['rect'])
            assert rect.width > 0 and rect.height > 0
            assert pygame.Rect(0, 0, width, height).contains(rect)
    for op in texts(model):
        assert op['text'], 'empty native text op'
        bounds = pygame.Rect(op['bounds'])
        assert card.contains(bounds), f'glyph box escapes the card: {op["text"]!r} {bounds}'
        assert op['pos'] == op['bounds'][:2], 'native text must anchor its own ink box'
        assert 0 < op['size'] <= 256
        assert op['fit'] == 'shrink'


@pytest.mark.parametrize('width,height', VIEWPORTS)
def test_briefing_hierarchy_scales_without_losing_the_card(width, height):
    model, layout = build(width, height)
    sizes = layout['sizes']
    assert sizes['eyebrow'] < sizes['body'] < sizes['title']
    assert sizes['footer'] < sizes['body']
    card = card_rect(model)
    assert layout['body_width'] <= card.width
    assert layout['capacity'] >= 4, 'a real briefing needs at least four readable rows'
    header = texts(model)[0]
    assert header['size'] < sizes['title']
    title = [op for op in texts(model) if op['text'] == layout['title_lines'][0]]
    assert title and title[0]['size'] == sizes['title']


def test_native_path_never_rasterizes_text_or_geometry(monkeypatch):
    import ast
    from pathlib import Path

    from render import mission_briefing

    original_face = mission_briefing._face

    class NoRasterFace:
        def __init__(self, face):
            self._face = face

        def render(self, *args, **kwargs):
            pytest.fail('native briefing called font.render')

        def __getattr__(self, name):
            return getattr(self._face, name)

    monkeypatch.setattr(mission_briefing, '_face',
                        lambda pixels: NoRasterFace(original_face(pixels)))

    def forbidden(*args, **kwargs):
        pytest.fail('native briefing rasterized geometry or a bitmap')

    for name in ('rect', 'line', 'circle', 'ellipse', 'polygon', 'arc'):
        monkeypatch.setattr(pygame.draw, name, forbidden)
    monkeypatch.setattr(pygame.image, 'tobytes', forbidden)
    monkeypatch.setattr(pygame.transform, 'scale', forbidden)
    monkeypatch.setattr(pygame.transform, 'smoothscale', forbidden)

    model = movie().native_model(1280, 800)
    vector_hud.encode(model)
    assert any(op['kind'] == 'text' for op in model['ops'])
    assert any(op['kind'] == 'polygon' for op in model['ops']), 'objective markers are missing'

    # Surface.blit/fill cannot be monkeypatched (immutable C type), so the call sites
    # themselves are checked: the native path may measure and emit, never paint.
    root = Path(__file__).resolve().parents[1]
    for path, scope in ((root / 'render' / 'mission_briefing.py', None),
                        (root / 'render' / 'cinematics.py', 'native_model')):
        tree = ast.parse(path.read_text())
        nodes = ast.walk(tree)
        if scope is not None:
            method = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                          for node in node.body
                          if isinstance(node, ast.FunctionDef) and node.name == scope)
            nodes = ast.walk(method)
        for node in nodes:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {'blit', 'fill', 'render', 'draw', 'convert', 'copy'}, \
                    f'{path.name} rasterizes through .{node.func.attr}()'


def test_long_unbroken_content_pages_without_dropping_a_character():
    long_mission = {
        'id': 'long',
        'name': 'LongTitle' * 60,
        'briefing': 'LongUnbrokenToken' * 80 + '\nsecond paragraph ' + 'Word' * 50,
        'objectives': [{'text': 'Secure ' + 'LongObjectiveToken' * 30},
                       {'description': 'Hold' * 200}],
    }
    model, layout = build(1280, 800, mission=long_mission)
    assert layout['pages'] > 2, 'unbroken text was clipped instead of paged'
    assert len(layout['title_lines']) <= 2
    assert layout['title_lines'][-1].endswith('…'), 'an oversized title must be visibly truncated'
    assert all(len(line) > 0 for line in layout['title_lines'])

    face = pygame.font.Font(mission_briefing.FONT_PATH, layout['sizes']['body'])
    seen, checked = [], 0
    for page in range(layout['pages']):
        model, current = build(1280, 800, mission=long_mission, elapsed=page * 5.0)
        assert current['page'] == page and current['pages'] == layout['pages']
        page_lines = body_texts(model, current)
        seen.extend(page_lines)
        for line in page_lines:
            assert '…' not in line, 'objective text must page, never truncate'
            assert face.size(line)[0] <= current['body_width'], 'wrapped line overflows the card'
        footer = texts(model)[-2:]
        assert footer[0]['text'] == SKIP_LABEL
        assert footer[1]['text'] == f'{page + 1}/{layout["pages"]}'
        checked += len(page_lines)
    assert checked >= layout['pages'] * 4
    expected = long_mission['briefing'] + '\n' + '\n'.join(
        objective.get('text', objective.get('description', ''))
        for objective in long_mission['objectives'])
    assert ''.join(''.join(seen).split()) == ''.join(expected.split()), 'paged text lost content'


def test_objectives_are_structured_and_caption_and_compose_stay_compatible():
    cinematic = movie()
    assert [entry['text'] for entry in cinematic.objectives] == [
        'Build a command station.', 'Escort the supply convoy to the relay.']
    assert cinematic.caption == (MISSION['briefing'] + '\n' + MISSION['objectives'][0]['text']
                                 + '\n' + MISSION['objectives'][1]['description'])
    surface = cinematic.compose(1280, 800)  # legacy raster control must stay intact
    assert surface.get_size() == (1280, 800)
    assert cinematic.caption_rects
    assert all(surface.get_rect().contains(rect) for rect in cinematic.caption_rects)
    cinematic.native_model(1280, 800)  # native path never touches the raster state
    assert cinematic.caption == (MISSION['briefing'] + '\n' + MISSION['objectives'][0]['text']
                                 + '\n' + MISSION['objectives'][1]['description'])


def test_pagination_follows_elapsed_and_extends_the_presentation_duration():
    long_mission = dict(MISSION, briefing='line ' * 400)
    cinematic = movie(long_mission)
    assert cinematic.duration == 10.
    model, layout = build(1280, 800, mission=long_mission)
    assert layout['pages'] > 1
    cinematic.elapsed = 0.
    cinematic.native_model(1280, 800)
    assert cinematic.native_pages == layout['pages']
    assert cinematic.native_page == 0
    assert cinematic.duration == max(10., layout['pages'] * 5.)
    cinematic.elapsed = 5.0
    model = cinematic.native_model(1280, 800)
    assert cinematic.native_page == 1
    assert texts(model)[-1]['text'] == f'2/{layout["pages"]}'
    cinematic.elapsed = 10 ** 6
    model = cinematic.native_model(1280, 800)
    assert cinematic.native_page == layout['pages'] - 1
    assert texts(model)[-1]['text'] == f'{layout["pages"]}/{layout["pages"]}'


@pytest.mark.parametrize('outcome,message', OUTCOMES)
def test_outcome_briefing_keeps_the_result_copy_and_camera_contract(outcome, message):
    camera = Camera(1280, 800)
    camera.follow_id = 7
    original = (list(camera.target), camera.distance, camera.yaw, camera.pitch, camera.follow_id)
    cinematic = CampaignCinematic(copy.deepcopy(MISSION), camera, outcome=outcome)
    model, layout = build(1280, 800, outcome=outcome)
    labels = [op['text'] for op in texts(model)]
    assert layout['eyebrow'] == outcome
    assert outcome in labels and message in labels
    assert MISSION['briefing'] not in labels
    assert cinematic.duration == 6.
    cinematic.native_model(1280, 800)
    assert cinematic.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert cinematic.finished
    assert original == (camera.target, camera.distance, camera.yaw, camera.pitch, camera.follow_id)


def test_chrome_uses_registry_labels_and_introduces_no_new_visible_string():
    from render import i18n
    previous = i18n.language()
    try:
        i18n.set_language('de')
        model = movie().native_model(1280, 800)
        labels = [op['text'] for op in texts(model)]
        assert 'KAMPAGNE / EINSATZ' in labels
        assert 'CAMPAIGN / DEPLOYMENT' not in labels
        assert SKIP_LABEL in labels, 'skip control copy must match the legacy label'
    finally:
        i18n.set_language(previous)

    model, layout = build(1280, 800)
    allowed = {layout['eyebrow'], SKIP_LABEL, layout['title_lines'][0], '1/1'}
    allowed.update(line['text'] for line in layout['lines'] if line['kind'] != 'space')
    allowed.update(layout['title_lines'])
    for op in texts(model):
        assert op['text'] in allowed, f'invented visible string: {op["text"]!r}'


def test_native_model_is_deterministic_and_leaves_state_alone():
    mission = copy.deepcopy(MISSION)
    camera = Camera(1280, 800)
    cinematic = CampaignCinematic(mission, camera, reduced_motion=True)
    snapshot = copy.deepcopy(mission)
    view = (list(camera.target), camera.distance, camera.yaw, camera.pitch, camera.follow_id)
    first = cinematic.native_model(1280, 800)
    second = cinematic.native_model(1280, 800)
    assert first == second, 'two consecutive frames of the same page must be identical'
    assert mission == snapshot
    assert view == (camera.target, camera.distance, camera.yaw, camera.pitch, camera.follow_id)
    # A caller that mutates the returned snapshot cannot poison the next frame.
    first['ops'].clear()
    assert cinematic.native_model(1280, 800)['ops']


def test_control_characters_are_sanitized_so_the_snapshot_always_encodes():
    mission = dict(MISSION, briefing='Tab\there\x00and\u2028there lonesurrogate\ud800',
                   objectives=[{'text': 'Bell\x07'}])
    model, _layout = build(1280, 800, mission=mission)
    vector_hud.encode(model)
    labels = [op['text'] for op in texts(model)]
    assert not any(any(ord(char) < 32 or 0xd800 <= ord(char) < 0xe000 for char in label)
                   for label in labels)


def test_empty_mission_still_publishes_a_small_valid_card():
    model, layout = build(1280, 800, mission={'name': '', 'briefing': '', 'objectives': []})
    vector_hud.encode(model)
    assert layout['pages'] == 1 and layout['page'] == 0
    assert layout['title_lines'] == ['Mission']
    assert not layout['page_lines']
    card = card_rect(model)
    assert card.height < 400, 'an empty briefing must not keep the body height of a full page'
    assert all(card.contains(pygame.Rect(op['bounds'])) for op in texts(model))
