"""Replay recording/playback + per-tick state checksums (spec §32/§48 Phase 8).

A replay file stores the initial GameState dict plus the full command log
(command, tick). Re-simulating from the state and injecting commands at their
recorded ticks must reproduce identical per-tick checksums — the same
guarantee lockstep multiplayer needs.

File format (JSON):
  {"format": "star-armada-replay", "version": 1,
   "seed": int, "map": str, "initial_state": {...},
   "commands": [{"tick": int, "cmd": {...}}, ...]}
"""
from __future__ import annotations

import hashlib
import json
import os

from ..core.commands import PlayerCommand
from ..core.state import GameState

REPLAY_FORMAT = "star-armada-replay"
REPLAY_VERSION = 1


# ----------------------------------------------------------------- checksums
def state_checksum(state: GameState) -> str:
    """Stable per-tick state digest (lockstep desync detection + replay verify).

    Round floats to 3dp (float noise across machines), iterate deterministically.
    Excludes per-frame plumbing (vel is derived, but included rounded since AI
    decisions depend on it indirectly — cheap and strict beats clever).
    """
    h = hashlib.sha256()
    st = state
    h.update(f"t{st.tick}|".encode())
    for eid in sorted(st.entities):
        e = st.entities[eid]
        h.update(
            f"{eid}|{e.data_id}|{e.owner}|"
            f"{e.pos.x:.3f},{e.pos.y:.3f},{e.pos.z:.3f}|"
            f"{e.hull:.3f}|{int(e.alive)}|{e.order_type};".encode())
        # #77: a refit level changes hull, shields, firepower and output, so a peer
        # that disagreed about it must fail the digest, not merely diverge quietly.
        h.update(f"L{e.upgrade_level}|".encode())
        h.update(json.dumps([e.crew, e.max_crew, e.crew_loss_accumulator,
                             e.crew_damage_accumulator, e.abandoned_attack_target,
                             e.subsystem_hp('life_support')], separators=(',', ':')).encode())
        h.update(json.dumps(e.boarding, sort_keys=True, separators=(',', ':')).encode())
        h.update(str(e.boarding_party_id).encode())
        h.update(json.dumps([e.recruitment_progress, e.crew_cargo,
                             e.cargo_loss_accumulator, e.crew_mission],
                            sort_keys=True, separators=(',', ':')).encode())
    for pid in sorted(st.players):
        p = st.players[pid]
        h.update(
            f"p{pid}|{p.credits:.3f}|{p.materials:.3f}|{p.energy:.3f}|"
            f"{p.crew:.3f}|{len(p.researched)};".encode())
    return h.hexdigest()


def _player_is_ai(initial: dict, player_id: int) -> bool:
    p = initial.get("players", {}).get(str(player_id)) or \
        initial.get("players", {}).get(player_id)
    return bool(p and p.get("is_ai"))


# ------------------------------------------------------------------ recording
class ReplayRecorder:
    """Records the initial state and every command with its tick."""

    def __init__(self, state: GameState, map_name: str = "skirmish01"):
        from copy import deepcopy
        self._initial = deepcopy(state.to_dict(precise=True))
        self.seed = state.seed
        self.map_name = map_name
        self._commands: list[dict] = []

    def on_command(self, cmd: PlayerCommand, tick: int) -> None:
        # Record ONLY human-originated commands. AI commands are deterministic
        # outputs of the simulation itself — re-feeding them on top of a
        # re-running AI would execute every build twice (found via probe:
        # replay spent 920 cr twice). In multiplayer, commands arriving via
        # the lockstep session are other humans' — record those too; the
        # recorder hook is bypassed for net commands by main.py re-queuing.
        if _player_is_ai(self._initial, cmd.player):
            return
        self._commands.append({"tick": tick, "cmd": cmd.to_dict()})

    def to_dict(self) -> dict:
        return {
            "format": REPLAY_FORMAT,
            "version": REPLAY_VERSION,
            "seed": self.seed,
            "map": self.map_name,
            "initial_state": self._initial,
            "commands": self._commands,
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f)


