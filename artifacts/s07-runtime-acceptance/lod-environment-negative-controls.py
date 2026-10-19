"""Run de-fixed in-memory production bodies against the same positive guards.

Expected result: two runs with assertion failures, no fixture errors. No disk
production source mutation, no GL import or context.
"""
import ast
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import test_s07_lod_environment as guard

original = guard.production_namespace
before = hashlib.sha256(guard.SOURCE.read_bytes()).hexdigest()


def remove_threshold_suppression(nodes):
    batch = next(n for n in nodes if isinstance(n, ast.FunctionDef)
                 and n.name == '_draw_ship_role_batch')
    loop = next(n for n in batch.body if isinstance(n, ast.For))
    matches = [n for n in loop.body if isinstance(n, ast.If)
               and any(isinstance(c, ast.Continue) for c in n.body)
               and 'apparent' in ast.unparse(n.test)]
    assert len(matches) == 2
    loop.body = [n for n in loop.body if n not in matches]
    return nodes


controls = (
    ('removed_actual_ship_threshold_suppression', remove_threshold_suppression,
     'test_registered_representatives_cached_thresholds_and_uncached_difference'),
    ('skipped_selected_rock_rng', guard.remove_rock_rng_before_selected,
     'test_actual_field_and_rock_branches_preserve_all_40_placements_and_final_rng'),
)
for label, mutation, test in controls:
    print('DE_FIXED_NEGATIVE_CONTROL', label, flush=True)
    with patch.object(guard, 'production_namespace', lambda mutation_arg=None: original(mutation)):
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite([guard.S07LodEnvironmentTests(test)]))
    if not result.failures or result.errors or result.wasSuccessful():
        raise SystemExit('control did not yield expected assertion failure')
    print('EXPECTED_RED', label, 'assertion_failures=', len(result.failures),
          'errors=', len(result.errors), flush=True)
assert hashlib.sha256(guard.SOURCE.read_bytes()).hexdigest() == before
print('PRODUCTION_SOURCE_SHA256_UNCHANGED', before, flush=True)
