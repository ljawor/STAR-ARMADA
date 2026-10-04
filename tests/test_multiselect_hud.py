"""Selection inspector regressions, using real simulation fixtures."""
import unittest
from helpers import make_game
from game.core.vectors import Vec3
from render.hud import HUD


class SelectionHUDTests(unittest.TestCase):
    def setUp(self):
        self.game = make_game(ai=False)
        self.st = self.game.state
        self.view = HUD(1280, 800, self.st)
        self.labels = []
        original = self.view._label
        def label(x, y, text, color=None, font=None):
            self.labels.append(str(text))
            original(x, y, text, color, font)
        self.view._label = label

    def test_mixed_selection_roster_is_not_first_ship_inspector(self):
        ships = [e for e in self.st.entities.values() if e.owner == 0 and e.is_ship]
        before = self.st.to_dict(precise=True)
        self.view._left_panel({e.id for e in ships} | {999999}, 0)
        self.assertIn(f'SELECTED UNITS · {len(ships)}', self.labels)
        for ship in ships:
            self.assertTrue(any((ship.name_override or self.view.ds.unit_name(ship)) in s for s in self.labels))
        self.assertEqual(before, self.st.to_dict(precise=True))

    def test_serialized_button_command_activates_only_eligible_owned_hulls(self):
        from types import SimpleNamespace
        from render.input import InputController
        from game.core.commands import PlayerCommand
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        aid = sd.abilities[0]
        a = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        b = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        foreign = self.game.factory.spawn_ship(sd.id, 1, Vec3())
        a.energy = b.energy = foreign.energy = 1000
        b.ability_cooldowns[aid] = 12
        selection = {a.id, b.id, foreign.id}
        self.view._left_panel(selection, 0)
        ctrl = InputController(self.st, SimpleNamespace(), self.view, SimpleNamespace())
        ctrl.selection = selection
        button = next(b for b in self.view.buttons if b['kind'] == 'ability' and b['payload']['ability_id'] == aid)
        ctrl._click_button(button['rect'].center)
        command = PlayerCommand.from_dict(self.st.command_queue.pop().to_dict())
        self.game.commands._apply(command)
        self.assertEqual(a.energy, 1000 - self.view.ds.abilities[aid].energy_cost)
        self.assertEqual(b.energy, 1000)
        self.assertEqual(foreign.energy, 1000)
        self.assertNotIn(aid, foreign.ability_cooldowns)

    def test_mixed_readiness_deduplicates_capabilities_and_counts_low_energy(self):
        from dataclasses import replace
        from render.hud import selected_ability_data
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        aid = sd.abilities[0]
        self.view.ds.ships[sd.id] = replace(sd, abilities=[aid, aid])
        ships = [self.game.factory.spawn_ship(sd.id, 0, Vec3()) for _ in range(3)]
        ships[0].energy = 1000
        ships[1].energy = 0
        ships[2].ability_cooldowns[aid] = 7.5
        before = self.st.to_dict(precise=True)
        rows = selected_ability_data(self.st, [s.id for s in ships] * 2, 0)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['count'], 3)
        self.assertEqual(row['unit_ids'], [ships[0].id])
        self.assertEqual(row['low_energy'], 1)
        self.assertEqual(row['cooldowns'], [7.5])
        self.assertEqual(before, self.st.to_dict(precise=True))

    def test_hidden_dead_and_allied_units_never_add_abilities_or_recipients(self):
        from render.hud import selected_ability_data
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        own = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        foreign = self.game.factory.spawn_ship(sd.id, 1, Vec3())
        dead = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        dead.alive = False
        hidden = self.game.factory.spawn_ship(sd.id, 1, Vec3(12000, 0, 12000))
        own.energy = 1000
        selection = {own.id, foreign.id, dead.id, hidden.id, 999999}
        before = self.st.to_dict(precise=True)
        rows = selected_ability_data(self.st, selection, 0)
        self.assertTrue(rows)
        self.assertTrue(all(r['count'] == 1 and r['unit_ids'] == [own.id] for r in rows))
        teams = (self.st.players[0].team, self.st.players[1].team)
        self.st.players[0].team = self.st.players[1].team = 0
        self.assertEqual(rows, selected_ability_data(self.st, selection, 0))
        self.st.players[0].team, self.st.players[1].team = teams
        self.assertEqual(before, self.st.to_dict(precise=True))
        self.view._left_panel({foreign.id}, 0)
        self.assertFalse(any(b['kind'] == 'ability' for b in self.view.buttons))

    def test_targeted_ability_escape_consumes_cancel_without_exiting(self):
        from types import SimpleNamespace
        from render.input import InputController
        import pygame
        exited = []
        ctrl = InputController(self.st, SimpleNamespace(follow_id=None), self.view,
            SimpleNamespace(request_exit=lambda: exited.append(True)))
        ctrl._pending_ability = {'ability_id': 'tractor_beam', 'unit_ids': []}
        self.view.ability_prompt = 'target'
        ctrl.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(exited)
        self.assertIsNone(ctrl._pending_ability)
        self.assertEqual(self.view.ability_prompt, '')

    def test_update_cancels_tractor_when_no_valid_recipients_remain(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from render.camera import Camera
        from render.input import InputController
        import pygame
        sd = next(s for s in self.view.ds.ships.values() if not s.is_squadron)
        self.view.ds.ships[sd.id] = replace(sd, abilities=['tractor_beam'])
        messages = []
        ctrl = InputController(self.st, Camera(1280, 800), self.view,
                               SimpleNamespace(flash=messages.append))
        for invalidation in ('dead', 'ownership', 'selection'):
            with self.subTest(invalidation=invalidation):
                ship = self.game.factory.spawn_ship(sd.id, 0, Vec3())
                ship.energy = 1000
                ctrl.selection = {ship.id}
                self.view.buttons = [{'rect': pygame.Rect(10, 10, 100, 20),
                    'kind': 'ability', 'payload': {'ability_id': 'tractor_beam',
                                                 'unit_ids': [ship.id]}}]
                ctrl._click_button((20, 15))
                self.assertIsNotNone(ctrl._pending_ability)
                if invalidation == 'dead':
                    ship.alive = False
                elif invalidation == 'ownership':
                    ship.owner = 1
                else:
                    ctrl.selection.clear()
                ctrl.dragging = True
                ctrl.drag_start = ctrl.drag_cur = ctrl.right_drag = (640, 300)
                before = self.st.to_dict(precise=True)
                ctrl.update(0)
                self.assertIsNone(ctrl._pending_ability)
                self.assertEqual(self.view.ability_prompt, '')
                self.assertFalse(ctrl.dragging)
                self.assertIsNone(ctrl.drag_start)
                self.assertIsNone(ctrl.drag_cur)
                self.assertIsNone(ctrl.right_drag)
                self.assertFalse(self.st.command_queue)
                self.assertEqual(before, self.st.to_dict(precise=True))
                self.assertIn('cancelled', messages[-1])

    def test_mixed_roster_squadron_status_and_ability_counts_fit(self):
        import pygame
        from dataclasses import replace
        squad_data = next(s for s in self.view.ds.ships.values() if s.is_squadron)
        squad = self.game.factory.spawn_ship(squad_data.id, 0, Vec3())
        squad.fighter_count = squad.max_fighters = 99999
        other = self.game.factory.spawn_ship(next(iter(self.view.ds.ships)), 0, Vec3())
        records = []
        original = self.view._label
        def label(x, y, text, color=None, font=None):
            records.append(pygame.Rect(x, y, *(font or self.view.font).size(str(text))))
            original(x, y, text, color, font)
        self.view._label = label
        self.view._left_panel({squad.id, other.id}, 0)
        panel = self.view.blocked_rects[0]
        self.assertTrue(all(panel.contains(r) for r in records))

    def test_targeted_ability_waits_for_visible_enemy_and_serializes_recipients(self):
        from types import SimpleNamespace
        from render.input import InputController
        from game.core.commands import PlayerCommand
        import pygame
        from dataclasses import replace
        sd = next(iter(self.view.ds.ships.values()))
        sd = replace(sd, abilities=['tractor_beam'])
        self.view.ds.ships[sd.id] = sd
        a = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        a.energy = 1000
        target = self.game.factory.spawn_ship(sd.id, 1, Vec3(500, 0, 0))
        camera = SimpleNamespace(follow_id=None, world_to_screen=lambda x, y, z: (x, z),
            eye_position=lambda: (0, 20000, 0), yaw=0, pitch=89, height=800, fov=60)
        ctrl = InputController(self.st, camera, self.view, SimpleNamespace(flash=lambda s: None))
        ctrl.selection = {a.id}
        self.view._left_panel(ctrl.selection, 0)
        button = next(b for b in self.view.buttons if b['kind'] == 'ability' and b['payload']['ability_id'] == 'tractor_beam')
        ctrl._click_button(button['rect'].center)
        self.assertFalse(self.st.command_queue)
        ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 0)))
        command = self.st.command_queue[-1]
        self.assertEqual(command.unit_ids, (a.id,))
        self.assertEqual(command.target_id, target.id)
        self.assertEqual(PlayerCommand.from_dict(command.to_dict()), command)

    def test_native_wheel_and_page_buttons_scroll_roster_without_world_input(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from render.input import InputController
        import pygame
        ships = [self.game.factory.spawn_ship(next(iter(self.view.ds.ships)), 0, Vec3()) for _ in range(30)]
        self.view._left_panel({e.id for e in ships}, 0)
        ctrl = InputController(self.st, SimpleNamespace(follow_id=None), self.view, SimpleNamespace())
        with patch('pygame.mouse.get_pos', return_value=(100, 120)):
            ctrl.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
        self.assertEqual(self.view.scroll['selection'], 1)
        button = next(b for b in self.view.buttons if b['kind'] == 'hud_scroll' and b['payload']['key'] == 'selection' and b['payload']['delta'] > 0)
        ctrl._click_button(button['rect'].center)
        self.assertGreater(self.view.scroll['selection'], 1)
        ctrl.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(15, 200)))
        self.assertFalse(ctrl.dragging)

    def test_authoritative_ability_rejects_incapable_ship(self):
        ship = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_construction)
        aid = next(a for a in self.view.ds.abilities if a not in self.view.ds.ships[ship.data_id].abilities)
        ship.energy = 1000
        before = self.st.to_dict(precise=True)
        from game.core.commands import AbilityCommand
        self.game.commands._apply(AbilityCommand(0, [ship.id], aid))
        self.assertEqual(before, self.st.to_dict(precise=True))

    def test_long_names_and_many_single_ship_abilities_fit_and_page(self):
        from copy import deepcopy
        from unittest.mock import patch
        from dataclasses import replace
        import pygame
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        ship = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        ship.name_override = 'An extraordinarily long vessel name ' * 4
        abilities = {f'probe{i}': replace(next(iter(self.view.ds.abilities.values())), id=f'probe{i}') for i in range(18)}
        sd = replace(sd, abilities=list(abilities))
        labels = []
        original = self.view._label
        def label(x, y, text, color=None, font=None):
            labels.append(pygame.Rect(x, y, *(font or self.view.font).size(str(text))))
            original(x, y, text, color, font)
        self.view._label = label
        with patch.dict(self.view.ds.ships, {sd.id: sd}), patch.dict(self.view.ds.abilities, abilities):
            for size in ((1280, 800), (1024, 768)):
                self.view.resize(*size)
                seen = set()
                for off in range(30):
                    self.view.scroll['abilities'] = off
                    self.view.buttons.clear()
                    self.view.blocked_rects.clear()
                    labels.clear()
                    self.view._left_panel({ship.id}, 0)
                    panel = self.view.blocked_rects[0]
                    self.assertTrue(all(panel.contains(r) for r in labels))
                    for b in self.view.buttons:
                        self.assertTrue(panel.contains(b['rect']))
                        if b['kind'] == 'ability':
                            seen.add(b['payload']['ability_id'])
                self.assertEqual(seen, set(abilities))

    def test_constructor_building_label_and_progress_do_not_overlap_order(self):
        import pygame
        ship = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_construction)
        ship.order_type = 'move'
        ship.build_queue = [{'item': 'sensor_station', 'time_left': 5, 'total': 10}]
        records, bars = [], []
        original = self.view._label
        def label(x, y, text, color=None, font=None):
            records.append((str(text), pygame.Rect(x, y, *(font or self.view.font).size(str(text)))))
            original(x, y, text, color, font)
        original_bar = self.view._bar
        def bar(x, y, w, h, *args):
            bars.append(pygame.Rect(x, y, w, h))
            original_bar(x, y, w, h, *args)
        self.view._label, self.view._bar = label, bar
        self.view._left_panel({ship.id}, 0)
        order = next(r for s, r in records if s.startswith('ORDER:'))
        build = next(r for s, r in records if s.startswith('BUILDING'))
        self.assertFalse(order.colliderect(build))
        self.assertFalse(any(build.colliderect(r) for r in bars))

    def test_large_selection_scroll_reaches_every_row_and_clips_hitboxes(self):
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        ships = [self.game.factory.spawn_ship(sd.id, 0, Vec3()) for _ in range(60)]
        selection = {s.id for s in ships}
        self.view._left_panel(selection, 0)
        self.assertTrue(any(key == 'selection' for _, key in self.view.scroll_rects))
        seen = set()
        for off in range(0, 100, 3):
            self.view.scroll['selection'] = off
            self.view.buttons.clear()
            self.view.blocked_rects.clear()
            self.view._left_panel(selection, 0)
            seen.update(self.view.visible_selection_ids)
            panel = self.view.blocked_rects[0]
            for button in self.view.buttons:
                self.assertTrue(panel.contains(button['rect']))
        self.assertEqual(seen, selection)

    def test_button_rechecks_current_selected_owned_capable_ready_recipients(self):
        from types import SimpleNamespace
        from render.input import InputController
        import pygame
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        a = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        b = self.game.factory.spawn_ship(sd.id, 0, Vec3())
        enemy = self.game.factory.spawn_ship(sd.id, 1, Vec3())
        aid = sd.abilities[0]
        a.energy = b.energy = 1000
        b.ability_cooldowns[aid] = 10
        ctrl = InputController(self.st, SimpleNamespace(), self.view, SimpleNamespace(flash=lambda s: None))
        ctrl.selection = {a.id, b.id, enemy.id}
        self.view.buttons = [{'rect': pygame.Rect(10, 10, 100, 20), 'kind': 'ability',
            'payload': {'ability_id': aid, 'unit_ids': [a.id, b.id, enemy.id, 999999]}}]
        ctrl._click_button((20, 15))
        self.assertEqual(self.st.command_queue[-1].unit_ids, (a.id,))

    def test_later_ship_ability_union_counts_ready_and_cooldown(self):
        plain = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_construction)
        sd = next(s for s in self.view.ds.ships.values() if s.abilities)
        a = self.game.factory.spawn_ship(sd.id, 0, plain.pos.copy())
        b = self.game.factory.spawn_ship(sd.id, 0, plain.pos.copy())
        aid = sd.abilities[0]
        b.ability_cooldowns[aid] = 12
        a.energy = a.max_energy = 1000
        self.view._left_panel({plain.id, a.id, b.id}, 0)
        buttons = [b for b in self.view.buttons if b['kind'] == 'ability' and b['payload']['ability_id'] == aid]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]['payload']['unit_ids'], [a.id])
        self.assertTrue(any('1/2 ready' in s and '12s' in s for s in self.labels))
