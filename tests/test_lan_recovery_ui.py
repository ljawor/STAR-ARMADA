"""Read-only recovery presentation and real-driver layout acceptance."""
import importlib.util
import tempfile
import unittest
from unittest.mock import patch


GL_PROBE = r'''
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
EVIDENCE = Path(sys.argv[2])
EVIDENCE.mkdir(parents=True, exist_ok=True)
import pygame
import numpy as np
from OpenGL import GL as gl
import render.menus as menus
from render.recovery_overlay import RecoveryOverlay
from render.clean_classic import font
font_owned = not pygame.font.get_init()
display_owned = not pygame.display.get_init()
pygame.font.init()
pygame.display.init()
cached = font(18)
reports = []
with tempfile.TemporaryDirectory(dir=EVIDENCE.parent) as directory:
    menus.USER_DIR = directory
    menus.SAVES_DIR = str(Path(directory) / 'saves')
    menus.SETTINGS_PATH = str(Path(directory) / 'settings.json')
    menus.CAMPAIGN_PATH = str(Path(directory) / 'campaign.json')
    menus.BALANCE_PATH = str(Path(directory) / 'balance.json')
    try:
        for width, height in ((640, 480), (1920, 1080)):
            pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
            overlay = RecoveryOverlay(width, height)
            try:
                gl.glViewport(0, 0, width, height)
                gl.glClearColor(0, 0, 0, 1)
                gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
                overlay.draw(dict(phase='draining', missing=[1, 2, 3], remaining=12.3, progress=.5))
                overlay.draw_gl()
                gl.glFinish()
                pixels = np.frombuffer(gl.glReadPixels(0, 0, width, height, gl.GL_RGB, gl.GL_UNSIGNED_BYTE), dtype=np.uint8).reshape(height, width, 3)[::-1].copy()
                expected = pygame.Surface((width, height))
                expected.fill((0, 0, 0))
                expected.blit(overlay.surface, (0, 0))
                surface_pixels = pygame.surfarray.array3d(expected).transpose(1, 0, 2)
                difference = float(np.abs(pixels.astype(float) - surface_pixels.astype(float)).mean())
                assert difference < 2, difference
                boxes = []
                for text, rect in zip(overlay.rendered_text, overlay.text_bounds):
                    assert overlay.panel_rect.contains(rect), rect
                    assert rect.height >= 16
                    crop = pixels[rect.y:rect.bottom, rect.x:rect.right]
                    contrast = float(crop.std())
                    assert contrast > 10, (text, contrast)
                    # Empty pre-feature GL framebuffer fails the same metric.
                    assert float(np.zeros_like(crop).std()) <= 10
                    boxes.append(dict(text=text, bbox=list(rect), contrast=contrast))
                pygame.image.save(pygame.image.frombuffer(pixels.tobytes(), (width, height), 'RGB'), str(EVIDENCE / f'overlay-{width}x{height}.png'))
                reports.append(dict(size=[width, height], driver=gl.glGetString(gl.GL_RENDERER).decode(),
                                    pixel_mean_error=difference, text_bounds=boxes))
            finally:
                overlay.cleanup()
            assert font(18) is cached
            assert cached.render('alive', True, (255, 255, 255)).get_width() > 0
    finally:
        if display_owned:
            pygame.display.quit()
        if font_owned:
            font.cache_clear()
            pygame.font.quit()
(EVIDENCE / 'overlay-report.json').write_text(json.dumps(reports, indent=2))
print('REAL_GL_RECOVERY_OK ' + json.dumps(reports))
'''


