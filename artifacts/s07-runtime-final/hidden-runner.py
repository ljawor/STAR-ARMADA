"""Run focused CPU guards and retain independent mutation/isolation receipts."""
from pathlib import Path
import hashlib
import inspect
import json
import sys
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import game.core.manager
from game.data.store import DataStore
from render import asset_selection as selection
from render.renderer import Renderer
import render.renderer as renderer_module
from test_s07_hidden_contact_acceptance import HiddenContactAcceptanceTests as Guards

out = ROOT/'artifacts/s07-runtime-final'
def protected():
    # Render-only acceptance does not invoke menu/persistence services. Include
    # all actual source-tree user namespaces plus selection/approved metadata.
    files = set(ROOT.glob('*.json'))
    for name in ('saves', 'replays', 'settings', 'assets/models', 'art/manifests'):
        p = ROOT/name
        if p.exists():
            files.update(q for q in p.rglob('*') if q.is_file())
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}

before = protected()
store = DataStore._instance
prior = selection._selection, selection._resolver, selection._generation
with (out/'hidden-focused-verified.txt').open('w') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
isolated = (DataStore._instance is store and selection._selection is prior[0]
            and selection._resolver is prior[1] and selection._generation == prior[2])
# Independent, non-expected-failure run exposes the exact de-fixed failures.
Guards.setUpClass()
try:
    source = textwrap.dedent(inspect.getsource(Renderer._visual_hit))
    gate = '    if not self.state.can_see(self.local_player, target_id):\n        return fx\n'
    assert source.count(gate) == 1
    namespace = dict(vars(renderer_module))
    exec(compile(source.replace(gate, '', 1), '<hidden-negative-control>', 'exec'), namespace)
    with patch.object(Renderer, '_visual_hit', namespace['_visual_hit']):
        with (out/'hidden-negative-control.txt').open('w') as stream:
            negative = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                Guards('test_hidden_historical_contacts_do_not_follow_current_transform'))
    rows = [r['binding'] for r in Guards.rows]
finally:
    Guards.doClassCleanups()
after = protected()
report = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
              representative_bindings=rows, datastore_selection_restored=isolated,
              protected_files=len(before), protected_unchanged=before == after,
              negative_control=dict(source='in-memory production _visual_hit with can_see early return removed',
                                    tests_run=negative.testsRun, failures=len(negative.failures),
                                    errors=len(negative.errors),
                                    failing_cases=[str(case) for case, tb in negative.failures]),
              limits=['CPU only; draw_hit GL endpoint intercepted, no rasterization',
                      'Four actual Imperial selected consumers, not exhaustive faction or asset coverage',
                      'Historical ballistic contact memory; no fabricated remembered ship/station snapshots',
                      'No full S07 closure, production activation, S08/S09, merge or release acceptance'])
(out/'hidden-report.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
assert result.wasSuccessful() and isolated and before == after
assert len(negative.failures) == 12 and not negative.errors
