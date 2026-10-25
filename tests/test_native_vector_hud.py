"""CPU-only native side HUD contract, using production GameState and painters."""
import pygame
import pytest

from game.core.manager import GameManager
from game.data.store import DataStore
from render.hud import HUD


@pytest.fixture
def game():
    from helpers import make_game
    return make_game(ai=False)


@pytest.fixture
def view(game):
    return HUD(1280, 800, game.state)


def test_native_capture_default_and_complete_sides(view, monkeypatch):
    assert view.native_panels is False
    view.native_panels = True
    constructor = next(e for e in view.state.entities.values() if e.owner == 0 and e.is_construction)
    def forbidden(*args, **kwargs):
        pytest.fail('Native scopes rasterized geometry')
    for name in ('rect', 'line', 'circle', 'ellipse', 'polygon'):
        monkeypatch.setattr(pygame.draw, name, forbidden)
    view._left_panel({constructor.id}, 0)
    view._right_panel({constructor.id}, 0)
    view._minimap({constructor.id}, 0)
    model = view.native_vector_model()
    assert set(model) == {'version', 'active', 'logical_size', 'ops', 'fog'}
    assert model['active'] and model['logical_size'] == [1280, 800]
    rects = [op['rect'] for op in model['ops'] if op['kind'] == 'rect']
    assert [10, 44, 240, 21] in rects
    assert [1030, 44, 240, 21] in rects
    assert [1058, 578, 210, 210] in rects
    assert all(op['clip'][2] > 0 and op['clip'][3] > 0 for op in model['ops'])
    assert any(op['kind'] == 'text' and 'ORBITAL' in op['text'] for op in model['ops'])
    assert any(b['kind'] == 'build_station_place' and b['rect'].x >= 1030 for b in view.buttons)
    assert model['fog'] is not None


def test_wrapped_lines_keep_full_words_and_explicit_source_line_width(view):
    view.native_panels = True
    text = 'one two three four five six ' + 'UnbrokenCustomName' * 8
    view._draw_collapsible('left', 'TEST', lambda: view._wrapped_labels(22, 80, text, 70))
    lines = [op for op in view.native_vector_model()['ops'] if op['kind'] == 'text' and op['pos'][1] >= 71]
    assert ' '.join(op['text'] for op in lines) == text
    assert all(op['bounds'][2] == round(10 + .75 * (92 - 10)) - round(10 + .75 * (22 - 10)) for op in lines)


class NoRasterFont:
    """Keep real font measurements; rasterization is forbidden, not simulated."""
    def __init__(self, font):
        self.font = font

    def render(self, *args, **kwargs):
        pytest.fail('Native HUD called font.render')

    def __getattr__(self, name):
        return getattr(self.font, name)


def forbid_raster(view, monkeypatch):
    for attr in ('font', 'font_small', 'font_big', 'font_title'):
        setattr(view, attr, NoRasterFont(getattr(view, attr)))
    def forbidden(*args, **kwargs):
        pytest.fail('Native HUD rasterized geometry/bitmap')
    for name in ('rect', 'line', 'circle', 'ellipse', 'polygon'):
        monkeypatch.setattr(pygame.draw, name, forbidden)
    monkeypatch.setattr(pygame.transform, 'scale', forbidden)
    monkeypatch.setattr(view.fog, 'surface', forbidden)


def reset_capture(view):
    view._vector_capture = None
    view.buttons = []
    view.blocked_rects = []
    view.scroll_rects = []


