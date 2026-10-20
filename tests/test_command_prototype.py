"""A single new station beside the unchanged, owner-approved Vigil prototype."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / 'visual_packs'


class CommandPrototypeTests(unittest.TestCase):
    def test_real_loader_adds_command_center_without_moving_vigil_or_siblings(self):
        from render.asset_registry import AssetResolver
        descriptor = PACKS / 'imperium-command-prototype/visual-pack.json'
        self.assertTrue(descriptor.is_file(), 'Command Center prototype is missing')
        resolver = AssetResolver(ROOT)
        baseline = resolver.resolve('imperial:command_station')
        siblings = {key: resolver.resolve(key).revision for key in ['imperial:shipyard', 'rebel:command_station']}
        accepted = resolver.activate_packs([PACKS / 'vigil-prototype/visual-pack.json', descriptor], pack_root=PACKS)
        self.assertEqual(accepted, ('prototype:vigil', 'prototype:imperium_command'), resolver.diagnostics)
        command = resolver.resolve('imperial:command_station')
        self.assertEqual(command.asset, 'prototype:imperial/command_station')
        self.assertNotEqual(command.revision, baseline.revision)
        self.assertEqual(resolver.resolve('imperial:corvette').asset, 'prototype:imperial/vigil')
        for key, revision in siblings.items():
            self.assertEqual(resolver.resolve(key).revision, revision)
        vigil = PACKS / 'vigil-prototype/assets/models/vigil.mesh.json'
        self.assertEqual(hashlib.sha256(vigil.read_bytes()).hexdigest(),
                         '3b1649ce032014875504cf9d6cc60f26c8410ed57058991321c6e129c4f3ca3b')
        content = json.loads(descriptor.read_text())['content']
        self.assertEqual([row['binding'] for row in content['replaces']], ['imperial:command_station'])
        payload = json.loads((PACKS / 'imperium-command-prototype/assets/models/command.mesh.json').read_text())
        self.assertLessEqual(payload['triangle_count'], 11888)
        self.assertTrue(all(payload['batches'].values()))
        manifest = json.loads((descriptor.parent / content['replaces'][0]['manifest']).read_text())
        self.assertNotIn('approval', manifest)
        resolver.activate_packs([], pack_root=PACKS)
        self.assertEqual(resolver.resolve('imperial:command_station').revision, baseline.revision)


if __name__ == '__main__':
    unittest.main()
