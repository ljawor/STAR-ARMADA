"""Bounded production-frame owner paint / shield / contact acceptance.
No geometry injection; preview and legacy are independently selected. Representative
coverage, not an assertion of catalogue-wide closure. Use a fresh output path.
"""
import argparse, hashlib, importlib.util, json, os, sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT)); os.chdir(ROOT)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
 out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
 helper=load('capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py')
 batch=load('batch',ROOT/'tools/diag_alliance_batch_review.py')
 helper.isolate(ROOT,out)
 import game.core.manager
 import pygame, numpy as np
 from OpenGL import GL
 from game.benchmark import state_hash
 from render import asset_selection as selection
 from render.camera import Camera
 from render.renderer import Renderer
 assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')
 protected=json.loads((ROOT/'artifacts/s07-integration/S07-PROTECTED-INPUTS.json').read_text())['sha256']
 shipped=sha(ROOT/'assets/menu/battle.zip')
 report={'schema':1,'source_commit':'56906ea7c73c219fbdc91c68176104b23d0f7712','harness_sha256':sha(__file__),'status':'running','scope':'Representative production-frame owner paint, standing shells and hull/shield contact rasterization. No simulation advance, full campaign/audio, packaging or scaffold registration.','rows':[]}
 W,H=1280,800; r=None
 pygame.display.init(); pygame.font.init()
 pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1); pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
 pygame.display.set_mode((W,H),pygame.OPENGL|pygame.DOUBLEBUF); GL.glViewport(0,0,W,H)
 report['gl']={k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]}
 report['msaa']=int(GL.glGetIntegerv(GL.GL_SAMPLES)); assert report['msaa']==4
 try:
  for preview in (False,True):
   selection.configure({'model_preview':preview})
   assert selection.mesh_for('shared:construction_scaffold') is None
   for faction,prefix in [('rebel','rebel'),('imperial','imperial'),('confederacy','confed'),('syndicate','syndicate')]:
    owner=batch.FACTION_OWNER[faction]
    for kind,data_id in [('ship',prefix+'_frigate'),('ship',prefix+'_constructor'),('station','shipyard')]:
     gm,st=batch.build_row_scene(helper,[('subject',kind,data_id,owner,[0.,0.,0.],0.)],factions=(faction,))
     e=next(iter(st.entities.values())); cam=Camera(W,H); cam.bind_scene(st,lambda:owner,lambda:3.)
     cam.target=[0.,0.,0.]; cam.distance=1000.; cam.yaw=48.; cam.pitch=35.
     r=Renderer(st,cam); r.local_player=owner; r.diff_render=True; r.time=3.
     assert not r.skip and r.materials.available
     radius=r._station_visual_radius(e) if e.is_station else r._ship_size(e).radius
     cam.distance=max(350.,radius*5.)
     binding=f'{faction}:{data_id}' if kind=='station' else selection.ship_binding(gm.ds,data_id,faction)
     resolved=selection.mesh_for(binding); assert (resolved is not None)==preview,(binding,preview)
     key=f'{int(preview)}-{faction}-{data_id}'
     row={'key':key,'binding':binding,'preview':preview,'radius':radius,'distance':cam.distance,'captures':{},'metrics':{}}; report['rows'].append(row)
     def capture(label):
      before=state_hash(st); frames=[]
      for _ in range(5):
       pygame.event.pump(); cam.apply(W,H); r.draw(0.,set()); GL.glFinish()
       assert GL.glGetError()==GL.GL_NO_ERROR
       assert state_hash(st)==before
       frames.append(np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy())
      assert np.array_equal(frames[-1],frames[-2]),(key,label,'frozen repeat')
      path=out/f'{key}-{label}.png'; pygame.image.save(pygame.image.frombuffer(frames[-1].tobytes(),(W,H),'RGB'),path)
      row['captures'][label]={'file':path.name,'sha256':sha(path),'state_sha256':before,'repeat_equal':True}
      return frames[-1]
     def difference(x,y): return int(np.any(np.abs(x.astype(int)-y.astype(int))>3,axis=2).sum())
     red=(1.,.18,.12); blue=(.12,.4,1.)
     st.players[owner].color=red; red_image=capture('red')
     st.players[owner].color=blue; blue_image=capture('blue')
     row['metrics']['owner_changed_pixels_gt3']=difference(red_image,blue_image)
     assert row['metrics']['owner_changed_pixels_gt3']>0,(key,'owner paint invisible')
     actual=r._draw_ship_role_batch
     def no_accent(role,*args,**kwargs):
      if role!='accent': return actual(role,*args,**kwargs)
     with patch.object(r,'_draw_ship_role_batch',side_effect=no_accent): ablated=capture('accent-disabled')
     row['metrics']['accent_changed_pixels_gt3']=difference(blue_image,ablated)
     assert row['metrics']['accent_changed_pixels_gt3']>0,(key,'accent invisible')
     assert np.array_equal(blue_image,capture('restored')),(key,'ablation leaked')
     with patch.object(r,'_draw_shields',return_value=None): no_shell=capture('shell-disabled')
     row['metrics']['shell_changed_pixels_gt3']=difference(blue_image,no_shell)
     # Shell applicability depends on shipped shield pools; record rather than fabricate.
     row['shield_pools']=dict(e.shields)
     if sum(e.shields.values())>0: assert row['metrics']['shell_changed_pixels_gt3']>0,(key,'shield invisible')
     eye=cam.eye_position(); norm=sum(v*v for v in eye)**.5; n=tuple(v/norm for v in eye)
     for effect in ('shield_hit','hull_hit'):
      st.effects=[dict(kind=effect,t=.12,target_id=e.id,pos=e.pos.to_tuple(),normal=n,size=12.,seed=7)]
      contact=capture(effect)
      with patch.object(r,'_draw_hits',return_value=None): no_hit=capture(effect+'-disabled')
      row['metrics'][effect+'_changed_pixels_gt3']=difference(contact,no_hit)
      assert row['metrics'][effect+'_changed_pixels_gt3']>0,(key,effect,'contact invisible')
     st.effects=[]
     r.close(); r=None
     print(json.dumps({'key':key,'metrics':row['metrics']}),flush=True)
  report['status']='passed'
 finally:
  if r: r.close()
  selection.configure({}); pygame.display.quit()
  report['protected_changed']=[p for p,h in protected.items() if sha(ROOT/p)!=h]
  report['shipped_movie_unchanged']=sha(ROOT/'assets/menu/battle.zip')==shipped
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 assert not report['protected_changed'] and report['shipped_movie_unchanged']
 print(json.dumps({'status':report['status'],'rows':len(report['rows'])}))
if __name__=='__main__': main()
