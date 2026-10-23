"""Native upper HUD: Python publishes display data, never a high-resolution bitmap."""
import importlib
import importlib.util
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('previous_native', [False, True])
@pytest.mark.parametrize('failure_name, expected_open', [('top-hud.ring', 5), ('camera.ring', 8)])
@pytest.mark.parametrize('cleanup_raises', [False, True])
def test_live_session_constructor_failure_rolls_back(
        tmp_path, monkeypatch, previous_native, failure_name, expected_open, cleanup_raises):
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring

    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    hud = HUD(1280, 800, gm.state)
    hud.native_top_bar = previous_native
    real_create, real_close, real_hud_close = ring.Ring.create, ring.Ring.close, hud.close
    opened, close_calls, hud_closes = [], [], []
    failure = OSError('injected constructor failure: ' + failure_name)

    def create(path, **kwargs):
        if path.name == failure_name:
            raise failure
        handle = real_create(path, **kwargs)
        opened.append(handle)
        return handle

    def close(handle):
        close_calls.append(handle)
        real_close(handle)
        if cleanup_raises and handle is opened[-1]:
            raise RuntimeError('injected cleanup failure')

    monkeypatch.setattr(ring.Ring, 'create', create)
    monkeypatch.setattr(ring.Ring, 'close', close)
    monkeypatch.setattr(hud, 'close', lambda: hud_closes.append(True))
    try:
        with pytest.raises(OSError) as caught:
            LiveSession(gm.state, gm.ds, directory=tmp_path, hud=hud)
        assert caught.value is failure, 'cleanup replaced the constructor exception'
        assert len(opened) == expected_open, 'fault injection did not reach the intended seam'
        assert not hud_closes, 'rollback closed the controller-owned HUD'
        # Check both leaked mode and leaked real mappings in the same failure report.
        assert (hud.native_top_bar, [h.path.name for h in opened if not h._closed]) == (
            previous_native, [])
        assert len(close_calls) == len(opened)
        assert all(handle._mapping.closed for handle in opened)
    finally:
        for handle in opened:
            real_close(handle)
        real_hud_close()


