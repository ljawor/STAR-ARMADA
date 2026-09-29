"""Multiplayer net layer (spec §48 Phase 8): lockstep command exchange.

Design (matches the sim's determinism guarantees):
- The simulation NEVER talks to the network. A `LockstepSession` sits beside
  the GameManager and exchanges serialized PlayerCommands only — the same
  objects the local queue consumes.
- Fixed lockstep at `LOCKSTEP_RATE` (20 Hz): each network turn collects all
  commands players submitted since the previous turn, stamps them with the
  tick they will execute on, and exchanges them with the peer. Commands
  received for tick T are held until the local sim reaches tick T
  (input-delay buffer), then queued in deterministic (player, arrival) order.
- Checksums: each turn carries the sender's checksum of the state AFTER its
  last simulated tick; a mismatch raises DesyncError (fatal by design —
  deterministic sims cannot be "resynced" safely mid-stream).

Transport is abstract (`Transport`): LAN play uses UDP `UdpTransport`
(direct IP:port, no matchmaking). A `LoopbackTransport` pair connects two
sessions in-process for tests.
"""
from __future__ import annotations

import json
import socket
import threading

from .replay import state_checksum
from ..core.commands import PlayerCommand

LOCKSTEP_RATE = 20          # network turns per second
INPUT_DELAY_TICKS = 10      # command scheduled this far in the future


class DesyncError(RuntimeError):
    pass


class Transport:
    """Peer link: send a JSON-able message, receive one (blocking with timeout)."""

    def send(self, msg: dict) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def recv(self, timeout: float) -> dict | None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        pass


class LoopbackTransport(Transport):
    """In-process pair for tests: a.send -> b.recv and vice versa."""

    peer: "LoopbackTransport | None"
    inbox: list[dict]

    def __init__(self):
        self.peer = None
        self.inbox: list[dict] = []

    @classmethod
    def pair(cls) -> tuple["LoopbackTransport", "LoopbackTransport"]:
        a, b = cls(), cls()
        a.peer, b.peer = b, a
        return a, b

    def send(self, msg: dict) -> None:
        self.peer.inbox.append(msg)

    def recv(self, timeout: float) -> dict | None:
        """Block up to `timeout` for a message (lockstep peers send+wait)."""
        import time
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self.inbox:
                return self.inbox.pop(0)
            time.sleep(0.001)
        return None


class UdpTransport(Transport):
    """Direct IP:port UDP link (host binds, join sends first)."""

    def __init__(self, bind_port: int = 0, peer: tuple[str, int] | None = None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", bind_port))
        self.sock.settimeout(0.5)
        self.peer = peer
        self._rx = threading.Thread(target=self._pump, daemon=True)
        self.inbox: list[dict] = []
        self._alive = True
        self._rx.start()

    def local_port(self) -> int:
        return self.sock.getsockname()[1]

    def _pump(self) -> None:
        while self._alive:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            if self.peer is None:
                self.peer = addr          # first packet from joiner = peer
            try:
                self.inbox.append(json.loads(data.decode()))
            except (ValueError, UnicodeDecodeError):
                pass

    def send(self, msg: dict) -> None:
        if self.peer is not None:
            self.sock.sendto(json.dumps(msg).encode(), self.peer)

    def recv(self, timeout: float) -> dict | None:
        """Block up to `timeout` for a packet (the pump thread fills inbox)."""
        import time
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self.inbox:
                return self.inbox.pop(0)
            time.sleep(0.002)
        return None

    def close(self) -> None:
        self._alive = False
        self.sock.close()


class LockstepSession:
    """Runs beside the GameManager; owns the input-delay buffer."""

    def __init__(self, local_player: int, transport: Transport,
                 player_count: int = 2):
        self.local_player = local_player
        self.transport = transport
        self.player_count = player_count
        self._outbox: list[PlayerCommand] = []       # submitted, not yet sent
        self._scheduled: dict[int, list] = {}        # tick -> [PlayerCommand]
        self._remote_last_checksum: str | None = None
        self.turn = 0
        self.last_checksum = ""

    # ------------------------------------------------------------------ local
    def submit(self, cmd: PlayerCommand, current_tick: int) -> None:
        """Local player command: schedule with input delay, send to peers."""
        run_tick = current_tick + INPUT_DELAY_TICKS
        self._scheduled.setdefault(run_tick, []).append(cmd)
        self._outbox.append(cmd)

    def commands_for_tick(self, tick: int) -> list:
        """Drain the buffer: commands due at this exact tick, in order."""
        cmds = self._scheduled.pop(tick, [])
        return sorted(cmds, key=lambda c: (c.player,))

    # ------------------------------------------------------------------ turns
    def end_turn(self, current_tick: int, checksum: str,
                 timeout: float = 2.0) -> None:
        """Called every LOCKSTEP tick: exchange commands + checksums."""
        self.turn += 1
        payload = {
            "turn": self.turn,
            "tick": current_tick,
            "checksum": checksum,
            "cmds": [c.to_dict() for c in self._outbox],
        }
        self._outbox = []
        self.transport.send(payload)
        acked = 0
        while acked < self.player_count - 1:
            msg = self.transport.recv(timeout)
            if msg is None:
                raise TimeoutError("lockstep peer did not respond")
            for d in msg.get("cmds", []):
                cmd = PlayerCommand.from_dict(d)
                run_tick = current_tick + INPUT_DELAY_TICKS
                self._scheduled.setdefault(run_tick, []).append(cmd)
            self._remote_last_checksum = msg.get("checksum")
            self.last_checksum = checksum
            acked += 1

    def check_desync(self, my_checksum: str) -> None:
        if self._remote_last_checksum and self._remote_last_checksum != my_checksum:
            raise DesyncError(
                f"checksum mismatch: local={my_checksum} "
                f"remote={self._remote_last_checksum}")