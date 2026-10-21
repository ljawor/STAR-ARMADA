from pathlib import Path
import sys,json,subprocess,hashlib,shutil
from PIL import Image,ImageDraw,ImageFont
import numpy as np
r=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01');sys.path.insert(0,str(r))
from render_bridge.protocol import decode,encode
s=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-evidence');e=r/'artifacts/cpp-renderer/w01/current-models';e.mkdir(exist_ok=True)
for name,extra in [('fleet',[]),('catalogue',['--catalogue'])]:
 subprocess.run([sys.executable,str(r/'tools/render/dump_snapshot.py'),'--out',str(e/(name+'.snap')),*extra],cwd=r,check=True,capture_output=True)
f=decode((e/'fleet.snap').read_bytes());p=f.payload
vigil=next(i for i in p['instances'] if i['binding']=='imperial:corvette');asset=next(a for a in p['assets'] if a['binding']==vigil['binding']);mesh=json.loads((r/asset['path']).read_text());v=np.asarray(mesh['vertices']);extent=float(np.max(v.max(axis=0)-v.min(axis=0)))*vigil['scale']
p['camera']=dict(target=vigil['position'],distance=extent*2.1,yaw=145.,pitch=28.,fov=55.)
p['metadata']['assumptions'].append('Vigil close-up camera only; same frozen world and source state.')
(e/'vigil.snap').write_bytes(encode(p,kind=f.kind,tick=f.tick,frame_index=f.frame_index))
jobs=[('timing','fleet',['--frames','240','--warmup','60'],False),('fleet','fleet',['--frames','30','--warmup','30'],True),('command','fleet',['--frames','30','--warmup','30','--preset','3'],True),('vigil','vigil',['--frames','30','--warmup','30'],True),('catalogue','catalogue',['--frames','30','--warmup','30'],True)]
for name,snap,extra,shot in jobs:
 command=[str(r/'render_cpp/build/armada_viewer'),'--snapshot',str(e/(snap+'.snap')),'--assets',str(r),'--no-overlay','--report',str(e/(name+'.json')),*extra]
 if shot:command+=['--screenshot',str(e/(name+'.png'))]
 result=subprocess.run([sys.executable,str(s/'bounded.py'),'60',str(e/(name+'.log')),*command],cwd=r,capture_output=True,text=True);print(result.stdout.strip(),flush=True);assert result.returncode==0,result.stderr
 if shot:
  im=Image.open(e/(name+'.png'));pixels=im.tobytes();im.save(e/(name+'.png'),optimize=True);assert Image.open(e/(name+'.png')).tobytes()==pixels
fleet=json.loads((e/'timing.json').read_text());cat=json.loads((e/'catalogue.json').read_text());command=json.loads((e/'command.json').read_text())
assert command['inspection_binding']=='imperial:command_station'
assert fleet['instances']==638 and cat['unique_meshes']==103 and fleet['backend']=='Metal'
selection=decode((e/'fleet.snap').read_bytes()).payload
selected={a['binding']:a for a in selection['assets']};assert selected['imperial:corvette']['manifest_asset']=='prototype:imperial/vigil' and selected['imperial:command_station']['manifest_asset']=='prototype:imperial/command_station'
pins={a['path']:hashlib.sha256((r/a['path']).read_bytes()).hexdigest() for a in decode((e/'catalogue.snap').read_bytes()).payload['assets']};assert len(pins)==103
metrics={}
for name in ['command','vigil','fleet','catalogue']:
 im=Image.open(e/(name+'.png')).convert('RGB');a=np.asarray(im).astype(int);mask=np.max(abs(a-a[0,0]),axis=2)>12;assert mask.sum()>0
 metrics[name]=dict(non_background_pixels=int(mask.sum()),bbox=Image.fromarray(mask).getbbox(),rgba_sha256=hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest())
sheet=Image.new('RGB',(1280,475),'#101621');draw=ImageDraw.Draw(sheet);font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
for x,name,label in [(0,'command','Current Imperial Command Center'),(640,'vigil','Current Vigil (corvette binding)')]:
 draw.text((x+12,12),label,fill='white',font=font);im=Image.open(e/(name+'.png'));im.thumbnail((640,400));sheet.paste(im,(x,42))
draw.text((12,447),'Native Metal viewer / shipped default visual packs / unchanged source meshes',fill='#c8d6e8',font=font);sheet.save(e/'review-sheet.png',optimize=True)
report=dict(code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),reason='Owner identified superseded core models; exporter omitted current default visual packs.',supersedes='Earlier W01 core-only pictures/timings are historical and not representative of shipped defaults.',selected_visual_packs=selection['metadata']['visual_selection'],asset_path_root='repository-root',state_sha256=selection['state_sha256'],geometry_sources_unchanged=True,selected_mesh_sha256=pins,focus_assets={k:selected[k] for k in ['imperial:corvette','imperial:command_station']},pixel_measurements=metrics,wall=fleet['wall_frame'],gpu=fleet['gpu_frame'],submitted_triangles_per_pass=fleet['submitted_triangles_per_pass'],catalogue_triangles=cat['unique_triangles'],limits=['offline mesh-only, not full-game FPS','default selection, not arbitrary saved user preferences','Metal only, no Windows/graphics acceptance','shading unchanged; no appearance approval inferred'])
for n in ['current-models-red.log','current-models-green.log']:shutil.copy2(s/n,e/n)
(e/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(focus=report['focus_assets'],wall=report['wall'],gpu=report['gpu'],triangles=report['submitted_triangles_per_pass'],catalogue_triangles=report['catalogue_triangles'],pixels=metrics),indent=2))
