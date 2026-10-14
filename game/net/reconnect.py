"""Snapshot/transfer foundations used by the opt-in live production backend.

Only trusted same-content/same-version LAN skirmishes. No pickle, arbitrary
imports, float rounding, simulation wallclock, or changes to the normal tick path.
`live_recovery.py` owns distributed freeze/drain, target-tick input reconciliation,
private admission, all-peer install ACK and absolute grace. RecoveryBarrier and
PendingInputs below remain standalone quiet-barrier policy primitives.
"""
from dataclasses import fields, is_dataclass
from typing import Any, get_type_hints, get_origin, get_args
import math
import types
import hashlib
import json

from game import __version__ as GAME_VERSION
from game.core.commands import PlayerCommand
from game.core.entity import Entity, SubsystemState
from game.core.manager import GameManager
from game.core.state import GameState, PlayerState, MapInfo
from game.core.vectors import Vec3
from game.core.world import Fleet, Projectile
from game.ai.ai import AIPlayer
from game.data.store import DataStore
from game.net.lan import (_json, _unique_object, content_hash, precise_checksum,
                          PROTOCOL_VERSION, INPUT_DELAY)

FORMAT = 'star-armada-lan-snapshot-1'
MAX_SNAPSHOT = 8 * 1024 * 1024
STATE_OMITTED = {'grid', 'events', 'dmg_system', 'effects', 'floating_texts'}
SYSTEMS = ('trading', 'squadrons', 'victory', 'mission')
TYPES: dict[str, type] = {c.__name__: c for c in (PlayerCommand, Entity, SubsystemState,
                               PlayerState, MapInfo, Vec3, Fleet, Projectile)}


def _encode(value):
    if is_dataclass(value):
        if type(value).__name__ not in TYPES or TYPES[type(value).__name__] is not type(value):
            raise ValueError('Unsupported snapshot dataclass')
        return ['object', type(value).__name__, {f.name: _encode(getattr(value, f.name))
                                                for f in fields(value)}]
    if isinstance(value, dict):
        # Explicit pairs preserve integer/tuple keys and insertion order.
        return ['dict', [[_encode(k), _encode(v)] for k, v in value.items()]]
    if type(value) in (tuple, list, set):
        values = [_encode(v) for v in value]
        if isinstance(value, set):
            values.sort(key=_json)
        return [type(value).__name__, values]
    if value is None or type(value) in (int, float, bool, str):
        return ['scalar', value]
    raise ValueError('Unsupported snapshot value')


# Encoding wrappers multiply wire nesting; 64 logical levels are ample for the
# shallow simulation graph. Count includes keys, scalars and containers across
# all three roots, bounding tiny-node amplification independently of byte size.
MAX_DECODE_DEPTH = 64
MAX_DECODE_NODES = 250000


def _decode(value, *, _depth=0, _budget=None) -> Any:
    budget = [MAX_DECODE_NODES] if _budget is None else _budget
    budget[0] -= 1
    if _depth > MAX_DECODE_DEPTH or budget[0] < 0:
        raise ValueError('Snapshot decode limit')
    def child(node):
        return _decode(node, _depth=_depth+1, _budget=budget)
    if type(value) is not list or not value or type(value[0]) is not str:
        raise ValueError('Invalid snapshot value')
    tag = value[0]
    if tag == 'scalar' and len(value) == 2:
        result = value[1]
        if result is None or type(result) in (int, bool, str):
            return result
        if type(result) is float and math.isfinite(result):
            return result
    elif (tag == 'object' and len(value) == 3
          and type(value[1]) is str and value[1] in TYPES):
        cls = TYPES[value[1]]
        if type(value[2]) is not dict or set(value[2]) != {f.name for f in fields(cls)}:
            raise ValueError('Snapshot field schema mismatch')
        obj = cls(**{k: child(v) for k, v in value[2].items()})
        _validate_type(obj, cls)
        return obj
    elif len(value) == 2 and type(value[1]) is list:
        if tag == 'dict':
            result = {}
            for pair in value[1]:
                if type(pair) is not list or len(pair) != 2:
                    raise ValueError('Invalid snapshot pair')
                k, v = map(child, pair)
                try:
                    if k in result:
                        raise ValueError('Duplicate snapshot key')
                    result[k] = v
                except TypeError as exc:
                    raise ValueError('Invalid snapshot key') from exc
            return result
        if tag in ('tuple', 'list', 'set'):
            try:
                return {'tuple': tuple, 'list': list, 'set': set}[tag](child(v) for v in value[1])
            except TypeError as exc:
                raise ValueError('Invalid snapshot collection') from exc
    raise ValueError('Invalid snapshot type')


