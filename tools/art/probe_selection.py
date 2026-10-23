import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import game.core
from render import asset_selection, menus
settings = dict(menus.DEFAULT_SETTINGS); settings.update(model_preview=True, visual_packs=[])
rep = asset_selection.configure_from_settings(settings)
print('report keys', list(rep))
eb = rep.get('effective_bindings')
print('type', type(eb).__name__, len(eb) if eb else 0)
if isinstance(eb, dict):
    for k in list(eb)[:3]: print('sample', k, eb[k])
    print('syndicate keys', [k for k in eb if k.startswith('syndicate:')])
else:
    print('sample', json.dumps(eb[:2], indent=1))
    print('syndicate rows', [r for r in eb if str(r.get('binding','')).startswith('syndicate:')][:4])
