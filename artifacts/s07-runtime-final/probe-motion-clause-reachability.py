"""Is the `is_authored` clause in the phased-motion predicate reachable?

The independent review noted that mutating the predicate to `':' in shape` (dropping the
is_authored clause) keeps every test green, because the legacy control selects nothing and
therefore gets the colon-free 'needle' shape. A surviving mutation means either a missing
test or a clause that cannot bite. This probe decides which, by measuring the real
catalogue: for every reachable ship binding, is there any (shape has a colon, is_authored
is False) row?

Run with the application imported first, on a real data store, with the real resolver
configured exactly as the runtime configures it.
"""
import json
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import game.core.manager  # noqa: F401  (import order: core before data store)
import render.asset_selection as selection
from game.data.store import DataStore
from render.ship_sizes import readable_size

rows = []
for preview in (False, True):
    selection.configure({'model_preview': preview, 'visual_packs': []})
    store = DataStore()
    for data_id, data in sorted(store.ships.items()):
        for faction in (data.faction, 'alliance', 'legion', 'syndicate', 'rebel', 'confed', 'imperial'):
            binding = selection.ship_binding(store, data_id, faction)
            shape = readable_size(store, data_id, 24.0, faction)
            shape = getattr(shape, 'shape', shape)
            rows.append({
                'preview': preview, 'data_id': data_id, 'faction': faction,
                'binding': binding, 'shape': shape,
                'shape_has_colon': isinstance(shape, str) and ':' in shape,
                'is_authored': bool(binding) and selection.is_authored(binding),
            })

reachable = [r for r in rows if r['shape_has_colon'] and not r['is_authored']]
authored = [r for r in rows if r['shape_has_colon']]
report = {
    'probe': 'phased-motion is_authored reachability',
    'rows_examined': len(rows),
    'rows_with_colon_shape': len(authored),
    'rows_colon_and_not_authored': len(reachable),
    'examples_colon_and_not_authored': reachable[:10],
    'conclusion': ('the is_authored clause is unreachable-false: every colon shape comes from a binding '
                   'that ship_binding already gated on is_authored, so dropping the clause cannot change '
                   'behaviour and no test can pin it without constructing an impossible state. The clause '
                   'is defence in depth, not a behavioural gate.'
                   if not reachable else
                   'REACHABLE: the clause changes behaviour for the listed rows, so it needs a test.'),
}
print(json.dumps(report, indent=2))
out = os.path.join(ROOT, 'artifacts/s07-runtime-final/motion-ownership-clause-reachability.json')
with open(out, 'w') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
sys.exit(0 if not reachable else 1)
