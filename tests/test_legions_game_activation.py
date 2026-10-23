"""The owner's ordinary native launch must use all 26 actual Legions exports."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='186903ae05aa9bd43d7e299fdc248be7cca42fd5'

class LegionsGameActivationTests(unittest.TestCase):
    def test_production_native_catalogue_uses_all_26_redesigns_without_unrelated_changes(self):
        from render_bridge.cpp_window import ensure_snapshot
        from render_bridge.protocol import decode
        from tools.art.legions_redesign_catalogue import ROWS
        with tempfile.TemporaryDirectory() as folder:
            path=Path(ensure_snapshot(str(ROOT),folder))
        self.assertEqual(path,ROOT/'assets/cpp/catalogue.snap')
        payload=decode(path.read_bytes()).payload
        old=decode(subprocess.check_output(['git','show',BASE+':assets/cpp/catalogue.snap'],cwd=ROOT)).payload
        before={r['binding']:r for r in old['assets']};after={r['binding']:r for r in payload['assets']}
        self.assertEqual(set(before),set(after))
        changed={b for b in before if before[b]!=after[b]}
        self.assertEqual(changed,{'confederacy:'+r[0] for r in ROWS})
        for kind,_,_,_ in ROWS:
            mesh=ROOT/f'visual_packs/legions-redesign/assets/models/{kind}.mesh.json'
            with self.subTest(kind=kind):
                self.assertEqual(after['confederacy:'+kind]['path'],str(mesh.relative_to(ROOT)))
                self.assertEqual(after['confederacy:'+kind]['sha256'],hashlib.sha256(mesh.read_bytes()).hexdigest())
        for data in (old,payload):
            data.pop('assets');data['metadata'].pop('visual_selection',None)
        self.assertEqual(old,payload)

if __name__=='__main__':unittest.main()
