"""The reworked Syndicate fleet must be core assets: a plain main.py launch draws them.

No pack, no review switch. These tests load the catalogue exactly as the game does and
check that every one of the 23 reworked bindings resolves to its new mesh, that the
mesh stays inside the envelope its binding was approved at, and that the manifest is
honest about approval state.
"""
import hashlib
import json
import unittest
from pathlib import Path

from render.asset_registry import AssetResolver

ROOT = Path(__file__).resolve().parents[1]
STEMS = ('corvette', 'frigate', 'cruiser', 'convoy', 'colonizer', 'constructor', 'fighter',
         'command_station', 'defense_platform', 'energy_relay', 'fighter_platform',
         'mining_station', 'repair_dock', 'research_station', 'sensor_station', 'shipyard',
         'trade_station', 'attack_satellite', 'defense_satellite', 'planet_extractor',
         'planet_pulsar_cannon', 'planet_shield_generator', 'planet_trade_hub')


def revision(asset, mesh_sha):
    return hashlib.sha256(f'{asset}\nmesh:{mesh_sha}'.encode()).hexdigest()


def envelopes():
    data = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
    return {row['binding']: row['envelope'] for row in data['bindings'] if row.get('envelope')}


class SyndicateFleetReworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boxes = envelopes()
        cls.resolver = AssetResolver(ROOT)
        cls.diagnostics = list(cls.resolver.diagnostics)

    def test_catalogue_loads_without_rejections(self):
        rejected = [entry for entry in self.diagnostics
                    if str(entry.get('code', '')).startswith('E_')]
        self.assertEqual(rejected, [])

    def test_no_visual_pack_is_required(self):
        self.assertEqual(self.resolver.pack_bindings(), [])
        self.assertFalse((ROOT / 'visual_packs/syndicate-fleet-prototypes').exists())

    def test_every_reworked_binding_is_core_and_resolves(self):
        for stem in STEMS:
            binding = 'syndicate:' + stem
            asset = self.resolver.resolve(binding)
            self.assertEqual(asset.asset, 'core:syndicate/' + stem, binding)
            self.assertFalse(asset.pack_id, binding)
            self.assertEqual(sorted(asset.mesh), ['accent', 'base', 'cool', 'dark', 'lit', 'trim'])

    def test_manifests_use_the_loader_revision_recipe(self):
        for stem in STEMS:
            manifest = json.loads(self.manifest_path(stem).read_text(encoding='utf-8'))
            mesh = manifest['files']['mesh']
            digest = hashlib.sha256((ROOT / mesh['path']).read_bytes()).hexdigest()
            self.assertEqual(mesh['sha256'], digest, stem)
            self.assertEqual(manifest['revision'], revision(manifest['asset'], digest), stem)
            self.assertEqual(len(mesh['sha256']), 64)

    def test_meshes_stay_inside_the_approved_envelopes(self):
        for stem in STEMS:
            binding = 'syndicate:' + stem
            manifest = json.loads(self.manifest_path(stem).read_text(encoding='utf-8'))
            box = self.boxes[binding]
            lo, hi = manifest['bounds']['min'], manifest['bounds']['max']
            for axis in range(3):
                self.assertGreaterEqual(lo[axis], box['min'][axis] - 1e-6, (binding, axis))
                self.assertLessEqual(hi[axis], box['max'][axis] + 1e-6, (binding, axis))

    def test_payload_identity_matches_its_manifest(self):
        for stem in STEMS:
            payload = json.loads((ROOT / 'assets/models' /
                                  f'syndicate_{stem}.mesh.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['asset'], 'core:syndicate/' + stem)
            self.assertGreater(payload['triangle_count'], 500, stem)
            self.assertEqual(sorted(payload['batches']),
                             ['accent', 'base', 'cool', 'dark', 'lit', 'trim'])

    def test_approval_state_is_honest(self):
        for stem in STEMS:
            manifest = json.loads(self.manifest_path(stem).read_text(encoding='utf-8'))
            approval = manifest['approval']
            self.assertTrue(approval['reviewed_evidence'], stem)
            self.assertEqual(approval['status'], 'approved', stem)
            self.assertEqual(approval['decided_by'], 'owner', stem)
            self.assertEqual(approval['reviewed_revision'], manifest['revision'], stem)
            # decision_id names the decision that approved the unchanged envelope, and the
            # receipt pins the whole manifest; the loader verifies both.
            receipts = json.loads((ROOT / 'assets/models/approval-receipts.json')
                                  .read_text(encoding='utf-8'))
            self.assertIn(manifest['asset'], receipts['receipts'], stem)

    def test_shipped_native_catalogue_matches_the_meshes(self):
        """The native window verifies each mesh against this file's SHA256.

        A reworked mesh with a stale catalogue stops the renderer on the first frame
        ('mesh SHA256 mismatch') and the match is left with no legacy fallback, so the
        shipped catalogue has to be current in the same commit as the meshes.
        """
        raw = (ROOT / 'assets/cpp/catalogue.snap').read_bytes()
        payload = json.loads(raw[raw.index(b'{'):raw.rindex(b'}') + 1])
        records = {record['binding']: record for record in payload['assets']}
        for binding, record in records.items():
            digest = hashlib.sha256((ROOT / record['path']).read_bytes()).hexdigest()
            self.assertEqual(record['sha256'], digest, binding)
        for stem in STEMS:
            self.assertIn('syndicate:' + stem, records)

    @staticmethod
    def manifest_path(stem):
        for path in sorted((ROOT / 'assets/models/manifests').glob('*.json')):
            if json.loads(path.read_text(encoding='utf-8')).get('asset') == \
                    f'core:syndicate/{stem}':
                return path
        raise AssertionError('no manifest for ' + stem)


if __name__ == '__main__':
    unittest.main()
