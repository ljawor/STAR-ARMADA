"""Run every test module in its own process, with a real video driver.

Why per module: `tests/test_weapon_sfx.py` sets SDL_VIDEODRIVER=dummy at import, process-wide.
In one process that poisons every later GL test — 18 errors and one test that "ran" 28 minutes
without completing, all of which pass in seconds when the driver is real. Separate processes stop
the leak crossing module boundaries, so each module's verdict is attributable and reproducible.

Three modules load zero tests under unittest because their tests are pytest functions
(test_classic_replays_gl, test_classic_screens, test_menu_movie). Those fall back to pytest and
their counts are recorded as pytest counts; a module yielding no tests under either runner is
recorded as `no_tests`, never as a pass.

A timeout is recorded as a timeout. It is never counted as a pass, and a module whose process
dies without any summary is `no_summary`, not `pass`.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 300
UNITTEST_SUMMARY = re.compile(r'^Ran (\d+) tests? in ([\d.]+)s', re.M)
PYTEST_COUNTS = re.compile(r'(\d+) (passed|failed|error|errors|skipped|deselected)')

# Three modules (test_faction_visuals, test_fleet_detail, test_skirmish_setup) cannot be imported
# cold at all: game/systems/__init__ imports a submodule that imports game/core/manager.py, which does
# `from ..systems import (UnitFactory, ...)` while the package is still initializing. Importing
# game.core first populates the package in a workable order — this is what the single-process suite
# does implicitly, and it is the same pre-existing cycle on 56906ea (16/1/9 errors there too).
# Declared explicitly here so the receipt states the prelude rather than hiding it.
RUNNER = (
    "import game.core, unittest, sys\n"
    "suite = unittest.defaultTestLoader.loadTestsFromName({module!r})\n"
    "result = unittest.TextTestRunner(verbosity=1).run(suite)\n"
    "sys.exit(0 if result.wasSuccessful() else 1)\n"
)


def modules():
    return sorted(p.stem for p in (ROOT / 'tests').glob('test_*.py'))


def run_unittest(module, env):
    started = time.time()
    try:
        proc = subprocess.run([sys.executable, '-c', RUNNER.format(module=module)],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {'module': module, 'runner': 'unittest', 'outcome': 'timeout', 'exit_code': None,
                'wall_seconds': TIMEOUT, 'unittest': {}, 'failing': [],
                'tail': [f'killed after {TIMEOUT}s']}
    text = proc.stdout + proc.stderr
    match = UNITTEST_SUMMARY.search(text)
    counts = {'ran': int(match.group(1)), 'seconds': float(match.group(2))} if match else {}
    failed = [line.strip() for line in text.splitlines()
              if line.startswith(('FAIL: ', 'ERROR: '))]
    if proc.returncode == 0:
        outcome = 'pass'
    elif counts:
        outcome = 'fail'
    else:
        outcome = 'no_summary'
    return {'module': module, 'runner': 'unittest', 'outcome': outcome,
            'exit_code': proc.returncode, 'wall_seconds': round(time.time() - started, 1),
            'unittest': counts, 'failing': failed, 'tail': text.strip().splitlines()[-4:]}


def run_pytest(module, env):
    """Fallback for modules whose tests are pytest functions, not unittest cases."""
    started = time.time()
    try:
        proc = subprocess.run([sys.executable, '-m', 'pytest', f'tests/{module}.py', '-q'],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {'module': module, 'runner': 'pytest', 'outcome': 'timeout', 'exit_code': None,
                'wall_seconds': TIMEOUT, 'unittest': {}, 'failing': [],
                'tail': [f'killed after {TIMEOUT}s']}
    text = proc.stdout + proc.stderr
    counts = {}
    for number, kind in PYTEST_COUNTS.findall(text):
        key = 'error' if kind.startswith('error') else kind
        counts[key] = counts.get(key, 0) + int(number)
    collected = sum(counts.get(k, 0) for k in ('passed', 'failed', 'error', 'skipped'))
    failed = [line.strip() for line in text.splitlines()
              if line.startswith(('FAILED ', 'ERROR '))]
    if proc.returncode == 0 and counts.get('passed'):
        outcome = 'pass'
    elif proc.returncode == 5 or not collected:
        outcome = 'no_tests'
    else:
        outcome = 'fail'
    return {'module': module, 'runner': 'pytest', 'outcome': outcome,
            'exit_code': proc.returncode, 'wall_seconds': round(time.time() - started, 1),
            'unittest': {'ran': collected}, 'pytest': counts,
            'failing': failed, 'tail': text.strip().splitlines()[-4:]}


def run_script(module, env):
    """Last resort: modules whose tests are a `main()` script rather than test cases."""
    started = time.time()
    try:
        proc = subprocess.run([sys.executable, f'tests/{module}.py'],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {'module': module, 'runner': 'script', 'outcome': 'timeout', 'exit_code': None,
                'wall_seconds': TIMEOUT, 'unittest': {}, 'failing': [],
                'tail': [f'killed after {TIMEOUT}s']}
    text = proc.stdout + proc.stderr
    ok_markers = [line.strip() for line in text.splitlines() if 'OK' in line and '=' in line]
    return {'module': module, 'runner': 'script',
            'outcome': 'pass' if proc.returncode == 0 and ok_markers else 'fail',
            'exit_code': proc.returncode, 'wall_seconds': round(time.time() - started, 1),
            'unittest': {}, 'script_markers': ok_markers,
            'failing': [], 'tail': text.strip().splitlines()[-3:]}


def summarise(results):
    tally, tests = {}, 0
    for row in results:
        tally[row['outcome']] = tally.get(row['outcome'], 0) + 1
        tests += row['unittest'].get('ran', 0)
    return tally, tests


def main(argv):
    only = None
    merge_path = None
    out_path = None
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == '--only':
            only = set(args.pop(0).split(','))
        elif flag == '--merge':
            merge_path = Path(args.pop(0))
        elif flag == '--out':
            out_path = Path(args.pop(0))
        else:
            raise SystemExit(f'unknown argument {flag}')

    env = {k: v for k, v in os.environ.items()
           if k not in ('SDL_VIDEODRIVER', 'STAR_ARMADA_FIXED_MATERIALS')}
    env['PYTHONPATH'] = str(ROOT / 'tests')
    env['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    todo = [m for m in modules() if only is None or m in only]
    results = []
    started_all = time.time()
    for index, module in enumerate(todo, 1):
        row = run_unittest(module, env)
        if not row['unittest'].get('ran') and row['outcome'] == 'pass':
            row = run_pytest(module, env)
        if row['outcome'] == 'no_tests':
            row = run_script(module, env)
        results.append(row)
        print(f'[{index:3d}/{len(todo)}] {row["outcome"]:<10} {row["wall_seconds"]:7.1f}s  '
              f'{module}  ({row["runner"]}, {row["unittest"].get("ran", 0)} tests)', flush=True)
        for line in row['failing'][:6]:
            print(f'            {line}', flush=True)

    out = Path(out_path) if out_path else ROOT / 'artifacts/s09/per-module.json'
    if merge_path:
        previous = json.loads(merge_path.read_text())
        by_module = {row['module']: row for row in previous['results']}
        for row in results:
            by_module[row['module']] = row
        merged = [by_module[name] for name in sorted(by_module)]
        tally, tests = summarise(merged)
        previous.update({
            'results': merged, 'modules': len(merged), 'tally': tally, 'tests_ran': tests,
            'not_passing': [r for r in merged if r['outcome'] != 'pass'],
            'merge_note': 'rows re-run under the pytest fallback merged into the original sweep',
        })
        previous['wall_seconds'] = round(previous['wall_seconds'] + (time.time() - started_all), 1)
        out.write_text(json.dumps(previous, indent=2) + '\n')
        print('\nmerged', len(results), 'rows; modules:', len(merged), 'tests:', tests,
              'tally:', tally, flush=True)
        print('not passing:', [r['module'] for r in previous['not_passing']] or 'none', flush=True)
        return 0 if not previous['not_passing'] else 1

    tally, tests = summarise(results)
    receipt = {
        'schema': 1,
        'method': 'one process per test module, real SDL video driver (SDL_VIDEODRIVER unset)',
        'candidate_head': None,
        'prelude': 'import game.core (declared: works around a pre-existing circular import in '
                   'game/systems/__init__.py <-> game/core/manager.py; identical on 56906ea)',
        'pytest_fallback': 'unittest yields zero tests for test_classic_replays_gl, '
                           'test_classic_screens and test_menu_movie; those run under pytest',
        'why_not_one_process': ('tests/test_weapon_sfx.py sets SDL_VIDEODRIVER=dummy at import, '
                                'process-wide; in a single process every later GL test errors or hangs. '
                                'Observed: 18 errors and one 28-minute non-completion, all of which pass '
                                'in seconds per process.'),
        'timeout_seconds_per_module': TIMEOUT,
        'modules': len(results),
        'tests_ran': tests,
        'tally': tally,
        'wall_seconds': round(time.time() - started_all, 1),
        'not_passing': [r for r in results if r['outcome'] != 'pass'],
        'results': results,
    }
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print('\nmodules:', len(results), 'tests:', tests, 'tally:', tally,
          'wall:', round(time.time() - started_all, 1), 's', flush=True)
    print('not passing:', [r['module'] for r in receipt['not_passing']] or 'none', flush=True)
    return 0 if not receipt['not_passing'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
