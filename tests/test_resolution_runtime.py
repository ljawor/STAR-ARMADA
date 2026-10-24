"""CPU/mocked display contracts; no SDL window, GL or native renderer is started."""
import ast
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pygame

ROOT = Path(__file__).resolve().parents[1]


def main_tree():
    return ast.parse((ROOT / 'main.py').read_text())


def main_helpers(*names, **env):
    nodes = [n for n in main_tree().body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    env.update(pygame=pygame, os=os)
    exec(compile(ast.Module(nodes, []), 'main.py', 'exec'), env)
    return env


class DisplaySelectionTests(unittest.TestCase):
    def display(self):
        self.assertIsNotNone(importlib.util.find_spec('render.display_settings'),
                             'validated display preferences are missing')
        from render import display_settings
        return display_settings

    def test_bounded_presets_and_legacy_auto_sizes(self):
        display = self.display()
        self.assertEqual(display.RESOLUTIONS, ('auto', '1280x720', '1280x800', '1440x900',
                         '1600x900', '1920x1080', '1920x1200', '2560x1440',
                         '2560x1600', '3840x2160'))
        for invalid in (None, [], {}, True, '0x0', '99999x99999', '1920X1080'):
            self.assertEqual(display.validate_resolution(invalid), 'auto')
        self.assertEqual(display.window_size('auto', (2560, 1600)), (1440, 900))
        self.assertEqual(display.window_size('auto', (1024, 768)), (1024, 640))
        self.assertEqual(display.window_size('auto', (2560, 1600), fullscreen=True), (2560, 1600))
        for full in (False, True):
            self.assertEqual(display.window_size('1920x1080', (2560, 1600), fullscreen=full),
                             (1920, 1080))
            self.assertEqual(display.window_size('3840x2160', (2560, 1600),
                                                 fullscreen=full, smoke=True), (1280, 800))
        self.assertEqual(display.window_size('broken', (0, 0)), (1440, 900))
        self.assertEqual(display.window_size('auto', (10**20, 10**20), fullscreen=True), (1440, 900))

    def test_unsupported_modes_fall_back_and_return_actual_surface(self):
        display = self.display()
        surface = Mock()
        fake = SimpleNamespace(FULLSCREEN=pygame.FULLSCREEN, error=pygame.error, display=Mock())
        fake.display.set_mode.side_effect = [pygame.error('mode'), pygame.error('desktop'), surface]
        result, full = display.open_display(fake, '1920x1080', (2560, 1600), pygame.OPENGL,
                                             fullscreen=True)
        self.assertIs(result, surface)
        self.assertFalse(full)
        self.assertEqual(fake.display.set_mode.call_args_list, [
            unittest.mock.call((1920, 1080), pygame.OPENGL | pygame.FULLSCREEN, display=0),
            unittest.mock.call((2560, 1600), pygame.OPENGL | pygame.FULLSCREEN, display=0),
            unittest.mock.call((1440, 900), pygame.OPENGL, display=0)])
        fake.display.set_mode.reset_mock()
        fake.display.set_mode.side_effect = pygame.error('no usable mode')
        with self.assertRaisesRegex(pygame.error, 'no usable mode'):
            display.open_display(fake, 'auto', (1440, 900), pygame.OPENGL)
        self.assertEqual(fake.display.set_mode.call_count, 1)

    def test_oversized_mode_never_reaches_sdl_or_redirects_to_the_second_display(self):
        display = self.display()
        fake = SimpleNamespace(FULLSCREEN=pygame.FULLSCREEN, error=pygame.error, display=Mock())
        desktops = [(2560, 1440), (2240, 1260)]
        modes = {0: [(2560, 1440), (1920, 1080), (1280, 720)],
                 1: [(4480, 2520), (3840, 2160), (2240, 1260)]}
        fake.display.get_desktop_sizes.return_value = desktops
        fake.display.list_modes.side_effect = lambda flags=0, display=0: modes[display]
        redirected = []
        def mode(size, flags, *, display=0):
            # Model SDL accepting a mode available only on monitor 1 rather than raising.
            if size == (3840, 2160):
                redirected.append(1)
            return pygame.Surface(size)
        fake.display.set_mode.side_effect = mode
        surface, full = display.open_display(fake, '3840x2160', desktops[0], pygame.OPENGL,
                                              fullscreen=True)
        self.assertFalse(redirected, 'oversized mode was sent to SDL and moved to monitor 1')
        self.assertEqual(surface.get_size(), desktops[0])
        self.assertTrue(full)
        fake.display.set_mode.assert_called_once_with(desktops[0], pygame.OPENGL | pygame.FULLSCREEN,
                                                      display=0)

    def test_unsupported_primary_mode_is_rejected_before_sdl(self):
        display = self.display()
        fake = SimpleNamespace(FULLSCREEN=pygame.FULLSCREEN, error=pygame.error, display=Mock())
        fake.display.list_modes.return_value = [(2560, 1440), (1920, 1080)]
        fake.display.set_mode.side_effect = lambda size, flags, **kw: pygame.Surface(size)
        surface, full = display.open_display(fake, '1440x900', (2560, 1440), pygame.OPENGL,
                                              fullscreen=True)
        self.assertEqual(surface.get_size(), (2560, 1440))
        self.assertTrue(full)
        fake.display.set_mode.assert_called_once_with((2560, 1440), pygame.OPENGL | pygame.FULLSCREEN,
                                                      display=0)

    def test_portrait_desktop_outside_native_limits_is_not_an_allocation_request(self):
        display = self.display()
        self.assertEqual(display.window_size('auto', (4320, 7680), fullscreen=True), (1440, 900))


class NativeResolutionTests(unittest.TestCase):
    def paths(self):
        return {key: '/unused/' + key for key in ('frame', 'tables', 'overlay', 'emit',
                'markers', 'fog', 'planets', 'input', 'camera', 'hardware')}

    def test_spawn_forwards_host_size_to_argv_readback_in_source_and_bundle(self):
        import inspect
        import json
        import tempfile
        from render_bridge import cpp_window, embedded
        self.assertIn('size', inspect.signature(cpp_window.spawn).parameters,
                      'spawn cannot receive the actual host size')
        for bundle in (None, '/unused/bundle'):
            with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
                process = Mock(stdout=None, returncode=0)
                process.poll.return_value = 0
                listener = Mock()
                listener.getsockname.return_value = ('127.0.0.1', 12345)
                listener.accept.return_value = (Mock(), ('127.0.0.1', 1))
                with self.subTest(bundle=bundle), \
                        patch.object(cpp_window, 'find_binary', return_value='/unused/armada_viewer'), \
                        patch('os.path.isfile', return_value=True), \
                        patch('pathlib.Path.is_file', return_value=True), \
                        patch.object(embedded.ctypes, 'CDLL', side_effect=AssertionError('parent CDLL')), \
                        patch.object(embedded.sys, '_MEIPASS', bundle, create=True), \
                        patch.object(embedded.sys, 'frozen', bool(bundle), create=True), \
                        patch.object(embedded.socket, 'socket', return_value=listener), \
                        patch.object(embedded.secrets, 'token_hex', return_value='a' * 64), \
                        patch.object(embedded, 'receive', side_effect=[{'nonce': 'a'*64}, {'ready': True}]), \
                        patch.object(embedded, 'send'), \
                        patch.object(embedded.EmbeddedWindow, '_drain_log'), \
                        patch.object(embedded.subprocess, 'Popen', return_value=process) as launch, \
                        patch('atexit.register'), \
                        patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '0',
                                                'STAR_ARMADA_CPP_LIBRARY': ''}):
                    paths = {key: str(Path(directory) / key) for key in self.paths()}
                    window = cpp_window.spawn(paths, root=directory, snapshot='/unused/catalogue.snap',
                                              size=(1920, 1080), log=lambda msg: None)
                    self.assertIsNotNone(window)
                    self.assertEqual(window.size, (1920, 1080))
                    self.assertEqual(len(window._pixels), 1920 * 1080 * 4)
                    command = launch.call_args.args[0]
                    config = json.loads(Path(command[-1]).read_text())
                    decoded = config['argv']
                    self.assertEqual(decoded[decoded.index('--width') + 1], '1920')
                    self.assertEqual(decoded[decoded.index('--height') + 1], '1080')
                    self.assertEqual((config['width'], config['height']), (1920, 1080))
                    self.assertEqual(Path(config['frame']).stat().st_size, 1920 * 1080 * 4)
                    library_name = 'armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib'
                    expected_library = (Path(bundle) / 'cpp' / library_name if bundle else
                                        Path(directory) / 'render_cpp' / 'build-w02' / library_name)
                    self.assertEqual(config['library'], str(expected_library))
                    self.assertEqual(command[1:-1], ['--native-render-worker'] if bundle else
                                     ['-u', '-m', 'render_bridge.native_worker'])
                    self.assertEqual(launch.call_args.kwargs['cwd'], directory)
                    window.terminate()
                    self.assertIsNone(window._mapping)
                    process.wait.assert_called()

    def test_embedded_rejects_unbounded_dimensions_before_loading_native(self):
        from render_bridge import embedded
        for size in (('999999999', '1080'), ('1920', '0'), ('-1', '800')):
            with self.subTest(size=size), patch.object(embedded.subprocess, 'Popen') as launch, \
                    patch.object(embedded, 'find_library') as discover:
                with self.assertRaises(ValueError):
                    embedded.EmbeddedWindow(['viewer', '--width', size[0], '--height', size[1]],
                                            root='/unused')
                discover.assert_not_called()
                launch.assert_not_called()

    def test_external_diagnostic_receives_same_host_dimensions(self):
        import inspect
        from render_bridge import cpp_window
        self.assertIn('size', inspect.signature(cpp_window.spawn).parameters)
        with patch.object(cpp_window, 'find_binary', return_value='/unused/viewer'), \
                patch('os.path.isfile', return_value=True), patch('shutil.which', return_value=None), \
                patch('subprocess.Popen') as spawn, patch('atexit.register'), \
                patch.dict(os.environ, {'STAR_ARMADA_CPP_EXTERNAL': '1'}):
            cpp_window.spawn(self.paths(), root='/unused', snapshot='/unused/catalogue.snap',
                             size=(2560, 1440), log=lambda msg: None)
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[argv.index('--width') + 1], '2560')
            self.assertEqual(argv[argv.index('--height') + 1], '1440')

    def test_pointer_mapping_remains_logical_and_already_remote_is_unchanged(self):
        from render_bridge.embedded import map_pointer_event
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(1440, 540), rel=(15, 27))
        mapped = map_pointer_event(event, (1920, 1080), (1280, 800))
        self.assertEqual(mapped.pos, (960, 400))
        self.assertEqual(mapped.rel, (10, 20))
        self.assertIs(map_pointer_event(mapped, (1920, 1080), (1280, 800)), mapped)


