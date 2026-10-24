"""Menu events use software surfaces: no display or OpenGL required."""
import os
import tempfile
import unittest
from unittest.mock import patch
import pygame
from render.menus import MenuStack, MenuResult


def press(menu, action, payload=None, release=True):
    button = next(b for b in menu.buttons if b['action'] == action
                  and (payload is None or b['payload'] == payload))
    pos = button['rect'].center
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    if release:
        menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    return pos


class SkirmishMenuTests(unittest.TestCase):
    def setUp(self):
        mouse = patch('pygame.mouse.get_pos', return_value=(0, 0))
        mouse.start()
        self.addCleanup(mouse.stop)
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        # `render.menus` freezes its persistence paths at import, so a temporary USER_DIR
        # does not move SETTINGS_PATH: pin the settings file itself, or this menu draws in
        # whatever language the developer's own game last saved.
        scope = patch('render.menus.SETTINGS_PATH',
                      os.path.join(holder.name, 'settings.json'))
        scope.start()
        self.addCleanup(scope.stop)
        self.menu = MenuStack(1280, 800)
        self.menu.screen = 'main'
        self.menu.render(0)

    def open_setup(self):
        press(self.menu, 'start_skirmish')
        self.menu.render(0)

    def test_every_active_slot_including_you_cycles_team_once_per_gesture(self):
        self.open_setup()
        press(self.menu, 'skirmish_map', 'skirmish03')
        self.menu.render(0)
        for _ in range(2):
            press(self.menu, 'skirmish_ai', 1)
            self.menu.render(0)
        original_colors = self.menu.skirmish_options['colors'][:]
        original_factions = self.menu.skirmish_options['factions'][:]
        controls = [b for b in self.menu.buttons if b['action'] == 'skirmish_team']
        self.assertEqual([b['payload'] for b in controls], [0, 1, 2, 3])
        for slot in range(4):
            for _ in range(4):
                old = self.menu.skirmish_options['teams'][slot]
                pos = press(self.menu, 'skirmish_team', slot, release=False)
                self.menu.render(0)
                self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
                self.assertEqual(self.menu.skirmish_options['teams'][slot], (old + 1) % 4)
                self.assertIn(f'Team {(old + 1) % 4 + 1}', ' '.join(self.menu.skirmish_rendered_text))
        self.assertEqual(self.menu.skirmish_options['colors'], original_colors)
        self.assertEqual(self.menu.skirmish_options['factions'], original_factions)

    def test_roster_explains_relative_allies_and_enemies_when_your_team_changes(self):
        self.open_setup()
        press(self.menu, 'skirmish_map', 'skirmish03')
        self.menu.render(0)
        press(self.menu, 'skirmish_ai', 1)
        self.menu.render(0)
        press(self.menu, 'skirmish_team', 0)
        self.menu.render(0)
        rendered = ' '.join(self.menu.skirmish_rendered_text)
        self.assertIn('You', rendered)
        self.assertIn('AI 1 · Ally', rendered)
        self.assertIn('AI 2 · Enemy', rendered)
        self.assertIn('Same team = allies', rendered)
        self.assertIn('share vision, not control', rendered)
        self.assertIn('AI PLAYERS', rendered)
        self.assertNotIn('FREE FOR ALL', rendered)
        self.assertEqual([b['payload'] for b in self.menu.buttons if b['action'] == 'skirmish_team'], [0, 1, 2])

    def test_all_allied_launch_is_blocked_with_clear_recoverable_error(self):
        self.open_setup()
        press(self.menu, 'skirmish_team', 0)  # Team 2 matches AI 1.
        press(self.menu, 'launch_skirmish')  # No intervening render.
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.assertIsNone(self.menu.result_payload)
        self.assertEqual(self.menu.screen, 'skirmish')
        self.assertIn('two different teams', self.menu.skirmish_notice)
        self.assertIn('enemy', self.menu.skirmish_notice)
        self.menu.render(0)
        self.assertIn('two different teams', ' '.join(self.menu.skirmish_rendered_text))
        press(self.menu, 'skirmish_team', 1)
        press(self.menu, 'launch_skirmish')
        self.assertEqual(self.menu.result, MenuResult.START_SKIRMISH)
        payload = self.menu.result_payload
        assert isinstance(payload, dict)
        self.assertEqual(payload['teams'], [1, 2, 2, 3])
        self.menu.skirmish_options['teams'][0] = 0
        self.assertEqual(payload['teams'][0], 1)

    def test_roster_faction_names_remain_fully_readable_beside_team_controls(self):
        self.open_setup()
        for faction in ('imperial', 'rebel', 'confederacy', 'syndicate'):
            self.menu.skirmish_options['factions'][0] = faction
            self.menu.render(0)
            name = self.menu.skirmish_store.factions[faction].display_name
            self.assertIn(name + ' ›', self.menu.skirmish_rendered_text)

    def test_eight_public_map_cards_with_capacity_and_preview(self):
        self.open_setup()
        cards = [b for b in self.menu.buttons if b['action'] == 'skirmish_map']
        self.assertEqual([b['payload'] for b in cards],
                         [f'skirmish0{i}' for i in range(1, 9)])
        self.assertEqual([self.menu.skirmish_capacity(b['payload']) for b in cards],
                         [2, 3, 4, 4, 8, 2, 2, 3])
        self.assertEqual(len(self.menu.skirmish_preview_starts), 2)
        self.assertTrue(self.menu.skirmish_text_bounds)

    def test_ai_count_map_clamp_and_inactive_choices_retained(self):
        self.open_setup()
        press(self.menu, 'skirmish_map', 'skirmish03')
        self.menu.render(0)
        for _ in range(4):
            press(self.menu, 'skirmish_ai', 1)
            self.menu.render(0)
        self.assertEqual(self.menu.skirmish_options['ai_count'], 3)
        press(self.menu, 'skirmish_team', 3)
        saved_teams = self.menu.skirmish_options['teams'][:]
        saved = self.menu.skirmish_options['colors'][:]
        press(self.menu, 'skirmish_map', 'skirmish02')
        self.assertEqual(self.menu.skirmish_options['ai_count'], 2)
        self.assertIn('capacity', self.menu.skirmish_notice.lower())
        self.menu.render(0)
        press(self.menu, 'skirmish_map', 'skirmish01')
        self.menu.render(0)
        press(self.menu, 'skirmish_ai', -1)
        self.assertEqual(self.menu.skirmish_options['ai_count'], 1)
        self.assertEqual(self.menu.skirmish_options['colors'], saved)
        self.assertEqual(self.menu.skirmish_options['teams'], saved_teams)
        self.menu.render(0)
        self.assertEqual([b['payload'] for b in self.menu.buttons if b['action'] == 'skirmish_team'], [0, 1])

    def test_color_cycle_swaps_duplicate_and_up_never_cycles_again(self):
        from game.core.skirmish import PLAYER_COLORS
        self.open_setup()
        press(self.menu, 'skirmish_map', 'skirmish03')
        self.menu.render(0)
        for _ in range(2):
            press(self.menu, 'skirmish_ai', 1)
            self.menu.render(0)
        keys = list(PLAYER_COLORS)
        original = self.menu.skirmish_options['colors'][:]
        pos = press(self.menu, 'skirmish_color', 0, release=False)
        self.assertEqual(self.menu.skirmish_options['colors'][0], keys[1])
        self.assertEqual(self.menu.skirmish_options['colors'][1], original[0])
        self.menu.render(0)
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
        self.assertEqual(self.menu.skirmish_options['colors'][0], keys[1])
        for slot in range(4):
            for _ in range(12):
                press(self.menu, 'skirmish_color', slot)
                self.menu.render(0)
                self.assertEqual(len(set(self.menu.skirmish_options['colors'])), 4)

    def test_reactivated_slot_gets_unique_color_without_changing_active_choices(self):
        self.open_setup()
        # Green belongs to inactive AI 2; YOU may use it for a two-player game.
        for _ in range(2):
            press(self.menu, 'skirmish_color', 0)
        active = self.menu.skirmish_options['colors'][:2]
        press(self.menu, 'skirmish_map', 'skirmish03')
        self.menu.render(0)
        press(self.menu, 'skirmish_ai', 1)
        self.assertEqual(self.menu.skirmish_options['colors'][:2], active)
        self.assertEqual(len(set(self.menu.skirmish_options['colors'][:3])), 3)

    def test_launch_reads_current_choices_and_returns_private_snapshot_once(self):
        self.open_setup()
        press(self.menu, 'skirmish_faction', 0)
        press(self.menu, 'skirmish_difficulty')
        self.assertEqual(self.menu.result, MenuResult.NONE)
        pos = press(self.menu, 'launch_skirmish')
        self.assertEqual(self.menu.result, MenuResult.START_SKIRMISH)
        payload = self.menu.result_payload
        assert isinstance(payload, dict)
        self.assertEqual(payload['factions'][0], 'rebel')
        self.assertEqual(payload['ai_difficulty'], 'hard')
        self.assertEqual(set(payload), {'map_id', 'ai_count', 'colors', 'factions', 'ai_difficulty', 'teams'})
        self.assertEqual(payload['teams'], [0, 1, 2, 3])
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        self.assertIs(self.menu.result_payload, payload)
        self.menu.skirmish_options['colors'][0] = 'pink'
        self.menu.skirmish_options['factions'][0] = 'syndicate'
        self.assertNotEqual(payload['colors'], self.menu.skirmish_options['colors'])
        self.assertNotEqual(payload['factions'], self.menu.skirmish_options['factions'])

    def test_escape_and_back_clear_stale_launch_targets(self):
        self.open_setup()
        launch = next(b for b in self.menu.buttons if b['action'] == 'launch_skirmish')['rect'].center
        self.menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(self.menu.screen, 'main')
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=launch, button=1))
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.menu.render(0)
        self.open_setup()
        press(self.menu, 'goto_main')
        self.assertEqual(self.menu.buttons, [])

    def test_selected_map_name_and_description_are_fully_readable(self):
        self.open_setup()
        for map_id in ('skirmish01', 'skirmish02', 'skirmish03', 'skirmish04'):
            press(self.menu, 'skirmish_map', map_id)
            self.menu.render(0)
            data = self.menu.skirmish_store.maps[map_id]
            rendered = ' '.join(self.menu.skirmish_rendered_text)
            self.assertIn(data['name'], rendered)
            self.assertIn(data['description'], rendered)

    def test_cycles_cover_all_factions_and_difficulties_once_per_press(self):
        self.open_setup()
        for faction in ('rebel', 'confederacy', 'syndicate', 'imperial'):
            pos = press(self.menu, 'skirmish_faction', 0, release=False)
            self.menu.render(0)
            self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
            self.assertEqual(self.menu.skirmish_options['factions'][0], faction)
        for difficulty in ('hard', 'easy', 'normal'):
            pos = press(self.menu, 'skirmish_difficulty', release=False)
            self.menu.render(0)
            self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
            self.assertEqual(self.menu.skirmish_options['ai_difficulty'], difficulty)

    def test_settings_toggle_down_up_remains_single_action(self):
        self.menu.screen = 'settings'
        self.menu.render(0)
        old = self.menu.settings['autosave']
        pos = press(self.menu, 'toggle', {'key': 'autosave'}, release=False)
        self.menu.render(0)
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
        self.assertEqual(self.menu.settings['autosave'], not old)

    def test_skirmish_opens_setup_without_launching(self):
        press(self.menu, 'start_skirmish')
        self.assertEqual(self.menu.screen, 'skirmish')
        self.assertEqual(self.menu.result, MenuResult.NONE)
        self.assertIsNone(self.menu.result_payload)
        self.assertEqual(self.menu.buttons, [])


if __name__ == '__main__':
    unittest.main()
