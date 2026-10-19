"""Run the modules the single-process suite could not decide, each in its own process.

The full suite cannot be a gate here: tests/test_weapon_sfx.py sets SDL_VIDEODRIVER=dummy at
import, process-wide, so every later GL module either errors or hangs. One process per module
with the real driver avoids the leak entirely and makes each module's verdict attributable.

Every run is bounded. A timeout is recorded as a timeout, never as a pass.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = [
    'test_audio',
    'test_crew_recovery_ui',
    'test_model_coverage_reconciliation',
    'test_renderer_constructor_cleanup',
    'test_model_context_lifecycle',
    'test_lan_recovery_handoff',
    'test_lan_recovery_ui',
    'test_ship_material_passes',
]
TIMEOUT = 420


def main():
    env = {k: v for k, v in __import__('os').environ.items()
           if k not in ('SDL_VIDEODRIVER', 'STAR_ARMADA_FIXED_MATERIALS')}
    env['PYTHONPATH'] = str(ROOT / 'tests')
    results = []
    for module in MODULES:
        started = time.time()
        try:
            proc = subprocess.run([sys.executable, '-m', 'unittest', '-v', module],
                                  cwd=ROOT, env=env, capture_output=True, text=True,
                                  timeout=TIMEOUT)
            elapsed = round(time.time() - started, 1)
            tail = (proc.stdout + proc.stderr).strip().splitlines()
            results.append({
                'module': module, 'outcome': 'pass' if proc.returncode == 0 else 'fail',
                'exit_code': proc.returncode, 'seconds': elapsed,
                'summary': [line for line in tail if line.startswith(('Ran ', 'OK', 'FAILED'))],
                'failing': [line for line in tail if line.startswith(('FAIL: ', 'ERROR: '))],
            })
        except subprocess.TimeoutExpired:
            results.append({'module': module, 'outcome': 'timeout',
                            'exit_code': None, 'seconds': TIMEOUT,
                            'summary': ['exceeded %ss and was killed' % TIMEOUT],
                            'failing': []})
        row = results[-1]
        print(f"{row['outcome']:<8} {row['seconds']:7.1f}s  {module}", flush=True)
        for line in row['failing']:
            print(f'         {line}', flush=True)
    out = ROOT / 'artifacts/s07-runtime-final/gl-modules-separate-processes.json'
    out.write_text(json.dumps({'schema': 1,
                               'why': 'single-process suite is not a valid gate: SDL_VIDEODRIVER=dummy '
                                      'is set process-wide at import by tests/test_weapon_sfx.py',
                               'driver': 'real (SDL_VIDEODRIVER unset)',
                               'timeout_seconds_per_module': TIMEOUT,
                               'results': results}, indent=2) + '\n')
    bad = [r['module'] for r in results if r['outcome'] != 'pass']
    print('\nnot passing:', bad if bad else 'none')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
