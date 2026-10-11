"""Real Cocoa/GL campaign probe using the unchanged production main loop.
Run: PYTHONPATH=. .venv/bin/python tools/diag_cinematics.py OUTPUT_DIR
"""
import ast
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import pygame
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home()/'.hermes/cache/scratch/cinematics'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.argv = [str(ROOT/'main.py')]
tree = ast.parse((ROOT/'main.py').read_text())
index = next(i for i,n in enumerate(tree.body) if isinstance(n, ast.While))
ns = {'__name__':'__cinematic_probe__','__file__':str(ROOT/'main.py')}
exec(compile(ast.Module(body=tree.body[:index],type_ignores=[]),'main.py','exec'),ns)
one = ast.For(target=ast.Name(id='_frame',ctx=ast.Store()),
              iter=ast.Tuple(elts=[ast.Constant(0)],ctx=ast.Load()),
              body=tree.body[index].body,orelse=[])
frame_code = compile(ast.fix_missing_locations(ast.Module(body=[one],type_ignores=[])),'main.py','exec')
# Do not create recordings/progress on this intentionally synthetic outcome probe.
ns['begin_recording'] = lambda manager: None
ns['finish_recording'] = lambda: None
unlocks = []
ns['_unlock_next_mission'] = lambda: unlocks.append(ns['mission_def']['id'])
ns['clock'] = SimpleNamespace(tick=lambda rate: 33)
ns['menu'].settings = ns['SETTINGS']


def precise():
    return json.loads(json.dumps(ns['state'].to_dict(precise=True)))


def frame(events=()):
    pygame.event.clear()
    for event in events:
        pygame.event.post(event)
    original_step = ns['gm'].step
    def checked_step(dt):
        assert ns['cinematic'] is None, 'simulation/AI stepped during presentation'
        return original_step(dt)
    ns['gm'].step = checked_step
    try:
        exec(frame_code, ns)
    finally:
        ns['gm'].step = original_step


def key(k, kind=pygame.KEYDOWN):
    return pygame.event.Event(kind,key=k,mod=0)


flip = pygame.display.flip
capture_name = None
capture_pixels = {}


def capture_flip():
    if capture_name:
        w,h = ns['W'],ns['H']
        raw = GL.glReadPixels(0,0,w,h,GL.GL_RGB,GL.GL_UNSIGNED_BYTE)
        image = pygame.image.frombuffer(raw,(w,h),'RGB')
        image = pygame.transform.flip(image,False,True)
        capture_pixels[capture_name] = pygame.image.tobytes(image,'RGB')
        pygame.image.save(image,str(OUT/capture_name))
    flip()


