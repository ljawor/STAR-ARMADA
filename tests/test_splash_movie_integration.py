"""Movie composition uses actual decoder assets, not a gameplay simulation."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import pygame
from render import menus


class SplashMovieIntegrationTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        asset = root / 'assets' / 'menu' / 'battle.zip'
        asset.parent.mkdir(parents=True)
        with zipfile.ZipFile(asset, 'w') as archive:
            archive.writestr('metadata.json', json.dumps(dict(version=1, width=8,
                height=6, fps=2, frame_count=4, still_frame=1, loop='baked-crossfade')))
            for index in range(4):
                frame = pygame.Surface((8, 6))
                frame.fill((50 + index * 50, 15, 25))
                encoded = io.BytesIO()
                pygame.image.save(frame, encoded, 'frame.jpg')
                archive.writestr(f'frames/{index:05d}.jpg', encoded.getvalue())
        self.scope = patch.object(menus, 'ASSET_ROOT', str(root))
        self.scope.start()
        self.addCleanup(self.scope.stop)
        saves = root / 'saves'
        paths = patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                               SETTINGS_PATH=str(saves / 'settings.json'),
                               CAMPAIGN_PATH=str(saves / 'campaign.json'))
        paths.start()
        self.addCleanup(paths.stop)
        self.menu = menus.MenuStack(800, 600)
        self.addCleanup(self.menu.close)
        self.menu.settings = dict(menus.DEFAULT_SETTINGS)

    def test_start_screen_lazily_composites_movie_and_keeps_entry_target(self):
        self.assertIsNone(getattr(self.menu, '_menu_movie', None))
        self.menu.render(0)
        self.assertIsNotNone(getattr(self.menu, '_menu_movie', None))
        self.assertTrue(self.menu._menu_movie.available)
        first = self.menu._surface.get_at((10, 10)).r
        self.menu.render(.6)
        self.assertGreater(self.menu._surface.get_at((10, 10)).r, first)
        self.assertEqual(self.menu.buttons[0]['action'], 'goto_main')
        self.assertEqual(self.menu.buttons[0]['rect'], pygame.Rect(0, 0, 800, 600))
        self.assertEqual(self.menu._menu_movie.cache_info()['frames'], 2)

    def test_reduced_motion_is_a_still_even_with_elapsed_time_and_resize(self):
        self.menu.settings['reduced_motion'] = True
        self.menu.render(0)
        first = pygame.image.tobytes(self.menu._surface, 'RGB')
        self.menu.t = 12  # Reduced Motion must ignore phase, including the hint.
        self.menu.render(10)
        self.assertEqual(first, pygame.image.tobytes(self.menu._surface, 'RGB'))
        self.menu.width, self.menu.height = 1024, 768
        self.menu._surface = pygame.Surface((1024, 768))
        self.menu.render(0)
        self.assertEqual(self.menu._surface.get_size(), (1024, 768))
        self.assertEqual(self.menu._menu_movie.cache_info()['frames'], 1)

    def test_replays_do_not_decode_movie_and_close_releases_archive(self):
        self.menu.render(0)
        movie = self.menu._menu_movie
        archive = movie._zip
        self.menu.screen = 'replays'
        with patch.object(movie, 'get_frame', side_effect=AssertionError('movie behind replays')):
            self.menu.render(.1)
        self.menu.close()
        self.assertIsNone(archive.fp)
        self.assertIsNone(self.menu._menu_movie)
        self.menu.close()

    def test_main_and_setup_composite_the_moving_movie_in_canvas_background(self):
        self.menu.selected_mission = 0
        for screen in ('main', 'skirmish', 'lan_host', 'lan', 'lan_join', 'lan_lobby',
                       'settings', 'campaign', 'briefing', 'saved_games'):
            with self.subTest(screen=screen):
                self.menu.screen = screen
                self.menu.t = 0
                self.menu.render(0)
                self.assertIsNotNone(self.menu._menu_movie)
                first = self.menu._surface.get_at((5, 100)).r
                self.menu.render(.6)
                self.assertGreater(self.menu._surface.get_at((5, 100)).r, first)
                self.assertLessEqual(self.menu._menu_movie.cache_info()['frames'], 2)

    def test_shared_backdrop_routes_every_menu_except_replays(self):
        self.menu.render(0)
        movie = self.menu._menu_movie
        for screen in ('splash', 'main', 'skirmish', 'lan', 'lan_host', 'lan_join',
                       'lan_lobby', 'settings', 'campaign', 'briefing', 'saved_games'):
            with self.subTest(screen=screen):
                self.menu.screen = screen
                with patch.object(movie, 'get_frame', wraps=movie.get_frame) as decode:
                    self.menu._draw_backdrop()
                decode.assert_called_once()
        self.menu.screen = 'replays'
        with patch.object(movie, 'get_frame', side_effect=AssertionError('replay decode')):
            self.menu._draw_backdrop()

    def test_disabled_cinematics_does_not_open_asset(self):
        self.menu.settings['cinematics_enabled'] = False
        self.menu.render(0)
        self.assertIsNone(self.menu._menu_movie)

    def test_missing_asset_uses_usable_static_starfield_fallback(self):
        (Path(self.temp.name) / 'assets/menu/battle.zip').unlink()
        self.menu.render(0)
        self.assertFalse(self.menu._menu_movie.available)
        self.assertEqual(self.menu.buttons[0]['action'], 'goto_main')
        self.assertIsNone(self.menu._splash_shade)
