"""Native selected station ghosts, queue progress and surface-slot presentation.
Queue state is a render fixture, not a claim of paid-command/buildability acceptance.
"""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);a=parser.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 helper=load('capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py');batch=load('batch',ROOT/'tools/diag_alliance_batch_review.py');helper.isolate(ROOT,out)
 import game.core.manager
 import pygame,numpy as np
 from PIL import Image,ImageDraw
 from OpenGL import GL
 from game.core.entity import Entity
 from game.core.vectors import Vec3
 from game.benchmark import state_hash
 from render import asset_selection as selection
 from render.camera import Camera
 from render.renderer import Renderer
 W,H=960,640;report={'status':'running','renderer_sha256':sha(ROOT/'render/renderer.py'),'harness_sha256':sha(__file__),'rows':[],'scope':'Native ghost/orbital/surface render fixtures through production Renderer.draw, unchanged state and queues. CPU command/placement guards are separate; no claim fixtures themselves prove paid command acceptance.'}
 pygame.display.init();pygame.font.init();pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4);pygame.display.set_mode((W,H),pygame.OPENGL|pygame.DOUBLEBUF);GL.glViewport(0,0,W,H)
 report['msaa']=int(GL.glGetIntegerv(GL.GL_SAMPLES));assert report['msaa']==4
 selection.configure({'model_preview':True,'visual_packs':[]});r=None;tiles=[]
 try:
  assert selection.mesh_for('shared:construction_scaffold') is not None, selection._resolver.diagnostics
  report['scaffold_revision']=selection._resolver.resolve('shared:construction_scaffold').revision
  for faction,prefix in [('rebel','rebel'),('imperial','imperial'),('confederacy','confed'),('syndicate','syndicate')]:
   owner=batch.FACTION_OWNER[faction]
   gm,st=batch.build_row_scene(helper,[('builder','ship',prefix+'_constructor',owner,[-500.,0.,400.],0.)],factions=(faction,));builder=next(iter(st.entities.values()))
   cam=Camera(W,H);cam.bind_scene(st,lambda:owner,lambda:3.);cam.target=[0.,40.,0.];cam.distance=1100.;cam.yaw=48.;cam.pitch=45.
   r=Renderer(st,cam);r.local_player=owner;r.diff_render=True;r.time=3.;assert r.materials.available and not r.skip
   def capture(label,selected=()):
    assert sha(ROOT/'render/renderer.py')==report['renderer_sha256'];r._reset_frame_cache();before=state_hash(st);frames=[]
    for _ in range(4):
     pygame.event.pump();cam.apply(W,H);r.draw(0.,set(selected));GL.glFinish();assert GL.glGetError()==0 and state_hash(st)==before
     frames.append(np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy())
    assert np.array_equal(frames[-1],frames[-2]),(faction,label,'repeat');path=out/f'{faction}-{label}.png';Image.fromarray(frames[-1]).save(path)
    return frames[-1],{'file':path.name,'sha256':sha(path),'state_sha256':before,'repeat_equal':True}
   def difference(x,y):return int(np.any(np.abs(x.astype(int)-y.astype(int))>3,axis=2).sum())
   for mode in ('ghost-valid','ghost-invalid','queue-0.1','queue-0.5','queue-0.9'):
    builder.build_queue=[];r.placement=None
    if mode.startswith('ghost'):r.placement={'builder_id':builder.id,'station_kind':'shipyard','ghost':{'world':(0.,0.,0.),'valid':mode=='ghost-valid'}};method='_draw_placement_preview'
    else:
     progress=float(mode.split('-')[1]);builder.build_queue=[dict(kind='station',item='shipyard',pos=(0.,0.,0.),time_left=100.*(1.-progress),total=100.)];method='_draw_construction_sites'
    image,record=capture(mode)
    with patch.object(r,method,return_value=None):empty,_=capture(mode+'-disabled')
    changed=difference(image,empty);assert changed>0,(faction,mode,'invisible');report['rows'].append(dict(faction=faction,mode=mode,capture=record,changed_pixels_gt3=changed,scaffold_selected=selection.mesh_for('shared:construction_scaffold') is not None))
    tile=Image.fromarray(image);tile.thumbnail((320,214));panel=Image.new('RGB',(320,238),(12,17,25));panel.paste(tile,(0,24));ImageDraw.Draw(panel).text((8,5),f'{faction} {mode}',fill='white');tiles.append(panel)
   builder.build_queue=[];r.placement=None
   planet=Entity(id=1000,kind='planet',is_planet=True,owner=owner,data_id='temperate',pos=Vec3(0.,0.,0.),radius=650.,colonized_by=owner);st.add_entity(planet)
   planet.build_queue=[dict(kind='planet_building',item='planet_extractor',slot=4,time_left=50.,total=100.)];st.grid.rebuild(st.entities);gm.visibility.update()
   cam.target=[0.,651.,0.];cam.distance=500.;cam.pitch=70.
   image,record=capture('surface-queue',{planet.id})
   with patch.object(r,'_draw_surface_slots',return_value=None):empty,_=capture('surface-queue-disabled',{planet.id})
   changed=difference(image,empty);assert changed>0,(faction,'surface queue invisible');report['rows'].append(dict(faction=faction,mode='surface-queue',capture=record,changed_pixels_gt3=changed))
   r.close();r=None;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(faction,'passed',flush=True)
  sheet=Image.new('RGB',(1600,238*4),(12,17,25))
  for i,tile in enumerate(tiles):sheet.paste(tile,((i%5)*320,(i//5)*238))
  sheet.save(out/'construction-sheet.jpg',quality=94);report['status']='passed';assert len(report['rows'])==24
 finally:
  if r:r.close()
  selection.configure({});pygame.display.quit();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'rows':len(report['rows'])}))
if __name__=='__main__':main()
