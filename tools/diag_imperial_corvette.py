#!/usr/bin/env python3
"""The Imperial corvette's review-picture entry point, kept so the recorded command still works.

The B6 harness is generic now: `tools/diag_imperial_ship.py` takes `--row` (inventory spelling with
or without its `ship:` prefix, mesh identifier, runtime registry key or label) and defaults to
`imperial:corvette`. This file is that harness with the row pinned to the corvette, so the command
in the batch handoff and in the row's own report runs unchanged:

    env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_imperial_corvette.py \
        --out artifacts/s06_alliance_batch_review/b6-corvette

The row is pinned, not defaulted: `--row` is accepted and validated but cannot retarget this entry
point at another ship - use `tools/diag_imperial_ship.py --row <row>` for that, so a picture can
never land in the corvette's directory carrying another row's name.
"""
import importlib.util
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().with_name('diag_imperial_ship.py')
_spec = importlib.util.spec_from_file_location('diag_imperial_ship', HARNESS)
_harness = importlib.util.module_from_spec(_spec)
sys.modules['diag_imperial_ship'] = _harness
_spec.loader.exec_module(_harness)

if __name__ == '__main__':
    # The pin is appended last, so it wins over any --row the caller passes.
    raise SystemExit(_harness.main([*sys.argv[1:], '--row', 'imperial:corvette']))
