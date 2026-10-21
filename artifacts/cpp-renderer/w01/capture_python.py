"""Current production world-only reference: frozen fixture, no simulation or HUD."""
import sys,os,time,json,hashlib
from pathlib import Path
root=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01');sys.path.insert(0,str(root))
os.environ['SDL_VIDEODRIVER']='cocoa'
from game.graphics_benchmark import make_fixture
from game.benchmark import state_hash,reported_drawable_size
from render import asset_selection
from render.camera import Camera
from render.renderer import Renderer
import pygame
from OpenGL import GL
out=Path('/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-evidence')
fixture=make_fixture('four-player-combat-v1');st=fixture.manager.state;before=state_hash(st)
asset_selection.configure({'model_preview':True},asset_root=root)
renderer=None
try:
 pygame.display.init();pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
 pygame.display.set_mode((1280,800),pygame.OPENGL|pygame.DOUBLEBUF,vsync=0)
 w,h=reported_drawable_size(pygame) or (1280,800);GL.glViewport(0,0,w,h)
 camera=Camera(w,h);fixture.camera.apply(camera)
 renderer=Renderer(st,camera);renderer.diff_render=True
 samples=[]
 for i in range(12):
  pygame.event.pump();start=time.perf_counter();renderer.draw(0.0,set());GL.glFinish();samples.append((time.perf_counter()-start)*1000)
  if i==11:
   raw=bytes(GL.glReadPixels(0,0,w,h,GL.GL_RGB,GL.GL_UNSIGNED_BYTE))
   image=pygame.image.frombytes(raw,(w,h),'RGB');pygame.image.save(pygame.transform.flip(image,False,True),str(out/'python-reference.png'))
  pygame.display.flip()
 report=dict(code_head='3ae5bf79b1157e3c38b81dde00cdd87e53ee8c73',fixture=fixture.name,state_sha256=before,state_unchanged=state_hash(st)==before,drawable=[w,h],actual_msaa=int(GL.glGetIntegerv(GL.GL_SAMPLES)),backend=GL.glGetString(GL.GL_RENDERER).decode(),scope='Current production world-only renderer, frozen; normal world passes and readability scales; no HUD or simulation. NOT equivalent native workload and NOT a speedup denominator.',camera=dict(target=camera.target,distance=camera.distance,yaw=camera.yaw,pitch=camera.pitch,fov=camera.fov,safe_eye=camera.eye_position()),world_glfinish_samples_ms=samples,framebuffer_sha256=hashlib.sha256(raw).hexdigest())
 assert report['state_unchanged']
 (out/'python-reference.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
finally:
 if renderer:renderer.close()
 pygame.display.quit()