@pytest.mark.parametrize('language', ['en', 'de', 'pl', 'ru'])
def test_all_control_paths_preserve_source_rows_payloads_and_state(game, view, monkeypatch, language):
    from render import i18n
    from render_bridge.vector_hud import Sink, Capture, encode
    from game.core.vectors import Vec3
    from game.net.replay import state_checksum
    previous = i18n.language()
    i18n.set_language(language)
    # Real factories exercise support, crew, boarding, colony, abilities, production,
    # research, running queues/refits, fleet creation/formations and data-driven values.
    spawned = [game.factory.spawn_ship(sid, 0, Vec3()) for sid in (
        'imperial_constructor', 'imperial_crew_transport', 'imperial_cruiser', 'imperial_colonizer')]
    ability = next(s for s in view.ds.ships.values() if s.abilities)
    spawned.append(game.factory.spawn_ship(ability.id, 0, Vec3()))
    stations = [game.factory.spawn_station(sid, 0, Vec3()) for sid in ('shipyard', 'research_station', 'command_station')]
    yard = stations[0]
    yard.collection_point = Vec3(7345.5, 0, -5234.25)
    yard.upgrade_level = 4
    yard.build_queue = [dict(kind='station_upgrade', item='shipyard', time_left=100),
                        dict(kind='ship', item='imperial_corvette', time_left=100)]
    td = next(t for t in view.ds.techs.values() if t.faction == game.state.players[0].faction)
    game.state.players[0].researching[td.id] = dict(time_left=12, total=60)
    planet = next(e for e in game.state.entities.values() if e.data_id == 'temperate')
    planet.colonized_by = 0
    planet.build_queue = [dict(kind='satellite', item='attack_satellite', slot=0, time_left=13, total=30)]
    spawned[0].name_override = 'Personalized ' + 'UnbrokenTranslatedHullName' * 6
    game.visibility.update()
    before = state_checksum(game.state)
    selections = [set(), {999999}, *({e.id} for e in spawned + stations),
                  {e.id for e in spawned}, {planet.id}]
    cases = [(selection, False, 'surface') for selection in selections]
    cases += [({planet.id}, False, 'orbit'), ({e.id for e in spawned}, True, 'surface')]
    legacy = HUD(1280, 800, game.state)
    expected = []
    try:
        for selection, fleet, page in cases:
            legacy.buttons = []; legacy.blocked_rects = []; legacy.scroll_rects = []
            legacy.fleet_panel, legacy.planet_page = fleet, page
            legacy._left_panel(selection, 0); legacy._right_panel(selection, 0)
            expected.append(([dict(b) for b in legacy.buttons], list(legacy.blocked_rects), list(legacy.scroll_rects)))
        view.native_panels = True
        forbid_raster(view, monkeypatch)
        for (selection, fleet, page), (buttons, blocks, scrolls) in zip(cases, expected):
            reset_capture(view)
            view.fleet_panel, view.planet_page = fleet, page
            view._left_panel(selection, 0); view._right_panel(selection, 0); view._minimap(selection, 0)
            actual = view.native_vector_model()
            encode(actual)
            assert len(view.buttons) == len(buttons), (language, selection)
            for native, source in zip(view.buttons, buttons):
                key = source.get('panel', source.get('payload', {}).get('panel'))
                sx, tx = (10, 10) if key == 'left' else (950, 1030)
                affine = Sink(Capture(1280, 800), (sx, 44, 320, 756), source_x=sx, target_x=tx, scale=.75)
                assert list(native['rect']) == affine.rect(source['rect'])
                assert (native['kind'], native['payload']) == (source['kind'], source['payload'])
            assert len(view.blocked_rects) == len(blocks)
            assert len(view.scroll_rects) == len(scrolls)
            for native, source in zip(view.blocked_rects, blocks):
                sx, tx = (10, 10) if source.x < 640 else (950, 1030)
                affine = Sink(Capture(1280, 800), (sx, 44, 320, 756), source_x=sx, target_x=tx, scale=.75)
                assert list(native) == affine.rect(source)
            for (native, key), (source, source_key) in zip(view.scroll_rects, scrolls):
                sx, tx = (10, 10) if source.x < 640 else (950, 1030)
                affine = Sink(Capture(1280, 800), (sx, 44, 320, 756), source_x=sx, target_x=tx, scale=.75)
                assert key == source_key and list(native) == affine.rect(source)
            if selection == {spawned[0].id}:
                assert any(spawned[0].name_override.upper() == op.get('text') for op in actual['ops'])
            assert list(view.minimap_rect) == [1058, 578, 210, 210]
            assert all(view.overlay.get_at(p).a == 0 for p in ((10, 44), (1030, 44), (1058, 578)))
        assert state_checksum(game.state) == before
    finally:
        i18n.set_language(previous)


def test_zero_clip_measurement_and_viewport_clips_emit_no_empty_ops(view, monkeypatch):
    from render.overlay_upload import painter
    view.native_panels = True
    forbid_raster(view, monkeypatch)
    def content():
        old = view.overlay.get_clip()
        view.overlay.set_clip((0, 0, 0, 0))
        view._label(22, 80, 'MEASUREMENT MUST NOT ESCAPE')
        painter.rect(view.overlay, (1, 2, 3), (10, 72, 320, 100))
        view.overlay.set_clip((20, 100, 100, 20))
        view._bar(22, 100, 296, 16, .5, (110, 200, 120), 'FULL BAR TEXT')
        view.overlay.set_clip(old)
    view._draw_collapsible('left', 'TEST', content)
    ops = view.native_vector_model()['ops']
    assert not any(op.get('text') == 'MEASUREMENT MUST NOT ESCAPE' for op in ops)
    bar_ops = [op for op in ops if op['clip'] != [10, 44, 240, 567]]
    assert len(bar_ops) == 4
    assert all(op['clip'] == [18, 86, 74, 15] for op in bar_ops)
    assert painter.native_sink is None


