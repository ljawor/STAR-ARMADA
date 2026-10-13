"""Real persistence regressions isolated from user campaign saves."""
import ast
import json
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from render import menus


class CampaignProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'campaign.json'
        self.patch = patch.object(menus, 'CAMPAIGN_PATH', str(self.path))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        # `render.menus` freezes its persistence paths at import, so a temporary
        # campaign path does not move SETTINGS_PATH: the language this menu draws in
        # must not come from the file the developer's own game wrote.
        self.settings = patch.object(menus, 'SETTINGS_PATH',
                                     str(Path(self.tmp.name) / 'settings.json'))
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def test_legacy_zero_keeps_first_fleet_unlocked_after_tutorial_insertion(self):
        self.path.write_text(json.dumps({'mission_index': 0}))
        self.assertEqual(menus.load_campaign_progress(), 1)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['schema_version'], 3)
        self.assertEqual(saved['unlocked_mission_ids'], ['m00_recovery_drill', 'm01_first_fleet'])
        self.assertEqual(saved['completed_mission_ids'], [])
    def test_all_legacy_unlocks_survive_and_migration_is_idempotent(self):
        for index in range(10):
            with self.subTest(index=index):
                self.path.write_text(json.dumps({'mission_index': index}))
                self.assertEqual(menus.load_campaign_progress(), index + 1)
                first = self.path.read_text()
                self.assertEqual(menus.load_campaign_progress(), index + 1)
                self.assertEqual(self.path.read_text(), first)

    def test_new_progress_roundtrip_retains_numeric_setter(self):
        self.assertEqual(menus.load_campaign_progress(), 0)
        menus.save_campaign_progress(3)
        self.assertEqual(menus.load_campaign_progress(), 3)
        menus.save_campaign_progress(1)
        self.assertEqual(menus.load_campaign_progress(), 1)

    def test_schema_ids_survive_reorder_without_unlocking_inserted_rows(self):
        self.path.write_text(json.dumps({'schema_version': 2,
            'unlocked_mission_ids': ['m00_recovery_drill', 'm01_first_fleet', 'future_mod']}))
        with patch.object(menus, '_campaign_ids', return_value=[
                'm00_recovery_drill', 'inserted', 'm01_first_fleet']):
            self.assertEqual(menus.load_campaign_progress(), 2)
            self.assertNotIn('inserted', menus.load_campaign_unlocks())
            self.assertIn('future_mod', menus.load_campaign_unlocks())

    def test_malformed_files_start_at_tutorial(self):
        for saved in ([], None, {'mission_index': -1}, {'mission_index': 'bad'},
                      {'schema_version': 2, 'unlocked_mission_ids': 'bad'}):
            self.path.write_text(json.dumps(saved))
            self.assertEqual(menus.load_campaign_progress(), 0)

    def test_missing_or_invalid_legacy_metadata_never_migrates_to_first_fleet(self):
        corrupt = ({}, {'unknown': 0}, {'schema_version': 3},
                   {'schema_version': 3, 'mission_index': 0},
                   {'schema_version': 'unknown', 'mission_index': 0},
                   {'schema_version': None, 'mission_index': 0},
                   {'schema_version': 2.0, 'unlocked_mission_ids': ['m01_first_fleet']},
                   {'mission_index': True}, {'mission_index': 0.0},
                   {'schema_version': 2, 'unlocked_mission_ids': [0]})
        for saved in corrupt:
            with self.subTest(saved=saved):
                raw = json.dumps(saved)
                self.path.write_text(raw)
                self.assertEqual(menus.load_campaign_unlocks(), {'m00_recovery_drill'})
                self.assertEqual(self.path.read_text(), raw)
        self.path.unlink()
        self.assertEqual(menus.load_campaign_unlocks(), {'m00_recovery_drill'})
        self.assertFalse(self.path.exists())

    def run_main_unlock(self, catalogue, completed='m01_first_fleet', playback=None):
        source = Path(__file__).resolve().parents[1] / 'main.py'
        tree = ast.parse(source.read_text())
        unlock = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                      and n.name == '_unlock_next_mission')
        ns = {'mission_def': {'id': completed}, 'playback': playback,
              'menu': SimpleNamespace(campaign={'missions': [{'id': mid} for mid in catalogue]})}
        exec(compile(ast.Module(body=[unlock], type_ignores=[]), str(source), 'exec'), ns)
        ns['_unlock_next_mission']()

    def test_actual_main_unlock_merges_next_id_without_catalogue_prefix(self):
        initial = ['m00_recovery_drill', 'm01_first_fleet', 'future_mod']
        catalogues = (
            ['m00_recovery_drill', 'inserted', 'm01_first_fleet', 'next', 'later'],
            ['m00_recovery_drill', 'm01_first_fleet', 'next', 'inserted', 'later'],
            ['m00_recovery_drill', 'later', 'inserted', 'm01_first_fleet', 'next'],
        )
        for catalogue in catalogues:
            for retained in (initial, initial + ['later']):
                with self.subTest(catalogue=catalogue, retained=retained):
                    self.path.write_text(json.dumps({'schema_version': 2,
                                                    'unlocked_mission_ids': retained}))
                    with patch.object(menus, '_campaign_ids', return_value=catalogue):
                        self.run_main_unlock(catalogue)
                        saved = json.loads(self.path.read_text())
                        self.assertEqual(saved['schema_version'], 3)
                        self.assertEqual(set(saved['unlocked_mission_ids']), set(retained + ['next']))
                        self.assertEqual(saved['completed_mission_ids'], ['m01_first_fleet'])
                        first = self.path.read_text()
                        self.run_main_unlock(catalogue)
                        self.assertEqual(self.path.read_text(), first)

    def test_actual_main_unlock_is_suppressed_during_replay(self):
        catalogue = ['m00_recovery_drill', 'm01_first_fleet', 'next']
        raw = json.dumps({'schema_version': 2, 'unlocked_mission_ids': [
            'm00_recovery_drill', 'm01_first_fleet', 'future_mod']})
        self.path.write_text(raw)
        self.run_main_unlock(catalogue, playback=object())
        self.assertEqual(self.path.read_text(), raw)

    def test_actual_main_unlock_finishing_the_campaign_only_marks_it_complete(self):
        catalogue = ['m00_recovery_drill', 'm01_first_fleet']
        self.run_main_unlock(catalogue, completed='m01_first_fleet')
        saved = json.loads(self.path.read_text())
        # no next mission exists, so nothing new is unlocked — the win is only recorded
        self.assertEqual(saved['unlocked_mission_ids'], ['m00_recovery_drill'])
        self.assertEqual(saved['completed_mission_ids'], ['m01_first_fleet'])

    def test_actual_main_unlock_never_records_an_unknown_mission(self):
        self.run_main_unlock(['m00_recovery_drill', 'm01_first_fleet'], completed='unknown')
        self.assertFalse(self.path.exists())

    def test_catalogue_pages_are_complete_selectable_and_do_not_overlap(self):
        import pygame
        pygame.font.init()
        for width, height in ((1024, 768), (1280, 800)):
            menu = menus.MenuStack(width, height)
            menu.screen = 'campaign'
            menus.save_campaign_progress(10)
            menu.mission_index = 10
            seen = set()
            with patch('pygame.mouse.get_pos', return_value=(0, 0)):
                for page in range(3):
                    menu.buttons = []
                    menu._screen_campaign()
                    buttons = list(menu.buttons)
                    for i, b in enumerate(buttons):
                        self.assertTrue(pygame.Rect(0, 0, width, height).contains(b['rect']))
                        self.assertFalse(any(b['rect'].colliderect(c['rect']) for c in buttons[i+1:]))
                    rows = [b for b in buttons if b['action'] == 'select_mission']
                    seen.update(b['payload'] for b in rows)
                    for row in rows:
                        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            button=1, pos=row['rect'].center))
                        self.assertEqual(menu.screen, 'briefing')
                        self.assertEqual(menu.selected_mission, row['payload'])
                        menu.screen = 'campaign'
                        menu.buttons = buttons
                    next_page = next((b for b in buttons if b['action'] == 'campaign_page'
                                      and b['payload'] == 1), None)
                    if next_page is None:
                        break
                    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                        button=1, pos=next_page['rect'].center))
            self.assertEqual(seen, set(range(11)))


if __name__ == '__main__':
    unittest.main()
