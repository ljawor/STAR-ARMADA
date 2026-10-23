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

if __name__=='__main__':unittest.main()
