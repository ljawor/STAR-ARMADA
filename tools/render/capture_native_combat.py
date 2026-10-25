"""Capture a small real fight through main.py and its embedded native presentation path.

Fixture-only spawn/attack orders, stock weapons/physics, all persistence redirected. No capture
changes to fog, shaders or ownership. Hidden SDL window; stops before touching an owner's game.
Run under an external process-group deadline (as with other native acceptance tools).
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--distance',type=float,default=1600)
    parser.add_argument('--frames',type=int,default=360)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.chdir(ROOT)
    os.environ['SDL_VIDEODRIVER']='cocoa' if sys.platform=='darwin' else os.environ.get('SDL_VIDEODRIVER','windows')
    os.environ['SDL_AUDIODRIVER']='dummy'
    from tools.render.capture_native_notification_hud_game import require_no_owner_game
    require_no_owner_game()
    import game.core
    import pygame
    from PIL import Image
    from render import menus
    from render_bridge import embedded
    from game.benchmark import state_hash
    from game.core.manager import GameManager
    from game.core.commands import PlayerCommand
    from game.core.vectors import Vec3
    encoder=shutil.which('ffmpeg')
    assert encoder,'ffmpeg required; no fabricated animation fallback'
    user=out/'user';(user/'saves').mkdir(parents=True,exist_ok=True)
    settings=dict(menus.DEFAULT_SETTINGS,resolution='1280x800',fullscreen=False,
        music_volume=0.,sfx_volume=0.,autosave=False,cinematics_enabled=False,tutorial_hints=False)
    (user/'saves/settings.json').write_text(json.dumps(settings))
    paths=dict(USER_DIR=user,SAVES_DIR=user/'saves',SETTINGS_PATH=user/'saves/settings.json',
        CAMPAIGN_PATH=user/'saves/campaign.json',BALANCE_PATH=user/'saves/balance.json')
    real_start=GameManager.start_skirmish
    real_present=embedded.EmbeddedWindow.present
    real_init=embedded.EmbeddedWindow.__init__
    real_mode=pygame.display.set_mode
    windows=[]; rows=[]; seen=set(); best=-1; proc=None
    recipe=[]
    def start(map_def,*a,**kw):
        definition=copy.deepcopy(map_def)
        for key in ('planets','asteroid_fields','gas_giants'): definition[key]=[]
        definition['players']=definition['players'][:2]
        for i,p in enumerate(definition['players']):
            p.update(slot=i,is_ai=False,team=i,faction=('imperial','rebel')[i],start_units={})
        gm=real_start(definition,*a,**kw)
        groups=[]
        for owner,faction in enumerate(('imperial','rebel')):
            sign=-1 if owner==0 else 1
            fleet=[]
            for role,x,y,z in [('cruiser',400,0,-100),('frigate',420,60,120),
                                ('tie_bomber_squadron' if owner==0 else 'y_squadron',330,30,0)]:
                key=f'{faction}_{role}'
                pos=Vec3(sign*x,y,sign*z)
                hull=gm.factory.spawn_ship(key,owner,pos,yaw=-sign*1.5707963267948966)
                fleet.append(hull)
                recipe.append(dict(data_id=key,owner=owner,pos=pos.to_tuple()))
            groups.append(fleet)
        gm.visibility.update()
        for owner,fleet in enumerate(groups):
            gm.state.command_queue.append(PlayerCommand('attack',player=owner,
                unit_ids=tuple(e.id for e in fleet),target_id=groups[1-owner][0].id))
        for _ in range(30):gm.step(1/30)
        return gm
    def init(window,argv,*,root):
        argv=list(argv)+['--focus','0,0,0','--distance',str(args.distance),'--pitch','35','--yaw','15',
                         '--report',str(out/'native-viewer.json')]
        return real_init(window,argv,root=root)
    def mode(size,flags=0,*a,**kw):
        return real_mode(size,(flags & ~pygame.FULLSCREEN)|pygame.HIDDEN,*a,**kw)
    def present(window):
        nonlocal best,proc
        ns=sys._getframe(1).f_globals
        st=ns['state'];gm=ns['gm']
        before=state_hash(st)
        result=real_present(window)
        assert state_hash(st)==before,'Presentation mutated simulation'
        assert not ns['CPP']['failed'],ns['CPP']['failed']
        if window not in windows:windows.append(window)
        raw=bytes(window._pixels)
        if proc is None:
            proc=subprocess.Popen([encoder,'-y','-v','error','-f','rawvideo','-pix_fmt','bgra',
                '-s',f'{window.size[0]}x{window.size[1]}','-r','60','-i','-','-an',
                '-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(out/'battle.mp4')],stdin=subprocess.PIPE)
        proc.stdin.write(raw)
        types={gm.ds.resolve_weapon(p.weapon_id).type for p in st.projectiles.values()}
        seen.update(types)
        rows.append(dict(frame=len(rows),tick=st.tick,simulation_seconds=st.time,
            projectiles=len(st.projectiles),weapon_types=sorted(types),state_sha256=before,
            hull_and_shield=sum(e.hull+e.total_shield() for e in st.entities.values() if e.alive)))
        if len(st.projectiles)>best:
            best=len(st.projectiles)
            Image.frombytes('RGBA',window.size,raw,'raw','BGRA').convert('RGB').save(out/'battle.png')
        if len(rows)>=args.frames:pygame.event.post(pygame.event.Event(pygame.QUIT))
        return result
    try:
        with patch.multiple(menus,**{k:str(v) for k,v in paths.items()}), \
             patch.object(GameManager,'start_skirmish',side_effect=start), \
             patch.object(pygame.display,'set_mode',side_effect=mode), \
             patch.object(embedded.EmbeddedWindow,'__init__',init), \
             patch.object(embedded.EmbeddedWindow,'present',present), \
             patch.object(sys,'argv',[str(ROOT/'main.py'),'--skirmish']):
            runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
    finally:
        if proc is not None:
            proc.stdin.close()
            try:code=proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait();raise
            assert code==0,code
    assert len(rows)>=args.frames, len(rows)
    assert windows and all(w._process.poll() is not None for w in windows),'Native worker leaked'
    native=json.loads((out/'native-viewer.json').read_text())
    assert native['emissive']['flight_primitives']>0,'No FLIGHT geometry reached native draw'
    assert native['emissive']['decode_failures']==0,'Native emission decode failed'
    assert native['emissive']['dropped_vertices']==0,'Native emission geometry overflow'
    assert best>0,'No real weapon fire'
    assert rows[-1]['tick']>rows[0]['tick'],'Simulation never advanced'
    assert min(r['hull_and_shield'] for r in rows)<rows[0]['hull_and_shield'],'No real damage'
    report=dict(frames=len(rows),distance=args.distance,weapon_types=sorted(seen),
        max_projectiles=best,native_emissive=native['emissive'],
        all_presentations_state_identical=True,all_workers_reaped=True,
        head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ['render/emissive_batch.py','render_bridge/emissive.py','render_cpp/src/viewer.cpp',
             'render_cpp/include/projectile_effects.hpp','render_cpp/include/emissive.hpp']},fixture=recipe,rows=rows)
    (out/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','fixture')},indent=2))


if __name__=='__main__':main()