def test_encode_strict_payload_budgets_and_inactive_clear(view, monkeypatch):
    from render_bridge import vector_hud
    import copy
    import json
    view.native_panels = True
    view._left_panel(set(), 0)
    model = view.native_vector_model()
    assert json.loads(vector_hud.encode(model)) == model
    text = next(op for op in model['ops'] if op['kind'] == 'text')
    for invalid in ('bad\x00text', 'bad\ntext', 'bad\x1ftext', '\ud800', '\x85', '\u2028', '\u202e', '\u2069'):
        candidate = copy.deepcopy(model)
        next(op for op in candidate['ops'] if op['kind'] == 'text')['text'] = invalid
        with pytest.raises((ValueError, UnicodeError)):
            vector_hud.encode(candidate)
    for change in ({'size': float('nan')}, {'size': 257}, {'size': 0}, {'color': [1, 2, 3]},
                   {'bounds': [1, 2, -1, 4]}, {'fit': 'wrap'}, {'extra': 0}, {'text': 'я' * 2049}):
        candidate = copy.deepcopy(model)
        next(op for op in candidate['ops'] if op['kind'] == 'text').update(change)
        with pytest.raises(ValueError):
            vector_hud.encode(candidate)
    candidate = copy.deepcopy(model)
    candidate['ops'] = [text] * 4097
    with pytest.raises(ValueError):
        vector_hud.encode(candidate)
    candidate['ops'] = [{**text, 'text': 'x' * 4096}] * 17
    with pytest.raises(ValueError):
        vector_hud.encode(candidate)
    for fog in ({'cells': 2, 'states': '012'}, {'cells': 2, 'states': '0123'}, {'cells': 2049, 'states': ''}):
        candidate = copy.deepcopy(model); candidate['fog'] = fog
        with pytest.raises(ValueError):
            vector_hud.encode(candidate)
    monkeypatch.setattr(vector_hud, 'MAX_PAYLOAD', 10)
    with pytest.raises(ValueError, match='payload'):
        vector_hud.encode(model)
    view.native_panels = False
    assert view.native_vector_model() == dict(version=1, active=False, logical_size=[1280, 800], ops=[], fog=None)


def test_fog_states_match_authoritative_mask_without_bitmap_capture(game, view):
    from game.core.vectors import Vec3
    # Deliberately asymmetric sources/exploration expose row/column reversal.
    for entity in game.state.entities.values():
        if entity.owner == 0 and not entity.is_planet:
            entity.pos = Vec3(-6700, 0, 3200)
    game.visibility.update()
    game.state.explored_cells[0].update({(11, -7), (12, -8)})
    surface = view.fog.surface(game.state, 0)
    view.native_panels = True
    view._minimap(set(), 0)
    fog = view.native_vector_model()['fog']
    n = fog['cells']
    assert surface.get_size() == (n, n)
    states = set()
    for z in range(n):
        for x in range(n):
            alpha = surface.get_at((x, z)).a
            expected = '2' if alpha == 0 else '1' if alpha == 155 else '0'
            states.add(expected)
            assert fog['states'][z*n + x] == expected
    assert states == set('012')


def test_native_scope_restored_on_exception_and_snapshot_copied(view):
    from render.overlay_upload import painter
    view.native_panels = True
    def content():
        view._label(22, 80, 'before exception')
        raise RuntimeError('injected')
    with pytest.raises(RuntimeError, match='injected'):
        view._draw_collapsible('left', 'TEST', content)
    assert painter.native_sink is None
    model = view.native_vector_model()
    model['ops'].clear()
    assert view.native_vector_model()['ops']


