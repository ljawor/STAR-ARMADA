"""Symmetric cross-platform LAN diagnostic (``--netdiag``, issue #56).

A mixed-platform connect failure needs both platforms, so this ships one
command that each machine runs once and writes one JSON file. Diff the two
files: bind address and port, every local address a peer could dial, the raw
``connect_ex`` code the game itself classifies, whether TCP arrived at the
listener, and — separately — whether the ``hello``/``welcome`` handshake
completed. That split is what tells a blocked SYN apart from a version or
content rejection.

Everything reachable locally runs through the real ``LanSession`` code, so the
report shows what the game does, not what a copy of it does::

    python main.py --netdiag info                    # environment + addresses + local pairing
    python main.py --netdiag listen --wait 60        # host side; the other machine dials it
    python main.py --netdiag connect --address A.B.C.D [--wait 20]

The frozen Windows build has no console (``console=False``), so the report is
the deliverable: it goes to ``--out`` (default ``<user dir>/netdiag/``), and on
Windows a message box shows the verdict and the file path::

    Start-Process -FilePath '.\\STAR ARMADA.exe' `
      -ArgumentList '--netdiag','listen','--wait','60' -Wait

Exit status: 0 diagnostic completed, 1 the probe found a connectivity failure,
2 the run itself failed (bad arguments, unwritable report path).
"""
from __future__ import annotations

import errno
import json
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone

from game import __version__ as GAME_VERSION
from game.data.store import DataStore
from game.net import lan as lan_module
from game.net.lan import (CONNECT_IN_PROGRESS, DEFAULT_PORT, PROTOCOL_VERSION, LanSession,
                          TIMEOUT, classify_connect_result, connect_failure_message,
                          content_hash, default_lan_options)

MODES = ('info', 'listen', 'connect')
_IN_PROGRESS_FAMILY = CONNECT_IN_PROGRESS - {0}
USAGE = (
    'usage: --netdiag [info|listen|connect] [--address IP] [--port N] '
    '[--wait SECONDS] [--out FILE] [--msgbox]\n'
    '  info     environment, local addresses, output path, local host+join pairing\n'
    '  listen   bind the TCP port and report every connection that reaches it\n'
    '  connect  dial a host address through the real join path and report the outcome\n'
)
# A black-holed destination (RFC 5737 TEST-NET-1) never answers, so a
# nonblocking connect to it stays in progress — the platform probe for the
# code the game must accept.
BLACK_HOLE = ('192.0.2.1', 7777)
LOOPBACK_PAIR_WAIT = 5.0
SIM_FINGERPRINT_TICKS = 60


# ----------------------------------------------------------------- reporting

def _say(line=''):
    """Console output that stays harmless in a console-less frozen build."""
    try:
        if sys.stdout is not None:
            sys.stdout.write(str(line) + '\n')
            sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        pass


def user_dir():
    """Writable user data directory, mirroring render.menus.USER_DIR.

    render.menus cannot be imported here: it pulls pygame and OpenGL, and a
    broken GL stack is a supported reason to run netdiag. tests/test_netdiag.py
    asserts the two agree whenever the path is not faked as frozen.
    """
    if not getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'STAR ARMADA')
    if os.name == 'nt':
        return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'STAR ARMADA')
    return os.path.join(os.environ.get('XDG_DATA_HOME',
                                       os.path.join(os.path.expanduser('~'), '.local', 'share')),
                        'STAR ARMADA')


def _content_hash():
    try:
        return content_hash(DataStore.get())
    except Exception as exc:                     # noqa: BLE001 - report, never crash
        return f'unavailable: {type(exc).__name__}: {exc}'


def environment():
    return dict(platform=sys.platform, os_name=os.name, machine=platform.machine(),
                os_release=platform.platform(), python=platform.python_version(),
                frozen=bool(getattr(sys, 'frozen', False)), executable=sys.executable,
                argv=list(sys.argv), cwd=os.getcwd(), user_dir=user_dir(),
                hostname=socket.gethostname(), game_version=GAME_VERSION,
                protocol_version=PROTOCOL_VERSION, content_hash=_content_hash(),
                started=datetime.now(timezone.utc).isoformat(timespec='seconds'))


