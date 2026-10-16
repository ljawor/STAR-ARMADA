"""Protected reproducible seals, inspection, camera plan and real-GL captures."""
import sys,os,json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).parent
LIVE=Path('/Users/lukaszjawor/Downloads/Project/STAR-ARMADA')
USER=Path.home()/'Library/Application Support/STAR ARMADA'
PY=LIVE/'.venv/bin/python'
def run(label,mode,peer=None,plan=None,compare=None):
    out=ROOT/(label+'-'+mode)
    cmd=[str(PY),str(ROOT/'capture_slice.py'),'--source',str(ROOT/(label+'-source')),'--output',str(out),'--mode',mode,'--ticks','180']
    if mode!='seal-source':cmd+=['--seal',str(ROOT/(label+'-seal-source/source-manifest.json'))]
    if peer:cmd+=['--geometry-peer',str(ROOT/(peer+'-inspect-source/geometry.json'))]
    if plan:cmd+=['--camera-plan',str(ROOT/(plan+'-plan-cameras/camera-plan.json'))]
    if compare:cmd+=['--compare',str(ROOT/(compare+'-baseline-capture'))]
    profile='(version 1)(allow default)'+''.join('(deny file-write* (subpath '+json.dumps(str(p))+'))' for p in (LIVE,USER))
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');env.pop('SDL_VIDEODRIVER',None)
    with (ROOT/(out.name+'.log')).open('w') as f:
        result=subprocess.run(['sandbox-exec','-p',profile,*cmd],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    print(out.name,result.returncode,flush=True)
    if result.returncode: print((ROOT/(out.name+'.log')).read_text());sys.exit(result.returncode)
if __name__=='__main__':
    if sys.argv[1]=='before':
        run('baseline','seal-source');run('baseline','inspect-source');run('baseline','plan-cameras','baseline');run('baseline','baseline-capture','baseline','baseline')
    elif sys.argv[1]=='paired':
        run('candidate','seal-source');run('candidate','inspect-source');run('candidate','plan-cameras','baseline')
        # Preserve the actual pre-implementation captures; final control gets the union-bound plan.
        # Prior pre-implementation captures already preserved.
        run('baseline','baseline-capture','candidate','candidate');run('candidate','candidate-capture','baseline','candidate','baseline')
