"""Independent recovery handoff seam; no application startup or network hooks."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.data.store import DataStore
from game.net.replay import MatchRecording, PlaybackSession, state_checksum
from game.net.replay_validation import reconstruct

ROOT = Path(__file__).resolve().parents[1]

APPLICATION_PROBE = r'''
"""Launch the unchanged real application, driving a real peer via tracing."""
import ast
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import tempfile
import time

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.chdir(ROOT)
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['STAR_ARMADA_MSAA'] = '0'
EVIDENCE = Path(sys.argv[2])
EVIDENCE.mkdir(parents=True, exist_ok=True)
import render.menus as menus
from game.net.replay import MatchRecording, PlaybackSession
from game.net.lan import precise_checksum
from test_lan import pump, free_port
from game.core.manager import GameManager
import pygame
from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE, glFinish, glReadBuffer, GL_BACK

source = ROOT / 'main.py'
tree = ast.parse(source.read_text())
loop = next(n for n in tree.body if isinstance(n, ast.While))
first_line = loop.body[0].lineno
screen_line = next(n.lineno for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'screen' for t in n.targets))
flip_line = max(n.lineno for n in ast.walk(loop)
                if isinstance(n, ast.Call) and ast.unparse(n.func) == 'pygame.display.flip')
started = False
lost = False
installed = False
saw_overlay = False
frames = 0
peer = peer_manager = peer_rec = initial_manager = original_recording = None
client_menu = None
last_tick = -1
future_hashes = []
paid_clicks = 0
paid_payloads = []
start_time = time.monotonic()

def sample(env):
    global last_tick
    if (installed and env['state'].tick == peer_manager.state.tick
            and env['state'].tick != last_tick):
        digest = precise_checksum(env['gm'])
        assert digest == precise_checksum(peer_manager)
        last_tick = env['state'].tick
        future_hashes.append(dict(tick=last_tick, hash=digest))
    if installed and env['state'].tick >= 42 and len(future_hashes) >= 20 and env['state'].tick == peer_manager.state.tick:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        return True
    return False


def trace(frame, event, arg):
    global started, lost, installed, saw_overlay, frames, paid_clicks
    global peer, peer_manager, peer_rec, initial_manager, original_recording, client_menu, last_tick
    if frame.f_code.co_filename != str(source):
        return None
    if event == 'return' and frame.f_code.co_name == 'cpp_publish' and arg is True:
        observe_overlay(env=frame.f_globals, front=True)
    if event != 'line':
        return trace
    env = frame.f_globals
    if frame.f_lineno == screen_line:
        env['W'], env['H'] = 800, 600
    if frame.f_lineno == first_line:
        frames += 1
        assert frames < 500 and time.monotonic() - start_time < 45, ('app stalled', frames,
            env.get('mode'), getattr(env.get('state'), 'tick', None),
            peer.snapshot if peer else None, getattr(peer_manager.state, 'tick', None) if peer_manager else None,
            env['net_session'].snapshot if env.get('net_session') else None)
        if not started:
            host_menu = env['menu']
            port = free_port()
            host_menu.screen, host_menu.lan_port = 'lan_host', str(port)
            host_menu._connect_lan()
            client_menu = menus.MenuStack(800, 600)
            client_menu.screen, client_menu.lan_port = 'lan_join', str(port)
            client_menu.lan_address = '127.0.0.1'
            client_menu._connect_lan()
            host, peer = host_menu.lan_session, client_menu.lan_session
            assert host._recovery and peer._recovery
            pump([host, peer], lambda: len(peer.snapshot['players']) == 2)
            host.set_ready(True)
            peer.set_ready(True)
            pump([host, peer], lambda: host.snapshot['can_start'])
            host.start()
            pump([host, peer], lambda: peer.launch is not None)
            app_session, peer = ((host, peer) if os.environ.get('STAR_ARMADA_APP_ROLE', 'host') == 'host'
                                 else (peer, host))
            env['start_game'](lan_session=app_session)
            # Match ownership moves out of the real host lobby.
            host_menu.lan_session = None
            client_menu.lan_session = None
            env['mode'] = 'game'
            initial_manager = env['gm']
            original_recording = env['recording']
            peer_manager = GameManager.start_skirmish(peer.launch['map_def'])
            peer_manager.state._net_session = peer
            peer_rec = MatchRecording(peer_manager, mode='lan')
            started = True
        assert not env['CPP'].get('failed'), env['CPP'].get('failed')
        host = env['net_session']
        assert host is not None and env['mode'] == 'game', env['menu'].lan_notice
        if env['gm'] is not initial_manager:
            installed = True
            assert env['recording'] is original_recording
            assert original_recording.gm is env['gm']
            assert env['audio'].state is env['state']
            assert env['renderer'].ds is env['gm'].ds
            assert env['camera']._scene is env['state']
        if ((paid_clicks == 0 and env['state'].tick >= 3)
                or (paid_clicks == 1 and installed and env['state'].tick >= 16)):
            state, controller, hud = env['state'], env['inputc'], env['hud']
            slot = env['local_player']
            yard = next(e for e in state.entities.values() if e.owner == slot and e.data_id == 'shipyard')
            controller.selection = {yard.id}
            hud.render(controller.selection, None, slot, False, '', 0., 30.)
            button = next(b for b in hud.buttons if b['kind'] == 'build_ship')
            paid_payloads.append(button['payload'])
            point = button['rect'].center
            if getattr(env['CPP'].get('window'), 'embedded', False):
                logical = env['CPP_HUD_SIZE']
                point = tuple(round(point[i] * (env['W'], env['H'])[i] / logical[i]) for i in range(2))
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                button=1, pos=point))
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP,
                                                button=1, pos=point))
            paid_clicks += 1
        if env['state'].tick >= 12 and not lost:
            peer._peers[0].sock.shutdown(socket.SHUT_RDWR)
            lost = True
        if sample(env):
            return trace
        peer.poll()
        assert peer.snapshot['status'] != 'error', peer.snapshot
        if peer.snapshot['status'] == 'recovering':
            peer.recovery_step(peer_manager)
            candidate = peer.take_restored_manager()
            if candidate is not None:
                assert precise_checksum(candidate) == precise_checksum(peer_manager)
                peer_rec.rebind_manager(candidate)
                peer_manager = candidate
                candidate.state._net_session = peer
                peer.acknowledge_install(candidate)
        elif peer_manager.state.tick <= env['state'].tick:
            peer.advance(peer_manager, 1/30)
        if sample(env):
            return trace
    if frame.f_lineno == flip_line:
        observe_overlay(env)
    return trace


def observe_overlay(env, front=False):
    global saw_overlay
    if env.get('recovery_overlay') is None:
        return
    overlay = env['recovery_overlay']
    assert env['accumulator'] == 0
    assert all(overlay.panel_rect.contains(r) for r in overlay.text_bounds)
    if not saw_overlay:
        before = precise_checksum(env['gm'])
        env['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
        assert precise_checksum(env['gm']) == before
        from OpenGL.GL import GL_FRONT
        glFinish()
        glReadBuffer(GL_FRONT if front else GL_BACK)
        data = glReadPixels(0, 0, env['W'], env['H'], GL_RGB, GL_UNSIGNED_BYTE)
        glReadBuffer(GL_BACK)
        image = pygame.image.frombuffer(data, (env['W'], env['H']), 'RGB')
        pygame.image.save(pygame.transform.flip(image, False, True), str(EVIDENCE / 'full-app-recovering.png'))
        saw_overlay = True

with tempfile.TemporaryDirectory(dir=EVIDENCE.parent) as directory:
    menus.USER_DIR = directory
    menus.SAVES_DIR = str(Path(directory) / 'saves')
    menus.SETTINGS_PATH = str(Path(directory) / 'settings.json')
    menus.CAMPAIGN_PATH = str(Path(directory) / 'campaign.json')
    sys.argv = [str(source)]
    try:
        sys.settrace(trace)
        result = runpy.run_path(str(source), run_name='__main__')
    finally:
        sys.settrace(None)
        if peer_rec is not None:
            peer_rec.close()
        if peer is not None:
            peer.close()
        if client_menu is not None:
            client_menu.close()
    assert installed and saw_overlay, (installed, saw_overlay)
    builds = [e for e in original_recording.to_dict()['commands'] if e['cmd']['type'] == 'build_ship']
    assert len(builds) == 2, builds
    assert len({e['tick'] for e in builds}) == 2
    assert paid_clicks == 2
    for entry, payload in zip(builds, paid_payloads):
        assert entry['cmd']['ship_id'] == payload['ship_id']
    for rec, manager in ((original_recording, result['gm']), (peer_rec, peer_manager)):
        playback = PlaybackSession(rec.to_dict())
        while playback.gm.state.tick < manager.state.tick:
            playback.step()
        assert precise_checksum(playback.gm) == precise_checksum(manager)
        rec.save(EVIDENCE / ('host-replay.json' if rec is original_recording else 'peer-replay.json'))
    report = dict(app_role=os.environ.get('STAR_ARMADA_APP_ROLE', 'host'),
                  installed=installed, saw_overlay=saw_overlay, frames=frames,
                  natural_paid_clicks=paid_clicks, paid_recorded_once=builds,
                  host_tick=result['state'].tick, peer_tick=peer_manager.state.tick,
                  future_hashes=future_hashes, replays_verified=True,
                  isolated_paths=[menus.USER_DIR, menus.SAVES_DIR, menus.SETTINGS_PATH, menus.CAMPAIGN_PATH])
    (EVIDENCE / 'full-app-report.json').write_text(json.dumps(report, indent=2))
    print('FULL_APP_RECOVERY_OK ' + json.dumps(report))
'''



def game():
    return GameManager.start_skirmish(DataStore.get().maps['skirmish01'])


def restored(manager):
    return reconstruct(json.loads(json.dumps(manager.state.to_dict(precise=True))))


class HandoffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.directory = directory
        self.addCleanup(directory.cleanup)
        # AST loading does not initialize main/menus. Still pin all four paths
        # so future fixture changes cannot escape to user persistence.
        import render.menus as menus
        for name, value in dict(USER_DIR=directory.name, SAVES_DIR=directory.name,
                                SETTINGS_PATH=directory.name + '/settings.json',
                                CAMPAIGN_PATH=directory.name + '/campaign.json').items():
            scope = patch.object(menus, name, value)
            scope.start()
            self.addCleanup(scope.stop)
        store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', store)

    def test_launched_full_application_reconnect_and_paid_replay(self):
        import os
        import subprocess
        import sys
        evidence = Path(self.directory.name) / 'full-app'
        env = dict(os.environ, SDL_AUDIODRIVER='dummy')
        if env.get('SDL_VIDEODRIVER') == 'dummy':
            env.pop('SDL_VIDEODRIVER')
        child = subprocess.run([sys.executable, '-c', APPLICATION_PROBE, str(ROOT), str(evidence)],
                               cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
        report = json.loads((evidence / 'full-app-report.json').read_text())
        self.assertTrue(report['installed'])
        self.assertTrue(report['saw_overlay'])
        self.assertTrue(report['replays_verified'])
        self.assertEqual(report['natural_paid_clicks'], 2)
        self.assertEqual(len(report['paid_recorded_once']), 2)
        self.assertGreaterEqual(len(report['future_hashes']), 20)
        self.assertEqual(report['host_tick'], report['peer_tick'])

    def test_launched_joined_application_reconnect_and_paid_replay(self):
        import os
        with patch.dict(os.environ, {'STAR_ARMADA_APP_ROLE': 'join'}):
            self.test_launched_full_application_reconnect_and_paid_replay()

    def test_real_tcp_recovery_runs_production_driver_and_preserves_future_replay(self):
        from test_lan_production_reconnect import ProductionReconnectTests
        from game.net.lan import precise_checksum
        import socket
        import time
        helper = ProductionReconnectTests()
        self.addCleanup(helper.doCleanups)
        tree = ast.parse((ROOT / 'main.py').read_text())
        names = {'advance_simulation', 'drive_lan_recovery', 'lan_recovering'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names, 'production recovery driver missing')
        sessions, managers = helper.setup_match(3)
        recordings = [MatchRecording(m, mode='lan') for m in managers]
        for rec in recordings:
            self.addCleanup(rec.close)
        helper.align(sessions, managers, 12)
        tree = ast.parse((ROOT / 'main.py').read_text())
        names = {'advance_simulation', 'drive_lan_recovery', 'lan_recovering'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names, 'production recovery driver missing')
        installed = set()
        contexts = []
        for index, (session, manager, rec) in enumerate(zip(sessions, managers, recordings)):
            context = dict(net_session=session, gm=manager, state=manager.state,
                           accumulator=0., TICK_DT=1/30, paused=False,
                           playback=None, cinematic=None)
            # The installer itself is real-GL-tested separately; here the
            # production driver must transfer the real recorder before ACK.
            def install(candidate, context=context, rec=rec, index=index):
                self.assertEqual(candidate.state.tick, context['gm'].state.tick)
                self.assertEqual(precise_checksum(candidate), precise_checksum(context['gm']))
                rec.rebind_manager(candidate)
                context['gm'], context['state'] = candidate, candidate.state
                candidate.state._net_session = context['net_session']
                installed.add(index)
            context['install_recovered_manager'] = install
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'main.py'), 'exec'), context)
            contexts.append(context)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        end = time.monotonic() + 8
        while time.monotonic() < end:
            for context in contexts:
                context['net_session'].poll()
                self.assertNotEqual(context['net_session'].snapshot['status'], 'error')
                context['advance_simulation'](.25)
                if context['net_session'].snapshot['status'] == 'recovering':
                    self.assertEqual(context['accumulator'], 0.)
            if len(installed) == 3 and all(s.snapshot['status'] == 'running' for s in sessions):
                break
        self.assertEqual(installed, {0, 1, 2}, [s.recovery_snapshot for s in sessions])
        managers = [c['gm'] for c in contexts]
        helper.align(sessions, managers, max(m.state.tick for m in managers) + 30)
        for rec, manager in zip(recordings, managers):
            playback = PlaybackSession(rec.to_dict())
            while playback.gm.state.tick < manager.state.tick:
                playback.step()
            self.assertEqual(precise_checksum(playback.gm), precise_checksum(manager))

    def test_application_install_validates_then_rebuilds_real_graph(self):
        tree = ast.parse((ROOT / 'main.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == 'install_recovered_manager']
        self.assertEqual(len(nodes), 1, 'production atomic installer missing')
        import pygame
        from game.net.lan import LanSession, default_lan_options, precise_checksum
        from render.camera import Camera
        from render.renderer import Renderer
        from render.hud import HUD
        from render.input import InputController
        from render.audio import Audio
        font_owned = not pygame.font.get_init()
        display_owned = not pygame.display.get_init()
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((800, 600), pygame.OPENGL | pygame.DOUBLEBUF)
        def cleanup_subsystems():
            if display_owned:
                pygame.display.quit()
            if font_owned:
                from render.clean_classic import font
                font.cache_clear()
                pygame.font.quit()
        self.addCleanup(cleanup_subsystems)
        old = game()
        import socket
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        session = LanSession.host(port, default_lan_options())
        self.addCleanup(session.close)
        old.state._net_session = session
        cam = Camera(800, 600)
        ren = Renderer(old.state, cam)
        hud = HUD(800, 600, old.state)
        hud.set_camera_ref(cam)
        inp = InputController(old.state, cam, hud, None)
        audio = Audio(old.state, muted=True)
        self.addCleanup(audio.cleanup)
        rec = MatchRecording(old, mode='lan')
        self.addCleanup(rec.close)
        own = next(e.id for e in old.state.entities.values() if e.owner == 0 and e.is_ship)
        inp.selection = {own, 999999}
        inp.groups = {1: {own, 999999}}
        inp._pending_ability = {'unsafe': True}
        cam.follow_id = own
        namespace: dict = dict(gm=old, state=old.state, camera=cam, renderer=ren,
                         hud=hud, inputc=inp, audio=audio, recording=rec,
                         net_session=session, local_player=0, DataStore=DataStore,
                         W=800, H=600, CPP_HUD_SIZE=(1280, 800), SETTINGS={}, accumulator=99,
                         mission_def=None, last_autosave=0,
                         Camera=Camera, Renderer=Renderer, HUD=HUD,
                         InputController=InputController, _AppGlue=lambda: object())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'main.py'), 'exec'), namespace)
        def release_views():
            namespace['renderer'].close()
            namespace['hud'].close()
        self.addCleanup(release_views)
        candidate = restored(old)
        before = tuple(namespace[k] for k in ('gm', 'state', 'camera', 'renderer', 'hud', 'inputc'))
        # Fault injection only at render resource construction; wire, state and
        # hashes remain real. Failed preparations cannot alter any old refs.
        def fail(*args, **kwargs):
            raise RuntimeError('injected construction failure')
        for name in ('HUD', 'InputController', 'Renderer'):
            with patch.dict(namespace, {name: fail}):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    namespace['install_recovered_manager'](candidate)
            self.assertEqual(before, tuple(namespace[k] for k in ('gm', 'state', 'camera', 'renderer', 'hud', 'inputc')))
            self.assertIs(rec.gm, old)
            self.assertIs(audio.state, old.state)
            self.assertIs(DataStore._instance, old.ds)
        with patch.object(rec, 'rebind_manager', side_effect=RuntimeError('injected transfer failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                namespace['install_recovered_manager'](candidate)
        self.assertIs(audio.state, old.state)
        self.assertIs(audio.camera, None)
        self.assertEqual(before, tuple(namespace[k] for k in ('gm', 'state', 'camera', 'renderer', 'hud', 'inputc')))
        candidate.state.players[0].credits += 1
        with self.assertRaises(ValueError):
            namespace['install_recovered_manager'](candidate)
        self.assertEqual(before, tuple(namespace[k] for k in ('gm', 'state', 'camera', 'renderer', 'hud', 'inputc')))
        self.assertIs(rec.gm, old)
        candidate = restored(old)
        digest = precise_checksum(old)
        history = rec.to_dict()
        namespace['install_recovered_manager'](candidate)
        self.assertEqual(precise_checksum(candidate), digest)
        for name in ('renderer', 'hud', 'inputc', 'audio'):
            self.assertIs(namespace[name].state, candidate.state)
        self.assertIs(namespace['renderer'].ds, candidate.ds)
        self.assertIs(namespace['camera']._scene, candidate.state)
        self.assertIs(namespace['hud'].camera, namespace['camera'])
        self.assertIs(namespace['audio'].camera, namespace['camera'])
        self.assertEqual(namespace['inputc'].selection, {own})
        self.assertEqual(namespace['inputc'].groups, {1: {own}})
        self.assertIsNone(namespace['inputc']._pending_ability)
        self.assertEqual(namespace['camera'].follow_id, own)
        self.assertIs(candidate.state._net_session, session)
        self.assertIsNone(old.state._net_session)
        self.assertEqual(namespace['renderer']._frame_cache, {})
        self.assertIsNot(namespace['renderer'].fog, ren.fog)
        self.assertIs(rec.gm, candidate)
        self.assertEqual(history, rec.to_dict())
        self.assertEqual(namespace['accumulator'], 0)

    def test_audio_rebind_detaches_old_bus_without_reopening_mixer(self):
        import pygame
        from render.audio import Audio
        old = game()
        candidate = restored(old)
        audio = Audio(old.state, muted=True)
        self.addCleanup(audio.cleanup)
        self.assertTrue(callable(getattr(audio, 'rebind_state', None)),
                        'non-destructive audio transfer missing')
        mixer = pygame.mixer.get_init()
        sounds = audio.sounds
        audio.rebind_state(candidate.state, candidate.ds)
        audio.rebind_state(candidate.state, candidate.ds)
        self.assertEqual(pygame.mixer.get_init(), mixer)
        self.assertIs(audio.sounds, sounds)
        self.assertIs(audio.state, candidate.state)
        self.assertIs(audio._ds, candidate.ds)
        for callbacks in old.state.events._subs.values():
            self.assertFalse(any(getattr(fn, '__self__', None) is audio for fn in callbacks))
        for callbacks in candidate.state.events._subs.values():
            owned = [fn for fn in callbacks if getattr(fn, '__self__', None) is audio]
            self.assertLessEqual(len(owned), 1)
        audio.cleanup()
        for callbacks in candidate.state.events._subs.values():
            self.assertFalse(any(getattr(fn, '__self__', None) is audio for fn in callbacks))

    def test_recorder_closed_transfer_stays_closed(self):
        old = game()
        rec = MatchRecording(old, mode='lan')
        rec.close()
        candidate = restored(old)
        native = candidate.step
        rec.rebind_manager(candidate)
        self.assertEqual(candidate.step, native, 'handoff resurrected a closed recorder')
        candidate.step(1/30)
        self.assertEqual(rec.to_dict()['end_tick'], 0)

    def test_recorder_tick_zero_transfer_does_not_duplicate_initial_pending(self):
        old = game()
        own = next(e.id for e in old.state.entities.values() if e.owner == 0 and e.is_ship)
        old.state.queue_command(PlayerCommand('stop', 0, unit_ids=(own,)))
        rec = MatchRecording(old, mode='lan')
        self.addCleanup(rec.close)
        candidate = restored(old)
        rec.rebind_manager(candidate)
        candidate.step(1/30)
        self.assertEqual(rec.to_dict()['commands'], [], 'initial pending command recorded twice')
        replay = PlaybackSession(rec.to_dict())
        replay.step()
        self.assertEqual(replay.gm.state.to_dict(precise=True), candidate.state.to_dict(precise=True))

    def test_recorder_transfer_keeps_original_history_and_playback(self):
        self.assertTrue(callable(getattr(MatchRecording, 'rebind_manager', None)),
                        'explicit recording transfer missing')
        old = game()
        own = next(e.id for e in old.state.entities.values() if e.owner == 0 and e.is_ship)
        old.state.queue_command(PlayerCommand('stop', 0, unit_ids=(own,)))
        rec = MatchRecording(old, mode='lan')
        self.addCleanup(rec.close)
        old.step(1 / 30)
        old.state.queue_command(PlayerCommand('hold', 0, unit_ids=(own,)))
        old.step(1 / 30)
        original = rec.to_dict()
        candidate = restored(old)
        native = candidate.step
        rec.rebind_manager(candidate)
        rec.rebind_manager(candidate)
        self.assertEqual(old.step.__self__, old)
        self.assertEqual(candidate.step.__self__, rec)
        self.assertEqual(rec._step, native)
        old.step(1 / 30)
        self.assertEqual(rec.to_dict(), original)
        candidate.state.queue_command(PlayerCommand('stop', 0, unit_ids=(own,)))
        candidate.step(1 / 30)
        data = rec.to_dict()
        self.assertEqual(data['initial_state'], original['initial_state'])
        self.assertEqual([e['tick'] for e in data['commands']], [1, 2])
        self.assertEqual(data['end_tick'], 3)
        playback = PlaybackSession(data)
        for _ in range(3):
            playback.step()
        self.assertEqual(playback.gm.state.to_dict(precise=True), candidate.state.to_dict(precise=True))
        rec.close()
        rec.close()
        self.assertEqual(candidate.step, native)


if __name__ == '__main__':
    unittest.main()