pygame.display.flip = capture_flip
results = []
try:
    assert pygame.display.get_driver() == 'cocoa', pygame.display.get_driver()
    missions = ns['menu'].campaign['missions']
    for w,h in ((1024,768),(1280,800)):
        pygame.display.set_mode((w,h),pygame.OPENGL|pygame.DOUBLEBUF)
        GL.glViewport(0,0,w,h)
        ns['W'],ns['H'] = w,h
        ns['SETTINGS'].update(cinematics_enabled=True,reduced_motion=False)
        ns['start_game'](mdef=missions[1])
        ns['mode'] = 'game'
        st = ns['state']
        initial = precise()
        assert st.tick == 0 and ns['cinematic'] is not None
        saved = ns['cinematic'].saved_view
        first_yaw = ns['camera'].yaw
        capture_name = f'intro-{w}x{h}.png'
        frame()
        capture_name = None
        for _ in range(4):
            frame()
        assert initial == precise(), 'intro mutated precise simulation'
        assert ns['camera'].yaw != first_yaw, 'normal camera did not pan'
        assert ns['accumulator'] == 0.
        # Test every catalogue/page caption in the actual compositor.
        from render.cinematics import CampaignCinematic
        caption_count = 0
        for mission in missions:
            movie = CampaignCinematic(mission,ns['camera'],reduced_motion=True)
            movie.compose(w,h)
            pages = int(movie.duration/5)
            for page in range(pages):
                movie.elapsed = page*5.
                movie.compose(w,h)
                panel = pygame.Rect(40,h-274,w-80,250)
                for r in movie.caption_rects:
                    assert pygame.Rect(0,0,w,h).contains(r)
                    assert panel.contains(r) if r.y > 140 else pygame.Rect(40,24,w-80,108).contains(r)
                    caption_count += 1
                for i,r in enumerate(movie.caption_rects):
                    assert not any(r.colliderect(o) for o in movie.caption_rects[i+1:])
            movie.finish()
        # Actual SDL skip gestures, frozen skip-frame, restored view, usable controls.
        for gesture in (key(pygame.K_RETURN),key(pygame.K_SPACE),key(pygame.K_ESCAPE),
                        pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(400,300))):
            ns['start_game'](mdef=missions[1])
            ns['mode']='game'
            initial = precise()
            saved = ns['cinematic'].saved_view
            frame([gesture, key(pygame.K_s)])
            assert precise() == initial and ns['cinematic'] is None
            cam=ns['camera']
            assert saved == (cam.target,cam.distance,cam.yaw,cam.pitch,cam.follow_id)
            assert ns['mode']=='game' and not ns['inputc'].keys
            frame([key(pygame.K_p)])
            assert ns['paused'], 'ordinary P control did not resume'
            frame([key(pygame.K_p,pygame.KEYUP)])
            frame([key(pygame.K_p)])
            assert not ns['paused']
            assert ns['state'].tick <= 1, 'simulation catch-up debt'
        # Reduced motion: identical production frame pixels and precise state.
        ns['SETTINGS']['reduced_motion']=True
        ns['start_game'](mdef=missions[1])
        ns['mode']='game'
        initial=precise()
        camera=ns['camera']
        view=(list(camera.target),camera.distance,camera.yaw,camera.pitch)
        capture_name=f'reduced-{w}x{h}.png'
        frame()
        capture_name=f'reduced-repeat-{w}x{h}.png'
        for _ in range(5): frame()
        capture_name=None
        assert capture_pixels[f'reduced-{w}x{h}.png']==capture_pixels[f'reduced-repeat-{w}x{h}.png'], 'reduced motion changed framebuffer'
        assert precise()==initial and view==(camera.target,camera.distance,camera.yaw,camera.pitch)
        # Natural time expiration, not skip, resumes with no accrued ticks.
        ns['cinematic'].elapsed=ns['cinematic'].duration-.01
        frame()
        assert ns['cinematic'] is None and precise()==initial
        frame()
        assert ns['state'].tick<=1
        # Fixture-latched real mission system outcome; no claim of human playthrough.
        ns['gm'].mission.completed=True
        ns['gm'].mission.failed=False
        before=precise()
        prior=len(unlocks)
        capture_name=f'outro-{w}x{h}.png'
        frame()
        capture_name=None
        assert ns['cinematic'].outcome=='MISSION COMPLETE'
        assert precise()==before and len(unlocks)==prior+1
        frame([key(pygame.K_ESCAPE)])
        assert ns['cinematic'] is None and precise()==before
        assert ns['mode']=='menu', 'outro did not return to fleet command'
        frame()
        assert ns['cinematic'] is None and len(unlocks)==prior+1
        # Failure doesn't unlock; bypass doesn't delay startup.
        ns['start_game'](mdef=missions[1])
        ns['mode']='game'
        ns['gm'].mission.failed=True
        ns['sync_campaign_outcome']()
        assert ns['cinematic'].outcome=='MISSION FAILED' and len(unlocks)==prior+1
        ns['SETTINGS']['cinematics_enabled']=False
        ns['start_game'](mdef=missions[1])
        assert ns['cinematic'] is None
        # Help through the production dispatcher, not a detached helper.
        ns['mode']='game'
        ns['paused']=True
        ns['inputc'].keys.add(pygame.K_w)
        before=precise()
        capture_name=f'help-main-{w}x{h}.png'
        frame([key(pygame.K_F1),key(pygame.K_b),key(pygame.K_F5)])
        capture_name=None
        assert ns['presentation'].help_visible and not ns['inputc'].keys
        assert precise()==before, 'modal help dispatched commands/save while paused'
        assert ns['presentation'].panel_rects
        assert all(r in ns['hud'].blocked_rects for r in ns['presentation'].panel_rects)
        frame([key(pygame.K_PAGEDOWN)])
        assert ns['presentation'].help_page==1
        frame([key(pygame.K_ESCAPE), key(pygame.K_s)])
        assert not ns['presentation'].help_visible and ns['mode']=='game'
        assert not ns['inputc'].keys and precise()==before, 'modal close leaked an order'
        # Pointer release over an actual rendered tutorial hint must cancel the
        # world gesture, not forward its release into selection/orders.
        ns['start_game'](mdef=missions[0])
        ns['mode']='game'
        ns['paused']=True
        controller=ns['inputc']
        controller.selection={next(e.id for e in ns['state'].entities.values()
                                   if e.owner==0 and e.is_ship)}
        frame()
        assert ns['presentation'].panel_rects, 'recovery hint was not rendered'
        hint=ns['presentation'].panel_rects[0].center
        world=next((x,y) for y in range(400,h-220,20) for x in range(400,w-100,20)
                   if not any(r.collidepoint((x,y)) or r.collidepoint((x+40,y))
                              for r in ns['hud'].blocked_rects))
        later=(world[0]+40,world[1])
        before=precise()
        selected=set(controller.selection)
        for button in (3,1):
            frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=button,pos=world)])
            assert controller.right_drag==world if button==3 else controller.dragging
            frame([pygame.event.Event(pygame.MOUSEBUTTONUP,button=button,pos=hint)])
            assert controller.right_drag is None if button==3 else not controller.dragging
            view=(ns['camera'].yaw,ns['camera'].pitch)
            frame([pygame.event.Event(pygame.MOUSEMOTION,pos=later,rel=(40,0),buttons=(0,0,0)),
                   pygame.event.Event(pygame.MOUSEBUTTONUP,button=button,pos=later)])
            assert (ns['camera'].yaw,ns['camera'].pitch)==view
            assert controller.selection==selected and precise()==before
            assert not ns['state'].command_queue, 'intercepted hint release issued an order'
        results.append(dict(resolution=[w,h],caption_rects=caption_count,
                            precise_invariance=True,skip_controls=True,reduced_motion=True,
                            outcome_once=True,production_help=True,hint_release_gestures=True,
                            driver=pygame.display.get_driver(),gl_error=int(GL.glGetError())))
        assert results[-1]['gl_error']==0
    (OUT/'report.json').write_text(json.dumps(results,indent=2))
    print('DIAG_CINEMATICS_OK '+json.dumps(results)+' output='+str(OUT))
finally:
    pygame.display.flip=flip
    if ns['audio'] is not None: ns['audio'].cleanup()
    if ns['renderer'] is not None: ns['renderer'].close()
    if ns['hud'] is not None: ns['hud'].close()
    if ns.get('presentation') is not None: ns['presentation'].cleanup()
    ns['menu'].close()
    pygame.quit()