@pytest.mark.parametrize('previous_native', [False, True])
def test_live_session_success_restores_shared_hud_on_repeated_close(
        tmp_path, monkeypatch, previous_native):
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring

    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    hud = HUD(1280, 800, gm.state)
    hud.native_top_bar = previous_native
    real_create, real_hud_close = ring.Ring.create, hud.close
    opened, hud_closes = [], []

    def create(path, **kwargs):
        handle = real_create(path, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(ring.Ring, 'create', create)
    monkeypatch.setattr(hud, 'close', lambda: hud_closes.append(True))
    session = None
    try:
        session = LiveSession(gm.state, gm.ds, directory=tmp_path, hud=hud)
        assert hud.native_top_bar is True
        session.close()
        session.close()
        assert hud.native_top_bar is previous_native
        assert not hud_closes
        assert len(opened) == 9
        assert all(handle._closed and handle._mapping.closed for handle in opened)
    finally:
        if session is not None:
            session.close()
        for handle in opened:
            ring.Ring.close(handle)
        real_hud_close()


def state():
    p = SimpleNamespace(credits=12345.0, materials=2345.0, energy=18.0, crew=84.0,
                        command_capacity=120, income_frame={'credits': 2.5, 'energy': 0.0},
                        command_used=lambda entities: 27)
    return SimpleNamespace(players={0: p}, entities={}, time=125.0)


def test_top_bar_is_a_bounded_display_model_not_pixels():
    assert importlib.util.find_spec('render_bridge.top_hud') is not None, \
        'native top-bar model producer is missing'
    wire = importlib.import_module('render_bridge.top_hud')
    model = wire.build(state(), 0, paused=True, fps=59.8)
    assert [cell['label'] for cell in model['cells']] == ['CR', 'MT', 'EN', 'CRW', 'CMD']
    assert [cell['value'] for cell in model['cells']] == ['12,345', '2,345', '18', '84', '27/120']
    assert model['cells'][0]['rate'] == '2.5/s'
    assert model['cells'][2]['rate'] == '0/s'
    assert model['cells'][2]['rate_color'] == [232, 92, 76]
    assert model['clock'] == '02:05'
    assert model['fps'] == '60 FPS'
    assert model['paused']
    payload = wire.encode(model)
    assert isinstance(payload, bytes)
    assert len(payload) < 2048
    assert b'pixels' not in payload and b'RGBA' not in payload


def test_live_session_publishes_native_data_and_leaves_other_panels_identical(tmp_path):
    import json
    import pygame
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    hud = HUD(1280, 800, gm.state)
    hud.compose(set(), None, 0, False)
    before = pygame.image.tobytes(hud.overlay, 'RGBA', False)
    session = LiveSession(gm.state, gm.ds, directory=tmp_path, hud=hud)
    try:
        assert 'top_hud' in session.paths, 'ordinary live session has no native top-bar stream'
        session.publish(gm.state, visible_ids=set())
        with ring.Ring.open(session.paths['top_hud']) as reader:
            model = json.loads(reader.latest()[1])
            assert model['active'] is True
            assert model['cells'][0]['value'] == f'{gm.state.players[0].credits:,.0f}'
            gm.state.players[0].credits = 765432.0
            session.publish(gm.state, visible_ids=set(), paused=True, fps=52.1)
            changed = json.loads(reader.latest()[1])
            assert changed['cells'][0]['value'] == '765,432'
            assert changed['paused'] and changed['fps'] == '52 FPS'
        # Render with the same state as the baseline before comparing all unmigrated pixels.
        hud.compose(set(), None, 0, False)
        after = pygame.image.tobytes(hud.overlay, 'RGBA', False)
        assert after[:1280 * 34 * 4] == bytes(1280 * 34 * 4), 'Python still paints the top bar'
        assert after[1280 * 34 * 4:] == before[1280 * 34 * 4:], 'unmigrated HUD pixels changed'
        assert pygame.Rect(0, 0, 1280, 34) in hud.blocked_rects, 'top strip leaks clicks into world'
    finally:
        session.close()
        hud.close()
    assert hud.native_top_bar is False, 'session leaked presentation mode into another match'


def test_game_launcher_passes_the_native_top_stream_to_the_real_renderer():
    import os
    from unittest.mock import patch
    from render_bridge import cpp_window
    paths = {name: '/unused/' + name for name in ('frame', 'tables', 'overlay', 'emit',
             'markers', 'fog', 'planets', 'input', 'camera', 'hardware', 'top_hud')}
    with patch.object(cpp_window, 'find_binary', return_value='/unused/viewer'), \
            patch('os.path.isfile', return_value=True), patch('shutil.which', return_value=None), \
            patch('subprocess.Popen') as launch, patch('atexit.register'), \
            patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '1'}):
        cpp_window.spawn(paths, root='/unused', snapshot='/unused/catalogue.snap',
                         size=(2560, 1440), log=lambda text: None)
    argv = launch.call_args.args[0]
    assert '--top-hud-ring' in argv, 'normal launcher never enables the native top bar'
    assert argv[argv.index('--top-hud-ring') + 1] == paths['top_hud']


def test_native_model_preserves_languages_warnings_and_simulation():
    import json
    from render import i18n
    from render_bridge import top_hud
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from game.net.replay import state_checksum
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    previous = i18n.language()
    baseline = state_checksum(gm.state)
    try:
        for language in ('en', 'de', 'pl', 'ru'):
            i18n.set_language(language)
            model = top_hud.build(gm.state, 0, paused=True, fps=61)
            assert model['paused'] == i18n.t('PAUSED')
            assert json.loads(top_hud.encode(model)) == model
            assert state_checksum(gm.state) == baseline
        assert model['paused'] == 'ПАУЗА'
        assert 'ПАУЗА'.encode() in top_hud.encode(model), 'Cyrillic was replaced by a lossy codec'
    finally:
        i18n.set_language(previous)
    st = state()
    st.players[0].command_capacity = 27
    st.players[0].income_frame['materials'] = -2.5
    model = top_hud.build(st, 0)
    assert model['cells'][4]['color'] == [232, 168, 76]
    assert model['cells'][1]['rate'] == '-2.5/s'
    assert model['paused'] == '' and model['fps'] == ''
    assert top_hud.build(st, 999)['active'] is False


def test_native_presentation_retains_the_existing_game_over_banner():
    import pygame
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render.hud import HUD
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    gm.state.game_over, gm.state.winner = True, 0
    hud = HUD(1280, 800, gm.state)
    try:
        hud.native_top_bar = False
        hud.compose(set(), None, 0, False)
        old = hud.overlay.subsurface((300, 300, 680, 160)).copy()
        hud.native_top_bar = True
        hud.compose(set(), None, 0, False, fps=60)
        native = hud.overlay.subsurface((300, 300, 680, 160))
        assert pygame.image.tobytes(old, 'RGBA') == pygame.image.tobytes(native, 'RGBA')
        assert max(pygame.surfarray.array_alpha(native).flatten()) > 0
    finally:
        hud.close()
