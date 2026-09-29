"""Replay + lockstep net layer (Phase 8 spec §48, replay files §32).

Replay: command-log recording with per-tick checksums; deterministic re-sim.
Lockstep: 20 Hz turn exchange beside the sim, input-delay buffer, UDP or
in-process loopback transport. The sim never blocks on the network —
main.py polls `commands_for_tick()` and re-queues them.
"""
import json
import os
import time
from .lockstep import (LockstepSession, LoopbackTransport, UdpTransport,
                       Transport, INPUT_DELAY_TICKS, LOCKSTEP_RATE,
                       DesyncError)
from .replay import ReplayRecorder, ReplayPlayer, load_replay, state_checksum

__all__ = [
    "LockstepSession", "LoopbackTransport", "UdpTransport", "Transport",
    "INPUT_DELAY_TICKS", "LOCKSTEP_RATE", "DesyncError",
    "ReplayRecorder", "ReplayPlayer", "load_replay", "state_checksum",
]