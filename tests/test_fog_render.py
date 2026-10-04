"""View-side fog contracts. Fixtures deliberately expose no permissive fallback."""
import unittest
from types import SimpleNamespace
from game.core.vectors import Vec3
from render.input import InputController


class FogState:
    def __init__(self):
        from game.core.entity import Entity
        self.entities = {1: Entity(id=1, kind='ship', owner=0, data_id='imperial_corvette',
                                   pos=Vec3(10, 0, 10), is_ship=True),
                         2: Entity(id=2, kind='ship', owner=1, data_id='imperial_corvette',
                                   pos=Vec3(80, 0, 80), is_ship=True)}
        self.visible = {1}
    def entity(self, eid):
        return self.entities.get(eid)
    def can_see(self, pid, eid):
        return eid in self.visible
    def known_entity(self, pid, eid):
        return self.entity(eid) if self.can_see(pid, eid) else None


class FogInputTests(unittest.TestCase):
    def setUp(self):
        self.state = FogState()
        from render.camera import Camera
        self.camera = Camera(1280, 800)
        self.camera.world_to_screen = lambda x, y, z: (x, z)
        self.camera.follow_id, self.camera.target = 2, [80, 0, 80]
        self.input = InputController(self.state, self.camera, SimpleNamespace(), SimpleNamespace(flash=lambda s: None))

    def test_hidden_enemy_not_pickable(self):
        self.assertIsNone(self.input._pick_target((80, 80)))
        self.input._single_select(80, 80)
        self.assertEqual(self.input.selection, set())

    def test_lost_contact_drops_selection_and_follow_not_own_units(self):
        self.input.selection = {1, 2}
        self.input.update(0)
        self.assertEqual(self.input.selection, {1})
        self.assertIsNone(self.camera.follow_id)
        self.assertEqual(self.camera.target, [80, 0, 80])


class FogHUDTests(unittest.TestCase):
    def test_charted_planet_minimap_marker_is_dimmed(self):
        from game.core.state import GameState, PlayerState
        from game.systems.unit_factory import UnitFactory
        from game.systems.visibility import VisibilitySystem
        from render.hud import HUD
        st = GameState()
        st.players[0] = PlayerState(0)
        f = UnitFactory(st)
        scout = f.spawn_ship('imperial_corvette', 0, Vec3(100, 0, 0))
        planet = f.spawn_planet({'id': 'chart', 'type': 'barren', 'pos': [0, 0, 0], 'radius': 500})
        planet.colonized_by = 0
        visibility = VisibilitySystem(st)
        visibility.update()
        hud = HUD(1280, 800, st)
        hud._minimap(set(), 0)
        x, y = hud.minimap_rect.center
        visible = hud.overlay.get_at((x, y))
        scout.pos.x = -9000
        visibility.update()
        hud.overlay.fill((0, 0, 0, 0))
        hud._minimap(set(), 0)
        charted = hud.overlay.get_at((x, y))
        self.assertLess(sum(charted[:3]), sum(visible[:3])*.7)

    def test_hidden_trade_convoy_count_does_not_update_visible_station_readout(self):
        from game.core.state import GameState, PlayerState
        from game.systems.unit_factory import UnitFactory
        from game.core.entity import Entity
        from render.hud import HUD
        st = GameState()
        st.players[0] = PlayerState(0)
        st.players[1] = PlayerState(1)
        f = UnitFactory(st)
        own = f.spawn_ship('imperial_corvette', 0, Vec3(0, 0, 0))
        market = f.spawn_station('trade_station', 1, Vec3(50, 0, 0))
        f.spawn_station('trade_station', 0, Vec3(200, 0, 0))
        hud = HUD(1280, 800, st)
        before = hud._trade_line(market)
        hidden = Entity(id=99, kind='ship', owner=1, data_id='trade_convoy', pos=Vec3(10000, 0, 0))
        st.entities[99] = hidden
        self.assertEqual(hud._trade_line(market), before)

    def test_selected_unit_lists_its_effective_sensor_range(self):
        from game.core.state import GameState, PlayerState
        from game.systems.unit_factory import UnitFactory
        from render.hud import HUD
        from game.systems.stats import effective_sensor_range
        st = GameState()
        st.players[0] = PlayerState(0)
        e = UnitFactory(st).spawn_ship('imperial_corvette', 0, Vec3(0, 0, 0))
        hud = HUD(1280, 800, st)
        labels = []
        hud._label = lambda x, y, text, *args: labels.append(text)
        hud._left_panel({e.id}, 0)
        self.assertIn(f'SENSORS {effective_sensor_range(st, e):,.0f}u', labels)


