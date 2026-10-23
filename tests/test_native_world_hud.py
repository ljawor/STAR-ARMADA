"""World-anchored HUD text belongs to the native vector layer, not the pygame bitmap.

The placement banner and ghost, the construction ring with its percentage and the floating
sim messages were the last HUD elements rasterized with the pygame Menlo bitmap font while
the panels beside them were already drawn by C++. These tests hold that boundary: with the
native side HUD live nothing here may call ``font.render`` or ``pygame.draw``, and the text,
line weights and arc must come out as vector ops.
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
import pytest

from game.core.manager import GameManager
from game.data.store import DataStore
from render.hud import HUD

WIDTH, HEIGHT = 1280, 800
SITE_SCREEN = (640, 400)


def match():
    return GameManager.start_skirmish(DataStore.get().maps['skirmish01'])


class _Camera:
    """Flat projection around the screen centre; the ring geometry stays predictable."""

    width, height = WIDTH, HEIGHT

    def world_to_screen(self, x, y, z):
        return (SITE_SCREEN[0] + x * 0.5, SITE_SCREEN[1] + z * 0.5)

    def basis(self):
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class NoRasterFont:
    """Keep real measurements; only rasterization is forbidden."""

    def __init__(self, font):
        self.font = font

    def render(self, *args, **kwargs):
        pytest.fail('native world HUD called font.render')

    def __getattr__(self, name):
        return getattr(self.font, name)


@pytest.fixture
def view():
    gm = match()
    hud = HUD(WIDTH, HEIGHT, gm.state)
    hud.native_panels = True
    hud._vector_capture = None
    hud.local_player = 0
    hud.set_camera_ref(_Camera())
    yield hud
    hud.close()


def forbid_raster(view, monkeypatch):
    for attr in ('font', 'font_small', 'font_big', 'font_title'):
        setattr(view, attr, NoRasterFont(getattr(view, attr)))

    def forbidden(*args, **kwargs):
        pytest.fail('native world HUD rasterized geometry/bitmap')

    for name in ('rect', 'line', 'circle', 'ellipse', 'polygon'):
        monkeypatch.setattr(pygame.draw, name, forbidden)


def ops(view):
    return view.native_vector_model()['ops']


def queue_station(view, kind='trade_station', fraction=1 / 3):
    builder = next(e for e in view.state.entities.values()
                   if e.owner == 0 and e.is_construction)
    builder.build_queue = [{'kind': 'station', 'item': kind,
                            'pos': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                            'total': 90.0, 'time_left': 90.0 * (1.0 - fraction)}]
    return builder


def test_placement_banner_and_ghost_are_vector_text_and_hairlines(view, monkeypatch):
    forbid_raster(view, monkeypatch)
    view.placement = {'station_kind': 'trade_station',
                      'ghost': {'sx': 700, 'sy': 400, 'radius': 120, 'valid': True}}
    view._placement_banner()
    model = view.native_vector_model()
    assert model['active'] is True
    texts = [op['text'] for op in model['ops'] if op['kind'] == 'text']
    assert any(t.startswith('PLACE TRADE STATION') for t in texts), texts
    assert '✓ place trade station' in texts
    circles = [op for op in model['ops'] if op['kind'] == 'circle']
    assert [op['stroke'] for op in circles] == [1, 0], 'ghost ring must be a hairline, disc a fill'
    lines = [op for op in model['ops'] if op['kind'] == 'line']
    assert len(lines) == 2 and all(op['stroke'] == 1 for op in lines)
    assert all(op['clip'] == [0, 0, WIDTH, HEIGHT] for op in model['ops'])


def test_invalid_ghost_keeps_its_reason_in_the_native_layer(view, monkeypatch):
    forbid_raster(view, monkeypatch)
    view.placement = {'station_kind': 'trade_station',
                      'ghost': {'sx': 700, 'sy': 400, 'radius': 120, 'valid': False,
                                'reason': 'too close to a planet'}}
    view._placement_banner()
    texts = [op['text'] for op in view.native_vector_model()['ops'] if op['kind'] == 'text']
    assert any('too close to a planet' in t for t in texts), texts
    assert not any(t.startswith('✓') for t in texts)


def test_construction_ring_is_a_filled_native_arc_with_a_native_percentage(view, monkeypatch):
    forbid_raster(view, monkeypatch)
    queue_station(view, fraction=2 / 3)
    view._construction_progress()
    model = view.native_vector_model()
    assert any(op['kind'] == 'text' and op['text'] == '67%' for op in model['ops']), \
        'the percentage must be drawn by the same layer as the ring'
    arcs = [op for op in model['ops'] if op['kind'] == 'polygon']
    assert len(arcs) == 1, 'the completed sweep is one annulus polygon'
    arc = arcs[0]
    assert arc['color'] == [110, 200, 120, 240]
    assert 3 < len(arc['points']) <= 256
    ring = [op for op in model['ops'] if op['kind'] == 'circle']
    assert [op['stroke'] for op in ring] == [1], 'the unfilled ring must be a hairline'


def test_floating_station_complete_message_is_vector_text_on_its_plate(view, monkeypatch):
    forbid_raster(view, monkeypatch)
    view.floating_texts = [(SITE_SCREEN[0], 300, 'Station complete', (110, 200, 120), 1.0)]
    view._draw_floating_texts()
    model = view.native_vector_model()
    texts = [op for op in model['ops'] if op['kind'] == 'text']
    assert [op['text'] for op in texts] == ['Station complete']
    plate = [op for op in model['ops'] if op['kind'] == 'rect']
    assert len(plate) == 1 and plate[0]['color'] == [10, 12, 18, 200]
    assert plate[0]['rect'][2] > texts[0]['bounds'][2], 'the plate must stay behind the text'


def test_arc_band_closes_the_full_circle_within_the_point_budget():
    points = HUD._arc_band((100, 100), 90, 1.0)
    assert len(points) <= 256
    xs = [p[0] for p in points]
    assert max(xs) == pytest.approx(190, abs=0.6) and min(xs) == pytest.approx(10, abs=0.6)


def test_legacy_overlay_still_rasterizes_when_the_native_layer_is_off():
    gm = match()
    hud = HUD(WIDTH, HEIGHT, gm.state)
    try:
        hud.local_player = 0
        hud.set_camera_ref(_Camera())
        queue_station(hud, fraction=0.5)
        hud.placement = {'station_kind': 'trade_station',
                         'ghost': {'sx': 700, 'sy': 400, 'radius': 120, 'valid': True}}
        hud.floating_texts = [(SITE_SCREEN[0], 300, 'Station complete', (110, 200, 120), 1.0)]
        hud._placement_banner()
        hud._construction_progress()
        hud._draw_floating_texts()
        raw = pygame.image.tostring(hud.overlay, 'RGBA')
        assert any(raw[3::4]), 'the fallback must still paint the labels'
    finally:
        hud.close()
