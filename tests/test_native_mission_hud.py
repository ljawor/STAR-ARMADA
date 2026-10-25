"""Mission objectives and contextual hints share one native collapsible scope."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest

from helpers import make_game
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.presentation import PresentationOverlay
from render_bridge.vector_hud import Capture, encode


class NoRasterFont:
    def __init__(self, face): self.face = face
    def render(self, *a, **k): raise AssertionError('Mission text rasterized instead of native glyphs')
    def __getattr__(self, name): return getattr(self.face, name)


@pytest.fixture
def mission_view():
    gm = make_game(ai=False)
    hud = HUD(1280, 800, gm.state)
    hud.native_panels = True
    hud.mission_name = 'Recovery Drill'
    hud.mission_progress = ['[ ] Board and capture the abandoned syndicate corvette']
    hud.mission_hints = ['Goal: board and capture the hull.', 'Select your cruiser to board (B).']
    ctrl = InputController(gm.state, Camera(1280, 800), hud, SimpleNamespace(flash=lambda *_: None))
    return gm, hud, ctrl


def texts(hud):
    return [op['text'] for op in hud.native_vector_model()['ops'] if op['kind'] == 'text']


def test_mission_scope_emits_native_text_without_any_rasterization(mission_view):
    _, hud, _ = mission_view
    for name in ('font', 'font_big', 'font_small'):
        setattr(hud, name, NoRasterFont(getattr(hud, name)))
    with patch.object(pygame.draw, 'rect', side_effect=AssertionError('Mission rect rasterized')):
        hud._mission_panel(0)
    labels = texts(hud)
    assert 'Recovery Drill' in labels
    assert any('abandoned syndicate' in text for text in labels)
    assert 'Select your cruiser to board (B).' in labels
    encode(hud.native_vector_model())
    assert pygame.surfarray.array_alpha(hud.overlay).max() == 0


def test_minimize_hides_objectives_hints_and_hitboxes_and_restore_recovers(mission_view):
    gm, hud, ctrl = mission_view
    before = gm.state.to_dict(precise=True)
    hud._mission_panel(0)
    assert any('Goal:' in text for text in texts(hud))
    control = next(b for b in hud.buttons if b['kind'] == 'hud_panel')
    ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=control['rect'].center))
    assert hud.minimized['mission']
    hud.compose(set(), None, 0, False)
    labels = texts(hud)
    assert not any('Recovery Drill' in s or 'Goal:' in s or 'cruiser to board' in s for s in labels)
    restore = next(b for b in hud.buttons if b['kind'] == 'hud_panel' and b['payload']['panel']=='mission')
    assert not any(r.collidepoint((640,200)) for r in hud.blocked_rects)
    ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=restore['rect'].center))
    hud.compose(set(), None, 0, False)
    assert any('cruiser to board' in s for s in texts(hud))
    assert gm.state.to_dict(precise=True) == before


def test_application_native_model_is_appended_after_normal_hud(mission_view):
    _, hud, _ = mission_view
    cap = Capture(1280,800)
    cap.append(dict(kind='rect',clip=[0,0,1280,800],rect=[400,100,480,500],stroke=0,radius=8,color=[8,14,25,250]))
    hud.native_application_model = cap.snapshot(True)
    hud.compose(set(), None, 0, False)
    assert hud.native_vector_model()['ops'][-1] == cap.ops[-1]
    hud.native_application_model = None
    hud.compose(set(), None, 0, False)
    assert cap.ops[-1] not in hud.native_vector_model()['ops']


def test_managed_mission_hints_do_not_create_a_second_raster_card(mission_view):
    gm, hud, ctrl = mission_view
    overlay = PresentationOverlay(1280,800,dict(tutorial_hints=True))
    with patch.object(overlay,'tutorial_paragraphs',return_value=['Goal: board and capture the hull.']):
        result = overlay.draw(gm.state,ctrl,mission_managed_by_hud=True)
    assert not overlay.panel_rects
    assert pygame.surfarray.array_alpha(result).max() == 0
    # Explicit modal help is independent of mission collapse.
    overlay.help_visible=True
    overlay.draw(gm.state,ctrl,mission_managed_by_hud=True)
    assert overlay.panel_rects


def test_cpp_application_path_publishes_native_briefing_not_raster_surface(mission_view):
    gm, hud, ctrl = mission_view
    source=Path(__file__).resolve().parents[1]/'main.py'
    nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='cpp_overlay_layers']
    cap=Capture(1280,800).snapshot(True)
    cinematic=SimpleNamespace(native_model=lambda *a:cap,compose=lambda *a:pytest.fail('Native briefing rasterized'))
    env=dict(hud=hud,cinematic=cinematic,CPP_HUD_SIZE=(1280,800),state=gm.state,inputc=ctrl,local_player=0)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),env)
    assert env['cpp_overlay_layers']()==[]
    assert hud.native_application_model==cap
