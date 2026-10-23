"""CPU-only notification capture contracts; no window, GL or GPU required."""
import pygame
import pytest

from game.core.manager import GameManager  # application import order
from game.core.events import GameEvent
from render.hud import HUD, BAD, GOOD, PANEL_BG, PANEL_EDGE, TXT_DIM, WARN
from render.overlay_upload import painter
from render_bridge.vector_hud import Capture, Sink, encode


@pytest.fixture
def view():
    from helpers import make_game
    hud = HUD(1280, 800, make_game(ai=False).state)
    hud.native_panels = True
    yield hud
    painter.native_sink = None
    painter.recorder = None


class MeasuredFont:
    """Production measurements, but no notification may call font.render."""
    def __init__(self, font):
        self.font = font

    def render(self, *args, **kwargs):
        pytest.fail('native notification rasterized text')

    def __getattr__(self, name):
        return getattr(self.font, name)


def forbid_raster(view, monkeypatch):
    for name in ('font', 'font_big', 'font_small'):
        setattr(view, name, MeasuredFont(getattr(view, name)))
    def forbidden(*args, **kwargs):
        pytest.fail('native notification rasterized geometry or bitmap')
    for name in ('rect', 'line', 'circle', 'polygon', 'ellipse'):
        monkeypatch.setattr(pygame.draw, name, forbidden)
    monkeypatch.setattr(painter, 'blit', forbidden)
    monkeypatch.setattr(pygame.transform, 'scale', forbidden)


@pytest.mark.parametrize('count', [1, 2, 9, 15])
def test_incoming_same_width_and_left_edge_as_approved_panel(view, monkeypatch, count):
    view.state.events.log[:] = [GameEvent('research_complete', {'owner': 0, 'tech': f'Tech {i}'})
                                for i in range(count)]
    view._left_panel(set(), 0)
    left = next(op['rect'] for op in view.native_vector_model()['ops'] if op['kind'] == 'rect')
    view._vector_capture = None
    view.blocked_rects.clear()
    forbid_raster(view, monkeypatch)
    view._event_log(0)
    ops = view.native_vector_model()['ops']
    panel = next(op['rect'] for op in ops if op['kind'] == 'rect')
    rows = min(count, 9)
    top = round(786 - .75 * (34 + 18 * rows))
    assert panel == [left[0], top, left[2], 786 - top]
    assert panel[0] == 10 and panel[2] == 240
    assert view.blocked_rects == [pygame.Rect(panel)]
    assert all(op['clip'] == panel for op in ops)
    lines = [op for op in ops if op['kind'] == 'text']
    assert [op['text'] for op in lines] == ['INCOMING'] + [f'✦ research: Tech {i}' for i in range(max(0, count - 9), count)]
    assert all(pygame.Rect(panel).contains(pygame.Rect(op['bounds'])) for op in lines)
    assert all(op['fit'] == 'shrink' for op in lines)
    assert view.overlay.get_bounding_rect().width == 0
    assert painter.native_sink is None
    encode(view.native_vector_model())


@pytest.mark.parametrize('message', ['Ready', 'Łódź — Antrieb bereit', 'Нет энергии',
                                   'threshold-below', 'threshold-above',
                                   'No space ' * 160, 'W' * 4096],
                         ids=['short', 'pl-de', 'ru', 'threshold-below', 'threshold-above',
                              'long-review-fixture', 'max-wire-text'])
