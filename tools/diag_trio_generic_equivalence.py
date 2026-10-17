#!/usr/bin/env python3
"""S05 exact rendered-pixel and deterministic simulation equivalence.

No game/source changes. Each source/selection runs in a fresh, serial process.
"""
from pathlib import Path
import json
import argparse
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import traceback

W, H = 1280, 800
CONTROL = '5bddd7b67245ddff4b595bb3b477ca8ceede0a6c'
CANDIDATE = '7030dd252ddb4da3bb4f69fecb2f2028650ffe6c'


def part_spans(data):
    offsets = dict.fromkeys(data['batches'], 0)
    spans = {}
    for p in data['parts']:
        role, count = p['role'], p['triangles']
        if p['name'] in spans or type(count) is not int or count < 1:
            raise ValueError('ambiguous part metadata')
        start = offsets[role]
        spans[p['name']] = (role, start, start + count)
        offsets[role] += count
    if offsets != {k: len(v) for k, v in data['batches'].items()}:
        raise ValueError('part metadata does not cover all role triangles')
    return spans


def same_ticks(a, b):
    return bool(a) and [(r['tick'], r['sha256']) for r in a] == [(r['tick'], r['sha256']) for r in b]


def feature_metrics(full, absent, screen, kind):
    import numpy as np
    x, y = (round(v) for v in screen[:2])
    radius = 22
    x0, x1 = max(0, x-radius), min(full.shape[1], x+radius+1)
    y0, y1 = max(0, y-radius), min(full.shape[0], y+radius+1)
    a, b = full[y0:y1, x0:x1].astype(int), absent[y0:y1, x0:x1].astype(int)
    if a.size == 0:
        return dict(passed=False, visible_pixels=0, bbox=None, screen=[x, y])
    delta = a-b
    color = ((a[:,:,0] > a[:,:,2]*1.15) & (a[:,:,0] > 150)) if kind == 'warm' else ((a[:,:,2] > a[:,:,0]*1.15) & (a[:,:,2] > 150))
    mask = (delta.max(2) > 20) & color
    yy, xx = np.nonzero(mask)
    bbox = [int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())] if len(xx) else None
    passed = len(xx) >= 25 and bbox[2]-bbox[0] >= 5 and bbox[3]-bbox[1] >= 3
    return dict(passed=bool(passed), visible_pixels=len(xx), bbox=bbox, screen=[x,y], crop=[x0,y0,x1,y1])


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_user(root):
    paths = [root/'saves', root/'replays', root/'settings.json', root/'campaign.json', root/'balance.json']
    return {str(p): file_hash(p) for top in paths for p in ([top] if top.is_file() else sorted(top.rglob('*'))) if p.is_file()}


