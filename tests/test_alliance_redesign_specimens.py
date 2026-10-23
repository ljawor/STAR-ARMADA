"""First Alliance style specimens: real bounded replacements, not renderer stand-ins."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'visual_packs/alliance-redesign'

class AllianceRedesignSpecimenTests(unittest.TestCase):
    def test_two_real_specimens_load_with_existing_imperium_packs(self):
        from render.asset_registry import AssetResolver
        from render.menus import DEFAULT_SETTINGS
        descriptor=PACK/'visual-pack.json'
        self.assertTrue(descriptor.is_file(),'Alliance frigate and shipyard must be real loadable replacements')
        resolver=AssetResolver(ROOT)
        paths=[ROOT/'visual_packs'/name/'visual-pack.json' for name in DEFAULT_SETTINGS['visual_packs']
               if name!='alliance-redesign']+[descriptor]
        accepted=resolver.activate_packs(paths,pack_root=ROOT/'visual_packs')
        self.assertIn('prototype:alliance_redesign',accepted,resolver.diagnostics)
        for kind in ('frigate','shipyard'):
            with self.subTest(kind=kind):
                result=resolver.resolve('rebel:'+kind)
                self.assertIsNotNone(result)
                self.assertEqual(result.asset,'prototype:alliance_redesign/'+kind)
                mesh=json.loads((PACK/f'assets/models/{kind}.mesh.json').read_text())
                self.assertGreater(mesh['triangle_count'],6000)
                self.assertLessEqual(mesh['triangle_count'],11888)
                self.assertLess(len(mesh['vertices']),9500)
                self.assertEqual(set(mesh['batches']),{'base','dark','trim','accent','lit','cool'})
                self.assertTrue(all(mesh['batches'].values()))

    def test_original_alliance_and_imperium_meshes_masters_and_helpers_are_untouched(self):
        import subprocess
        changed=subprocess.check_output(['git','diff','--name-only',
            '805b2eccfd6bd7259a38abca0f5ff60b81e69f98','--','visual_packs','art/blender',
            'assets/models','tools/art/imperium_fleet_geometry.py','tools/art/alliance_common.py'],
            cwd=ROOT,text=True).splitlines()
        # New separate-pack files may appear after commit; no baseline file may change.
        old=set(subprocess.check_output(['git','ls-tree','-r','--name-only',
            '805b2eccfd6bd7259a38abca0f5ff60b81e69f98','--','visual_packs','art/blender',
            'assets/models','tools/art/imperium_fleet_geometry.py','tools/art/alliance_common.py'],
            cwd=ROOT,text=True).splitlines())
        self.assertEqual(sorted(old.intersection(changed)),[])

if __name__=='__main__':unittest.main()
