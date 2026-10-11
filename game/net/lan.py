"""Direct-IP LAN multiplayer, unencrypted: trusted local networks only.

host(port, options) / join(address, port) return sessions; poll is nonblocking.
Snapshot is a detached lobby dict. Configure resets readiness; start requires
all configured human slots connected and ready. Launch supplies canonical map.
Attach session to state._net_session; advance(gm, dt) performs at most one fixed
1/30-second tick, never accumulating network-wait time. AI stays local on every
peer. Fatal protocol/disconnect/desync/timeout errors stop the session.
Cold renderer/audio loading has a separate absolute 60-second budget; the
initial all-human checksum barrier restores normal 15-second stall detection.
"""
from copy import deepcopy
from game.core.skirmish import build_skirmish_map, PLAYER_COLORS

DEFAULT_PORT = 7777


def default_lan_options():
    return dict(map_id='skirmish01', human_count=2, ai_count=0,
                colors=list(PLAYER_COLORS)[:4], factions=['imperial'] * 4,
                ai_difficulty='normal', cooperative=False)


def build_lan_map(ds, options):
    if not isinstance(options, dict):
        raise ValueError('LAN options must be a dict')
    h, a = options.get('human_count'), options.get('ai_count')
    if type(h) is not int or not 2 <= h <= 4:
        raise ValueError('Human count must be 2..4')
    if type(a) is not int or not 0 <= a <= 2 or h + a > 4:
        raise ValueError('AI count must be 0..2; total slots <=4')
    if type(options.get('cooperative')) is not bool:
        raise ValueError('cooperative must be boolean')
    temporary = deepcopy(options)
    temporary['ai_count'] = h + a - 1
    result = build_skirmish_map(ds, temporary)
    for slot, p in enumerate(result['players']):
        p.update(is_ai=slot >= h, name=f'Player {slot + 1}' if slot < h else f'AI {slot - h + 1}',
                 team=(0 if slot < h else 1) if options['cooperative'] else slot)
    return result

import hashlib
from pathlib import Path
from dataclasses import asdict, fields, is_dataclass
import math
from game.core.commands import PlayerCommand
import errno
import json
import socket
import struct
import time
from game.data.store import DataStore
from game import __version__ as GAME_VERSION
from game.systems.campaign_script import CampaignScript

PROTOCOL_VERSION = 1
MAX_FRAME = 262144
MAX_BUFFER = MAX_FRAME * 2
IO_BUDGET = 65536
TIMEOUT = 15.0
LOADING_TIMEOUT = 60.0  # Bounded renderer/audio startup, until initial checksum barrier.


def _local_addresses():
    addresses = ['127.0.0.1']
    # UDP connect performs a local route lookup only: no packet is sent.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1', 1))
            address = probe.getsockname()[0]
            if address not in addresses and address != '0.0.0.0':
                addresses.append(address)
    except OSError:
        pass
    return addresses


