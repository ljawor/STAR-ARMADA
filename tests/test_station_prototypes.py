"""The Imperial station and dockyard prototypes beside the unchanged approved packs.

Focused guard for one reviewed batch: each replacement loads through the real resolver,
lands inside its binding's approved envelope, keeps the six material roles, and leaving the
pack out restores the core asset exactly.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / 'visual_packs'
ROLES = {'accent', 'base', 'cool', 'dark', 'lit', 'trim'}

STATIONS = (
    dict(pack='imperium-research-prototype', stem='research', pack_id='prototype:imperial_research',
         binding='imperial:research_station', asset='prototype:imperial/research_station'),
    dict(pack='imperium-defense-prototype', stem='defense', pack_id='prototype:imperial_defense',
         binding='imperial:defense_platform', asset='prototype:imperial/defense_platform'),
    dict(pack='imperium-sensor-prototype', stem='sensor', pack_id='prototype:imperial_sensor',
         binding='imperial:sensor_station', asset='prototype:imperial/sensor_station'),
    dict(pack='imperium-trade-prototype', stem='trade', pack_id='prototype:imperial_trade',
         binding='imperial:trade_station', asset='prototype:imperial/trade_station'),
    dict(pack='imperium-fighter-prototype', stem='fighter', pack_id='prototype:imperial_fighter',
         binding='imperial:fighter_platform', asset='prototype:imperial/fighter_platform'),
    dict(pack='imperium-repair-prototype', stem='repair', pack_id='prototype:imperial_repair',
         binding='imperial:repair_dock', asset='prototype:imperial/repair_dock'),
    dict(pack='imperium-relay-prototype', stem='relay', pack_id='prototype:imperial_relay',
         binding='imperial:energy_relay', asset='prototype:imperial/energy_relay'),
)


def envelopes():
    registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
    return {row['binding']: row['envelope'] for row in registry['bindings'] if 'envelope' in row}


class StationPrototypeTests(unittest.TestCase):
    def test_each_station_replaces_only_its_binding_and_restores_on_unload(self):
        from render.asset_registry import AssetResolver
        envelope = envelopes()
        resolver = AssetResolver(ROOT)
        baseline = {row['binding']: resolver.resolve(row['binding']).revision for row in STATIONS}
        siblings = resolver.resolve('imperial:shipyard').revision
        descriptors = [PACKS / row['pack'] / 'visual-pack.json' for row in STATIONS]
        for descriptor in descriptors:
            self.assertTrue(descriptor.is_file(), f'{descriptor} is missing')

        accepted = resolver.activate_packs(descriptors, pack_root=PACKS)
        self.assertEqual(accepted, tuple(row['pack_id'] for row in STATIONS), resolver.diagnostics)
        for row in STATIONS:
            resolved = resolver.resolve(row['binding'])
            self.assertEqual(resolved.asset, row['asset'], row['binding'])
            self.assertNotEqual(resolved.revision, baseline[row['binding']])
            content = json.loads((PACKS / row['pack'] / 'visual-pack.json').read_text())['content']
            self.assertEqual([r['binding'] for r in content['replaces']], [row['binding']])
        self.assertEqual(resolver.resolve('imperial:shipyard').revision, siblings)

        for row in STATIONS:
            mesh = PACKS / row['pack'] / f'assets/models/{row["stem"]}.mesh.json'
            payload = json.loads(mesh.read_text())
            low, high = payload['bounds']
            box = envelope[row['binding']]
            for axis in range(3):
                self.assertGreaterEqual(low[axis], box['min'][axis], f'{row["binding"]} axis {axis}')
                self.assertLessEqual(high[axis], box['max'][axis], f'{row["binding"]} axis {axis}')
            self.assertLessEqual(payload['triangle_count'], 11888, row['binding'])
            self.assertGreater(payload['triangle_count'], 1800, row['binding'])
            self.assertEqual(set(payload['batches']), ROLES, row['binding'])
            self.assertTrue(all(payload['batches'].values()), row['binding'])
            self.assertTrue(all(len(tri) == 6 for batch in payload['batches'].values() for tri in batch))
            manifest = json.loads((PACKS / row['pack'] / f'assets/models/manifests/{row["stem"]}.json').read_text())
            self.assertNotIn('approval', manifest, row['binding'])
            self.assertGreaterEqual(manifest['budgets']['triangles'], payload['triangle_count'])
            self.assertEqual(manifest['bounds'], {'min': low, 'max': high})

        resolver.activate_packs([], pack_root=PACKS)
        for row in STATIONS:
            self.assertEqual(resolver.resolve(row['binding']).revision, baseline[row['binding']])


if __name__ == '__main__':
    unittest.main()
