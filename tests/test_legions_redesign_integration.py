"""Legions scope, authorized resource guard, production ownership and actual exports."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class LegionsRedesignTests(unittest.TestCase):
    def test_resource_change_is_exactly_owner_authorized(self):
        from render.asset_registry import MAX_PACK_SNAPSHOT_TRIANGLES,MAX_PACK_SNAPSHOT_BYTES,MAX_VERTICES,MAX_TRIANGLES,MAX_BYTES
        authorization=json.loads((ROOT/'artifacts/legions-redesign/resource-budget-authorization.json').read_text())
        self.assertEqual(authorization['owner_response_verbatim'],'Approve the 360,000-triangle shared ceiling for the full Legions redesign')
        self.assertEqual(MAX_PACK_SNAPSHOT_TRIANGLES,360000)
        self.assertEqual((MAX_PACK_SNAPSHOT_BYTES,MAX_VERTICES,MAX_TRIANGLES,MAX_BYTES),(32000000,10000,12000,2000000))

    def test_exact_complete_existing_scope_and_valid_factory_ids(self):
        from tools.art.legions_redesign_catalogue import ROWS,TRIANGLE_LIMITS,SHIP_KINDS
        from render_bridge.protocol import decode
        existing={r['binding'] for r in decode((ROOT/'assets/cpp/catalogue.snap').read_bytes()).payload['assets'] if r['binding'].startswith('confederacy:')}
        self.assertEqual(len(ROWS),26)
        self.assertEqual({'confederacy:'+r[0] for r in ROWS},existing)
        self.assertEqual(set(TRIANGLE_LIMITS),{r[0] for r in ROWS})
        self.assertEqual(len(SHIP_KINDS),10)
        self.assertLessEqual(223872+sum(TRIANGLE_LIMITS.values()),360000)
        from tools.render.verify_legions_redesign import spawn_subject,subject_snapshot
        from tools.render import dump_snapshot
        from render import menus
        from game.graphics_benchmark import make_fixture
        fixture=make_fixture('four-player-close-v1')
        fixture.manager.state.players[0].faction='confederacy'
        settings=dict(menus.DEFAULT_SETTINGS,visual_packs=[n for n in menus.DEFAULT_SETTINGS['visual_packs'] if n!='legions-redesign'])
        with patch.object(dump_snapshot,'_default_selection',return_value=settings):
            for kind,template,live,_ in ROWS:
                with self.subTest(kind=kind):
                    fixture.manager.state.entities.clear()
                    spawn_subject(fixture,kind,live)
                    payload=subject_snapshot(fixture)
                    self.assertEqual([r['binding'] for r in payload['instances']],['confederacy:'+kind])
                    self.assertEqual([r['binding'] for r in payload['assets']],['confederacy:'+kind])
                    self.assertEqual(payload['assets'][0]['path'],'assets/models/'+template+'.mesh.json')
                    self.assertEqual(payload['metadata']['factions'][0],'confederacy')
                    self.assertNotIn('combat_mix_per_player',payload['metadata'])

    def test_all_exports_are_real_strictly_accepted_and_inside_combined_budget(self):
        from render.asset_registry import AssetResolver,MAX_PACK_SNAPSHOT_TRIANGLES,MAX_PACK_SNAPSHOT_BYTES
        from render.menus import DEFAULT_SETTINGS
        from tools.art.legions_redesign_catalogue import ROWS,TRIANGLE_LIMITS
        names=[p for p in DEFAULT_SETTINGS['visual_packs'] if p!='legions-redesign']+['legions-redesign']
        resolver=AssetResolver(ROOT)
        accepted=resolver.activate_packs([ROOT/'visual_packs'/p/'visual-pack.json' for p in names],pack_root=ROOT/'visual_packs')
        self.assertEqual(len(accepted),len(names),resolver.diagnostics)
        triangles=0;size=0
        for name in names:
            pack=ROOT/'visual_packs'/name
            for row in json.loads((pack/'visual-pack.json').read_text())['content']['replaces']:
                m=json.loads((pack/row['manifest']).read_text())
                triangles+=m['budgets']['triangles'];size+=m['files']['mesh']['bytes']
        self.assertLessEqual(triangles,MAX_PACK_SNAPSHOT_TRIANGLES)
        self.assertLessEqual(size,MAX_PACK_SNAPSHOT_BYTES)
        for kind,_,_,_ in ROWS:
            with self.subTest(kind=kind):
                selected=resolver.resolve('confederacy:'+kind)
                self.assertEqual(selected.asset,'prototype:legions_redesign/'+kind)
                mesh=json.loads((ROOT/f'visual_packs/legions-redesign/assets/models/{kind}.mesh.json').read_text())
                self.assertGreater(mesh['triangle_count'],1800)
                self.assertLessEqual(mesh['triangle_count'],TRIANGLE_LIMITS[kind])
                self.assertEqual(set(mesh['batches']),{'base','dark','trim','accent','lit','cool'})
                self.assertTrue(all(mesh['batches'].values()))

if __name__=='__main__':unittest.main()
