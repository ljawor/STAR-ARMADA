"""The native catalogue used by ordinary main.py must contain the entire reviewed faction."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class AllianceGameCatalogueTests(unittest.TestCase):
    def test_real_native_entry_catalogue_contains_all_26_alliance_replacements(self):
        from render_bridge.cpp_window import ensure_snapshot
        from render_bridge.protocol import decode
        from tools.art.alliance_redesign_catalogue import ROWS
        with tempfile.TemporaryDirectory() as directory:
            actual=Path(ensure_snapshot(str(ROOT),directory))
            self.assertEqual(actual,ROOT/'assets/cpp/catalogue.snap')
            payload=decode(actual.read_bytes()).payload
        assets={row['binding']:row for row in payload['assets']}
        for kind,_,_,_ in ROWS:
            with self.subTest(kind=kind):
                relative=f'visual_packs/alliance-redesign/assets/models/{kind}.mesh.json'
                self.assertEqual(assets['rebel:'+kind]['path'],relative)
                self.assertEqual(assets['rebel:'+kind]['sha256'],hashlib.sha256((ROOT/relative).read_bytes()).hexdigest())

    def test_alliance_config_keeps_all_existing_imperium_choices(self):
        from render import asset_selection
        from render.menus import DEFAULT_SETTINGS
        from tools.art.alliance_redesign_catalogue import ROWS
        settings={**DEFAULT_SETTINGS,'visual_packs':list(DEFAULT_SETTINGS['visual_packs'])}
        if 'alliance-redesign' not in settings['visual_packs']:
            settings['visual_packs'].append('alliance-redesign')
        try:
            report=asset_selection.configure(settings,asset_root=ROOT,pack_root=ROOT/'visual_packs')
            by_binding={r['binding']:r for r in report['effective_bindings']}
            for kind,_,_,_ in ROWS:
                with self.subTest(kind=kind):
                    self.assertEqual(by_binding['rebel:'+kind]['pack_id'],'prototype:alliance_redesign')
            self.assertEqual(sum(r['binding'].startswith('imperial:') for r in by_binding.values()),20)
        finally:
            asset_selection.configure({})

class AllianceDefaultRolloutTests(unittest.TestCase):
    def load(self,saved=None):
        from unittest.mock import patch
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

    def test_fresh_defaults_enable_alliance_and_all_26_approved_meshes(self):
        from render import menus,asset_selection
        settings=self.load()
        self.assertIn('alliance-redesign',settings['visual_packs'])
        self.assertEqual(settings['visual_packs'],menus.DEFAULT_SETTINGS['visual_packs'])
        try:
            report=asset_selection.configure_from_settings(settings)
            alliance=[r for r in report['effective_bindings'] if r['pack_id']=='prototype:alliance_redesign']
            self.assertEqual(len(alliance),26)
        finally:asset_selection.configure({})

    def test_both_historical_shipped_cohorts_migrate_preserving_preferences(self):
        from render import menus
        from tools.play_imperium_fleet import ACCEPTED_PACKS
        for cohort in (list(ACCEPTED_PACKS),[*ACCEPTED_PACKS,'imperium-fleet-prototypes']):
            with self.subTest(cohort=len(cohort)):
                saved={**menus.DEFAULT_SETTINGS,'visual_packs':cohort,'music_volume':.23,'language':'pl',
                       'resolution':'auto','fullscreen':False,'opaque_mod_preference':{'x':[1,2]}}
                loaded=self.load(saved)
                self.assertEqual(loaded['visual_packs'],menus.DEFAULT_SETTINGS['visual_packs'])
                self.assertEqual(len(loaded['visual_packs']),15)
                self.assertEqual({k:v for k,v in loaded.items() if k!='visual_packs'},
                                 {k:v for k,v in saved.items() if k!='visual_packs'})

    def test_custom_order_subset_extension_empty_and_current_selection_are_preserved(self):
        from render import menus
        from tools.play_imperium_fleet import ACCEPTED_PACKS
        previous=[*ACCEPTED_PACKS,'imperium-fleet-prototypes']
        for packs in ([],list(reversed(previous)),previous[:-2],previous+['custom-last'],
                      ['custom-first']+previous,['custom-only'],list(menus.DEFAULT_SETTINGS['visual_packs'])):
            with self.subTest(packs=packs):
                self.assertEqual(self.load({'visual_packs':packs})['visual_packs'],packs)

if __name__=='__main__':unittest.main()
