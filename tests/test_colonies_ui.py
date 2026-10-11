"""Real HUD overlay and input intent, without mocking catalogue decisions."""
import json
import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from game.core.vectors import Vec3
from render.camera import Camera
from render.hud import HUD
from render.input import InputController


class ColonyHUDTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        self.camera = Camera(1280, 800)
        self.camera.target = self.planet.pos.to_dict()
        self.camera.distance = 5000
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, self.camera, self.hud, SimpleNamespace(flash=lambda text: None))

    def tearDown(self):
        self.hud.close()

    def test_owned_planet_menu_queues_serialized_paid_build_only_in_tick(self):
        before = json.loads(json.dumps(self.st.to_dict(precise=True)))
        self.ctrl.selection = {self.planet.id}
        self.hud._right_panel(self.ctrl.selection, 0)
        buttons = [b for b in self.hud.buttons if b['kind'] == 'build_satellite']
        self.assertEqual(len(buttons), 2)
        self.assertEqual(before, json.loads(json.dumps(self.st.to_dict(precise=True))))
        self.ctrl._click_button(buttons[0]['rect'].center)
        self.assertEqual(self.st.command_queue[-1].type, 'build_satellite')
        self.assertEqual(self.planet.build_queue, [])
        self.gm.step(1 / 30)
        self.assertEqual(len(self.planet.build_queue), 1)

    def test_only_colony_owner_sees_live_production(self):
        self.planet.build_queue = [dict(item='attack_satellite', time_left=13.25, total=22)]
        labels = []
        self.hud._label = lambda x, y, text, *args: labels.append(str(text))
        self.hud._left_panel({self.planet.id}, 0)
        self.assertTrue(any('BUILDING ATTACK SATELLITE' in s for s in labels))
        self.planet.colonized_by = 1
        self.gm.factory.spawn_ship('imperial_corvette', 0, self.planet.pos + Vec3(100, 0, 0))
        self.assertTrue(self.st.can_see(0, self.planet.id))
        labels.clear()
        self.hud._left_panel({self.planet.id}, 0)
        self.assertFalse(any('BUILDING' in s for s in labels), labels)
        self.gm.visibility.update()
        for e in self.st.entities.values():
            if not e.is_planet:
                e.pos = Vec3(-12000, 0, -12000)
        self.gm.visibility.update()
        self.assertFalse(self.st.can_see(0, self.planet.id))
        labels.clear(); self.hud.buttons.clear()
        self.hud._left_panel({self.planet.id}, 0)
        self.hud._right_panel({self.planet.id}, 0)
        self.assertFalse(any('BUILDING' in s or 'ATTACK SATELLITE' in s for s in labels), labels)
        self.assertFalse(any(b['kind'] == 'build_satellite' for b in self.hud.buttons))

    def test_remembered_planet_contains_public_geometry_not_private_runtime(self):
        from game.core.state import GameState
        self.planet.colonized_by = 1
        self.planet.pos = Vec3(123.456789, 0, 789.123456)
        self.planet.radius = 501.23456789
        self.planet.build_queue = [dict(item='attack_satellite', time_left=13.25, total=22)]
        self.planet.weapon_cooldowns = {0: 8.75}
        self.planet.ability_cooldowns = {'secret': 9.5}
        self.planet.order_type = 'attack'
        self.planet.order_target_id = 777
        self.gm.factory.spawn_ship('imperial_corvette', 0, self.planet.pos + Vec3(100, 0, 0))
        self.gm.visibility.update()
        remembered = self.st.discovered_planets[0][self.planet.id]
        self.assertEqual(remembered.pos, self.planet.pos, 'rounded observed geometry')
        self.assertEqual(remembered.radius, self.planet.radius)
        self.assertEqual(remembered.build_queue, [], 'snapshot leaks production')
        self.assertEqual(remembered.weapon_cooldowns, {})
        self.assertEqual(remembered.ability_cooldowns, {})
        self.assertEqual(remembered.order_type, 'idle')
        self.assertIsNone(remembered.order_target_id)
        cells = set(self.st.explored_cells[0])
        for e in self.st.entities.values():
            if not e.is_planet:
                e.pos = Vec3(-12000, 0, -12000)
        self.planet.colonized_by = None
        self.gm.visibility.update()
        self.assertFalse(self.st.can_see(0, self.planet.id))
        known = self.st.known_entity(0, self.planet.id)
        self.assertEqual(known.colonized_by, 1, 'lost last-observed owner')
        self.assertEqual(known.pos, remembered.pos)
        self.assertEqual(known.radius, remembered.radius)
        self.assertTrue(cells <= self.st.explored_cells[0], 'erased fog history')
        saved = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameState.from_dict(saved)
        self.assertEqual(saved, json.loads(json.dumps(restored.to_dict(precise=True))))
        # Old saves may carry full enemy entities in memory. Sanitize on restore too.
        saved['discovered_planets']['0'][str(self.planet.id)]['build_queue'] = self.planet.build_queue
        restored = GameState.from_dict(saved)
        self.assertEqual(restored.discovered_planets[0][self.planet.id].build_queue, [])
        self.assertEqual(restored.explored_cells[0], self.st.explored_cells[0])

    def test_colony_ship_hint_uses_configured_control_timer(self):
        colony = self.gm.factory.spawn_ship('imperial_colonizer', 0, self.planet.pos)
        rules = self.hud.ds.rules.setdefault('colonies', {})
        previous = rules.get('control_seconds')
        rules['control_seconds'] = 27.5
        labels = []
        self.hud._label = lambda x, y, text, *args: labels.append(str(text))
        try:
            self.hud._right_panel({colony.id}, 0)
            self.assertIn('27.5 seconds', ' '.join(labels))
            self.assertNotIn('15 seconds', ' '.join(labels))
        finally:
            if previous is None:
                rules.pop('control_seconds')
            else:
                rules['control_seconds'] = previous

    def test_colony_panel_all_labels_fit_at_supported_resolutions(self):
        colony = self.gm.factory.spawn_ship('imperial_colonizer', 0, self.planet.pos + Vec3(0, 0, 1000))
        self.planet.build_queue = [dict(item='attack_satellite', time_left=13.25, total=22)]
        for width, height in ((1280, 800), (1024, 768)):
            hud = HUD(width, height, self.st)
            labels = []
            def label(x, y, text, color=None, font=None):
                labels.append((text, pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
            hud._label = label
            try:
                for selection in ({self.planet.id}, {colony.id}):
                    labels.clear(); hud.blocked_rects.clear()
                    hud._left_panel(selection, 0); hud._right_panel(selection, 0)
                    for text, rect in labels:
                        self.assertTrue(any(p.contains(rect) for p in hud.blocked_rects),
                                        f'{width}: {text} outside panels: {rect}')
            finally:
                hud.close()

    def test_satellite_meshes_have_canonical_faction_roles_not_research_fallback(self):
        from render.fleet_geometry import station_mesh
        from render.faction_visuals import normalize_station_key
        for faction in ('imperial', 'rebel', 'confederacy'):
            for role in ('defense_satellite', 'attack_satellite'):
                self.assertEqual(normalize_station_key(role, faction), (faction, role))
                mesh = station_mesh(role, faction)
                self.assertGreater(len(mesh['base']), 20)
                self.assertTrue(mesh['accent'])
                self.assertNotEqual(mesh, station_mesh('research_station', faction))
            self.assertNotEqual(station_mesh('defense_satellite', faction), station_mesh('attack_satellite', faction))

    def test_actual_single_pick_selects_owned_terrain_planet(self):
        point = self.camera.world_to_screen(*self.planet.pos.to_dict())
        self.ctrl._single_select(*point)
        self.assertEqual(self.ctrl.selection, {self.planet.id})

    def test_colony_labels_income_progress_and_no_constructor_menu(self):
        labels = []
        original = self.hud._label
        def label(x, y, text, *args):
            labels.append(str(text))
            original(x, y, text, *args)
        self.hud._label = label
        self.hud._left_panel({self.planet.id}, 0)
        self.assertTrue(any('COLONY OWNER' in s and 'Player' in s for s in labels))
        self.assertTrue(any('INCOME' in s for s in labels))
        self.assertIn('crew: 2', labels)
        self.assertIn('credits: 6', labels)
        self.planet.colonized_by = None
        ship = self.gm.factory.spawn_ship('imperial_colonizer', 0, self.planet.pos + Vec3(0, 0, 1000))
        self.gm.construction.start_colonize(ship.id, self.planet.id, 0)
        self.gm.step(1 / 30)
        labels.clear()
        self.hud._left_panel({ship.id}, 0)
        self.hud._right_panel({ship.id}, 0)
        self.assertTrue(any('COLONIZING' in s for s in labels))
        self.assertTrue(any('COLONY SHIP' in s for s in labels))
        self.assertFalse(any('ORBITAL CONSTRUCTION' in s for s in labels))

    def test_planet_right_click_capture_and_command_only_catalogue(self):
        self.planet.colonized_by = 1
        colony = self.gm.factory.spawn_ship('imperial_colonizer', 0, self.planet.pos + Vec3(0, 0, 1000))
        self.ctrl.selection = {colony.id}
        point = self.camera.world_to_screen(*self.planet.pos.to_dict())
        self.assertIs(self.ctrl._pick_target(point), self.planet)
        self.ctrl._right_click(point)
        self.assertEqual(self.st.command_queue[-1].type, 'colonize')
        yard = next(e for e in self.st.entities.values() if e.owner == 0 and e.data_id == 'shipyard')
        command = next(e for e in self.st.entities.values() if e.owner == 0 and e.data_id == 'command_station')
        self.assertNotIn(colony.data_id, [s.id for s in self.hud._shipyard_items(yard, self.hud.ds.stations[yard.data_id])])
        self.assertIn(colony.data_id, [s.id for s in self.hud._shipyard_items(command, self.hud.ds.stations[command.data_id])])
        self.assertTrue(all(s.faction == 'imperial' for s in self.hud._shipyard_items(command, self.hud.ds.stations[command.data_id])))
