"""Clean classic presentation contracts, using actual software menu pixels."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import pygame
from render.menus import MenuStack


class CleanClassicTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        saves = root / 'saves'
        scope = patch.multiple('render.menus', USER_DIR=str(root), SAVES_DIR=str(saves),
                               SETTINGS_PATH=str(saves / 'settings.json'),
                               CAMPAIGN_PATH=str(saves / 'campaign.json'))
        scope.start()
        self.addCleanup(scope.stop)

    def make_menu(self, w, h):
        menu = MenuStack(w, h)
        self.addCleanup(menu.close)
        return menu
    def test_join_and_lobby_keep_actions_without_per_frame_font_allocation(self):
        with patch('pygame.mouse.get_pos', return_value=(0, 0)):
            for screen in ('lan_join', 'lan_lobby'):
                menu = self.make_menu(800, 600)
                menu.screen = screen
                menu.render(0)
                self.assertIn('lan_back', [b['action'] for b in menu.buttons])
                if screen == 'lan_join':
                    self.assertIn('lan_connect', [b['action'] for b in menu.buttons])
                    self.assertEqual([b['payload'] for b in menu.buttons if b['action'] == 'lan_field'], ['lan_name', 'lan_port', 'lan_address'])
                with patch('pygame.font.SysFont', side_effect=AssertionError('per-frame font allocation')):
                    menu.render(0)

    def test_host_uses_shared_battlefield_preview_swatches_and_pinned_session_controls(self):
        from game.core.skirmish import PLAYER_COLORS
        with patch('pygame.mouse.get_pos', return_value=(0, 0)):
            menu = self.make_menu(1120, 700)
            menu.screen = 'lan_host'
            menu.render(0)
            maps = [b['rect'] for b in menu.buttons if b['action'] == 'lan_map']
            self.assertEqual(len(set(r.x for r in maps)), 1)
            self.assertTrue(hasattr(menu, 'lan_preview_rect'))
            colors = [b for b in menu.buttons if b['action'] == 'lan_color']
            self.assertEqual([b['payload'] for b in colors], [0, 1, 2, 3])
            for b in colors:
                rgb = tuple(round(c * 255) for c in PLAYER_COLORS[menu.lan_options['colors'][b['payload']]])
                self.assertEqual(tuple(menu._surface.get_at((b['rect'].x + 15, b['rect'].y + 16)))[:3], rgb)
            connect = next(b['rect'] for b in menu.buttons if b['action'] == 'lan_connect')
            self.assertGreater(connect.top, max(b['rect'].bottom for b in colors))
            self.assertIn('lan_field', [b['action'] for b in menu.buttons])
            with patch('pygame.font.SysFont', side_effect=AssertionError('per-frame font allocation')):
                menu.render(0)

    def test_multiline_glyph_bounds_never_overlap_at_larger_resolution(self):
        with patch('pygame.mouse.get_pos', return_value=(0, 0)):
            menu = self.make_menu(1440, 900)
            menu.screen = 'skirmish'
            menu.render(0)
            bounds = [r for r in menu.skirmish_text_bounds if r.w]
            for i, rect in enumerate(bounds):
                self.assertFalse(any(rect.colliderect(other) for other in bounds[i + 1:]), rect)

    def test_skirmish_battlefield_list_preview_roster_settings_and_cached_fonts(self):
        with patch('pygame.mouse.get_pos', return_value=(0, 0)):
            menu = self.make_menu(1280, 800)
            menu.screen = 'skirmish'
            menu.render(0)
            maps = [b['rect'] for b in menu.buttons if b['action'] == 'skirmish_map']
            self.assertEqual(len(set(r.x for r in maps)), 1)
            preview = menu.skirmish_preview_rect
            self.assertTrue(all(r.right < preview.left for r in maps))
            roster = [b['rect'] for b in menu.buttons if b['action'] == 'skirmish_faction']
            settings = next(b['rect'] for b in menu.buttons if b['action'] == 'skirmish_difficulty')
            self.assertTrue(all(r.left >= preview.left and r.right < settings.left for r in roster))
            with patch('pygame.font.SysFont', side_effect=AssertionError('per-frame font allocation')):
                menu.render(0)

    def test_centered_primary_action_has_seaglass_fill_and_quiet_secondaries(self):
        with patch('pygame.mouse.get_pos', return_value=(0, 0)):
            for w, h in ((800, 600), (960, 640), (1280, 800), (1440, 900)):
                menu = self.make_menu(w, h)
                menu.screen = 'main'
                menu.render(0)
                self.assertEqual([b['action'] for b in menu.buttons],
                                 ['start_skirmish', 'goto_lan', 'goto_campaign', 'goto_saved_games', 'goto_replays', 'goto_settings', 'exit'])
                for b in menu.buttons:
                    self.assertEqual(b['rect'].centerx, w // 2)
                    self.assertTrue(pygame.Rect(0, 0, w, h).contains(b['rect']))
                primary = menu.buttons[0]['rect']
                self.assertEqual(tuple(menu._surface.get_at((primary.x + 12, primary.y + 12)))[:3], (184, 220, 215))
                self.assertNotEqual(tuple(menu._surface.get_at((menu.buttons[1]['rect'].x + 12, menu.buttons[1]['rect'].y + 12)))[:3], (184, 220, 215))
