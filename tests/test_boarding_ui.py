import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from game.core.vectors import Vec3
from render.hud import HUD
from render.camera import Camera
from render.input import InputController


class TestBoardingUI(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ship = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        self.target = self.gm.factory.spawn_ship('imperial_frigate', 1, Vec3(500, 0, 0))
        self.target.crew = 0
        self.target.shields = {q: 0 for q in self.target.shields}
        self.hud = HUD(1280, 800, self.st)
        self.messages = []
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud,
                                    SimpleNamespace(flash=self.messages.append))
        self.ctrl.selection = {self.ship.id}

    def test_hud_button_arms_target_and_only_queues_serialized_intent(self):
        before = self.st.to_dict(precise=True)
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next((b for b in self.hud.buttons if b['kind'] == 'board'), None)
        self.assertIsNotNone(button)
        self.ctrl._click_button(button['rect'].center)
        self.assertIn('BOARD', self.hud.ability_prompt)
        self.assertEqual(before, self.st.to_dict(precise=True))
        # Use the real input targeting path with a deterministic scene pick.
        self.ctrl._pick_target = lambda pos: self.target
        self.ctrl._confirm_ability((400, 300))
        self.assertEqual(self.st.command_queue[0].type, 'board')
        self.assertEqual(self.st.command_queue[0].target_id, self.target.id)
        self.assertEqual(self.ship.crew, self.ship.max_crew)
        self.gm.commands.consume()
        self.assertTrue(any(e.boarding for e in self.st.entities.values()))

    def test_keyboard_target_feedback_and_cancel_when_selection_loses_capability(self):
        self.ctrl.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b))
        self.assertIsNotNone(self.ctrl._pending_ability)
        self.ctrl._pick_target = lambda pos: self.target
        self.target.shields['front'] = 1
        self.ctrl._confirm_ability((400, 300))
        self.assertEqual(self.st.command_queue, [])
        self.assertIn('shields', self.messages[-1])
        self.ship.crew = 0
        self.ctrl.update(0)
        self.assertIsNone(self.ctrl._pending_ability)

    def test_active_boarding_inspector_shows_transit_and_control_progress(self):
        from game.core.commands import PlayerCommand
        self.st.queue_command(PlayerCommand('board', 0, unit_ids=(self.ship.id,), target_id=self.target.id))
        self.gm.commands.consume()
        craft = next(e for e in self.st.entities.values() if e.boarding)
        labels = []
        self.hud._label = lambda x, y, text, *args: labels.append(str(text))
        self.hud._left_panel({self.ship.id}, 0)
        self.assertTrue(any('BOARDING TRANSIT' in text for text in labels))
        labels.clear()
        craft.pos = self.target.pos.copy()
        self.gm.boarding.update(1)
        self.hud._left_panel({self.target.id}, 0)
        self.assertTrue(any('BOARDING CONTROL 20%' in text for text in labels))

    def test_boarding_shuttle_is_smaller_than_a_corvette(self):
        from render.ship_sizes import ship_size
        shuttle = ship_size(self.gm.ds, 'boarding_craft')
        corvette = ship_size(self.gm.ds, 'imperial_corvette')
        self.assertLess(shuttle.length, corvette.length * .5)

    def test_no_build_hotkey_is_advertised_as_boarding(self):
        labels = []
        self.hud._label = lambda x, y, text, *args: labels.append(str(text))
        self.hud._right_panel(self.ctrl.selection, 0)
        self.assertFalse(any('B  build menu' in text for text in labels))

    def test_inspector_shows_onboard_crew_life_support_and_abandonment(self):
        labels = []
        orig = self.hud._label
        def label(x, y, text, color=None, font=None):
            labels.append(str(text)); orig(x, y, text, color, font)
        self.hud._label = label
        self.target.systems['life_support'].hp = 0
        self.hud._left_panel({self.target.id}, 0)
        self.assertTrue(any('CREW 0/' in s for s in labels))
        self.assertTrue(any('LIFE' in s for s in labels))
        self.assertTrue(any('ABANDONED' in s for s in labels))
