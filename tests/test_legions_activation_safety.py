"""Activation write guards must survive -O and recover from partial I/O failure."""
import os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class LegionsActivationSafetyTests(unittest.TestCase):
    def test_optimized_python_rejects_unrelated_scene_change(self):
        code='''
from pathlib import Path
from unittest.mock import patch
from render_bridge.protocol import decode,encode,WORLD
from tools.art import activate_legions_review as activation
path=Path('assets/cpp/catalogue.snap')
original=decode(path.read_bytes()).payload
import copy
changed=copy.deepcopy(original)
changed['camera']['distance']+=1
before=encode(changed,kind=WORLD,tick=0,frame_index=0)
with patch('tools.render.dump_snapshot.build_catalogue',return_value=original):
    try:activation.candidate_catalogue(before)
    except ValueError:print('OPTIMIZED_GUARD_OK')
    else:raise SystemExit(5)
'''
        result=subprocess.run([sys.executable,'-O','-c',code],cwd=ROOT,capture_output=True,text=True,timeout=30,env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('OPTIMIZED_GUARD_OK',result.stdout)

    def test_second_write_failure_restores_both_original_files(self):
        from tools.art import activate_legions_review as activation
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'settings.json';b=Path(folder)/'catalogue.snap'
            a.write_bytes(b'old-settings');b.write_bytes(b'old-catalogue')
            real=activation.atomic_write
            calls=0
            def injected(path,raw):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('injected second-target failure')
                return real(path,raw)
            with patch.object(activation,'atomic_write',side_effect=injected):
                with self.assertRaisesRegex(OSError,'injected second-target failure'):
                    activation.apply_transaction({a:b'new-settings',b:b'new-catalogue'})
            self.assertEqual(a.read_bytes(),b'old-settings')
            self.assertEqual(b.read_bytes(),b'old-catalogue')
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['catalogue.snap','settings.json'])

    def test_successful_transaction_reads_back_exact_new_bytes(self):
        from tools.art import activate_legions_review as activation
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_bytes(b'old-a');b.write_bytes(b'old-b')
            activation.apply_transaction({a:b'new-a',b:b'new-b'})
            self.assertEqual((a.read_bytes(),b.read_bytes()),(b'new-a',b'new-b'))

if __name__=='__main__':unittest.main()
