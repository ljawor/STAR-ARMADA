"""Resolution settings contracts; CPU only, never start native/GL code."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pygame
from render import menus


class ResolutionSettingsTests(unittest.TestCase):
    def test_unsupported_fullscreen_toggle_falls_back_without_crashing(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        tree = ast.parse(Path('main.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'toggle_fullscreen')
        env = dict(pygame=pygame, W=1440, H=900, FULLSCREEN=False,
                   SESSION_RESOLUTION='3840x2160', DESKTOP_SIZE=(2560, 1600),
                   CPP={'window': None}, camera=None, hud=None, flash=Mock(), SMOKE=False)
        exec(compile(ast.Module([function], []), 'main.py', 'exec'), env)
        with patch.object(pygame.display, 'set_mode', side_effect=[
                pygame.error('unsupported mode'), pygame.Surface((2560, 1600))]):
            env['toggle_fullscreen']()
        self.assertTrue(env['FULLSCREEN'])
        self.assertEqual((env['W'], env['H']), (2560, 1600))

    def test_fullscreen_keeps_selected_mode_and_never_resizes_live_native(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        tree = ast.parse(Path('main.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'toggle_fullscreen')
        env = dict(pygame=pygame, W=1920, H=1080, FULLSCREEN=False,
                   SESSION_RESOLUTION='1920x1080', DESKTOP_SIZE=(2560, 1600),
                   CPP={'window': Mock(), 'fell_back': False}, RENDERER='cpp',
                   CPP_HUD_SIZE=(1280, 800), camera=None, hud=None, flash=Mock(), SMOKE=False)
        exec(compile(ast.Module([function], []), 'main.py', 'exec'), env)
        with patch.object(pygame.display, 'set_mode', return_value=pygame.Surface((1920, 1080))) as mode:
            env['toggle_fullscreen']()
            mode.assert_not_called()
            self.assertFalse(env['FULLSCREEN'])
            env['CPP']['window'] = None
            env['toggle_fullscreen']()
            self.assertTrue(env['FULLSCREEN'])
            self.assertEqual((env['W'], env['H']), (1920, 1080))
            env['toggle_fullscreen']()
            self.assertFalse(env['FULLSCREEN'])
            self.assertEqual((env['W'], env['H']), (1920, 1080))

    def test_fixed_hud_camera_projects_and_picks_at_native_aspect(self):
        from render.camera import Camera
        physical = Camera(1920, 1080)
        logical = Camera(1280, 800)
        logical.projection_aspect = 1920 / 1080
        for camera in (physical, logical):
            camera._proj = camera._view = object()  # analytic math only; never call GL
        for point in ((300, 0, 0), (-500, 0, 700), (100, 0, -400)):
            native = physical.world_to_screen(*point)
            hud = logical.world_to_screen(*point)
            self.assertAlmostEqual(hud[0] / 1280, native[0] / 1920)
            self.assertAlmostEqual(hud[1] / 800, native[1] / 1080)
            picked = logical.screen_to_world(*hud)
            for actual, expected in zip(picked, point):
                self.assertAlmostEqual(actual, expected)
        self.assertEqual((logical.width, logical.height), (1280, 800))

    def test_main_bootstrap_and_session_keep_drawable_and_hud_sizes_separate(self):
        tree = ast.parse(Path('main.py').read_text())
        start = next((i for i, n in enumerate(tree.body) if isinstance(n, ast.ImportFrom)
                      and n.module == 'render.display_settings'), None)
        self.assertIsNotNone(start, 'main does not load the selected display mode')
        stop = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.FunctionDef)
                    and n.name == 'toggle_fullscreen')
        env = dict(pygame=pygame, SETTINGS={'resolution': '1920x1080'}, FULLSCREEN=False,
                   _flags=pygame.OPENGL, SMOKE=False)
        with patch.object(pygame.display, 'get_desktop_sizes', return_value=[(2560, 1600)]), \
                patch.object(pygame.display, 'set_mode', return_value=pygame.Surface((1920, 1080))) as mode:
            exec(compile(ast.Module(tree.body[start:stop], []), 'main.py', 'exec'), env)
        mode.assert_called_once_with((1920, 1080), pygame.OPENGL)
        self.assertEqual((env['W'], env['H']), (1920, 1080))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cpp_session')
        with tempfile.TemporaryDirectory() as directory, \
                patch('render_bridge.live.LiveSession') as session, \
                patch('render_bridge.cpp_window.spawn', return_value=None) as spawn:
            env.update(CPP={'session': None}, CPP_DIR=directory, CPP_HUD_SIZE=(1280, 800),
                       camera=Mock(), hud=Mock(), ROOT=directory, os=__import__('os'), flash_print=Mock())
            exec(compile(ast.Module([function], []), 'main.py', 'exec'), env)
            env['cpp_session'](object(), object(), 0)
            self.assertEqual(session.call_args.kwargs['size'], (1280, 800))
            self.assertEqual(spawn.call_args.kwargs.get('size'), (1920, 1080))
            env['CPP']['directory'].cleanup()

    def test_native_argv_and_readback_buffer_match_host_not_hud(self):
        from render_bridge import cpp_window, embedded
        paths = {key: '/unused/' + key for key in ('frame', 'tables', 'overlay', 'emit',
                 'markers', 'fog', 'planets', 'input', 'camera', 'hardware')}
        library = Mock()
        library.armada_abi_version.return_value = 1
        library.armada_open.return_value = 1
        with patch.object(cpp_window, 'find_binary', return_value='/unused/armada_viewer'), \
                patch('os.path.isfile', return_value=True), \
                patch('pathlib.Path.is_file', return_value=True), \
                patch.object(embedded.ctypes, 'CDLL', return_value=library), \
                patch('atexit.register'), patch.dict('os.environ', {'STAR_ARMADA_CPP_EXTERNAL': '0'}):
            import inspect
            self.assertIn('size', inspect.signature(cpp_window.spawn).parameters,
                          'native spawn cannot accept the host resolution')
            window = cpp_window.spawn(paths, root='/unused', snapshot='/unused/catalogue.snap',
                                      size=(1920, 1080), log=lambda msg: None)
            self.assertIsNotNone(window)
            self.assertEqual(window.size, (1920, 1080))
            self.assertEqual(len(window._pixels), 1920 * 1080 * 4)
            argc, argv = library.armada_open.call_args.args
            decoded = [argv[i].decode() for i in range(argc)]
            self.assertEqual(decoded[decoded.index('--width') + 1], '1920')
            self.assertEqual(decoded[decoded.index('--height') + 1], '1080')
            window.terminate()
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(1440, 540), rel=(15, 27))
        mapped = embedded.map_pointer_event(event, (1920, 1080), (1280, 800))
        self.assertEqual(mapped.pos, (960, 400))
        self.assertEqual(mapped.rel, (10, 20))
        self.assertIs(embedded.map_pointer_event(mapped, (1920, 1080), (1280, 800)), mapped)
        tree = ast.parse(Path('main.py').read_text())
        hud_size = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'CPP_HUD_SIZE' for t in n.targets))
        self.assertEqual(ast.literal_eval(hud_size), (1280, 800))

    def test_clean_classic_selector_mouse_keyboard_and_footer_clearance(self):
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        with tempfile.TemporaryDirectory() as directory, patch.multiple(
                menus, SETTINGS_PATH=str(Path(directory) / 'settings.json'),
                CAMPAIGN_PATH=str(Path(directory) / 'campaign.json')):
            for width, height in ((800, 600), (1280, 800), (1920, 1080)):
                menu = menus.MenuStack(width, height)
                self.addCleanup(menu.close)
                menu.screen = 'settings'
                menu.settings['resolution'] = 'auto'
                menu.render(0)
                controls = [b for b in menu.buttons if isinstance(b.get('payload'), dict)
                            and 'key' in b['payload']]
                resolution = [b for b in controls if b['payload']['key'] == 'resolution']
                self.assertEqual(len(resolution), 1, 'resolution selector is missing')
                button = resolution[0]
                self.assertTrue(pygame.Rect(0, 0, width, height).contains(button['rect']))
                for i, control in enumerate(controls):
                    for other in controls[i + 1:]:
                        self.assertFalse(control['rect'].colliderect(other['rect']))
                from render.classic_screens import _map_rect
                help_top = _map_rect(menu, (52, 552, 1016, 24)).top
                self.assertLessEqual(max(b['rect'].bottom for b in controls), help_top)
                menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                     button=1, pos=button['rect'].center))
                self.assertEqual(menu.settings['resolution'], '1280x720')
                menu.settings_focus = controls.index(button)
                menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
                self.assertEqual(menu.settings['resolution'], '1280x800')
                menu.apply_pending()
                self.assertEqual(menus.load_settings()['resolution'], '1280x800')
                texts = ' '.join(menu.settings_rendered_text).lower()
                self.assertIn('restart', texts)
                menu.close()

    def test_window_selection_and_failed_mode_fallback_use_actual_surface_size(self):
        from render import display_settings as display
        self.assertTrue(hasattr(display, 'window_size'), 'window size selection is missing')
        self.assertEqual(display.window_size('auto', (2560, 1600)), (1440, 900))
        self.assertEqual(display.window_size('auto', (2560, 1600), fullscreen=True), (2560, 1600))
        self.assertEqual(display.window_size('1920x1080', (2560, 1600)), (1920, 1080))
        self.assertEqual(display.window_size('1920x1080', (2560, 1600), fullscreen=True), (1920, 1080))
        self.assertEqual(display.window_size('auto', (1024, 768)), (1024, 640))
        self.assertEqual(display.window_size('auto', (2560, 1600), smoke=True), (1280, 800))
        self.assertEqual(display.window_size('broken', (0, 0)), (1440, 900))
        requested = []
        def set_mode(size, flags):
            requested.append((size, flags))
            if len(requested) < 3:
                raise pygame.error('unsupported mode')
            return pygame.Surface((1024, 640))
        with patch.object(pygame.display, 'set_mode', side_effect=set_mode):
            surface, full = display.open_display(pygame, '3840x2160', (2560, 1600),
                                                 pygame.OPENGL, fullscreen=True)
        self.assertEqual(surface.get_size(), (1024, 640))
        self.assertFalse(full)
        self.assertEqual(requested, [((3840, 2160), pygame.OPENGL | pygame.FULLSCREEN),
                                    ((2560, 1600), pygame.OPENGL | pygame.FULLSCREEN),
                                    ((1440, 900), pygame.OPENGL)])

    def test_resolution_persists_and_bad_values_default_to_auto(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            with patch.object(menus, 'SETTINGS_PATH', str(path)):
                self.assertEqual(menus.load_settings().get('resolution'), 'auto')
                values = dict(menus.DEFAULT_SETTINGS, resolution='1920x1080', unknown_mod=17)
                menus.save_settings(values)
                self.assertEqual(menus.load_settings()['resolution'], '1920x1080')
                self.assertEqual(menus.load_settings()['unknown_mod'], 17)
                for bad in (None, [], {}, True, '0x0', '99999x99999', '1920X1080'):
                    path.write_text(json.dumps(dict(values, resolution=bad)))
                    self.assertEqual(menus.load_settings()['resolution'], 'auto')


if __name__ == '__main__':
    unittest.main()
