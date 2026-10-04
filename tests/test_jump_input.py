"""Destination picking through real InputController pygame events."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import pygame
from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.input import InputController


class JumpInputTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.st = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
        self.camera = Camera(1280, 800)
        self.hud = SimpleNamespace(placement=None, fleet_panel=False, buttons=[],
            minimap_rect=pygame.Rect(1058, 578, 210, 210), scroll_rects=[],
            width=1280, height=800)
        self.messages = []
        self.app = SimpleNamespace(flash=self.messages.append, request_exit=Mock())
        self.ic = InputController(self.st, self.camera, self.hud, self.app)
        self.ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        self.ship = self.ships[0]
        self.ic.selection = {self.ship.id}

    def press(self, key, release=True):
        self.ic.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        if release:
            self.ic.handle_event(pygame.event.Event(pygame.KEYUP, key=key))

    def click(self, pos, button=1):
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ic.handle_event(pygame.event.Event(kind, button=button, pos=pos))

    def arm_tractor(self):
        from dataclasses import replace
        ds = DataStore.get()
        sd = ds.ships[self.ship.data_id]
        ds.ships[sd.id] = replace(sd, abilities=['tractor_beam'])
        self.ship.energy = 1000
        self.hud.blocked_rects = []
        self.hud.buttons = [{'rect': pygame.Rect(10, 10, 100, 20),
            'kind': 'ability', 'payload': {'ability_id': 'tractor_beam',
                                         'unit_ids': [self.ship.id]}}]
        self.ic._click_button((20, 15))
        self.assertIsNotNone(self.ic._pending_ability)

    def test_jump_replaces_tractor_targeting_before_click_or_escape(self):
        for action in ('click', 'escape'):
            with self.subTest(action=action):
                self.arm_tractor()
                self.camera.screen_to_world = Mock(return_value=(8000, 0, 6000))
                self.press(pygame.K_j)
                self.assertIsNone(self.ic._pending_ability)
                self.assertEqual(self.hud.ability_prompt, '')
                self.assertEqual(self.ic._pending_jump, (self.ship.id,))
                self.assertTrue(self.hud.jump_prompt)
                if action == 'click':
                    self.click((640, 300))
                    self.assertEqual(len(self.st.command_queue), 1)
                    cmd = self.st.command_queue.pop()
                    self.assertEqual(cmd.type, 'jump')
                    self.assertEqual(cmd.unit_ids, (self.ship.id,))
                    self.assertEqual(cmd.target_pos, (8000, 0, 6000))
                else:
                    self.press(pygame.K_ESCAPE)
                    self.assertFalse(self.st.command_queue)
                    self.app.request_exit.assert_not_called()
                self.assertIsNone(self.ic._pending_jump)
                self.assertIsNone(self.ic._pending_ability)
                self.assertFalse(self.hud.jump_prompt)
                self.assertFalse(self.ic.dragging)

    def test_tractor_replaces_jump_targeting(self):
        self.press(pygame.K_j)
        self.arm_tractor()
        self.assertIsNone(self.ic._pending_jump)
        self.assertFalse(self.hud.jump_prompt)
        self.assertTrue(self.hud.ability_prompt)
        self.press(pygame.K_ESCAPE)
        self.assertIsNone(self.ic._pending_ability)
        self.assertFalse(self.st.command_queue)
        self.app.request_exit.assert_not_called()

    def test_world_click_queues_snapshot_at_ground_tuple_without_fallthrough(self):
        self.camera.screen_to_world = Mock(return_value=(8000.0, 0.0, 6000.0))
        self.press(pygame.K_j)
        self.ic.selection = {self.ships[1].id}
        before = list(self.camera.target)
        self.click((640, 300))
        self.assertEqual(len(self.st.command_queue), 1)
        cmd = self.st.command_queue[0]
        self.assertEqual(cmd.type, 'jump')
        self.assertEqual(cmd.unit_ids, (self.ship.id,))
        self.assertEqual(cmd.target_pos, (8000.0, 0.0, 6000.0))
        self.assertFalse(self.ic.dragging)
        self.assertEqual(self.ic.selection, {self.ships[1].id})
        self.assertEqual(self.camera.target, before)
        self.assertIsNone(self.ic._pending_jump)

    def test_currently_sensed_ground_queues_jump(self):
        from game.core.vectors import Vec3
        target = self.ship.pos + Vec3(500, 0, 0)
        self.assertTrue(self.st.is_position_explored(0, target))
        self.assertTrue(self.st.is_position_visible(0, target))
        self.camera.screen_to_world = Mock(return_value=(target.x, 0, target.z))
        self.press(pygame.K_j)
        self.click((640, 300))
        self.assertEqual(len(self.st.command_queue), 1)
        self.assertEqual(self.st.command_queue[0].target_pos, (target.x, 0, target.z))
        self.assertIsNone(self.ic._pending_jump)

    def test_invalid_ground_rejected_stays_armed(self):
        self.press(pygame.K_j)
        half = self.st.map_info.bounds / 2
        for world, reason in [((half + 1, 0, 0), 'bounds'),
                              ((float('nan'), 0, 0), 'bounds'),
                              (None, 'ground')]:
            with self.subTest(world=world):
                self.camera.screen_to_world = Mock(return_value=world)
                self.click((640, 300))
                self.assertFalse(self.st.command_queue)
                self.assertIsNotNone(self.ic._pending_jump)
                self.assertIn(reason, self.messages[-1])

    def test_minimap_uses_content_mapping_without_relocating_camera(self):
        self.press(pygame.K_j)
        self.camera.screen_to_world = Mock(side_effect=AssertionError('not ground'))
        before = list(self.camera.target)
        r = self.hud.minimap_rect
        self.click((r.centerx + 50, r.centery - 50))
        cmd = self.st.command_queue[0]
        scale = (self.st.map_info.bounds / 2) / (r.width / 2 - 4)
        self.assertEqual(cmd.target_pos, (50 * scale, 0, -50 * scale))
        self.assertEqual(self.camera.target, before)

    def test_minimap_margin_rejected_not_interpreted_as_world(self):
        self.press(pygame.K_j)
        self.camera.screen_to_world = Mock(return_value=(8000, 0, 8000))
        self.click(self.hud.minimap_rect.topleft)
        self.assertFalse(self.st.command_queue)
        self.assertIsNotNone(self.ic._pending_jump)
        self.camera.screen_to_world.assert_not_called()

    def test_ordinary_minimap_click_still_relocates_camera(self):
        r = self.hud.minimap_rect
        self.click((r.centerx + 50, r.centery - 50))
        scale = (self.st.map_info.bounds / 2) / (r.width / 2 - 4)
        self.assertEqual(self.camera.target, [50 * scale, 0, -50 * scale])
        self.assertFalse(self.st.command_queue)

    def test_eligibility_filters_on_arm_and_confirmation(self):
        enemy = next(e for e in self.st.entities.values() if e.owner == 1 and e.is_ship)
        station = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_station)
        from copy import deepcopy
        extras = [deepcopy(self.ship) for _ in range(2)]
        for index, e in enumerate(extras, 10001):
            e.id = index
            self.st.entities[e.id] = e
        dead, cooldown, charging, dataless = self.ships[1:3] + extras
        dead.alive = False
        cooldown.ability_cooldowns['_jump_cd'] = 10
        charging.jump_charge = 1
        dataless.data_id = 'trade_convoy'
        self.ic.selection = {self.ship.id, enemy.id, station.id, dead.id,
                             cooldown.id, charging.id, dataless.id}
        self.press(pygame.K_j)
        self.assertEqual(self.ic._pending_jump, (self.ship.id,))
        self.ship.alive = False
        self.camera.screen_to_world = Mock(return_value=(8000, 0, 8000))
        self.click((640, 300))
        self.assertFalse(self.st.command_queue)
        self.assertIsNone(self.ic._pending_jump)
        self.assertIn('eligible', self.messages[-1])

    def test_no_eligible_selection_does_not_arm(self):
        self.ship.ability_cooldowns['_jump_cd'] = 10
        self.press(pygame.K_j)
        self.assertIsNone(self.ic._pending_jump)
        self.assertIn('eligible', self.messages[-1])

    def test_snapshot_refilters_owner_and_capability_at_confirmation(self):
        self.ic.selection = {e.id for e in self.ships[:3]}
        self.press(pygame.K_j)
        self.ships[1].owner = 1
        self.ships[2].data_id = 'trade_convoy'
        self.camera.screen_to_world = Mock(return_value=(8000, 0, 8000))
        self.click((640, 300))
        self.assertEqual(self.st.command_queue[0].unit_ids, (self.ship.id,))

    def test_cancel_events_clear_mode_without_orders_or_camera_drag(self):
        self.ic._right_click = Mock()
        for cancel in ('escape', 'right', 'focus'):
            with self.subTest(cancel=cancel):
                self.press(pygame.K_j)
                if cancel == 'escape':
                    self.press(pygame.K_ESCAPE)
                elif cancel == 'right':
                    self.click((640, 300), button=3)
                    self.ic.handle_event(pygame.event.Event(
                        pygame.MOUSEMOTION, pos=(650, 300), rel=(10, 0)))
                else:
                    self.ic.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
                self.assertIsNone(self.ic._pending_jump)
                self.assertIsNone(self.ic.right_drag)
                self.assertFalse(self.st.command_queue)
                self.ic._right_click.assert_not_called()
                self.app.request_exit.assert_not_called()

    def test_hud_click_rejected_without_buttons_selection_or_ground_pick(self):
        self.hud.blocked_rects = [pygame.Rect(0, 0, 1280, 34),
                                  pygame.Rect(10, 44, 320, 430)]
        self.hud.buttons = [{'rect': pygame.Rect(900, 90, 100, 30),
                             'kind': 'build_ship', 'payload': {}}]
        self.camera.screen_to_world = Mock(return_value=(8000, 0, 8000))
        self.press(pygame.K_j)
        for pos in [(640, 10), (20, 100), (920, 100)]:
            self.click(pos)
            self.assertFalse(self.st.command_queue)
            self.assertIsNotNone(self.ic._pending_jump)
            self.assertFalse(self.ic.dragging)
            self.assertIn('HUD', self.messages[-1])
        self.camera.screen_to_world.assert_not_called()

    def test_arm_clears_placement_fleet_and_old_mouse_gestures(self):
        self.hud.placement = {'builder_id': self.ship.id}
        self.hud.fleet_panel = True
        self.ic._pending_fleet = [self.ship.id]
        self.ic.drag_start = (640, 300)
        self.ic.dragging = True
        self.ic.right_drag = (640, 300)
        self.press(pygame.K_j)
        self.assertIsNone(self.hud.placement)
        self.assertFalse(self.hud.fleet_panel)
        self.assertIsNone(self.ic._pending_fleet)
        self.assertFalse(self.ic.dragging)
        self.assertIsNone(self.ic.right_drag)

    def test_fleet_and_group_controls_cancel_jump(self):
        for key in (pygame.K_f, pygame.K_g, pygame.K_1):
            with self.subTest(key=key):
                self.ic.selection = {self.ship.id}
                self.press(pygame.K_j)
                self.press(key)
                self.assertIsNone(self.ic._pending_jump)
                self.hud.fleet_panel = False
                self.ic._pending_fleet = None
        self.assertFalse(self.st.command_queue)

    def test_update_cancels_when_snapshot_disappears(self):
        self.press(pygame.K_j)
        del self.st.entities[self.ship.id]
        self.ic.update(0)
        self.assertIsNone(self.ic._pending_jump)
        self.assertIn('eligible', self.messages[-1])

    def test_offscreen_click_cannot_target_even_with_valid_unprojection(self):
        self.press(pygame.K_j)
        self.camera.screen_to_world = Mock(return_value=(8000, 0, 8000))
        for pos in [(-1, 300), (1280, 300), (640, -1), (640, 800)]:
            self.click(pos)
            self.assertFalse(self.st.command_queue)
            self.assertIsNotNone(self.ic._pending_jump)
        self.camera.screen_to_world.assert_not_called()

    def test_zero_hull_squadron_or_existing_jump_target_cannot_arm(self):
        from game.core.vectors import Vec3
        for field, value in [('hull', 0), ('is_squadron', True),
                             ('jump_target', Vec3(8000, 0, 8000))]:
            with self.subTest(field=field):
                original = getattr(self.ship, field)
                setattr(self.ship, field, value)
                self.press(pygame.K_j)
                self.assertIsNone(self.ic._pending_jump)
                setattr(self.ship, field, original)

    def test_j_arms_without_center_jump_and_ignores_repeat(self):
        self.press(pygame.K_j, release=False)
        self.assertFalse(self.st.command_queue, 'J must not jump to center')
        self.assertEqual(self.ic._pending_jump, (self.ship.id,))
        self.press(pygame.K_j, release=False)
        self.assertEqual(self.ic._pending_jump, (self.ship.id,))
        self.assertIn('click destination', self.messages[-1])
        self.assertNotIn('unexplored', self.messages[-1].lower())

    def test_persistent_hud_prompt_requests_destination_not_unexplored_only(self):
        from render.hud import HUD
        hud = HUD(1280, 800, self.st)
        # Exercise the real HUD composition; only GL upload needs a context.
        hud._upload = Mock()
        render = Mock(wraps=hud.font.render)
        hud.font = SimpleNamespace(render=render, size=hud.font.size)
        hud.jump_prompt = True
        hud.render({self.ship.id}, None, 0, False)
        prompts = [c.args[0] for c in render.call_args_list
                   if c.args[0].startswith('JUMP:')]
        self.assertEqual(len(prompts), 1)
        self.assertIn('click destination', prompts[0])
        self.assertNotIn('unexplored', prompts[0].lower())