class FogIntegrationTests(unittest.TestCase):
    def test_actual_state_position_contract_and_detector_loss(self):
        from game.core.state import GameState, PlayerState
        from game.systems.unit_factory import UnitFactory
        from game.systems.visibility import VisibilitySystem
        from game.data.store import DataStore
        from render.fog import FogMask, effect_visible
        DataStore.get()
        st = GameState()
        st.players[0] = PlayerState(0)
        st.players[1] = PlayerState(1)
        f = UnitFactory(st)
        scout = f.spawn_ship('imperial_corvette', 0, Vec3(0, 0, 0))
        enemy = f.spawn_ship('imperial_cruiser', 1, Vec3(10, 0, 0))
        VisibilitySystem(st).update()
        self.assertTrue(effect_visible(st, 0, {'pos': [10, 0, 0]}))
        mask = FogMask()
        mask.surface(st, 0)
        self.assertTrue(st.can_see(0, enemy.id))
        scout.alive = False
        VisibilitySystem(st).update()
        self.assertFalse(effect_visible(st, 0, {'pos': [10, 0, 0]}))
        self.assertFalse(st.can_see(0, enemy.id))


class FogMaskTests(unittest.TestCase):
    def test_mask_rebuild_does_not_rescan_sources_for_every_cell(self):
        from render.fog import FogMask
        class State:
            map_info = SimpleNamespace(bounds=1000)
            visibility_cell_size = 100
            explored_cells = {0: set()}
            calls = 0
            def sensor_sources(self, pid):
                self.calls += 1
                return [(SimpleNamespace(id=1, pos=Vec3(0, 0, 0)), 100)]
            def is_position_visible(self, pid, pos):
                return any((pos.x-e.pos.x)**2+(pos.z-e.pos.z)**2 <= r*r
                           for e, r in self.sensor_sources(pid))
            def is_position_explored(self, pid, pos):
                return False
        st = State()
        FogMask().surface(st, 0)
        self.assertLessEqual(st.calls, 2, 'fog repeatedly scans every source for each map cell')

    def test_mask_three_states_cached_and_invalidated(self):
        from render import fog
        self.assertTrue(hasattr(fog, 'FogMask'), 'no visual fog mask')
        st = SimpleNamespace(map_info=SimpleNamespace(bounds=1000), visibility_cell_size=500,
            explored_cells={0: {(0, 0)}}, tick=0,
            sensor_sources=lambda pid: [(SimpleNamespace(id=1, pos=Vec3(-250, 0, -250)), 200)],
            is_position_visible=lambda pid, pos: pos.x < 0 and pos.z < 0,
            is_position_explored=lambda pid, pos: pos.x >= 0 and pos.z >= 0)
        mask = fog.FogMask()
        surf = mask.surface(st, 0)
        self.assertEqual(surf.get_at((0, 0)).a, 0)
        self.assertEqual(surf.get_at((1, 0)).a, 255)
        self.assertGreater(surf.get_at((1, 1)).a, 0)
        self.assertLess(surf.get_at((1, 1)).a, 255)
        self.assertIs(mask.surface(st, 0), surf)
        st.explored_cells[0].add((1, 1))
        self.assertIsNot(mask.surface(st, 0), surf)


class FogViewTests(unittest.TestCase):
    def test_beam_cannot_bridge_two_separated_sensor_islands(self):
        from render.fog import effect_visible
        st = SimpleNamespace(is_position_visible=lambda pid, p: p.x < 100 or p.x > 900,
            sensor_sources=lambda pid: [(SimpleNamespace(pos=Vec3(0, 0, 0)), 100),
                                        (SimpleNamespace(pos=Vec3(1000, 0, 0)), 100)])
        self.assertFalse(effect_visible(st, 0, {'pos': [0, 0, 0], 'target_pos': [1000, 0, 0]}))

    def test_view_uses_snapshot_not_hidden_live_planet(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('render.fog'), 'fog graphics module missing')
        from render.fog import known_entities, effect_visible
        st = FogState()
        stale = SimpleNamespace(id=3, owner=-1, is_planet=True, alive=True, colonized_by=None)
        live = SimpleNamespace(id=3, owner=1, is_planet=True, alive=True, colonized_by=1)
        st.entities[3] = live
        st.known_entity = lambda pid, eid: stale if eid == 3 else (st.entity(eid) if eid in st.visible else None)
        self.assertEqual(list(known_entities(st, 0)), [st.entities[1], stale])
        st.is_position_visible = lambda pid, pos: pos.x < 30
        self.assertFalse(effect_visible(st, 0, {'pos': [80, 0, 80]}))
        self.assertFalse(effect_visible(st, 0, {'pos': [10, 0, 10], 'target_pos': [80, 0, 80]}))


if __name__ == '__main__':
    unittest.main()
