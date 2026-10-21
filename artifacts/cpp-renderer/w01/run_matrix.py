from pathlib import Path
import subprocess,sys,json
root=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01')
e=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-evidence')
viewer=root/'render_cpp/build-source-check/armada_viewer'
jobs=[('fleet-timing','fleet', ['--warmup','60','--frames','240','--no-overlay']),
 ('fleet','fleet',['--warmup','30','--frames','30','--no-overlay']),
 ('capital','fleet',['--warmup','30','--frames','30','--preset','2','--no-overlay']),
 ('station','fleet',['--warmup','30','--frames','30','--preset','3','--no-overlay']),
 ('catalogue','catalogue',['--warmup','30','--frames','30','--no-overlay']),
 ('capital-no-shadows','fleet',['--warmup','30','--frames','30','--preset','2','--no-overlay','--no-shadows']),
 ('controls','fleet',['--warmup','30','--frames','90','--exercise-controls'])]
for name,snap,extra in jobs:
 command=[str(viewer),'--snapshot',str(e/(snap+'.snap')),'--assets',str(root/'assets'),'--report',str(e/(name+'.json')),*extra]
 if name!='fleet-timing':command+=['--screenshot',str(e/(name+'.png'))]
 result=subprocess.run([sys.executable,str(e/'bounded.py'),'60',str(e/(name+'.log')),*command],cwd=root,capture_output=True,text=True)
 print(result.stdout.strip(),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
 d=json.loads((e/(name+'.json')).read_text())
 print(json.dumps(dict(name=name,backend=d['backend'],instances=d['instances'],meshes=d['unique_meshes'],wall=d['wall_frame'],gpu=d['gpu_frame'],inspection=d.get('inspection_binding'),controls=d['control_exercise'])),flush=True)
