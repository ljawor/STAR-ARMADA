"""Six-second actual-game review reel: escort / industrial yard / approved capital.
Each segment uses an explicit orbit around the current real entity, identical on
both source snapshots. Stock combat commands, normal fog, GLSL/postfx and 4MSAA.
"""
import sys,json,hashlib
from pathlib import Path
import capture_slice as h
S=Path(__file__).parent;label=sys.argv[1];peer='candidate' if label=='baseline' else 'baseline'
source=S/(label+'-source');out=S/(label+'-motion');out.mkdir()
seal=h.manifest(source);assert seal==h.load(S/(label+'-seal-source/source-manifest.json'))
h.dump(out/'source-manifest.json',seal);h.dump(out/'invocation.json',dict(argv=sys.argv,harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
h.isolate(source,out)
import pygame,numpy as np
from OpenGL import GL
from render.renderer import Renderer
from render.camera import Camera
from game.benchmark import state_hash
pygame.display.init();pygame.font.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
pygame.display.set_mode((h.W,h.H),pygame.OPENGL|pygame.DOUBLEBUF)
GL.glEnable(GL.GL_DEPTH_TEST);GL.glEnable(GL.GL_MULTISAMPLE)
gm,ids,recipe=h.build_scene();st=gm.state;cam=Camera(h.W,h.H);r=Renderer(st,cam);r.diff_render=True
plan=h.load(S/'candidate-plan-cameras/camera-plan.json')
geometries=[h.geometry(st),h.load(S/(peer+'-inspect-source/geometry.json'))['geometry']]
assert GL.glGetIntegerv(GL.GL_SAMPLES)==4 and r.materials.available and not r.skip
rows=[];events=[];st.events.subscribe('weapon_fired',lambda e:events.append(st.tick))
try:
 with (out/'commands.jsonl').open('w') as commands:
  for tick in range(1,181):
   h.issue(gm,tick,commands);gm.step(h.DT);assert st.tick==tick
   label_view=[('escort','escort-close'),('yard','yard-close'),('capital','capital-detail')][(tick-1)//60]
   subject,view=label_view;spec=dict(plan['views'][view]);spec['target']=list(st.entities[ids[subject]].pos.to_tuple())
   spec['yaw']+=((tick-1)%60)/59*18-9
   h.configure(cam,spec);r.time=3+tick*h.DT
   before=state_hash(st);check=h.camera_check(cam,st,geometries,r.time)
   pygame.event.pump();r.draw(0.,{ids['capital']});GL.glFinish()
   assert before==state_hash(st) and GL.glGetError()==GL.GL_NO_ERROR
   pixels=np.frombuffer(GL.glReadPixels(0,0,h.W,h.H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(h.H,h.W,3)[::-1].copy()
   pygame.image.save(pygame.image.frombuffer(pixels.tobytes(),(h.W,h.H),'RGB'),str(out/f'frame-{tick:04d}.png'))
   rows.append(dict(tick=tick,sha256=before,subject=subject,camera=check,view_time=r.time))
 h.dump(out/'ticks.json',rows)
 expected=[json.loads(line)['sha256'] for line in (S/(label+'-candidate-capture' if label=='candidate' else 'baseline-baseline-capture')/'ticks.jsonl').read_text().splitlines()][1:]
 assert expected==[row['sha256'] for row in rows]
 h.dump(out/'summary.json',dict(source_sha256=seal['sha256'],frames=len(rows),fps=30,display_samples=4,weapon_fired=len(events),state_hashes_match_still_combat=True,final_state_sha256=state_hash(st),cameras='three explicit subject-relative 18 degree orbits, per frame in ticks.json'))
finally:
 r.close();pygame.font.quit();pygame.display.quit();assert h.manifest(source)==seal
