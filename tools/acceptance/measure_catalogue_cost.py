"""Run one benchmark trial under an explicitly chosen model selection.

The benchmark CLI builds its own state and renderer but never configures model
selection, so a bare `main.py --benchmark` always measures the legacy default.
S09 has to measure the complete opt-in catalogue, so this wrapper configures the
real selection seam (the same function the application calls) and then hands the
argument list to the real benchmark CLI. It changes no product code, no fixture
and no quality parameter.

Usage:
  .venv/bin/python tools/acceptance/measure_catalogue_cost.py \
      --selection preview|legacy -- <benchmark CLI arguments>

Every trial must be a fresh process; the driver loops this script.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv):
    args = list(argv[1:])
    selection = 'legacy'
    if '--selection' in args:
        index = args.index('--selection')
        selection = args[index + 1]
        del args[index:index + 2]
    if args[:1] == ['--']:
        args = args[1:]
    if selection not in ('legacy', 'preview'):
        raise SystemExit(f'unknown selection {selection!r}')

    sys.path.insert(0, str(ROOT))
    # Import the application package first: game/systems <-> game/core has a
    # real import cycle and tests/probes that skip this cannot import.
    import game.core  # noqa: F401
    from render.asset_selection import configure_from_settings, diagnostics

    settings = {'model_preview': selection == 'preview', 'visual_packs': []}
    configure_from_settings(settings, data_store=None)
    active = diagnostics()
    if (active.get('mode') == 'preview') != (selection == 'preview'):
        raise SystemExit(f'selection did not take effect: asked {selection}, got {active}')

    from game.benchmark import cli
    rc = cli(args)
    print('SELECTION ' + json.dumps(active, sort_keys=True), flush=True)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))