class CameraResolutionTests(unittest.TestCase):
    def test_logical_projection_and_pick_rays_match_actual_output_aspect(self):
        from render.camera import Camera
        for width, height in ((1920, 1080), (1280, 720), (1920, 1200), (2560, 1600)):
            physical, logical = Camera(width, height), Camera(1280, 800)
            logical.projection_aspect = width / height
            for camera in (physical, logical):
                camera._proj = camera._view = object()  # analytic paths only
            for point in ((300, 0, 0), (-500, 0, 700), (100, 0, -400)):
                native = physical.world_to_screen(*point)
                hud = logical.world_to_screen(*point)
                self.assertAlmostEqual(hud[0] / 1280, native[0] / width)
                self.assertAlmostEqual(hud[1] / 800, native[1] / height)
                picked = logical.screen_to_world(native[0] * 1280 / width,
                                                  native[1] * 800 / height)
                for actual, expected in zip(picked, point):
                    self.assertAlmostEqual(actual, expected)
            self.assertEqual((logical.width, logical.height), (1280, 800))

    def test_gl_projection_keepout_ray_and_safe_eye_cache_share_output_aspect(self):
        from render import camera as module
        camera = module.Camera(1280, 800)
        camera._scene = SimpleNamespace(entities={})
        with patch('render.camera_geometry.camera_ray', return_value=None) as ray, \
                patch('render.camera_geometry.scene_boxes', return_value=()), \
                patch('render.camera_geometry.safe_eye', side_effect=lambda target, eye, *args: eye) as safe:
            camera.projection_aspect = 1920 / 1080
            camera.eye_position()
            self.assertEqual(ray.call_args.args[4], 1920 / 1080)
            self.assertEqual(safe.call_args.args[5], 1920 / 1080)
            camera.eye_position()
            self.assertEqual(safe.call_count, 1)
            camera.projection_aspect = 2560 / 1600
            camera.eye_position()
            self.assertEqual(safe.call_count, 2, 'aspect changes must invalidate keepout caches')
            self.assertEqual(ray.call_args.args[4], 2560 / 1600)
            self.assertEqual(safe.call_args.args[5], 2560 / 1600)
        camera._scene = None
        with patch.object(module, 'glMatrixMode'), patch.object(module, 'glLoadIdentity'), \
                patch.object(module, 'glGetFloatv'), patch.object(module, 'gluLookAt'), \
                patch.object(module, '_gluPerspective') as perspective:
            camera.projection_aspect = 1920 / 1080
            camera.apply(1280, 800)
            self.assertEqual(perspective.call_args.args[1], 1920 / 1080)
        camera.projection_aspect = None
        self.assertEqual(camera.aspect, 1280 / 800)