def child(args):
    import numpy as np
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True
    assert not os.environ.get('STAR_ARMADA_FIXED_MATERIALS')
    assert not os.environ.get('STAR_ARMADA_SKIP')
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy'
    recipe = load_module(source/'artifacts/alliance_blender_trio/evidence/capture_slice.py', 'trio_recipe')
    seal = recipe.manifest(source)
    recipe.isolate(source, output)
    import game.core
    import render
    assert Path(game.core.__file__).resolve().is_relative_to(source)
    assert Path(render.__file__).resolve().is_relative_to(source)
    from render import menus
    assert all(Path(getattr(menus,k)).is_relative_to(output) for k in ('USER_DIR','SAVES_DIR','SETTINGS_PATH','CAMPAIGN_PATH','BALANCE_PATH'))
    if args.selection != 'prototype':
        from render.asset_selection import configure
        configure({'model_preview': args.selection == 'preview'}, asset_root=source)
    import pygame
    from OpenGL import GL
    from render.camera import Camera
    from render.renderer import Renderer
    from game.benchmark import state_hash
    from game.core.skirmish import PLAYER_COLORS
    report = dict(selection=args.selection, source=str(source), source_manifest=seal, harness_sha256=file_hash(Path(__file__).resolve()),
                  frames=[], features=[], ticks=[], draw_checks=[], status='running', commands=[])
    r = None
    encoder = None
    peer = json.loads((args.peer/'summary.json').read_text()) if args.peer else None
    full_frames = []
    encoder_error = output/'encode.txt'
    try:
        pygame.display.init()
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        pygame.display.set_mode((W,H), pygame.OPENGL|pygame.DOUBLEBUF)
        GL.glEnable(GL.GL_DEPTH_TEST); GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glClearColor(.008,.012,.025,1.)
        assert tuple(GL.glGetIntegerv(GL.GL_VIEWPORT)) == (0,0,W,H)
        assert int(GL.glGetIntegerv(GL.GL_SAMPLES)) == 4
        assert int(GL.glGetIntegerv(GL.GL_SAMPLE_BUFFERS)) == 1
        report['display'] = dict(size=[W,H], samples=4, sample_buffers=1, driver=pygame.display.get_driver(),
                                **{k:GL.glGetString(v).decode() for k,v in [('vendor',GL.GL_VENDOR),('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]})
        gm, ids, scene = recipe.build_scene()
        report['recipe'] = scene
        st = gm.state
        cam = Camera(W,H)
        r = Renderer(st,cam)
        assert r.materials.available, r.materials.error
        assert not r.skip
        report['production_materials'] = True
        report['normal_fog'] = type(r.fog).__module__+'.'+type(r.fog).__name__
        r.diff_render, r.time = True, 3.
        from render.ship_sizes import ship_size
        from render.planet_building_geometry import station_frame
        from game.core import detmath as math
        model_payloads = {label: json.loads((source/f'assets/models/alliance_{asset}.mesh.json').read_text())
                          for label,asset in [('capital','battleship'),('escort','frigate'),('yard','shipyard')]}
        report['repeat_policy'] = dict(policy_id=POLICY_ID, max_channel_delta=1, max_changed_pixels=128,
                                      payload_sha256={label:file_hash(source/f'assets/models/alliance_{asset}.mesh.json') for label,asset in [('capital','battleship'),('escort','frigate'),('yard','shipyard')]})
        def protected_region(time):
            models = []
            for label,data in model_payloads.items():
                e = st.entities[ids[label]]
                if label == 'yard':
                    frame = station_frame(st,e,math.radians(time*3.))
                else:
                    ca,sa = math.cos(e.yaw),math.sin(e.yaw)
                    frame = (e.pos.to_tuple(),((ca,0.,-sa),(0.,1.,0.),(sa,0.,ca)),ship_size(gm.ds,e.data_id,'rebel').scale)
                models.append(dict(name=label, vertices=data['vertices'], frame=frame))
            return conservative_model_mask(cam,models)
        def pixels(spec, time=3.):
            recipe.configure(cam,spec)
            r.time = time
            pygame.event.pump()
            before = state_hash(st)
            r.draw(0.,{ids['capital']})
            after = state_hash(st)
            assert before == after, 'draw mutated simulation'
            report['draw_checks'].append(dict(tick=st.tick,before=before,after=after))
            GL.glFinish()
            assert GL.glGetError() == GL.GL_NO_ERROR
            return np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)[::-1].copy()
        def save(name, a):
            pygame.image.save(pygame.image.frombuffer(a.tobytes(),(W,H),'RGB'),str(output/(name+'.png')))
        def capture(name, spec, time=3., retain=False):
            # Warm caches, require a repeated frozen frame under the same state.
            for _ in range(3): pixels(spec,time)
            a=pixels(spec,time); b=pixels(spec,time)
            mask, proof = protected_region(time)
            repeated = repeat_metrics(a,b,mask)
            if repeated['changed_pixels']:
                prefix = ('ALLOWED-' if repeated['passed'] else 'FAILED-')+name
                save(prefix+'-first',a); save(prefix+'-repeat',b)
                save(prefix+'-protected-mask',np.repeat((mask.astype(np.uint8)*255)[:,:,None],3,axis=2))
                dump(output/(prefix+'.json'),dict(metrics=repeated,projection=proof))
            enforce_repeat(a,b,mask)
            if name == 'motion-0270-escort-close' and args.failure_pair:
                original = [np.transpose(pygame.surfarray.array3d(pygame.image.load(str(p))), (1,0,2)).copy() for p in args.failure_pair]
                diagnostic = dict(metrics=repeat_metrics(*original,mask), projection=proof, tick=st.tick,state=state_hash(st),view=spec,
                                  inputs={str(p):file_hash(p) for p in args.failure_pair})
                dump(output/'known-failure-replay.json',diagnostic)
                save('known-failure-protected-mask',np.repeat((mask.astype(np.uint8)*255)[:,:,None],3,axis=2))
            if not report['frames']:
                # Exercise the actual acceptance gates on this real rendered image.
                controls = {}
                outside = np.argwhere(~mask); inside = np.argwhere(mask)
                for key,coords,amplitude,count in [('background-1',outside,1,1),('background-2',outside,2,1),('background-129',outside,1,129),('protected-1',inside,1,1)]:
                    assert len(coords) >= count
                    modified = a.copy()
                    for y,x in coords[:count]: modified[y,x,0] = int(a[y,x,0])+amplitude if a[y,x,0] <= 255-amplitude else int(a[y,x,0])-amplitude
                    try: enforce_repeat(a,modified,mask); accepted=True
                    except AssertionError: accepted=False
                    controls[key]=dict(accepted=accepted,metrics=repeat_metrics(a,modified,mask))
                    if key=='background-1':
                        try: enforce_exact(a,modified); cross_accepted=True
                        except AssertionError: cross_accepted=False
                        controls['cross-source-1']=dict(accepted=cross_accepted)
                assert {k:v['accepted'] for k,v in controls.items()} == {'background-1':True,'background-2':False,'background-129':False,'protected-1':False,'cross-source-1':False}
                report['policy_negative_controls']=controls
            row=dict(name=name,view=spec,time=time,tick=st.tick,state=state_hash(st),pixels_sha256=hashlib.sha256(a.tobytes()).hexdigest(),
                     repeat=repeated,protected_projection=proof,
                     actual_eye=list(cam.eye_position()),view_matrix=np.asarray(cam._view).tolist(),projection_matrix=np.asarray(cam._proj).tolist())
            index=len(report['frames'])
            if peer:
                prior=peer['frames'][index]
                assert all(prior[k]==row[k] for k in ('name','view','time','tick','state'))
                if args.selection=='preview':
                    assert all(prior[k]==row[k] for k in ('actual_eye','view_matrix','projection_matrix'))
                old=np.load(args.peer/'frames'/f'{index:04d}.npy')
                row['comparison']=pixel_metrics(old,a)
                if args.selection=='preview' and name.startswith('motion-'):
                    pair=np.concatenate((old,a),axis=1)
                    surf=pygame.image.frombuffer(pair.tobytes(),(W*2,H),'RGB')
                    surf=pygame.transform.smoothscale(surf,(W,H//2))
                    # Labels make source sides explicit in the paired movie.
                    font=pygame.font.Font(None,22)
                    surf.blit(font.render('PROTOTYPE CONTROL',True,'white'),(8,8))
                    surf.blit(font.render('GENERIC PREVIEW',True,'white'),(W//2+8,8))
                    encoder.stdin.write(pygame.image.tobytes(surf,'RGB'))
            else:
                directory=output/'frames'; directory.mkdir(exist_ok=True)
                np.save(directory/f'{index:04d}.npy',a)
            if retain: save(name,a)
            report['frames'].append(row)
            return a
        views=('common-scale','capital-close','escort-close','yard-close','capital-rear','escort-rear','yard-rear','tactical','capital-engine','escort-engine')
        recipe.VIEWS['escort-engine']=dict(recipe.VIEWS['escort-rear'],yaw=178.,pitch=8.)
        for name in views:
            capture('initial-'+name,recipe.VIEWS[name],retain=True)
        report['palette'] = {k:list(v) for k,v in PLAYER_COLORS.items()}
        # All supported palette colours, each approved binding's close view plus common scale.
        original=st.players[0].color
        for color,value in PLAYER_COLORS.items():
            st.players[0].color=value
            for name in ('capital-close','escort-close','yard-close','common-scale'):
                capture('palette-'+color+'-'+name,recipe.VIEWS[name],retain=color==next(iter(PLAYER_COLORS)) and name=='common-scale')
        st.players[0].color=original
        if args.selection != 'legacy':
            from render.faction_ships import ship_mesh
            from render.faction_stations import station_mesh
            from render.planet_building_geometry import station_frame
            from render.ship_sizes import ship_size
            from game.core import detmath as math
            for asset,label,view in [('shipyard','yard','yard-close'),('battleship','capital','capital-engine'),('frigate','escort','escort-engine')]:
                data=json.loads((source/f'assets/models/alliance_{asset}.mesh.json').read_text())
                spans=part_spans(data)
                mesh=station_mesh('rebel',asset) if label=='yard' else ship_mesh('rebel',asset)
                spec=dict(recipe.VIEWS['escort-rear'],yaw=178.,pitch=8.) if view=='escort-engine' else recipe.VIEWS[view]
                full=pixels(spec)
                save('features-'+asset,full)
                for name,(role,start,end) in spans.items():
                    if not (name.startswith('Worklight exposed lens') if label=='yard' else 'emitter' in name.lower()): continue
                    triangles=mesh[role][start:end]
                    points=[p for _,tri in triangles for p in tri]
                    center=[(min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3)]
                    e=st.entities[ids[label]]
                    if label=='yard':
                        center=next(f['center'] for f in data['features']['worklights'] if f['name']==name)
                        origin,basis,scale=station_frame(st,e,math.radians(9.))
                        world=[origin[j]+scale*sum(basis[k][j]*center[k] for k in range(3)) for j in range(3)]
                    else:
                        scale=ship_size(gm.ds,e.data_id,'rebel').scale
                        # Match _draw_ship_role_batch's translate/rotate/scale; initial yaw is zero.
                        assert e.yaw==0.
                        world=[e.pos.x+scale*center[0],e.pos.y+scale*center[1],e.pos.z+scale*center[2]]
                    screen=cam.world_to_screen(*world)
                    lst=GL.glGenLists(1)
                    GL.glNewList(lst,GL.GL_COMPILE)
                    r._emit_detail_mesh(mesh[role][:start]+mesh[role][end:])
                    GL.glEndList()
                    old_station,old_ship=r._station_detail_list,r._ship_display_list
                    try:
                        if label=='yard':
                            r._station_detail_list=lambda did, ro, faction='imperial': lst if (did,ro,faction)==('shipyard',role,'rebel') else old_station(did,ro,faction)
                        else:
                            r._ship_display_list=lambda shape: lst if shape=='rebel:'+asset+'_'+role else old_ship(shape)
                        absent=pixels(spec)
                    finally:
                        r._station_detail_list,r._ship_display_list=old_station,old_ship
                        GL.glDeleteLists(lst,1)
                    # Override occurs at actual list lookup (no stale CPU/GPU cache mutation).
                    restored=pixels(spec)
                    assert np.array_equal(full,restored),'ablation leaked into restored render'
                    metric=feature_metrics(full,absent,screen,'warm' if label=='yard' else 'cool')
                    metric.update(asset=asset,name=name,role=role,span=[start,end],world=world,view=spec,
                                  global_difference=pixel_metrics(full,absent),restored_equal=True,
                                  full_pixels_sha256=hashlib.sha256(full.tobytes()).hexdigest(),
                                  absent_pixels_sha256=hashlib.sha256(absent.tobytes()).hexdigest())
                    metric['negative_control_fails']=not feature_metrics(absent,absent,screen,'warm' if label=='yard' else 'cool')['passed']
                    index=len(report['features'])
                    save('feature-absent-'+str(index),absent)
                    report['features'].append(metric)
        if args.selection=='preview':
            pygame.font.init()
            if not shutil.which('ffmpeg'): raise RuntimeError('ffmpeg not installed; no movie encoder')
            encoder=subprocess.Popen([shutil.which('ffmpeg'),'-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H//2}','-r','12','-i','-','-an','-c:v','libx264','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'paired-motion.mp4')],stdin=subprocess.PIPE,stdout=encoder_error.open('ab'),stderr=encoder_error.open('ab'))
        events=[]
        st.events.subscribe('weapon_fired',lambda event:events.append(dict(tick=st.tick,data=dict(event.data))))
        start_entities=recipe.stats(st,ids)
        report['ticks'].append(dict(tick=st.tick,sha256=state_hash(st)))
        class Commands:
            def write(self,text): report['commands'].append(json.loads(text))
            def flush(self): pass
        commands=Commands()
        motion_views=('common-scale','capital-close','escort-close','yard-close')
        for tick in range(1,361):
            recipe.issue(gm,tick,commands)
            gm.step(recipe.DT)
            assert st.tick==tick,'simulation stopped early'
            stats=recipe.stats(st,ids)
            row=dict(tick=tick,sha256=state_hash(st),projectiles=len(st.projectiles),entities=stats)
            report['ticks'].append(row)
            if tick%6==0:
                name=motion_views[((tick//6)-1)//15]
                spec=dict(recipe.VIEWS[name])
                # Ships are followed as they move; station stays static amid the battle.
                label={'capital-close':'capital','escort-close':'escort','yard-close':'yard'}.get(name)
                if label: spec['target']=list(st.entities[ids[label]].pos.to_tuple())
                spec['yaw']+=tick/360*18
                capture(f'motion-{tick:04d}-{name}',spec,3.+tick*recipe.DT,retain=tick in (6,96,186,276,360))
        report['activity']=dict(weapon_fired=len(events),commands=len(report['commands']),projectiles_observed=any(t.get('projectiles',0)>0 for t in report['ticks']),
            movement_observed=any(any(t['entities'][k]['pos']!=v['pos'] for k,v in start_entities.items() if k in ('capital','escort')) for t in report['ticks'][1:]),
            damage_observed=any(any(t['entities'][k]['hull']<v['hull'] or sum(t['entities'][k]['shields'].values())<sum(v['shields'].values()) for k,v in start_entities.items() if k!='planet') for t in report['ticks'][1:]))
        assert all(report['activity'].values()), report['activity']
        if peer:
            report['per_tick_equal']=same_ticks(peer['ticks'],report['ticks'])
            assert report['per_tick_equal'],'per-tick digest divergence'
        report['status']='measured'
    except BaseException as exc:
        report.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
        raise
    finally:
        if encoder:
            encoder.stdin.close()
            report['encoder_exit']=encoder.wait()
        if r: r.close()
        pygame.display.quit()
        if pygame.font.get_init(): pygame.font.quit()
        report['source_preserved']=recipe.manifest(source)==seal
        dump(output/'summary.json',report)
        assert report['source_preserved'],'source changed during capture'


def archive_sources(root, snapshots):
    """Archive pinned commits, independently of HEAD and dirty owner work."""
    revisions = [('control', CONTROL), ('candidate', CANDIDATE)]
    for variant, revision in revisions:
        try:
            subprocess.run(['git', 'cat-file', '-e', revision+'^{commit}'],
                           cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f'missing pinned {variant} revision {revision}; fetch its Git history') from exc
    snapshots.mkdir()
    receipts = {}
    for variant, revision in revisions:
        target = snapshots/variant
        target.mkdir()
        with subprocess.Popen(['git', 'archive', revision], cwd=root, stdout=subprocess.PIPE) as archive:
            try:
                subprocess.run(['tar', '-x', '-C', str(target)], stdin=archive.stdout, check=True)
            finally:
                archive.stdout.close()
            if archive.wait() != 0:
                raise RuntimeError(f'git archive failed for pinned {variant} revision {revision}')
        receipts[variant] = dict(revision=revision, source=str(target))
    return receipts


def approved_pins(receipts):
    """Bind historical asset proof to the sealed candidate's own manifest."""
    candidate = Path(receipts['candidate']['source'])
    pins = json.loads((candidate/'art/manifests/approved-trio-source-hashes.json').read_text())
    # Only source/exporter/approved-runtime pins; integration render changes are expected.
    return {p:h for p,h in pins.items() if p.startswith(('art/blender/','tools/art/','assets/models/'))}


def preservation_roots(root, user_roots=()):
    """Inventory the checkout, any conventional live tree, and selected user roots."""
    owner = Path.home()/'Downloads/Project/STAR-ARMADA'
    roots = [root] + ([owner] if owner.exists() else []) + list(user_roots)
    return list(dict.fromkeys(p.resolve() for p in roots))


def orchestrate(args):
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    snapshots=output/'sources'
    preserved_roots=preservation_roots(root,args.user_root)
    before={str(p):snapshot_user(p) for p in preserved_roots}
    dump(output/'user-before.json',before)
    receipts=archive_sources(root,snapshots)
    approved=approved_pins(receipts)
    hashes={k:{p:file_hash(Path(v['source'])/p) for p in approved} for k,v in receipts.items()}
    e1=hashes['control']==hashes['candidate']==approved
    dump(output/'source-receipts.json',dict(sources=receipts,approved_pins=approved,actual=hashes,E1=e1))
    commands=[]
    try:
        for variant,selection in [('control','prototype'),('candidate','preview'),('legacy','legacy')]:
            src=snapshots/('control' if variant=='control' else 'candidate')
            command=[sys.executable,str(Path(__file__).resolve()),'capture','--source',str(src),'--output',str(output/variant),'--selection',selection]
            if args.scratch_root is not None:
                command+=['--scratch-root',str(args.scratch_root.resolve())]
            if variant!='control':command+=['--peer',str(output/'control')]
            if getattr(args, 'failure_pair', None): command+=['--failure-pair', *[str(p.resolve()) for p in args.failure_pair]]
            commands.append(command)
            dump(output/'commands.json',commands)
            with (output/(variant+'-execution.txt')).open('wb') as log:
                subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
        a,b,c=[json.loads((output/k/'summary.json').read_text()) for k in ('control','candidate','legacy')]
        assert {f['name'] for f in a['frames']}=={f['name'] for f in b['frames']}=={f['name'] for f in c['frames']}
        palette_distinct=all(len({f['pixels_sha256'] for f in b['frames'] if f['name'].startswith('palette-') and f['name'].endswith(view)})==len(b['palette'])
                             for view in ('capital-close','escort-close','yard-close','common-scale'))
        gates=dict(E1=e1,E2=a['display']==b['display'] and all(f['comparison']['changed_pixels']==0 for f in b['frames']),
                   E3=palette_distinct and bool(b['palette']) and all(f['comparison']['changed_pixels']==0 for f in b['frames'] if f['name'].startswith('palette-')) and all(f['comparison']['changed_pixels']>0 for f in c['frames']),
                   E4=b['per_tick_equal'] and all(b['activity'].values()) and (output/'candidate/paired-motion.mp4').is_file() and b.get('encoder_exit')==0,
                   E5=a['features']==b['features'] and len(a['features'])==len(b['features'])==8 and all(f['passed'] and f['negative_control_fails'] for s in (a,b) for f in s['features']),
                   E6=False)
        dump(output/'summary.json',dict(status='pending-image-inspection' if all(v for k,v in gates.items() if k!='E6') else 'blocked',gates=gates,
             frames=len(b['frames']),ticks=len(b['ticks']),sources=receipts,features=b['features'],activity=b['activity'],commands=commands,
             inspection='Pending independent inspection of exported selected captures; no approval recorded.'))
    except BaseException as exc:
        dump(output/'failure.json',dict(error=repr(exc),traceback=traceback.format_exc(),commands=commands))
        raise
    finally:
        after={str(p):snapshot_user(p) for p in preserved_roots}
        dump(output/'user-after.json',after)
        dump(output/'user-preservation.json',dict(before=before,after=after,equal=before==after))
        assert before==after,'user files changed'


def guard_output(output, scratch_root=None):
    """Never fall back to a system temporary directory or escape scratch."""
    scratch = (scratch_root or Path.home()/'.hermes/cache/scratch').resolve()
    output = output.resolve()
    if output == scratch or not output.is_relative_to(scratch):
        raise ValueError(f'output must be below selected scratch root: {scratch}')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['run','capture'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--selection',choices=['prototype','preview','legacy'])
    parser.add_argument('--peer',type=Path)
    parser.add_argument('--failure-pair',type=Path,nargs=2,help='immutable original failed repeat PNG pair, diagnostic only')
    parser.add_argument('--user-root',type=Path,action='append',default=[],
                        help='additional user-data root to inventory (repeatable)')
    parser.add_argument('--scratch-root',type=Path,
                        help='output workspace (default: ~/.hermes/cache/scratch)')
    args=parser.parse_args()
    args.output=guard_output(args.output,args.scratch_root)
    if args.mode=='run':orchestrate(args)
    else:child(args)


POLICY_ID = 's05-background-repeatability-2026-10-16'


def conservative_model_mask(cam, models):
    """An unprojectable instance removes the allowance for the entire frame."""
    import numpy as np
    try:
        return projected_model_mask(cam, models)
    except ValueError as exc:
        mask = np.ones((cam.height,cam.width), bool)
        return mask, dict(fail_closed=True,reason=str(exc),protected_pixels=int(mask.sum()),
                          model_names=[m['name'] for m in models],
                          mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest())


def projected_model_mask(cam, models, padding=8):
    """Project full immutable payload AABB corners, with all roles included.

    Positive-depth perspective extrema of a convex box occur at its vertices.
    Clip only after projection; near-plane intersections are refused, not omitted.
    """
    import numpy as np
    import math
    import itertools
    try:
        if type(cam.width) is not int or type(cam.height) is not int or min(cam.width, cam.height) <= 0:
            raise ValueError('invalid image dimensions')
        if type(padding) is not int or padding < 8 or not models:
            raise ValueError('invalid protected region inputs')
        eye = np.asarray(cam.eye_position(), dtype=float)
        camera_basis = np.asarray(cam.basis(), dtype=float)
        near, fov = float(cam.near), float(cam.fov)
        if eye.shape != (3,) or camera_basis.shape != (3,3) or not np.isfinite(eye).all() or not np.isfinite(camera_basis).all() or not math.isfinite(near) or not math.isfinite(fov) or near <= 0 or not 0 < fov < 179:
            raise ValueError('invalid camera')
        mask = np.zeros((cam.height, cam.width), bool)
        records = []
        with np.errstate(all='raise'):
            for model in models:
                vertices = np.asarray(model['vertices'], dtype=float)
                origin, basis, scale = model['frame']
                origin, basis, scale = np.asarray(origin, dtype=float), np.asarray(basis, dtype=float), float(scale)
                if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices) or origin.shape != (3,) or basis.shape != (3,3) or not all(np.isfinite(v).all() for v in (vertices,origin,basis)) or not math.isfinite(scale) or scale <= 0:
                    raise ValueError('invalid model transform/vertices')
                lo, hi = vertices.min(0), vertices.max(0)
                corners = np.array(list(itertools.product(*zip(lo, hi))))
                world = origin + scale * (corners @ basis)
                relative = (world-eye) @ camera_basis.T
                if not np.isfinite(relative).all() or np.any(relative[:,2] <= near):
                    raise ValueError('protected geometry crosses near plane')
                factor = cam.height/2 / math.tan(math.radians(fov)/2)
                xy = np.column_stack((cam.width/2+relative[:,0]/relative[:,2]*factor,
                                      cam.height/2-relative[:,1]/relative[:,2]*factor))
                if not np.isfinite(xy).all(): raise ValueError('invalid projection')
                x0,y0 = [int(math.floor(v))-padding for v in xy.min(0)]
                x1,y1 = [int(math.ceil(v))+padding+1 for v in xy.max(0)]
                clipped = [max(0,min(cam.width,x0)),max(0,min(cam.height,y0)),max(0,min(cam.width,x1)),max(0,min(cam.height,y1))]
                a,b,c,d = clipped
                mask[b:d,a:c] = True
                records.append(dict(name=model['name'], local_bounds=[lo.tolist(),hi.tolist()],
                                    frame=[origin.tolist(),basis.tolist(),scale], projected_corners=xy.tolist(),
                                    unclipped_bbox=[x0,y0,x1,y1], clipped_bbox=clipped))
        return mask, dict(padding_pixels=padding, models=records, protected_pixels=int(mask.sum()),
                          mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest())
    except (TypeError, KeyError, IndexError, OverflowError, FloatingPointError) as exc:
        raise ValueError('unusable protected projection') from exc


def repeat_metrics(a, b, protected):
    """Capture-only allowance; all other image comparisons remain exact."""
    import numpy as np
    for image in (a, b):
        if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or not image.size:
            raise ValueError('nonempty uint8 RGB image required')
    if not isinstance(protected, np.ndarray) or protected.dtype != np.bool_ or protected.shape != a.shape[:2]:
        raise ValueError('boolean image-sized protected mask required')
    result = pixel_metrics(a, b)
    changed = np.any(a != b, axis=2)
    yy, xx = np.nonzero(changed)
    protected_changes = int(np.count_nonzero(changed & protected))
    result.update(policy_id=POLICY_ID, max_allowed_channel_delta=1, max_allowed_changed_pixels=128,
                  protected_changes=protected_changes,
                  changed_bbox=[int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())] if len(xx) else None,
                  passed=result['max_channel_delta'] <= 1 and result['changed_pixels'] <= 128 and protected_changes == 0)
    return result


def enforce_repeat(a, b, protected):
    result = repeat_metrics(a, b, protected)
    assert result['passed'], 'capture repeat policy failed: '+str(result)
    return result


def enforce_exact(a, b):
    result = pixel_metrics(a, b)
    assert result['changed_pixels'] == 0, 'strict cross-source pixel divergence: '+str(result)
    return result


def pixel_metrics(a, b):
    import numpy as np
    if a.shape != b.shape or a.ndim != 3 or a.shape[2] != 3:
        raise ValueError('paired RGB dimensions differ')
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return dict(changed_pixels=int(np.any(delta, axis=2).sum()),
                changed_channels=int(np.count_nonzero(delta)),
                max_channel_delta=int(delta.max()), mean_channel_delta=float(delta.mean()))


if __name__=='__main__':main()
