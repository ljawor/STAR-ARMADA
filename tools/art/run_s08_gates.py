"""Bounded, serial S08 focused gate; each module owns its native context.

Not the full S09 suite. Logs/counts are real executions; zero tests/skips fail.
Run with the project's venv Python from any directory. Never mutates user paths.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/s08/integrated'
MODULES = (
    'test_s08_asset_updates', 'test_s08_gameplay_dependencies', 'test_s08_pack_safety',
    'test_s08_example_packs', 'test_s08_cosmetic_compatibility', 'test_asset_registry',
    'test_asset_selection', 'test_generic_model_preview', 'test_model_context_lifecycle',
    'test_asset_contract', 'test_runtime_asset_metadata', 'test_model_pipeline',
    'test_model_coverage_reconciliation', 'test_s07_approval_preservation',
    'test_s06_appearance_records', 'test_draw_view_scope', 'test_station_bounds_cache',
    'test_detmath',
)


def input_hashes():
    result = {}
    for directory in ('game', 'render', 'assets', 'art', 'tools', 'tests', 'examples', 'mods'):
        for p in sorted((ROOT / directory).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    for relative in ('main.py',):
        result[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    return result


def run(name, command, env, timeout=180):
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    timed_out = False
    try:
        text, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        text, _ = process.communicate()
    log = OUT / (name + '.txt')
    log.write_text(text)
    row = {'name': name, 'command': command, 'exit_code': process.returncode,
           'timed_out': timed_out, 'seconds': round(time.monotonic() - started, 3),
           'log': log.relative_to(ROOT).as_posix(), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
    if name.startswith('test_'):
        match = re.search(r'^Ran (\d+) tests? in ', text, re.M)
        row['tests_ran'] = int(match[1]) if match else 0
        row['skipped'] = re.findall(r'^.*\.\.\. skipped.*$', text, re.M)
        row['ok'] = process.returncode == 0 and row['tests_ran'] > 0 and not row['skipped'] and not timed_out
    else:
        row['ok'] = process.returncode == 0 and not timed_out
    print(f'{name}: exit={process.returncode} tests={row.get("tests_ran", "tool")} ok={row["ok"]}', flush=True)
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = input_hashes()
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'tests') + os.pathsep + str(ROOT),
               PYTHONDONTWRITEBYTECODE='1', SDL_VIDEODRIVER='cocoa', SDL_AUDIODRIVER='dummy',
               S08_COSMETIC_EVIDENCE=str(OUT / 'cosmetic'))
    results = []
    for module in MODULES:
        code = ('import game.core, unittest, sys; '
                f'suite=unittest.defaultTestLoader.loadTestsFromName({module!r}); '
                'r=unittest.TextTestRunner(verbosity=2).run(suite); '
                'sys.exit(0 if r.wasSuccessful() else 1)')
        results.append(run(module, [sys.executable, '-c', code], env))
    for name, argv in (
        ('validate-models', ['tools/art/validate-models', '--all']),
        ('coverage-check', ['tools/art/reconcile_model_coverage.py', '--check']),
        ('example-check', ['tools/art/build_s08_examples.py', '--check']),
        ('lifecycle-controls', ['tools/art/verify_s08_controls.py']),
    ):
        results.append(run(name, [sys.executable, *argv], env))
    after = input_hashes()
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    report = {'scope': 'S08 focused integration, not the S09 whole suite/package/platform gate',
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'prelude': 'import game.core', 'runner': 'unittest, one fresh process per named module',
              'input_sha256': before, 'source_changed': changed, 'results': results,
              'tests_ran': sum(row.get('tests_ran', 0) for row in results),
              'modules': len(MODULES), 'ok': not changed and all(row['ok'] for row in results)}
    (OUT / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('input_sha256', 'results')}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
