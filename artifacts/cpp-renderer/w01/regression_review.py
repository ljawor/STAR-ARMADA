import json,struct,subprocess,sys
from pathlib import Path
p=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-evidence');r=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01')
b=bytearray((p/'fleet.snap').read_bytes());struct.pack_into('<H',b,10,2);(p/'world-shaped-ui.snap').write_bytes(b)
mode=sys.argv[1]; outcomes=[]
cases=[('kind-confusion',['--snapshot',str(p/'world-shaped-ui.snap'),'--validate-only'],3,None),('short-capture',['--snapshot',str(p/'fleet.snap'),'--frames','1','--warmup','0','--no-overlay','--screenshot',str(p/('short-'+mode+'.png'))],0,p/('short-'+mode+'.png')),('device-error',['--snapshot',str(p/'fleet.snap'),'--shaders',str(p/'no-such-shaders'),'--frames','1'],4,None)]
for name,args,expected,shot in cases:
 command=[str(r/'render_cpp/build/armada_viewer'),'--assets',str(r/'assets'),*args]
 result=subprocess.run([sys.executable,str(p/'bounded.py'),'45',str(p/(name+'-'+mode+'.log')),*command],cwd=r,capture_output=True,text=True)
 receipt=json.loads(result.stdout.strip().splitlines()[-1]);passed=receipt['exit_code']==expected and (shot is None or shot.is_file())
 outcomes.append(dict(case=name,expected_exit=expected,observed_exit=receipt['exit_code'],capture_exists=shot.is_file() if shot else None,passed=passed))
print(json.dumps(outcomes,indent=2));(p/('review-regressions-'+mode+'.json')).write_text(json.dumps(outcomes,indent=2)+'\n')
assert all(x['passed'] for x in outcomes),'W01 regression checks failed'
