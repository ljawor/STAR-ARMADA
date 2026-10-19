"""Exact native cached/uncached authored-role pixels at naturally reachable sizes."""
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);a=parser.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 spec=importlib.util.spec_from_file_location('capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.isolate(ROOT,out)
 import game.core.manager
 import pygame,numpy as np
 from OpenGL import GL
 from tools.build_menu_movie import PresentationFixture,PresentationState,offline_selection
 from render.camera import Camera
 from render.renderer import Renderer
 from game.benchmark import state_hash
 pygame.display.init();pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4);pygame.display.set_mode((640,480),pygame.OPENGL|pygame.DOUBLEBUF);GL.glViewport(0,0,640,480)
 report={'status':'running','renderer_sha256':sha(ROOT/'render/renderer.py'),'samples':[],'scope':'Exact native parity at naturally reachable fighter24/34/60px and four close-range authored ships. CPU tests cover all37 shipbindings and both legacy boundaries. No new meshes/quality tolerances or natural16px acceptance.'};r=None
 assert int(GL.glGetIntegerv(GL.GL_SAMPLES))==4
 try:
  with offline_selection(True):
   for data_id in ('imperial_tie_squadron','rebel_frigate','confed_frigate','syndicate_constructor'):
    f=PresentationFixture();e=next(e for e in f.state.entities.values() if e.owner==0);e.data_id=data_id;e.kind='squadron' if 'squadron' in data_id else 'ship';e.is_squadron=e.kind=='squadron';e.is_ship=not e.is_squadron;e.pos.x=e.pos.y=e.pos.z=0.;e.vel.x=e.vel.y=e.vel.z=0.
    st=PresentationState();st.players=f.state.players;st.map_info=f.state.map_info;st.add_entity(e)
    cam=Camera(640,480);cam.target=[0.,0.,0.];cam.yaw=45.;cam.pitch=55.;cam.distance=1000.
    r=Renderer(st,cam);r.diff_render=True;r.time=0.;r.marker_mode='off';assert not r.skip and r.materials.available
    original=r._draw_ships
    for desired in ((24.,33.99,34.01,60.) if e.is_squadron else (None,)):
     cam.distance=1000.
     if desired is not None:
      for _ in range(20):
       r._reset_frame_cache();v=r._ensure_frame_cache(set())[e.id];cam.distance*=v['apparent']/desired
     r._reset_frame_cache();actual=r._ensure_frame_cache(set())[e.id]['apparent']
     if desired is not None:assert abs(actual-desired)<1e-4 and cam.zoom_limits[0]<=cam.distance<=cam.zoom_limits[1]
     before=state_hash(st);images={}
     for mode in ('disabled','cached','uncached'):
      r._draw_ships=(lambda selected,cache:None) if mode=='disabled' else original if mode=='cached' else lambda selected,cache:original(selected,None)
      frames=[]
      for _ in range(5):
       pygame.event.pump();r.draw(0.,set());GL.glFinish();assert GL.glGetError()==0 and state_hash(st)==before
       frames.append(np.frombuffer(GL.glReadPixels(0,0,640,480,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(480,640,3)[::-1].copy())
      assert np.array_equal(frames[-1],frames[-2]);images[mode]=frames[-1];pygame.image.save(pygame.image.frombuffer(images[mode].tobytes(),(640,480),'RGB'),out/f'{data_id}-{actual:.2f}-{mode}.png')
     changed=int(np.any(images['cached']!=images['uncached'],axis=2).sum());subject=int(np.any(images['cached']!=images['disabled'],axis=2).sum())
     report['samples'].append({'data_id':data_id,'apparent_px':actual,'cached_uncached_changed_pixels':changed,'subject_pixels':subject,'state_sha256':before});(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(report['samples'][-1],flush=True)
     assert subject>0 and changed==0,(data_id,actual,changed,subject)
    r.close();r=None
  report['status']='passed'
 finally:
  if r:r.close()
  pygame.display.quit();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
if __name__=='__main__':main()
