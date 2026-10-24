"""Natural-input deployment and pinned footer acceptance."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import pygame
from render.menus import MenuStack, MenuResult
from test_skirmish_menu import press


class DeploymentUITests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = self.stack.enter_context(tempfile.TemporaryDirectory())
        for name, leaf in [('USER_DIR', ''), ('SAVES_DIR', 'saves'),
                           ('SETTINGS_PATH', 'settings.json'), ('CAMPAIGN_PATH', 'campaign.json'),
                           ('BALANCE_PATH', 'balance.json')]:
            self.stack.enter_context(patch('render.menus.' + name, os.path.join(root, leaf)))
        self.stack.enter_context(patch('pygame.mouse.get_pos', return_value=(0, 0)))
        self.menu = MenuStack(1280, 800)
        self.addCleanup(self.menu.close)
        self.menu.screen = 'skirmish'
        self.menu.render(0)

    def test_click_map_start_swaps_player_and_launches_at_selected_anchor(self):
        from game.core.skirmish import build_skirmish_map
        m = self.menu
        self.assertIn('skirmish_spawn_point', [b['action'] for b in m.buttons])
        press(m, 'skirmish_spawn_point', 1)
        self.assertEqual(m.skirmish_options['spawn_slots'][:2], [1, 0])
        m.render(0)
        press(m, 'launch_skirmish')
        self.assertEqual(m.result, MenuResult.START_SKIRMISH)
        result = build_skirmish_map(m.skirmish_store, m.result_payload)
        self.assertEqual(result['players'][0]['start'], m.skirmish_store.maps['skirmish01']['players'][1]['start'])

    def test_square_preview_and_footer_unchanged(self):
        m = self.menu
        rect = m.skirmish_preview_rect
        self.assertEqual(rect.w, rect.h)
        scale = min(m.width / 1120, m.height / 700)
        ox, oy = (m.width-round(1120*scale))//2, (m.height-round(700*scale))//2
        for action, logical in [('goto_main', (32,650,180,36)), ('launch_skirmish', (852,650,236,36))]:
            expected = pygame.Rect(ox+round(logical[0]*scale), oy+round(logical[1]*scale), round(logical[2]*scale),round(logical[3]*scale))
            self.assertEqual(next(b['rect'] for b in m.buttons if b['action']==action), expected)

    def test_all_maps_at_capacity_fit_and_launch_from_reassigned_starts(self):
        from game.core.skirmish import SKIRMISH_MAP_IDS, build_skirmish_map
        m = self.menu
        for width,height in ((800,600),(1024,768),(1440,900)):
            m.width,m.height = width,height
            m._surface = pygame.Surface((width,height))
            m.result = MenuResult.NONE
            for map_id in SKIRMISH_MAP_IDS:
                m.buttons = []
                m.render(0)
                press(m,'skirmish_map',map_id)
                m.render(0)
                capacity = m.skirmish_capacity(map_id)
                while m.skirmish_options['ai_count'] < capacity-1:
                    press(m,'skirmish_ai',1)
                    m.render(0)
                self.assertEqual(len([b for b in m.buttons if b['action']=='skirmish_spawn']),capacity)
                window = pygame.Rect(0,0,width,height)
                for i,b in enumerate(m.buttons):
                    self.assertTrue(window.contains(b['rect']), (map_id,b))
                    self.assertFalse(any(b['rect'].colliderect(o['rect']) for o in m.buttons[i+1:]),(map_id,b))
                for i,r in enumerate(m.skirmish_text_bounds):
                    self.assertTrue(window.contains(r), (map_id,r))
                    self.assertFalse(any(r.colliderect(o) for o in m.skirmish_text_bounds[i+1:]),(map_id,r))
                press(m,'skirmish_spawn_point',capacity-1)
                m.render(0)
                starts = m.skirmish_options['spawn_slots']
                self.assertEqual(len(set(starts)),capacity)
                built = build_skirmish_map(m.skirmish_store,m.skirmish_options)
                self.assertEqual(built['players'][0]['start'],m.skirmish_store.maps[map_id]['players'][capacity-1]['start'])

    def test_translated_eight_player_roster_and_terrain_labels_fit(self):
        from render import i18n
        previous = i18n.language()
        self.addCleanup(i18n.set_language,previous)
        for code,_ in i18n.LANGUAGES:
            i18n.set_language(code)
            self.test_all_maps_at_capacity_fit_and_launch_from_reassigned_starts()

    def test_inactive_duplicate_color_does_not_create_nine_choice_slots(self):
        m = self.menu
        press(m,'skirmish_color',0)
        press(m,'skirmish_color',0)
        self.assertEqual(m.skirmish_options['colors'][0],m.skirmish_options['colors'][2])
        press(m,'skirmish_map','skirmish05')
        self.assertEqual(len(m.skirmish_options['colors']),8)
        m.render(0)
        for _ in range(6):
            press(m,'skirmish_ai',1)
            m.render(0)
        press(m,'launch_skirmish')
        self.assertEqual(m.result,MenuResult.START_SKIRMISH)

    def test_map_shrink_preserves_valid_high_team_ids(self):
        m = self.menu
        press(m,'skirmish_map','skirmish05')
        m.render(0)
        for slot,target in ((0,7),(1,6)):
            while m.skirmish_options['teams'][slot] != target:
                press(m,'skirmish_team',slot)
                m.render(0)
        press(m,'skirmish_map','skirmish01')
        m.render(0)
        press(m,'launch_skirmish')
        self.assertEqual(m.result,MenuResult.START_SKIRMISH)
        self.assertEqual(m.result_payload['teams'][:2],[7,6])

    def test_roster_spawn_control_cycles_without_duplicate_starts(self):
        m = self.menu
        press(m, 'skirmish_spawn', 1)
        self.assertEqual(m.skirmish_options['spawn_slots'][:2], [1, 0])
        m.render(0)
        self.assertEqual(len({tuple(b['rect']) for b in m.buttons}), len(m.buttons))