# Bare container annotations in core models need runtime element types here.
_CONTAINER_TYPES = {
    Entity: {'systems': dict[str, SubsystemState], 'shields': dict[str, float],
             'weapon_cooldowns': dict[int, float], 'ability_cooldowns': dict[str, float],
             'ability_active': dict[str, float], 'build_queue': list[dict]},
    PlayerState: {'researched': set[str], 'researching': dict[str, dict],
                  'income_frame': dict[str, float], 'color': tuple[float, float, float]},
    # FormationSystem writes a list; legacy Fleet.from_dict writes a tuple.
    Fleet: {'member_ids': set[int],
            'rally_point': tuple[float, float, float] | list[float] | None},
    Projectile: {'color': tuple[float, float, float]},
    MapInfo: {'nebulas': list[dict], 'jump_points': list[dict]},
    GameState: {'entities': dict[int, Entity], 'projectiles': dict[int, Projectile],
                'players': dict[int, PlayerState], 'fleets': dict[int, Fleet],
                'command_queue': list[PlayerCommand], 'dead_ids': list[int],
                'damage_queue': list[dict], 'explored_cells': dict[int, set[tuple[int, int]]],
                'discovered_planets': dict[int, dict[int, Entity]]},
}


def _validate_type(value, expected):
    """Exact runtime types, numeric floats may also be finite non-bool ints.

    Untyped payload dictionaries remain host-owned semantics, not save-file
    authorization. Dataclasses and their typed children never accept dict twins.
    """
    origin, args = get_origin(expected), get_args(expected)
    if origin is types.UnionType:
        for option in args:
            try:
                _validate_type(value, option)
                return
            except ValueError:
                pass
        raise ValueError('Snapshot runtime schema mismatch')
    base = origin or expected
    if base is float:
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError('Snapshot numeric schema mismatch')
        return
    if type(value) is not base:
        raise ValueError('Snapshot runtime schema mismatch')
    if is_dataclass(base):
        for name, hint in get_type_hints(base).items():
            _validate_type(getattr(value, name), _CONTAINER_TYPES.get(base, {}).get(name, hint))
        if base is Entity and value.crew_damage_accumulator < 0:
            raise ValueError('Snapshot crew_damage_accumulator schema mismatch')
        if base is Fleet and value.rally_point is not None and len(value.rally_point) != 3:
            raise ValueError('Snapshot rally coordinate schema mismatch')
    elif args and base is dict:
        for key, item in value.items():
            _validate_type(key, args[0])
            _validate_type(item, args[1])
    elif args and base in (list, set, tuple):
        if base is tuple and len(args) > 1 and args[-1] is not Ellipsis:
            if len(value) != len(args):
                raise ValueError('Snapshot tuple schema mismatch')
            for item, hint in zip(value, args):
                _validate_type(item, hint)
        else:
            for item in value:
                _validate_type(item, args[0])


def _validate_attributes(attributes, template):
    if type(attributes) is not dict or set(attributes) != set(template):
        raise ValueError('Snapshot attributes schema mismatch')
    for key, default in template.items():
        value = attributes[key]
        if type(default) is dict:
            _validate_type(value, dict)
            # Fixed dictionaries (cfg/script/progress) retain their required keys.
            _validate_attributes(value, default)
        else:
            _validate_type(value, type(default))