class RecoveryUITests(unittest.TestCase):
    def setUp(self):
        import pygame
        import render.menus as menus
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for key, value in dict(USER_DIR=self.directory.name, SAVES_DIR=self.directory.name,
                               SETTINGS_PATH=self.directory.name + '/settings.json',
                               CAMPAIGN_PATH=self.directory.name + '/campaign.json',
                               BALANCE_PATH=self.directory.name + '/balance.json').items():
            scope = patch.object(menus, key, value)
            scope.start()
            self.addCleanup(scope.stop)
        self.font_owned = not pygame.font.get_init()
        pygame.font.init()
        def close_owned_font():
            if self.font_owned:
                from render.clean_classic import font
                font.cache_clear()
                pygame.font.quit()
        self.addCleanup(close_owned_font)

    def test_draw_returns_surface_for_native_hud_composition(self):
        from render.recovery_overlay import RecoveryOverlay
        overlay = RecoveryOverlay(1280, 800)
        self.assertIs(overlay.draw({'phase': 'waiting', 'missing': [1]}), overlay.surface)

    def test_real_gl_small_and_large_capture_matches_measured_surface(self):
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        root = Path(__file__).resolve().parents[1]
        evidence = Path(self.directory.name) / 'real-gl'
        env = dict(os.environ)
        if env.get('SDL_VIDEODRIVER') == 'dummy':
            env.pop('SDL_VIDEODRIVER')
        child = subprocess.run([sys.executable, '-c', GL_PROBE, str(root), str(evidence)],
                               cwd=root, env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        reports = json.loads((evidence / 'overlay-report.json').read_text())
        self.assertEqual([r['size'] for r in reports], [[640, 480], [1920, 1080]])
        for report in reports:
            self.assertLess(report['pixel_mean_error'], 2)
            self.assertEqual(len(report['text_bounds']), 6)
            self.assertTrue(all(b['contrast'] > 10 for b in report['text_bounds']))

    def test_production_loop_routes_recovery_before_other_modal_input(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        event_loop = next(n for n in ast.walk(loop) if isinstance(n, ast.For)
                          and ast.unparse(n.iter) == 'pygame.event.get()')
        calls = [n.func.id for n in ast.walk(event_loop)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn('dispatch_game_event', calls, 'main bypasses shared game event routing')
        # Follow the production dispatcher and execute it: moving routing out of the loop
        # must not weaken the recovery-before-help/world-order contract.
        dispatch = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'dispatch_game_event')
        import pygame
        from types import SimpleNamespace
        order = []
        namespace = dict(pygame=pygame, state=object(), gm=object(), mode='game', running=True,
                         inputc=SimpleNamespace(), playback=None, cinematic=None,
                         net_session=None, HumanCommandRejected=RuntimeError,
                         handle_recovery_event=lambda event: order.append('recovery') or True,
                         handle_presentation_input=lambda event: order.append('presentation') or False,
                         handle_game_input=lambda event: order.append('input'))
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), 'main.py', 'exec'), namespace)
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(20, 20), rel=(0, 0), buttons=(0, 0, 0))
        namespace['dispatch_game_event'](event)
        self.assertEqual(order, ['recovery'])
        order.clear()
        namespace['handle_recovery_event'] = lambda event: order.append('recovery') or False
        namespace['dispatch_game_event'](event)
        self.assertEqual(order, ['recovery', 'presentation', 'input'])
        all_calls = [n.func.id for n in ast.walk(loop)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        # The window owns every surface now (#160): the loop hands the frame to the producer, and the
        # producer composes the recovery overlay into it (`cpp_overlay_layers`).
        self.assertIn('cpp_publish', all_calls, 'main never displays the world the loop is running')
        layers = next(n for n in ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text()).body
                      if isinstance(n, ast.FunctionDef) and n.name == 'cpp_overlay_layers')
        self.assertIn('recovery_overlay.draw', ast.unparse(layers),
                      'the native overlay composer must carry abort/progress')

    def test_lan_menu_failed_recovery_opt_in_releases_unusable_socket(self):
        from render.menus import MenuStack
        from game.net.lan import LanSession
        from test_lan import free_port
        menu = MenuStack(640, 480)
        self.addCleanup(menu.close)
        menu.screen, menu.lan_port = 'lan_host', str(free_port())
        with patch.object(LanSession, 'enable_recovery', side_effect=ValueError('recovery unavailable')):
            menu._connect_lan()
        self.assertIsNone(menu.lan_session, 'failed opt-in left an unsupported lobby/socket alive')
        self.assertIn('recovery unavailable', menu.lan_notice)
        self.assertEqual(menu.screen, 'lan_host')

    def test_real_lan_menu_host_and_join_opt_in_before_handshake(self):
        from render.menus import MenuStack
        from test_lan import free_port, pump
        from game.data.store import DataStore
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        host_menu = MenuStack(640, 480)
        client_menu = MenuStack(640, 480)
        self.addCleanup(host_menu.close)
        self.addCleanup(client_menu.close)
        port = free_port()
        host_menu.screen, host_menu.lan_port = 'lan_host', str(port)
        host_menu._connect_lan()
        self.assertIsNotNone(host_menu.lan_session, host_menu.lan_notice)
        self.assertIsNotNone(host_menu.lan_session._recovery, 'host menu did not enable recovery')
        client_menu.screen, client_menu.lan_port = 'lan_join', str(port)
        client_menu.lan_address = '127.0.0.1'
        client_menu._connect_lan()
        self.assertIsNotNone(client_menu.lan_session, client_menu.lan_notice)
        self.assertIsNotNone(client_menu.lan_session._recovery)
        sessions = [host_menu.lan_session, client_menu.lan_session]
        pump(sessions, lambda: all(len(s.snapshot['players']) == 2 for s in sessions))
        self.assertIsNotNone(client_menu.lan_session._recovery.credential)

    def test_production_recovery_input_blocks_orders_but_allows_camera_and_abort(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        names = {'handle_recovery_event', 'lan_recovering', 'sync_recovery_overlay'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names, 'production recovery input gate missing')
        import pygame
        import socket
        from test_lan_production_reconnect import ProductionReconnectTests
        from test_lan import pump
        from game.net.lan import precise_checksum
        from render.camera import Camera
        from render.hud import HUD
        from render.input import InputController
        helper = ProductionReconnectTests()
        self.addCleanup(helper.doCleanups)
        sessions, managers = helper.setup_match(2)
        helper.align(sessions, managers, 8)
        session, manager = sessions[0], managers[0]
        camera = Camera(640, 480)
        hud = HUD(640, 480, manager.state)
        self.addCleanup(hud.close)
        controller = InputController(manager.state, camera, hud, None)
        controller.keys = {pygame.K_j, pygame.K_w}
        controller._pending_ability = {'unsafe': True}
        hud.placement = {'unsafe': True}
        notices = []
        namespace: dict = dict(net_session=session, gm=manager, state=manager.state,
                         camera=camera, hud=hud, inputc=controller, pygame=pygame,
                         recovery_overlay=None, W=640, H=480, accumulator=42.,
                         CPP_HUD_SIZE=(1280, 800),
                         leave_game=lambda reason: notices.append(reason))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), namespace)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        pump(sessions, lambda: session.snapshot['status'] == 'recovering')
        before = precise_checksum(manager)
        namespace['sync_recovery_overlay']()
        self.addCleanup(namespace['recovery_overlay'].cleanup)
        self.assertEqual(controller.keys, set())
        self.assertIsNone(controller._pending_ability)
        self.assertIsNone(hud.placement)
        for event in (pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j),
                      pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE),
                      pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(30, 30))):
            self.assertTrue(namespace['handle_recovery_event'](event))
        distance = camera.distance
        namespace['handle_recovery_event'](pygame.event.Event(pygame.MOUSEWHEEL, y=1))
        self.assertLess(camera.distance, distance)
        self.assertEqual(precise_checksum(manager), before)
        self.assertEqual(namespace['accumulator'], 0.)
        namespace['handle_recovery_event'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(len(notices), 1)
        self.assertEqual(session.snapshot['status'], 'error')

    def test_small_and_large_readable_bounds_and_explicit_cancel(self):
        self.assertIsNotNone(importlib.util.find_spec('render.recovery_overlay'),
                             'production recovery overlay missing')
        import pygame
        from render.recovery_overlay import RecoveryOverlay
        for width, height in ((640, 480), (1920, 1080)):
            overlay = RecoveryOverlay(width, height)
            self.addCleanup(overlay.cleanup)
            overlay.draw(dict(phase='draining', missing=[1, 2, 3], remaining=12.3,
                              progress=.5), width=width, height=height)
            self.assertTrue(any('Escape' in t for t in overlay.rendered_text))
            self.assertTrue(any('Player 2' in t for t in overlay.rendered_text))
            self.assertTrue(any('12.3' in t for t in overlay.rendered_text))
            self.assertTrue(any('50%' in t for t in overlay.rendered_text))
            for rect in overlay.text_bounds:
                self.assertTrue(overlay.panel_rect.contains(rect), str(rect))
                self.assertGreaterEqual(rect.height, 16)
            self.assertTrue(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)))
            self.assertFalse(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, repeat=True)))
            self.assertTrue(overlay.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP,
                                        button=1, pos=overlay.cancel_rect.center)))
            self.assertFalse(overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j)))
            overlay.draw(dict(phase='waiting', missing=[], remaining=None), width=width, height=height)
            self.assertTrue(any('Waiting' in t for t in overlay.rendered_text))

    def test_registered_fixture_cleanups_do_not_destroy_shared_font_ownership(self):
        from render.clean_classic import font
        from test_lan_recovery_handoff import HandoffTests
        cached = font(18)
        nested = RecoveryUITests('test_small_and_large_readable_bounds_and_explicit_cancel')
        nested.setUp()
        try:
            nested.test_small_and_large_readable_bounds_and_explicit_cancel()
        finally:
            nested.doCleanups()
        handoff = HandoffTests('test_application_install_validates_then_rebuilds_real_graph')
        handoff.setUp()
        try:
            handoff.test_application_install_validates_then_rebuilds_real_graph()
        finally:
            handoff.doCleanups()
        self.assertIs(font(18), cached)
        self.assertGreater(cached.render('shared cached font remains alive', True, (255, 255, 255)).get_width(), 0)

    def test_cleanup_keeps_shared_cached_fonts_alive(self):
        self.assertIsNotNone(importlib.util.find_spec('render.recovery_overlay'))
        import pygame
        from render.clean_classic import font
        from render.recovery_overlay import RecoveryOverlay
        cached = font(18)
        overlay = RecoveryOverlay(640, 480)
        overlay.cleanup()
        self.assertIs(font(18), cached)
        self.assertGreater(cached.render('still alive', True, (255, 255, 255)).get_width(), 0)
        self.assertTrue(pygame.font.get_init())


if __name__ == '__main__':
    unittest.main()
