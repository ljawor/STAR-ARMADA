"""Ordinary-session activation and lifecycle of the native side HUD."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def match():
    from game.core.manager import GameManager
    from game.data.store import DataStore
    return GameManager.start_skirmish(DataStore.get().maps['skirmish01'])


def test_normal_session_publishes_complete_vector_hud_and_restores_mode(tmp_path):
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring
    gm = match()
    hud = HUD(1280, 800, gm.state)
    session = LiveSession(gm.state, gm.ds, directory=tmp_path, hud=hud)
    try:
        assert 'vector_hud' in session.paths, 'ordinary session has no native side HUD stream'
        assert hud.native_panels is True
        selected = {e.id for e in gm.state.entities.values() if e.owner == 0 and e.is_station}
        session.publish(gm.state, selection=selected, visible_ids=set())
        with ring.Ring.open(session.paths['vector_hud']) as reader:
            model = json.loads(reader.latest()[1])
            assert model['version'] == 1 and model['active'] is True
            assert model['logical_size'] == [1280, 800]
            assert model['ops'] and any(op['kind'] == 'fog' for op in model['ops'])
            assert model['fog']['cells'] ** 2 == len(model['fog']['states'])
            assert set(model['fog']['states']) <= set('012')
            session.publish(gm.state, selection=set(), visible_ids=set())
            # A late reader receives a complete latest snapshot, not dependent patches.
            changed = json.loads(reader.latest()[1])
            assert changed['active'] and changed['ops'] and changed['fog']
        assert session.counts['vector_hud_bytes'] > 0
    finally:
        session.close()
        hud.close()
    assert hud.native_panels is False


@pytest.mark.parametrize('previous', [False, True])
def test_vector_ring_constructor_failure_does_not_activate_shared_hud(tmp_path, previous):
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring
    gm = match()
    hud = HUD(1280, 800, gm.state)
    hud.native_panels = previous
    create = ring.Ring.create
    opened = []
    error = OSError('injected vector ring failure')
    def failing(path, *a, **kw):
        if Path(path).name == 'hud-vector.ring':
            raise error
        handle = create(path, *a, **kw)
        opened.append(handle)
        return handle
    try:
        with patch.object(ring.Ring, 'create', side_effect=failing), pytest.raises(OSError) as raised:
            LiveSession(gm.state, gm.ds, directory=tmp_path, hud=hud)
        assert raised.value is error
        assert hud.native_panels is previous
        assert opened
        for handle in opened:
            assert handle._mapping.closed
    finally:
        hud.close()


def test_ordinary_launcher_forwards_vector_stream():
    import os
    from render_bridge import cpp_window
    paths = {name: '/unused/' + name for name in ('frame', 'tables', 'overlay', 'emit',
             'markers', 'fog', 'planets', 'input', 'camera', 'hardware', 'top_hud', 'vector_hud')}
    with patch.object(cpp_window, 'find_binary', return_value='/unused/viewer'), \
            patch('os.path.isfile', return_value=True), patch('shutil.which', return_value=None), \
            patch('subprocess.Popen') as launch, patch('atexit.register'), \
            patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '1'}):
        cpp_window.spawn(paths, root='/unused', snapshot='/unused/catalogue.snap',
                         size=(2560, 1440), log=lambda text: None)
    argv = launch.call_args.args[0]
    assert '--vector-hud-ring' in argv
    assert argv[argv.index('--vector-hud-ring') + 1] == paths['vector_hud']


@pytest.mark.parametrize('previous_top', [False, True])
@pytest.mark.parametrize('previous_panels', [False, True])
def test_closed_session_cannot_restore_replacement_shared_hud_modes(
        tmp_path, monkeypatch, previous_top, previous_panels):
    from render.hud import HUD
    from render_bridge.live import LiveSession
    from render_bridge import ring
    gm = match()
    hud = HUD(1280, 800, gm.state)
    hud.native_top_bar = previous_top
    hud.native_panels = previous_panels
    real_close, real_hud_close = ring.Ring.close, hud.close
    closed, hud_closes = [], []

    def close(handle):
        closed.append(handle)
        real_close(handle)

    monkeypatch.setattr(ring.Ring, 'close', close)
    monkeypatch.setattr(hud, 'close', lambda: hud_closes.append(True))
    first = replacement = None
    try:
        first = LiveSession(gm.state, gm.ds, directory=tmp_path / 'first', hud=hud)
        assert (hud.native_top_bar, hud.native_panels) == (True, True)
        first.close()
        first.close()
        assert (hud.native_top_bar, hud.native_panels) == (previous_top, previous_panels)
        assert all(handle._mapping.closed for handle in first._rings)

        replacement = LiveSession(
            gm.state, gm.ds, directory=tmp_path / 'replacement', hud=hud)
        for _ in range(3):
            first.close()
            assert (hud.native_top_bar, hud.native_panels) == (True, True), \
                'stale close restored modes owned by the replacement session'
            assert all(not handle._mapping.closed for handle in replacement._rings)
        replacement.close()
        replacement.close()
        assert (hud.native_top_bar, hud.native_panels) == (previous_top, previous_panels)
        assert all(handle._mapping.closed for handle in replacement._rings)
        assert closed == list(reversed(first._rings)) + list(reversed(replacement._rings))
        assert not hud_closes, 'session closed the controller-owned HUD'
    finally:
        if replacement is not None:
            replacement.close()
        if first is not None:
            first.close()
        real_hud_close()


@pytest.mark.parametrize('height', [8, 12, 14])
def test_native_bar_label_ink_box_is_inside_its_bar(monkeypatch, height):
    import pygame
    from render.hud import HUD, _p
    from render_bridge.vector_hud import Capture, Sink
    gm = match()
    hud = HUD(1280, 800, gm.state)
    capture = Capture(1280, 800)
    sink = Sink(capture, (0, 0, 1280, 800), source_x=10, target_x=10, scale=.75)
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(_p, 'native_sink', sink)
            hud._bar(20, 120, 100, height, 1, (86, 140, 220), 'FR')
        bar = pygame.Rect(sink.rect((20, 120, 100, height)))
        label = next(op for op in capture.ops if op['kind'] == 'text')
        assert bar.contains(pygame.Rect(label['bounds'])), 'native ink-top label escapes its bar'
        assert label['pos'][1] >= bar.top
    finally:
        hud.close()