def test_affine_controls_collapse_restore_and_stale_wheel_are_reachable(game, view, monkeypatch):
    from render.camera import Camera
    from render.input import InputController
    from game.net.replay import state_checksum
    from types import SimpleNamespace
    view.native_panels = True
    constructor = next(e for e in game.state.entities.values() if e.owner == 0 and e.is_construction)
    ctrl = InputController(game.state, Camera(1280, 800), view, SimpleNamespace(flash=lambda *_: None))
    ctrl.selection = {constructor.id}
    def draw():
        reset_capture(view)
        view._left_panel(ctrl.selection, 0); view._right_panel(ctrl.selection, 0)
    def click(button):
        for event in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            ctrl.handle_event(pygame.event.Event(event, button=1, pos=button['rect'].center))
    before = state_checksum(game.state)
    draw()
    region, key = next((rect, key) for rect, key in view.scroll_rects if key == 'stations')
    assert region.x >= 1030 and region.width <= 240
    old_scroll = dict(view.scroll)
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: region.center)
    ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
    assert view.scroll[key] > old_scroll[key]
    draw()
    collapse = next(b for b in view.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == 'right')
    # Edge rounding uses the same rect as the native outlined button.
    assert any(op['kind'] == 'rect' and op['rect'] == list(collapse['rect']) for op in view.native_vector_model()['ops'])
    click(collapse)
    assert view.minimized['right']
    old_scroll, old_distance = dict(view.scroll), ctrl.camera.distance
    ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
    assert view.scroll == old_scroll and ctrl.camera.distance == old_distance
    draw()
    restore = next(b for b in view.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == 'right')
    assert restore['rect'].right == 1270
    assert not any(key == 'stations' for _, key in view.scroll_rects)
    assert any(op.get('text', '').endswith('  +') for op in view.native_vector_model()['ops'])
    click(restore)
    assert not view.minimized['right']
    draw()
    assert any(key == 'stations' for _, key in view.scroll_rects)
    assert state_checksum(game.state) == before


def test_native_station_production_preserves_every_wheel_reachable_row(game, view):
    from game.core.vectors import Vec3
    from render.camera import Camera
    from render.input import InputController
    from types import SimpleNamespace
    from unittest.mock import patch
    from game.net.replay import state_checksum
    yard = game.factory.spawn_station('shipyard', 0, Vec3())
    yard.collection_point = Vec3(7345, 0, -5234)
    yard.upgrade_level = 4
    yard.build_queue = [dict(kind='station_upgrade', item='shipyard', time_left=100),
                        dict(kind='ship', item='imperial_corvette', time_left=100),
                        dict(kind='ship', item='imperial_corvette', time_left=100)]
    player = game.state.players[0]
    player.credits = player.materials = player.energy = player.crew = 100000
    view.native_panels = True
    ctrl = InputController(game.state, Camera(1280, 800), view, SimpleNamespace(flash=lambda *_: None))
    ctrl.selection = {yard.id}
    expected = {d.id for d in view._shipyard_items(yard, game.ds.stations['shipyard'])
                if game.construction.station_can_build_ship(yard, d.id)}
    before = state_checksum(game.state)
    seen, kinds = set(), set()
    for _ in range(40):
        reset_capture(view)
        view._right_panel(ctrl.selection, 0)
        seen.update(b['payload']['ship_id'] for b in view.buttons if b['kind'] == 'build_ship')
        kinds.update(b['kind'] for b in view.buttons)
        for region, key in list(view.scroll_rects):
            with patch('pygame.mouse.get_pos', return_value=region.center):
                ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
    assert seen == expected
    assert {'collection_clear', 'cancel_build', 'build_ship'} <= kinds
    assert state_checksum(game.state) == before


def test_native_compose_resets_complete_snapshot_and_keeps_other_overlay(view):
    view.native_panels = True
    view.native_top_bar = True
    view.mission_progress = ['[ ] Mission uses native glyphs']
    view.compose(set(), None, 0, False)
    first = view.native_vector_model()
    assert any('Mission uses native glyphs' in op.get('text', '') for op in first['ops'])
    view.compose(set(), None, 0, False)
    assert first == view.native_vector_model(), 'complete frames must not accumulate ops'
    view.native_top_bar = False
    view.compose(set(), None, 0, False)
    assert first == view.native_vector_model(), 'top bar flag must be independent'
    assert view.overlay.get_at((1, 1)).a > 0
    assert view.overlay.get_at((1031, 70)).a == 0
    assert view.overlay.get_at((1058, 578)).a == 0


@pytest.mark.parametrize('op,fog', [
    ({'kind': 'polygon', 'points': [[0, 0], [1, 1]], 'color': [1, 2, 3, 255], 'stroke': 0}, None),
    ({'kind': 'fog', 'rect': [0, 0, 202, 202]}, None),
])
def test_encoder_rejects_shapes_native_decoder_cannot_accept(view, op, fog):
    from render_bridge.vector_hud import encode
    model = view.native_vector_model()
    model.update(active=True, ops=[dict(op, clip=[0, 0, 1280, 800])], fog=fog)
    with pytest.raises(ValueError):
        encode(model)