def _address_caveat(address):
    if address.startswith('127.'):
        return 'loopback: only reachable on this machine'
    if address.startswith('169.254.'):
        return 'link-local: no DHCP lease, other machines cannot dial it'
    if address.startswith(('192.168.56.', '10.211.55.', '10.37.129.', '172.16.')):
        return 'looks like a virtual/hypervisor adapter: other machines usually cannot reach it'
    return None


def local_addresses():
    """Every IPv4 a peer could dial, route-preferred one first.

    Deliberately wider than the lobby list: on Windows a Hyper-V/VirtualBox
    adapter can win the route lookup, and the host then reads out an address no
    other machine can dial.
    """
    found = list(lan_module._local_addresses())
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            if address != '0.0.0.0' and address not in found:
                found.append(address)
    except OSError:
        pass
    rows = [dict(address=address, caveat=_address_caveat(address)) for address in found]
    usable = [r['address'] for r in rows if r['caveat'] is None]
    return dict(route_preferred=found[1] if len(found) > 1 else None,
                all=found, detail=rows, dialable=usable)


def port_status(port):
    """Can this machine bind the TCP port right now?"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(('', port))
        return dict(port=port, bindable=True)
    except OSError as exc:
        return dict(port=port, bindable=False, error=f'{exc.errno}: {exc}')
    finally:
        probe.close()


def raw_connect(address, port, timeout=5.0):
    """Reachability numbers for one address, independent of the session code.

    The nonblocking code is the one the game classifies; the blocking attempt
    with a timeout distinguishes 'nothing is listening' (refused) from
    'nothing answers at all' (timeout — a firewall dropping the SYN).
    """
    result = dict(address=address, port=port)
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setblocking(False)
        started = time.monotonic()
        code = probe.connect_ex((address, port))
        result['nonblocking_code'] = code
        result['nonblocking_verdict'] = classify_connect_result(code)
        result['nonblocking_seconds'] = round(time.monotonic() - started, 4)
        if code != 0 and result['nonblocking_verdict'] == 'pending':
            # Same wait the production poll loop performs before SO_ERROR.
            import select
            _, writable, exceptional = select.select([], [probe], [probe], timeout)
            result['pending_writable'] = bool(writable or exceptional)
            if writable or exceptional:
                so_error = probe.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                result['so_error_after_pending'] = so_error
                result['nonblocking_verdict'] = 'connected' if so_error == 0 else 'failed'
    except OSError as exc:
        result['nonblocking_error'] = str(exc)
    finally:
        probe.close()
    blocking = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        blocking.settimeout(timeout)
        started = time.monotonic()
        code = blocking.connect_ex((address, port))
        elapsed = round(time.monotonic() - started, 4)
        result['blocking_code'] = code
        result['blocking_seconds'] = elapsed
        if code == 0:
            result['outcome'] = 'connected'
        elif code in _IN_PROGRESS_FAMILY and elapsed >= timeout * 0.8:
            # connect_ex with a socket timeout reports EAGAIN/EWOULDBLOCK (POSIX)
            # or the Winsock in-progress code when the wait itself expired, so
            # the elapsed time is what identifies a dropped SYN.
            result['outcome'] = 'timeout'
            result['outcome_message'] = (
                f'no answer within {timeout:g}s — the SYN is being dropped (host firewall) '
                f'or {address} is not routable from here')
        else:
            result['outcome'] = 'refused' if code in (errno.ECONNREFUSED, 10061) else 'failed'
            result['outcome_message'] = connect_failure_message(code, address, port)
    except OSError as exc:
        result['blocking_error'] = str(exc)
        result['outcome'] = 'error'
        result['outcome_message'] = str(exc)
    finally:
        blocking.close()
    return result


def _base_report(mode, port=None):
    return dict(tool='netdiag', mode=mode, port=port, environment=environment(),
                addresses=local_addresses(), timeline=[])


def _pump(sessions, predicate, seconds, timeline=None, label=''):
    """Poll real sessions until the predicate holds or the deadline passes."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        for session in sessions:
            session.poll()
        if predicate():
            return True
        time.sleep(0.02)
    if timeline is not None and label:
        timeline.append(f'{label}: still waiting after {seconds:g}s')
    return predicate()


