import json
import re
import string
import unittest
from collections import Counter

import pygame

from render import clean_classic, i18n, menus
import test_i18n
from test_i18n import read_pack


class RussianPackTests(unittest.TestCase):
    def test_russian_is_registered_with_its_native_name(self):
        self.assertIn(('ru', 'Русский'), i18n.available())
        self.assertEqual(i18n.label('ru'), 'Русский')

    def test_complete_catalogue_has_no_stale_keys_or_changed_format_fields(self):
        english = read_pack('en')
        russian = read_pack('ru')
        self.assertEqual(set(russian), set(english))
        self.assertEqual(set(russian['names']), set(english['names']))
        formatter = string.Formatter()
        for section in (None, 'names'):
            source = english if section is None else english[section]
            target = russian if section is None else russian[section]
            for key, value in source.items():
                if key == 'names':
                    continue
                with self.subTest(section=section, key=key):
                    self.assertIsInstance(target[key], str)
                    self.assertTrue(target[key].strip())
                    fields = lambda text: Counter((field, spec, conversion)
                        for _, field, spec, conversion in formatter.parse(text)
                        if field is not None)
                    self.assertEqual(fields(value), fields(target[key]))
                    self.assertEqual(value.count('\n'), target[key].count('\n'))
                    invariant = {'APPDATA', 'Application Support', 'RGB', 'RGBA',
                                 'STAR ARMADA', '▲', '▼', '{label} +{percent}%',
                                 '{outcome} — {name}'}
                    if key not in invariant:
                        self.assertRegex(target[key], '[А-Яа-яЁё]')

    def test_high_signal_labels_and_names_are_russian(self):
        pack = read_pack('ru')
        for key, expected in {'Settings': 'Настройки', 'Language': 'Язык',
                              'MISSION COMPLETE': 'МИССИЯ ВЫПОЛНЕНА',
                              'MISSION FAILED': 'МИССИЯ ПРОВАЛЕНА',
                              'Launch skirmish': 'Начать схватку',
                              'DELETE ALL SAVES': 'УДАЛИТЬ ВСЕ СОХРАНЕНИЯ'}.items():
            self.assertEqual(pack[key], expected)
        self.assertEqual(pack['names']['Shipyard'], 'Верфь')
        self.assertEqual(pack['names']['Command Station'], 'Командная станция')

    def test_cyrillic_glyphs_have_real_distinct_pixels(self):
        owned = not pygame.font.get_init()
        if owned:
            pygame.font.init()
            self.addCleanup(pygame.font.quit)
            self.addCleanup(clean_classic.font.cache_clear)
        font = clean_classic.font(24)
        pack = read_pack('ru')
        alphabet = sorted(set(re.findall('[А-Яа-яЁё]', json.dumps(pack, ensure_ascii=False))))
        self.assertGreaterEqual(len(alphabet), 60)
        missing = pygame.image.tobytes(font.render('\U0010ffff', True, 'white'), 'RGBA')
        bitmaps = []
        for letter in alphabet:
            with self.subTest(letter=letter):
                surface = font.render(letter, True, 'white')
                bitmap = pygame.image.tobytes(surface, 'RGBA')
                self.assertNotEqual(bitmap, missing)
                self.assertGreater(int(pygame.surfarray.array_alpha(surface).sum()), 0)
                metrics = font.metrics(letter)[0]
                self.assertIsNotNone(metrics)
                self.assertGreater(metrics[1] - metrics[0], 0)
                bitmaps.append(bitmap)
        self.assertEqual(len(set(bitmaps)), len(alphabet))


class RussianSettingsTests(unittest.TestCase):
    make_menu = test_i18n.SettingsIntegrationTests.make_menu
    open_settings = test_i18n.SettingsIntegrationTests.open_settings

    def setUp(self):
        test_i18n.SettingsIntegrationTests.setUp(self)
        if not pygame.font.get_init():
            pygame.font.init()
            self.addCleanup(pygame.font.quit)
            self.addCleanup(clean_classic.font.cache_clear)

    def test_natural_click_cycle_saves_russian_and_restores_before_drawing(self):
        menu = self.make_menu()
        for expected in ('de', 'pl', 'ru'):
            self.open_settings(menu, 3)
            row = next(b for b in menu.buttons if b['action'] == 'cycle_language')
            menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                 pos=row['rect'].center))
            menu.apply_pending()
            self.assertEqual(menu.settings['language'], expected)
            self.assertEqual(i18n.language(), expected)
        self.assertIn('Язык · Страница 4/5', self.open_settings(menu, 3))
        self.assertIn('Русский ›', menu.settings_rendered_text)
        menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(json.loads((self.saves / 'settings.json').read_text(encoding='utf-8'))['language'], 'ru')
        menu.close()
        restored = self.make_menu()
        self.assertEqual(restored.settings['language'], 'ru')
        self.assertEqual(i18n.language(), 'ru')
        restored.render(0)
        start = next(b for b in restored.buttons if b['action'] == 'goto_main')
        restored.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                pos=start['rect'].center))
        restored.render(0)
        self.assertIn('Настройки', restored.main_rendered_text)
        self.assertIn('Кампания', restored.main_rendered_text)
        self.assertNotIn('Settings', restored.main_rendered_text)

    def test_nested_fixture_cleanup_preserves_active_shared_display(self):
        self.assertTrue(pygame.display.get_init())
        surface = pygame.display.get_surface()
        if surface is None:
            surface = pygame.display.set_mode((320, 240))
        font = clean_classic.font(24)
        fixture = RussianSettingsTests('test_natural_click_cycle_saves_russian_and_restores_before_drawing')
        try:
            fixture.setUp()
            menu = fixture.make_menu()
            menu.render(0)
        finally:
            fixture.doCleanups()
        self.assertTrue(pygame.display.get_init(), 'nested fixture quit the shared display')
        self.assertIs(pygame.display.get_surface(), surface)
        self.assertIs(clean_classic.font(24), font)
        surface.blit(font.render('Русский', True, 'white'), (0, 0))
        pygame.display.flip()
        pygame.event.pump()
        # The outer fixture must still be able to use its menu lifecycle.
        self.make_menu().render(0)

    def test_fixture_cleanup_preserves_live_shared_fonts(self):
        font = clean_classic.font(24)
        fixture = RussianSettingsTests('test_natural_click_cycle_saves_russian_and_restores_before_drawing')
        fixture.setUp()
        fixture.make_menu()
        fixture.doCleanups()
        glyph_fixture = RussianPackTests('test_cyrillic_glyphs_have_real_distinct_pixels')
        glyph_fixture.test_cyrillic_glyphs_have_real_distinct_pixels()
        glyph_fixture.doCleanups()
        self.assertIs(clean_classic.font(24), font)
        self.assertGreater(font.render('Русский', True, 'white').get_width(), 0)


if __name__ == '__main__':
    unittest.main()
