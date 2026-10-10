import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from game.core.vectors import Vec3
from render.hud import HUD
from render.camera import Camera
from render.input import InputController
from render.ship_sizes import ship_size
from render.faction_visuals import ship_visual_key


class RecoveryUITests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.base = self.gm.factory.spawn_station('command_station', 0, Vec3())
        self.t = self.gm.factory.spawn_ship('imperial_crew_transport', 0, Vec3(0, 0, 300))
        self.target = self.gm.factory.spawn_ship('imperial_frigate', 0, Vec3(2000, 0, 0))
        self.target.crew = 0
        self.hud = HUD(1024, 768, self.st)
        self.messages = []
        self.ctrl = InputController(self.st, Camera(1024, 768), self.hud, SimpleNamespace(flash=self.messages.append))
        self.ctrl.selection = {self.t.id}

    def test_real_buttons_load_and_target_owned_hull_only_queue_intent(self):
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next((b for b in self.hud.buttons if b['kind'] == 'crew_load'), None)
        self.assertIsNotNone(button)
        self.ctrl._click_button(button['rect'].center)
        self.assertEqual(self.st.command_queue[-1].type, 'crew_load')
        self.assertEqual(self.t.crew_cargo, 0)
        self.gm.commands.consume()
        self.gm.recovery.update(1)
        button = next(b for b in self.hud.buttons if b['kind'] == 'crew_deliver')
        self.ctrl._click_button(button['rect'].center)
        self.assertIn('CREW', self.hud.ability_prompt)
        self.ctrl._pick_target = lambda pos: self.target
        self.ctrl._confirm_ability((400, 300))
        self.assertEqual(self.st.command_queue[-1].type, 'crew_deliver')
        self.assertEqual(self.st.command_queue[-1].target_id, self.target.id)
        self.assertEqual(self.target.crew, 0)
        self.assertEqual(self.t.crew_cargo, 4)

    def test_inspector_distinguishes_operating_staff_passengers_and_recovery_reason(self):
        self.t.crew_cargo = 20
        self.t.crew //= 2
        self.gm.recovery.start(self.t, 'load')
        labels = []
        self.hud._label = lambda x, y, text, *args: labels.append(str(text))
        before = self.st.to_dict(precise=True)
        self.hud._left_panel({self.t.id}, 0)
        self.assertTrue(any('CARGO 20/240' in s for s in labels))
        self.assertTrue(any('STAFF 50%' in s for s in labels))
        self.assertTrue(any('CREW LOAD' in s for s in labels))
        self.assertEqual(before, self.st.to_dict(precise=True))

    def test_faction_transports_have_small_known_solid_visuals(self):
        for faction, prefix in [('imperial', 'imperial'), ('rebel', 'rebel'), ('confederacy', 'confed'), ('syndicate', 'syndicate')]:
            sid = prefix + '_crew_transport'
            self.assertEqual(self.gm.ds.ships[sid].crew_capacity, 240)
            shape = ship_visual_key(self.gm.ds, sid)
            self.assertEqual(shape, 'box' if faction == 'imperial' else faction + ':convoy')
            self.assertLessEqual(ship_size(self.gm.ds, sid).length, ship_size(self.gm.ds, 'imperial_corvette').length)


if __name__ == '__main__':
    unittest.main()
