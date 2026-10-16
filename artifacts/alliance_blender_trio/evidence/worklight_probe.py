"""Per-feature production-frame ablation: each lamp must add a broad visible warm face."""
import sys,json,hashlib
from pathlib import Path
import capture_slice as h
S=Path(__file__).resolve().parent
source=S/'candidate-source';out=S/'worklight-pixels';out.mkdir()
seal=h.manifest(source);h.dump(out/'source-manifest.json',seal)
h.isolate(source,out)
import pygame,numpy as np
from OpenGL import GL
from render.renderer import Renderer
from render.camera import Camera
from render.planet_building_geometry import station_frame
from game.benchmark import state_hash
pygame.display.init();pygame.font.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
pygame.display.set_mode((h.W,h.H),pygame.OPENGL|pygame.DOUBLEBUF)
GL.glEnable(GL.GL_DEPTH_TEST);GL.glEnable(GL.GL_MULTISAMPLE)
gm,ids,recipe=h.build_scene();st=gm.state;cam=Camera(h.W,h.H);r=Renderer(st,cam);r.diff_render=True;r.time=3.
plan=h.load(S/'candidate-plan-cameras/camera-plan.json');h.configure(cam,plan['views']['yard-close'])
assert GL.glGetIntegerv(GL.GL_SAMPLES)==4 and r.materials.available and not r.skip
asset=h.load(source/'assets/models/alliance_shipyard.mesh.json')
mesh=__import__('render.faction_stations',fromlist=['station_mesh']).station_mesh('rebel','shipyard')
spans={};offsets={role:0 for role in asset['batches']}
for part in asset['parts']:
 role=part['role'];start=offsets[role];spans[part['name']]=(start,start+part['triangles']);offsets[role]+=part['triangles']
assert offsets=={k:len(v) for k,v in mesh.items()}
original=r._station_detail_list;override=[None]
def detail(data_id,role,faction='imperial'):
 if data_id=='shipyard' and role=='lit' and faction=='rebel' and override[0] is not None:return override[0]
 return original(data_id,role,faction)
r._station_detail_list=detail
before=state_hash(st)
def image(name):
 for _ in range(4):r.draw(0.,{ids['capital']})
 GL.glFinish();a=np.frombuffer(GL.glReadPixels(0,0,h.W,h.H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(h.H,h.W,3)[::-1].copy()
 pygame.image.save(pygame.image.frombuffer(a.tobytes(),(h.W,h.H),'RGB'),str(out/(name+'.png')))
 assert state_hash(st)==before
 return a
try:
 full=image('all-four-visible');assert np.array_equal(full,image('repeated-full'))
 yard=st.entities[ids['yard']];origin,basis,scale=station_frame(st,yard,__import__('math').radians(9.))
 report=[]
 for i,f in enumerate(asset['features']['worklights']):
  start,end=spans[f['name']];lst=GL.glGenLists(1);GL.glNewList(lst,GL.GL_COMPILE)
  r._emit_detail_mesh(mesh['lit'][:start]+mesh['lit'][end:]);GL.glEndList();override[0]=lst
  absent=image('without-light-'+str(i));GL.glDeleteLists(lst,1);override[0]=None
  p=f['center'];world=[origin[j]+scale*sum(basis[k][j]*p[k] for k in range(3)) for j in range(3)]
  x,y=cam.world_to_screen(*world)[:2];x=int(round(x));y=int(round(y));rad=22
  a=full[y-rad:y+rad+1,x-rad:x+rad+1];b=absent[y-rad:y+rad+1,x-rad:x+rad+1]
  delta=a.astype(int)-b.astype(int);mask=(delta.max(2)>20)&(a[:,:,0]>a[:,:,2]*1.15)&(a[:,:,0]>150)
  yy,xx=np.nonzero(mask);count=len(xx);bbox=[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())] if count else None
  row=dict(name=f['name'],screen=[x,y],visible_warm_pixels=count,bbox=bbox,triangle_span=[start,end],state_sha256=before)
  report.append(row);print(row,flush=True)
  assert count>=25 and bbox[2]-bbox[0]>=5 and bbox[3]-bbox[1]>=3, 'worklight broad face not visible'
 h.dump(out/'metrics.json',dict(source_sha256=seal['sha256'],display_samples=int(GL.glGetIntegerv(GL.GL_SAMPLES)),lights=report,state_sha256=before))
finally:
 r.close();pygame.font.quit();pygame.display.quit()
 assert h.manifest(source)==seal
