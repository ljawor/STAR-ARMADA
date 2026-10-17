import sys, json, importlib.util, hashlib
from pathlib import Path
ROOT=Path('/Users/lukaszjawor/.hermes/cache/scratch')
source=ROOT/'s05-parent-verification/sources/candidate'
out=ROOT/'s05-repeat-diagnosis'/sys.argv[1]; out.mkdir()
spec=importlib.util.spec_from_file_location('recipe',source/'artifacts/alliance_blender_trio/evidence/capture_slice.py'); recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
seal=recipe.manifest(source);recipe.isolate(source,out)
import game.core
from render.asset_selection import configure
configure({'model_preview':True},asset_root=source)
import pygame, numpy as np
from OpenGL import GL
from render.renderer import Renderer
from render.camera import Camera
from game.benchmark import state_hash
pygame.display.init(); pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1);pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4);pygame.display.set_mode((1280,800),pygame.OPENGL|pygame.DOUBLEBUF)
GL.glEnable(GL.GL_DEPTH_TEST);GL.glEnable(GL.GL_MULTISAMPLE);GL.glClearColor(.008,.012,.025,1.)
gm,ids,scene=recipe.build_scene();st=gm.state;cam=Camera(1280,800);r=Renderer(st,cam);r.diff_render=True
log={'quality':{'samples':int(GL.glGetIntegerv(GL.GL_SAMPLES)),'sample_buffers':int(GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS)),'materials':r.materials.available,'fog':type(r.fog).__module__,'dither':bool(GL.glIsEnabled(GL.GL_DITHER))},'repeats':[]}
def read():
 GL.glFinish();return np.frombuffer(GL.glReadPixels(0,0,1280,800,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(800,1280,3)[::-1].copy()
def metrics(a,b):
 d=np.abs(a.astype('int16')-b.astype('int16'));y,x=np.where(np.any(d,2));return {'pixels':len(x),'channels':int(np.count_nonzero(d)),'max':int(d.max()),'bbox':[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if len(x) else None}
def save(name,a):pygame.image.save(pygame.image.frombuffer(a.tobytes(),(1280,800),'RGB'),str(out/(name+'.png')))
def draw(v,t):
 recipe.configure(cam,v);r.time=t;pygame.event.pump();before=state_hash(st);r.draw(0.,{ids['capital']});assert before==state_hash(st);assert GL.glGetError()==0;return read()
class Sink:
 def write(self,*a):pass
 def flush(self):pass
try:
 for tick in range(1,271):
  recipe.issue(gm,tick,Sink());gm.step(recipe.DT)
  if tick%6==0:
   name=('common-scale','capital-close','escort-close','yard-close')[((tick//6)-1)//15];v=dict(recipe.VIEWS[name]);label={'capital-close':'capital','escort-close':'escort','yard-close':'yard'}.get(name)
   if label:v['target']=list(st.entities[ids[label]].pos.to_tuple())
   v['yaw']+=tick/360*18
   for i in range(5):a=draw(v,3+tick*recipe.DT)
 log['state']=state_hash(st);log['view']=v;log['camera']={'view':np.asarray(cam._view).tolist(),'proj':np.asarray(cam._proj).tolist()};save('initial',a)
 prev=a
 for i in range(500):
  a=draw(v,12.);b=read();m=metrics(prev,a);log['repeats'].append({'i':i,'draw':m,'reread':metrics(a,b),'hash':hashlib.sha256(a.tobytes()).hexdigest()})
  if m['pixels']:save('repeat-%03d'%i,a);save('before-%03d'%i,prev)
  prev=a
 # Observe pass boundaries without removing any production pass.
 stages={};active=[0]
 for name in ['_draw_starfield','_draw_nebulas','_draw_star','_draw_jump_points','_draw_planets','_draw_planet_shields','_draw_effects','_draw_projectiles','_draw_ships','_draw_shields','_draw_hits','_draw_selection_rings']:
  original=getattr(r,name)
  def wrapper(*args,_orig=original,_name=name,**kw):
   result=_orig(*args,**kw);stages.setdefault(_name,[]).append(read());return result
  setattr(r,name,wrapper)
 for i in range(4):draw(v,12.)
 log['stages']={name:[metrics(arr[i-1],arr[i]) for i in range(1,len(arr))] for name,arr in stages.items()}
 for name,arr in stages.items():save('stage'+name,arr[-1])
 log['error']=int(GL.glGetError());log['source_preserved']=seal==recipe.manifest(source)
finally:
 r.close();pygame.display.quit();(out/'result.json').write_text(json.dumps(log,indent=2));print(json.dumps(log))
