"""Software-Surface fleet HUD tests; never initialize a display or GL."""
import unittest

import pygame

from helpers import make_game
from render.hud import HUD


class TestFleetPanel(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.state = make_game(ai=False).state
        self.hud = HUD(1280, 800, self.state)

    def draw(self, selection):
        self.hud.overlay.fill((0, 0, 0, 0))
        self.hud.buttons = []
        self.hud.scroll_rects = []
        self.hud.blocked_rects.clear()
        self.hud._right_panel(selection, 0)
        return self.hud.buttons

    def test_open_panel_declares_data_driven_fleet_actions(self):
        self.hud.fleet_panel = True
        self.hud.fleet_formation = 'wedge'
        self.hud.fleet_commander = 'recon'
        own = {e.id for e in self.state.entities.values()
               if e.owner == 0 and e.alive and e.is_ship}
        dead = next(e for e in self.state.entities.values()
                    if e.owner == 1 and e.is_ship)
        dead.owner = 0
        dead.hull = 0
        dead.alive = False
        selection = own | {dead.id, 999999} | {
            e.id for e in self.state.entities.values() if not e.is_ship or e.owner != 0}
        before = self.state.to_dict(precise=True)
        buttons = self.draw(selection)
        self.assertEqual({b['payload']['formation'] for b in buttons
                          if b['kind'] == 'fleet_formation'},
                         set(self.hud.ds.rules['formations']))
        self.assertEqual({b['payload']['commander'] for b in buttons
                          if b['kind'] == 'fleet_commander'},
                         set(self.hud.ds.rules['commanders']) | {None})
        creates = [b for b in buttons if b['kind'] == 'fleet_create']
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0]['payload'], {
            'unit_ids': sorted(own), 'formation': 'wedge', 'commander': 'recon'})
        self.assertEqual([b['payload'] for b in buttons if b['kind'] == 'fleet_close'], [{}])
        self.assertFalse(any(b['kind'].startswith('build_') or b['kind'] == 'research'
                             for b in buttons))
        self.assertEqual(self.state.to_dict(precise=True), before)

    def test_empty_or_ineligible_selection_has_no_create_action(self):
        self.hud.fleet_panel = True
        ineligible = {e.id for e in self.state.entities.values()
                      if e.owner != 0 or not e.is_ship}
        for selection in (set(), ineligible, {999999}):
            with self.subTest(selection=selection):
                buttons = self.draw(selection)
                self.assertFalse(any(b['kind'] == 'fleet_create' for b in buttons))
                self.assertTrue(any(b['kind'] == 'fleet_close' for b in buttons))
        ship = next(e for e in self.state.entities.values() if e.owner == 0 and e.is_ship)
        self.assertTrue(any(b['kind'] == 'fleet_create' for b in self.draw({ship.id})))
        ship.alive = False
        self.assertFalse(any(b['kind'] == 'fleet_create' for b in self.draw({ship.id})))

    def test_layout_draws_readable_nonoverlapping_controls_at_both_sizes(self):
        self.hud.fleet_panel = True
        selection = {e.id for e in self.state.entities.values() if e.owner == 0 and e.is_ship}
        ship = self.state.entity(min(selection))
        ship.name_override = 'Very long ship name ' * 20
        for width, height in ((1280, 800), (1440, 900)):
            with self.subTest(size=(width, height)):
                self.hud.resize(width, height)
                labels = []
                original = self.hud._label
                def record(x, y, text, color=None, font=None):
                    used_font = font or self.hud.font
                    labels.append((str(text), pygame.Rect(x, y, *used_font.size(str(text)))))
                    original(x, y, text, color, font)
                self.hud._label = record
                try:
                    buttons = self.draw(selection)
                finally:
                    self.hud._label = original
                # Production registers the union of the independent rail/body.
                # Use that actual occlusion geometry, not the old body height.
                panels = self.hud.blocked_rects
                self.assertEqual(len(panels), 1)
                viewport = self.hud.overlay.get_rect()
                self.assertTrue(all(viewport.contains(p) for p in panels))
                self.assertEqual(sum(b['kind'] == 'hud_panel' for b in buttons), 1)
                for button in buttons:
                    self.assertTrue(any(panel.contains(button['rect']) for panel in panels))
                    # Actual painted bright glyphs, not just declared button rects.
                    rgb = pygame.surfarray.array3d(self.hud.overlay.subsurface(button['rect']))
                    self.assertGreater(int((rgb.max(axis=2) > 120).sum()), 5)
                for i, button in enumerate(buttons):
                    for other in buttons[i + 1:]:
                        self.assertFalse(button['rect'].colliderect(other['rect']))
                for text, rect in labels:
                    self.assertTrue(any(panel.contains(rect) for panel in panels), text)
                for i, (text, rect) in enumerate(labels):
                    for other_text, other_rect in labels[i + 1:]:
                        self.assertFalse(rect.colliderect(other_rect), (text, other_text))
                self.assertTrue(any(text.endswith('…') for text, _ in labels))
                self.assertEqual(self.hud.overlay.get_size(), (width, height))

    def test_idle_help_advertises_fleet_panel_key(self):
        labels = []
        original = self.hud._label
        def record(x, y, text, color=None, font=None):
            labels.append(str(text))
            original(x, y, text, color, font)
        self.hud._label = record
        try:
            self.draw(set())
            self.hud._left_panel(set(), 0)
        finally:
            self.hud._label = original
        self.assertTrue(any('F  fleet' in text for text in labels))
        self.assertTrue(any('F fleet menu' in text for text in labels))

    def test_defaults_keep_fleet_panel_closed(self):
        self.assertIs(getattr(self.hud, 'fleet_panel', None), False)
        self.assertEqual(getattr(self.hud, 'fleet_formation', None), 'line')
        self.assertIsNone(self.hud.fleet_commander)
        self.assertFalse(any(b['kind'].startswith('fleet_') for b in self.draw(set())))