def loopback_pair(port=None):
    """Start a real host and a real client session on this machine.

    Proves this machine's own listen/accept/handshake path works. If this
    fails, no cross-machine pairing can succeed, so it is reported first.
    """
    if port is None:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
    host = client = None
    try:
        host = LanSession.host(port, default_lan_options(), name='netdiag-host')
        client = LanSession.join('127.0.0.1', port, name='netdiag-client')
        pair = _pump([host, client], lambda: client.snapshot['status'] == 'lobby', LOOPBACK_PAIR_WAIT)
        snapshot = client.snapshot
        return dict(port=port, paired=bool(pair), host_status=host.snapshot['status'],
                    client_status=snapshot['status'], client_error=snapshot['error'],
                    local_player=snapshot.get('local_player', client.local_player),
                    players=[p['name'] for p in snapshot.get('players', [])])
    except Exception as exc:                     # noqa: BLE001 - report, never crash
        return dict(port=port, paired=False, client_error=f'{type(exc).__name__}: {exc}')
    finally:
        for session in (client, host):
            if session is not None:
                session.close()


# -------------------------------------------------------------------- modes

def run_info(port=DEFAULT_PORT):
    report = _base_report('info', port)
    report['port_status'] = port_status(port)
    report['output_path'] = default_out('info')
    report['loopback_pair'] = loopback_pair()
    report['socket_probes'] = socket_probes()
    report['sim_fingerprint'] = sim_fingerprint()
    report['verdict'] = []
    pair = report['loopback_pair']
    if pair.get('paired'):
        report['verdict'].append(
            f'Local host+join pairing works on this machine (port {pair["port"]}, '
            f'{len(pair.get("players", []))} lobby entries).')
    else:
        report['verdict'].append(
            'Local host+join pairing FAILED on this machine — fix this before testing '
            f'across machines: {pair.get("client_error") or pair.get("client_status")}')
    if not report['port_status']['bindable']:
        report['verdict'].append(
            f'TCP {port} is not bindable here ({report["port_status"]["error"]}): another '
            'program holds it, or a policy blocks it.')
    if len(report['addresses']['dialable']) > 1:
        report['verdict'].append(
            'This machine has several dialable addresses; the other machine must dial the '
            'one on the shared network: ' + ', '.join(report['addresses']['dialable']))
    fingerprint = report['sim_fingerprint']
    if fingerprint['checksum'] is None:
        report['verdict'].append(
            f'Simulation fingerprint FAILED to run: {fingerprint["error"]}')
    else:
        report['verdict'].append(
            f'Simulation fingerprint {fingerprint["checksum"][:16]} over '
            f'{fingerprint["ticks"]} ticks — this value must be identical on both '
            'machines, or the match will desync after it connects.')
    observed = report['socket_probes']['black_hole'].get('nonblocking_code')
    if classify_connect_result(observed) == 'failed':
        report['verdict'].append(
            f'This platform reports connect_ex() = {observed} '
            f'({errno.errorcode.get(observed, "unrecognized")}) for a connection that cannot '
            'finish — a hard failure, so the in-progress code cannot be observed from here '
            '(no route off this machine?).')
    else:
        report['verdict'].append(
            f'This platform reports connect_ex() = {observed} for a connection that cannot '
            f'finish ({classify_connect_result(observed)}); the join path accepts both the '
            'POSIX and the Winsock in-progress codes.')
    report['ok'] = bool(pair.get('paired'))
    return report


