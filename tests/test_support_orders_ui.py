"""User-facing support orders: real factories, queued intent, read-only HUD."""
import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from game.core.vectors import Vec3
from game.core.commands import PlayerCommand
from render.hud import HUD
from render.camera import Camera
from render.input import InputController


class SupportOrdersUITests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.hud = HUD(1024, 768, self.st)
        self.labels = []
        self.rects = []
        original = self.hud._label
        def label(x, y, text, color=None, font=None, translate=True):
            self.labels.append(str(text))
            self.rects.append(pygame.Rect(x, y, *(font or self.hud.font).size(str(text))))
            original(x, y, text, color, font, translate)
        self.hud._label = label
        self.messages = []
        self.ctrl = InputController(self.st, Camera(1024, 768), self.hud,
            SimpleNamespace(flash=self.messages.append, request_exit=lambda: self.fail('cancel exited')))

    def test_every_build_row_displays_actual_crew_fee_in_bounds(self):
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 1e9
        panel = pygame.Rect(694, 44, 320, 430)
        for data in list(self.hud.ds.ships.values()) + list(self.hud.ds.stations.values()):
            with self.subTest(data=data.id):
                self.labels.clear(); self.rects.clear(); self.hud.buttons.clear()
                next_y = self.hud._build_row(panel, 60, data, p, {}, 'build_ship')
                self.assertTrue(any(f'{data.crew_cost:,.0f} crew' in label for label in self.labels))
                self.assertTrue(all(panel.contains(rect) for rect in self.rects))
                self.assertLessEqual(max(r.bottom for r in self.rects), next_y)


    def test_production_pages_show_full_rows_without_overlapping_costs(self):
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 1e9
        station = self.gm.factory.spawn_station('shipyard', 0, Vec3())
        items = list(self.hud.ds.ships.values())
        panel = pygame.Rect(694, 44, 320, 430)
        shown = set()
        for offset in range(len(items)):
            self.labels.clear(); self.rects.clear(); self.hud.buttons.clear()
            self.hud.scroll['ships'] = offset
            self.hud._scrollable(panel, 82, items, p, 'ships', self.hud._row_build_ship, station)
            rows = [b for b in self.hud.buttons if b['kind'] == 'build_ship']
            shown.update(b['payload']['ship_id'] for b in rows)
            self.assertTrue(all(panel.contains(b['rect']) for b in rows))
            self.assertTrue(all(not a['rect'].colliderect(b['rect']) for i, a in enumerate(rows) for b in rows[i+1:]))
        self.assertEqual(shown, {d.id for d in items})


    def test_constructor_repair_control_arms_target_mode_and_queues_only_on_confirmation(self):
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        target = self.gm.factory.spawn_station('repair_dock', 0, Vec3(400, 0, 0))
        target.hull -= 100
        self.ctrl.selection = {builder.id}
        before = self.st.to_dict(precise=True)
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next((b for b in self.hud.buttons if b['kind'] == 'repair'), None)
        self.assertIsNotNone(button, 'constructor needs an explicit repair control')
        self.ctrl._click_button(button['rect'].center)
        self.assertIsNotNone(self.ctrl._pending_ability)
        self.assertEqual(before, self.st.to_dict(precise=True))
        self.ctrl._pick_target = lambda pos: target
        self.ctrl._confirm_ability((500, 500))
        cmd = PlayerCommand.from_dict(self.st.command_queue[-1].to_dict())
        self.assertEqual((cmd.type, tuple(cmd.unit_ids), cmd.target_id), ('repair', (builder.id,), target.id))
        self.assertIsNone(self.ctrl._pending_ability)


    def test_fighter_exploration_button_queues_owned_capable_subset_immediately(self):
        own = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        foreign = self.gm.factory.spawn_ship('imperial_tie_squadron', 1, Vec3())
        other = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.ctrl.selection = {own.id, foreign.id, other.id}
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next((b for b in self.hud.buttons if b['kind'] == 'explore'), None)
        self.assertIsNotNone(button, 'mixed selection must expose fighter exploration')
        before = self.st.to_dict(precise=True)
        self.ctrl._click_button(button['rect'].center)
        command = PlayerCommand.from_dict(self.st.command_queue[-1].to_dict())
        self.assertEqual((command.type, tuple(command.unit_ids)), ('explore', (own.id,)))
        self.assertIsNone(command.target_id)
        self.assertIsNone(self.ctrl._pending_ability)
        after = self.st.to_dict(precise=True)
        # Ignore ONLY the verified new input, in both save representations;
        # retain all prior queued commands and every other runtime/AI field.
        self.assertEqual(after['command_queue'].pop(), command.to_dict())
        from game.net.reconnect import _encode
        queues = [value for key, value in after['runtime_state']['state'][1]
                  if key == ['scalar', 'command_queue']]
        self.assertEqual(len(queues), 1)
        self.assertEqual(queues[0][1].pop(), _encode(command))
        self.assertEqual(before, after)


    def test_support_panels_fit_and_boarding_help_has_current_requirements(self):
        for ship_id in ('imperial_constructor', 'imperial_tie_squadron', 'imperial_frigate', 'imperial_crew_transport'):
            with self.subTest(ship_id=ship_id):
                ship = self.gm.factory.spawn_ship(ship_id, 0, Vec3())
                self.hud.buttons.clear(); self.hud.blocked_rects.clear(); self.labels.clear(); self.rects.clear()
                self.hud._right_panel({ship.id}, 0)
                panel = self.hud.blocked_rects[-1]
                self.assertTrue(all(panel.contains(r) for r in self.rects), [s for s,r in zip(self.labels,self.rects) if not panel.contains(r)])
                self.assertTrue(all(panel.contains(b['rect']) for b in self.hud.buttons))
                if ship_id == 'imperial_frigate':
                    self.ctrl.selection = {ship.id}
                    self.ctrl._queue_board()
                    self.assertIn('all shields down', self.hud.ability_prompt.lower())
                    self.assertNotIn('disabled', self.hud.ability_prompt.lower())


    def test_restored_support_orders_show_readonly_progress_and_modded_rates(self):
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        target = self.gm.factory.spawn_station('shipyard', 0, Vec3(300, 0, 0))
        target.hull -= 80
        builder.order_type = 'repair'; builder.order_target_id = target.id
        self.hud.ds.rules['engineer_repairs'] = dict(hp_per_second=7, credits_per_hp=.3, materials_per_hp=.4, range=400)
        before = self.st.to_dict(precise=True)
        self.hud._left_panel({builder.id}, 0)
        self.assertTrue(any('HP missing' in t for t in self.labels))
        self.assertTrue(any('7 HP/s' in t for t in self.labels))
        self.assertTrue(any('0.3 CR/HP' in t for t in self.labels))
        self.assertTrue(any('0.4 MT/HP' in t for t in self.labels))
        self.assertTrue(all(self.hud.blocked_rects[0].contains(r) for r in self.rects))
        self.assertEqual(before, self.st.to_dict(precise=True))
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        fighter.order_type = 'explore'; fighter.order_target_pos = Vec3(800, 0, 1200)
        self.labels.clear(); self.rects.clear(); self.hud.blocked_rects.clear()
        self.hud._left_panel({fighter.id}, 0)
        self.assertTrue(any('800' in t and '1,200' in t for t in self.labels))
        self.assertTrue(any('avoid detected enemies' in t.lower() for t in self.labels))
        self.assertTrue(all(self.hud.blocked_rects[0].contains(r) for r in self.rects))


    def test_stale_support_controls_revalidate_operating_recipients(self):
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        self.ctrl.selection = {fighter.id}
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next(b for b in self.hud.buttons if b['kind'] == 'explore')
        fighter.crew = 0
        self.ctrl._click_button(button['rect'].center)
        self.assertFalse(self.st.command_queue)
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.ctrl.selection = {builder.id}
        self.hud.buttons.clear()
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next(b for b in self.hud.buttons if b['kind'] == 'repair')
        builder.jump_charge = 10
        self.ctrl._click_button(button['rect'].center)
        self.assertIsNone(self.ctrl._pending_ability)

    def test_repair_mode_cancels_stale_original_recipients_and_is_exclusive(self):
        for mutation in ('death', 'capture', 'deselection'):
            builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
            self.ctrl.selection = {builder.id}
            self.ctrl._pending_jump = (builder.id,); self.hud.jump_prompt = True
            self.ctrl._queue_repair({'unit_ids': [builder.id]})
            self.assertIsNone(self.ctrl._pending_jump)
            if mutation == 'death': builder.alive = False
            elif mutation == 'capture': builder.owner = 1
            else: self.ctrl.selection.clear()
            self.ctrl.update(0)
            self.assertIsNone(self.ctrl._pending_ability)
            self.assertEqual(self.hud.ability_prompt, '')
            self.assertFalse(self.st.command_queue)
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.ctrl.selection = {builder.id}
        self.ctrl._queue_repair({'unit_ids': [builder.id]})
        self.ctrl._queue_jump()
        self.assertIsNone(self.ctrl._pending_ability)
        self.ctrl._cancel_jump()
        for event in (pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
                      pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(500,500))):
            self.ctrl.keys.clear()
            self.ctrl._queue_repair({'unit_ids': [builder.id]})
            self.ctrl.handle_event(event)
            self.assertIsNone(self.ctrl._pending_ability)
            self.assertFalse(self.st.command_queue)


    def test_stop_cancels_pending_repair_without_late_confirmation(self):
        """Stop is Backspace since #48 (S is a camera pan key again)."""
        builder = self.gm.factory.spawn_ship('imperial_constructor', 0, Vec3())
        self.ctrl.selection = {builder.id}
        self.ctrl._queue_repair({'unit_ids': [builder.id]})
        self.ctrl.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
        self.assertIsNone(self.ctrl._pending_ability)
        self.assertEqual(self.hud.ability_prompt, '')
        self.assertEqual([c.type for c in self.st.command_queue], ['stop'])
        self.assertFalse(self.ctrl.dragging)

    def test_explore_exits_stale_fleet_creation_mode(self):
        fighter = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        self.ctrl.selection = {fighter.id}
        self.hud._right_panel(self.ctrl.selection, 0)
        button = next(b for b in self.hud.buttons if b['kind'] == 'explore')
        self.hud.fleet_panel = True
        self.ctrl._pending_fleet = [fighter.id]
        self.ctrl._click_button(button['rect'].center)
        self.assertFalse(self.hud.fleet_panel)
        self.assertIsNone(self.ctrl._pending_fleet)
        self.assertEqual([c.type for c in self.st.command_queue], ['explore'])

    def test_support_help_explains_limits_before_ordering(self):
        for ship_id, required in (
            ('imperial_constructor', ('CR/HP', 'MT/HP', 'no crew', 'Backspace to stop')),
            ('imperial_frigate', ('all shields down', 'satellites', '10%')),
            ('imperial_tie_squadron', ('avoid detected enemies', 'no combat')),
            ('repair_dock', ('ships / fighters only', 'not stations'))):
            entity = (self.gm.factory.spawn_station(ship_id, 0, Vec3()) if ship_id == 'repair_dock'
                      else self.gm.factory.spawn_ship(ship_id, 0, Vec3()))
            self.labels.clear(); self.rects.clear(); self.hud.blocked_rects.clear(); self.hud.buttons.clear()
            self.hud._right_panel({entity.id}, 0)
            text = ' '.join(self.labels)
            for phrase in required:
                self.assertIn(phrase, text)
            self.assertTrue(all(self.hud.blocked_rects[-1].contains(r) for r in self.rects))


    def test_satellite_cost_rows_and_help_fit_after_universal_crew_costs(self):
        planet = next(e for e in self.st.entities.values() if e.is_planet and e.data_id != 'gas_giant')
        planet.colonized_by = 0
        self.hud._planet_menu(planet, 0)
        self.assertTrue(all(self.hud.blocked_rects[-1].contains(r) for r in self.rects),
                        [t for t,r in zip(self.labels,self.rects) if not self.hud.blocked_rects[-1].contains(r)])


if __name__ == '__main__':
    unittest.main()
