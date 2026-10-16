import subprocess,json,os,sys
from pathlib import Path
S=Path(__file__).parent;R=Path('/Users/lukaszjawor/Downloads/Project/STAR-ARMADA');U=Path.home()/'Library/Application Support/STAR ARMADA'
PROFILE='(version 1)(allow default)'+''.join('(deny file-write* (subpath '+json.dumps(str(x))+'))' for x in [R,U])
def run(label,mode,peer,plan=None,compare=None):
    out=S/(label+'-extra-'+mode)
    cmd=[str(R/'.venv/bin/python'),str(S/'capture_extra.py'),'--source',str(S/(label+'-source')),'--output',str(out),'--mode',mode,'--seal',str(S/(label+'-seal-source/source-manifest.json')),'--geometry-peer',str(S/(peer+'-inspect-source/geometry.json'))]
    if plan:cmd+=['--camera-plan',str(S/(plan+'-extra-plan-cameras/camera-plan.json'))]
    if compare:cmd+=['--compare',str(S/(compare+'-extra-baseline-capture'))]
    with (S/(out.name+'.log')).open('w') as f: result=subprocess.run(['sandbox-exec','-p',PROFILE,*cmd],cwd=S,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=f,stderr=subprocess.STDOUT)
    print(out.name,result.returncode,flush=True)
    if result.returncode: print((S/(out.name+'.log')).read_text());raise SystemExit(result.returncode)
if __name__=='__main__':
    run('candidate','plan-cameras','baseline');run('baseline','baseline-capture','candidate','candidate');run('candidate','candidate-capture','baseline','candidate','baseline')
