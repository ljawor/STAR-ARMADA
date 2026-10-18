#!/usr/bin/env python3
"""Review-only injection of the pending scaffold through the production build-queue draw.

No registration or appearance decision. Real native GL; not FPS/platform acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
W,H=1280,800

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    helper=load_module('scaffold_capture_slice',ROOT/'artifacts/alliance_blender_trio/evidence/capture_slice.py')
    batch=load_module('scaffold_batch',ROOT/'tools/diag_alliance_batch_review.py')
    paths=[p for folder in ('game','render','art/manifests','art/blender','assets/models','tools/art')
           for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    protected={str(p.relative_to(ROOT)):digest(p) for p in paths}
    helper.isolate(ROOT,out)
    sys.path.insert(0,str(ROOT))
    import numpy as np
    import pygame
    from OpenGL import GL
    import game.core.manager
    from game.benchmark import state_hash
    from render import asset_selection as selection
    from render.authored_mesh import _load_profile
    from render.camera import Camera
    from render.renderer import Renderer
    from PIL import Image,ImageDraw
    sheet=json.loads((ROOT/'art/manifests/pending/S06-BATCH-B9-CONSTRUCTION.json').read_text())
    asset=next(a for a in sheet['assets'] if a['binding']=='shared:construction_scaffold')
    candidate=_load_profile(ROOT/asset['mesh'],asset['identifier'],tuple(zip(*asset['envelope'])),asset['min_length'])
    selection.configure({})
    original=selection.mesh_for
    assert original(asset['binding']) is None
    active={'enabled':False,'mesh':candidate}
    selection.mesh_for=lambda b:active['mesh'] if active['enabled'] and b==asset['binding'] else original(b)
    report=dict(schema=1,status='pending_owner_appearance',binding=asset['binding'],
                scope='Review-only scoped mesh_for injection, production Renderer.draw and queued construction. No registration, platform, paced FPS or packaging acceptance.',
                source={k:v for k,v in protected.items() if k.startswith(('render/','game/'))},
                runtime_sha256=digest(ROOT/asset['mesh']),captures={},ablations={})
    pygame.display.init(); pygame.font.init()
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS,1)
    pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES,4)
    pygame.display.set_mode((W,H),pygame.OPENGL|pygame.DOUBLEBUF)
    GL.glViewport(0,0,W,H)
    report['gl']={k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]}
    report['samples']=int(GL.glGetIntegerv(GL.GL_SAMPLES)); assert report['samples']==4
    scenarios=[('imperial',.1),('imperial',.5),('imperial',.9),('rebel',.5),('confederacy',.5),('syndicate',.5)]
    tiles=[]; renderer=None
    try:
        for faction,progress in scenarios:
            data=next(a['data_id'] for a in sheet['assets'] if a['binding']==f'{faction}:constructor')
            owner=batch.FACTION_OWNER[faction]
            gm,st=batch.build_row_scene(helper,[('builder','ship',data,owner,[-330.,0.,250.],0.)],factions=(faction,))
            builder=next(iter(st.entities.values()))
            builder.build_queue=[dict(kind='station',item='shipyard',pos=[0.,0.,0.],time_left=100*(1-progress),total=100.)]
            initial=state_hash(st)
            cam=Camera(W,H); cam.bind_scene(st,lambda:owner,lambda:3.)
            geometry=helper.geometry(st)
            views=dict(close=dict(target=[0.,35.,0.],distance=630.,yaw=48.,pitch=35.),
                       tactical=dict(target=[0.,35.,0.],distance=1400.,yaw=48.,pitch=55.))
            key=f'{faction}-{progress:.1f}'; images={}; record=dict(initial_state_sha256=initial,views=views,variants={})
            for variant in ('before','after'):
                active['enabled']=variant=='after'; selection.invalidate_geometry_helpers()
                renderer=Renderer(st,cam); renderer.local_player=owner
                renderer.diff_render=True; renderer.time=3.
                assert not renderer.skip and renderer.materials.available
                def draw(view,name=None):
                    pygame.event.pump(); helper.configure(cam,view)
                    check=helper.camera_check(cam,st,[geometry],3.)
                    # Camera must also remain outside the scaffold's conservative world box.
                    eye=cam.eye_position(); radius=gm.ds.stations['shipyard'].radius
                    assert not (-radius<=eye[0]<=radius and 0<=eye[1]<=radius and -radius<=eye[2]<=radius)
                    renderer.draw(0.,set())
                    assert state_hash(st)==initial
                    GL.glFinish()
                    pixels=np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy()
                    assert GL.glGetError()==GL.GL_NO_ERROR
                    if name: Image.fromarray(pixels).save(out/name)
                    return pixels,check
                record['variants'][variant]={}
                for view_name,view in views.items():
                    for _ in range(3): draw(view)
                    name=f'{key}-{variant}-{view_name}.png'
                    pixels,check=draw(view,name); repeat,_=draw(view)
                    changed=int(np.any(pixels!=repeat,axis=2).sum())
                    assert changed==0,(key,variant,view_name,changed)
                    record['variants'][variant][view_name]=dict(file=name,sha256=digest(out/name),repeat_changed_pixels=changed,camera=check,state_sha256=state_hash(st))
                    images[variant,view_name]=pixels
                if faction=='imperial' and progress==.5 and variant=='after':
                    for role in ('accent','dark','cool'):
                        active['mesh']=dict(candidate); active['mesh'][role]=()
                        draw(views['close']); image,_=draw(views['close'],f'{key}-ablated-{role}.png')
                        changed=int(np.any(np.abs(image.astype(int)-images['after','close'].astype(int))>3,axis=2).sum())
                        report['ablations'][role]=dict(changed_pixels_gt3=changed)
                        assert changed>0,(role,changed)
                        active['mesh']=candidate
                renderer.close(); renderer=None
            record['comparison']={}
            for name in views:
                delta=np.any(np.abs(images['before',name].astype(int)-images['after',name].astype(int))>3,axis=2)
                count=int(delta.sum()); assert count>0,(key,name)
                record['comparison'][name]=dict(changed_pixels_gt3=count)
            report['captures'][key]=record
            for variant in ('before','after'):
                tile=Image.fromarray(images[variant,'close']); tile.thumbnail((600,375))
                framed=Image.new('RGB',(600,405),(12,17,25)); framed.paste(tile,(0,30))
                ImageDraw.Draw(framed).text((12,8),f'{faction} | {progress:.0%} construction | {variant.upper()}',fill='white')
                tiles.append(framed)
            print(key,record['comparison'],flush=True)
        grid=Image.new('RGB',(1200,405*len(scenarios)),(12,17,25))
        for index,tile in enumerate(tiles): grid.paste(tile,((index%2)*600,(index//2)*405))
        grid.save(out/'scaffold-appearance-grid.jpg',quality=92)
    finally:
        if renderer: renderer.close()
        selection.mesh_for=original
        selection.configure({})
        pygame.quit()
    after={str(p.relative_to(ROOT)):digest(p) for p in paths}
    assert after==protected,'protected inputs changed'
    assert selection.mesh_for(asset['binding']) is None
    report.update(protected_files_preserved=True,production_scaffold_unselected_after_review=True,
                  grid=dict(file='scaffold-appearance-grid.jpg',sha256=digest(out/'scaffold-appearance-grid.jpg')))
    (out/'metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(captures=len(report['captures']),ablations=report['ablations'],protected_files_preserved=True)))

if __name__=='__main__': main()
