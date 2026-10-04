"""Close-camera regressions use factory-spawned hardware, not fake radii."""
import math
import unittest
from types import SimpleNamespace
import pygame
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.unit_factory import UnitFactory
from render.camera import Camera
from render.input import InputController


class CameraSafetyTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.st = GameManager.start_skirmish(DataStore.get().maps['skirmish01']).state
        self.st.entities.clear()
        self.base = UnitFactory(self.st).spawn_station('command_station', 0, Vec3(0, 0, 0))
        self.cam = Camera(960, 640)
        self.hud = SimpleNamespace(minimap_rect=pygame.Rect(740, 420, 200, 200))
        self.input = InputController(self.st, self.cam, self.hud, SimpleNamespace(flash=lambda *_: None))

    def test_separated_real_fleets_do_not_scan_irrelevant_enemy_visibility(self):
        from unittest.mock import patch
        from game.systems.visibility import SensorQueries
        from game.systems import stats
        for count in (250, 500):
            with self.subTest(per_side=count):
                self.st.entities.clear()
                factory = UnitFactory(self.st)
                for owner, x in ((0, -11000), (1, 11000)):
                    for i in range(count):
                        factory.spawn_ship('imperial_corvette', owner, Vec3(x, 0, i * 2))
                self.cam.target = [-11000., 0., 0.]
                self.cam.distance, self.cam.pitch, self.cam.yaw = 180., 55., 45.
                before = self.st.to_dict(precise=True)
                original = SensorQueries._covers
                calls = []
                def covers(queries, entity, pos):
                    calls.append(entity.id)
                    return original(queries, entity, pos)
                with patch.object(type(self.st), 'can_see', autospec=True, side_effect=type(self.st).can_see) as visible, \
                        patch.object(SensorQueries, '_covers', covers), \
                        patch.object(stats, 'effective_sensor_range', wraps=stats.effective_sensor_range) as ranges:
                    self.cam.refresh_scene()
                self.assertEqual(self.st.to_dict(precise=True), before)
                self.assertEqual(len(calls), 0, 'off-ray enemies must not exhaustively scan observers')
                self.assertEqual(ranges.call_count, 0)
                self.assertLessEqual(visible.call_count, count)

    def test_held_pan_refreshes_once_after_camera_motion(self):
        from unittest.mock import patch
        from render.camera_geometry import scene_boxes
        self.input.keys.add(pygame.K_d)
        with patch('render.camera_geometry.scene_boxes', wraps=scene_boxes) as boxes:
            self.input.update(1 / 30)
            self.cam.eye_position()
        self.assertEqual(boxes.call_count, 1, 'refresh must use the final pan/follow target')

    def test_scene_unbinding_clears_keepouts_and_rebinding_resets_animation(self):
        self.cam.target, self.cam.distance, self.cam.pitch = [0., 0., 0.], 180., 8.
        self.cam.bind_scene(self.st, lambda: 0, lambda: .75)
        self.assertNotEqual(self.cam.eye_position(), self.cam._requested_eye())
        self.cam.bind_scene(None, lambda: 0)
        self.assertEqual(self.cam._camera_boxes, ())
        self.assertEqual(self.cam.eye_position(), self.cam._requested_eye())
        self.cam.bind_scene(self.st, lambda: 0)
        self.assertEqual(self.cam._station_angle(), 0.)
        self.assertNotEqual(self.cam.eye_position(), self.cam._requested_eye())

    def test_same_tick_scene_refresh_rechecks_spawns_movement_ownership_and_sensors(self):
        self.st.entities.clear()
        f = UnitFactory(self.st)
        self.cam.target, self.cam.distance, self.cam.pitch = [0., 0., 0.], 180., 8.
        observer = f.spawn_ship('imperial_corvette', 0, Vec3(-5000, 0, 0))
        observer.sensor_range = 0.
        tick = self.st.tick
        def check():
            from render.camera_geometry import scene_boxes, safe_eye
            before = self.st.to_dict(precise=True)
            self.cam.refresh_scene()
            expected = safe_eye(self.cam.target, self.cam._requested_eye(),
                scene_boxes(self.st, 0, 0.), self.cam.near, self.cam.fov,
                self.cam.width / self.cam.height, self.cam.height)
            self.assertEqual(self.cam.eye_position(), expected)
            self.assertEqual(self.st.to_dict(precise=True), before)
            self.assertEqual(self.st.tick, tick)
            return expected
        empty = check()
        enemy = f.spawn_station('command_station', 1, Vec3())
        self.assertEqual(check(), empty)
        observer.sensor_range = 10000.
        detected = check()
        self.assertNotEqual(detected, empty)
        observer.ability_active['sensor_jammed'] = 10.
        self.assertEqual(check(), empty)
        observer.ability_active.clear()
        self.assertEqual(check(), detected)
        observer.systems['sensors'].hp = 0.
        self.assertEqual(check(), empty)
        observer.systems['sensors'].hp = observer.systems['sensors'].max_hp
        self.assertEqual(check(), detected)
        ds = DataStore.get()
        self.st.map_info.nebulas = [dict(pos=[-5000, 0, 0], radius=100)]
        ds.rules.setdefault('sensors', {})['nebula_detection_multiplier'] = .1
        self.assertEqual(check(), empty)
        ds.rules['sensors']['nebula_detection_multiplier'] = 1.
        self.assertEqual(check(), detected)
        self.st.map_info.nebulas.clear()
        observer.sensor_range = 0.
        enemy.owner = 0
        self.assertEqual(check(), detected)
        enemy.pos.x = 6000.
        self.assertEqual(check(), empty)
        enemy.pos.x = 0.
        self.assertEqual(check(), detected)
        enemy.alive = False
        self.assertEqual(check(), empty)
        enemy.alive = True
        self.assertEqual(check(), detected)
        self.st.entities.pop(enemy.id)
        self.assertEqual(check(), empty)
        replacement = f.spawn_station('command_station', 0, Vec3())
        self.assertEqual(check(), detected)
        replacement.owner = 1
        self.assertEqual(check(), empty)

    def test_filtered_geometry_matches_exhaustive_after_direct_camera_config_changes(self):
        from render.camera_geometry import scene_boxes, safe_eye
        f = UnitFactory(self.st)
        ds = DataStore.get()
        data_id = next(s.id for s in ds.ships.values() if s.category == 'supercapital')
        f.spawn_ship(data_id, 0, Vec3(130, 40, 170))
        f.spawn_station('sensor_station', 0, Vec3(300, 100, 300))
        before = self.st.to_dict(precise=True)
        for height, width, near, fov in ((640, 960, 20., 55.), (64, 96, 40., 90.),
                                         (800, 1600, 1., 35.)):
            self.cam.height, self.cam.width, self.cam.near, self.cam.fov = height, width, near, fov
            for target in ([0., 0., 0.], [-135.4, 0., -135.4], [400., 0., 400.]):
                self.cam.target = target
                for pitch in (8., 55., 89.):
                    for yaw in (0., 45., 225.):
                        self.cam.pitch, self.cam.yaw, self.cam.distance = pitch, yaw, 180.
                        expected = safe_eye(target, self.cam._requested_eye(),
                            scene_boxes(self.st, 0, 0.), near, fov, width / height, height)
                        self.assertEqual(self.cam.eye_position(), expected)
        self.assertEqual(self.st.to_dict(precise=True), before)

    def test_minimap_icon_click_cannot_put_eye_inside_real_command_tower(self):
        self.cam.distance, self.cam.pitch, self.cam.yaw = 180., 8., 45.
        before = self.st.to_dict(precise=True)
        self.input._minimap_jump((839, 519))
        eye = self.cam.eye_position()
        # Real command hardware bounds are +/-161.2 XZ, -20.8..143 Y.
        inside = -161.2 < eye[0] < 161.2 and -20.8 < eye[1] < 143. and -161.2 < eye[2] < 161.2
        self.assertFalse(inside, f'eye {eye} is inside real base hardware')
        self.assertEqual(self.cam.distance, 180., 'safety must preserve requested ship zoom')
        self.assertEqual(self.st.to_dict(precise=True), before)

    def test_low_pitch_projection_and_ground_pick_use_the_rendered_eye(self):
        self.cam.distance, self.cam.pitch, self.cam.yaw = 180., 8., 45.
        self.input._minimap_jump((839, 519))
        self.cam._proj = self.cam._view = object()  # analytic methods need no GL context
        screen = self.cam.world_to_screen(*self.cam.target)
        self.assertAlmostEqual(screen[0], 480., places=8)
        self.assertAlmostEqual(screen[1], 320., places=8)
        world = self.cam.screen_to_world(480., 320.)
        for a, b in zip(world, self.cam.target):
            self.assertAlmostEqual(a, b, places=8)
    def test_renderer_and_ship_picking_depth_share_low_pitch_basis(self):
        from render.renderer import Renderer
        self.cam.distance, self.cam.pitch = 180., 8.
        self.input._minimap_jump((839, 519))
        r = Renderer.__new__(Renderer)
        r.camera = self.cam
        right, up, fwd = self.cam.basis()
        rr, ru, toward = r._camera_basis()
        for actual, expected in ((rr, right), (ru, up), (toward, tuple(-v for v in fwd))):
            for a, b in zip(actual, expected):
                self.assertAlmostEqual(a, b, places=10)
        distance = math.dist(self.cam.target, self.cam.eye_position())
        expected = self.cam.height / (2 * distance * math.tan(math.radians(self.cam.fov / 2)))
        self.assertAlmostEqual(r._px_per_world(self.cam.target, camera_depth=True), expected, places=10)
    def test_planet_escape_uses_rendered_sphere_not_box_corners(self):
        self.st.entities.clear()
        planet = UnitFactory(self.st).spawn_planet(dict(id='test', type='temperate', pos=[0, 0, 0], radius=300))
        from game.systems.visibility import VisibilitySystem
        UnitFactory(self.st).spawn_ship('imperial_corvette', 0, Vec3(100, 0, 0))
        VisibilitySystem(self.st).update()
        self.cam.target = [0., 0., 0.]
        self.cam.distance, self.cam.pitch = 180., 55.
        self.input.update(0)
        self.assertGreater(math.dist(self.cam.eye_position(), (0, 0, 0)), planet.radius * 1.018 + self.cam.near)
        self.cam.target = [400., 0., 400.]
        self.input.update(0)
        self.assertAlmostEqual(math.dist(self.cam.eye_position(), self.cam.target), 180.)
    def test_camera_escapes_real_ship_hardware_without_using_collision_radius(self):
        from render.ship_sizes import ship_size, _bounds
        self.st.entities.clear()
        ds = DataStore.get()
        data_id = next(s.id for s in ds.ships.values() if s.category == 'supercapital')
        ship = UnitFactory(self.st).spawn_ship(data_id, 0, Vec3(0, 60, 0))
        ship.radius = 1e6  # saves/mods may carry physics-only inflated radii
        self.cam.target = [-135.41666666666666, 0., -135.41666666666666]
        self.cam.distance, self.cam.pitch = 180., 8.
        self.input.update(0)
        size = ship_size(ds, data_id)
        lo, hi, _ = _bounds(size.shape)
        eye = tuple(self.cam.eye_position()[i] - (ship.pos.x, ship.pos.y, ship.pos.z)[i] for i in range(3))
        self.assertFalse(all(lo[i] * size.scale < eye[i] < hi[i] * size.scale for i in range(3)))
        self.assertLess(math.dist(self.cam.eye_position(), self.cam.target), 1000.)
        ship.pos = Vec3(6000, 0, 6000)
        self.input.update(0)
        self.assertAlmostEqual(math.dist(self.cam.eye_position(), self.cam.target), math.hypot(180 * math.cos(math.radians(8)), 60))
    def test_audio_attenuation_and_pan_use_the_same_effective_eye(self):
        from render.audio import Audio, _REF_DIST
        self.cam.distance, self.cam.pitch = 180., 8.
        self.input._minimap_jump((839, 519))
        audio = Audio.__new__(Audio)
        audio.camera = self.cam
        eye = self.cam.eye_position()
        gain, pan = audio._spatial(eye)
        self.assertAlmostEqual(gain, 1., places=10)
        self.assertAlmostEqual(pan, 0., places=10)
        pos = (eye[0], eye[1] + 100., eye[2])
        gain, pan = audio._spatial(pos)
        self.assertAlmostEqual(gain, 1. / (1. + (100. / _REF_DIST) ** 1.4), places=10)
        self.assertAlmostEqual(pan, 0., places=10)
    def test_minimap_recentering_detaches_follow_without_changing_zoom(self):
        self.cam.follow_id = self.base.id
        self.cam.distance = 180.
        self.input._minimap_jump((839, 519))
        target = list(self.cam.target)
        self.input.update(0)
        self.assertIsNone(self.cam.follow_id)
        self.assertEqual(self.cam.target, target)
        self.assertEqual(self.cam.distance, 180.)
    def assert_clear(self):
        from render.camera_geometry import box_interval
        eye = self.cam.eye_position()
        delta = tuple(eye[i] - self.cam.target[i] for i in range(3))
        length = math.sqrt(sum(v*v for v in delta))
        direction = tuple(v / length for v in delta)
        clearance = self.cam.near * math.sqrt(1. + math.tan(math.radians(self.cam.fov / 2))**2 * (1. + (self.cam.width/self.cam.height)**2)) + 2.
        for obstacle in self.cam._camera_boxes:
            interval = box_interval(self.cam.target, direction, obstacle, clearance)
            self.assertFalse(interval is not None and interval[0] <= length <= interval[1], (eye, obstacle))

    def test_crowded_base_rotation_pan_follow_and_direct_mutations_are_safe(self):
        f = UnitFactory(self.st)
        for data_id, pos in [('sensor_station', (170, 100, 150)), ('shipyard', (320, 0, 300)), ('command_station', (400, 130, 400))]:
            f.spawn_station(data_id, 0, Vec3(*pos))
        before = self.st.to_dict(precise=True)
        for pitch in (8., 20., 55., 89.):
            for yaw in (0., 45., 90., 180., 225., 315.):
                self.cam.target = [-135.4, 0., -135.4]
                self.cam.distance, self.cam.pitch, self.cam.yaw = 180., pitch, yaw
                self.input.update(0)
                self.assert_clear()
                self.cam.rotate(17., -3.)
                self.assert_clear()
                self.cam.pan(35., -21.)
                self.assert_clear()
                self.cam.distance = 25.  # diagnostics/direct writes bypass zoom()
                self.assert_clear()
        self.cam.follow_id = self.base.id
        self.input.update(0)
        self.assertEqual(self.cam.target, [0., 0., 0.])
        self.assert_clear()
        self.assertEqual(self.st.to_dict(precise=True), before)

    def test_hidden_enemy_geometry_cannot_move_eye_or_reveal_contact(self):
        from game.systems.visibility import VisibilitySystem
        self.cam.target = [-135.4, 0., -135.4]
        self.cam.distance, self.cam.pitch = 180., 8.
        enemy = UnitFactory(self.st).spawn_station('sensor_station', 1, Vec3(190, 120, 190))
        self.base.sensor_range = 0.
        VisibilitySystem(self.st).update()
        self.assertFalse(self.st.can_see(0, enemy.id))
        self.input.update(0)
        eye = self.cam.eye_position()
        enemy.pos = Vec3(*eye)
        enemy.radius = 1e7
        self.input.update(0)
        self.assertEqual(self.cam.eye_position(), eye)
        self.assertFalse(self.st.can_see(0, enemy.id))

    def test_safe_empty_space_and_close_corvette_zoom_are_unchanged(self):
        self.st.entities.clear()
        ship = UnitFactory(self.st).spawn_ship('imperial_corvette', 0, Vec3(0, 0, 0))
        ship.radius = 1e6
        for target in ([0., 0., 0.], [6000., 0., 6000.]):
            self.cam.target = list(target)
            self.cam.distance, self.cam.pitch, self.cam.yaw = 300., 55., 45.
            self.input.update(0)
            control = Camera(960, 640)
            control.target = list(target)
            control.distance = 300.
            for _ in range(12):
                self.cam.zoom(.88)
                control.zoom(.88)
                self.assertEqual(self.cam.eye_position(), control.eye_position())
            self.assertEqual(self.cam.distance, 180.)
    def test_direct_top_down_pitch_keeps_yaw_basis(self):
        self.cam.pitch, self.cam.yaw = 90., 0.
        self.cam.target, self.cam.distance = [6000., 0., 6000.], 3000.
        self.input.update(0)
        right, _, _ = self.cam.basis()
        self.assertEqual(right, (1., 0., 0.))
        x, y = self.cam.world_to_screen(6010., 0., 6000.)
        self.assertGreater(x, self.cam.width / 2)
        self.assertAlmostEqual(y, self.cam.height / 2, places=8)
    def test_ship_behind_eye_does_not_get_an_enormous_readability_boost(self):
        from render.renderer import Renderer
        from render.ship_sizes import ship_size
        ship = UnitFactory(self.st).spawn_ship('imperial_corvette', 0, Vec3(1000, 0, 1000))
        self.cam.target, self.cam.distance = [0., 0., 0.], 180.
        r = Renderer.__new__(Renderer)
        r.camera, r.ds = self.cam, DataStore.get()
        self.input.update(0)
        actual, expected = r._ship_size(ship), ship_size(r.ds, ship.data_id)
        self.assertEqual(actual, expected, 'nonpositive depth must not inflate behind-eye ships')
    def test_safe_fractional_target_preserves_the_requested_eye_exactly(self):
        self.st.entities.clear()
        self.cam.target = [-135.41666666666666, 0., -135.41666666666666]
        self.cam.distance, self.cam.pitch, self.cam.yaw = 180., 8., 45.
        self.input.update(0)
        yaw, pitch = math.radians(self.cam.yaw), math.radians(self.cam.pitch)
        expected = (self.cam.target[0] + 180 * math.cos(pitch) * math.sin(yaw),
                    60., self.cam.target[2] + 180 * math.cos(pitch) * math.cos(yaw))
        self.assertEqual(self.cam.eye_position(), expected)
    def test_keepout_covers_actual_readability_scaled_hardware(self):
        from render.renderer import Renderer
        from render.ship_sizes import _bounds
        self.st.entities.clear()
        ds = DataStore.get()
        data_id = next(s.id for s in ds.ships.values() if s.category == 'supercapital')
        ship = UnitFactory(self.st).spawn_ship(data_id, 0, Vec3())
        self.cam.width, self.cam.height = 96, 64
        self.cam.target, self.cam.distance, self.cam.pitch, self.cam.yaw = [0., 0., 0.], 3000., 8., 0.
        self.input.update(0)
        r = Renderer.__new__(Renderer)
        r.camera, r.ds = self.cam, ds
        size = r._ship_size(ship)
        lo, hi, _ = _bounds(size.shape)
        eye = self.cam.eye_position()
        inside = all(lo[i] * size.scale - self.cam.near < eye[i] < hi[i] * size.scale + self.cam.near for i in range(3))
        self.assertFalse(inside, 'camera keepout disagrees with actual readable mesh scale')
    def test_readability_keepout_intervals_match_shared_renderer_sizes(self):
        from render.camera_geometry import readable_intervals, box_interval
        from render.ship_sizes import (ship_size, readable_size, _bounds,
            READABILITY_PX, READABILITY_HALF, READABILITY_SCALE, READABILITY_FLOOR)
        ds = DataStore.get()
        ids = ['imperial_corvette', next(s.id for s in ds.ships.values() if s.category == 'supercapital')]
        tangent = math.tan(math.radians(55. / 2))
        cap = READABILITY_PX / (READABILITY_FLOOR * READABILITY_SCALE)
        for data_id in ids:
            base = ship_size(ds, data_id)
            lo, hi, _ = _bounds(base.shape)
            for height in (64, 480, 800):
                slope = READABILITY_PX * 2 * tangent / (READABILITY_HALF * READABILITY_SCALE * height)
                for center in ((0., 0., 0.), (100., 60., 100.), (-6000., 0., -6000.), (3000., 0., 3000.)):
                    box = (center, .7, tuple(v*base.scale for v in lo), tuple(v*base.scale for v in hi), True)
                    for pitch in (8., 55., 89.):
                        for yaw in (45., 225.):
                            p, y = math.radians(pitch), math.radians(yaw)
                            direction = (math.cos(p)*math.sin(y), math.sin(p), math.cos(p)*math.cos(y))
                            intervals = readable_intervals((0., 0., 0.), direction, box, 30., slope, cap)
                            for distance in (10., 180., 300., 1200., 3000., 12000., 200000.):
                                depth = distance - sum(center[i]*direction[i] for i in range(3))
                                ppw = height/(2*depth*tangent) if depth > 1e-6 else 0.
                                actual = readable_size(ds, data_id, ppw)
                                rendered = (center, .7, tuple(v*actual.scale for v in lo), tuple(v*actual.scale for v in hi))
                                expected = box_interval((0., 0., 0.), direction, rendered, 30.)
                                inside = expected is not None and expected[0] <= distance <= expected[1]
                                self.assertEqual(any(a <= distance <= b for a, b in intervals), inside,
                                    (data_id, height, center, pitch, yaw, distance))


if __name__ == '__main__':
    unittest.main()
