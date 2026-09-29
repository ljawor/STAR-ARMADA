"""Probe: does main.py shut down cleanly when no game was ever started?

main.py runs its loop at module level and has no import guard, so a plain
import would execute the whole game. This execs the real file in a fresh
namespace with one injection: `pygame.event.get` starts returning a QUIT event,
which drives the loop out through its normal exit path — including the final
teardown lines — while `audio` is still None (i.e. the user quit from a menu).

That is the reported crash: the teardown called `audio.cleanup()`
unconditionally, so quitting from any menu raised
`AttributeError: 'NoneType' object has no attribute 'cleanup'`.

Usage:
  PYTHONPATH=. ./.venv/bin/python tools/probe_main_exit.py [path/to/main.py]

Exits 0 and prints MAIN_EXIT_OK when the shutdown is clean, 1 otherwise.
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "main.py")
os.chdir(ROOT)
sys.path.insert(0, ROOT)

print(f"probing {target}")

import pygame                                            # noqa: E402

# Force the loop to end the way a menu-exit does: a QUIT event, arriving while
# mode == "menu" and audio is still None. Counted, not time-based, so the
# window and menus get a chance to come up first.
_calls = {"n": 0}
_real_get = pygame.event.get


def _get(*a, **k):
    _calls["n"] += 1
    if _calls["n"] > 150:
        return [pygame.event.Event(pygame.QUIT)]
    return _real_get(*a, **k)


pygame.event.get = _get

src = open(target).read()
g = {"__name__": "__main__", "__file__": target}
try:
    exec(compile(src, target, "exec"), g)
except AttributeError as exc:
    if "cleanup" in str(exc):
        print(f"MAIN_EXIT_FAIL — {exc!r}")
        print("  (the teardown called audio.cleanup() before a game was started)")
        sys.exit(1)
    traceback.print_exc()
    sys.exit(1)
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    pygame.event.get = _real_get

mode = g.get("mode")
audio = g.get("audio")
print(f"loop exited: mode={mode}  audio={audio!r}")
if mode != "menu" or audio is not None:
    print(f"MAIN_EXIT_INCONCLUSIVE — expected to exit from a menu with audio "
          f"unset, got mode={mode} audio={audio!r}")
    sys.exit(1)
print("MAIN_EXIT_OK — menu exit with no active game shuts down cleanly")
