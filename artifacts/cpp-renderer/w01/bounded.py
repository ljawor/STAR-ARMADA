import json,os,signal,subprocess,sys,time
from pathlib import Path
seconds=float(sys.argv[1]); log=Path(sys.argv[2]); command=sys.argv[3:]
start=time.monotonic(); log.parent.mkdir(parents=True,exist_ok=True)
with log.open('w') as f:
 p=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 timedout=False
 try: result=p.wait(timeout=seconds)
 except subprocess.TimeoutExpired:
  timedout=True; os.killpg(p.pid,signal.SIGKILL);result=p.wait()
r=dict(command=command,pid=p.pid,exit_code=result,timed_out=timedout,elapsed_seconds=time.monotonic()-start,process_terminated=p.poll() is not None,log=str(log))
log.with_suffix(log.suffix+'.receipt.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r));sys.exit(124 if timedout else result)
