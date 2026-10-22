"""CPU-only production main helpers, without importing its SDL/GL bootstrap."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import os
import pygame

SOURCE = Path(__file__).resolve().parents[1] / 'main.py'


def helpers(*names, **env):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    env.update(pygame=pygame, os=os)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env


class HybridDispatchTests(unittest.TestCase):
    def env(self):
        return helpers('dispatch_game_event', '_GameEventDispatcher', mode='game', running=True,
                       cinematic=None, presentation=None, playback=None, SMOKE=False,
                       SAVES_DIR='/saved', inputc=Mock(), handle_recovery_event=Mock(return_value=False),
                       handle_presentation_input=Mock(return_value=False),
                       handle_network_event=Mock(return_value=False), handle_game_input=Mock(),
                       write_save=Mock(), flash=Mock(), rebuild=Mock(), toggle_fullscreen=Mock(),
                       escape_from_decided_match=Mock(return_value=False))

    def test_bridge_dispatches_app_quicksave_before_controller(self):
        env = self.env()
        self.assertIn('_GameEventDispatcher', env, 'native events need the application dispatcher')
        target = env['_GameEventDispatcher']()
        target.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
        env['write_save'].assert_called_once_with('/saved/quicksave.json')
        env['handle_game_input'].assert_not_called()

    def test_poll_delivers_real_ring_quicksave_through_application(self):
        import tempfile
        from render_bridge import input as wire, ring
        from render.input_bridge import RingInput
        env = self.env()
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
            path = Path(directory) / 'input.bin'
            with ring.Ring.create(path, slots=8, slot_bytes=4096) as writer:
                writer.publish(wire.encode_batch([wire.Event(wire.KEY_DOWN, code=wire.KEYCODE_F1 + 4)]))
                with RingInput(path, env['_GameEventDispatcher'](), (1280, 800), from_oldest=True) as bridge:
                    self.assertEqual(bridge.poll(limit=1), 1)
        env['write_save'].assert_called_once_with('/saved/quicksave.json')
        env['handle_game_input'].assert_not_called()

    def test_poll_honors_leave_without_accessing_closed_bridge(self):
        cpp = dict(input=Mock(), failed=False)
        bridge = cpp['input']
        bridge.poll.side_effect = lambda **kwargs: cpp.update(input=None)
        session = SimpleNamespace(paths={'input': Mock()})
        env = helpers('cpp_poll_input', RENDERER='cpp', CPP=cpp, state=object(),
                      gm=SimpleNamespace(ds=object()), local_player=0,
                      cpp_session=Mock(return_value=session), cpp_reset=Mock(), flash_print=Mock())
        env['cpp_poll_input']()
        bridge.poll.assert_called_once_with(limit=1)
        env['cpp_reset'].assert_not_called()
        self.assertNotIn('quit', cpp)

    def test_modal_recovery_precedes_save_and_presentation(self):
        env = self.env()
        env['handle_recovery_event'].return_value = True
        env['dispatch_game_event'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
        env['write_save'].assert_not_called()
        env['handle_presentation_input'].assert_not_called()

    def test_replay_quickload_uses_replay_gate(self):
        env = self.env()
        env['playback'] = object()
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9)
        env['dispatch_game_event'](event)
        env['handle_game_input'].assert_called_once_with(event)
        env['rebuild'].assert_not_called()

    def test_old_ring_batch_stops_after_replacement_and_leave(self):
        env = self.env()
        target = env['_GameEventDispatcher']()
        env['inputc'] = Mock()
        target.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
        env['write_save'].assert_not_called()
        env['mode'] = 'menu'
        env['dispatch_game_event'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
        env['write_save'].assert_not_called()

    def test_local_loop_uses_same_dispatcher_and_polls_before_simulation(self):
        tree = ast.parse(SOURCE.read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        text = ast.unparse(loop)
        self.assertIn('dispatch_game_event(ev)', text)
        self.assertIn('cpp_poll_input()', text)
        self.assertLess(text.index('cpp_poll_input()'), text.index('step_game_frame(dt_frame)'))
        self.assertLess(text.index('cpp_poll_input()'), text.index('inputc.update(dt_frame)'))
        publish = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cpp_publish')
        self.assertNotIn('.poll(limit=1)', ast.unparse(publish))


class HybridLifecycleTests(unittest.TestCase):
    def test_native_leave_prevents_same_frame_simulation(self):
        tree = ast.parse(SOURCE.read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        once = ast.For(target=ast.Name(id='_frame', ctx=ast.Store()),
                       iter=ast.Call(func=ast.Name(id='range', ctx=ast.Load()), args=[ast.Constant(1)], keywords=[]),
                       body=loop.body, orelse=[])
        env = dict(mode='game', running=True, clock=Mock(), TICK_RATE=30,
                   poll_network=Mock(), sync_campaign_outcome=Mock(), presentation=None,
                   cinematic=None, CPP={}, step_game_frame=Mock())
        env['clock'].tick.return_value = 33
        env['cpp_poll_input'] = lambda: env.update(mode='menu')
        from unittest.mock import patch
        with patch.object(pygame.event, 'get', return_value=[]):
            env['pygame'] = pygame
            exec(compile(ast.fix_missing_locations(ast.Module(body=[once], type_ignores=[])),
                         str(SOURCE), 'exec'), env)
        env['step_game_frame'].assert_not_called()

    def test_native_frame_reaches_real_autosave_tail_once(self):
        tree = ast.parse(SOURCE.read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        start = next(i for i, n in enumerate(loop.body) if isinstance(n, ast.AugAssign)
                     and isinstance(n.target, ast.Name) and n.target.id == 'frames')
        env = dict(frames=0, fps_time=0., dt_frame=.03, state=SimpleNamespace(time=60., game_over=False),
                   playback=None, net_session=None, last_autosave=0., SETTINGS={}, SMOKE=False,
                   native_drawn=True, write_save=Mock(), SAVES_DIR='/saved', os=os)
        exec(compile(ast.Module(body=loop.body[start:], type_ignores=[]), str(SOURCE), 'exec'), env)
        env['write_save'].assert_called_once_with('/saved/autosave_0.json')
        self.assertEqual(env['last_autosave'], 60.)
        self.assertEqual(env['frames'], 1)

    def test_native_cinematic_publishes_frozen_world_and_never_draws_legacy(self):
        cinematic = SimpleNamespace(update=Mock(), compose=Mock(return_value=object()),
                                    draw_gl=Mock(), finished=False)
        env = helpers('draw_campaign_presentation', cinematic=cinematic, accumulator=5.,
                      RENDERER='cpp', CPP={'failed': False}, SMOKE=False,
                      camera=Mock(), renderer=Mock(), hud=Mock(), CPP_HUD_SIZE=(1280, 800),
                      cpp_publish=Mock(return_value=True), cpp_drawing=Mock(return_value=True),
                      state=object(), gm=SimpleNamespace(ds=object()), local_player=0,
                      inputc=SimpleNamespace(selection=set()), fps=30.)
        from unittest.mock import patch
        with patch.object(pygame.display, 'flip') as flip:
            env['draw_campaign_presentation'](.03)
        self.assertTrue(env['cpp_publish'].called, 'cinematic must reach the native display')
        self.assertEqual(env['cpp_publish'].call_args.args[4], 0.)
        env['renderer'].draw.assert_not_called()
        env['hud'].resize.assert_not_called()
        cinematic.draw_gl.assert_not_called()
        flip.assert_not_called()
        self.assertEqual(env['accumulator'], 0.)

    def test_native_cinematic_restores_host_before_legacy_when_viewer_is_gone(self):
        cinematic = SimpleNamespace(update=Mock(), draw_gl=Mock(), finished=False)
        calls = Mock()
        hud = SimpleNamespace(width=1280, height=800, resize=calls.resize)
        env = helpers('draw_campaign_presentation', cinematic=cinematic, accumulator=5.,
                      RENDERER='cpp', CPP={'failed': False, 'fell_back': False}, SMOKE=False,
                      camera=Mock(), renderer=calls.renderer, hud=hud, CPP_HUD_SIZE=(1280, 800),
                      cpp_publish=Mock(return_value=True), cpp_drawing=Mock(return_value=False),
                      cpp_reset=calls.reset, W=1440, H=900,
                      state=object(), gm=SimpleNamespace(ds=object()), local_player=0, fps=30.)

        def resize(width, height):
            self.assertFalse(env['CPP']['fell_back'], 'resize must precede the fallback latch')
            hud.width, hud.height = width, height

        def draw(*args):
            self.assertEqual((hud.width, hud.height), (1440, 900))
            self.assertTrue(env['CPP']['fell_back'])

        hud.resize.side_effect = resize
        env['renderer'].draw.side_effect = draw
        from unittest.mock import patch, call
        with patch.object(pygame.display, 'flip') as flip:
            env['draw_campaign_presentation'](.03)
            env['draw_campaign_presentation'](.03)  # intro continues after fallback is latched
        env['cpp_publish'].assert_called_once()
        env['cpp_drawing'].assert_called_once()
        self.assertEqual(calls.mock_calls, [call.reset(), call.resize(1440, 900),
                                          call.renderer.draw(0.0, set()),
                                          call.renderer.draw(0.0, set())])
        self.assertEqual(env['camera'].apply.call_args_list,
                         [call(1280, 800), call(1440, 900), call(1440, 900)])
        self.assertEqual(cinematic.draw_gl.call_args_list, [call(1440, 900), call(1440, 900)])
        self.assertEqual(flip.call_count, 2)

    def test_native_publish_includes_presentation_and_recovery_surfaces(self):
        session = Mock()
        presentation = Mock()
        presentation.draw.return_value = 'help surface'
        presentation.panel_rects = ['help rect']
        recovery = Mock()
        recovery.draw.return_value = 'recovery surface'
        env = helpers('cpp_publish', 'cpp_overlay_layers', CPP={},
                      cpp_session=Mock(return_value=session), cpp_seen_ids=Mock(return_value=set()),
                      cpp_reset=Mock(), flash_print=Mock(), presentation=presentation,
                      recovery_overlay=recovery, cinematic=None, sync_recovery_overlay=Mock(),
                      hud=SimpleNamespace(blocked_rects=['hud rect', 'help rect']), CPP_HUD_SIZE=(1280, 800),
                      state=object(), inputc=Mock(), local_player=0,
                      net_session=SimpleNamespace(recovery_snapshot={}))
        self.assertTrue(env['cpp_publish'](env['state'], object(), 0, set(), .03))
        self.assertEqual(session.publish.call_args.kwargs.get('overlay_layers'),
                         ['help surface', 'recovery surface'])
        self.assertIn('help rect', env['hud'].blocked_rects)
        self.assertEqual(presentation.draw.call_args.kwargs['blocked_rects'], ['hud rect'])

    def test_cpp_fullscreen_keeps_composition_pixel_dimensions(self):
        camera = SimpleNamespace(width=1280, height=800, _proj=object(), _view=object())
        hud = Mock()
        display = Mock()
        display.Info.return_value = SimpleNamespace(current_w=1920, current_h=1080)
        env = helpers('toggle_fullscreen', W=1440, H=900, FULLSCREEN=False,
                      RENDERER='cpp', CPP_HUD_SIZE=(1280, 800), CPP={'fell_back': False},
                      camera=camera, hud=hud, SMOKE=False, flash=Mock())
        from unittest.mock import patch
        with patch.object(pygame, 'display', display):
            env['toggle_fullscreen']()
        self.assertEqual((camera.width, camera.height), (1280, 800))
        hud.resize.assert_called_once_with(1280, 800)

    def test_empty_presentation_does_not_force_full_surface_uploads(self):
        presentation = Mock()
        presentation.panel_rects = []
        env = helpers('cpp_overlay_layers', presentation=presentation,
                      recovery_overlay=None, cinematic=None, state=object(),
                      CPP_HUD_SIZE=(1280, 800), inputc=Mock(), local_player=0,
                      hud=SimpleNamespace(blocked_rects=[]), sync_recovery_overlay=Mock())
        self.assertEqual(env['cpp_overlay_layers'](), [])

    def test_restore_keeps_the_gl_context_and_never_builds_a_second_window(self):
        # The rest of the contract (only after an iconification, SDL not pygame) lives in
        # tests/test_host_window.py; here the point is that restoring does not re-enter
        # pygame.display.set_mode, which would throw away the menu's cached textures.
        from unittest.mock import patch
        env = helpers('cpp_restore_window', CPP={'iconified': False})
        self.assertIn('cpp_restore_window', env)
        with patch('pygame.display.set_mode') as set_mode, \
                patch('pygame._sdl2.video.Window') as window:
            env['cpp_restore_window']()
        set_mode.assert_not_called()
        window.from_display_module.assert_not_called()

    def test_live_session_allocates_a_fresh_ring_directory(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            env = helpers('cpp_session', CPP={'session': None}, CPP_DIR=directory,
                          CPP_HUD_SIZE=(1280, 800), camera=object(), hud=object(), SMOKE=True)
            with patch('render_bridge.live.LiveSession') as session:
                env['cpp_session'](object(), object(), 0)
                first = session.call_args.kwargs['directory']
                first_owner = env['CPP']['directory']
                env['CPP']['session'] = None
                env['cpp_session'](object(), object(), 0)
                second = session.call_args.kwargs['directory']
                first_owner.cleanup()
                env['CPP']['directory'].cleanup()
            self.assertNotEqual(first, second, 'old input-ring counters must never cross matches')
            self.assertEqual(Path(first).parent, Path(directory))
            self.assertEqual(Path(second).parent, Path(directory))

    def test_reset_closes_every_owner_and_clears_match_caches(self):
        bridge, session, window = Mock(), Mock(), Mock()
        cpp = dict(input=bridge, session=session, window=window, failed='old failure',
                   seen={12}, seen_tick=400, selection={12}, quit=True, fell_back=True,
                   camera=object(), bridge_mark=(4, 5, 6))
        env = helpers('cpp_reset', CPP=cpp, inputc=SimpleNamespace(keys={1}, right_drag=(1, 2),
                      dragging=True, drag_start=(1, 1), drag_cur=(2, 2)))
        self.assertIn('cpp_reset', env, 'match resources must have an explicit reset')
        env['cpp_reset']()
        bridge.close.assert_called_once()
        session.close.assert_called_once()
        window.terminate.assert_called_once()
        window.wait.assert_called_once_with(timeout=1.0)
        for name in ('input', 'session', 'window'):
            self.assertIsNone(cpp[name])
        self.assertEqual(cpp['seen_tick'], -1)
        self.assertFalse(cpp['failed'])
        self.assertFalse(env['inputc'].keys)
        env['cpp_reset']()
        session.close.assert_called_once()

    def test_native_branch_has_no_continue_before_common_autosave(self):
        tree = ast.parse(SOURCE.read_text())
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        branch = next(n for n in loop.body if isinstance(n, ast.If) and
                      any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and
                          x.func.id == 'cpp_publish' for x in ast.walk(n)))
        self.assertFalse(any(isinstance(n, ast.Continue) for n in ast.walk(branch)),
                         'native rendering must reach the common autosave tail')

    def test_fresh_match_visibility_is_computed_on_tick_zero(self):
        state = SimpleNamespace(tick=0, entities={7: SimpleNamespace(id=7, alive=True)},
                                can_see=Mock(return_value=True))
        env = helpers('cpp_seen_ids', CPP={'seen_tick': -1, 'seen': set()})
        self.assertEqual(env['cpp_seen_ids'](state, 0), {7})
        state.can_see.assert_called_once_with(0, 7)

    def test_match_boundaries_reset_and_share_hud(self):
        tree = ast.parse(SOURCE.read_text())
        for name in ('start_game', 'install_recovered_manager', 'leave_game'):
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertIn('cpp_reset()', ast.unparse(fn), name)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cpp_session')
        self.assertIn('hud=hud', ast.unparse(fn))


if __name__ == '__main__':
    unittest.main()
