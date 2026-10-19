"""Prove S08 lifecycle guards reject deliberate in-memory regressions.

Run in a fresh native GL process. No production or approved asset is modified.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
from unittest import TestResult
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import game.core
from render import asset_selection as selection
from test_s08_asset_updates import SessionAssetUpdates, NativeSessionAssetUpdates


def run_case(case, mutation):
    result = TestResult()
    with mutation:
        case.run(result)
    # An unexpected infrastructure error is never evidence of a biting guard.
    return {'ran': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'skips': len(result.skipped),
            'assertions': [text for _, text in result.failures],
            'unexpected_errors': [text for _, text in result.errors]}


def main():
    from render import renderer as renderer_module
    controls = {
        'stale_cpu_helpers': run_case(SessionAssetUpdates(
            'test_same_path_revision_update_invalidates_all_bounds_and_contact_helpers'),
            patch.object(selection, 'invalidate_geometry_helpers', lambda: None)),
        'path_only_gpu_key': run_case(SessionAssetUpdates(
            'test_same_path_revision_update_invalidates_all_bounds_and_contact_helpers'),
            patch.object(selection, 'gpu_cache_key', lambda binding, role, legacy: legacy)),
        'undeleted_gl_lists': run_case(NativeSessionAssetUpdates(
            'test_native_lists_are_deleted_and_recompiled_after_update_and_context_recreation'),
            patch.object(renderer_module._gl, 'glDeleteLists', lambda *args: None)),
    }
    controls['restored_cpu'] = run_case(SessionAssetUpdates(
        'test_same_path_revision_update_invalidates_all_bounds_and_contact_helpers'), contextlib.nullcontext())
    controls['restored_native_gl'] = run_case(NativeSessionAssetUpdates(
        'test_native_lists_are_deleted_and_recompiled_after_update_and_context_recreation'), contextlib.nullcontext())
    ok = all(v['ran'] == 1 and v['failures'] == 1 and v['errors'] == 0 and v['skips'] == 0
             for k, v in controls.items() if not k.startswith('restored_'))
    ok = ok and all(v['ran'] == 1 and v['failures'] == 0 and v['errors'] == 0 and v['skips'] == 0
                    for k, v in controls.items() if k.startswith('restored_'))
    report = {'ok': ok, 'controls': controls}
    output = ROOT / 'artifacts/s08/lifecycle-controls.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
