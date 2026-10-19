"""Run a command with an enforced process-group deadline, retaining full output."""
import argparse, json, os, signal, subprocess, sys, time
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--seconds',type=float,required=True); p.add_argument('--log',type=Path,required=True); p.add_argument('command',nargs=argparse.REMAINDER); a=p.parse_args()
command=a.command[1:] if a.command[:1]==['--'] else a.command
assert command and a.seconds>0
start=time.monotonic(); timed_out=False
env=dict(os.environ,PYTHONPATH='tests')
a.log.parent.mkdir(parents=True,exist_ok=True)
with a.log.open('wb') as output:
 child=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,start_new_session=True,env=env)
 try: code=child.wait(timeout=a.seconds)
 except subprocess.TimeoutExpired:
  timed_out=True; os.killpg(child.pid,signal.SIGKILL); code=child.wait()
receipt={'command':command,'pid':child.pid,'exit_code':code,'timed_out':timed_out,'deadline_seconds':a.seconds,'elapsed_seconds':round(time.monotonic()-start,3),'log':str(a.log)}
a.log.with_suffix(a.log.suffix+'.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
sys.exit(124 if timed_out else code)
