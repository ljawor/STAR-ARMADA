"""Wheel ownership through production HUD geometry, input and native input rings."""
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest

from helpers import make_game
from game.core.vectors import Vec3
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.input_bridge import RingInput
from render.replay_input import ReplayInput
from render_bridge import input as wire, ring


@pytest.fixture
def view():
    game = make_game(ai=False)
    hud = HUD(1280, 800, game.state)
    hud.native_panels = True
    hud.native_top_bar = True
    camera = Camera(1280, 800)
    controller = InputController(game.state, camera, hud, SimpleNamespace(flash=lambda *_: None))
    return game, hud, camera, controller


def draw(view, selection=None):
    game, hud, camera, controller = view
    if selection is not None:
        controller.selection = {selection.id}
    hud.compose(controller.selection, None, 0, False)


def wheel(controller, pos, direction, legacy=False, with_pos=True):
    if legacy:
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                  button=4 if direction > 0 else 5, pos=pos, remote=True)
    else:
        attrs = dict(x=0, y=direction)
        if with_pos:
            attrs.update(pos=pos, remote=True)
        event = pygame.event.Event(pygame.MOUSEWHEEL, **attrs)
    controller.handle_event(event)


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('direction', [-1, 1])
@pytest.mark.parametrize('panel', ['top', 'left', 'right', 'minimap'])
def test_visible_hud_never_zooms_world(view, panel, direction, legacy):
    _, hud, camera, controller = view
    draw(view)
    pos = dict(top=(640, 15), left=(100, 52), right=(1150, 52),
               minimap=hud.minimap_rect.center)[panel]
    before = camera.distance
    # Native event coordinates must win over the unrelated Python-window pointer.
    with patch('pygame.mouse.get_pos', return_value=(640, 400)):
        wheel(controller, pos, direction, legacy)
    assert camera.distance == before


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('builder', ['constructor', 'shipyard'])
def test_real_build_list_scrolls_without_zoom(view, builder, legacy):
    game, hud, camera, controller = view
    entity = (next(e for e in game.state.entities.values() if e.owner == 0 and e.is_construction)
              if builder == 'constructor' else game.factory.spawn_station('shipyard', 0, Vec3()))
    game.visibility.update()
    draw(view, entity)
    key = 'stations' if builder == 'constructor' else 'ships'
    region, key = next((r, k) for r, k in hud.scroll_rects if k == key)
    pos = region.center
    hud.scroll[key] = 0
    distance = camera.distance
    before = game.state.to_dict(precise=True)
    with patch('pygame.mouse.get_pos', return_value=(640, 400)):
        wheel(controller, pos, -1, legacy)
    assert hud.scroll[key] == 1
    assert camera.distance == distance
    with patch('pygame.mouse.get_pos', return_value=(640, 400)):
        wheel(controller, pos, 1, legacy)
    assert hud.scroll[key] == 0
    assert camera.distance == distance
    assert game.state.to_dict(precise=True) == before


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('direction', [-1, 1])
def test_world_wheel_still_zooms_when_local_pointer_is_over_hud(view, legacy, direction):
    _, _, camera, controller = view
    draw(view)
    before = camera.distance
    with patch('pygame.mouse.get_pos', return_value=(1150, 52)):
        wheel(controller, (640, 400), direction, legacy)
    assert (camera.distance < before) == (direction > 0)
    assert camera.distance != before


def test_local_wheel_without_position_uses_actual_local_pointer(view):
    _, _, camera, controller = view
    draw(view)
    before = camera.distance
    with patch('pygame.mouse.get_pos', return_value=(1150, 52)):
        wheel(controller, None, -1, with_pos=False)
    assert camera.distance == before
    with patch('pygame.mouse.get_pos', return_value=(640, 400)):
        wheel(controller, None, -1, with_pos=False)
    assert camera.distance > before


@pytest.mark.parametrize('legacy', [False, True])
def test_scaled_native_ring_wheel_obeys_hud_occlusion(view, tmp_path, legacy):
    _, _, camera, controller = view
    draw(view)
    path = tmp_path / 'input.ring'
    with ring.Ring.create(path, slots=8, slot_bytes=4096) as writer:
        # Retina physical coordinates must map into the actual logical HUD header.
        event = (wire.Event(wire.BUTTON_DOWN, button=5, x=2300, y=104) if legacy else
                 wire.Event(wire.WHEEL, code=-1, x=2300, y=104))
        writer.publish(wire.encode_batch([wire.Event(wire.RESIZE, extra=(2560 << 16) | 1600), event]))
        before = camera.distance
        with RingInput(path, controller, (1280, 800), from_oldest=True) as bridge:
            with patch('pygame.mouse.get_pos', return_value=(640, 400)):
                bridge.poll()
        assert camera.distance == before


def test_replay_wheel_also_respects_visible_hud(view):
    game, hud, camera, _ = view
    controller = ReplayInput(game.state, camera, hud, SimpleNamespace(flash=lambda *_: None))
    draw(view)
    before = camera.distance
    wheel(controller, (1150, 52), -1)
    assert camera.distance == before
    wheel(controller, (640, 400), -1)
    assert camera.distance > before
