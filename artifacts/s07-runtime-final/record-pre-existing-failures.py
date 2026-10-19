"""Record the pre-existing failures with the evidence that classifies them.

A failure that is merely asserted to be "pre-existing" is an opinion. This records, for each
failure on the final tree, the same test run against a pristine extraction of the base commit,
so the classification is reproducible from the file rather than trusted from the message.

Two distinct phenomena are recorded, because they need different handling:
  * test_crew_recovery_ui — a guard whose expectation contradicts an approved decision.
  * the import-order modules — not failures at all under a declared prelude; the earlier
    isolation-only numbers are kept beside the resolved ones.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path('/Users/lukaszjawor/.hermes/cache/scratch/sa-base-step1')
BASE_COMMIT = '56906ea7c73c219fbdc91c68176104b23d0f7712'
FLAKY_ORDER = ['test_faction_visuals', 'test_fleet_detail', 'test_skirmish_setup']
PRELUDE = ('import game.core, unittest\nsuite = unittest.defaultTestLoader.loadTestsFromName({m!r})\n'
           'result = unittest.TextTestRunner(verbosity=0).run(suite)\n')


def env_at(root):
    env = {k: v for k, v in os.environ.items()
           if k not in ('SDL_VIDEODRIVER', 'STAR_ARMADA_FIXED_MATERIALS')}
    env['PYTHONPATH'] = str(root / 'tests')
    return env


def run(root, args, timeout=300):
    proc = subprocess.run(args, cwd=root, env=env_at(root), capture_output=True,
                          text=True, timeout=timeout)
    return {'exit_code': proc.returncode, 'output': (proc.stdout + proc.stderr)}


def failing_lines(text):
    return [line.strip() for line in text.splitlines()
            if line.startswith(('FAIL: ', 'ERROR: ', 'AssertionError', 'ImportError'))]


def counts(text):
    ran = re.search(r'^Ran (\d+) tests?', text, re.M)
    fails = len(re.findall(r'^FAIL: ', text, re.M))
    errors = len(re.findall(r'^ERROR: ', text, re.M))
    return {'ran': int(ran.group(1)) if ran else 0, 'failures': fails, 'errors': errors}


record = {
    'schema': 1,
    'base_commit': BASE_COMMIT,
    'baseline_extraction': str(BASELINE),
    'baseline_note': ('a `git archive` extraction of the base commit outside the worktree, so the '
                      'same tests can be run against bytes this increment never touched'),
    'method': 'same command, same interpreter, same driver; only the tree differs',
    'pre_existing': {},
}

# 1. the guard whose expectation contradicts the approved convoy-parity decision
module = 'test_crew_recovery_ui'
ours = run(ROOT, [sys.executable, '-m', 'unittest', '-v', module])
theirs = run(BASELINE, [sys.executable, '-m', 'unittest', '-v', module])
record['pre_existing']['test_crew_recovery_ui'] = {
    'test': 'test_crew_recovery_ui.RecoveryUITests.test_faction_transports_have_small_known_solid_visuals',
    'final_tree': {'exit_code': ours['exit_code'], 'counts': counts(ours['output']),
                   'detail': failing_lines(ours['output'])},
    'base_commit': {'exit_code': theirs['exit_code'], 'counts': counts(theirs['output']),
                    'detail': failing_lines(theirs['output'])},
    'contradicted_decision': 's06-imperial-convoy-parity-2026-10-18',
    'classification': 'pre_existing',
    'why_it_fails': ('the guard expects the legacy box shape for imperial transports, but imperial '
                     'convoys are authored hardware since the convoy-parity decision, so the tree '
                     'returns imperial:convoy'),
    'handling': ('carried as a recorded pre-existing failure; repairing the expectation means editing '
                 'an S06 guard together with the record that authorized the change, which is not '
                 'part of this increment'),
}

# 2. modules that cannot be imported cold — resolved by a declared prelude, not a failure
record['import_order'] = {}
for module in FLAKY_ORDER:
    cold = run(ROOT, [sys.executable, '-m', 'unittest', module])
    base = run(BASELINE, [sys.executable, '-m', 'unittest', module])
    prelude = run(ROOT, [sys.executable, '-c',
                         PRELUDE.format(m=module) + 'import sys; sys.exit(0 if result.wasSuccessful() else 1)\n'])
    record['import_order'][module] = {
        'cold_import_final_tree': {'exit_code': cold['exit_code'], 'counts': counts(cold['output']),
                                   'detail': failing_lines(cold['output'])[:2]},
        'cold_import_base_commit': {'exit_code': base['exit_code'], 'counts': counts(base['output'])},
        'with_declared_prelude_final_tree': {'exit_code': prelude['exit_code'],
                                             'counts': counts(prelude['output'])},
        'classification': ('not_a_failure: pre-existing circular import between '
                           'game/systems/__init__.py and game/core/manager.py; identical on the base commit'),
    }

# 3. the single-process run that could not serve as a gate
record['invalid_gate'] = {
    'why': ('tests/test_weapon_sfx.py sets SDL_VIDEODRIVER=dummy at import, process-wide, so later GL '
            'modules error (18) or hang; one test did not complete in ~28 minutes and passes in seconds '
            'per process'),
    'evidence': ['artifacts/s07-runtime-final/full-suite-bounded.log',
                 'artifacts/s07-runtime-final/full-suite-final-opaque-aborted.log',
                 'artifacts/s07-runtime-final/full-suite-not-a-valid-gate.json'],
}

out = ROOT / 'artifacts/s07-runtime-final/pre-existing-failures.json'
out.write_text(json.dumps(record, indent=2) + '\n')
crew = record['pre_existing']['test_crew_recovery_ui']
print('crew_recovery — final tree exit', crew['final_tree']['exit_code'],
      crew['final_tree']['counts'], '| base commit exit', crew['base_commit']['exit_code'],
      crew['base_commit']['counts'])
for module, row in record['import_order'].items():
    print(f"{module}: cold final={row['cold_import_final_tree']['counts']} "
          f"cold base={row['cold_import_base_commit']['counts']} "
          f"prelude final={row['with_declared_prelude_final_tree']['counts']}")
print('wrote', out)
