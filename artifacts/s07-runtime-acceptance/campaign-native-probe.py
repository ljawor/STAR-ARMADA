"""Real GL campaign launch via natural menu clicks + actual extracted main branch.
Audio remains stubbed; no OS event loop or simulation advancement claimed.
"""
import ast, copy, hashlib, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]; os.chdir(ROOT)
import game.core.manager
import pygame, numpy as np
from OpenGL import GL
from test_s07_campaign_preview_entry import CampaignPreviewEntryTests
from test_lan_main import factories
from render import menus, asset_selection as selection
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD
from render.input import InputController
from game.benchmark import state_hash
out=ROOT/'artifacts/s07-runtime-acceptance/campaign-native-attempt2'; out.mkdir(exist_ok=False)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
protected=json.loads((ROOT/'artifacts/s07-integration/S07-PROTECTED-INPUTS.json').read_text())['sha256']
shipped=ROOT/'assets/menu/battle.zip'; shipped_before=sha(shipped)
pygame.display.init(); pygame.font.init()
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
pygame.display.set_mode((1280,720),pygame.OPENGL|pygame.DOUBLEBUF)
GL.glViewport(0,0,1280,720)
report={'scope':'Natural campaign/briefing clicks, actual main START_MISSION/start_game, real Camera/Renderer/HUD/InputController, stub audio. No simulation advance or OS event loop.', 'samples':[]}
try:
 for preview in (False,True):
  test=CampaignPreviewEntryTests(); ns=None
  try:
   test.setUp(); menu=test.menu
   settings=dict(menus.DEFAULT_SETTINGS,model_preview=preview,cinematics_enabled=False)
   menus.save_settings(settings)
   menu.screen='campaign'; menu.buttons=[]; menu._screen_campaign(); test.click('select_mission')
   menu.buttons=[]; menu._screen_briefing(); test.click('launch_mission')
   assert menu.result==menus.MenuResult.START_MISSION
   ns=factories(); ns.update(menu=menu,SETTINGS=settings,mode='menu',W=1280,H=720,
       Camera=Camera,Renderer=Renderer,HUD=HUD,InputController=InputController,
       save_settings=menus.save_settings,MenuResult=menus.MenuResult,res=menu.result,payload=menu.result_payload)
   tree=ast.parse((ROOT/'main.py').read_text())
   branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare)
       and any(isinstance(c,ast.Attribute) and c.attr=='START_MISSION' for c in n.test.comparators))
   exec(compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(branch.body),type_ignores=[])),str(ROOT/'main.py'),'exec'),ns)
   assert isinstance(ns['renderer'],Renderer) and ns['mode']=='game'
   st=ns['state']; r=ns['renderer']; r.diff_render=True; r.time=0.
   ns['hud'].mission_name=ns['mission_def'].get('name','MISSION')
   ns['hud'].mission_progress=ns['gm'].mission.progress_text()
   before=state_hash(st); pixels=[]
   for _ in range(4):
    pygame.event.pump(); ns['camera'].apply(1280,720)
    r.draw(0.,set()); ns['hud'].render(set(),None,0,False); ns['hud'].draw_gl()
    GL.glFinish(); assert GL.glGetError()==GL.GL_NO_ERROR
    assert state_hash(st)==before
    pixels.append(bytes(GL.glReadPixels(0,0,1280,720,GL.GL_RGB,GL.GL_UNSIGNED_BYTE)))
   assert pixels[-1]==pixels[-2]
   image=np.frombuffer(pixels[-1],np.uint8).reshape(720,1280,3)[::-1].copy()
   path=out/('preview.png' if preview else 'legacy.png')
   pygame.image.save(pygame.image.frombuffer(image.tobytes(),(1280,720),'RGB'),path)
   visible=r._ensure_frame_cache(set())['visible']; pins=[]
   for e,entry in visible:
    if e.is_ship:
     binding=selection.ship_binding(r.ds,e.data_id,st.players[e.owner].faction)
     resolved=selection._resolver.resolve(binding) if binding and selection._resolver else None
     pins.append({'id':e.id,'data_id':e.data_id,'binding':binding,'revision':resolved.revision if resolved else None})
   report['samples'].append({'preview':preview,'file':path.name,'sha256':sha(path),'state_sha256':before,
     'visible_consumers':len(visible),'ships':pins,'msaa':int(GL.glGetIntegerv(GL.GL_SAMPLES)),
     'gl_renderer':GL.glGetString(GL.GL_RENDERER).decode(),'repeat_equal':True})
  finally:
   if ns:
    if ns.get('presentation'): ns['presentation'].cleanup()
    if ns.get('hud'): ns['hud'].close()
    if ns.get('renderer'): ns['renderer'].close()
   test.doCleanups()
 assert report['samples'][0]['state_sha256']==report['samples'][1]['state_sha256']
 assert all(p['revision'] for p in report['samples'][1]['ships'])
 assert (out/'preview.png').read_bytes()!=(out/'legacy.png').read_bytes()
 report['protected_changed']=[p for p,h in protected.items() if sha(ROOT/p)!=h]
 assert not report['protected_changed'] and sha(shipped)==shipped_before
 report['shipped_movie_unchanged']=True
finally:
 pygame.quit()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
