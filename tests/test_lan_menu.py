"""Software-surface LAN UI tests (no GL context)."""
import os
import tempfile
import unittest
from unittest.mock import patch
import pygame
from render.menus import MenuStack, MenuResult
from test_skirmish_menu import press


class LanMenuTests(unittest.TestCase):
    def setUp(self):
        p = patch('pygame.mouse.get_pos', return_value=(0, 0))
        p.start()
        self.addCleanup(p.stop)
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `render.menus` freezes its persistence paths at import, so a temporary USER_DIR
        # does not move SETTINGS_PATH: pin the settings file itself, or this menu draws in
        # whatever language the developer's own game last saved.
        scope = patch('render.menus.SETTINGS_PATH',
                      os.path.join(holder.name, 'settings.json'))
        scope.start()
        self.addCleanup(scope.stop)
        self.menu = MenuStack(800, 600)
        self.menu.screen = 'main'
        self.menu.render(0)

    def open_host(self):
        press(self.menu, 'goto_lan')
        self.menu.render(0)
        press(self.menu, 'lan_host_setup')
        self.menu.render(0)

    def test_host_capacity_roster_and_choices_are_current_once_per_gesture(self):
        self.open_host()
        self.assertEqual(self.menu.screen, 'lan_host')
        self.assertEqual(self.menu.lan_port, '7777')
        for mid, capacity in zip(('skirmish01', 'skirmish02', 'skirmish03', 'skirmish04'), (2, 3, 4, 4)):
            press(self.menu, 'lan_map', mid)
            self.menu.render(0)
            for _ in range(4):
                press(self.menu, 'lan_humans', 1)
                self.menu.render(0)
            self.assertEqual(self.menu.lan_options['human_count'], capacity)
            self.assertEqual(self.menu.lan_options['ai_count'], 0)
        press(self.menu, 'lan_humans', -1)
        self.menu.render(0)
        press(self.menu, 'lan_ai', 1)
        self.menu.render(0)
        self.assertEqual(self.menu.lan_options['ai_count'], 1)
        press(self.menu, 'lan_color', 0)
        press(self.menu, 'lan_faction', 0)
        press(self.menu, 'lan_difficulty')
        press(self.menu, 'lan_cooperative')
        self.assertEqual(len(set(self.menu.lan_options['colors'])), 8)
        self.assertEqual(self.menu.lan_options['factions'][0], 'rebel')
        self.assertTrue(self.menu.lan_options['cooperative'])
        self.assertTrue(all(self.menu._surface.get_rect().contains(b['rect']) for b in self.menu.buttons))

    def test_text_fields_validate_port_before_connection(self):
        self.open_host()
        press(self.menu, 'lan_field', 'lan_port')
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL, unicode='a'))
        self.menu.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='65536'))
        self.assertEqual(self.menu.lan_port, '65536')
        press(self.menu, 'lan_connect')
        self.assertIsNone(self.menu.lan_session)
        self.assertIn('1', self.menu.lan_notice)
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(self.menu.screen, 'lan')
        self.assertEqual(self.menu.buttons, [])

    def test_lobby_ready_gating_snapshot_readonly_launch_transfer_and_cancel(self):
        from copy import deepcopy
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.open_host()
        snapshot = dict(status='lobby', error=None, players=[dict(slot=0, name='Host', ready=False)],
                        options=deepcopy(self.menu.lan_options), port=7777,
                        addresses=['192.168.1.8'], is_host=True, can_start=False)
        session = SimpleNamespace(snapshot=snapshot, local_player=0, launch=None,
                                  poll=Mock(), close=Mock(), set_ready=Mock(), start=Mock())
        self.menu.lan_session = session
        self.menu.screen = 'lan_lobby'
        before = deepcopy(snapshot)
        self.menu.apply_pending()
        self.menu.render(0)
        self.assertIn('192.168.1.8', ' '.join(self.menu.lan_rendered_text))
        self.assertNotIn('lan_start', [b['action'] for b in self.menu.buttons])
        press(self.menu, 'lan_ready')
        session.set_ready.assert_called_once_with(True)
        self.assertEqual(snapshot, before)
        snapshot['can_start'] = True
        self.menu.render(0)
        press(self.menu, 'lan_start')
        session.start.assert_called_once()
        session.launch = dict(map_def={}, local_player=0)
        self.menu.apply_pending()
        self.assertEqual(self.menu.result, MenuResult.START_LAN)
        self.assertIs(self.menu.result_payload, session)
        self.assertIsNone(self.menu.lan_session)
        session.close.assert_not_called()
        self.menu.lan_session = session
        self.menu.result = MenuResult.NONE
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        session.close.assert_called_once()

    def test_host_lobby_can_edit_and_configure_without_replacing_connection(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from copy import deepcopy
        self.open_host()
        snap = dict(is_host=True, error=None, status='lobby', port=7777, addresses=[],
                    players=[dict(slot=0, name='Host', ready=False)], can_start=False,
                    options=deepcopy(self.menu.lan_options))
        session = SimpleNamespace(snapshot=snap, launch=None, local_player=0, configure=Mock(), close=Mock())
        self.menu.lan_session = session
        self.menu.screen = 'lan_lobby'
        self.menu.render(0)
        self.assertIn('lan_edit', [b['action'] for b in self.menu.buttons])
        press(self.menu, 'lan_edit')
        self.menu.render(0)
        press(self.menu, 'lan_map', 'skirmish03')
        self.menu.render(0)
        press(self.menu, 'lan_ai', 1)
        self.menu.render(0)
        press(self.menu, 'lan_connect')
        self.assertIs(self.menu.lan_session, session)
        self.assertEqual(self.menu.screen, 'lan_lobby')
        session.configure.assert_called_once()
        self.assertEqual(session.configure.call_args.args[0]['ai_count'], 1)
        self.assertEqual(snap['options']['ai_count'], 0)
        session.close.assert_not_called()

    def test_ready_transport_failure_is_visible_and_does_not_escape_event_handler(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.open_host()
        session = SimpleNamespace(snapshot=dict(is_host=False, error=None, status='lobby',
                  options=self.menu.lan_options, port=7777, addresses=[], can_start=False,
                  players=[dict(slot=1, name='Client', ready=False)]), local_player=1,
                  set_ready=Mock(side_effect=ConnectionError('Connection lost')), close=Mock())
        self.menu.lan_session = session
        self.menu.screen = 'lan_lobby'
        self.menu.render(0)
        press(self.menu, 'lan_ready')
        self.assertIn('Connection lost', self.menu.lan_notice)
        self.assertIsNone(self.menu.lan_session)
        session.close.assert_called_once()
        self.assertEqual(self.menu.screen, 'lan_join')

    def test_menu_close_releases_session_and_overlay_once(self):
        from unittest.mock import Mock
        self.assertTrue(hasattr(self.menu, 'close'), 'Menu GL/session cleanup missing')
        self.menu.lan_session = Mock()
        session = self.menu.lan_session
        self.menu.overlay_tex = 17
        with patch('OpenGL.GL.glDeleteTextures') as delete:
            self.menu.close()
            self.menu.close()
            delete.assert_called_once_with([17])
        session.close.assert_called_once()
        self.assertIsNone(self.menu.overlay_tex)

    def test_multiplayer_opens_host_join_without_launch_or_stale_targets(self):
        self.assertIn('goto_lan', [b['action'] for b in self.menu.buttons])
        pos = press(self.menu, 'goto_lan')
        self.assertEqual(self.menu.screen, 'lan')
        self.assertEqual(self.menu.buttons, [])
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.menu.render(0)
        self.assertIn('lan_host_setup', [b['action'] for b in self.menu.buttons])
        self.assertIn('lan_join_setup', [b['action'] for b in self.menu.buttons])
