"""Small privacy-safe failure ring. No messages, payloads or tracebacks on disk."""
import builtins
import json
import os
from pathlib import Path
import sys
import threading
import time
from game import __version__

MAX_REPORTS = 8
_PHASES = frozenset(('transport', 'input', 'simulation', 'termination', 'unhandled'))
_lock = threading.Lock()
_sequence = 0


def _reason(reason, exception):
    if not isinstance(reason, str):
        return 'unknown'
    # Emit only fixed classifications, never fragments of caller/peer text.
    for prefix, code in (('Desync', 'desync'), ('Disconnected', 'disconnect'),
                         ('Peer disconnected', 'disconnect'), ('Loading timeout', 'loading_timeout'),
                         ('Lockstep timeout', 'lockstep_timeout'), ('Peer timeout', 'peer_timeout'),
                         ('Connection failed', 'connect_failure'), ('Invalid', 'protocol_rejection'),
                         ('Missing required', 'protocol_rejection'), ('Command count limit', 'protocol_rejection'),
                         ('Frame command count', 'protocol_rejection'), ('Unexpected message', 'protocol_rejection')):
        if reason.startswith(prefix):
            return code
    return 'python_exception' if exception is not None else 'controlled_termination'


def record_failure(user_dir, *, phase, tick, reason='', exception=None):
    """Best effort atomic ring write, <1 KiB/record, never throws to gameplay.

    user_dir is the caller's persistence root, not a peer-supplied path. Record
    contents are fsynced before atomic replace; power loss can still defeat
    best-effort logging.
    """
    global _sequence
    try:
        if not isinstance(phase, str) or phase not in _PHASES:
            return False
        row = dict(schema=1, time_unix=int(time.time()), build=__version__, phase=phase,
                   tick=tick if type(tick) is int and 0 <= tick <= 2**63-1 else None,
                   reason=_reason(reason, exception))
        if exception is not None:
            kind = type(exception)
            row['exception'] = kind.__name__ if getattr(builtins, kind.__name__, None) is kind else 'Exception'
        data = json.dumps(row, sort_keys=True, separators=(',', ':')).encode('utf8')
        if len(data) >= 1024:
            return False
        with _lock:
            folder = Path(user_dir) / 'diagnostics'
            folder.mkdir(parents=True, exist_ok=True)
            slot = _sequence % MAX_REPORTS
            _sequence += 1
            target = folder / f'failure-{slot}.json'
            temporary = folder / f'failure-{slot}.tmp'
            try:
                with temporary.open('wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except Exception:
                    pass
        return True
    except Exception:
        return False


def install_exception_hook(user_dir, tick_provider):
    """Capture uncaught Python exceptions, then retain Python's normal hook.

    Does not capture native GL/access-violation crashes, signals, os._exit, or
    exceptions swallowed elsewhere. No exception message or traceback is stored.
    """
    previous = sys.excepthook
    def hook(kind, exception, traceback):
        try:
            tick = tick_provider()
        except Exception:
            tick = None
        record_failure(user_dir, phase='unhandled', tick=tick,
                       exception=exception)
        previous(kind, exception, traceback)
    sys.excepthook = hook
