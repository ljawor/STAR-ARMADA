#!/usr/bin/env python3
"""Load the Syndicate prototype pack through the real resolver (no GPU)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import game.core  # breaks the core/systems import cycle, per the project skill
from render.asset_registry import AssetResolver

resolver = AssetResolver(ROOT)
print('pack_bindings before', len(resolver.pack_bindings()))
# activate_packs takes *descriptor file paths*; handing it the pack directory
# is rejected per path with a diagnostic rather than raising, so print them.
accepted = resolver.activate_packs(
    [ROOT / 'visual_packs' / 'syndicate-imperium-prototypes' / 'visual-pack.json'])
print('accepted', accepted)
for item in resolver.diagnostics:
    print('DIAG', item)
print('pack_bindings after', [b['binding'] for b in resolver.pack_bindings()])
for binding in ('syndicate:bomber', 'syndicate:battleship', 'syndicate:supercapital'):
    print('has', binding, resolver.has_binding(binding), 'authored', resolver.is_authored(binding))
    asset = resolver.resolve(binding)
    print('  asset', asset.asset, 'revision', asset.revision[:16],
          'pack', asset.pack_id, 'lod', asset.lod)
