"""Approved fleet is available through ordinary main.py settings, not review flags."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class ImperiumGameActivationTests(unittest.TestCase):
    def test_fresh_main_settings_enable_the_approved_remaining_fleet(self):
        import game.core
        from render import menus,asset_selection
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(menus,'SETTINGS_PATH',str(Path(folder)/'settings.json')):
                settings=menus.load_settings()
        self.assertIn('imperium-fleet-prototypes',settings['visual_packs'])
        try:
            report=asset_selection.configure_from_settings(settings)
            self.assertTrue(report['coverage']['ok'])
            effective={r['binding']:r for r in report['effective_bindings']}
            for kind in ('bomber','frigate','cruiser','battleship','supercapital','colonizer','convoy'):
                self.assertEqual(effective['imperial:'+kind]['pack_id'],'prototype:imperium_fleet')
        finally:asset_selection.configure({})

    def test_existing_previous_shipped_pack_selection_migrates_without_other_changes(self):
        import game.core
        from render import menus
        from tools.play_imperium_fleet import ACCEPTED_PACKS
        saved=dict(menus.DEFAULT_SETTINGS,visual_packs=list(ACCEPTED_PACKS),music_volume=.25,language='pl')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';path.write_text(json.dumps(saved))
            with patch.object(menus,'SETTINGS_PATH',str(path)):loaded=menus.load_settings()
        self.assertEqual(loaded['visual_packs'],[*ACCEPTED_PACKS,'imperium-fleet-prototypes','alliance-redesign'])
        self.assertEqual(loaded['music_volume'],.25);self.assertEqual(loaded['language'],'pl')
        self.assertEqual(len(loaded['visual_packs']),len(set(loaded['visual_packs'])))

    def test_normal_native_shipped_catalogue_contains_the_approved_fleet_meshes(self):
        from render_bridge.protocol import decode
        from render_bridge.cpp_window import ensure_snapshot
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            path=ensure_snapshot(str(root),folder)
        self.assertEqual(Path(path),root/'assets/cpp/catalogue.snap')
        payload=decode(Path(path).read_bytes()).payload
        assets={row['binding']:row for row in payload['assets']}
        approved=json.loads((root/'artifacts/imperium-fleet/OWNER_REVIEW.json').read_text())['assets']
        for row in approved:
            with self.subTest(binding=row['binding']):
                self.assertEqual(assets[row['binding']]['sha256'],row['mesh_sha256'])
                self.assertEqual(assets[row['binding']]['path'],row['mesh'])

    def test_explicit_custom_selection_is_not_overwritten_or_reordered(self):
        import game.core
        from render import menus
        for packs in ([],['custom-first','custom-second']):
            with self.subTest(packs=packs),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'settings.json';path.write_text(json.dumps({'visual_packs':packs}))
                with patch.object(menus,'SETTINGS_PATH',str(path)):loaded=menus.load_settings()
                self.assertEqual(loaded['visual_packs'],packs)

if __name__=='__main__':unittest.main()
