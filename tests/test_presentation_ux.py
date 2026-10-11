"""Bounded presentation UX regression tests; no GL calls in unit tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pygame
from render import menus

NEW_DEFAULTS = dict(audio_dynamic_range='standard', audio_mono=False,
                    cinematics_enabled=True, reduced_motion=False,
                    tutorial_hints=True, high_contrast_ui=False)


class SettingsTests(unittest.TestCase):
    def test_corrupt_legacy_values_do_not_crash_settings_controls(self):
        for value in (None, 'broken', [], {}, True, float('nan'), float('inf')):
            values = dict(menus.DEFAULT_SETTINGS, music_volume=value,
                          sfx_volume=value, pan_speed=value, fullscreen=value,
                          autosave=value, markers=value)
            normalized = menus.validate_presentation_settings(values)
            for key in ('music_volume', 'sfx_volume', 'pan_speed'):
                self.assertEqual(normalized[key], menus.DEFAULT_SETTINGS[key])
            self.assertEqual(normalized['markers'], 'all')
        normalized = menus.validate_presentation_settings({'music_volume': -2, 'sfx_volume': 8,
                                                            'pan_speed': 10 ** 1000})
        self.assertEqual(normalized['pan_speed'], 1)
        self.assertEqual(normalized['music_volume'], 0)
        self.assertEqual(normalized['sfx_volume'], 1)

    def test_validated_new_preferences_roundtrip_preserves_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'settings.json')
            with patch.object(menus, 'SETTINGS_PATH', path):
                self.assertEqual({k: menus.load_settings().get(k) for k in NEW_DEFAULTS}, NEW_DEFAULTS)
                values = dict(menus.DEFAULT_SETTINGS, audio_dynamic_range='night',
                              audio_mono=True, cinematics_enabled=False, reduced_motion=True,
                              tutorial_hints=False, high_contrast_ui=True, music_volume=0.32,
                              sfx_volume=0.71, pan_speed=0.8, fullscreen=True, markers='hostiles')
                menus.save_settings(values)
                self.assertEqual(menus.load_settings(), values)
                Path(path).write_text(json.dumps(dict(values, audio_mono='false',
                    cinematics_enabled=0, audio_dynamic_range='LOUD', tutorial_hints=None)))
                loaded = menus.load_settings()
                for key in ('audio_mono', 'cinematics_enabled', 'audio_dynamic_range', 'tutorial_hints'):
                    self.assertEqual(loaded[key], NEW_DEFAULTS[key])
                self.assertEqual(loaded['music_volume'], 0.32)
                Path(path).write_text('[]')
                self.assertEqual(menus.load_settings(), menus.DEFAULT_SETTINGS)

    def test_reduced_motion_freezes_menu_backdrop_and_splash_pulse(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        menu = menus.MenuStack(1024, 768)
        menu.settings['reduced_motion'] = True
        before = menu.stars.copy()
        menu.render(0.5)
        self.assertTrue((menu.stars == before).all())
        first = pygame.image.tobytes(menu._surface, 'RGB')
        menu.render(1.0)
        self.assertEqual(pygame.image.tobytes(menu._surface, 'RGB'), first)
        menu.settings['reduced_motion'] = False
        menu.render(0.1)
        self.assertFalse((menu.stars == before).all())

    def test_all_settings_reachable_contained_keyboard_and_mouse(self):
        expected = set(menus.DEFAULT_SETTINGS)
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        for width, height in ((1024, 768), (1280, 800)):
            menu = menus.MenuStack(width, height)
            menu.settings = dict(menus.DEFAULT_SETTINGS)
            menu.screen = 'settings'
            seen = set()
            for page in range(3):
                menu.render(0)
                viewport = pygame.Rect(0, 0, width, height)
                for button in menu.buttons:
                    self.assertTrue(viewport.contains(button['rect']))
                    payload = button.get('payload')
                    if isinstance(payload, dict) and 'key' in payload:
                        seen.add(payload['key'])
                    if button['action'] == 'cycle_markers':
                        seen.add('markers')
                for text, bounds in menu.settings_text_bounds:
                    self.assertTrue(viewport.contains(bounds), text)
                menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
            self.assertEqual(seen, expected)
            menu.settings_page = 2
            menu.render(0)
            menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0))
            menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertTrue(menu.settings['high_contrast_ui'])
            menu.settings_page = 1
            menu.render(0)
            button = next(b for b in menu.buttons if (b.get('payload') or {}).get('key') == 'audio_dynamic_range')
            menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
            self.assertEqual(menu.settings['audio_dynamic_range'], 'night')
            menu.settings_page = 0
            menu.render(0)
            menu.settings_focus = 0
            menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
            self.assertEqual(menu.settings['music_volume'], 0.55)


class HelpTests(unittest.TestCase):
    def test_lazy_gl_lifecycle_without_a_context(self):
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1024, 768)
        self.assertIsNone(overlay.overlay_tex)
        overlay.draw(None)
        overlay.draw_gl()  # Empty overlays must not call GL, even headlessly.
        overlay.cleanup()
        overlay.cleanup()
        self.assertIsNone(overlay.overlay_tex)

    def test_visible_overlay_rejects_missing_gl_context_without_allocating(self):
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1024, 768)
        overlay.help_visible = True
        overlay.draw(None)
        with patch('pygame.display.get_surface', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'OpenGL'):
                overlay.draw_gl()
        self.assertIsNone(overlay.overlay_tex)

    def test_hints_avoid_actual_hud_geometry(self):
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1024, 768)
        state = recovery_drill().state
        occupied = [pygame.Rect(0, 0, 1024, 34),
                    pygame.Rect(340, 46, 344, 240),
                    pygame.Rect(10, 44, 320, 623),
                    pygame.Rect(694, 44, 320, 430),
                    pygame.Rect(302, 656, 420, 50)]
        overlay.draw(state, selection=[], blocked_rects=occupied)
        self.assertTrue(overlay.panel_rects)
        self.assertFalse(any(a.colliderect(b) for a in overlay.panel_rects for b in occupied))
        for text, rect in overlay.text_bounds:
            self.assertTrue(overlay.panel_rects[0].inflate(-24, -24).contains(rect), text)

    def test_wrap_long_tokens_and_crowded_hud_omit_optional_hints(self):
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1024, 768)
        text = 'SUPPORT_' * 90
        lines = overlay._wrap(text, overlay.font, 180)
        self.assertEqual(''.join(lines), text)
        self.assertTrue(all(overlay.font.size(line)[0] <= 180 for line in lines))
        overlay.draw(recovery_drill().state, selection=[],
                     blocked_rects=[pygame.Rect(0, 0, 1024, 768)])
        self.assertEqual(overlay.panel_rects, [])
        self.assertEqual(overlay.text_bounds, [])

    def test_f1_help_modal_paged_legible_settings_and_resize(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('render.presentation'), 'presentation overlay missing')
        from render.presentation import PresentationOverlay
        overlay = PresentationOverlay(1024, 768)
        self.assertFalse(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b)))
        self.assertTrue(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1)))
        self.assertTrue(overlay.help_visible)
        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1, repeat=True))
        self.assertTrue(overlay.help_visible)
        overlay.draw(None)
        self.assertTrue(any('Select' in t for t, r in overlay.text_bounds))
        for text, rect in overlay.text_bounds:
            self.assertTrue(overlay.panel_rects[0].inflate(-24, -24).contains(rect), text)
        overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
        overlay.draw(None, width=1280, height=800)
        self.assertTrue(any('Life support' in t for t, r in overlay.text_bounds))
        before = pygame.image.tobytes(overlay.surface, 'RGBA')
        overlay.apply_settings(dict(high_contrast_ui=True, tutorial_hints=False))
        overlay.draw(None)
        self.assertNotEqual(pygame.image.tobytes(overlay.surface, 'RGBA'), before)
        self.assertTrue(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)))
        self.assertFalse(overlay.help_visible)
        overlay.draw(None)
        self.assertEqual(overlay.text_bounds, [])


def recovery_drill():
    from game.core.manager import GameManager
    from game.data.store import DataStore
    ds = DataStore.get()
    definition = next(m for m in ds.campaign['missions'] if m['id'] == 'm00_recovery_drill')
    gm = GameManager.start_mission(ds.maps[definition['map']], definition)
    gm.step(1 / 30)
    return gm


class TutorialTests(unittest.TestCase):
    def test_neutral_selection_does_not_offer_enemy_boarding(self):
        from render.presentation import PresentationOverlay
        state = recovery_drill().state
        planet = next(e for e in state.entities.values() if e.data_id == 'trade')
        overlay = PresentationOverlay(1024, 768)
        text = ' '.join(overlay.tutorial_paragraphs(state, [planet.id]))
        self.assertNotIn('click this detected hull', text)
        self.assertNotIn('target shields', text)

    def test_empty_transport_requires_recovery_not_loading(self):
        from render.presentation import PresentationOverlay
        state = recovery_drill().state
        transport = next(e for e in state.entities.values() if 'crew_transport' in e.data_id)
        transport.crew = 0
        text = ' '.join(PresentationOverlay(1024, 768).tutorial_paragraphs(state, [transport.id]))
        self.assertIn('Deliver passengers', text)
        self.assertNotIn('L: load', text)

    def test_actual_drill_selection_context_visibility_settings_and_readonly(self):
        from render.presentation import PresentationOverlay
        gm = recovery_drill()
        state = gm.state
        overlay = PresentationOverlay(1024, 768)
        initial = json.dumps(state.to_dict(precise=True), sort_keys=True)
        overlay.draw(state, selection=[])
        self.assertTrue(any('Select' in t for t, r in overlay.text_bounds))
        cruiser = next(e for e in state.entities.values() if e.owner == 0 and 'cruiser' in e.data_id)
        transport = next(e for e in state.entities.values() if 'crew_transport' in e.data_id)
        frigate = next(e for e in state.entities.values() if e.data_id == 'imperial_frigate')
        target = next(e for e in state.entities.values() if e.data_id == 'syndicate_corvette')
        overlay.draw(state, selection=[cruiser.id])
        self.assertTrue(any('B' in t and 'shields' in t for t, r in overlay.text_bounds))
        overlay.draw(state, selection=[transport.id])
        self.assertTrue(any('L:' in t for t, r in overlay.text_bounds))
        overlay.draw(state, selection=[frigate.id])
        text = ' '.join(t for t, r in overlay.text_bounds)
        self.assertIn('equipment', text.lower())
        self.assertIn('crew', text)
        self.assertEqual(json.dumps(state.to_dict(precise=True), sort_keys=True), initial)
        # Explicit fixture progression, not a human tutorial-completion claim.
        gm.mission.objectives[0]['done'] = True
        gm.mission.objectives[1]['active'] = True
        transport.crew_cargo = 4
        overlay.draw(state, selection=[transport.id])
        self.assertTrue(any('R:' in t for t, r in overlay.text_bounds))
        with patch.object(state.__class__, 'can_see', return_value=False):
            overlay.draw(state, selection=[target.id])
            hidden_text = ' '.join(t for t, r in overlay.text_bounds)
            target.crew = 987
            target.systems['life_support'].hp = 1
            overlay.draw(state, selection=[target.id])
            self.assertEqual(' '.join(t for t, r in overlay.text_bounds), hidden_text)
            self.assertNotIn('987', hidden_text)
        frigate.systems['life_support'].hp = frigate.systems['life_support'].max_hp * .1
        overlay.draw(state, selection=[frigate.id])
        self.assertTrue(any('repair' in t.lower() for t, r in overlay.text_bounds))
        overlay.apply_settings({'tutorial_hints': False})
        overlay.draw(state, selection=[transport.id])
        self.assertEqual(overlay.text_bounds, [])
        overlay.apply_settings({'tutorial_hints': True})
        state.mission_id = 'm01_first_fleet'
        overlay.draw(state, selection=[transport.id])
        self.assertEqual(overlay.text_bounds, [])


if __name__ == '__main__':
    unittest.main()
