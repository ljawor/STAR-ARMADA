"""Keyboard regressions exercised through real pygame events and sim state."""
import unittest
from types import SimpleNamespace

import pygame

from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.input import InputController


class InputControlsTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        self.state = self.gm.state
        self.camera = Camera(1280, 800)
        self.hud = SimpleNamespace(placement=None, fleet_panel=False,
                                   fleet_formation='line', fleet_commander=None,
                                   buttons=[], minimap_rect=None, scroll_rects=[])
        self.paused = False
        self.exited = False
        self.messages = []
        app = SimpleNamespace(toggle_pause=self.toggle_pause,
                              request_exit=self.request_exit,
                              flash=self.messages.append)
        self.input = InputController(self.state, self.camera, self.hud, app)
        self.ship = next(e for e in self.state.entities.values()
                         if e.owner == 0 and e.alive and e.is_ship)
        self.input.selection = {self.ship.id}

    def toggle_pause(self):
        self.paused = not self.paused

    def request_exit(self):
        self.exited = True

    def press(self, key, release=True):
        self.input.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        if release:
            self.input.handle_event(pygame.event.Event(pygame.KEYUP, key=key, mod=0))

    def test_space_follows_selection_without_pausing(self):
        self.press(pygame.K_SPACE)
        self.assertEqual(self.camera.follow_id, self.ship.id)
        self.assertFalse(self.paused)
        self.ship.pos.x += 50
        self.input.update()
        self.assertEqual(self.camera.target[0], self.ship.pos.x)

    def test_m_toggles_follow_and_free_camera(self):
        self.press(pygame.K_m)
        self.assertEqual(self.camera.follow_id, self.ship.id)
        self.press(pygame.K_m)
        self.assertIsNone(self.camera.follow_id)

    def test_q_e_rotate_continuously_until_released(self):
        initial = self.camera.yaw
        self.press(pygame.K_q, release=False)
        self.input.update()
        first = self.camera.yaw
        self.assertLess(first, initial)
        self.input.update()
        self.assertLess(self.camera.yaw, first)
        self.input.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_q))
        stopped = self.camera.yaw
        self.input.update()
        self.assertEqual(self.camera.yaw, stopped)
        self.press(pygame.K_e, release=False)
        self.input.update()
        self.assertGreater(self.camera.yaw, stopped)

    def test_x_enters_tactical_overview_and_releases_follow(self):
        self.camera.follow_id = self.ship.id
        self.camera.target = [self.ship.pos.x, 0.0, self.ship.pos.z]
        self.press(pygame.K_x)
        self.assertIsNone(self.camera.follow_id)
        self.assertEqual(self.camera.target, [0.0, 0.0, 0.0])
        self.assertEqual(self.camera.distance, self.camera.zoom_limits[1])
        self.assertEqual(self.camera.pitch, 89.0)

    def test_escape_returns_to_menu_during_active_game(self):
        self.press(pygame.K_ESCAPE)
        self.assertTrue(self.exited)

    def test_escape_cancels_placement_before_exiting(self):
        self.hud.placement = {'builder_id': self.ship.id}
        self.press(pygame.K_ESCAPE)
        self.assertIsNone(self.hud.placement)
        self.assertFalse(self.exited)

    def test_escape_closes_fleet_panel_before_exiting(self):
        self.hud.fleet_panel = True
        self.press(pygame.K_ESCAPE)
        self.assertFalse(self.hud.fleet_panel)
        self.assertFalse(self.exited)

    def test_f_toggles_fleet_panel_without_g_prefix(self):
        self.press(pygame.K_f)
        self.assertTrue(self.hud.fleet_panel)
        self.assertFalse(self.state.command_queue)
        self.press(pygame.K_f)
        self.assertFalse(self.hud.fleet_panel)

    def test_p_pauses_without_changing_follow(self):
        self.camera.follow_id = self.ship.id
        self.press(pygame.K_p)
        self.assertTrue(self.paused)
        self.assertEqual(self.camera.follow_id, self.ship.id)
        self.press(pygame.K_p)
        self.assertFalse(self.paused)

    def click_fleet_button(self, kind, payload):
        self.hud.buttons = [{'rect': pygame.Rect(900, 100, 100, 30),
                             'kind': kind, 'payload': payload}]
        self.input.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                  button=1, pos=(910, 110)))

    def fleet_panel_buttons(self):
        """Keep one rendered button snapshot throughout an event batch."""
        self.hud.fleet_panel = True
        self.hud.buttons = [
            {'rect': pygame.Rect(900, 100 + 40 * index, 100, 30),
             'kind': kind, 'payload': payload}
            for index, (kind, payload) in enumerate([
                ('fleet_create', {'unit_ids': [self.ship.id],
                                  'formation': 'line', 'commander': None}),
                ('fleet_close', {}),
                ('fleet_formation', {'formation': 'wedge'}),
                ('fleet_commander', {'commander': next(iter(
                    DataStore.get().rules['commanders']))}),
            ])
        ]

    def click_rendered_fleet_button(self, kind):
        button = next(b for b in self.hud.buttons if b['kind'] == kind)
        for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.input.handle_event(pygame.event.Event(
                event_type, button=1, pos=button['rect'].center))

    def test_duplicate_fleet_create_in_same_batch_queues_only_once(self):
        self.fleet_panel_buttons()
        self.click_rendered_fleet_button('fleet_create')
        self.click_rendered_fleet_button('fleet_create')
        self.assertEqual(len(self.state.command_queue), 1)
        self.assertFalse(self.hud.fleet_panel)
        self.assertEqual(self.input.selection, {self.ship.id})
        self.assertFalse(self.input.dragging)
        self.assertFalse(self.state.fleets, 'UI must not mutate the sim')

    def test_closed_fleet_controls_consume_stale_clicks_without_actions(self):
        for close in ('escape', 'f', 'fleet_close'):
            for kind in ('fleet_create', 'fleet_close', 'fleet_formation',
                         'fleet_commander'):
                with self.subTest(close=close, stale=kind):
                    self.fleet_panel_buttons()
                    self.hud.fleet_formation = 'line'
                    self.hud.fleet_commander = None
                    self.state.command_queue.clear()
                    if close == 'escape':
                        self.press(pygame.K_ESCAPE)
                    elif close == 'f':
                        self.press(pygame.K_f)
                    else:
                        self.click_rendered_fleet_button(close)
                    self.click_rendered_fleet_button(kind)
                    self.assertFalse(self.state.command_queue)
                    self.assertEqual(self.hud.fleet_formation, 'line')
                    self.assertIsNone(self.hud.fleet_commander)
                    self.assertFalse(self.hud.fleet_panel)
                    self.assertEqual(self.input.selection, {self.ship.id})
                    self.assertFalse(self.input.dragging)
                    self.assertIsNone(self.input.drag_start)
                    self.assertFalse(self.exited)

    def test_fleet_choice_then_create_uses_current_choices_without_rendering(self):
        for choice in ('fleet_formation', 'fleet_commander'):
            with self.subTest(choice=choice):
                self.fleet_panel_buttons()
                self.hud.fleet_formation = 'line'
                self.hud.fleet_commander = None
                self.state.command_queue.clear()
                self.click_rendered_fleet_button(choice)
                self.click_rendered_fleet_button('fleet_create')
                self.assertEqual(len(self.state.command_queue), 1)
                command = self.state.command_queue[0]
                self.assertEqual(command.formation, self.hud.fleet_formation)
                self.assertEqual(command.commander, self.hud.fleet_commander)
                self.assertFalse(self.hud.fleet_panel)
                self.assertFalse(self.state.fleets, 'UI must not mutate the sim')

    def test_fleet_buttons_queue_formation_and_commander(self):
        self.hud.fleet_panel = True
        self.click_fleet_button('fleet_formation', {'formation': 'wedge'})
        self.assertEqual(self.hud.fleet_formation, 'wedge')
        commander = next(iter(DataStore.get().rules['commanders']))
        self.click_fleet_button('fleet_commander', {'commander': commander})
        self.assertEqual(self.hud.fleet_commander, commander)
        self.click_fleet_button('fleet_create', {'unit_ids': [self.ship.id],
                               'formation': 'line', 'commander': None})
        self.assertEqual(len(self.state.command_queue), 1)
        command = self.state.command_queue[0]
        self.assertEqual(command.type, 'fleet_create')
        self.assertEqual(command.formation, 'wedge')
        self.assertEqual(command.commander, commander)
        self.assertFalse(self.state.fleets, 'UI must not mutate the sim')
        self.gm.step(1.0 / 30.0)
        fleet = next(iter(self.state.fleets.values()))
        self.assertEqual(fleet.formation, 'wedge')
        self.assertEqual(fleet.commander, commander)
        self.assertIn(self.ship.id, fleet.member_ids)
        self.assertFalse(self.hud.fleet_panel)

    def test_focus_loss_clears_held_keys(self):
        self.press(pygame.K_q, release=False)
        self.input.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.assertFalse(self.input.keys)
        before = self.camera.yaw
        self.input.update()
        self.assertEqual(self.camera.yaw, before)

    def test_repeated_keydown_does_not_toggle_pause_twice(self):
        self.press(pygame.K_p, release=False)
        self.press(pygame.K_p, release=False)
        self.assertTrue(self.paused)

    def test_manual_pan_releases_follow_and_uses_frame_time(self):
        self.press(pygame.K_SPACE)
        self.press(pygame.K_RIGHT, release=False)
        before = list(self.camera.target)
        self.input.update(0.1)
        self.assertIsNone(self.camera.follow_id)
        self.assertNotEqual(self.camera.target, before)

    def _world_offset(self, point=(0.0, 0.0, 0.0), yaw=45.0):
        """Analytic screen offset of a fixed world point in the camera basis.

        +x is to the right on screen, +y is up; both normalised by depth, so
        this is the same comparison the GL projection makes, without a context.
        """
        self.camera.yaw = yaw
        right, up, fwd = self.camera.basis()
        eye = self.camera.eye_position()
        rel = [point[i] - eye[i] for i in range(3)]
        depth = sum(a * b for a, b in zip(rel, fwd))
        self.assertGreater(depth, 1e-6, 'probe point fell behind the eye')
        return (sum(a * b for a, b in zip(rel, right)) / depth,
                sum(a * b for a, b in zip(rel, up)) / depth)

    def test_pan_keys_move_the_view_the_way_the_player_expects(self):
        """#48 reported the camera keys as reversed.

        Pressing up/left pans the view up/left, so the world has to scroll
        down/right. Checked through the camera's own basis at two yaws, so it
        holds for a rotated camera as well as a fresh one.
        """
        for key, direction, axis in (
                (pygame.K_UP, 'up', 'dy'), (pygame.K_w, 'up', 'dy'),
                (pygame.K_DOWN, 'down', 'dy'),
                (pygame.K_LEFT, 'left', 'dx'), (pygame.K_a, 'left', 'dx'),
                (pygame.K_RIGHT, 'right', 'dx'), (pygame.K_d, 'right', 'dx')):
            for yaw in (45.0, 120.0):
                with self.subTest(key=pygame.key.name(key), yaw=yaw):
                    self.input.selection = set()
                    self.camera.follow_id = None
                    self.camera.target = [0.0, 0.0, 0.0]
                    index = 1 if axis == 'dy' else 0
                    before = self._world_offset(yaw=yaw)[index]
                    self.input.keys = {key}
                    self.input.update(1.0 / 30.0)
                    after = self._world_offset(yaw=yaw)[index]
                    delta = after - before
                    self.assertNotAlmostEqual(delta, 0.0, places=6,
                                              msg=f'{pygame.key.name(key)} did not pan')
                    wanted = -1.0 if direction in ('up', 'right') else 1.0
                    self.assertGreater(
                        delta * wanted, 0.0,
                        f'{pygame.key.name(key)} panned the view {direction} but the '
                        f'world scrolled the wrong way (delta {delta:+.4f})')

    def test_s_pans_the_camera_down_when_nothing_is_selected(self):
        """#48 also reported the S key as dead; with no selection it pans."""
        self.input.selection = set()
        self.camera.target = [0.0, 0.0, 0.0]
        before = self._world_offset()[1]
        self.input.keys = {pygame.K_s}
        self.input.update(1.0 / 30.0)
        self.assertGreater(self._world_offset()[1] - before, 0.0,
                           'S pans the view down, so the world scrolls up')

    def test_backspace_stops_selected_ships_without_panning(self):
        """#48: Stop moved to Backspace so S can always pan."""
        before = list(self.camera.target)
        self.press(pygame.K_BACKSPACE, release=False)
        self.input.update()
        self.assertEqual(self.camera.target, before)
        self.assertEqual(self.state.command_queue[0].type, 'stop')

    def test_backspace_without_a_selection_stops_nothing(self):
        self.input.selection = set()
        self.press(pygame.K_BACKSPACE)
        self.input.update()
        self.assertFalse(self.state.command_queue)

    def test_s_pans_with_a_selection_and_stops_nothing(self):
        """The reported 'dead S key': panning must survive a selection."""
        self.assertTrue(self.input.selection)
        self.camera.target = [0.0, 0.0, 0.0]
        before = self._world_offset()[1]
        self.press(pygame.K_s, release=False)
        self.input.update(1.0 / 30.0)
        self.assertGreater(self._world_offset()[1] - before, 0.0,
                           'S pans the view down even with units selected')
        self.assertFalse(self.state.command_queue,
                         'S must not secretly issue a stop order')


if __name__ == '__main__':
    unittest.main()