def _validate_graph(state, systems, brains, manager):
    if type(state) is not dict or set(state) != _state_names():
        raise ValueError('Snapshot state schema mismatch')
    hints = get_type_hints(GameState, localns={'MissionSystem': object, 'SensorQueries': object})
    for name, value in state.items():
        _validate_type(value, _CONTAINER_TYPES[GameState].get(name, hints[name]))
    for name in ('entities', 'projectiles', 'players', 'fleets'):
        if any(key != value.id for key, value in state[name].items()):
            raise ValueError('Snapshot identity schema mismatch')
    if type(systems) is not dict or set(systems) != set(SYSTEMS):
        raise ValueError('Snapshot systems schema mismatch')
    for name in SYSTEMS:
        _validate_attributes(systems[name], _attributes(getattr(manager, name)))
    if type(brains) is not dict:
        raise ValueError('Snapshot AI schema mismatch')
    expected = {pid for pid, player in state['players'].items() if player.is_ai}
    # Before the first tick AIManager has intentionally not constructed brains.
    if set(brains) != (expected if state['tick'] > 0 else set()):
        raise ValueError('Snapshot AI ownership schema mismatch')
    for pid, attributes in brains.items():
        _validate_type(pid, int)
        if type(attributes) is not dict or set(attributes) != set(_attributes(AIPlayer(manager.state, pid))):
            raise ValueError('Snapshot AI schema mismatch')
        for name, hint in {'player_id': int, 'decision_timer': float, 'tactical_timer': float,
                           'last_strategic': dict, '_pending_site': dict[int, tuple[str, Vec3]]}.items():
            _validate_type(attributes[name], hint)
        if 'attack_fleet_id' not in attributes['last_strategic']:
            raise ValueError('Snapshot AI strategy schema mismatch')
        _validate_type(attributes['last_strategic']['attack_fleet_id'], int | None)
        if attributes['player_id'] != pid:
            raise ValueError('Snapshot AI player schema mismatch')


def _attributes(obj):
    from game.systems.campaign_script import CampaignScript
    return {k: (dict(triggers=v.triggers, progress=v.progress)
                if isinstance(v, CampaignScript) else v)
            for k, v in vars(obj).items() if k not in ('state', 'ds')}


def _state_names():
    return {f.name for f in fields(GameState)
            if not f.name.startswith('_') and f.name not in STATE_OMITTED}


def capture_snapshot(manager):
    """Detached full fidelity skirmish snapshot at a caller-proven quiet barrier."""
    if manager.mission.mission is not None:
        raise ValueError('LAN reconnect snapshots are skirmish-only')
    body = dict(state=_encode({k: getattr(manager.state, k) for k in _state_names()}),
                ai=_encode({pid: _attributes(ai) for pid, ai in manager.ai.ais.items()}),
                systems=_encode({name: _attributes(getattr(manager, name)) for name in SYSTEMS}),
                capacity_timer=manager._capacity_timer)
    envelope = dict(format=FORMAT, version=GAME_VERSION, protocol=PROTOCOL_VERSION,
                    content=content_hash(manager.ds), tick=manager.state.tick,
                    checksum=precise_checksum(manager), body=body)
    data = _json(envelope)
    if len(data) > MAX_SNAPSHOT:
        raise ValueError('Snapshot size limit')
    return data


