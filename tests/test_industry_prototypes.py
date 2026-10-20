"""Narrow playtest integration for the two owner-requested industrial stations."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IndustryPrototypeTests(unittest.TestCase):
    def test_real_packs_replace_only_the_two_named_industrial_stations(self):
        from render.asset_registry import AssetResolver
        packroot = ROOT / 'visual_packs'
        rows = [('shipyard', 'imperium-shipyard-prototype', 'prototype:imperium_shipyard'),
                ('mining_station', 'imperium-mining-prototype', 'prototype:imperium_mining')]
        resolver = AssetResolver(ROOT)
        old = {key: resolver.resolve('imperial:' + key).revision for key in ['shipyard', 'mining_station', 'command_station', 'corvette']}
        descriptors = [packroot / folder / 'visual-pack.json' for _, folder, _ in rows]
        self.assertTrue(all(p.is_file() for p in descriptors), 'The Shipyard and Mining Station packs are missing')
        self.assertEqual(resolver.activate_packs(descriptors, pack_root=packroot), tuple(row[2] for row in rows), resolver.diagnostics)
        for key, folder, _ in rows:
            with self.subTest(station=key):
                asset = resolver.resolve('imperial:' + key)
                self.assertEqual(asset.asset, 'prototype:imperial/' + key)
                self.assertNotEqual(asset.revision, old[key])
                content = json.loads((packroot / folder / 'visual-pack.json').read_text())['content']
                self.assertEqual([r['binding'] for r in content['replaces']], ['imperial:' + key])
        for key in ['command_station', 'corvette']:
            self.assertEqual(resolver.resolve('imperial:' + key).revision, old[key])
        resolver.activate_packs([], pack_root=packroot)
        for key in ['shipyard', 'mining_station']:
            self.assertEqual(resolver.resolve('imperial:' + key).revision, old[key])

    def test_only_mining_focus_adds_an_isolated_prebuilt_review_mine(self):
        spec = importlib.util.spec_from_file_location('play_industry_test', ROOT / 'tools/play_vigil_prototype.py')
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, 'review_map'), 'The isolated mining-review scenario is missing')
        import game.core.manager
        from game.core.manager import GameManager
        from game.data.store import DataStore
        original = DataStore.get().maps['skirmish01']
        before = copy.deepcopy(original)
        mapped = mod.review_map(original, 'mining')
        self.assertEqual(original, before)
        self.assertEqual(mapped['players'][0]['start_units']['mining_station'], 1)
        self.assertEqual(mapped['players'][1:], before['players'][1:])
        for focus in ['vigil', 'command', 'shipyard']:
            self.assertEqual(mod.review_map(original, focus), before)
        gm = GameManager.start_skirmish(mapped)
        self.assertEqual(sum(e.owner == 0 and e.data_id == 'mining_station' for e in gm.state.entities.values()), 1)
        self.assertEqual(original, before)


if __name__ == '__main__':
    unittest.main()
