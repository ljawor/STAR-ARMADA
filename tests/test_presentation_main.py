"""Exercise production presentation dispatch without opening OpenGL."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import pygame
from test_cinematics import main_functions
from render.presentation import PresentationOverlay
from render.camera import Camera
from render.input import InputController
from game.core.manager import GameManager
from game.data.store import DataStore


class TutorialPointerTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.state = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
        self.camera = Camera(1024, 768)
        # Ground unprojection requires GL; keep the real camera/gesture handlers.
        self.camera.screen_to_world = Mock(return_value=(8000., 0., 6000.))
        self.hud = SimpleNamespace(placement=None, fleet_panel=False, buttons=[],
            minimap_rect=None, blocked_rects=[], scroll_rects=[])
        self.controller = InputController(self.state, self.camera, self.hud,
            SimpleNamespace(flash=Mock()))
        self.controller.selection = {next(e.id for e in self.state.entities.values()
                                         if e.owner == 0 and e.is_ship)}
        self.overlay = PresentationOverlay(1024, 768)
        self.overlay.panel_rects = [pygame.Rect(340, 46, 344, 137)]
        self.ns = main_functions(presentation=self.overlay, inputc=self.controller,
                                 hud=self.hud)

    def dispatch(self, kind, **values):
        event = pygame.event.Event(kind, **values)
        consumed = self.ns['handle_presentation_input'](event)
        if not consumed:
            self.ns['handle_game_input'](event)
        return consumed

    def test_right_world_drag_released_over_hint_cannot_rotate_or_order_later(self):
        self.assertFalse(self.dispatch(pygame.MOUSEBUTTONDOWN, button=3, pos=(500, 500)))
        self.assertEqual(self.controller.right_drag, (500, 500))
        self.assertTrue(self.dispatch(pygame.MOUSEBUTTONUP, button=3, pos=(400, 100)))
        self.assertFalse(self.state.command_queue, 'intercepted release must not issue an order')
        view = (self.camera.yaw, self.camera.pitch)
        selection = set(self.controller.selection)
        self.dispatch(pygame.MOUSEMOTION, pos=(540, 500), rel=(40, 0), buttons=(0, 0, 0))
        self.dispatch(pygame.MOUSEBUTTONUP, button=3, pos=(540, 500))
        self.assertEqual((self.camera.yaw, self.camera.pitch), view)
        self.assertEqual(self.controller.selection, selection)
        self.assertFalse(self.state.command_queue, 'stale release must not issue an order')
        self.assertIsNone(self.controller.right_drag)


    def test_left_world_drag_released_over_hint_cannot_select_later(self):
        self.assertFalse(self.dispatch(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 500)))
        self.dispatch(pygame.MOUSEMOTION, pos=(520, 500), rel=(20, 0), buttons=(1, 0, 0))
        self.assertTrue(self.controller.dragging)
        self.assertEqual(self.controller.drag_cur, (520, 500))
        self.assertTrue(self.dispatch(pygame.MOUSEBUTTONUP, button=1, pos=(400, 100)))
        selection = set(self.controller.selection)
        view = (self.camera.yaw, self.camera.pitch)
        self.dispatch(pygame.MOUSEMOTION, pos=(540, 500), rel=(20, 0), buttons=(0, 0, 0))
        self.dispatch(pygame.MOUSEBUTTONUP, button=1, pos=(540, 500))
        self.assertEqual(self.controller.selection, selection)
        self.assertEqual((self.camera.yaw, self.camera.pitch), view)
        self.assertFalse(self.state.command_queue)
        self.assertFalse(self.controller.dragging)
        self.assertIsNone(self.controller.drag_start)
        self.assertIsNone(self.controller.drag_cur)


    def test_hint_release_preserves_other_gesture_and_nonpointer_intent(self):
        for button in (1, 2, 3):
            with self.subTest(button=button):
                self.setUp()
                self.dispatch(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 500))
                self.dispatch(pygame.MOUSEBUTTONDOWN, button=3, pos=(500, 500))
                self.dispatch(pygame.MOUSEMOTION, pos=(520, 500), rel=(20, 0), buttons=(1, 0, 1))
                controller = self.controller
                controller.keys.add(pygame.K_w)
                controller._pending_fleet = [18]
                controller._pending_jump = (18,)
                controller._pending_ability = {'ability_id': '_repair', 'unit_ids': [18]}
                self.hud.placement = {'station_kind': 'mining_station'}
                intent = (set(controller.keys), controller._pending_fleet,
                          controller._pending_jump, controller._pending_ability,
                          self.hud.placement)
                view = (self.camera.yaw, self.camera.pitch)
                selection = set(controller.selection)
                self.assertTrue(self.dispatch(pygame.MOUSEBUTTONUP, button=button, pos=(400, 100)))
                self.assertEqual(controller.right_drag, None if button == 3 else (500, 500))
                self.assertEqual(controller.dragging, button != 1)
                self.assertEqual(controller.drag_start, None if button == 1 else (500, 500))
                self.assertEqual(controller.drag_cur, None if button == 1 else (520, 500))
                self.assertEqual((controller.keys, controller._pending_fleet,
                                  controller._pending_jump, controller._pending_ability,
                                  self.hud.placement), intent)
                self.assertEqual((self.camera.yaw, self.camera.pitch), view)
                self.assertEqual(controller.selection, selection)
                self.assertFalse(self.state.command_queue)

    def test_hint_press_and_motion_do_not_cancel_world_gestures(self):
        self.dispatch(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 500))
        self.dispatch(pygame.MOUSEBUTTONDOWN, button=3, pos=(500, 500))
        view = (self.camera.yaw, self.camera.pitch)
        self.assertTrue(self.dispatch(pygame.MOUSEMOTION, pos=(400, 100), rel=(40, 0), buttons=(1, 0, 1)))
        self.assertTrue(self.dispatch(pygame.MOUSEBUTTONDOWN, button=2, pos=(400, 100)))
        self.assertTrue(self.controller.dragging)
        self.assertEqual(self.controller.drag_start, (500, 500))
        self.assertEqual(self.controller.right_drag, (500, 500))
        self.assertEqual((self.camera.yaw, self.camera.pitch), view)
        self.assertFalse(self.state.command_queue)

    def test_unintercepted_world_gestures_still_rotate_select_and_order(self):
        self.dispatch(pygame.MOUSEBUTTONDOWN, button=3, pos=(500, 500))
        yaw = self.camera.yaw
        self.dispatch(pygame.MOUSEMOTION, pos=(540, 500), rel=(40, 0), buttons=(0, 0, 1))
        self.assertEqual(self.camera.yaw, yaw - 10)
        self.assertFalse(self.dispatch(pygame.MOUSEBUTTONUP, button=3, pos=(540, 500)))
        self.assertEqual(len(self.state.command_queue), 1)
        self.assertIsNone(self.controller.right_drag)
        self.state.command_queue.clear()
        self.dispatch(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 500))
        self.dispatch(pygame.MOUSEMOTION, pos=(540, 500), rel=(40, 0), buttons=(1, 0, 0))
        self.assertFalse(self.dispatch(pygame.MOUSEBUTTONUP, button=1, pos=(540, 500)))
        self.assertFalse(self.controller.selection)
        self.assertFalse(self.controller.dragging)
        self.assertFalse(self.state.command_queue)


class PresentationMainTests(unittest.TestCase):
    def fixture(self):
        overlay = PresentationOverlay(1024, 768)
        controller = SimpleNamespace(keys={pygame.K_w}, dragging=True,
            drag_start=(1, 1), drag_cur=(2, 2), right_drag=(3, 3),
            _pending_fleet=[1], _cancel_jump=Mock(), _cancel_ability=Mock())
        return main_functions(presentation=overlay, inputc=controller), overlay, controller

    def test_production_dispatch_opens_help_and_clears_held_gestures(self):
        ns, overlay, controller = self.fixture()
        self.assertIn('handle_presentation_input', ns,
                      'help is not routed by the production main')
        consumed = ns['handle_presentation_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
        self.assertTrue(consumed)
        self.assertTrue(overlay.help_visible)
        self.assertFalse(controller.keys)
        self.assertFalse(controller.dragging)
        self.assertIsNone(controller.right_drag)
        self.assertIsNone(controller._pending_fleet)
        controller._cancel_jump.assert_called_once()
        controller._cancel_ability.assert_called_once()
        ns['handle_presentation_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(overlay.help_visible)
        self.assertFalse(ns['handle_presentation_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s)))

    def test_help_does_not_pause_or_add_network_debt(self):
        ns, overlay, controller = self.fixture()
        calls = []
        ns.update(net_session=SimpleNamespace(advance=lambda gm, dt: calls.append(dt)), gm=object(),
                  state=SimpleNamespace(game_over=False), accumulator=4.0)
        self.assertIn('handle_presentation_input', ns)
        ns['handle_presentation_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
        ns['advance_simulation'](.033)
        self.assertEqual(calls, [1 / 30])
        self.assertFalse(ns['paused'])
        self.assertEqual(ns['accumulator'], 0.)

    def test_draw_uses_owned_viewpoint_and_registers_real_occlusion_rects(self):
        panel = pygame.Rect(20, 20, 100, 50)
        overlay = SimpleNamespace(draw=Mock(), draw_gl=Mock(), panel_rects=[panel])
        hud = SimpleNamespace(blocked_rects=[])
        ns = main_functions(presentation=overlay, inputc=object(), hud=hud,
                            state=object(), W=1024, H=768, local_player=2)
        self.assertIn('draw_presentation_overlay', ns)
        ns['draw_presentation_overlay']()
        overlay.draw.assert_called_once_with(ns['state'], ns['inputc'], width=1024,
                                            height=768, local_player=2, blocked_rects=hud.blocked_rects)
        overlay.draw_gl.assert_called_once()
        self.assertEqual(hud.blocked_rects, [panel])

    def test_cinematic_final_frame_returns_to_menu_only_for_outro(self):
        for outcome, left in ((None, False), ('MISSION COMPLETE', True), ('MISSION FAILED', True)):
            movie = SimpleNamespace(outcome=outcome, finished=True, update=Mock(), draw_gl=Mock())
            ns = main_functions(cinematic=movie, camera=SimpleNamespace(apply=Mock()),
                renderer=SimpleNamespace(draw=Mock()), W=1024, H=768,
                accumulator=3., pygame=SimpleNamespace(display=SimpleNamespace(flip=Mock())))
            ns['leave_game'] = Mock()
            ns['draw_campaign_presentation'](.033)
            self.assertEqual(ns['leave_game'].called, left)
            self.assertIsNone(ns['cinematic'])
            self.assertEqual(ns['accumulator'], 0.)


if __name__ == '__main__':
    unittest.main()
