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
        h.update(json.dumps([e.crew, e.max_crew, e.crew_loss_accumulator,
                             e.subsystem_hp('life_support')], separators=(',', ':')).encode())
        h.update(json.dumps(e.boarding, sort_keys=True, separators=(',', ':')).encode())
        h.update(str(e.boarding_party_id).encode())
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
        self._initial = state.to_dict(precise=True)
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
def load_replay(path: str) -> dict:
    with open(path) as f:
        d = json.load(f)
    if d.get("format") != REPLAY_FORMAT:
        raise ValueError(f"not a replay file: {path}")
    return d


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