# ------------------------------------------------------------------ playback
def load_replay(path) -> dict:
    try:
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_REPLAY_BYTES + 1)
        if len(raw) > MAX_REPLAY_BYTES:
            raise ValueError('Replay exceeds the 16 MiB size limit.')
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError('Invalid replay JSON.') from exc
    return validate_replay(data)


class ReplayPlayer:
    """Feeds recorded commands into a game at their recorded ticks."""

    def __init__(self, replay: dict):
        self.data = replay
        self._by_tick: dict[int, list[PlayerCommand]] = {}
        for entry in replay.get("commands", []):
            self._by_tick.setdefault(int(entry["tick"]), []).append(
                PlayerCommand.from_dict(entry["cmd"]))

    def commands_for_tick(self, tick: int) -> list[PlayerCommand]:
        return self._by_tick.get(tick, [])


MAX_REPLAY_BYTES = 16 * 1024 * 1024
MAX_REPLAY_TICKS = 30 * 60 * 60 * 6
MAX_REPLAY_COMMANDS = 100000


def validate_replay(data, check_compatibility=False) -> dict:
    """Bounded JSON-only validation before constructing simulation objects."""
    import math
    import re
    from copy import deepcopy
    from ..core.commands import COMMAND_TYPES
    if not isinstance(data, dict) or data.get('format') != REPLAY_FORMAT:
        raise ValueError('Not a STAR ARMADA replay.')
    # Iterative tree walk bounds recursion, collection sizes, nonfinite values.
    pending, nodes = [(data, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 750000 or depth > 32:
            raise ValueError('Replay structure exceeds validation limits.')
        if isinstance(value, (dict, list)):
            if len(value) > MAX_REPLAY_COMMANDS:
                raise ValueError('Replay collection exceeds validation limits.')
            children = value.values() if isinstance(value, dict) else value
            pending.extend((v, depth + 1) for v in children)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Replay contains a nonfinite number.')
        elif isinstance(value, str) and len(value) > 4096:
            raise ValueError('Replay text exceeds validation limits.')
    version = data.get('version')
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported replay format version.')
    initial = data.get('initial_state')
    if not isinstance(initial, dict) or not isinstance(initial.get('players'), dict):
        raise ValueError('Replay initial state is invalid.')
    if (not isinstance(initial.get('entities', {}), dict)
            or not isinstance(initial.get('command_queue', []), list)):
        raise ValueError('Replay initial state containers are invalid.')
    def integer(value, low=0, high=MAX_REPLAY_TICKS):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Replay tick or identifier is invalid.')
        return value
    start = integer(initial.get('tick', 0))
    players = initial['players']
    if any(not isinstance(player, dict) for player in players.values()):
        raise ValueError('Replay initial state player objects are invalid.')
    if not players or len(players) > 16 or len(initial.get('entities', {})) > 10000:
        raise ValueError('Replay state exceeds supported limits.')
    def command(cmd):
        if (not isinstance(cmd, dict) or not isinstance(cmd.get('type'), str)
                or cmd.get('type') not in COMMAND_TYPES):
            raise ValueError('Replay command type is invalid.')
        for key in ('station_kind', 'ship_id', 'tech_id', 'ability_id', 'formation', 'stance', 'name', 'commander'):
            value = cmd.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 512):
                raise ValueError('Replay command text payload is invalid.')
        pid = integer(cmd.get('player'), 0, 15)
        if str(pid) not in players and pid not in players:
            raise ValueError('Replay command player is invalid.')
        units = cmd.get('unit_ids', [])
        if not isinstance(units, (list, tuple)) or len(units) > 10000:
            raise ValueError('Replay command unit IDs are invalid.')
        for uid in units:
            integer(uid, 0, 100000000)
        if cmd.get('target_id') is not None:
            integer(cmd['target_id'], 0, 100000000)
        pos = cmd.get('target_pos')
        if pos is not None and (not isinstance(pos, (list, tuple)) or len(pos) != 3
                               or any(type(v) not in (int, float) or abs(v) > 1e9 for v in pos)):
            raise ValueError('Replay command position is invalid.')
        try:
            PlayerCommand.from_dict(cmd)
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError('Replay command payload is invalid.') from exc
    entries = data.get('commands')
    if not isinstance(entries, list) or len(entries) > MAX_REPLAY_COMMANDS:
        raise ValueError('Replay command log exceeds limits.')
    previous = start
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Replay command entry is invalid.')
        tick = integer(entry.get('tick'), start)
        if tick < previous:
            raise ValueError('Replay commands are not tick ordered.')
        previous = tick
        command(entry.get('cmd'))
        if _player_is_ai(initial, entry['cmd']['player']):
            raise ValueError('Replay must not inject deterministic AI outputs.')
    for cmd in initial.get('command_queue', []):
        command(cmd)
    result = deepcopy(data)
    if 'compatibility_warning' in result and not isinstance(result['compatibility_warning'], str):
        raise ValueError('Replay compatibility warning metadata is invalid.')
    # Warnings are validator output, never trusted file assertions.
    result.pop('compatibility_warning', None)
    if version == 1:
        if initial.get('command_queue'):
            raise ValueError('Legacy replay has ambiguous pending commands.')
        result['end_tick'] = max(start, max((e['tick'] + 1 for e in entries), default=start))
        result['compatibility_warning'] = ('Legacy v1: duration is unknown; playback ends after the last command. '
                                           'Original game/content compatibility cannot be verified.')
    end = integer(result.get('end_tick'), start)
    if any(e['tick'] >= end for e in entries):
        raise ValueError('Replay command is outside its recorded duration.')
    mods = result.get('mods', [])
    if not isinstance(mods, list) or len(mods) > 16 or any(not isinstance(m, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', m) for m in mods):
        raise ValueError('Replay mod identifiers are invalid.')
    if version == 2:
        if result.get('tick_rate') != 30 or type(result.get('tick_rate')) is not int:
            raise ValueError('Unsupported replay tick rate.')
        if result.get('mode') not in ('skirmish', 'campaign', 'lan'):
            raise ValueError('Replay mode is invalid.')
        duration = result.get('duration_seconds')
        if (type(duration) not in (int, float) or not 0 <= duration <= MAX_REPLAY_TICKS / 30
                or abs(duration - (end - start) / 30) > 1e-9):
            raise ValueError('Replay duration metadata is invalid.')
        pid = integer(result.get('local_player'), 0, 15)
        if str(pid) not in players and pid not in players:
            raise ValueError('Replay viewpoint is invalid.')
        if check_compatibility:
            from game import __version__
            from ..data.store import DataStore
            if result.get('game_version') != __version__:
                raise ValueError('Replay game version is incompatible.')
            store = DataStore(mods=mods or None)
            if result.get('content_digest') != content_digest(store):
                raise ValueError('Replay content/mods are incompatible.')
    from .replay_validation import reconstruct
    reconstruct(initial, mods)
    if initial.get('runtime_state') is None:
        result['compatibility_warning'] = (result.get('compatibility_warning', '') +
            ' Persistent future AI/system state is unavailable: fresh brains and reset system timers are used; '
            'exact mid-match continuation cannot be guaranteed.').strip()
    return result


# Player-facing v2 uses pre-step state ticks; legacy v1 APIs above stay intact.
def content_digest(store=None) -> str:
    from dataclasses import asdict
    from ..data.store import DataStore
    store = store or DataStore.get()
    data = {name: {key: asdict(value) for key, value in getattr(store, name).items()}
            for name in ('weapons', 'ships', 'stations', 'abilities', 'techs', 'factions')}
    data.update({name: getattr(store, name) for name in ('maps', 'rules', 'campaign')})
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class MatchRecording:
    """Observe actual manager steps, including LAN accepted frames, not UI intent."""
    def __init__(self, gm, mode='skirmish', local_player=0, mods=None):
        from copy import deepcopy
        from game import __version__
        self.gm = gm
        self.user_dir: str | None = None
        self.error = ''
        self._step = gm.step
        self._initial_pending = list(gm.state.command_queue)
        from datetime import datetime, timezone
        self._data: dict = dict(format=REPLAY_FORMAT, version=2, game_version=__version__,
                          created_utc=datetime.now(timezone.utc).isoformat(),
                          content_digest=content_digest(gm.ds), tick_rate=30,
                          mode=mode, local_player=local_player, mods=list(mods or []),
                          seed=gm.state.seed, map=gm.state.map_info.name,
                          initial_state=deepcopy(gm.state.to_dict(precise=True)),
                          end_tick=gm.state.tick, commands=[])
        gm.step = self.step

    def step(self, dt):
        if self.gm.state.game_over:
            return self._step(dt)
        tick = self.gm.state.tick
        accepted = []
        for cmd in self.gm.state.command_queue:
            if any(cmd is pending for pending in self._initial_pending):
                continue
            if not _player_is_ai(self._data['initial_state'], cmd.player):
                accepted.append(dict(tick=tick, cmd=cmd.to_dict()))
        if len(self._data['commands']) + len(accepted) > MAX_REPLAY_COMMANDS or tick >= MAX_REPLAY_TICKS:
            self.error = 'Replay recording limit exceeded; the match remains playable.'
            self.close()
            return self._step(dt)
        self._initial_pending = []
        result = self._step(dt)
        if self.gm.state.tick > tick:
            self._data['commands'].extend(accepted)
            self._data['end_tick'] = self.gm.state.tick
        return result

    def rebind_manager(self, manager):
        """Transfer the single step observer without resetting replay history.

        Recovery must drain to the recorded boundary, not skip or replay ticks.
        The caller validates the recovered graph before invoking this seam.
        """
        if manager is self.gm:
            return
        old = self.gm
        active = old.step == self.step
        native = manager.step
        # Pending initial commands belong to the serialized initial snapshot,
        # not the command log. Reconstruction creates new command identities.
        pending_indices = [i for i, cmd in enumerate(old.state.command_queue)
                           if any(cmd is pending for pending in self._initial_pending)]
        pending = [manager.state.command_queue[i] for i in pending_indices]
        if active:
            old.step = self._step
        self.gm = manager
        self._step = native
        self._initial_pending = pending
        if active:
            manager.step = self.step

    def close(self):
        if self.gm.step == self.step:
            self.gm.step = self._step

    def to_dict(self):
        from copy import deepcopy
        data = deepcopy(self._data)
        data['duration_seconds'] = (data['end_tick'] - data['initial_state']['tick']) / data['tick_rate']
        return data

    def save(self, path):
        if self.error:
            raise ValueError(self.error)
        import tempfile
        data = validate_replay(self.to_dict())
        encoded = json.dumps(data, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > MAX_REPLAY_BYTES:
            raise ValueError('Replay exceeds the 16 MiB size limit.')
        folder = os.path.dirname(os.path.abspath(os.fspath(path)))
        os.makedirs(folder, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.replay-', suffix='.tmp', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class PlaybackSession:
    """Private simulation rebuilt from an immutable recording snapshot."""
    def __init__(self, data):
        from copy import deepcopy
        from ..core.manager import GameManager
        self._data: dict = validate_replay(data, check_compatibility=True)
        from .replay_validation import reconstruct
        self.gm = reconstruct(self._data['initial_state'], self._data.get('mods'))
        self.player = ReplayPlayer(self._data)
        self.end_tick = self._data['end_tick']
        self.paused = False
        self.speed = 1.0
        self.accumulator = 0.0

    @property
    def ended(self):
        return self.gm.state.tick >= self.end_tick or self.gm.state.game_over

    def advance(self, dt_frame):
        import math
        if not math.isfinite(dt_frame) or dt_frame < 0:
            raise ValueError('Invalid replay frame duration.')
        if self.paused or self.ended:
            self.accumulator = 0.0
            return
        self.accumulator += min(dt_frame, .25) * self.speed
        # Bounded catch-up: at 4x, at most 30 steps per rendered frame.
        for _ in range(30):
            if self.accumulator + 1e-12 < 1/30 or self.ended:
                break
            self.step()
            self.accumulator = max(0., self.accumulator - 1/30)

    def change_speed(self, direction):
        speeds = (.25, .5, 1., 2., 4.)
        index = speeds.index(self.speed)
        self.speed = speeds[min(len(speeds) - 1, max(0, index + direction))]

    def step(self):
        if self.ended:
            return False
        tick = self.gm.state.tick
        self.gm.state.command_queue.extend(self.player.commands_for_tick(tick))
        self.gm.step(1/30)
        return True