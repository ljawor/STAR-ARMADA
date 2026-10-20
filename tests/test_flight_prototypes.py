"""Focused real-loader integration for the next original Imperial flight pair."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FlightPrototypeTests(unittest.TestCase):
    def test_flight_pair_joins_four_accepted_packs_without_changing_them(self):
        from render.asset_registry import AssetResolver
        packroot = ROOT / 'visual_packs'
        accepted_names = ['vigil-prototype', 'imperium-command-prototype', 'imperium-shipyard-prototype', 'imperium-mining-prototype']
        new_names = ['imperium-talon-prototype', 'imperium-engineer-prototype']
        new_files = [packroot / name / 'visual-pack.json' for name in new_names]
        self.assertTrue(all(p.is_file() for p in new_files), 'Talon and Engineering Corps prototype packs are missing')
        resolver = AssetResolver(ROOT)
        core = {key: resolver.resolve('imperial:' + key).revision for key in ['fighter', 'constructor']}
        old_files = [packroot / name / 'visual-pack.json' for name in accepted_names]
        self.assertEqual(len(resolver.activate_packs(old_files, pack_root=packroot)), 4)
        preserved = {key: resolver.resolve(key).revision for key in ['imperial:corvette', 'imperial:command_station', 'imperial:shipyard', 'imperial:mining_station', 'imperial:bomber', 'rebel:fighter']}
        self.assertEqual(resolver.activate_packs(old_files + new_files, pack_root=packroot),
                         ('prototype:vigil', 'prototype:imperium_command', 'prototype:imperium_shipyard', 'prototype:imperium_mining', 'prototype:imperium_talon', 'prototype:imperium_engineer'), resolver.diagnostics)
        for kind, folder, stem, cap in [('fighter', new_names[0], 'talon', 6000), ('constructor', new_names[1], 'engineer', 11888)]:
            with self.subTest(binding=kind):
                self.assertEqual(resolver.resolve('imperial:' + kind).asset, 'prototype:imperial/' + kind)
                self.assertNotEqual(resolver.resolve('imperial:' + kind).revision, core[kind])
                descriptor = json.loads((packroot / folder / 'visual-pack.json').read_text())
                self.assertEqual([r['binding'] for r in descriptor['content']['replaces']], ['imperial:' + kind])
                mesh = json.loads((packroot / folder / f'assets/models/{stem}.mesh.json').read_text())
                self.assertLessEqual(mesh['triangle_count'], cap)
                self.assertTrue(all(mesh['batches'].values()))
        for key, revision in preserved.items():
            self.assertEqual(resolver.resolve(key).revision, revision)
        resolver.activate_packs([], pack_root=packroot)
        for key, revision in core.items():
            self.assertEqual(resolver.resolve('imperial:' + key).revision, revision)
        import game.core.manager
        from game.data.store import DataStore
        self.assertEqual(DataStore.get().ships['imperial_tie_squadron'].squadron_size, 6)
        self.assertTrue(DataStore.get().ships['imperial_constructor'].is_construction)


if __name__ == '__main__':
    unittest.main()
