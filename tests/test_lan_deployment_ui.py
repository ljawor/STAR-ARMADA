"""Host deployment parity, eight-slot natural input and pinned LAN controls."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pygame
from render import menus, i18n
from game.core.skirmish import SKIRMISH_MAP_IDS
from game.net.lan import build_lan_map
from test_skirmish_menu import press


class HostDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.scope = ExitStack()
        self.addCleanup(self.scope.close)
        root = Path(self.scope.enter_context(tempfile.TemporaryDirectory()))
        for key, leaf in [('USER_DIR', ''), ('SAVES_DIR', 'saves'),
                          ('SETTINGS_PATH', 'settings.json'), ('CAMPAIGN_PATH', 'campaign.json'),
                          ('BALANCE_PATH', 'balance.json')]:
            self.scope.enter_context(patch.object(menus, key, str(root / leaf)))
        self.scope.enter_context(patch('pygame.mouse.get_pos', return_value=(0, 0)))
        self.menu = menus.MenuStack(1120, 700)
        self.addCleanup(self.menu.close)
        self.menu.screen = 'lan_host'
        self.menu.render(0)

    def choose(self, action, value=None):
        press(self.menu, action, value)
        self.menu.render(0)

    def test_all_maps_square_chart_roster_and_lan_footer(self):
        m = self.menu
        self.assertEqual([b['payload'] for b in m.buttons if b['action'] == 'lan_map'], list(SKIRMISH_MAP_IDS))
        self.assertEqual(m.lan_preview_rect, pygame.Rect(280, 140, 420, 420))
        for action, expected in [('lan_back', (32, 650, 180, 36)), ('lan_connect', (852, 650, 236, 36))]:
            self.assertEqual(next(b['rect'] for b in m.buttons if b['action'] == action), pygame.Rect(expected))
        self.assertEqual({b['payload'] for b in m.buttons if b['action'] == 'lan_field'}, {'lan_name', 'lan_port'})
        self.assertIn('Create lobby', m.lan_rendered_text)

    def test_eight_humans_or_two_humans_six_ai_launch_all_slots(self):
        self.choose('lan_map', 'skirmish05')
        for _ in range(8):
            self.choose('lan_humans', 1)
        self.assertEqual(self.menu.lan_options['human_count'], 8)
        self.assertEqual(len([b for b in self.menu.buttons if b['action'] == 'lan_faction']), 8)
        built = build_lan_map(self.menu.skirmish_store, self.menu.lan_options)
        self.assertEqual([p['is_ai'] for p in built['players']], [False] * 8)
        for _ in range(8):
            self.choose('lan_humans', -1)
        for _ in range(8):
            self.choose('lan_ai', 1)
        self.assertEqual((self.menu.lan_options['human_count'], self.menu.lan_options['ai_count']), (2, 6))
        self.assertEqual([p['is_ai'] for p in build_lan_map(self.menu.skirmish_store, self.menu.lan_options)['players']], [False] * 2 + [True] * 6)

    def test_color_faction_and_starts_survive_resize_and_map_shrink(self):
        m = self.menu
        self.choose('lan_map', 'skirmish05')
        self.choose('lan_color', 7)
        self.choose('lan_faction', 7)
        self.choose('lan_spawn', 7)
        saved = (m.lan_options['colors'][7], m.lan_options['factions'][7])
        self.assertEqual(len(set(m.lan_options['colors'])), 8)
        self.assertEqual(sorted(m.lan_options['spawn_slots']), list(range(8)))
        for _ in range(6):
            self.choose('lan_humans', 1)
        self.choose('lan_map', 'skirmish06')
        self.assertEqual(m.lan_options['human_count'], 2)
        self.assertEqual(m.lan_options['ai_count'], 0)
        self.assertEqual(m.lan_options['spawn_slots'], [0, 1])
        self.choose('lan_map', 'skirmish05')
        self.assertEqual((m.lan_options['colors'][7], m.lan_options['factions'][7]), saved)
        self.choose('lan_spawn_point', 7)
        built = build_lan_map(m.skirmish_store, m.lan_options)
        self.assertEqual(built['players'][0]['start'], m.skirmish_store.maps['skirmish05']['players'][7]['start'])

    def test_create_and_edit_lobby_preserve_payload_and_connection_fields(self):
        m = self.menu
        self.choose('lan_map', 'skirmish05')
        self.choose('lan_spawn', 7)
        self.choose('lan_field', 'lan_port')
        m.lan_port = '7781'
        m.lan_name = 'Commander'
        session = SimpleNamespace(snapshot={'is_host': True}, local_player=0, close=lambda: None, enable_recovery=lambda: None)
        with patch('game.net.lan.LanSession.host', return_value=session) as host:
            self.choose('lan_connect')
            host.assert_called_once_with(7781, deepcopy(m.lan_options), name='Commander')
        m.screen = 'lan_host'
        session.configure = lambda options: setattr(session, 'configured', options)
        m.render(0)
        self.choose('lan_connect')
        self.assertEqual(session.configured, m.lan_options)
        self.assertIsNot(session.configured, m.lan_options)

    def assert_layout(self, prefix='lan'):
        m = self.menu
        viewport = pygame.Rect(0, 0, m.width, m.height)
        for i, b in enumerate(m.buttons):
            self.assertTrue(viewport.contains(b['rect']), b)
            self.assertFalse(any(b['rect'].colliderect(v['rect']) for v in m.buttons[i + 1:]), b)
        bounds = [r for r in getattr(m, prefix + '_text_bounds') if r.w]
        for i, r in enumerate(bounds):
            self.assertTrue(viewport.contains(r), r)
            self.assertFalse(any(r.colliderect(v) for v in bounds[i + 1:]), (r, bounds))

    def test_all_maps_full_capacity_languages_and_windows_have_no_overlaps(self):
        previous = i18n.language()
        self.addCleanup(i18n.set_language, previous)
        m = self.menu
        for language, _ in i18n.LANGUAGES:
            i18n.set_language(language)
            for width, height in ((800, 600), (1024, 768), (1440, 900)):
                m.width, m.height = width, height
                m._surface = pygame.Surface((width, height))
                for mid in SKIRMISH_MAP_IDS:
                    self.choose('lan_map', mid)
                    while m.lan_options['human_count'] < m.skirmish_capacity(mid):
                        self.choose('lan_humans', 1)
                    self.assert_layout()
                    self.assertEqual(len(m.lan_preview_starts), m.skirmish_capacity(mid))
                    self.assertEqual(m.lan_preview_rect.w, m.lan_preview_rect.h)

    def test_eight_human_lobby_ready_edit_launch_controls_remain_visible(self):
        m = self.menu
        m.lan_options.update(map_id='skirmish05', human_count=8, ai_count=0)
        m.lan_session = SimpleNamespace(local_player=0, close=lambda: None,
            snapshot=dict(options=deepcopy(m.lan_options), is_host=True, can_start=True,
                          players=[dict(slot=i, name=f'Commander {i + 1}', ready=True) for i in range(8)]))
        m.screen = 'lan_lobby'
        for width, height in ((800, 600), (1440, 900)):
            m.width, m.height = width, height
            m._surface = pygame.Surface((width, height))
            m.render(0)
            self.assert_layout()
            self.assertTrue({'lan_edit', 'lan_ready', 'lan_start', 'lan_back'} <= {b['action'] for b in m.buttons})
            self.assertIn('Commander 8', m.lan_rendered_text)
