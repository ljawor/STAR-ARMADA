#!/usr/bin/env python3
"""Actual production renderer, UNAPPROVED REVIEW-ONLY in-process geometry injection.

No registry, approval or production source is written. Defaults stay unchanged.
Run .venv/bin/python tools/diag_alliance_cruiser_review.py --out ARTIFACT_SUBDIR
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
W,H=1280,800

def build_review_scene(helper):
    """Keep shared scene setup, but declare this orbit harness's actual intent.

    No helper.issue calls are made; renderer and HUD receive empty selections.
    The inherited recipe describes the helper's separate combat harness.
    """
    gm, ids, recipe = helper.build_scene()
    return gm, ids, dict(recipe, command_schedule=[], selection=[])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    source_before=helper.manifest(ROOT)
    protected={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('saves','replays','art/blender','tools/art') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    helper.isolate(ROOT,out)
    import pygame
    import numpy as np
    from OpenGL import GL
    import game.core.manager
    from game.benchmark import state_hash
    from render import asset_selection as selection
    from render.authored_mesh import _load_profile
    from render.camera import Camera
    from render.renderer import Renderer
    from render.ship_sizes import ship_size
    from render.hud import HUD
    assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')
    asset_path=ROOT/'assets/models/alliance_cruiser.mesh.json'
    asset=json.loads(asset_path.read_text())
    candidate=_load_profile(asset_path,'alliance_cruiser',((-66,66),(-11.265,19.3),(-99.925,97.5)),197.4)
    selection.configure({'model_preview':True})
    production_mesh_for=selection.mesh_for
    assert production_mesh_for('rebel:cruiser') is None,'Pending specimen must not be approved/selected'
    helper.PLACEMENTS=[('capital','ship','rebel_cruiser',0,[-4200,0,2200],0.),
                       ('escort','ship','rebel_frigate',0,[-4200,0,2500],0.),
                       ('battleship','ship','rebel_battleship',0,[-4200,0,1600],0.),
                       ('enemy_a','ship','imperial_frigate',1,[-3500,0,2200],-1.5707963267948966),
                       ('enemy_b','ship','imperial_frigate',1,[-3500,0,2550],-1.5707963267948966)]
    gm,ids,recipe=build_review_scene(helper); st=gm.state
    initial=state_hash(st)
    baseline_geometry=helper.geometry(st)
    active={'enabled':False,'mesh':candidate}
    def review_mesh(binding):
        return active['mesh'] if active['enabled'] and binding=='rebel:cruiser' else production_mesh_for(binding)
    selection.mesh_for=review_mesh
    active['enabled']=True; selection.invalidate_geometry_helpers()
    candidate_geometry=helper.geometry(st)
    union=[baseline_geometry,candidate_geometry]
    cam=Camera(W,H)
    cam.bind_scene(st,lambda:0,lambda:0.)
    views={
        'close':dict(target=[-4200,0,2200],distance=270.,yaw=48.,pitch=35.),
        'rear':dict(target=[-4200,0,2200],distance=270.,yaw=178.,pitch=5.),
        'tactical':dict(target=[-4200,0,2200],distance=1100.,yaw=48.,pitch=55.),
        'common-scale':dict(target=[-4200,0,2200],distance=1050.,yaw=86.,pitch=46.)}
    report=dict(status='pending_owner_approval',integration='UNAPPROVED REVIEW-ONLY harness monkeypatch of mesh_for; no production activation or approval records',
                authority='blend',source_sha256=source_before['sha256'],recipe=recipe,views=views,
                baseline_geometry=baseline_geometry,candidate_geometry=candidate_geometry,
                initial_state_sha256=initial,captures={},features={},comparison={},motion={},
                mesh=dict(sha256=hashlib.sha256(asset_path.read_bytes()).hexdigest(),triangles=asset['triangle_count'],vertices=len(asset['vertices']),bytes=asset_path.stat().st_size,bounds=asset['bounds']),
                warning='Offline orbit video: production draw and real simulation ticks; not paced FPS or battle acceptance')
    pygame.display.init(); pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
    pygame.display.set_mode((W,H),pygame.OPENGL|pygame.DOUBLEBUF)
    GL.glEnable(GL.GL_DEPTH_TEST); GL.glEnable(GL.GL_MULTISAMPLE)
    samples=int(GL.glGetIntegerv(GL.GL_SAMPLES)); viewport=list(map(int,GL.glGetIntegerv(GL.GL_VIEWPORT)))
    assert samples==4 and viewport==[0,0,W,H]
    report['display']=dict(samples=samples,viewport=viewport,gl={k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]})
    renderer=None; hud=None; images={}; states={}
    try:
        for variant in ('before','after'):
            active['enabled']=variant=='after'; active['mesh']=candidate
            selection.invalidate_geometry_helpers()
            gm,ids,_=build_review_scene(helper); st=gm.state
            assert state_hash(st)==initial
            cam=Camera(W,H); cam.bind_scene(st,lambda:0,lambda:0.)
            renderer=Renderer(st,cam); renderer.diff_render=True; renderer.time=3.
            assert not renderer.skip and renderer.materials.available
            report['production_shaders']=renderer.materials.available
            hud=HUD(W,H,st)
            def draw(view,save=None,with_hud=False):
                pygame.event.pump(); helper.configure(cam,view)
                check=helper.camera_check(cam,st,union,3.)
                before=state_hash(st)
                renderer.draw(0.,set())
                if with_hud:
                    hud.render(set(),None,0,False); hud.draw_gl()
                assert state_hash(st)==before
                GL.glFinish()
                pixels=np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy()
                assert GL.glGetError()==GL.GL_NO_ERROR
                if save:pygame.image.save(pygame.image.frombuffer(pixels.tobytes(),(W,H),'RGB'),str(out/save))
                return pixels,check
            for name,view in views.items():
                for _ in range(3):draw(view,with_hud=name=='tactical')
                pixels,check=draw(view,f'{variant}-{name}.png',name=='tactical')
                repeat,_=draw(view,with_hud=name=='tactical')
                delta=np.abs(pixels.astype(int)-repeat.astype(int))
                report['captures'][f'{variant}-{name}']=dict(camera=check,state_sha256=state_hash(st),repeat_changed_pixels=int(np.any(delta,axis=2).sum()),repeat_max_delta=int(delta.max()))
                images[variant,name]=pixels
            if variant=='after':
                # Isolate EACH named emitter via its role-local exported span.
                offsets={r:0 for r in candidate}
                for part in asset['parts']:
                    role=part['role']; start=offsets[role]; end=start+part['triangles']; offsets[role]=end
                    if 'Recessed cyan emitter' not in part['name']:continue
                    ablated=dict(candidate); ablated[role]=candidate[role][:start]+candidate[role][end:]
                    active['mesh']=ablated
                    renderer.close(); renderer=Renderer(st,cam); renderer.diff_render=True; renderer.time=3.
                    for _ in range(3):draw(views['rear'])
                    pixels,_=draw(views['rear'],f'ablated-emitter-{len(report["features"])}.png')
                    full=images['after','rear']; changed=np.any(np.abs(full.astype(int)-pixels.astype(int))>3,axis=2)
                    ys,xs=np.where(changed)
                    report['features'][part['name']]=dict(changed_pixels=int(changed.sum()),bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None)
                    active['mesh']=candidate
                renderer.close(); renderer=Renderer(st,cam); renderer.diff_render=True; renderer.time=3.
                for _ in range(3):draw(views['rear'])
                restored,_=draw(views['rear'],'after-rear-restored.png')
                report['emitter_restored_changed_pixels']=int(np.any(restored!=images['after','rear'],axis=2).sum())
                # Isolate owner paint and broad armor/machinery presentation.
                report['role_ablation']={}
                for role in ('accent','trim','dark'):
                    ablated=dict(candidate); ablated[role]=()
                    active['mesh']=ablated
                    renderer.close(); renderer=Renderer(st,cam); renderer.diff_render=True; renderer.time=3.
                    for _ in range(3):draw(views['close'])
                    pixels,_=draw(views['close'],f'ablated-{role}.png')
                    full=images['after','close']; delta=np.abs(full.astype(int)-pixels.astype(int))
                    changed=np.any(delta>3,axis=2)
                    blue=(full[:,:,2].astype(int)>full[:,:,0].astype(int)+25)&(full[:,:,2].astype(int)>full[:,:,1].astype(int)+5)
                    report['role_ablation'][role]=dict(changed_pixels=int(changed.sum()),blue_owner_pixels=int((changed&blue).sum()))
                active['mesh']=candidate
                renderer.close(); renderer=Renderer(st,cam); renderer.diff_render=True; renderer.time=3.
            # Five seconds at 30 frames/s; same simulation recipe and orbit.
            video=out/f'{variant}-motion.mp4'
            command=['ffmpeg','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate','30','-i','-','-an','-c:v','libx264','-crf','19','-pix_fmt','yuv420p',str(video)]
            with (out/f'{variant}-ffmpeg.txt').open('w') as log:
                encoder=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=log)
                timeline=[]
                try:
                    for frame in range(150):
                        gm.step(1/30)
                        view=dict(views['close']); view['yaw']=48.+frame*.6; view['distance']=300.
                        renderer.time=3.+frame/30
                        pixels,_=draw(view)
                        timeline.append(state_hash(st)); encoder.stdin.write(pixels.tobytes())
                        if frame in (0,75,149):pygame.image.save(pygame.image.frombuffer(pixels.tobytes(),(W,H),'RGB'),str(out/f'{variant}-motion-{frame:03d}.png'))
                finally:
                    encoder.stdin.close(); assert encoder.wait()==0
            states[variant]=timeline
            report['motion'][variant]=dict(frames=len(timeline),seconds=5,fps=30,final_state_sha256=timeline[-1],video=video.name)
            hud.close(); hud=None; renderer.close(); renderer=None
        report['motion_state_samples_equal']=states['before']==states['after']
        assert report['motion_state_samples_equal']
        for name in views:
            a,b=images['before',name],images['after',name]
            diff=np.abs(a.astype(int)-b.astype(int)); changed=np.any(diff>3,axis=2)
            ys,xs=np.where(changed)
            report['comparison'][name]=dict(changed_pixels_gt3=int(changed.sum()),changed_percent=round(float(changed.mean()*100),4),bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None)
        # Actual palette response, capture only: no state mutation to forge owner paint.
        # Paint is supplied by production player palette; include its exact values.
        report['owner_palette']={str(k):list(v.color) for k,v in st.players.items()}
        selection.mesh_for=production_mesh_for; selection.invalidate_geometry_helpers()
        assert production_mesh_for('rebel:cruiser') is None
        report['production_candidate_unselected_after_review']=True
        report['source_preserved']=helper.manifest(ROOT)==source_before
        protected_after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('saves','replays','art/blender','tools/art') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        report['protected_files_preserved']=protected==protected_after
        assert report['source_preserved'] and report['protected_files_preserved']
        report['protected_file_hashes']=protected
        # Label full-resolution captures in an eight-panel sheet.
        sheet=pygame.Surface((1280,1740)); sheet.fill((10,16,25)); font=pygame.font.SysFont('Arial',18)
        for i,name in enumerate(views):
            for j,variant in enumerate(('before','after')):
                x=j*640; y=i*430
                sheet.blit(pygame.transform.smoothscale(pygame.image.frombuffer(images[variant,name].tobytes(),(W,H),'RGB'),(640,400)),(x,y+25))
                sheet.blit(font.render(f'{variant.upper()} / {name} / same camera',True,(230,240,248)),(x+10,y))
        sheet.blit(font.render('UNAPPROVED REVIEW ONLY • Liberty Cruiser • Blender master • 4MSAA / production shaders / normal fog',True,(200,220,240)),(12,1720))
        pygame.image.save(sheet,str(out/'review-sheet.png'))
        helper.dump(out/'metrics.json',report)
        helper.dump(out/'motion-state-hashes.json',states)
        print(json.dumps({k:report[k] for k in ('status','mesh','features','comparison','motion_state_samples_equal','source_preserved','protected_files_preserved')},indent=2))
    finally:
        selection.mesh_for=production_mesh_for
        if hud is not None:hud.close()
        if renderer is not None:renderer.close()
        pygame.display.quit(); pygame.font.quit()

if __name__=='__main__':main()
