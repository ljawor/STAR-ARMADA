"""Responsive classic screens and preserved live interaction contracts."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import pygame
import pytest
from render.menus import MenuStack, DEFAULT_SETTINGS
from render.clean_classic import ACCENT

SIZES = ((800, 600), (1280, 800), (1440, 900), (2400, 1400))

# #160 retired the renderer, preview and pack-order rows: the window is the one renderer, the
# approved catalogue is always on, and the pack list is shipped order. `model_preview` and
# `visual_packs` are still read out of the settings file by `render.asset_selection`, and
# `model_preview_explicit` is bookkeeping; no screen offers any of the four. Exclude them by
# name rather than letting the walk quietly stop comparing them (same set as
# test_presentation_ux.NO_ROW).
NO_ROW = {'renderer', 'model_preview', 'visual_packs', 'model_preview_explicit'}



@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr('render.menus.USER_DIR', str(tmp_path))
    monkeypatch.setattr('render.menus.SAVES_DIR', str(tmp_path / 'saves'))
    monkeypatch.setattr('render.menus.SETTINGS_PATH', str(tmp_path / 'saves/settings.json'))
    monkeypatch.setattr('render.menus.CAMPAIGN_PATH', str(tmp_path / 'saves/campaign.json'))
    # The balance editor writes this one (#106): a fixture that only patched the other three
    # would let a screen test tune the developer's own balance file.
    monkeypatch.setattr('render.menus.BALANCE_PATH', str(tmp_path / 'saves/balance.json'))
    instances = []
    original = MenuStack
    def tracked(*args, **kwargs):
        menu = original(*args, **kwargs)
        instances.append(menu)
        return menu
    monkeypatch.setattr(__name__ + '.MenuStack', tracked)
    try:
        yield
    finally:
        for menu in reversed(instances):
            menu.close()

def menu_at(size, screen):
    menu = MenuStack(*size)
    menu.screen = screen
    menu.settings = dict(DEFAULT_SETTINGS)
    return menu

def test_fixture_patches_all_paths_and_closes_on_failure(tmp_path):
    from contextlib import ExitStack
    from inspect import isgenerator
    from pathlib import Path
    from unittest.mock import Mock
    from render import menus
    outer = tmp_path / 'outer'
    outer.mkdir()
    campaign = outer / 'campaign.json'
    settings = outer / 'settings.json'
    campaign_bytes = b'{"mission_index":3}\n'
    settings_bytes = b'{"music_volume":0.13}\n'
    campaign.write_bytes(campaign_bytes)
    settings.write_bytes(settings_bytes)
    for fail in (False, True):
        menu = None
        inner = tmp_path / ('failure' if fail else 'success')
        inner.mkdir()
        try:
            with patch.multiple(menus, USER_DIR=str(outer), SAVES_DIR=str(outer),
                                SETTINGS_PATH=str(settings), CAMPAIGN_PATH=str(campaign)):
                with ExitStack() as stack:
                    scoped = stack.enter_context(pytest.MonkeyPatch.context())
                    fixture = isolated_user_data.__wrapped__(inner, scoped)
                    if isgenerator(fixture):
                        next(fixture)
                        stack.callback(lambda: next(fixture, None))
                    for name in ('USER_DIR', 'SAVES_DIR', 'SETTINGS_PATH', 'CAMPAIGN_PATH'):
                        assert Path(getattr(menus, name)).is_relative_to(inner), name
                    menu = menu_at((800, 600), 'settings')
                    menu.close = Mock(wraps=menu.close)
                    if fail:
                        raise RuntimeError('injected body failure')
        except RuntimeError as exc:
            assert fail and str(exc) == 'injected body failure'
        finally:
            if menu is not None:
                try:
                    menu.close.assert_called_once()
                finally:
                    menu.close()
        assert campaign.read_bytes() == campaign_bytes
        assert settings.read_bytes() == settings_bytes


def test_diagnostic_closes_and_isolates_all_paths_on_assertion_failure(tmp_path):
    import importlib.util
    from pathlib import Path
    from unittest.mock import Mock
    from render import menus
    spec = importlib.util.spec_from_file_location('classic_diag',
            Path(__file__).resolve().parents[1] / 'tools/diag_classic_screens.py')
    diag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diag)
    instance = Mock()
    instance.render.side_effect = AssertionError('injected diagnostic assertion')
    observed = {}
    def construct(*args):
        observed.update({key: getattr(menus, key) for key in
                         ('USER_DIR', 'SAVES_DIR', 'SETTINGS_PATH', 'CAMPAIGN_PATH')})
        return instance
    out = tmp_path / 'diagnostic'
    with patch.object(diag, 'MenuStack', side_effect=construct), \
            patch.object(diag.sys, 'argv', ['diag', str(out)]), \
            patch.object(diag.pygame, 'init'), patch.object(diag.pygame, 'quit'), \
            patch.object(diag.pygame.display, 'set_mode'), \
            patch.object(diag.pygame.event, 'pump'), patch.object(diag, 'glViewport'):
        with pytest.raises(AssertionError, match='injected diagnostic assertion'):
            diag.main()
    instance.close.assert_called_once()
    for key, value in observed.items():
        assert Path(value).is_relative_to(out), key


def geometry(menu, bounds):
    window = menu._surface.get_rect()
    assert all(window.contains(b['rect']) for b in menu.buttons)
    assert all(window.contains(r) for r in bounds)
    for i, r in enumerate(bounds):
        assert not any(r.colliderect(other) for other in bounds[i+1:] if other.w), r
    for i, b in enumerate(menu.buttons):
        assert not any(b['rect'].colliderect(other['rect']) for other in menu.buttons[i+1:])

def test_settings_classic_responsive_focus_and_slider_payload_mapping():
    from render.classic_screens import SETTINGS_PAGE_COUNT
    with patch('pygame.mouse.get_pos', return_value=(0, 0)):
        for size in SIZES:
            menu = menu_at(size, 'settings')
            seen = set()
            # Every page, counted by the screen itself: a walk shorter than the page list
            # silently stops covering the settings that live on the pages it never opens.
            for page in range(SETTINGS_PAGE_COUNT):
                menu.settings_page = page
                menu.settings_focus = 0
                menu.render(0)
                geometry(menu, [r for _, r in menu.settings_text_bounds if r.w])
                controls = [b for b in menu.buttons if isinstance(b['payload'], dict)]
                seen.update(b['payload']['key'] for b in controls)
                if not controls:
                    # A page that carries no setting control — the Game Balance door (#106) —
                    # has no row to focus, measure or slide.
                    continue
                first = controls[0]['rect']
                assert first.w > size[0] * .7
                pixels = [tuple(menu._surface.get_at((first.centerx, first.top + dy)))[:3] for dy in range(3)]
                assert min(max(abs(a - b) for a, b in zip(pixel, ACCENT)) for pixel in pixels) <= 35
                for b in controls:
                    if b['action'] == 'slider':
                        bar = b['payload']['rect']
                        assert b['rect'].contains(bar)
                        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(bar.right, bar.centery)))
                        assert menu.settings[b['payload']['key']] == 1.0
                with patch('pygame.font.SysFont', side_effect=AssertionError('uncached font')):
                    menu.render(0)
            assert seen == set(DEFAULT_SETTINGS) - NO_ROW


def test_briefing_family_measured_wrap_objectives_and_launch_at_all_sizes():
    with patch('pygame.mouse.get_pos', return_value=(0, 0)):
        for size in SIZES:
            menu = menu_at(size, 'briefing')
            for index, mission in enumerate(menu.campaign['missions']):
                menu.selected_mission = index
                menu.render(0)
                assert hasattr(menu, 'briefing_text_bounds'), 'Briefing needs measured classic panels'
                geometry(menu, [r for r in menu.briefing_text_bounds if r.w])
                text = ' '.join(menu.briefing_rendered_text)
                assert mission['briefing'] == ' '.join(mission['briefing'].split())
                assert mission['briefing'] in text
                for objective in mission.get('objectives', []):
                    assert objective.get('text', objective.get('type', '?')) in text
                launch = next(b for b in menu.buttons if b['action'] == 'launch_mission')
                assert launch['payload'] == index
                assert launch['rect'].y > size[1] * .8
                with patch('pygame.font.SysFont', side_effect=AssertionError('uncached font')):
                    menu.render(0)


def test_campaign_classic_rows_scale_locked_status_and_index_payloads():
    with patch('pygame.mouse.get_pos', return_value=(0, 0)), patch('render.menus.load_campaign_unlocks', return_value={'a'}):
        for size in SIZES:
            menu = menu_at(size, 'campaign')
            menu.campaign = {'campaign': 'Outer Armada', 'missions': [dict(id='a', name='First fleet'), dict(id='b', name='Second fleet')]}
            menu.render(0)
            assert hasattr(menu, 'campaign_text_bounds'), 'Campaign needs classic measured rows'
            geometry(menu, [r for r in menu.campaign_text_bounds if r.w])
            assert all(r.w > size[0] * .7 for r in menu.campaign_rows.values())
            assert [b['payload'] for b in menu.buttons if b['action'] == 'select_mission'] == [0]
            assert 'LOCKED' in menu.campaign_rendered_text
            assert 'AVAILABLE' in menu.campaign_rendered_text
            with patch('pygame.font.SysFont', side_effect=AssertionError('uncached font')):
                menu.render(0)


def test_lan_family_responsive_actions_status_and_readonly_lobby():
    with patch('pygame.mouse.get_pos', return_value=(0, 0)):
        for size in SIZES:
            for screen in ('lan', 'lan_join', 'lan_lobby'):
                menu = menu_at(size, screen)
                snap = dict(status='Lobby', port=7777, addresses=['192.168.1.8'],
                    options=deepcopy(menu.lan_options), is_host=True, can_start=True, error=None,
                    players=[dict(slot=0, name='Host', ready=False)])
                if screen == 'lan_lobby':
                    menu.lan_session = SimpleNamespace(snapshot=snap, local_player=0, close=lambda: None)
                before = deepcopy(snap)
                menu.render(0)
                assert hasattr(menu, 'lan_text_bounds'), 'LAN needs measured classic typography'
                geometry(menu, [r for r in menu.lan_text_bounds if r.w])
                actions = [b['action'] for b in menu.buttons]
                if screen == 'lan':
                    assert actions == ['lan_host_setup', 'lan_join_setup', 'goto_main']
                elif screen == 'lan_join':
                    assert [b['payload'] for b in menu.buttons if b['action'] == 'lan_field'] == ['lan_name', 'lan_port', 'lan_address']
                    assert 'lan_connect' in actions
                else:
                    assert {'lan_edit', 'lan_ready', 'lan_start', 'lan_back'} <= set(actions)
                    assert '192.168.1.8' in ' '.join(menu.lan_rendered_text)
                    assert snap == before
                with patch('pygame.font.SysFont', side_effect=AssertionError('uncached font')):
                    menu.render(0)
