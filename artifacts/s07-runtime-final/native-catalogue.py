"""Enumerated registered-catalogue native presentation coverage (not S09).
Uses actual factory entities and normal Renderer.draw. No mesh injection. All
outputs append per completed row, so a failed row or deadline retains evidence.
"""
import argparse, hashlib, json, os, sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]; sys.path[:0]=[str(ROOT),str(ROOT/'tests')]; os.chdir(ROOT)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--category',default='all');a=p.parse_args()
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 import importlib.util
 spec=importlib.util.spec_from_file_location('capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py'); helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.isolate(ROOT,out)
 import game.core.manager
 import pygame,numpy as np
 from OpenGL import GL
 from game.core.manager import GameManager
 from game.core.entity import Entity
 from game.core.state import PlayerState
 from game.core.vectors import Vec3
 from game.benchmark import state_hash
 from render import asset_selection as selection
 from render.camera import Camera
 from render.renderer import Renderer
 from test_s07_selected_geometry_matrix import catalogue_rows
 from PIL import Image,ImageDraw
 W,H=960,640; selection.configure({'model_preview':True,'visual_packs':[]})
 gm=GameManager(); rows=catalogue_rows(gm.ds)
 supported={'combat_hull','construction','logistics_hull','squadron','station','satellite','planet_installation'}
 rows=[x for x in rows if x['category'] in supported and (a.category=='all' or x['category']==a.category)]
 # This harness captures spawnable units. The shared scaffold is a render-only queue
 # prop with no data_id; its presentation is captured by native-construction.py through
 # the real construction seam, not by an orbit sample here. Any other row without a
 # spawnable data_id is an error, never a silent skip.
 non_spawnable={'shared:construction_scaffold':'render-only construction queue prop; covered by native-construction.py'}
 unspawnable=[x['binding'] for x in rows if not x['consumers'] or not x['consumers'][0].get('data_id')]
 assert set(unspawnable)<=set(non_spawnable),unspawnable
 rows=[x for x in rows if x['binding'] not in non_spawnable]
 report={'schema':1,'status':'running','renderer_sha256':sha(ROOT/'render/renderer.py'),'harness_sha256':sha(__file__),'expected_bindings':[row['binding'] for row in rows],'excluded_bindings':{b:non_spawnable[b] for b in sorted(unspawnable)},'rows':[],'limits':'Native presentation orbit samples, not simulation progression, full OS campaign, native Windows, FPS or packaging. Neutral prop and construction scaffold use separately scoped production routes.'}
 pygame.display.init();pygame.font.init();pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
 pygame.display.set_mode((W,H),pygame.OPENGL|pygame.DOUBLEBUF);GL.glViewport(0,0,W,H)
 report['gl']={k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]};report['samples']=int(GL.glGetIntegerv(GL.GL_SAMPLES));assert report['samples']==4
 renderer=None;tiles=[]
 try:
  for row in rows:
   assert sha(ROOT/'render/renderer.py')==report['renderer_sha256'],'renderer changed during acceptance'
   faction=row['binding'].split(':')[0]; gm=GameManager();st=gm.state;m=gm.ds.maps['skirmish01'];st.map_info.bounds=m['bounds'];st.map_info.star=dict(m['star']);st.seed=12345
   st.players={0:PlayerState(0,faction=faction,team=0,is_ai=False,color=(1.,.18,.12))}
   data_id=row['consumers'][0]['data_id'];pos=Vec3(0.,5000.,0.)
   if row['category'] in ('station','satellite','planet_installation'):e=gm.factory.spawn_station(data_id,0,pos)
   elif data_id=='trade_convoy':
    e=Entity(id=1,kind='ship',owner=0,data_id=data_id,is_ship=True,pos=pos,radius=32.);st.add_entity(e)
   else:e=gm.factory.spawn_ship(data_id,0,pos)
   if row['category'] in ('satellite','planet_installation'):
    planet=Entity(id=1000,kind='planet',owner=0,data_id='temperate',is_planet=True,pos=Vec3(0.,4349.,0.),radius=650.);st.add_entity(planet);e.planet_id=planet.id
    if row['category']=='satellite':e.satellite_slot=2
    else:e.planet_building_slot=4
   st.grid.rebuild(st.entities);gm.visibility.update()
   cam=Camera(W,H);cam.target=list(pos.to_tuple());cam.distance=1000.;cam.yaw=48.;cam.pitch=55.;cam.bind_scene(st,lambda:0,lambda:3.)
   renderer=Renderer(st,cam);r=renderer;r.local_player=0;r.diff_render=True;r.time=3.;assert not r.skip and r.materials.available
   radius=r._station_visual_radius(e) if e.is_station else r._ship_size(e).radius;cam.distance=max(200.,radius*5.)
   selected=selection._resolver.resolve(row['binding']);assert selected is not None
   result={'binding':row['binding'],'category':row['category'],'data_id':data_id,'revision':selected.revision,'captures':{},'metrics':{}}
   def capture(label):
    r._reset_frame_cache();before=state_hash(st);frames=[]
    for _ in range(4):
     pygame.event.pump();cam.apply(W,H);r.draw(0.,set());GL.glFinish();assert GL.glGetError()==0;assert state_hash(st)==before
     frames.append(np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy())
    assert np.array_equal(frames[-1],frames[-2]),(row['binding'],label,'repeat')
    path=out/(row['binding'].replace(':','-')+'-'+label+'.png');Image.fromarray(frames[-1]).save(path)
    result['captures'][label]={'file':path.name,'sha256':sha(path),'state_sha256':before,'repeat_equal':True};return frames[-1]
   def delta(x,y):return int(np.any(np.abs(x.astype(int)-y.astype(int))>3,axis=2).sum())
   red=capture('red');st.players[0].color=(.12,.4,1.);blue=capture('blue')
   result['metrics']['owner_changed_pixels_gt3']=delta(red,blue);assert result['metrics']['owner_changed_pixels_gt3']>0,(row['binding'],'owner paint invisible')
   # Remove only the real subject, leaving its parent planet and background intact.
   original=st.entities.pop(e.id)
   empty=capture('subject-disabled');st.entities[e.id]=original
   result['metrics']['subject_changed_pixels_gt3']=delta(blue,empty);assert result['metrics']['subject_changed_pixels_gt3']>0
   restored=capture('restored');assert np.array_equal(restored,blue)
   # Presentation orbit, not synthetic simulation motion: two additional camera/time samples.
   for index,(yaw,time) in enumerate(((78.,3.12),(108.,3.24))):
    cam.yaw=yaw;r.time=time;image=capture(f'orbit-{index}');result['metrics'][f'orbit_{index}_changed_pixels_gt3']=delta(blue,image);assert result['metrics'][f'orbit_{index}_changed_pixels_gt3']>0
   r.close();renderer=None
   report['rows'].append(result);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
   panel=Image.new('RGB',(320,230),(12,17,25));im=Image.fromarray(blue);im.thumbnail((320,210));panel.paste(im,(0,20));ImageDraw.Draw(panel).text((6,4),row['binding'],fill='white');tiles.append(panel)
   print(json.dumps({'binding':row['binding'],'metrics':result['metrics']}),flush=True)
  assert len(report['rows'])==len(report['expected_bindings']) and len({x['binding'] for x in report['rows']})==len(rows)
  for page,start in enumerate(range(0,len(tiles),20)):
   batch=tiles[start:start+20];sheet=Image.new('RGB',(1280,230*((len(batch)+3)//4)),(12,17,25))
   for index,tile in enumerate(batch):sheet.paste(tile,((index%4)*320,(index//4)*230))
   sheet.save(out/f'catalogue-{page}.jpg',quality=94)
  report['status']='passed'
 finally:
  if renderer:renderer.close()
  selection.configure({});pygame.display.quit();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'rows':len(report['rows'])}))
if __name__=='__main__':main()
