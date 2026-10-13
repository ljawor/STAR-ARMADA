"""Independent HUD collapse through production input, without GL upload."""
import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from render.hud import HUD
from render.camera import Camera
from render.input import InputController


class CollapsibleHUDTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud,
                                    SimpleNamespace(flash=lambda *_: None))
        self.hud.mission_progress = ['[ ] Secure the colony']
        self.hud.mission_name = 'Mission'

    def draw(self):
        self.hud.buttons.clear(); self.hud.blocked_rects.clear(); self.hud.scroll_rects.clear()
        self.hud._left_panel(self.ctrl.selection, 0)
        self.hud._right_panel(self.ctrl.selection, 0)
        self.hud._mission_panel(0)

    def click(self, point, button=1):
        self.ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=point))
        self.ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=point))

    def test_independent_collapse_restore_removes_world_occlusion(self):
        before = self.st.to_dict(precise=True)
        self.draw()
        controls = [b for b in self.hud.buttons if b['kind'] == 'hud_panel']
        self.assertEqual({b['payload']['panel'] for b in controls}, {'left', 'right', 'mission'})
        for control in controls:
            key = control['payload']['panel']
            self.click(control['rect'].center)
            self.assertTrue(self.hud.minimized[key])
            self.assertFalse(self.ctrl.dragging)
        self.draw()
        self.assertFalse(any(r.collidepoint((100, 110)) for r in self.hud.blocked_rects))
        self.assertEqual(len(self.hud.buttons), 3)
        for control in list(self.hud.buttons): self.click(control['rect'].center)
        self.assertFalse(any(self.hud.minimized.values()))
        self.assertEqual(before, self.st.to_dict(precise=True))


    def test_resize_selection_changes_keep_minimized_state_and_invalidate_controls(self):
        self.draw()
        left = next(b for b in self.hud.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == 'left')
        self.click(left['rect'].center)
        self.hud.resize(1024, 768)
        self.ctrl.selection = {e.id for e in self.st.entities.values() if e.owner == 0 and e.is_ship}
        self.draw()
        self.assertTrue(self.hud.minimized['left'])
        self.assertTrue(all(pygame.Rect(0, 0, 1024, 768).contains(b['rect']) for b in self.hud.buttons))
        old = next(b for b in self.hud.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == 'right')
        self.hud.resize(1280, 800)
        self.click(old['rect'].center)
        self.assertFalse(self.hud.minimized['right'], 'resize must retire old controls')

    def test_minimized_panel_stale_wheel_does_not_scroll_or_zoom(self):
        from unittest.mock import patch
        constructor = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_construction)
        self.ctrl.selection = {constructor.id}
        self.draw()
        region, key = self.hud.scroll_rects[0]
        control = next(b for b in self.hud.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == 'right')
        self.click(control['rect'].center)
        old_scroll = dict(self.hud.scroll)
        old_distance = self.ctrl.camera.distance
        with patch('pygame.mouse.get_pos', return_value=region.center):
            self.ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
        self.assertEqual(old_scroll, self.hud.scroll)
        self.assertEqual(old_distance, self.ctrl.camera.distance)
        self.draw()
        self.assertFalse(self.hud.scroll_rects)

    def test_collapse_button_label_is_not_truncated(self):
        labels = []
        original = self.hud._label
        def label(x, y, text, *args, **kwargs):
            labels.append(text)
            original(x, y, text, *args)
        self.hud._label = label
        self.draw()
        self.assertEqual(labels.count('Minimize'), 3)

    def test_right_click_and_world_drag_release_over_hud_are_consumed(self):
        self.draw()
        self.ctrl.selection = {next(e.id for e in self.st.entities.values() if e.owner == 0 and e.is_ship)}
        self.ctrl.camera.screen_to_world = lambda *_: (0, 0, 0)
        self.click((100, 100), 3)
        self.assertFalse(self.st.command_queue)
        self.assertIsNone(self.ctrl.right_drag)
        self.ctrl.dragging = True
        self.ctrl.drag_start = (600, 500)
        selected = set(self.ctrl.selection)
        self.ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(100, 100)))
        self.assertFalse(self.ctrl.dragging)
        self.assertEqual(selected, self.ctrl.selection)


if __name__ == '__main__': unittest.main()
