"""Focused acceptance for one reversible visual-only Vigil replacement."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / 'visual_packs'
PACK = PACK_ROOT / 'vigil-prototype'


class VigilPrototypeTests(unittest.TestCase):
    def test_launcher_uses_separate_profile_and_enables_only_the_prototype(self):
        import tempfile
        launcher = ROOT / 'tools/play_vigil_prototype.py'
        self.assertTrue(launcher.is_file(), 'A directly playable prototype launcher is missing')
        from tools.play_vigil_prototype import prepare_profile
        settings = ROOT / 'saves/settings.json'
        previous = settings.read_bytes() if settings.exists() else None
        with tempfile.TemporaryDirectory(prefix='vigil-test-', dir=ROOT.parent) as temp:
            profile = Path(temp)
            prepare_profile(profile)
            saved = json.loads((profile / 'saves/settings.json').read_text())
            self.assertTrue(saved['model_preview'])
            self.assertEqual(saved['visual_packs'], ['vigil-prototype', 'imperium-command-prototype'])
            self.assertTrue((profile / 'visual_packs/vigil-prototype/visual-pack.json').is_file())
            self.assertEqual(settings.read_bytes() if settings.exists() else None, previous)

    def test_real_loader_replaces_only_vigil_and_can_return_to_core(self):
        from render.asset_registry import AssetResolver
        descriptor = PACK / 'visual-pack.json'
        self.assertTrue(descriptor.is_file(), 'Vigil prototype pack is not installed')
        resolver = AssetResolver(ROOT)
        original = resolver.resolve('imperial:corvette')
        sibling = resolver.resolve('imperial:frigate')
        self.assertEqual(resolver.activate_packs([descriptor], pack_root=PACK_ROOT),
                         ('prototype:vigil',), resolver.diagnostics)
        replacement = resolver.resolve('imperial:corvette')
        self.assertEqual(replacement.asset, 'prototype:imperial/vigil')
        self.assertNotEqual(original.revision, replacement.revision)
        self.assertEqual(resolver.resolve('imperial:frigate').revision, sibling.revision)
        self.assertEqual([r['binding'] for r in json.loads(descriptor.read_text())['content']['replaces']],
                         ['imperial:corvette'])
        payload = json.loads((PACK / 'assets/models/vigil.mesh.json').read_text())
        self.assertLessEqual(payload['triangle_count'], 11888)
        self.assertEqual(set(payload['batches']), {'base', 'dark', 'trim', 'accent', 'lit', 'cool'})
        for role in payload['batches']:
            self.assertTrue(payload['batches'][role], role)
        self.assertGreaterEqual(payload['bounds'][1][2] - payload['bounds'][0][2], 91.4)
        manifest = json.loads((PACK / 'assets/models/manifests/vigil.json').read_text())
        self.assertNotIn('approval', manifest, 'A prototype must not inherit an old appearance approval')
        self.assertEqual(resolver.activate_packs([], pack_root=PACK_ROOT), ())
        self.assertEqual(resolver.resolve('imperial:corvette').revision, original.revision)
        self.assertEqual(hashlib.sha256((ROOT / 'assets/models/imperial_corvette.mesh.json').read_bytes()).hexdigest(),
                         'be894218b84c00b4c6f78c96a46df1cf69441b627fa75155df02be41f6c30d05')


if __name__ == '__main__':
    unittest.main()