def test_flash_measured_card_and_centered_text_bounds_without_raster(view, monkeypatch, message):
    if message.startswith('threshold-'):
        count = 1
        while view.font_big.size('W' * count)[0] <= view.width - 48:
            count += 1
        message = 'W' * (count - (message == 'threshold-below'))
    # Execute the actual legacy drawing branch, not a copy of native layout.
    view.native_panels = False
    view._flash_message(message, 1.25)
    bg, = view.blocked_rects
    r = bg.inflate(-24, -12)
    assert bg.width == view.font_big.render(message, True, WARN).get_width() + 24
    center = (view.width // 2, view.height - 60)

    def transformed(rect):
        left = round(center[0] + .75 * (rect.left - center[0]))
        right = round(center[0] + .75 * (rect.right - center[0]))
        top = round(center[1] + .75 * (rect.top - center[1]))
        bottom = round(center[1] + .75 * (rect.bottom - center[1]))
        return [left, top, right - left, bottom - top]

    view.native_panels = True
    view.blocked_rects.clear()
    view.overlay.fill((0, 0, 0, 0))
    forbid_raster(view, monkeypatch)
    view._flash_message(message, 1.25)
    model = view.native_vector_model()
    assert len(model['ops']) == 3
    fill, edge, text = model['ops']
    assert fill['rect'] == edge['rect'] == transformed(bg)
    assert fill['color'] == list(PANEL_BG) and edge['color'] == list(PANEL_EDGE)
    assert fill['radius'] == edge['radius'] == 4.5
    assert edge['stroke'] == .75
    assert text['text'] == message and text['color'] == [*WARN, 255]
    assert text['size'] == 19 * 1.5 * .75
    assert text['bounds'] == transformed(r) and text['fit'] == 'center'
    assert text['pos'] == transformed(r)[:2]
    assert abs(pygame.Rect(text['bounds']).centerx - center[0]) <= 1
    assert abs(pygame.Rect(text['bounds']).centery - center[1]) <= 1
    assert pygame.Rect(fill['rect']).contains(pygame.Rect(text['bounds']))
    expected_clip = transformed(bg.clip(view.overlay.get_rect()))
    assert all(op['clip'] == expected_clip for op in model['ops'])
    assert abs(fill['rect'][2] - bg.width * .75) <= 1
    if message == 'No space ' * 160:
        assert bg.width == 17304
        assert fill['rect'][2] == 12978
    if bg.width > view.width * 2:
        assert fill['rect'][0] < 0 and fill['rect'][2] > view.width
        assert pygame.Rect(fill['clip']).width < fill['rect'][2]
    assert view.blocked_rects == [pygame.Rect(fill['rect'])]
    assert view.overlay.get_bounding_rect().width == 0
    assert painter.native_sink is None
    encode(model)


@pytest.mark.parametrize('language', ['en', 'pl', 'de', 'ru'])
@pytest.mark.parametrize('player', [0, 1])
def test_incoming_local_owner_order_exact_strings_colours_and_state(view, monkeypatch, language, player):
    import copy
    from render import i18n
    from game.net.replay import state_checksum
    previous = i18n.language()
    i18n.set_language(language)
    events = []
    types = ['unit_destroyed', 'station_built', 'construction_complete',
             'research_complete', 'planet_colonized']
    for i in range(15):
        events.append(GameEvent(types[i % len(types)], dict(owner=player, unit=f'Unit {i}',
            station=f'Station {i}', tech=f'Tech {i}', planet=f'Planet {i}', faction='imperial')))
        events.append(GameEvent('research_complete', dict(owner=1 - player, tech='ENEMY SECRET')))
        events.append(GameEvent('weapon_fired', dict(owner=player, unit='UNSUPPORTED SECRET')))
    events.append(GameEvent('station_built', dict(station='MISSING OWNER SECRET')))
    view.state.events.log[:] = events
    saved = copy.deepcopy(events)
    before = state_checksum(view.state)
    own = [event for event in events if event.type in types and event.data.get('owner') == player][-9:]
    expected = [i18n.t('INCOMING')] + [i18n.t(view._event_text(event, player)) for event in own]
    try:
        forbid_raster(view, monkeypatch)
        view._event_log(player)
        text = [op for op in view.native_vector_model()['ops'] if op['kind'] == 'text']
        assert [op['text'] for op in text] == expected
        assert text[0]['color'] == [*TXT_DIM, 255]
        assert [op['color'] for op in text[1:]] == [
            [*(BAD if event.type == 'unit_destroyed' else GOOD), 255] for event in own]
        assert 'SECRET' not in str(view.native_vector_model())
        assert state_checksum(view.state) == before
        assert view.state.events.log == saved
    finally:
        i18n.set_language(previous)


@pytest.mark.parametrize('size', [(1024, 640), (1280, 800), (1920, 1080)])
def test_compose_replaces_expires_switches_player_and_clears_without_stale_ops(view, size):
    view.width, view.height = size
    view.overlay = pygame.Surface(size, pygame.SRCALPHA)
    view.native_top_bar = True
    view.state.events.log[:] = [GameEvent('research_complete', dict(owner=0, tech='OWN ZERO')),
                                GameEvent('research_complete', dict(owner=1, tech='OWN ONE'))]
    def frame(player=0, msg='First warning', left=1):
        view.compose(set(), None, player, False, msg, left)
        model = view.native_vector_model()
        encode(model)
        return model
    first = frame()
    assert any(op.get('text') == 'First warning' for op in first['ops'])
    assert any(op.get('text') == '✦ research: OWN ZERO' for op in first['ops'])
    assert first == frame(), 'complete snapshots must not append stale operations'
    replaced = frame(1, 'Replacement')
    assert not any('OWN ZERO' in op.get('text', '') or op.get('text') == 'First warning' for op in replaced['ops'])
    assert any(op.get('text') == '✦ research: OWN ONE' for op in replaced['ops'])
    assert any(op.get('text') == 'Replacement' for op in replaced['ops'])
    for msg, left in [('Replacement', 0), ('Replacement', -1), ('', 1)]:
        expired = frame(1, msg, left)
        assert not any(op.get('fit') == 'center' for op in expired['ops'])
    view.state.events.log.clear()
    empty = frame(1, '', 0)
    assert not any(op.get('text') == 'INCOMING' for op in empty['ops'])
    assert all(not (rect.x == 10 and rect.bottom == view.height - 14) for rect in view.blocked_rects)
    assert painter.native_sink is None


def test_notification_migration_leaves_approved_vectors_and_residual_mission_unchanged(view):
    view.native_top_bar = True
    view.state.events.log.clear()
    view.mission_progress = ['[ ] Residual mission stays raster']
    view.compose(set(), None, 0, False)
    approved = view.native_vector_model()
    residual = pygame.image.tobytes(view.overlay, 'RGBA')
    view.state.events.log[:] = [GameEvent('station_built', dict(owner=0, station='Notification'))]
    view.compose(set(), None, 0, False, 'Native flash', 1)
    with_notifications = view.native_vector_model()
    notification_texts = {'INCOMING', '△ Notification online', 'Native flash'}
    assert {op['text'] for op in with_notifications['ops'] if op.get('text') in notification_texts} == notification_texts
    # Event block has 2 rects + heading + row; flash has 2 rects + text.
    assert len(with_notifications['ops']) == len(approved['ops']) + 7
    event_start = next(i for i, op in enumerate(with_notifications['ops']) if op.get('text') == 'INCOMING') - 2
    assert (with_notifications['ops'][:event_start] + with_notifications['ops'][event_start + 4:-3]) == approved['ops']
    assert pygame.image.tobytes(view.overlay, 'RGBA') == residual, 'notifications must not duplicate into raster'
    assert not any('Residual mission' in op.get('text', '') for op in with_notifications['ops'])
    view.native_panels = False
    view.compose(set(), None, 0, False, 'Legacy flash', 1)
    assert view.native_vector_model()['ops'] == []
    assert not view.native_vector_model()['active']
    view.native_panels = True
    view.compose(set(), None, 0, False, '', 0)
    assert not any(op.get('fit') == 'center' for op in view.native_vector_model()['ops'])


def test_legacy_notification_fallback_keeps_original_dimensions_and_raster(view):
    view.native_panels = False
    message = 'Legacy warning'
    r = view.font_big.render(message, True, WARN).get_rect(center=(640, 740))
    view._flash_message(message, 1)
    assert view.blocked_rects == [r.inflate(24, 12)]
    assert view.overlay.get_bounding_rect().width > 0
    view.state.events.log[:] = [GameEvent('station_built', dict(owner=0, station='Legacy'))]
    view._event_log(0)
    assert view.blocked_rects[-1] == pygame.Rect(10, 734, 420, 52)
    assert view.native_vector_model()['ops'] == []
    assert not view.native_vector_model()['active']


@pytest.mark.parametrize('method', ['_event_log', '_flash_message'])
def test_notification_scope_restored_after_exception(view, monkeypatch, method):
    view.state.events.log[:] = [GameEvent('station_built', dict(owner=0, station='Station'))]
    previous = Sink(Capture(view.width, view.height), (0, 0, view.width, view.height))
    monkeypatch.setattr(painter, 'native_sink', previous)
    def broken(*args, **kwargs):
        raise RuntimeError('injected notification geometry failure')
    monkeypatch.setattr(painter, 'rect', broken)
    with pytest.raises(RuntimeError, match='injected notification'):
        getattr(view, method)(*( (0,) if method == '_event_log' else ('Message', 1)))
    assert painter.native_sink is previous


def test_notifications_clip_to_existing_surface_clip(view):
    view.state.events.log[:] = [GameEvent('research_complete', dict(owner=0, tech='Long ' * 300))]
    view.overlay.set_clip((20, 740, 100, 20))
    view._event_log(0)
    assert all(op['clip'] == [18, 752, 74, 14] for op in view.native_vector_model()['ops'])
    assert any(op.get('text') == '✦ research: ' + 'Long ' * 300 for op in view.native_vector_model()['ops'])
    view._vector_capture = None
    view.overlay.set_clip((0, 0, 0, 0))
    view._event_log(0)
    view._flash_message('Not visible', 1)
    assert view.native_vector_model()['ops'] == []


def test_center_fit_is_explicit_and_survives_wire_roundtrip():
    import json
    capture = Capture(1280, 800)
    sink = Sink(capture, (0, 0, 1280, 800))
    surface = pygame.Surface((1280, 800), pygame.SRCALPHA)
    sink.text(surface, 400, 700, 'Centred Łódź', WARN, 28.5, 200, 25, fit='center')
    sink.text(surface, 400, 650, 'Default remains shrink', WARN, 18, 200, 18)
    model = capture.snapshot(True)
    assert [op['fit'] for op in model['ops']] == ['center', 'shrink']
    assert json.loads(encode(model)) == model


def test_sink_optional_vertical_anchor_preserves_defaults():
    capture = Capture(1280, 800)
    old = Sink(capture, (10, 44, 320, 756), source_x=10, target_x=10, scale=.75)
    assert old.point((110, 144)) == [85, 119]
    bottom = Sink(capture, (10, 600, 320, 186), source_x=10, target_x=10,
                  source_y=786, target_y=786, scale=.75)
    assert bottom.point((10, 786)) == [10, 786]
    assert bottom.rect((10, 600, 320, 186)) == [10, 646, 240, 140]
