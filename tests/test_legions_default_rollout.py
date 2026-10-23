"""Approved Legions delivery must work through fresh and historical normal settings."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class LegionsDefaultRolloutTests(unittest.TestCase):
    def load(self,saved=None):
        from render import menus
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            if saved is not None:path.write_text(json.dumps(saved))
            with patch.object(menus,'SETTINGS_PATH',str(path)):
                loaded=menus.load_settings()
                menus.save_settings(loaded)
                again=menus.load_settings()
            self.assertEqual(again,loaded)
            return loaded

    def test_fresh_settings_resolve_all_26_approved_legions_meshes(self):
        from render import menus,asset_selection
        from tools.art.legions_redesign_catalogue import ROWS
        loaded=self.load()
        self.assertEqual(len(loaded['visual_packs']),16)
        self.assertEqual(loaded['visual_packs'],menus.DEFAULT_SETTINGS['visual_packs'])
        self.assertEqual(loaded['visual_packs'].count('legions-redesign'),1)
        try:
            report=asset_selection.configure_from_settings(loaded)
            effective={r['binding']:r for r in report['effective_bindings']}
            for kind,_,_,_ in ROWS:
                with self.subTest(kind=kind):
                    self.assertEqual(effective['confederacy:'+kind]['pack_id'],'prototype:legions_redesign')
            self.assertEqual(sum(b.startswith('imperial:') for b in effective),20)
            self.assertEqual(sum(b.startswith('rebel:') for b in effective),26)
        finally:asset_selection.configure({})

    def test_all_three_historical_cohorts_migrate_without_unrelated_changes(self):
        from render import menus
        from tools.play_imperium_fleet import ACCEPTED_PACKS
        old13=list(ACCEPTED_PACKS)
        old14=[*old13,'imperium-fleet-prototypes']
        old15=[*old14,'alliance-redesign']
        for cohort in (old13,old14,old15):
            with self.subTest(cohort=len(cohort)):
                saved={**menus.DEFAULT_SETTINGS,'visual_packs':cohort,'music_volume':.23,'language':'pl',
                       'resolution':'auto','fullscreen':False,'opaque_mod_preference':{'x':[1,2]}}
                loaded=self.load(saved)
                self.assertEqual(len(loaded['visual_packs']),16)
                self.assertEqual(loaded['visual_packs'],menus.DEFAULT_SETTINGS['visual_packs'])
                self.assertEqual({k:v for k,v in loaded.items() if k!='visual_packs'},
                                 {k:v for k,v in saved.items() if k!='visual_packs'})

    def test_custom_empty_reordered_subset_extended_and_current_lists_stay_exact(self):
        from render import menus
        from tools.play_imperium_fleet import ACCEPTED_PACKS
        for cohort in (list(ACCEPTED_PACKS),[*ACCEPTED_PACKS,'imperium-fleet-prototypes'],
                       [*ACCEPTED_PACKS,'imperium-fleet-prototypes','alliance-redesign']):
            for packs in ([],list(reversed(cohort)),cohort[1:],cohort+['custom-last'],
                          ['custom-first']+cohort,['custom-only'],
                          list(menus.DEFAULT_SETTINGS['visual_packs'])):
                with self.subTest(cohort=len(cohort),packs=packs):
                    self.assertEqual(self.load({'visual_packs':packs})['visual_packs'],packs)

    def test_owner_approval_pins_all_current_runtime_meshes(self):
        coverage=json.loads((ROOT/'artifacts/legions-redesign/coverage.json').read_text())
        approved=json.loads((ROOT/'artifacts/legions-redesign/OWNER_REVIEW.json').read_text())
        self.assertEqual(approved['owner_words_verbatim'],'Looking good. Weel done. Merge please')
        self.assertTrue(approved['appearance_approved'])
        self.assertTrue(approved['merge_authorized'])
        self.assertFalse(approved['release_or_tag_authorized'])
        self.assertEqual(set(approved['runtime_sha256']),{r['binding'] for r in coverage['rows']})
        for row in coverage['rows']:
            with self.subTest(binding=row['binding']):
                self.assertEqual(approved['runtime_sha256'][row['binding']],
                                 hashlib.sha256((ROOT/row['replacement_mesh']).read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
