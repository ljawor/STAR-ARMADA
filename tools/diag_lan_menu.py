"""Real SDL/GL + TCP LAN acceptance. Run with PYTHONPATH=. .venv/bin/python.

Executes the trusted main.py prefix and unchanged one-frame loop, not a parallel
mock game implementation. No settings/saves are written; captures live in TMPDIR.
"""
import ast
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
from OpenGL.GL import glGetError, glViewport, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
from game.net.lan import LOADING_TIMEOUT, precise_checksum
from render.menus import MenuStack


def main():
    tree = ast.parse((ROOT / 'main.py').read_text())
    loop_index = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.While))
    prefix = ast.Module(body=tree.body[:loop_index], type_ignores=[])
    loop = ast.For(target=ast.Name(id='_diag_frame', ctx=ast.Store()),
                   iter=ast.Call(func=ast.Name(id='range', ctx=ast.Load()), args=[ast.Constant(1)], keywords=[]),
                   body=tree.body[loop_index].body, orelse=[])
    frame = compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])), str(ROOT / 'main.py'), 'exec')
    ns = dict(__name__='__lan_diag__', __file__=str(ROOT / 'main.py'))
    sessions, graphs = [], []
    out = Path.home() / '.hermes/cache/scratch/lan-menu-diag'
    out.mkdir(parents=True, exist_ok=True)
    with patch.object(sys, 'argv', ['main.py']), patch('render.menus.save_settings'), patch('render.menus.save_campaign_progress'):
        try:
            exec(compile(prefix, str(ROOT / 'main.py'), 'exec'), ns)
            ns['save_settings'] = lambda *a: None
            pygame.display.set_mode((800, 600), pygame.DOUBLEBUF | pygame.OPENGL)
            glViewport(0, 0, 800, 600)
            ns['W'], ns['H'] = 800, 600
            host_menu = ns['menu'] = MenuStack(800, 600)
            host_menu.screen = 'main'
            def step():
                exec(frame, ns)
            def click(menu, action, payload=None, actual=False):
                menu.render(0)
                b = next(b for b in menu.buttons if b['action'] == action and (payload is None or b['payload'] == payload))
                events = [pygame.event.Event(t, button=1, pos=b['rect'].center)
                          for t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)]
                if actual:
                    for ev in events:
                        pygame.event.post(ev)
                    step()
                else:
                    for ev in events:
                        menu.handle_event(ev)
            click(host_menu, 'goto_lan', actual=True)
            click(host_menu, 'lan_host_setup', actual=True)
            assert ns['gm'] is None
            click(host_menu, 'lan_map', 'skirmish03', actual=True)
            click(host_menu, 'lan_ai', 1, actual=True)
            click(host_menu, 'lan_cooperative', actual=True)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            click(host_menu, 'lan_field', 'lan_port', actual=True)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL, unicode='a'))
            pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=str(port)))
            step()
            assert host_menu.lan_port == str(port)
            click(host_menu, 'lan_field', 'lan_name', actual=True)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL, unicode='a'))
            pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text='Host diagnostic'))
            step()
            click(host_menu, 'lan_connect', actual=True)
            host = host_menu.lan_session
            assert host is not None, host_menu.lan_notice
            sessions.append(host)
            client_menu = MenuStack(800, 600)
            client_menu.screen = 'lan_join'
            client_menu.lan_port = str(port)
            client_menu.lan_name = 'Client diagnostic'
            click(client_menu, 'lan_connect')
            client = client_menu.lan_session
            sessions.append(client)
            deadline = time.monotonic() + 8
            while len(host.snapshot['players']) < 2 or len(client.snapshot['players']) < 2:
                assert time.monotonic() < deadline, (host.snapshot, client.snapshot)
                step()
                client_menu.apply_pending()
            assert 'lan_start' not in [b['action'] for b in host_menu.buttons]
            # Reconfigure via the actual host lobby, retaining both sockets.
            click(host_menu, 'lan_edit', actual=True)
            click(host_menu, 'lan_difficulty', actual=True)
            click(host_menu, 'lan_connect', actual=True)
            assert host_menu.lan_session is host
            assert host.snapshot['options']['ai_difficulty'] == 'hard'
            # The client must see the edited setup before consenting to it.
            deadline = time.monotonic() + 8
            while client.snapshot.get('revision') != host.snapshot.get('revision'):
                assert time.monotonic() < deadline, (host.snapshot, client.snapshot)
                step()
                client_menu.apply_pending()
            click(host_menu, 'lan_ready', actual=True)
            click(client_menu, 'lan_ready')
            deadline = time.monotonic() + 8
            while not host.snapshot['can_start']:
                assert time.monotonic() < deadline
                step()
                client_menu.apply_pending()
            host_menu.render(0)
            host_menu.draw_gl()
            data = glReadPixels(0, 0, 800, 600, GL_RGB, GL_UNSIGNED_BYTE)
            image = pygame.transform.flip(pygame.image.frombuffer(data, (800, 600), 'RGB'), False, True)
            pygame.image.save(image, out / 'lobby.png')
            assert glGetError() == 0
            # Loading has a separate absolute budget, including both cold graphs.
            deadline = time.monotonic() + LOADING_TIMEOUT
            click(host_menu, 'lan_start', actual=True)
            assert ns['mode'] == 'game', host_menu.lan_notice
            host_gm = ns['gm']
            graphs.append(dict(ns))
            while client.launch is None:
                host.poll()
                client_menu.apply_pending()
                assert time.monotonic() < deadline, (host.snapshot, client.snapshot, client_menu.lan_notice)
            # A single SDL process has one mixer: release the host viewpoint
            # before constructing the client's audio (real apps are separate).
            ns['audio'].cleanup()
            ns['audio'] = None
            graphs[0]['audio'] = None
            # Fresh globals, same real factories, one window/context.
            client_ns = dict(ns)
            for key in ('gm', 'state', 'camera', 'renderer', 'hud', 'audio', 'inputc', 'net_session'):
                client_ns[key] = None
            functions = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))], type_ignores=[])
            exec(compile(functions, str(ROOT / 'main.py'), 'exec'), client_ns)
            client_ns['menu'] = client_menu
            client_ns['start_game'](lan_session=client)
            assert time.monotonic() < deadline, 'Cold object graphs exceeded loading budget'
            client_ns['mode'] = 'game'
            ns = client_ns
            graphs.append(ns)
            st = ns['state']
            assert ns['local_player'] == 1
            assert all(ns[k].local_player == 1 for k in ('renderer', 'hud', 'audio', 'inputc'))
            assert not st.players[0].is_ai and not st.players[1].is_ai and st.players[2].is_ai
            assert st.players[0].team == st.players[1].team != st.players[2].team
            own = next(e for e in st.entities.values() if e.owner == 1 and e.is_ship)
            ns['inputc'].selection = {own.id}
            # Real input -> human hook, no immediate local execution.
            submitted = []
            real_submit = client.submit
            def submit(command, tick):
                submitted.append((command, tick))
                return real_submit(command, tick)
            client.submit = submit
            # Stop has been on Backspace since #48/#63; S pans the view, so the
            # old K_s probe no longer submits anything (stale since that merge).
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, unicode='', mod=0))
            before = len(st.command_queue)
            step()
            assert len(st.command_queue) == before
            assert len(submitted) == 1 and submitted[0][0].player == 1
            assert submitted[0][0].unit_ids == (own.id,)
            assert ns['hud'].local_player == 1
            for key in (pygame.K_p, pygame.K_F5, pygame.K_F9):
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode='', mod=0))
            step()
            assert not ns['paused'] and ns['net_session'] is client
            deadline = time.monotonic() + 12
            while st.tick < 10:
                host.advance(host_gm, ns['TICK_DT'])
                step()
                assert ns['mode'] == 'game', ns['menu'].lan_notice
                assert time.monotonic() < deadline
            # Catch host up only; compare exact current tick, no renderer mutation.
            while host_gm.state.tick < st.tick:
                host.advance(host_gm, ns['TICK_DT'])
                client.poll()
            assert host_gm.state.tick == st.tick
            assert precise_checksum(host_gm) == precise_checksum(ns['gm'])
            assert len(submitted) == 1, 'AI must not enter the human network hook'
            assert glGetError() == 0
            ns['camera'].apply(800, 600)
            ns['renderer'].draw(.033, ns['inputc'].selection)
            ns['hud'].render(ns['inputc'].selection, None, 1, False)
            ns['hud'].draw_gl()
            data = glReadPixels(0, 0, 800, 600, GL_RGB, GL_UNSIGNED_BYTE)
            image = pygame.transform.flip(pygame.image.frombuffer(data, (800, 600), 'RGB'), False, True)
            pygame.image.save(image, out / 'client.png')
            # #69: Escape aborts the current operation first; a single press
            # must not drop a networked player out of a live match.
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
            step()
            assert ns['mode'] == 'game', 'one Escape left the match'
            assert ns['net_session'] is not None, 'one Escape closed the session'
            pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0))
            step()
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
            step()
            assert ns['mode'] == 'menu' and ns['net_session'] is None
            host.poll()
            graphs[0]['poll_network']()
            assert graphs[0]['poll_network'].__globals__['mode'] == 'menu'
            print(f'LAN_MENU_DIAG_OK tick={st.tick} port={port} client_slot=1 human_submits=1 captures={out}')
        finally:
            for session in sessions:
                if session is not None:
                    session.close()
            for graph in graphs:
                for key in ('renderer', 'hud'):
                    if graph.get(key) is not None:
                        graph[key].close()
                if graph.get('renderer') is not None:
                    assert not graph['renderer'].ship_lists
                    assert graph['renderer']._unit_sphere_tex is None
                if graph.get('hud') is not None:
                    assert graph['hud'].tex is None
                if graph.get('audio') is not None and pygame.mixer.get_init() is not None:
                    graph['audio'].cleanup()
            if ns.get('menu') is not None:
                for menu in (ns['menu'], locals().get('host_menu')):
                    if menu is not None:
                        menu.close()
                        assert menu.overlay_tex is None and menu.lan_session is None
            pygame.quit()


if __name__ == '__main__':
    main()
