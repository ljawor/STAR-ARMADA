"""Planetary view consumes the surface-building API, never pays or allocates."""
import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game
from render.hud import HUD
from render.camera import Camera
from render.input import InputController
from game.systems.planet_buildings import BUILDING_TYPES, building_rules


class PlanetBuildingUITests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False); self.st = self.gm.state
        from game.systems.colonies import eligible_planet
        self.planet = next(e for e in self.st.entities.values() if eligible_planet(e))
        self.planet.colonized_by = 0
        observer = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_ship)
        observer.pos = self.planet.pos.copy()
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud, SimpleNamespace(flash=lambda *_: None))
        self.ctrl.selection = {self.planet.id}
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000
        self.labels = []
        original = self.hud._label
        def label(x, y, text, color=None, font=None):
            self.labels.append((str(text), pygame.Rect(x, y, *(font or self.hud.font).size(str(text)))))
            original(x, y, text, color, font)
        self.hud._label = label

    def draw(self):
        self.hud.buttons.clear(); self.hud.blocked_rects.clear(); self.hud.scroll_rects.clear(); self.labels.clear()
        self.hud._right_panel(self.ctrl.selection, 0)

    def test_surface_catalogue_pages_and_slots_are_separate_from_satellites(self):
        seen = set(); before = self.st.to_dict(precise=True)
        for size in ((1280, 800), (1024, 768)):
            self.hud.resize(*size)
            for offset in range(4):
                self.hud.scroll['planet_buildings'] = offset
                self.draw()
                rows = [b for b in self.hud.buttons if b['kind'] == 'build_planet_building']
                self.assertTrue(rows, 'owned colony must offer surface builds')
                panel = self.hud.blocked_rects[0]
                self.assertTrue(all(panel.contains(r) for _, r in self.labels))
                for b in rows:
                    seen.add(b['payload']['station_kind'])
                    data = self.hud.ds.stations[b['payload']['station_kind']]
                    self.assertTrue(any(f'{data.crew_cost:,.0f} crew' in t and b['rect'].contains(r) for t, r in self.labels))
                self.assertTrue(any('SURFACE 0/6' in t and 'ORBIT 0/6' in t for t, _ in self.labels))
        self.assertEqual(seen, set(BUILDING_TYPES))
        self.assertEqual(before, self.st.to_dict(precise=True))

    def click(self, point):
        for event in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(event, button=1, pos=point))

    def test_stale_build_rows_cannot_act_after_page_selection_or_owner_changes(self):
        self.draw()
        row = next(b for b in self.hud.buttons if b['kind'] == 'build_planet_building')
        page = next(b for b in self.hud.buttons if b['kind'] == 'hud_planet_page' and b['payload']['page'] == 'orbit')
        self.click(page['rect'].center)
        self.click(row['rect'].center)
        self.assertFalse(self.st.command_queue)
        self.hud.planet_page = 'surface'
        self.ctrl.selection.clear()
        self.click(row['rect'].center)
        self.assertFalse(self.st.command_queue)
        self.ctrl.selection = {self.planet.id}
        self.planet.colonized_by = 1
        self.click(row['rect'].center)
        self.assertFalse(self.st.command_queue)

    def test_colony_inspector_reports_base_and_surface_income_separately(self):
        from game.systems.planet_buildings import start_building
        start_building(self.gm.construction, self.planet.id, 'planet_trade_hub', 0)
        self.gm.construction.update(1000)
        self.hud._left_panel(self.ctrl.selection, 0)
        self.assertTrue(any('BASE COLONY' in t for t, _ in self.labels))
        self.assertTrue(any('SURFACE BONUS' in t for t, _ in self.labels))

    def test_enemy_surface_income_does_not_reveal_hidden_staffing(self):
        self.planet.colonized_by = 1
        building = self.gm.construction.factory.spawn_station('planet_extractor', 1,
            self.planet.pos.copy())
        building.planet_id = self.planet.id
        building.planet_building_slot = 0
        observer = next(e for e in self.st.entities.values() if e.owner == 0 and e.is_ship)
        observer.sensor_range = 10
        building.pos.x += 100000
        self.assertTrue(self.st.can_see(0, self.planet.id))
        self.assertFalse(self.st.can_see(0, building.id))
        self.hud._left_panel(self.ctrl.selection, 0)
        before = [t for t, _ in self.labels]
        building.crew = 0
        self.labels.clear()
        self.hud._left_panel(self.ctrl.selection, 0)
        self.assertEqual(before, [t for t, _ in self.labels])
        self.assertFalse(any('SURFACE BONUS' in t for t in before))

    def test_paid_slots_disable_surface_rows_but_not_orbit_builds(self):
        self.planet.build_queue = [dict(kind='planet_building', item=BUILDING_TYPES[0],
            slot=s, time_left=30, total=30, source_owner=0) for s in range(6)]
        self.draw()
        self.assertFalse(any(b['kind'] == 'build_planet_building' for b in self.hud.buttons))
        self.hud.planet_page = 'orbit'
        self.draw()
        self.assertTrue(any(b['kind'] == 'build_satellite' for b in self.hud.buttons))

    def test_real_input_queues_paid_surface_build_and_changes_orbit_page(self):
        self.draw()
        row = next(b for b in self.hud.buttons if b['kind'] == 'build_planet_building')
        before = self.st.to_dict(precise=True)
        self.click(row['rect'].center)
        self.assertEqual(len(self.st.command_queue), 1)
        cmd = self.st.command_queue[0]
        self.assertEqual((cmd.type, cmd.target_id, cmd.station_kind),
                         ('build_planet_building', self.planet.id, row['payload']['station_kind']))
        self.st.command_queue.clear()
        self.assertEqual(before, self.st.to_dict(precise=True))
        self.st.queue_command(cmd)
        self.gm.step(1 / 30)
        self.assertEqual(self.planet.build_queue[0]['kind'], 'planet_building')
        self.assertEqual(self.planet.build_queue[0]['slot'], 0)
        self.draw()
        page = next(b for b in self.hud.buttons if b['kind'] == 'hud_planet_page' and b['payload']['page'] == 'orbit')
        self.click(page['rect'].center)
        self.assertEqual(self.hud.planet_page, 'orbit')
        self.draw()
        self.assertTrue(any(b['kind'] == 'build_satellite' for b in self.hud.buttons))


if __name__ == '__main__': unittest.main()
