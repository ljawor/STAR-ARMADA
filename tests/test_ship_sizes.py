"""Visual-only catalogue proportions; no SDL/GL context needed."""
import unittest
from game.data.store import DataStore
from render.fleet_geometry import ship_mesh


class ShipSizesTests(unittest.TestCase):
    def test_catalogue_lengths_use_actual_all_role_bounds(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('render.ship_sizes'), 'visual size policy missing')
        from render import ship_sizes
        ds = DataStore.get()
        ratios = {'fighter_squadron': .6, 'corvette': 1., 'frigate': 1.5,
                  'cruiser': 2.5, 'battleship': 3.5, 'supercapital': 5.,
                  'construction': 1.}
        points = [p for mesh in ship_mesh('needle').values() for _,tri in mesh for p in tri]
        reference = (max(p[2] for p in points)-min(p[2] for p in points))*.7
        for did, data in ds.ships.items():
            with self.subTest(did=did):
                size = ship_sizes.ship_size(ds, did)
                points = [p for mesh in ship_mesh(size.shape).values() for _,tri in mesh for p in tri]
                actual = (max(p[2] for p in points)-min(p[2] for p in points))*size.scale
                self.assertAlmostEqual(actual, reference*ratios[data.category])
                self.assertLessEqual(actual, reference*5+1e-9)
        self.assertAlmostEqual(ship_sizes.ship_size(ds, 'imperial_corvette').scale, .7)

    def test_renderer_transform_ignores_restored_collision_radius(self):
        from unittest.mock import patch, Mock
        from contextlib import ExitStack, nullcontext
        from types import SimpleNamespace
        from game.core.entity import Entity
        from render import renderer as module
        from render.ship_sizes import ship_size
        from OpenGL import GL
        r = module.Renderer.__new__(module.Renderer)
        r.ds = DataStore.get()
        r.local_player = 0
        r.camera = SimpleNamespace(world_to_screen=lambda *args: (0, 0))
        r._px_per_world = lambda pos, **kw: 1.
        r._owner_color = lambda owner: (.3, .5, .9)
        r._ship_display_list = lambda shape: 1
        r._material_metal = r._material_matte = lambda *args: None
        r.materials = SimpleNamespace(use=lambda *args, **kw: nullcontext(), hull_pass=lambda *args: None)
        from game.core.manager import GameManager
        from game.core.state import GameState
        import copy
        st = GameManager.start_skirmish(r.ds.maps['skirmish01']).state
        e = Entity(id=1, kind='ship', owner=0, data_id='imperial_supercapital')
        e.is_ship = True
        st.entities = {e.id:e}
        restored = GameState.from_dict(st.to_dict(precise=True))
        e = restored.entities[1]
        r.state = restored
        with ExitStack() as stack:
            for name, value in vars(module).items():
                if name.startswith('gl') and callable(value): stack.enter_context(patch.object(module, name, Mock()))
            for name in ('glEnable', 'glDisable'): stack.enter_context(patch.object(GL, name, Mock()))
            for radius in (1., 260., 2600.):
                e.radius = radius
                before = copy.deepcopy(restored.to_dict(precise=True))
                r._draw_ship(e)
                self.assertEqual(restored.to_dict(precise=True), before)
                expected = ship_size(r.ds, e.data_id).scale
                self.assertEqual(module.glScalef.call_args.args, (expected,)*3)
            from game.core.vectors import Vec3
            e.vel = Vec3(0., 0., 64.)
            r._in_front = lambda *args: True
            r._draw_glow = Mock()
            module.glVertex3f.reset_mock()
            with patch.object(module, 'segment_visible', return_value=True) as visibility, \
                    patch.object(GameState, 'is_position_visible', return_value=True):
                before = copy.deepcopy(restored.to_dict(precise=True))
                r._draw_ship(e)
                self.assertEqual(restored.to_dict(precise=True), before)
                trail_tip = module.glVertex3f.call_args_list[0].args
                tested_tail = visibility.call_args.args[3]
                self.assertAlmostEqual(tested_tail.z, trail_tip[2]+e.pos.z)
                size = r._ship_size(e)
                self.assertEqual(r._draw_glow.call_args.args[0], (0.,0.,size.stern))

    def test_equal_depth_readability_keeps_catalogue_ratios(self):
        from render import ship_sizes
        self.assertTrue(hasattr(ship_sizes, 'readable_size'), 'shared readability policy missing')
        ds = DataStore.get()
        for ppw in (1., .1, .01, .001):
            ref = ship_sizes.readable_size(ds, 'imperial_corvette', ppw)
            for did, data in ds.ships.items():
                size = ship_sizes.readable_size(ds, did, ppw)
                self.assertAlmostEqual(size.length/ref.length, ship_sizes.RATIOS[data.category])
                self.assertLessEqual(size.length, 5*ref.length+1e-8)
            self.assertAlmostEqual(ref.scale, max(.7, 7./(26*ppw)))
        for did in ('trade_convoy', 'unknown_mod_ship'):
            self.assertLessEqual(ship_sizes.readable_size(ds, did, .001).length/ref.length, 1.5)

    def test_shields_and_motion_use_visual_bounds_not_collision_radius(self):
        from types import SimpleNamespace
        from game.core.entity import Entity
        from render.renderer import Renderer
        from render.ship_sizes import readable_size
        r = Renderer.__new__(Renderer)
        r.ds = DataStore.get()
        r._px_per_world = lambda pos, **kw: 1.
        e = Entity(id=1, kind='ship', owner=0, data_id='imperial_supercapital', radius=2600.)
        e.is_ship = True
        size = readable_size(r.ds, e.data_id, 1.)
        self.assertAlmostEqual(r._shield_radius(e), size.radius*1.08)
        self.assertTrue(hasattr(r, '_ship_size'), 'motion attachment sizing missing')
        self.assertEqual(r._ship_size(e), size)
        e.is_ship = False
        e.is_station = True
        self.assertAlmostEqual(r._shield_radius(e), e.radius*1.35)

    def test_hit_contacts_remap_without_mutating_saved_effect(self):
        from game.core.entity import Entity
        from game.core.vectors import Vec3
        from render.renderer import Renderer
        from render.ship_sizes import readable_size
        import copy
        r = Renderer.__new__(Renderer)
        r.ds = DataStore.get()
        r._px_per_world = lambda pos, **kw: 1.
        e = Entity(id=1, kind='ship', owner=0, data_id='imperial_supercapital', radius=260.)
        e.is_ship = True
        from types import SimpleNamespace
        r.local_player = 0
        r.state = SimpleNamespace(entities={1:e}, can_see=lambda *args: True)
        self.assertTrue(hasattr(r, '_visual_hit'), 'hit contact remapping missing')
        fx = dict(kind='shield_hit', target_id=1, center=(0,0,0), normal=(0,0,1), pos=(0,0,351), radius=351., size=18.)
        before = copy.deepcopy(fx)
        mapped = r._visual_hit(fx)
        self.assertAlmostEqual(mapped['radius'], r._shield_radius(e))
        self.assertEqual(mapped['pos'], (0., 0., mapped['radius']))
        self.assertLessEqual(mapped['size'], r._ship_size(e).length*.12)
        self.assertEqual(fx, before)
        fx['kind'] = 'hull_hit'
        mapped = r._visual_hit(fx)
        self.assertLessEqual(mapped['pos'][2], r._ship_size(e).radius)
        self.assertAlmostEqual(mapped['pos'][2], 108.*r._ship_size(e).scale)

    def _hit_fog_scene(self, target_x=1100.):
        from game.core.manager import GameManager
        from game.core.vectors import Vec3
        from render.renderer import Renderer
        gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        st = gm.state
        st.entities.clear()
        observer = gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        observer.sensor_range = 1000.
        target = gm.factory.spawn_ship('imperial_supercapital', 1, Vec3(target_x, 0, 0))
        target.radius = 260.
        r = Renderer.__new__(Renderer)
        r.ds, r.state, r.local_player = DataStore.get(), st, 0
        r._px_per_world = lambda pos, **kw: 1.
        return gm, r, observer, target

    def test_hidden_hit_keeps_visible_historical_contact_without_following_target(self):
        import copy
        from unittest.mock import patch
        from game.core.vectors import Vec3
        from render.fog import effect_visible
        gm, r, observer, target = self._hit_fog_scene()
        gm.damage._spawn_hit('hull_hit', target, Vec3(944, 0, 0), observer, 14.)
        fx = r.state.effects[0]
        cached = copy.deepcopy(fx)
        self.assertTrue(effect_visible(r.state, 0, fx))
        for x in (1100., 1400., None):
            if x is None:
                r.state.entities.pop(target.id)
            else:
                target.pos.x = x
            self.assertFalse(r.state.can_see(0, target.id))
            saved = copy.deepcopy(r.state.to_dict(precise=True))
            with patch('render.hit_effects.draw_hit') as draw:
                r._draw_hits()
            self.assertEqual(draw.call_count, 1, 'legal static ballistic contact was suppressed')
            self.assertEqual(draw.call_args.args[1], cached, 'hidden target leaked into contact')
            self.assertEqual(r.state.effects[0], cached)
            self.assertEqual(r.state.to_dict(precise=True), saved)

    def test_visible_target_remap_outside_sensor_is_not_drawn(self):
        import copy
        from unittest.mock import patch
        from game.core.vectors import Vec3
        from render.fog import effect_visible
        gm, r, observer, target = self._hit_fog_scene(800.)
        gm.damage._spawn_hit('hull_hit', target, Vec3(956, 0, 0), observer, 14.)
        target.pos.x = 990.
        fx = r.state.effects[0]
        self.assertTrue(r.state.can_see(0, target.id))
        self.assertTrue(effect_visible(r.state, 0, fx))
        self.assertFalse(effect_visible(r.state, 0, r._visual_hit(fx)))
        saved, cached = copy.deepcopy(r.state.to_dict(precise=True)), copy.deepcopy(fx)
        with patch('render.hit_effects.draw_hit') as draw:
            r._draw_hits()
        draw.assert_not_called()
        self.assertEqual(fx, cached)
        self.assertEqual(r.state.to_dict(precise=True), saved)

    def test_hidden_hit_does_not_read_live_transform(self):
        from types import SimpleNamespace
        from render.renderer import Renderer
        class HiddenTarget:
            @property
            def pos(self):
                raise AssertionError('hidden live position read')
            is_station, is_ship, is_squadron = False, True, False
        r = Renderer.__new__(Renderer)
        r.local_player = 0
        r.state = SimpleNamespace(entities={1: HiddenTarget()}, can_see=lambda *args: False)
        fx = dict(kind='hull_hit', target_id=1, pos=(944, 0, 0))
        self.assertIs(r._visual_hit(fx), fx)

    def test_allied_always_visible_remap_still_obeys_contact_sensor_gate(self):
        from unittest.mock import patch
        from game.core.vectors import Vec3
        gm, r, observer, target = self._hit_fog_scene()
        r.state.players[0].team = r.state.players[1].team = 7
        target.sensor_range = 0.
        gm.damage._spawn_hit('hull_hit', target, Vec3(944, 0, 0), observer, 14.)
        self.assertTrue(r.state.can_see(0, target.id))
        self.assertNotEqual(r._visual_hit(r.state.effects[0])['pos'], r.state.effects[0]['pos'])
        with patch('render.hit_effects.draw_hit') as draw:
            r._draw_hits()
            draw.assert_not_called()
            target.pos.x = 900.
            r._draw_hits()
            self.assertEqual(draw.call_count, 1)
            self.assertTrue(draw.call_args.args[1]['visual_contact'])

    def test_equal_camera_depth_has_equal_lod_even_off_axis(self):
        from render.renderer import Renderer
        from render.camera import Camera
        r = Renderer.__new__(Renderer)
        r.camera = Camera(960, 720)
        r.camera.yaw, r.camera.pitch, r.camera.distance = 0., 90., 3000.
        self.assertAlmostEqual(r._px_per_world((0,0,0), camera_depth=True),
                               r._px_per_world((2500,0,0), camera_depth=True))

    def test_station_projection_keeps_committed_distance_policy(self):
        import math
        from render.renderer import Renderer
        from render.camera import Camera
        r=Renderer.__new__(Renderer); r.camera=Camera(960,720)
        r.camera.yaw,r.camera.pitch,r.camera.distance=0.,90.,3000.
        expected=720/(2*math.hypot(3000.,2500.)*math.tan(math.radians(55./2)))
        self.assertAlmostEqual(r._px_per_world((2500,0,0)),expected)

    def test_draw_hit_respects_visual_shell_radius(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from render import hit_effects
        r = SimpleNamespace(_px_per_world=lambda pos: .1, camera=SimpleNamespace(yaw=0.,pitch=60.))
        fx = dict(kind='shield_hit', pos=(0,0,10), center=(0,0,0), radius=10., visual_contact=True)
        with patch.object(hit_effects, 'hit_geometry', return_value=dict(triangles=[],lines=[])) as geometry:
            hit_effects.draw_hit(r, fx)
            self.assertEqual(geometry.call_args.kwargs['radius'], 10.)

    def test_picking_includes_visual_bow_without_collision_radius_growth(self):
        from render.input import InputController
        from render.camera import Camera
        from game.core.entity import Entity
        from types import SimpleNamespace
        e = Entity(id=7, kind='ship', owner=0, data_id='imperial_supercapital', radius=2600.)
        e.is_ship=True
        cam=Camera(960,720)
        cam.yaw,cam.pitch,cam.distance=0.,90.,900.
        # Deterministic top-down projection, no GL context needed.
        cam.world_to_screen=lambda x,y,z: (480+x,360-z)
        ctl=InputController(SimpleNamespace(entities={7:e},can_see=lambda *args: True),cam,None,None)
        ctl._single_select(480,220)
        self.assertEqual(ctl.selection,{7}, 'visual bow cannot be selected')
        self.assertIs(ctl._pick_target((480,220)),e)
        self.assertIsNone(ctl._pick_target((900,220)), 'collision radius created a giant pick target')


if __name__ == '__main__': unittest.main()
