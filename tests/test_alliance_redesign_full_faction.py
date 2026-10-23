"""Complete actual Alliance catalogue coverage, shared resource ceiling, factory bindings."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class AllianceFullFactionTests(unittest.TestCase):
    def test_builder_covers_exactly_all_26_actual_bindings(self):
        from tools.art.build_alliance_redesign import ROWS
        scope=json.loads((ROOT/'artifacts/alliance-redesign/coverage.json').read_text())
        self.assertEqual(len(ROWS),26)
        self.assertEqual({'rebel:'+row[0] for row in ROWS},{r['binding'] for r in scope['rows']})
        self.assertEqual(len({row[0] for row in ROWS}),len(ROWS))

    def test_every_runtime_factory_subject_uses_the_actual_alliance_binding(self):
        from tools.art.build_alliance_redesign import ROWS
        from tools.render.verify_alliance_redesign import spawn_subject,subject_snapshot
        from game.graphics_benchmark import make_fixture
        fixture=make_fixture('four-player-close-v1')
        fixture.manager.state.players[0].faction='rebel'
        for kind,_,live,_ in ROWS:
            with self.subTest(kind=kind):
                fixture.manager.state.entities.clear()
                spawn_subject(fixture,kind,live)
                payload=subject_snapshot(fixture)
                self.assertEqual([r['binding'] for r in payload['instances']],['rebel:'+kind])
                self.assertEqual([r['binding'] for r in payload['assets']],['rebel:'+kind])

    def test_all_26_real_exports_load_with_unchanged_imperium_inside_combined_budget(self):
        from render.asset_registry import AssetResolver,MAX_PACK_SNAPSHOT_TRIANGLES,MAX_PACK_SNAPSHOT_BYTES
        from render.menus import DEFAULT_SETTINGS
        from tools.art.build_alliance_redesign import ROWS
        resolver=AssetResolver(ROOT)
        names=[name for name in DEFAULT_SETTINGS['visual_packs'] if name!='alliance-redesign']+['alliance-redesign']
        accepted=resolver.activate_packs([ROOT/'visual_packs'/p/'visual-pack.json' for p in names],pack_root=ROOT/'visual_packs')
        self.assertIn('prototype:alliance_redesign',accepted,resolver.diagnostics)
        descriptor=json.loads((ROOT/'visual_packs/alliance-redesign/visual-pack.json').read_text())
        self.assertEqual(len(descriptor['content']['replaces']),26)
        allocation=json.loads((ROOT/'artifacts/alliance-redesign/triangle-budget-plan.json').read_text())
        total_triangles=0;total_bytes=0
        for name in names:
            pack=ROOT/'visual_packs'/name
            metadata=json.loads((pack/'visual-pack.json').read_text())
            for row in metadata['content']['replaces']:
                manifest=json.loads((pack/row['manifest']).read_text())
                total_triangles+=manifest['budgets']['triangles']
                total_bytes+=manifest['files']['mesh']['bytes']
        # The Legions decision expands retained capacity, not these approved meshes.
        self.assertEqual(MAX_PACK_SNAPSHOT_TRIANGLES,360000)
        self.assertLessEqual(total_triangles,MAX_PACK_SNAPSHOT_TRIANGLES)
        self.assertLessEqual(total_bytes,MAX_PACK_SNAPSHOT_BYTES)
        for kind,_,_,_ in ROWS:
            with self.subTest(kind=kind):
                selected=resolver.resolve('rebel:'+kind)
                self.assertIsNotNone(selected)
                self.assertEqual(selected.asset,'prototype:alliance_redesign/'+kind)
                mesh=json.loads((ROOT/f'visual_packs/alliance-redesign/assets/models/{kind}.mesh.json').read_text())
                self.assertGreater(mesh['triangle_count'],1800)
                self.assertLessEqual(mesh['triangle_count'],allocation['per_binding_alliance_allocations'][kind])
                self.assertEqual(set(mesh['batches']),{'base','dark','trim','accent','lit','cool'})
                self.assertTrue(all(mesh['batches'].values()))

if __name__=='__main__':unittest.main()