class MainResolutionTests(unittest.TestCase):
    def bootstrap(self, resolution, fullscreen, side_effect=None, smoke=False):
        tree = main_tree()
        start = next((i for i, node in enumerate(tree.body) if isinstance(node, ast.ImportFrom)
                      and node.module == 'render.display_settings'), None)
        self.assertIsNotNone(start, 'bootstrap never reads the persisted display preference')
        stop = next(i for i, node in enumerate(tree.body)
                    if isinstance(node, ast.FunctionDef) and node.name == 'toggle_fullscreen')
        fake = SimpleNamespace(FULLSCREEN=pygame.FULLSCREEN, error=pygame.error, display=Mock())
        fake.display.get_desktop_sizes.return_value = [(2560, 1600)]
        fake.display.set_mode.side_effect = side_effect
        if side_effect is None:
            fake.display.set_mode.side_effect = lambda size, flags, **kwargs: pygame.Surface(size)
        env = dict(pygame=fake, SETTINGS={'resolution': resolution}, FULLSCREEN=fullscreen,
                   _flags=pygame.OPENGL, SMOKE=smoke)
        with patch('builtins.print') as notice:
            exec(compile(ast.Module(tree.body[start:stop], []), 'main.py', 'exec'), env)
        return env, fake.display.set_mode, notice

    def test_startup_applies_explicit_resolution_in_both_window_modes_and_latches_token(self):
        for fullscreen in (False, True):
            env, mode, _ = self.bootstrap('1920x1080', fullscreen)
            mode.assert_called_once_with((1920, 1080), pygame.OPENGL |
                                         (pygame.FULLSCREEN if fullscreen else 0), display=0)
            self.assertEqual((env['W'], env['H']), (1920, 1080))
            self.assertEqual(env['FULLSCREEN'], fullscreen)
            self.assertEqual(env['SESSION_RESOLUTION'], '1920x1080')
            env['SETTINGS']['resolution'] = '3840x2160'
            self.assertEqual(env['SESSION_RESOLUTION'], '1920x1080')

    def test_startup_auto_uses_desktop_fullscreen_old_default_window_and_fixed_smoke(self):
        for full, expected in ((False, (1440, 900)), (True, (2560, 1600))):
            env, _, _ = self.bootstrap('auto', full)
            self.assertEqual((env['W'], env['H']), expected)
        env, _, _ = self.bootstrap('3840x2160', False, smoke=True)
        self.assertEqual((env['W'], env['H']), (1280, 800))
        env, _, _ = self.bootstrap(['unsafe'], False)
        self.assertEqual(env['SESSION_RESOLUTION'], 'auto')

    def test_startup_reports_fallback_and_tracks_actual_surface_without_overwriting_choice(self):
        for full in (False, True):
            attempts = [pygame.error('unsupported')]
            if full:
                attempts.append(pygame.error('no fullscreen'))
            attempts.append(pygame.Surface((1024, 640)))
            env, _, notice = self.bootstrap('1920x1080', full, side_effect=attempts)
            self.assertEqual((env['W'], env['H']), (1024, 640))
            self.assertFalse(env['FULLSCREEN'])
            self.assertEqual(env['SETTINGS']['resolution'], '1920x1080')
            messages = ' '.join(str(c) for c in notice.call_args_list).lower()
            self.assertIn('fallback', messages)
            self.assertIn('1024x640', messages)
            self.assertIn('windowed', messages)

    def test_fullscreen_menu_toggle_keeps_latched_dimensions_and_reads_actual_size(self):
        env = main_helpers('toggle_fullscreen', W=1920, H=1080, FULLSCREEN=False,
                           SESSION_RESOLUTION='1920x1080', DESKTOP_SIZE=(2560, 1600),
                           SETTINGS={'resolution': '3840x2160'}, CPP={'window': None},
                           CPP_HUD_SIZE=(1280, 800), camera=Mock(), hud=Mock(),
                           SMOKE=False, flash=Mock())
        with patch.object(pygame.display, 'Info', return_value=SimpleNamespace(current_w=2560, current_h=1600)), \
                patch.object(pygame.display, 'list_modes', return_value=-1), \
                patch.object(pygame.display, 'set_mode', side_effect=lambda size, flags, **kwargs: pygame.Surface(size)) as mode:
            env['toggle_fullscreen']()
            self.assertTrue(env['FULLSCREEN'])
            self.assertEqual((env['W'], env['H']), (1920, 1080))
            self.assertEqual(env['camera'].projection_aspect, 1920 / 1080)
            env['toggle_fullscreen']()
            self.assertFalse(env['FULLSCREEN'])
            self.assertEqual(mode.call_args_list, [
                unittest.mock.call((1920, 1080), pygame.DOUBLEBUF | pygame.OPENGL | pygame.FULLSCREEN, display=0),
                unittest.mock.call((1920, 1080), pygame.DOUBLEBUF | pygame.OPENGL, display=0)])
        with patch.object(pygame.display, 'list_modes', return_value=-1), \
                patch.object(pygame.display, 'set_mode', side_effect=[pygame.error('unsupported'),
                          pygame.Surface((2560, 1600))]):
            env['toggle_fullscreen']()
        self.assertTrue(env['FULLSCREEN'])
        self.assertEqual((env['W'], env['H']), (2560, 1600))

    def test_live_native_owner_defers_toggle_without_resizing_or_reinitializing(self):
        env = main_helpers('toggle_fullscreen', W=1920, H=1080, FULLSCREEN=False,
                           SESSION_RESOLUTION='1920x1080', DESKTOP_SIZE=(2560, 1600),
                           CPP={'window': Mock()}, CPP_HUD_SIZE=(1280, 800), camera=Mock(), hud=Mock(),
                           SMOKE=False, flash=Mock())
        with patch.object(pygame.display, 'Info', return_value=SimpleNamespace(current_w=2560, current_h=1600)), \
                patch.object(pygame.display, 'set_mode') as mode:
            env['toggle_fullscreen']()
        mode.assert_not_called()
        self.assertFalse(env['FULLSCREEN'])
        env['hud'].resize.assert_not_called()
        env['CPP']['window'].terminate.assert_not_called()
        env['flash'].assert_called_once()

    def test_native_session_receives_actual_host_size_while_hud_stays_codec_bounded(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
            env = main_helpers('cpp_session', CPP={'session': None}, CPP_DIR=directory,
                               CPP_HUD_SIZE=(1280, 800), SETTINGS={'markers': 'selected'},
                               W=1918, H=1078, SMOKE=False, camera=Mock(), hud=Mock(),
                               ROOT=directory, cpp_unavailable=Mock(return_value=None), flash_print=Mock())
            with patch('render_bridge.live.LiveSession') as session, \
                    patch('render_bridge.cpp_window.spawn', return_value=SimpleNamespace(embedded=True)) as spawn:
                try:
                    env['cpp_session'](object(), object(), 0)
                    self.assertEqual(session.call_args.kwargs['size'], (1280, 800))
                    self.assertEqual(session.call_args.kwargs['marker_mode'], 'selected')
                    self.assertEqual(spawn.call_args.kwargs.get('size'), (1918, 1078))
                finally:
                    env['CPP']['directory'].cleanup()
        hud_size = next(node.value for node in main_tree().body if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'CPP_HUD_SIZE' for t in node.targets))
        self.assertEqual(ast.literal_eval(hud_size), (1280, 800))

    def test_fresh_and_recovered_cameras_keep_hud_coordinates_with_actual_projection(self):
        from render.camera import Camera
        for name, variable in (('start_game', 'camera'), ('install_recovered_manager', 'prepared_camera')):
            function = next(n for n in main_tree().body if isinstance(n, ast.FunctionDef) and n.name == name)
            # Exercise the production camera-construction slice without building a game or invoking GL.
            body = (function.body if name == 'start_game' else
                    next(n.body for n in function.body if isinstance(n, ast.Try)))
            start = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == 'view_size' for t in n.targets))
            stop = start + 2
            while stop < len(body) and isinstance(body[stop], ast.Assign):
                target = body[stop].targets[0]
                if not isinstance(target, ast.Attribute) or target.attr != 'projection_aspect':
                    break
                stop += 1
            env = dict(CPP_HUD_SIZE=(1280, 800), W=1920, H=1080, Camera=Camera)
            exec(compile(ast.Module(body[start:stop], []), 'main.py', 'exec'), env)
            self.assertEqual((env[variable].width, env[variable].height), (1280, 800))
            self.assertEqual(env[variable].aspect, 1920 / 1080, name)


if __name__ == '__main__':
    unittest.main()