def _port(port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Port must be an integer from 1 to 65535')
    return port


def _name(name):
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or any(ord(c) < 32 for c in name):
        raise ValueError('Name must be 1..64 printable characters')
    return name


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def content_hash(ds):
    """Canonical raw JSON plus loaded data; reject modded LAN sessions."""
    if ds.mod_files:
        raise ValueError('LAN does not support mods')
    raw = {p.relative_to(ds.assets_dir).as_posix(): json.loads(p.read_text())
           for p in sorted(Path(ds.assets_dir).rglob('*.json'))}
    loaded = {key: {k: asdict(v) for k, v in getattr(ds, key).items()}
              for key in ('weapons', 'ships', 'stations', 'abilities', 'techs', 'factions')}
    loaded.update(maps=ds.maps, rules=ds.rules, campaign=ds.campaign)
    return hashlib.sha256(_json(dict(raw=raw, loaded=loaded))).hexdigest()


MAX_COMMANDS = 64
MAX_UNITS = 256
FIXED_DT = 1 / 30
INPUT_DELAY = 3  # 100 ms: pipeline network round trips, never wait on the frame thread.
COMMAND_TYPES = {'move', 'attack', 'attack_move', 'stop', 'hold', 'build_station',
                 'build_satellite', 'build_planet_building', 'build_ship', 'colonize', 'research', 'ability', 'fleet_create',
                 'fleet_stance', 'jump', 'trade_route', 'repair', 'explore'}


def _canonical(value):
    if isinstance(value, CampaignScript):
        return _canonical(dict(triggers=value.triggers, progress=value.progress))
    if is_dataclass(value):
        return {f.name: _canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted((_canonical(v) for v in value), key=lambda v: _json(v))
    if value is None or type(value) in (int, float, str, bool):
        return value
    raise TypeError(f'Unserializable simulation value: {type(value)}')


def precise_checksum(manager):
    """Full-precision state and future-affecting AI/system state, no caches.

    Include all entity dataclass fields (even fields omitted by save files),
    queues, seed/tick (rng is derived from these), and persistent system timers.
    Cross-platform float divergence is a fatal desync, never rounded away.
    """
    st = manager.state
    omitted = {'grid', 'events', 'dmg_system', 'effects', 'floating_texts'}
    state = {f.name: _canonical(getattr(st, f.name)) for f in fields(st)
             if not f.name.startswith('_') and f.name not in omitted}
    brains = {pid: {k: _canonical(v) for k, v in vars(ai).items()
                    if k not in ('state', 'ds')}
              for pid, ai in manager.ai.ais.items()}
    systems = {name: {k: _canonical(v) for k, v in vars(getattr(manager, name)).items()
                      if k not in ('state', 'ds')}
               for name in ('trading', 'squadrons', 'victory', 'mission')}
    return hashlib.sha256(_json(_canonical(dict(state=state, ai=brains, systems=systems,
                                               capacity_timer=manager._capacity_timer)))).hexdigest()


def _commands(commands, owner):
    if not isinstance(commands, list) or len(commands) > MAX_COMMANDS:
        raise ValueError('Command count limit')
    valid = {f.name for f in fields(PlayerCommand)}
    for d in commands:
        if not isinstance(d, dict) or set(d) - valid:
            raise ValueError('Invalid command fields')
        if type(d.get('player')) is not int or d['player'] != owner:
            raise ValueError('Command slot ownership violation')
        if d.get('type') not in COMMAND_TYPES:
            raise ValueError('Invalid command type')
        required = {'move': ('target_pos',), 'attack_move': ('target_pos',),
                    'jump': ('target_pos',), 'attack': ('target_id',),
                    'repair': ('target_id',),
                    'build_station': ('station_kind', 'target_pos'),
                    'build_satellite': ('station_kind', 'target_id'),
                    'build_planet_building': ('station_kind', 'target_id'),
                    'build_ship': ('ship_id',), 'colonize': ('target_id',),
                    'research': ('tech_id',), 'ability': ('ability_id',)}
        if any(d.get(key) is None for key in required.get(d['type'], ())):
            raise ValueError('Missing required command fields')
        if d['type'] == 'build_ship' and 'name' in d:
            count = d['name']
            if not isinstance(count, str) or not count.isascii() or not count.isdigit() or len(count) > 2 or not 1 <= int(count) <= 99:
                raise ValueError('Ship build count limit')
        units = d.get('unit_ids', [])
        if not isinstance(units, list) or len(units) > MAX_UNITS or any(type(i) is not int or not 0 < i <= 2147483647 for i in units):
            raise ValueError('Invalid unit ids')
        pos = d.get('target_pos')
        if pos is not None and (not isinstance(pos, list) or len(pos) != 3 or
                                any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e9 for x in pos)):
            raise ValueError('Invalid target coordinates')
        for key, value in d.items():
            if key == 'target_id':
                if type(value) is not int or not 0 < value <= 2147483647:
                    raise ValueError('Invalid target id')
            elif key not in ('player', 'unit_ids', 'target_pos'):
                if not isinstance(value, str) or len(value) > 128:
                    raise ValueError('Invalid command string')
    return commands


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _players(players, options, local):
    if not isinstance(players, list) or not 2 <= len(players) <= options['human_count'] or local >= len(players):
        raise ValueError('Invalid lobby player count')
    for i, p in enumerate(players):
        if (not isinstance(p, dict) or type(p.get('slot')) is not int or p['slot'] != i
                or type(p.get('ready')) is not bool):
            raise ValueError('Invalid lobby slot')
        _name(p.get('name'))
    return players


class _Peer:
    def __init__(self, sock):
        self.sock = sock
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.rx = bytearray()
        self.tx = bytearray()
        self.slot = None
        self.next_tick = 0
        self.last = time.monotonic()
        self.connected = True

    def send(self, message):
        data = _json(message)
        if len(data) > MAX_FRAME or len(self.tx) + len(data) + 4 > MAX_BUFFER:
            raise ValueError('Outbound buffer limit')
        self.tx.extend(struct.pack('!I', len(data)) + data)

    def flush(self):
        if self.tx:
            try:
                n = self.sock.send(self.tx[:IO_BUDGET])
                if n == 0:
                    raise ConnectionError('Disconnected')
                del self.tx[:n]
            except BlockingIOError:
                pass

    def poll(self):
        self.flush()
        try:
            data = self.sock.recv(IO_BUDGET)
            if not data:
                raise ConnectionError('Disconnected')
            self.last = time.monotonic()
            self.rx.extend(data)
        except BlockingIOError:
            pass
        messages = []
        if len(self.rx) > MAX_BUFFER:
            raise ValueError('Inbound buffer limit')
        while len(self.rx) >= 4 and len(messages) < 32:
            size = struct.unpack('!I', self.rx[:4])[0]
            if not 1 <= size <= MAX_FRAME:
                raise ValueError('Invalid frame length')
            if len(self.rx) < 4 + size:
                break
            data = bytes(self.rx[4:4 + size])
            del self.rx[:4 + size]
            message = json.loads(data, object_pairs_hook=_unique_object, parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
            if not isinstance(message, dict):
                raise ValueError('Expected JSON object')
            messages.append(message)
        return messages

    def close(self):
        self.sock.close()


class LanSession:
    intercepts_commands = True

    def __init__(self, port, name, is_host):
        self.port = _port(port)
        self.name = _name(name)
        self.is_host = is_host
        self.local_player = 0 if is_host else -1
        self._listener = None
        self._peers = []
        self._players = []
        self._options = {}
        self._revision = 0
        self._status = 'lobby' if is_host else 'connecting'
        self._error = ''
        self._launch = None
        self._tick = 0
        self._pending = []
        self._sealed = None
        self._inputs = {}
        # Empty startup turns are safe only after turn zero verifies initial state.
        self._frames = {tick: dict(commands=[], checksum=None) for tick in range(1, INPUT_DELAY)}
        self._checksums = {}
        self._progress = time.monotonic()
        self._loading_started = None
        self._heartbeat = time.monotonic()
        self._ds = DataStore.get()
        self._content = content_hash(self._ds)
        self._addresses = _local_addresses()

    @classmethod
    def host(cls, port, options, name='Host'):
        self = cls(port, name, True)
        build_lan_map(self._ds, options)
        self._options = deepcopy(options)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('', port))
            listener.listen(8)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self._listener = listener
        self._players = [dict(slot=0, name=name, ready=False)]
        return self

    @classmethod
    def join(cls, address, port, name='Player'):
        self = cls(port, name, False)
        # Numeric direct-IP only: do not run blocking DNS on the frame thread.
        try:
            socket.inet_pton(socket.AF_INET, address)
        except (OSError, TypeError):
            raise ValueError('Enter a numeric IPv4 address') from None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer = _Peer(sock)
        result = sock.connect_ex((address, port))
        if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
            sock.close()
            self._fail('Connection failed')
            return self
        peer.connected = result == 0
        self._peers = [peer]
        peer.send(dict(type='hello', name=name, version=GAME_VERSION,
                       protocol=PROTOCOL_VERSION, content=self._content))
        return self

    @property
    def snapshot(self):
        return deepcopy(dict(status=self._status, error=self._error, players=self._players,
                             options=self._options, revision=self._revision, port=self.port, addresses=self._addresses,
                             is_host=self.is_host, can_start=self.is_host and self._status == 'lobby'
                             and len(self._players) == self._options.get('human_count')
                             and all(p['ready'] for p in self._players)))

    @property
    def launch(self):
        return deepcopy(self._launch)

    def _broadcast(self, message):
        for peer in self._peers:
            if peer.slot is not None:
                peer.send(message)

    def _lobby(self):
        self._broadcast(dict(type='lobby', players=self._players, options=self._options, revision=self._revision))

    def configure(self, options):
        if not self.is_host or self._status != 'lobby':
            raise ValueError('Only lobby host may configure')
        build_lan_map(self._ds, options)
        if options['human_count'] < len(self._players):
            raise ValueError('Cannot remove connected humans')
        self._options = deepcopy(options)
        self._revision += 1
        for p in self._players:
            p['ready'] = False
        self._lobby()

    def set_ready(self, ready):
        if type(ready) is not bool or self._status != 'lobby':
            raise ValueError('Readiness requires a lobby and boolean')
        if self.is_host:
            self._players[0]['ready'] = ready
            self._lobby()
        else:
            self._peers[0].send(dict(type='ready', ready=ready, revision=self._revision))

    def start(self):
        if not self.snapshot['can_start']:
            raise ValueError('All configured humans must connect and be ready')
        map_def = build_lan_map(self._ds, self._options)
        for p in self._players:
            map_def['players'][p['slot']]['name'] = p['name']
        map_def = json.loads(_json(map_def))
        self._launch = dict(map_def=map_def, local_player=0)
        self._status = 'running'
        self._progress = time.monotonic()
        self._loading_started = self._progress
        self._broadcast(dict(type='start', map_def=map_def))
        # Do not leave launch queued while the frame thread builds renderer/audio.
        # One bounded nonblocking write; subsequent polls handle short writes.
        try:
            for peer in self._peers:
                if peer.slot is not None:
                    peer.flush()
        except (OSError, ValueError) as exc:
            self._fail(str(exc))

    def _receive(self, peer, m):
        kind = m.get('type')
        if kind == 'ping' and ((self.is_host and peer.slot is not None) or (not self.is_host and self.local_player >= 0)):
            return
        if self._status == 'running' and kind in ('input', 'frame'):
            self._receive_tick(peer, m)
            return
        if self.is_host:
            if peer.slot is None:
                if kind != 'hello' or self._status != 'lobby' or len(self._players) >= self._options['human_count']:
                    raise ValueError('Lobby full or invalid handshake')
                for field, expected in (('version', GAME_VERSION), ('protocol', PROTOCOL_VERSION),
                                        ('content', self._content)):
                    if type(m.get(field)) is not type(expected) or m[field] != expected:
                        raise ValueError(f'{field} mismatch')
                name = _name(m.get('name'))
                peer.slot = len(self._players)
                self._players.append(dict(slot=peer.slot, name=name, ready=False))
                peer.send(dict(type='welcome', slot=peer.slot, version=GAME_VERSION,
                               protocol=PROTOCOL_VERSION, content=self._content))
                self._lobby()
            elif kind == 'ready' and self._status == 'lobby' and type(m.get('ready')) is bool:
                if type(m.get('revision')) is not int or m['revision'] != self._revision:
                    return  # Old consent must never apply to a changed configuration.
                self._players[peer.slot]['ready'] = m['ready']
                self._lobby()
            else:
                raise ValueError('Unexpected message')
        else:
            if kind == 'welcome' and self.local_player == -1:
                for field, expected in (('version', GAME_VERSION), ('protocol', PROTOCOL_VERSION),
                                        ('content', self._content)):
                    if m.get(field) != expected:
                        raise ValueError(f'{field} mismatch')
                if type(m.get('slot')) is not int or not 1 <= m['slot'] <= 3:
                    raise ValueError('Invalid slot')
                self.local_player = m['slot']
                self._status = 'lobby'
            elif kind == 'lobby' and self._status == 'lobby':
                if type(m.get('revision')) is not int or m['revision'] < self._revision:
                    raise ValueError('Invalid configuration revision')
                self._revision = m['revision']
                self._options = m['options']
                build_lan_map(self._ds, self._options)
                self._players = _players(m['players'], self._options, self.local_player)
            elif kind == 'start' and self._status == 'lobby':
                expected = build_lan_map(self._ds, self._options)
                if len(self._players) != self._options['human_count'] or not all(p['ready'] for p in self._players):
                    raise ValueError('Start requires all humans ready')
                for p in self._players:
                    expected['players'][p['slot']]['name'] = p['name']
                if _json(expected) != _json(m['map_def']):
                    raise ValueError('Start map mismatch')
                self._launch = dict(map_def=m['map_def'], local_player=self.local_player)
                self._progress = time.monotonic()
                self._loading_started = self._progress
                self._status = 'running'
            else:
                raise ValueError('Unexpected message')

    def submit(self, cmd, current_tick):
        if self._status != 'running' or type(current_tick) is not int or current_tick != self._tick:
            raise ValueError('Command requires current running tick')
        data = cmd.to_dict()
        _commands([data], self.local_player)
        if len(self._pending) >= MAX_COMMANDS:
            raise ValueError('Command count limit')
        self._pending.append(data)

    def _receive_tick(self, peer, m):
        tick = m.get('tick')
        if type(tick) is not int or not self._tick <= tick <= self._tick + 2 * INPUT_DELAY:
            raise ValueError('Invalid tick window')
        if not _digest(m.get('checksum')):
            raise ValueError('Invalid checksum')
        if self.is_host:
            if peer.slot is None or m['type'] != 'input':
                raise ValueError('Invalid input sender')
            if tick != peer.next_tick:
                raise ValueError('Invalid input sequence')
            commands = _commands(m.get('commands'), peer.slot)
            peer.next_tick = INPUT_DELAY if tick == 0 else tick + 1
            inputs = self._inputs.setdefault(tick, {})
            if peer.slot in inputs:
                raise ValueError('Duplicate tick input')
            inputs[peer.slot] = dict(checksum=m['checksum'], commands=commands)
            self._coordinate(tick)
        else:
            if m['type'] != 'frame' or tick != peer.next_tick or tick in self._frames:
                raise ValueError('Invalid frame sequence')
            commands = m.get('commands')
            if not isinstance(commands, list) or len(commands) > MAX_COMMANDS * self._options['human_count']:
                raise ValueError('Frame command count limit')
            last = -1
            counts = {}
            for d in commands:
                owner = d.get('player') if isinstance(d, dict) else None
                if type(owner) is not int or not 0 <= owner < self._options['human_count'] or owner < last:
                    raise ValueError('Frame slot ownership/order violation')
                _commands([d], owner)
                last = owner
                counts[owner] = counts.get(owner, 0) + 1
                if counts[owner] > MAX_COMMANDS:
                    raise ValueError('Command count limit')
            self._frames[tick] = m
            peer.next_tick = INPUT_DELAY if tick == 0 else tick + 1

    def _coordinate(self, tick):
        inputs = self._inputs.get(tick, {})
        if len(inputs) != self._options['human_count'] or tick in self._frames:
            return
        hashes = {i['checksum'] for i in inputs.values()}
        if len(hashes) != 1:
            raise ValueError(f'Desync at tick {tick - INPUT_DELAY if tick else 0}')
        frame = dict(type='frame', tick=tick, checksum=next(iter(hashes)),
                     commands=[d for slot in sorted(inputs) for d in inputs[slot]['commands']])
        self._frames[tick] = frame
        self._broadcast(frame)

    def advance(self, gm, dt):
        """One nonblocking fixed step; input/checksum frames pipeline three turns ahead.

        Frame t carries commands for t and the precise state hash at t-delay.
        Initial state is checked before tick zero; subsequent divergence is fatal
        within the bounded pipeline. No receive waits or extra simulation steps.
        The caller paces attempts at 30 Hz; dt never becomes network catch-up debt.
        """
        self.poll()
        if self._status != 'running':
            return False
        try:
            if gm.state.tick != self._tick:
                raise ValueError('Simulation tick mismatch')
            if self._sealed is None:
                self._sealed = precise_checksum(gm)
                target = self._tick + INPUT_DELAY
                self._checksums[target] = self._sealed
                messages = [dict(type='input', tick=target, checksum=self._sealed,
                                 commands=self._pending)]
                self._pending = []
                if self._tick == 0:
                    # Initial state is verified before any simulation executes.
                    self._checksums[0] = self._sealed
                    messages.insert(0, dict(type='input', tick=0, checksum=self._sealed, commands=[]))
                for message in messages:
                    if self.is_host:
                        self._inputs.setdefault(message['tick'], {})[0] = message
                        self._coordinate(message['tick'])
                    else:
                        self._peers[0].send(message)
                self.poll()  # Flush freshly sealed inputs without a render-frame delay.
                if self._status != 'running':
                    return False
            frame = self._frames.get(self._tick)
            if frame is None:
                return False
            if frame['checksum'] is not None and frame['checksum'] != self._checksums.get(self._tick):
                raise ValueError(f'Desync at tick {self._tick}')
            gm.state.command_queue.extend(PlayerCommand.from_dict(d) for d in frame['commands'])
            gm.step(FIXED_DT)
            del self._frames[self._tick]
            self._inputs.pop(self._tick, None)
            self._checksums.pop(self._tick, None)
            self._tick = gm.state.tick
            self._sealed = None
            self._progress = time.monotonic()
            self._loading_started = None  # Tick zero proved every human graph loaded.
            self.poll()  # Flush released frame even if caller stops after this tick.
            return True
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self._fail(str(exc))
            return False

    def poll(self):
        if self._status in ('closed', 'error'):
            return
        try:
            if time.monotonic() - self._heartbeat > TIMEOUT / 3:
                for peer in self._peers:
                    if peer.connected and ((self.is_host and peer.slot is not None) or (not self.is_host and self.local_player >= 0)):
                        peer.send(dict(type='ping'))
                self._heartbeat = time.monotonic()
            if self._status == 'running':
                if self._loading_started is not None:
                    if time.monotonic() - self._loading_started > LOADING_TIMEOUT:
                        raise ConnectionError('Loading timeout')
                elif time.monotonic() - self._progress > TIMEOUT:
                    raise ConnectionError('Lockstep timeout')
            if self._listener:
                for _ in range(8):
                    try:
                        sock, _ = self._listener.accept()
                    except BlockingIOError:
                        break
                    if len(self._peers) >= 4:
                        sock.close()
                        continue
                    self._peers.append(_Peer(sock))
            for peer in list(self._peers):
                try:
                    if not peer.connected:
                        if time.monotonic() - peer.last > TIMEOUT:
                            raise ConnectionError('Peer timeout')
                        import select
                        _, writable, exceptional = select.select([], [peer.sock], [peer.sock], 0)
                        if not writable and not exceptional:
                            continue
                        if peer.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                            raise ConnectionError('Connection failed')
                        peer.connected = True
                    for message in peer.poll():
                        self._receive(peer, message)
                    # Read buffered launch first: this poll may follow a cold
                    # graph build longer than the old lobby receive timeout.
                    # Loading uses an absolute deadline, never poll/heartbeat progress.
                    loading_peer = self._loading_started is not None and (not self.is_host or peer.slot is not None)
                    if not loading_peer and time.monotonic() - peer.last > TIMEOUT:
                        raise ConnectionError('Peer timeout')
                    peer.flush()
                except (OSError, ValueError, KeyError, TypeError, IndexError, RecursionError, OverflowError):
                    if not self.is_host or peer.slot is not None:
                        raise
                    # A TCP port probe is not a participant in the match.
                    peer.close()
                    self._peers.remove(peer)
        except (OSError, ValueError, KeyError, TypeError, IndexError, RecursionError, OverflowError) as exc:
            self._fail(str(exc))

    def _fail(self, error):
        self.close()
        self._status = 'error'
        self._error = str(error)

    def close(self):
        if self._listener:
            self._listener.close()
            self._listener = None
        for p in self._peers:
            p.close()
        self._peers = []
        self._status = 'closed'
