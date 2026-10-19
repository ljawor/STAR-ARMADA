"""Natural camera-size GL samples of existing cached/uncached role semantics.
No equality or new visual-quality threshold is asserted or inferred.
"""
import sys,os,json,hashlib
from contextlib import ExitStack
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT)];os.chdir(ROOT)
import game.core.manager
import pygame,numpy as np
from OpenGL import GL
from tools.build_menu_movie import PresentationFixture,PresentationState,offline_selection
from render.camera import Camera
from render.renderer import Renderer
from game.benchmark import state_hash
out=ROOT/'artifacts/s07-runtime-acceptance/lod-native-attempt7';out.mkdir(exist_ok=False)
pygame.display.init();pygame.font.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
pygame.display.set_mode((640,480),pygame.OPENGL|pygame.DOUBLEBUF);GL.glViewport(0,0,640,480)
GL.glEnable(GL.GL_MULTISAMPLE);GL.glEnable(GL.GL_DEPTH_TEST)
GL.glClearColor(.006,.009,.018,1.)
report={'scope':'Existing natural projected-size cached vs uncached behavior; not visual parity, new LOD policy, FPS or catalogue-wide visual acceptance. All production passes retained.','samples':[]}
r=None
try:
 with offline_selection(True), ExitStack() as cleanup:
  f=PresentationFixture(); e=next(e for e in f.state.entities.values() if e.owner==0)
  e.data_id='imperial_tie_squadron';e.kind='squadron';e.is_ship=False;e.is_squadron=True
  e.pos.x=e.pos.y=e.pos.z=0.
  state=PresentationState();state.players=f.state.players;state.map_info=f.state.map_info
  state.add_entity(e);f.state=state
  cam=Camera(640,480);cam.target=[0.,0.,0.];cam.yaw=45.;cam.pitch=55.
  r=Renderer(f.state,cam);r.marker_mode='off';r.diff_render=True;r.time=0.
  cleanup.callback(r.close)
  original=r._draw_ships
  sheet=pygame.Surface((600,4*120));sheet.fill((10,15,22));font=pygame.font.SysFont('Arial',16)
  # The shared readability floor keeps this fighter above 21.84px at normal
  # zoom. The supercapital chosen in attempts1-6 cannot naturally reach16/34:
  # the solver ran past the far plane. Preserve those failed probes; measure
  # the reachable fighter transition, never claim natural16px acceptance.
  for row,px in enumerate((24.,33.99,34.01,60.)):
   cam.distance=1000.
   for _ in range(20):
    r._reset_frame_cache();v=r._ensure_frame_cache(set())[e.id]
    cam.distance*=v['apparent']/px
   r._reset_frame_cache();actual=r._ensure_frame_cache(set())[e.id]['apparent'];assert abs(actual-px)<1e-4,(actual,px)
   assert cam.zoom_limits[0]<=cam.distance<=cam.zoom_limits[1]
   frames={};before=state_hash(f.state)
   r._draw_ships=lambda selected,cache:None
   r.draw(0.,set());GL.glFinish()
   empty=np.frombuffer(GL.glReadPixels(0,0,640,480,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(480,640,3)[::-1].copy()
   for col,mode in enumerate(('cached','uncached')):
    r._draw_ships=original if mode=='cached' else lambda selected,cache:original(selected,None)
    for _ in range(3):
     pygame.event.pump();r.draw(0.,set());GL.glFinish();assert GL.glGetError()==0
    assert state_hash(f.state)==before
    image=np.frombuffer(GL.glReadPixels(0,0,640,480,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(480,640,3)[::-1].copy();frames[mode]=image
    surf=pygame.image.frombuffer(image.tobytes(),(640,480),'RGB');pygame.image.save(surf,out/f'{mode}-{px}.png')
    print('diagnostic',mode,px,'distance',cam.distance,'eye',cam.eye_position(),'size',r._ship_size(e),
          'skip',r.skip,'visible',[(x.id,d['apparent']) for x,d in r._ensure_frame_cache(set())['visible']],flush=True)
    assert np.any(image!=empty),(mode,px,'blank subject')
    crop=surf.subsurface((240,160,160,160));sheet.blit(pygame.transform.scale(crop,(100,100)),(col*300,row*120+20))
    sheet.blit(font.render(f'{mode} {actual:.2f}px',True,(235,240,245)),(col*300,row*120))
   delta=np.any(frames['cached']!=frames['uncached'],axis=2)
   report['samples'].append({'data_id':e.data_id,'apparent_px':actual,'cached_roles':['base'] if actual<16 else ['base','lit'] if actual<34 else ['base','dark','trim','accent','lit','cool'],'uncached_roles':'all six','cached_uncached_changed_pixels':int(delta.sum()),'state_sha256':before})
  pygame.image.save(sheet,out/'comparison.png');r.close();r=None
finally:
 if r:r.close()
 pygame.quit();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
