"""All remaining Imperium ship bindings, without moving accepted neighbours."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BINDINGS=('bomber','frigate','cruiser','battleship','supercapital','colonizer','convoy')
PACK=ROOT/'visual_packs/imperium-fleet-prototypes'

class RemainingImperiumFleetTests(unittest.TestCase):
    def test_complete_fleet_pack_replaces_only_the_seven_remaining_bindings(self):
        from render.asset_registry import AssetResolver
        import game.core.manager
        from render.menus import DEFAULT_SETTINGS
        descriptor=PACK/'visual-pack.json'
        self.assertTrue(descriptor.is_file(),'Remaining seven Imperium models have no real loadable pack yet')
        defaults=[ROOT/'visual_packs'/name/'visual-pack.json' for name in DEFAULT_SETTINGS['visual_packs']
                  if name!='imperium-fleet-prototypes']
        resolver=AssetResolver(ROOT)
        resolver.activate_packs(defaults,pack_root=ROOT/'visual_packs')
        before={key:resolver.resolve(key).revision for key in
                ['imperial:corvette','imperial:fighter','imperial:constructor',
                 'imperial:command_station','imperial:shipyard','imperial:mining_station',
                 'imperial:research_station','imperial:defense_platform','imperial:sensor_station',
                 'imperial:trade_station','imperial:fighter_platform','imperial:repair_dock',
                 'imperial:energy_relay','rebel:frigate','confederacy:cruiser','syndicate:corvette']}
        core={kind:resolver.resolve('imperial:'+kind).revision for kind in BINDINGS}
        activated=resolver.activate_packs(defaults+[descriptor],pack_root=ROOT/'visual_packs')
        self.assertIn('prototype:imperium_fleet',activated,resolver.diagnostics)
        content=json.loads(descriptor.read_text())['content']['replaces']
        self.assertEqual({row['binding'] for row in content},{'imperial:'+k for k in BINDINGS})
        self.assertEqual(len(content),len(BINDINGS))
        for kind in BINDINGS:
            with self.subTest(kind=kind):
                selected=resolver.resolve('imperial:'+kind)
                self.assertEqual(selected.asset,'prototype:imperial/'+kind)
                self.assertNotEqual(selected.revision,core[kind])
                entry=next(row for row in content if row['binding']=='imperial:'+kind)
                manifest=json.loads((PACK/entry['manifest']).read_text())
                raw=(PACK/manifest['files']['mesh']['path']).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest['files']['mesh']['sha256'])
                model=json.loads(raw)
                self.assertEqual(set(model['batches']),{'base','dark','trim','accent','lit','cool'})
                self.assertTrue(all(model['batches'].values()))
                self.assertGreater(model['triangle_count'],1800)
                self.assertLessEqual(model['triangle_count'],6000 if kind=='bomber' else 11888)
                self.assertLess(len(model['vertices']),9500)
                self.assertLess(len(raw),2000000)
        for key,revision in before.items():self.assertEqual(resolver.resolve(key).revision,revision,key)
        resolver.activate_packs(defaults,pack_root=ROOT/'visual_packs')
        for kind,revision in core.items():self.assertEqual(resolver.resolve('imperial:'+kind).revision,revision)

if __name__=='__main__':unittest.main()