def restore_snapshot(data):
    """Build a NEW fully bound manager; caller must rebind UI/network references."""
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_SNAPSHOT:
        raise ValueError('Snapshot size limit')
    try:
        envelope = json.loads(data, object_pairs_hook=_unique_object,
                              parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Nonfinite snapshot')))
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('Snapshot JSON decode limit or encoding') from exc
    from game.net.lan import _digest
    if (type(envelope) is not dict
            or set(envelope) != {'format', 'version', 'protocol', 'content', 'tick', 'checksum', 'body'}
            or type(envelope['tick']) is not int or envelope['tick'] < 0
            or not _digest(envelope['checksum'])):
        raise ValueError('Snapshot envelope schema mismatch')
    for key, expected in (('format', FORMAT), ('version', GAME_VERSION),
                          ('protocol', PROTOCOL_VERSION), ('content', content_hash(DataStore.get()))):
        if type(envelope.get(key)) is not type(expected) or envelope[key] != expected:
            raise ValueError(f'Snapshot {key} mismatch')
    body = envelope['body']
    if (type(body) is not dict or set(body) != {'state', 'systems', 'ai', 'capacity_timer'}):
        raise ValueError('Snapshot body schema mismatch')
    _validate_type(body['capacity_timer'], float)
    budget = [MAX_DECODE_NODES]
    state = _decode(body['state'], _budget=budget)
    systems = _decode(body['systems'], _budget=budget)
    brains = _decode(body['ai'], _budget=budget)
    # Validate the complete detached graph before installing a single field.
    manager = GameManager()
    _validate_graph(state, systems, brains, manager)
    if systems['mission']['mission'] is not None or state['game_type'] != 'skirmish':
        raise ValueError('LAN reconnect snapshots are skirmish-only')
    # Constructor resets damage queues/visibility before exact installation.
    for key, value in state.items():
        setattr(manager.state, key, value)
    manager.state.grid.rebuild(manager.state.entities)
    for name, attributes in systems.items():
        system = getattr(manager, name)
        if set(attributes) != set(_attributes(system)):
            raise ValueError('Snapshot system schema mismatch')
        for key, value in attributes.items():
            if name == 'mission' and key == 'script':
                system.script.triggers = value['triggers']
                system.script.progress = value['progress']
            else:
                setattr(system, key, value)
    for pid, attributes in brains.items():
        if type(pid) is not int or pid not in manager.state.players or not manager.state.players[pid].is_ai:
            raise ValueError('Snapshot AI ownership mismatch')
        ai = AIPlayer(manager.state, pid)
        if set(attributes) != set(_attributes(ai)):
            raise ValueError('Snapshot AI schema mismatch')
        vars(ai).update(attributes)
        manager.ai.ais[pid] = ai
    manager._capacity_timer = body['capacity_timer']
    if manager.state.tick != envelope['tick'] or precise_checksum(manager) != envelope['checksum']:
        raise ValueError('Snapshot checksum mismatch')
    return manager


class RecoveryBarrier:
    """Host-only policy for an ALREADY quiesced canonical barrier.

    Caller supplies monotonic transport time. Never use this as permission to
    snapshot a running graph; distributed quiescence is not implemented here.
    Bearer credentials must travel only on the authenticated slot's connection.
    """
    def __init__(self, humans, content):
        import secrets
        if type(humans) is not int or not 2 <= humans <= 4:
            raise ValueError('Human count must be 2..4')
        self.humans = humans
        self.content = content
        self.session = secrets.token_hex(32)
        self._tokens = {slot: secrets.token_hex(32) for slot in range(1, humans)}
        self.epoch = 0
        self._generation = 0
        self.status = 'running'
        self.deadline = None
        self._connected = set(range(humans))
        self._acks = set()

    def credentials(self, slot):
        return dict(session=self.session, token=self._tokens[slot], generation=self._generation,
                    version=GAME_VERSION, protocol=PROTOCOL_VERSION)

    def interrupt(self, slot, *, tick, digest, now):
        from game.net.lan import _digest
        self.poll(now=now)
        if (self.status == 'error' or type(slot) is not int or not 1 <= slot < self.humans
                or type(tick) is not int or tick < 0 or not _digest(digest)):
            raise ValueError('Invalid recovery interruption')
        if self.status == 'running':
            self.epoch += 1
            self.status = 'paused'
            self.tick = tick
            self.digest = digest
            self.deadline = now + 60.
        elif tick != self.tick or digest != self.digest:
            self.abort()
            raise ValueError('Canonical barrier changed')
        self._connected.discard(slot)
        self._acks.clear()

    def poll(self, *, now):
        if self.status == 'paused' and now >= self.deadline:
            self.status = 'error'
            self.error = 'Reconnect grace expired'

    def abort(self):
        self.status = 'error'
        self.error = 'Reconnect explicitly aborted'

    def host_lost(self):
        self.status = 'error'
        self.error = 'Host lost; migration is not supported'

    def authenticate(self, slot, *, session, token, generation, version, protocol, content, now):
        import hmac
        self.poll(now=now)
        if (self.status != 'paused' or type(slot) is not int or slot in self._connected
                or version != GAME_VERSION or type(protocol) is not int or protocol != PROTOCOL_VERSION
                or session != self.session or content != self.content
                or type(generation) is not int or generation != self._generation or slot not in self._tokens
                or not isinstance(token, str) or len(token) != 64 or not token.isascii()
                or not hmac.compare_digest(token, self._tokens[slot])):
            raise ValueError('Invalid resume credentials')
        self._connected.add(slot)

    def acknowledge(self, slot, *, epoch, tick, digest, now):
        self.poll(now=now)
        if self.status != 'paused' or type(slot) is not int or slot not in self._connected:
            raise ValueError('Invalid recovery acknowledgement sender')
        if (type(epoch) is not int or type(tick) is not int
                or epoch != self.epoch or tick != self.tick or digest != self.digest):
            self.status = 'error'
            self.error = 'Recovery protocol/hash mismatch'
            raise ValueError(self.error)
        self._acks.add(slot)

    @property
    def can_resume(self):
        return self.status == 'paused' and len(self._acks) == self.humans

    def finish(self, *, now):
        import secrets
        self.poll(now=now)
        if not self.can_resume:
            raise ValueError('All-peer acknowledgement required')
        self.status = 'running'
        self._generation = self.epoch
        self._tokens = {slot: secrets.token_hex(32) for slot in range(1, self.humans)}


class PendingInputs:
    """Bounded authoritative delayed-input journal, separate from GameState.

    Per-slot sequence is required BEFORE sending input; retries retain that ID.
    The existing LanSession protocol does not supply these IDs yet.
    """
    def __init__(self, humans, *, barrier_tick):
        if type(humans) is not int or not 2 <= humans <= 4 or type(barrier_tick) is not int or barrier_tick < 0:
            raise ValueError('Invalid input ledger')
        self.humans = humans
        self.barrier_tick = barrier_tick
        self._next = [0] * humans
        self._spent = [-1] * humans
        self._entries = {}

    def accept(self, slot, *, sequence, target_tick, commands):
        from game.net.lan import _commands, INPUT_DELAY
        if (type(slot) is not int or not 0 <= slot < self.humans
                or type(sequence) is not int or sequence < 0
                or type(target_tick) is not int
                or not self.barrier_tick <= target_tick <= self.barrier_tick + 2 * INPUT_DELAY):
            raise ValueError('Invalid delayed input window')
        _commands(commands, slot)
        entry = dict(slot=slot, sequence=sequence, target_tick=target_tick,
                     commands=json.loads(_json(commands)))
        key = (slot, sequence)
        if key in self._entries:
            if self._entries[key] != entry:
                raise ValueError('Conflicting input retry')
            return False
        if sequence <= self._spent[slot] or sequence != self._next[slot]:
            raise ValueError('Spent or skipped input sequence')
        latest = max((e['target_tick'] for e in self._entries.values() if e['slot'] == slot),
                     default=self.barrier_tick-1)
        if target_tick <= latest:
            raise ValueError('One input batch per slot per increasing target tick')
        if len(self._entries) >= self.humans * (2 * INPUT_DELAY + 1):
            raise ValueError('Pending input limit')
        self._entries[key] = entry
        self._next[slot] += 1
        return True

    def for_tick(self, tick):
        entries = sorted(self._entries.values(), key=lambda e: (e['slot'], e['sequence']))
        return json.loads(_json([cmd for e in entries if e['target_tick'] == tick for cmd in e['commands']]))

    def commit_through(self, tick):
        if type(tick) is not int or tick < self.barrier_tick:
            raise ValueError('Invalid committed tick')
        for key, entry in list(self._entries.items()):
            if entry['target_tick'] <= tick:
                self._spent[entry['slot']] = max(self._spent[entry['slot']], entry['sequence'])
                del self._entries[key]
        self.barrier_tick = tick + 1

    def export(self):
        return json.loads(_json(dict(humans=self.humans, barrier_tick=self.barrier_tick,
                                    next=self._next, spent=self._spent,
                                    entries=list(self._entries.values()))))

    @classmethod
    def restore(cls, data):
        if type(data) is not dict or set(data) != {'humans', 'barrier_tick', 'next', 'spent', 'entries'}:
            raise ValueError('Invalid restored ledger schema')
        ledger = cls(data['humans'], barrier_tick=data['barrier_tick'])
        if (not isinstance(data['next'], list) or not isinstance(data['spent'], list)
                or len(data['next']) != ledger.humans or len(data['spent']) != ledger.humans
                or any(type(n) is not int or n < 0 for n in data['next'])
                or any(type(s) is not int or not -1 <= s < n
                       for s, n in zip(data['spent'], data['next']))
                or not isinstance(data['entries'], list)
                or len(data['entries']) > ledger.humans * (2 * INPUT_DELAY + 1)):
            raise ValueError('Invalid restored ledger schema')
        ledger._spent = list(data['spent'])
        # Every outstanding sequence must be present exactly once. Starting
        # from spent+1 prevents a missing prefix or an empty gap being blessed.
        ledger._next = [spent + 1 for spent in ledger._spent]
        for entry in data['entries']:
            if type(entry) is not dict or set(entry) != {'slot', 'sequence', 'target_tick', 'commands'}:
                raise ValueError('Invalid restored input entry schema')
            if not ledger.accept(entry['slot'], sequence=entry['sequence'],
                                 target_tick=entry['target_tick'], commands=entry['commands']):
                raise ValueError('Duplicate restored input sequence')
        if ledger._next != data['next']:
            raise ValueError('Invalid restored input sequence')
        return ledger


CHUNK_BYTES = 32768


class ChunkSender:
    """One bounded frame per pump, backpressure through existing _Peer.tx."""
    def __init__(self, data):
        import secrets
        if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_SNAPSHOT:
            raise ValueError('Snapshot size limit')
        self.data = data
        self.digest = hashlib.sha256(data).hexdigest()
        self.transfer = secrets.token_hex(16)
        self.index = -1
        self.done = False

    def pump(self, peer):
        import base64
        from game.net.lan import IO_BUDGET
        if self.done or len(peer.tx) > IO_BUDGET:
            return False
        if self.index == -1:
            message = dict(type='snapshot_begin', transfer=self.transfer,
                           size=len(self.data), digest=self.digest)
        else:
            begin = self.index * CHUNK_BYTES
            message = dict(type='snapshot_chunk', transfer=self.transfer, index=self.index,
                           data=base64.b64encode(self.data[begin:begin+CHUNK_BYTES]).decode('ascii'))
        peer.send(message)
        self.index += 1
        if self.index * CHUNK_BYTES >= len(self.data):
            self.done = True
        return True


class ChunkReceiver:
    """Strict contiguous bounded reassembly; expected digest from host barrier."""
    def __init__(self, expected_digest):
        self.expected_digest = expected_digest
        self.transfer = None
        self.size = None
        self.data = bytearray()
        self.index = 0
        self.done = False

    def receive(self, message):
        import base64
        if self.done:
            raise ValueError('Snapshot transfer already complete')
        if self.transfer is None:
            if (set(message) != {'type', 'transfer', 'size', 'digest'}
                    or message['type'] != 'snapshot_begin'
                    or type(message['size']) is not int or not 1 <= message['size'] <= MAX_SNAPSHOT
                    or message['digest'] != self.expected_digest
                    or not isinstance(message['transfer'], str) or len(message['transfer']) != 32):
                raise ValueError('Invalid snapshot manifest')
            self.transfer, self.size = message['transfer'], message['size']
            return None
        if (set(message) != {'type', 'transfer', 'index', 'data'}
                or message['type'] != 'snapshot_chunk' or message['transfer'] != self.transfer
                or type(message['index']) is not int or message['index'] != self.index
                or not isinstance(message['data'], str)
                or len(message['data']) > ((CHUNK_BYTES+2)//3)*4):
            raise ValueError('Invalid snapshot chunk sequence')
        try:
            chunk = base64.b64decode(message['data'], validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError('Invalid snapshot chunk encoding') from exc
        assert self.size is not None
        if len(chunk) != min(CHUNK_BYTES, self.size-len(self.data)):
            raise ValueError('Invalid snapshot chunk length')
        self.data.extend(chunk)
        self.index += 1
        if len(self.data) == self.size:
            self.done = True
            if hashlib.sha256(self.data).hexdigest() != self.expected_digest:
                raise ValueError('Snapshot transfer hash mismatch')
            return bytes(self.data)
        return None
