"""Two independent Python simulations over real localhost TCP.

Run: PYTHONPATH=. .venv/bin/python tools/diag_lan.py --out DIR --ticks 300
Default pacing repeats 33/33/34ms; --pacing clock uses real pygame Clock.tick(30).
Writes host/client per-tick precise hashes and counters, verifies every tick.
No renderer, mock transport, or fabricated state. Output failure is nonzero.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path, data):
    temporary = path.with_suffix('.pending')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def worker(args):
    from game.net.lan import LanSession, default_lan_options, precise_checksum
    from game.core.manager import GameManager
    from game.core.commands import MoveCommand
    from game.core.vectors import Vec3
    out = Path(args.out)
    # Initialize SDL before joining: device setup must not stall a live peer.
    clock = None
    if args.pacing == 'clock':
        import pygame
        pygame.display.init()  # initializes SDL timing without audio devices
        clock = pygame.time.Clock()
    if args.worker == 'host':
        opts = default_lan_options()
        opts.update(map_id='skirmish04', ai_count=1, cooperative=True)
        session = LanSession.host(args.port, opts)
        write_json(out/'listening.json', dict(port=session.port))
    else:
        session = LanSession.join('127.0.0.1', args.port)
    try:
        ready = False
        deadline = time.monotonic() + 45
        while not session.launch:
            session.poll()
            if session.snapshot['error']:
                raise RuntimeError(session.snapshot['error'])
            if not ready and session.snapshot['status'] == 'lobby' and len(session.snapshot['players']) == 2:
                session.set_ready(True)
                ready = True
            if session.snapshot['can_start']:
                session.start()
            if time.monotonic() > deadline:
                raise RuntimeError('Lobby deadline')
            time.sleep(.001)
        gm = GameManager.start_skirmish(session.launch['map_def'])
        gm.state._net_session = session
        pid = session.local_player
        ship = next(e for e in gm.state.entities.values() if e.owner == pid and e.is_ship and not e.is_squadron)
        start = (ship.pos.x, ship.pos.z)
        hashes = [precise_checksum(gm)]
        queued_ticks = set()
        human_commands = 0
        ai_commands = 0
        polls = 0
        import ast
        tree = ast.parse((ROOT/'main.py').read_text())
        advance_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'advance_simulation')
        main = dict(gm=gm, state=gm.state, net_session=session, accumulator=0.,
                    paused=False, TICK_DT=1/30)
        exec(compile(ast.Module(body=[advance_node], type_ignores=[]), 'main.py', 'exec'), main)
        # Match main's initialized SDL Clock, not an idealized 1/30 delta.
        if clock is not None:
            clock.tick()  # exclude lobby/device setup from the first delta
        started = time.monotonic()
        next_frame = started
        max_advance = 0.
        while gm.state.tick < args.ticks:
            tick = gm.state.tick
            if tick in (0, args.ticks//2) and tick not in queued_ticks:
                queued_ticks.add(tick)
                factor = .8 if tick == 0 else .6
                gm.state.queue_command(MoveCommand(pid, [ship.id], Vec3(start[0]*factor, 0, start[1]*factor)))
                human_commands += 1
            if clock is not None:
                dt_frame = clock.tick(30) / 1000
            else:
                dt_frame = (33, 33, 34)[polls % 3] / 1000
                next_frame += dt_frame
                time.sleep(max(0., next_frame-time.monotonic()))
            polls += 1
            frame_start = time.monotonic()
            session.poll()  # main's normal per-render poll
            main['advance_simulation'](dt_frame)
            max_advance = max(max_advance, time.monotonic()-frame_start)
            if gm.state.tick != tick:
                hashes.append(precise_checksum(gm))
                ai_commands += sum(gm.state.players[c.player].is_ai for c in gm.state.command_queue)
            if session.snapshot['error']:
                raise RuntimeError(session.snapshot['error'])
            if time.monotonic() > deadline:
                raise RuntimeError('Simulation deadline')
        result = dict(role=args.worker, pacing=args.pacing, pid=os.getpid(), ticks=gm.state.tick,
                      checksums=hashes, human_commands=human_commands,
                      ai_commands=ai_commands, polls=polls,
                      elapsed=time.monotonic()-started,
                      ticks_per_second=gm.state.tick/(time.monotonic()-started),
                      max_advance=max_advance,
                      human_moved=(ship.pos.x, ship.pos.z) != start)
        write_json(out/f'{args.worker}.json', result)
        other = out/('client.json' if args.worker == 'host' else 'host.json')
        while not other.exists() and time.monotonic() < deadline:
            session.poll()
            time.sleep(.001)
        if not other.exists():
            raise RuntimeError('Peer report deadline')
    finally:
        session.close()


def _verification_problems(reports, ticks):
    """Name every failed clause: 'Hash/counter verification failed' alone made a
    cross-platform CI failure impossible to diagnose (a host with no route, a
    slow runner and a real divergence all read the same)."""
    host, client = reports
    problems = []
    if host['checksums'] != client['checksums']:
        first = next((i for i, (a, b) in enumerate(zip(host['checksums'], client['checksums']))
                      if a != b), None)
        problems.append(f'checksums differ (first at index {first} of {ticks + 1})')
    for label, report in zip(('host', 'client'), reports):
        if len(report['checksums']) != ticks + 1:
            problems.append(f'{label} compared {len(report["checksums"])} of {ticks + 1} ticks')
        if report['ticks'] != ticks:
            problems.append(f'{label} simulated {report["ticks"]} of {ticks} ticks')
        if not report['human_moved']:
            problems.append(f'{label} human ship never moved')
        if report['ai_commands'] == 0:
            problems.append(f'{label} saw no AI commands')
        if report['ticks_per_second'] < 27.:
            # Pacing, not correctness: a slow/overloaded host cannot accept this
            # gate, so it is reported separately from a state divergence.
            problems.append(f'{label} paced {report["ticks_per_second"]:.1f} ticks/s '
                            f'(below the 27 ticks/s LAN floor)')
    return problems


def diagnostic(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('host.json', 'client.json', 'listening.json'):
        (out/name).unlink(missing_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    children = []
    logs = []
    try:
        for role in ('host', 'client'):
            if role == 'client':
                deadline = time.monotonic()+10
                while not (out/'listening.json').exists():
                    if children[0].poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Host failed to listen; see host.log')
                    time.sleep(.01)
            log = (out/f'{role}.log').open('w')
            logs.append(log)
            children.append(subprocess.Popen([sys.executable, __file__, '--worker', role,
                                              '--port', str(port), '--out', str(out),
                                              '--ticks', str(args.ticks), '--pacing', args.pacing], cwd=ROOT,
                                             stdout=log, stderr=subprocess.STDOUT))
        for child in children:
            if child.wait(timeout=55):
                raise RuntimeError(f'Worker {child.pid} failed; see logs in {out}')
        reports = [json.loads((out/f'{r}.json').read_text()) for r in ('host', 'client')]
        problems = _verification_problems(reports, args.ticks)
        if problems:
            raise RuntimeError('Hash/counter verification failed: ' + '; '.join(problems))
        summary = dict(pacing=args.pacing, ticks=args.ticks, checksums_compared=args.ticks+1,
                       processes=[r['pid'] for r in reports],
                       ticks_per_second=[r['ticks_per_second'] for r in reports],
                       max_advance=[r['max_advance'] for r in reports],
                       human_commands=[r['human_commands'] for r in reports],
                       ai_commands=[r['ai_commands'] for r in reports], result='DIAG_LAN_OK')
        write_json(out/'summary.json', summary)
        print(json.dumps(summary))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='saves/diag_lan')
    parser.add_argument('--ticks', type=int, default=180)
    parser.add_argument('--port', type=int, default=7777)
    parser.add_argument('--worker', choices=('host', 'client'))
    parser.add_argument('--pacing', choices=('quantized', 'clock'), default='quantized')
    args = parser.parse_args()
    if args.ticks < 6:
        parser.error('ticks must be at least 6 to exercise AI')
    if args.worker:
        worker(args)
    else:
        diagnostic(args)