def socket_probes():
    """The two connect outcomes that differ most between POSIX and Windows.

    Reported on every machine so the two netdiag files show each platform's own
    code instead of the table both are assumed to satisfy.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(('127.0.0.1', 0))
    closed_port = probe.getsockname()[1]
    probe.close()
    return dict(black_hole=raw_connect(BLACK_HOLE[0], BLACK_HOLE[1], timeout=1.0),
                refused=raw_connect('127.0.0.1', closed_port, timeout=1.0))


def sim_fingerprint(ticks=SIM_FINGERPRINT_TICKS):
    """Checksum of one fixed scene: do two platforms simulate the same game?

    Lockstep only survives if every peer computes identical state every tick, so
    the report carries the checksum of a real LAN scene (canonical map build,
    one AI opponent, no human orders). Two machines that print different values
    will desync as soon as the match starts, whatever the handshake says; a
    mixed-platform pair therefore compares this before playing.
    """
    from game.core.manager import GameManager
    from game.net.lan import build_lan_map, precise_checksum
    try:
        map_def = build_lan_map(DataStore.get(), default_lan_options())
        manager = GameManager.start_skirmish(map_def)
        for _ in range(int(ticks)):
            manager.step(1 / 30)
        return dict(ticks=manager.state.tick, checksum=precise_checksum(manager))
    except Exception as exc:                     # noqa: BLE001 - report, never crash
        return dict(ticks=0, checksum=None, error=f'{type(exc).__name__}: {exc}')


def run_listen(port=DEFAULT_PORT, wait=60.0):
    report = _base_report('listen', port)
    report['port_status'] = port_status(port)
    session = None
    try:
        session = LanSession.host(port, default_lan_options(), name='netdiag-host')
    except Exception as exc:                     # noqa: BLE001 - report, never crash
        report['bind_error'] = f'{type(exc).__name__}: {exc}'
        report['verdict'] = [
            f'Could not open TCP {port} on this machine: {exc}',
            'Nothing else can be probed until the port is free.',
        ]
        report['ok'] = False
        return report
    try:
        report['listening'] = dict(port=port, addresses=report['addresses'],
                                   dial_hint=report['addresses']['route_preferred'])
        hint = report['addresses']['route_preferred'] or "this machine's LAN address"
        report['timeline'].append(f'listening on TCP {port}; tell the other machine to dial {hint}')
        seen = {}
        deadline = time.monotonic() + max(0.0, wait)
        while time.monotonic() < deadline:
            session.poll()
            for index, peer in enumerate(session.peer_report()):
                key = (index, peer['address'])
                row = seen.setdefault(key, dict(address=peer['address'], tcp_arrived=True,
                                                handshake_completed=False, slot=None))
                if peer['slot'] is not None:
                    row['handshake_completed'] = True
                    row['slot'] = peer['slot']
            if session.snapshot['status'] in ('error', 'closed'):
                break
            if session.snapshot['status'] == 'lobby' and len(session.snapshot['players']) > 1:
                # One peer is enough to answer the question that was asked.
                report['timeline'].append('handshake completed with a peer')
                break
            time.sleep(0.05)
        report['connections'] = list(seen.values())
        report['session'] = session.snapshot
        report['peers'] = session.peer_report()
    finally:
        session.close()
    report['verdict'] = _listen_verdict(report)
    report['ok'] = any(row['handshake_completed'] for row in report.get('connections', []))
    return report


def _listen_verdict(report):
    rows = report.get('connections', [])
    reached = [r for r in rows if r['tcp_arrived']]
    completed = [r for r in rows if r['handshake_completed']]
    error = (report.get('session') or {}).get('error')
    if completed:
        return [f'OK: {len(completed)} peer(s) connected and completed the handshake '
                f'({", ".join(r["address"] or "?" for r in completed)}).',
                'Cross-machine TCP and the lobby handshake both work on this pairing.']
    if reached:
        return [f'TCP arrived from {len(reached)} peer(s) but the handshake was refused: {error}',
                'That is a version/content mismatch, not a firewall problem: both machines '
                'must run the same release (check game_version and content_hash in the '
                'two netdiag reports).']
    window = report.get('wait')
    return [f'No TCP connection reached port {report["port"]}'
            + (f' in the {window:g}s probe window.' if window else '.'),
            'Check, in order: (1) the other machine dialed this machine\'s LAN address '
            f'({report["addresses"]["route_preferred"] or "see addresses above"}), not a '
            'virtual/loopback one; (2) a Windows host allows the program inbound on the '
            'Private profile (Windows Security -> Firewall & network protection -> Allow an '
            'app through firewall; a dismissed first-run prompt leaves a BLOCK rule that also '
            'blocks outgoing traffic); (3) both machines are on the same subnet and no VPN is '
            'routing around it; (4) the other machine was actually started with --netdiag connect.']


def run_connect(address, port=DEFAULT_PORT, wait=None):
    if type(address) is not str or not address.strip():
        raise ValueError('--address requires the host IPv4 address')
    address = address.strip()
    try:
        socket.inet_pton(socket.AF_INET, address)
    except (OSError, TypeError):
        raise ValueError(f'--address must be a numeric IPv4 address, got {address!r}') from None
    report = _base_report('connect', port)
    report['address'] = address
    report['raw_connect'] = raw_connect(address, port)
    session = None
    try:
        session = LanSession.join(address, port, name='netdiag-client')
        lobby = _pump([session],
                      lambda: session.snapshot['status'] in ('lobby', 'running', 'error', 'closed'),
                      TIMEOUT + 5.0 if wait is None else wait,
                      timeline=report['timeline'], label='join')
        snapshot = session.snapshot
        report['handshake'] = dict(reached_lobby=snapshot['status'] in ('lobby', 'running'),
                                   local_player=snapshot.get('local_player'),
                                   sent=dict(version=GAME_VERSION, protocol=PROTOCOL_VERSION,
                                             content=_content_hash()),
                                   players=[p['name'] for p in snapshot.get('players', [])],
                                   error=snapshot['error'])
        report['session'] = snapshot
    finally:
        if session is not None:
            session.close()
    report['verdict'] = _connect_verdict(report)
    report['ok'] = bool(report.get('handshake', {}).get('reached_lobby'))
    return report


def _connect_verdict(report):
    address, port = report['address'], report['port']
    raw = report.get('raw_connect', {})
    session = report.get('session') or {}
    error = session.get('error') or report.get('handshake', {}).get('error') or ''
    if report.get('handshake', {}).get('reached_lobby'):
        return [f'OK: joined the lobby at {address}:{port} as slot '
                f'{report["handshake"].get("local_player")} '
                f'({", ".join(report["handshake"].get("players", []))}).',
                'TCP, the handshake and the version/content check all passed on this pairing.']
    verdicts = [f'Could not join {address}:{port}.']
    if 'mismatch' in error:
        verdicts.append(
            f'Handshake refused with "{error}": the two machines run different game '
            'versions or data. Compare game_version and content_hash in both netdiag '
            'reports and update the older install.')
    if 'Connection failed' in error:
        verdicts.append(error)
    if raw.get('outcome') == 'connected' or raw.get('nonblocking_verdict') == 'connected':
        verdicts.append(
            'TCP itself completes, so nothing is blocked at the network layer — the host '
            'game is not accepting/handshaking (host not in the lobby yet, or it rejected '
            'this version).')
    elif raw.get('outcome_message'):
        verdicts.append('Raw probe: ' + raw['outcome_message'])
    if raw.get('outcome') == 'timeout':
        verdicts.append(
            'A dropped SYN with no reply is the signature of a host-side firewall rule; on '
            'Windows check Windows Security -> Firewall & network protection -> Allow an app '
            'through firewall for the STAR ARMADA program on the Private profile.')
    if raw.get('nonblocking_code') not in (None, 0) and raw.get('blocking_code') == 0:
        verdicts.append(
            f'Note: nonblocking connect_ex returned {raw["nonblocking_code"]} '
            f'({classify_connect_result(raw["nonblocking_code"])}) while a blocking connect '
            'succeeded — that is the Windows Winsock in-progress code, accepted by '
            'classify_connect_result.')
    if error and 'mismatch' not in error and 'Connection failed' not in error:
        verdicts.append(f'Session error: {error}')
    verdicts.append('If the host is on Windows, allow its STAR ARMADA program inbound on the '
                    'Private firewall profile; a dismissed first-run prompt blocks it both ways.')
    return verdicts


# ------------------------------------------------------------------ reporting

def default_out(mode):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return os.path.join(user_dir(), 'netdiag', f'netdiag-{mode}-{stamp}.json')


def _dedupe(lines):
    """Order-preserving dedupe: the session error and the raw probe often agree."""
    seen = set()
    unique = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique


def _write_report(report, out):
    """Write the JSON report; return (ok, error). Preflights every failure mode.

    The report cannot carry its own 'written' flag (the flag would have to be
    set after the bytes are already on disk), so the exit status is the signal:
    0 written, 2 not written. A stale successful file therefore cannot be
    mistaken for this run's result.
    """
    try:
        if os.path.isdir(out):
            raise OSError(f'{out} is a directory, not a report file')
        parent = os.path.dirname(os.path.abspath(out))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(out, 'w') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
        size = os.path.getsize(out)
        if size <= 0:
            raise OSError(f'{out} is empty after writing')
        return True, None
    except OSError as exc:
        return False, str(exc)


def _notify(title, text):
    """Message box so a console-less frozen Windows build still reports itself."""
    if os.name != 'nt' or not (getattr(sys, 'frozen', False)
                               or os.environ.get('STAR_ARMADA_NETDIAG_MSGBOX') == '1'):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text[:2000], title, 0x40)
    except Exception:                            # noqa: BLE001 - cosmetic only
        pass


def _finish(report, out, msgbox=False):
    report['output_path'] = out
    report['verdict'] = _dedupe(report.get('verdict', []))
    ok, error = _write_report(report, out)
    _say()
    for line in report.get('verdict', []):
        _say('  ' + line)
    if report.get('connections') is not None:
        _say(f'  connections observed: {len(report["connections"])}')
    if ok:
        _say(f'  report: {out}')
    else:
        _say(f'  REPORT WRITE FAILED: {error}')
    summary = '\n'.join(report.get('verdict', [])[:4])
    if ok:
        summary += f'\n\nReport: {out}'
    else:
        summary += f'\n\nReport could not be written: {error}'
    if msgbox or (getattr(sys, 'frozen', False) and os.name == 'nt'):
        _notify('STAR ARMADA netdiag', summary)
    if not ok:
        return 2
    return 0 if report.get('ok', True) else 1


# ---------------------------------------------------------------------- cli

def _parse(argv):
    mode = 'info'
    if argv and not argv[0].startswith('-'):
        mode = argv[0]
        argv = argv[1:]
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode!r} (expected one of {", ".join(MODES)})')
    options = dict(mode=mode, address=None, port=DEFAULT_PORT, wait=None, out=None, msgbox=False)
    index = 0
    while index < len(argv):
        flag = argv[index]
        value = argv[index + 1] if index + 1 < len(argv) else None
        if flag in ('-h', '--help'):
            raise SystemExit(USAGE)
        if flag == '--msgbox':
            options['msgbox'] = True
            index += 1
            continue
        if value is None:
            raise ValueError(f'{flag} requires a value')
        if flag in ('-a', '--address'):
            options['address'] = value
        elif flag in ('-p', '--port'):
            try:
                options['port'] = int(value)
            except ValueError:
                raise ValueError(f'--port must be an integer, got {value!r}') from None
            if not 1 <= options['port'] <= 65535:
                raise ValueError('--port must be 1..65535')
        elif flag in ('-w', '--wait'):
            try:
                options['wait'] = float(value)
            except ValueError:
                raise ValueError(f'--wait must be a number of seconds, got {value!r}') from None
            if options['wait'] < 0:
                raise ValueError('--wait cannot be negative')
        elif flag == '--out':
            options['out'] = value
        else:
            raise ValueError(f'unknown option {flag!r}')
        index += 2
    if options['mode'] == 'connect' and not options['address']:
        raise ValueError('connect needs --address <host IPv4>')
    return options


def cli(argv):
    """Entry point for ``main.py --netdiag``; returns the process exit status."""
    try:
        options = _parse(list(argv))
    except SystemExit as exc:
        _say(str(exc))
        return 0
    except ValueError as exc:
        _say(f'netdiag: {exc}')
        _say(USAGE)
        return 2
    try:
        if options['mode'] == 'info':
            report = run_info(options['port'])
        elif options['mode'] == 'listen':
            report = run_listen(options['port'],
                                wait=60.0 if options['wait'] is None else options['wait'])
            report['wait'] = 60.0 if options['wait'] is None else options['wait']
        else:
            report = run_connect(options['address'], options['port'], wait=options['wait'])
    except ValueError as exc:
        _say(f'netdiag: {exc}')
        return 2
    _say(f'== STAR ARMADA netdiag / {options["mode"]} ==')
    _say(f'platform {report["environment"]["platform"]} · {report["environment"]["os_release"]}')
    _say(f'game {report["environment"]["game_version"]} · protocol '
         f'{report["environment"]["protocol_version"]} · content '
         f'{str(report["environment"]["content_hash"])[:16]}')
    for row in report['addresses']['detail']:
        _say(f'  local address {row["address"]}'
             + (f'  <-- {row["caveat"]}' if row['caveat'] else ''))
    for line in report['timeline']:
        _say('  ' + line)
    fingerprint = report.get('sim_fingerprint') or {}
    if fingerprint.get('checksum'):
        _say(f'  sim fingerprint {fingerprint["checksum"][:16]} over '
             f'{fingerprint["ticks"]} ticks')
    out = options['out'] or default_out(options['mode'])
    return _finish(report, out, msgbox=options['msgbox'])


if __name__ == '__main__':                       # pragma: no cover - manual entry
    raise SystemExit(cli(sys.argv[1:]))
