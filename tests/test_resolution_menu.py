"""Resolution control: real Settings events, persisted choice and truthful running mode."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pygame
import game.core
from game.data.store import DataStore
from render import menus, i18n


class ResolutionMenuTests(unittest.TestCase):
    def setUp(self):
        previous_store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous_store)
        language = i18n.language()
        self.addCleanup(i18n.set_language, language)
        if not pygame.display.get_init():
            pygame.display.init()
            self.addCleanup(pygame.display.quit)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        scope = patch.multiple(menus, USER_DIR=str(self.root), SAVES_DIR=str(self.root / 'saves'),
                               SETTINGS_PATH=str(self.root / 'saves/settings.json'),
                               CAMPAIGN_PATH=str(self.root / 'saves/campaign.json'),
                               BALANCE_PATH=str(self.root / 'saves/balance.json'))
        scope.start()
        self.addCleanup(scope.stop)

    def menu(self, size):
        menu = menus.MenuStack(*size)
        self.addCleanup(menu.close)
        menu.settings.update(reduced_motion=True, cinematics_enabled=False)
        menu.screen = 'settings'
        return menu

    def test_mouse_and_natural_keyboard_selection_persists_without_changing_live_mode(self):
        for size in ((800, 600), (1280, 800), (1920, 1080)):
            with self.subTest(size=size):
                menu = self.menu(size)
                menu.settings['resolution'] = 'auto'
                display = Mock()
                display.get_size.return_value = (1600, 900)
                display.get_flags.return_value = 0
                with patch.object(pygame.display, 'get_surface', return_value=display), \
                        patch.object(pygame.display, 'set_mode') as set_mode:
                    menu.render(0)
                    controls = [b for b in menu.buttons if isinstance(b.get('payload'), dict)
                                and 'key' in b['payload']]
                    rows = [b for b in controls if b['payload']['key'] == 'resolution']
                    self.assertEqual(len(rows), 1, 'resolution selector is missing')
                    row = rows[0]
                    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                       button=1, pos=row['rect'].center))
                    self.assertEqual(menu.settings['resolution'], '1280x720')
                    # Reach the row through actual Tab events, not direct focus assignment.
                    for _ in range(controls.index(row) + 1):
                        menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0))
                    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
                    self.assertEqual(menu.settings['resolution'], '1280x800')
                    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
                    self.assertEqual(menu.settings['resolution'], '1280x720')
                    menu.apply_pending()
                    self.assertEqual(menus.load_settings()['resolution'], '1280x720')
                    menu.render(0)
                    text = ' '.join(menu.settings_rendered_text)
                    self.assertIn('1600 × 900', text)
                    self.assertIn('1280 × 720', text)
                    self.assertIn('restarting', text)
                    set_mode.assert_not_called()
                    self.assertEqual(menu.result, menus.MenuResult.NONE)

    def test_saved_resolution_is_validated_without_losing_other_preferences(self):
        path = Path(menus.SETTINGS_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        for bad in (None, [], {}, True, '0x0', '99999x99999', '1920X1080'):
            with self.subTest(bad=bad):
                path.write_text(json.dumps({'resolution': bad, 'music_volume': 0.13,
                                           'mod_option': 17}), encoding='utf-8')
                loaded = menus.load_settings()
                self.assertEqual(loaded['resolution'], 'auto')
                self.assertEqual(loaded['music_volume'], 0.13)
                self.assertEqual(loaded['mod_option'], 17)
        path.write_text(json.dumps({'resolution': '1920x1080', 'fullscreen': True}), encoding='utf-8')
        loaded = menus.load_settings()
        self.assertEqual(loaded['resolution'], '1920x1080')
        self.assertTrue(loaded['fullscreen'])

    def test_actual_resolution_and_mode_are_localized_and_clear_of_controls(self):
        for size in ((800, 600), (1280, 800), (1920, 1080)):
            menu = self.menu(size)
            menu.settings['resolution'] = '2560x1440'  # pending; must not masquerade as current
            for code, _label in i18n.LANGUAGES:
                i18n.set_language(code)
                for fullscreen in (False, True):
                    with self.subTest(size=size, code=code, fullscreen=fullscreen):
                        display = Mock()
                        display.get_size.return_value = (1920, 1080)
                        display.get_flags.return_value = pygame.FULLSCREEN if fullscreen else 0
                        with patch.object(pygame.display, 'get_surface', return_value=display):
                            menu.render(0)
                        expected = i18n.t('Current resolution: {width} × {height} · {mode}',
                                          width=1920, height=1080,
                                          mode=i18n.t('Fullscreen' if fullscreen else 'Windowed'))
                        self.assertIn(expected, menu.settings_rendered_text)
                        bounds = [rect for _text, rect in menu.settings_text_bounds if rect.w]
                        window = pygame.Rect(0, 0, *size)
                        self.assertTrue(all(window.contains(rect) for rect in bounds))
                        self.assertTrue(all(window.contains(b['rect']) for b in menu.buttons))
                        for index, rect in enumerate(bounds):
                            self.assertFalse(any(rect.colliderect(other) for other in bounds[index + 1:]),
                                             (code, rect, bounds))


if __name__ == '__main__':
    unittest.main()
