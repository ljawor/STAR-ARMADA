"""The B6 batch's acceptance test: is the authored Imperial ship actually served?

Three measurements, in the order that matters:

1. **Stock** - no preview session, nothing patched. `ship_visual_key` must return the legacy shape, and
   `selected_binding` must be false. Appearance approval is not activation, and a pending row serves
   nothing by default.
2. **Registered?** - the registry row must *not* carry an authored status and the binding must not be in
   `art/manifests/pipeline.json`. This is the measurement the batch's guards and the five
   `test_no_pending_binding_is_registered_anywhere_in_production` guards agree on: serving a reviewer
   must never mean registering the row.
3. **A review session is shown the candidate** - with a preview session configured *and* selection
   patched for this one binding, exactly the way the batch review harness patches it, `ship_visual_key`
   returns the authored binding. That is the seam working: it reads the selection, not a registry entry.

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b6_servability.py imperial:corvette
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class _Ship:
    def __init__(self, faction, role):
        self.faction = faction
        self.category = role
        self.crew_capacity = 0


class _Store:
    """The minimum a data row has to offer, so the function can be driven without a live game."""

    def __init__(self, data_id, faction, role, legacy_shape):
        self.ships = {data_id: _Ship(faction, role)}
        self._shape = legacy_shape

    def ship_visual(self, _data_id):
        return {'shape': self._shape}


def main():
    sys.path.insert(0, str(ROOT))
    from render import asset_selection as sel
    from render.faction_visuals import ship_visual_key

    binding = sys.argv[1] if len(sys.argv) > 1 else 'imperial:corvette'
    faction, role = binding.split(':')[0], binding.split(':')[1]
    data_id = f'{faction}_{role}'
    store = _Store(data_id, faction, role, role)
    row = next((b for b in json.loads((ROOT / 'assets/models/registry.json').read_text())['bindings']
                if b['binding'] == binding), None)
    pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text())

    sel.configure({})
    stock = ship_visual_key(store, data_id)
    registered = row is not None and row.get('status') not in ('procedural_legacy', 'authoring_pending')
    in_pipeline = binding in {a['binding'] for a in pipeline['assets']}

    sel.configure({'model_preview': True}, asset_root=str(ROOT))
    original = sel.selected_binding
    try:
        sel.selected_binding = lambda candidate: candidate == binding
        reviewed = ship_visual_key(store, data_id)
    finally:
        sel.selected_binding = original
        sel.configure({})

    print(f'stock      -> {stock!r}      (registered={registered}, in pipeline={in_pipeline})')
    print(f'review     -> {reviewed!r}')
    ok = (stock != binding and reviewed == binding and not registered and not in_pipeline
          and row is not None and row.get('manifest') is not None)
    print('SERVING_OK' if ok else 'SERVING_FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
