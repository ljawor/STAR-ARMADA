"""Language packs (#93): the packs are complete, the lookups are safe, and a language
can never reach the simulation.

The last point is the one that matters: translations are applied at the drawing edges, so
two lockstep peers may run STAR ARMADA in two different languages and still agree on
`lan.precise_checksum`.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pygame

from game.net import lan
from helpers import make_game
from render import i18n, menus

ROOT = Path(__file__).resolve().parent.parent
LANG_DIR = ROOT / 'assets' / 'data' / 'lang'

#: Labels a player navigates by, per language. Identity here means the pack is a stub.
HIGH_SIGNAL_STRINGS = {
    'de': {'Settings': 'Einstellungen', 'MISSION COMPLETE': 'MISSION ABGESCHLOSSEN',
           'DELETE ALL SAVES': 'ALLE SPEICHERUNGEN LÖSCHEN', 'Language': 'Sprache',
           'MISSION FAILED': 'MISSION GESCHEITERT', 'Launch skirmish': 'Gefecht starten'},
    'pl': {'Settings': 'Ustawienia', 'MISSION COMPLETE': 'MISJA UKOŃCZONA',
           'DELETE ALL SAVES': 'USUŃ WSZYSTKIE ZAPISY', 'Language': 'Język',
           'MISSION FAILED': 'MISJA NIEUDANA', 'Launch skirmish': 'Startuj potyczkę'},
}

#: The same, for the data-driven names in a pack's `names` section.
HIGH_SIGNAL_NAMES = {
    'de': {'Shipyard': 'Werft', 'Command Station': 'Kommandostation', 'Temperate': 'Gemäßigt'},
    'pl': {'Shipyard': 'Stocznia', 'Command Station': 'Stacja dowodzenia',
           'Temperate': 'Umiarkowana'},
}


def read_pack(code):
    return json.loads((LANG_DIR / f'{code}.json').read_text(encoding='utf-8'))


def catalogue():
    data = read_pack(i18n.DEFAULT_LANGUAGE)
    names = data.pop('names')
    return data, names


class PackCoverageTests(unittest.TestCase):
    def test_every_catalogue_string_and_name_is_translated_in_every_pack(self):
        strings, names = catalogue()
        self.assertGreater(len(strings), 250)
        self.assertGreater(len(names), 50)
        for code, label in i18n.LANGUAGES:
            if code == i18n.DEFAULT_LANGUAGE:
                continue
            with self.subTest(pack=f'{code} ({label})'):
                pack = read_pack(code)
                self.assertEqual(sorted(k for k in strings if k not in pack), [])
                self.assertEqual(sorted(k for k in names if k not in pack['names']), [])

    def test_no_pack_carries_a_key_the_catalogue_lost(self):
        # A reworded UI string must not leave a translation behind that nobody can reach.
        strings, names = catalogue()
        for code, _label in i18n.LANGUAGES:
            with self.subTest(pack=code):
                pack = read_pack(code)
                self.assertEqual(
                    sorted(k for k in pack if k != 'names' and k not in strings), [])
                self.assertEqual(sorted(k for k in pack['names'] if k not in names), [])

    def test_labels_a_player_navigates_by_are_not_identity_mappings(self):
        for code, expected in HIGH_SIGNAL_STRINGS.items():
            pack = read_pack(code)
            for key, value in expected.items():
                with self.subTest(pack=code, key=key):
                    self.assertEqual(pack[key], value)
                    self.assertNotEqual(pack[key], key)

    def test_data_names_a_player_picks_by_are_not_identity_mappings(self):
        for code, expected in HIGH_SIGNAL_NAMES.items():
            pack = read_pack(code)
            for key, value in expected.items():
                with self.subTest(pack=code, key=key):
                    self.assertEqual(pack['names'][key], value)
                    self.assertNotEqual(pack['names'][key], key)


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.DEFAULT_LANGUAGE)
        i18n.set_language('de')

    def test_known_strings_translate_and_unknown_ones_pass_through(self):
        self.assertEqual(i18n.t('Settings'), 'Einstellungen')
        self.assertEqual(i18n.t('a string no pack carries'), 'a string no pack carries')

    def test_a_data_name_uses_the_same_lookup(self):
        self.assertEqual(i18n.name('Shipyard'), 'Werft')
        self.assertEqual(i18n.name('Shipyard-class Mod Hull'), 'Shipyard-class Mod Hull')

    def test_runtime_templates_are_formatted_and_a_missing_field_is_survivable(self):
        self.assertEqual(i18n.t('{outcome} — {name}', outcome=i18n.t('VICTORY'), name='Lukasz'),
                         'SIEG — Lukasz')
        # A drawing helper must never raise because a caller forgot a field.
        self.assertEqual(i18n.t('{outcome} — {name}', outcome='SIEG'), '{outcome} — {name}')

    def test_non_strings_pass_through_untouched(self):
        for value in (None, 0, 3.5, ['Settings'], {}):
            with self.subTest(value=value):
                self.assertEqual(i18n.t(value), value)
        self.assertEqual(i18n.t(''), '')

    def test_english_is_the_catalogue_so_english_looks_translate_to_themselves(self):
        i18n.set_language('en')
        self.assertEqual(i18n.language(), 'en')
        for key in ('Settings', 'MISSION COMPLETE', 'Shipyard'):
            self.assertEqual(i18n.t(key), key)

    def test_an_unknown_code_resolves_to_english_and_is_reported(self):
        self.assertEqual(i18n.set_language('klingon'), 'en')
        self.assertEqual(i18n.language(), 'en')
        self.assertEqual(i18n.t('Settings'), 'Settings')

    def test_a_pack_that_cannot_be_read_falls_back_to_english(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(i18n, 'LANG_DIR', directory), patch.object(i18n, '_loaded', {}):
                self.assertEqual(i18n.set_language('pl'), 'en')
                self.assertEqual(i18n.t('Settings'), 'Settings')
        self.assertEqual(i18n.set_language('pl'), 'pl')
        self.assertEqual(i18n.t('Settings'), 'Ustawienia')

    def test_cycle_walks_the_shipped_packs_and_wraps(self):
        self.assertEqual(i18n.cycle('en'), 'de')
        self.assertEqual(i18n.cycle('de'), 'pl')
        self.assertEqual(i18n.cycle('pl'), 'ru')
        self.assertEqual(i18n.cycle('ru'), 'en')
        self.assertEqual(i18n.cycle('ru', -1), 'pl')
        self.assertEqual(i18n.cycle('klingon'), 'en')
        self.assertEqual(i18n.cycle('en', -1), 'ru')

    def test_available_reports_only_packs_that_are_shipped(self):
        codes = [code for code, _label in i18n.available()]
        self.assertEqual(codes, ['en', 'de', 'pl', 'ru'])
        self.assertEqual(i18n.label('pl'), 'Polski')

    def test_apply_from_settings_corrects_a_language_this_build_does_not_ship(self):
        settings = {'language': 'klingon'}
        self.assertEqual(i18n.apply_from_settings(settings), 'en')
        self.assertEqual(settings['language'], 'en')
        settings = {'language': 'pl'}
        self.assertEqual(i18n.apply_from_settings(settings), 'pl')
        self.assertEqual(settings['language'], 'pl')
        self.assertEqual(i18n.apply_from_settings(None), 'en')


class SettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        saves = root / 'saves'
        saves.mkdir()
        self.saves = saves
        # Persistence constants are patched before any MenuStack exists.
        scope = patch.multiple(menus, USER_DIR=str(root), SAVES_DIR=str(saves),
                               SETTINGS_PATH=str(saves / 'settings.json'),
                               CAMPAIGN_PATH=str(saves / 'campaign.json'),
                               BALANCE_PATH=str(saves / 'balance.json'))
        scope.start()
        self.addCleanup(scope.stop)
        self.addCleanup(i18n.set_language, i18n.DEFAULT_LANGUAGE)
        if not pygame.display.get_init():
            pygame.display.init()
            self.addCleanup(pygame.display.quit)

    def make_menu(self, width=1024, height=768):
        menu = menus.MenuStack(width, height)
        self.addCleanup(menu.close)
        return menu

    def open_settings(self, menu, page):
        menu.screen = 'settings'
        menu.settings_page = page
        menu.buttons = []
        menu.render(0)
        return menu.settings_rendered_text

    def test_default_settings_carry_a_language(self):
        self.assertEqual(menus.DEFAULT_SETTINGS['language'], 'en')
        self.assertEqual(menus.load_settings()['language'], 'en')

    def test_validation_rejects_a_language_this_build_does_not_ship(self):
        for value in ('klingon', None, 7, [], True):
            with self.subTest(value=value):
                normalized = menus.validate_presentation_settings(
                    dict(menus.DEFAULT_SETTINGS, language=value))
                self.assertEqual(normalized['language'], 'en')
        self.assertEqual(menus.validate_presentation_settings(
            dict(menus.DEFAULT_SETTINGS, language='pl'))['language'], 'pl')

    def test_the_menu_applies_a_saved_language_before_the_first_frame(self):
        (self.saves / 'settings.json').write_text(json.dumps(
            dict(menus.DEFAULT_SETTINGS, language='de')), encoding='utf-8')
        menu = self.make_menu()
        self.assertEqual(menu.settings['language'], 'de')
        self.assertEqual(i18n.language(), 'de')
        self.assertIn('Einstellungen', self.open_settings(menu, 0))

    def test_the_language_row_cycles_applies_and_persists_immediately(self):
        menu = self.make_menu()
        self.open_settings(menu, 3)
        row = next(b for b in menu.buttons if b['action'] == 'cycle_language')
        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=row['rect'].center))
        self.assertEqual(menu.settings['language'], 'de')
        self.assertEqual(i18n.language(), 'de')
        self.assertTrue(menu._dirty_settings)
        texts = self.open_settings(menu, 3)
        self.assertIn('Sprache', texts)

    def test_the_language_row_names_each_pack_in_its_own_language(self):
        menu = self.make_menu()
        seen = []
        for expected in ('English', 'Deutsch', 'Polski', 'Русский'):
            texts = self.open_settings(menu, 3)
            seen.append(next(t for t in texts if t.endswith(expected + ' ›')))
            row = next(b for b in menu.buttons if b['action'] == 'cycle_language')
            menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                 pos=row['rect'].center))
        self.assertEqual(len(seen), 4)

    def test_every_settings_row_stays_reachable_now_that_a_language_page_exists(self):
        menu = self.make_menu()
        menu.screen = 'settings'
        menu.settings_page = 0
        seen = set()
        pages = 0
        while pages < 6:
            menu.buttons = []
            menu.render(0)
            for button in menu.buttons:
                payload = button.get('payload')
                if isinstance(payload, dict) and 'key' in payload:
                    seen.add(payload['key'])
                elif button['action'] == 'cycle_markers':
                    seen.add('markers')
            pages += 1
            menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
            if menu.settings_page == pages - 1 and pages > 4:
                break
        self.assertEqual(seen, set(menus.DEFAULT_SETTINGS))

    def test_the_main_menu_draws_translated_labels(self):
        # This screen renders its own labels instead of going through the classic canvas,
        # so it is the one menu that can silently stay English.
        menu = self.make_menu()
        menu.settings['language'] = 'de'
        i18n.set_language('de')
        menu.screen = 'main'
        menu.render(0)
        labels = menu.main_rendered_text
        self.assertIn('Einstellungen', labels)
        self.assertIn('Kampagne', labels)
        self.assertNotIn('Settings', labels)

    def test_the_settings_subtitle_is_translated_as_one_unit(self):
        menu = self.make_menu()
        menu.settings['language'] = 'pl'
        i18n.set_language('pl')
        texts = self.open_settings(menu, 3)
        self.assertIn('Język · Strona 4/5', texts)
        self.assertIn('Język', texts)

    def test_the_refit_block_translates_its_assembled_lines(self):
        # Lines the HUD assembles at runtime ("REFIT · LEVEL 1/5", a resource bill) are
        # not msgids, so they need a template: assert the templates are asked for.
        from render import hud as hud_module
        from render.camera import Camera
        from render.hud import HUD
        from render.input import InputController
        from game.core.vectors import Vec3
        from helpers import make_game
        from types import SimpleNamespace

        i18n.set_language('de')
        game = make_game(ai=False)
        player = game.state.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        observer = next(e for e in game.state.entities.values()
                        if e.owner == 0 and e.is_ship)
        yard = game.factory.spawn_station('shipyard', 0, observer.pos + Vec3(0, 0, 400))
        # Level 3 so the accumulated-effects line is real: at level 1 the block shows the
        # "as built" hint instead and the per-bonus templates are never reached.
        yard.upgrade_level = 3
        hud = HUD(1280, 800, game.state)
        ctrl = InputController(game.state, Camera(1280, 800), hud,
                               SimpleNamespace(flash=lambda *_: None))
        ctrl.selection = {yard.id}
        hud.buttons.clear(); hud.blocked_rects.clear(); hud.scroll_rects.clear()
        asked = []
        real_t = i18n.t

        def recorder(text, **fields):
            asked.append(text)
            return real_t(text, **fields)

        hud_module.i18n.t = recorder
        try:
            hud._right_panel(ctrl.selection, 0)
        finally:
            hud_module.i18n.t = real_t
        for template in ('REFIT · LEVEL {level}/{max}', '▲ Refit to level {level}',
                         'hull', 'shields', 'cargo', '+{count} shot/mount',
                         '+{count} convoy', '{label} +{percent}%'):
            self.assertIn(template, asked)
        self.assertEqual(real_t('hull'), 'Rumpf')
        self.assertEqual(real_t('+{count} convoy', count=1), '+1 Konvoi')
        # At level 1 there are no bonuses yet, so the block shows the "as built" hint —
        # a long sentence that must survive the wrapper's word-by-word line breaking.
        asked.clear()
        yard.upgrade_level = 1
        hud_module.i18n.t = recorder
        try:
            hud._right_panel(ctrl.selection, 0)
        finally:
            hud_module.i18n.t = real_t
        hint = 'As built · buy a level to raise hull, shields and output.'
        self.assertIn(hint, asked)
        self.assertEqual(real_t(hint),
                         'Wie gebaut · kaufe eine Stufe für mehr Rumpf, Schilde und Ertrag.')


class HudDrawingEdgeTests(unittest.TestCase):
    """The HUD's panel labels are translated in exactly one place: `HUD._label`.

    Panels hand it English literals and data names unchanged, so if that helper ever
    stops looking them up, every panel heading silently reverts to English while the
    rest of this file — which asserts on packs and on the strings panels *ask for* —
    keeps passing.
    """

    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.DEFAULT_LANGUAGE)
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        from render.hud import HUD
        game = make_game(ai=False)
        self.hud = HUD(1280, 800, game.state)

    def draw(self, text, translate=True):
        self.hud.overlay.fill((0, 0, 0))
        self.hud._label(24, 24, text, (255, 255, 255), translate=translate)
        return pygame.surfarray.array3d(self.hud.overlay).copy()

    def test_a_panel_label_is_looked_up_at_the_drawing_edge(self):
        from render import hud as hud_module
        asked = []
        real_t = hud_module.i18n.t

        def recorder(text, **fields):
            asked.append(text)
            return real_t(text, **fields)

        i18n.set_language('de')
        hud_module.i18n.t = recorder
        try:
            self.draw('Settings')
            self.assertEqual(asked, ['Settings'])
            # A caller that already holds a translated string must not be looked up
            # again: a wrapped line is not a msgid, so the second lookup could only miss.
            self.draw('Einstellungen', translate=False)
        finally:
            hud_module.i18n.t = real_t
        self.assertEqual(asked, ['Settings'])

    def test_the_translation_reaches_the_canvas_and_not_just_the_lookup(self):
        # A lookup that happens and is then dropped on the floor draws English, so
        # compare pixels: the German label must paint exactly what its own text paints.
        i18n.set_language('de')
        painted = self.draw('Settings')
        self.assertGreater(int(painted.sum()), 0, 'the label did not draw anything')
        self.assertTrue((painted == self.draw('Einstellungen', translate=False)).all(),
                        'the label was not drawn in German')
        self.assertFalse((painted == self.draw('Settings', translate=False)).all(),
                         'German and English draw identically')


class PresentationOnlyTests(unittest.TestCase):
    def test_no_simulation_module_references_the_language_layer(self):
        offenders = sorted(str(path.relative_to(ROOT))
                           for path in (ROOT / 'game').rglob('*.py')
                           if 'i18n' in path.read_text(encoding='utf-8'))
        self.assertEqual(offenders, [])

    def test_two_peers_running_different_languages_agree_on_the_ticksum(self):
        self.addCleanup(i18n.set_language, i18n.DEFAULT_LANGUAGE)
        def run(code, ticks=40):
            i18n.set_language(code)
            game = make_game(ai=False)
            for _ in range(ticks):
                game.step(1 / 30)
            return lan.precise_checksum(game)

        i18n.set_language(i18n.DEFAULT_LANGUAGE)
        baseline = make_game(ai=False)
        first = lan.precise_checksum(baseline)
        de_first = run('de', ticks=0)
        self.assertEqual(de_first, first, 'the fixture is not deterministic')
        self.assertNotEqual(run('en'), '')
        self.assertEqual(run('de'), run('pl'))
        self.assertEqual(run('en'), run('ru'))


if __name__ == '__main__':
    unittest.main()
