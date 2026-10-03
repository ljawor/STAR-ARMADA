"""Real-window model probe. Export main renderer, never reset the working tree.

PYTHONPATH=. .venv/bin/python tools/diag_fleet_detail.py --out saves/fleet_detail --label before --renderer OLD.py
PYTHONPATH=. .venv/bin/python tools/diag_fleet_detail.py --out saves/fleet_detail --label after --compare saves/fleet_detail/before_metrics.json
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pygame
from PIL import Image, ImageDraw
from OpenGL import GL
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.entity import Entity, QUADRANTS
from game.core.vectors import Vec3
from render.camera import Camera
from tools.diag_modern_fleet import checksum

W, H = 960, 720
SHIPS = ['imperial_tie_squadron', 'imperial_corvette', 'imperial_cruiser',
         'imperial_battleship', 'imperial_constructor']
STATIONS = ['command_station', 'shipyard', 'defense_platform', 'research_station',
            'mining_station', 'sensor_station', 'trade_station', 'fighter_platform',
            'repair_dock', 'energy_relay']
EXTENTS = dict(zip(SHIPS, [38, 52, 94, 110, 32]))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--label', default='after')
    ap.add_argument('--renderer', type=Path)
    ap.add_argument('--compare', type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.renderer:
        spec = importlib.util.spec_from_file_location('render.fleet_baseline', args.renderer)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        import render.renderer as module
    pygame.init()
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(20)
    GL.glEnable(GL.GL_DEPTH_TEST)
    GL.glClearColor(.008, .012, .025, 1)
    ds = DataStore.get()
    st = GameManager.start_skirmish(ds.maps['skirmish01']).state
    st.entities.clear()
    cam = Camera(W, H)
    r = module.Renderer(st, cam)
    r.diff_render, r.time = True, 3.0
    r.skip = {'starfield','star','planets','nebulas','jumppoints','rings','sites','effects','projectiles','shields'}
    caps = {n: GL.glGetString(v).decode() for n,v in [('renderer',GL.GL_RENDERER),('version',GL.GL_VERSION)]}
    metrics = {'caps':caps, 'subjects':{}, 'label':args.label}
    grid = Image.new('RGB', (1800, 870))
    def entity(did, idx, owner=0, pos=(0,0,0)):
        station = did in ds.stations
        data = (ds.stations if station else ds.ships)[did]
        e = Entity(id=9000+idx, kind='station' if station else 'ship', owner=owner,
                   data_id=did, radius=data.radius, pos=Vec3(*pos))
        e.is_ship, e.is_station, e.is_squadron = not station, station, False
        e.yaw = .55
        # Real derived combat fields are required for tactical shield evidence.
        e.max_shield_quad = 100
        e.shields = {q:100 for q in QUADRANTS}
        return e
    def capture():
        cam.apply(W,H)
        r.draw(0,set())
        GL.glFinish()
        assert GL.glGetError() == 0, 'GL error'
        assert int(GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM)) == 0, 'shader leaked'
        a = np.flipud(np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)).copy()
        return a
    def save(a,name):
        path = args.out / f'{args.label}_{name}.png'
        Image.fromarray(a).save(path)
        return str(path)
    for i,did in enumerate(SHIPS+STATIONS):
        st.entities.clear()
        e = entity(did,i, i%2)
        st.entities[e.id] = e
        cam.target = [0,0,0]
        cam.yaw, cam.pitch = 32, 30
        half = e.radius*1.8 if e.is_station else EXTENTS[did]*ds.ship_visual(did)['scale']*max(1,e.radius/40)
        cam.distance = half*4.3
        original = checksum(st)
        capture()  # Prime lazy lists and inherited compatibility state.
        capture()
        a = capture()
        assert np.array_equal(a,capture()), 'non-deterministic frozen frame'
        assert checksum(st) == original, 'view mutated sim'
        path = save(a,did)
        lit = int((a.max(2)>45).sum())
        warm = int(((a[:,:,0]>200)&(a[:,:,1]>120)&(a[:,:,2]<180)).sum())
        colors = len(np.unique(a.reshape(-1,3),axis=0))
        assert lit>1000 and colors>20, (did,lit,colors)
        metrics['subjects'][did] = {'lit':lit,'warm':warm,'colors':colors,'image':path,'checksum':original}
        rear_yaw = cam.yaw
        cam.yaw += 180
        rear = capture()
        rear_path = save(rear, did + '_rear')
        cam.yaw = rear_yaw
        metrics['subjects'][did]['rear_image'] = rear_path
        if not args.renderer:
            # Ablate the actual light lists; thresholds must measure the light
            # mechanism, not bright alloy/specular pixels coincidentally nearby.
            light_lists = {value for key,value in r.ship_lists.items()
                           if isinstance(key,str) and
                           (key.endswith(('_lit','_cool',':lit',':cool')))}
            call_list = module.glCallList
            try:
                module.glCallList = lambda value: None if value in light_lists else call_list(value)
                unlit = capture()
                cam.yaw += 180
                rear_unlit = capture()
                cam.yaw = rear_yaw
            finally:
                module.glCallList = call_list
                cam.yaw = rear_yaw
            difference = np.abs(a.astype(int)-unlit.astype(int)).max(2)
            warm_mask = (a[:,:,0]>200)&(a[:,:,1]>120)&(a[:,:,2]<180)
            cool_mask = (a[:,:,2]>220)&(a[:,:,0]<150)&(a[:,:,1]>160)
            visible_warm = int((warm_mask & (difference>30)).sum())
            rear_difference = np.abs(rear.astype(int)-rear_unlit.astype(int)).max(2)
            rear_cool = (rear[:,:,2]>220)&(rear[:,:,0]<150)&(rear[:,:,1]>160)
            visible_cool = int((cool_mask & (difference>30)).sum() +
                               (rear_cool & (rear_difference>30)).sum())
            metrics['subjects'][did].update(warm_light_pixels=visible_warm,cool_light_pixels=visible_cool)
            assert visible_warm>10,(did,'warm glazing buried',visible_warm)
            assert visible_cool>10,(did,'cool nozzles/bays buried',visible_cool)
        tile = Image.fromarray(a).crop(((W-360)//2,(H-270)//2,(W+360)//2,(H+270)//2))
        ImageDraw.Draw(tile).text((8,8),did,fill='white')
        grid.paste(tile,((i%5)*360,(i//5)*290))
        print('SUBJECT',did,metrics['subjects'][did])
    grid.save(args.out/f'{args.label}_closeup_grid.png')
    st.entities.clear()
    cam.target, cam.yaw, cam.pitch, cam.distance = [0,0,0], 0, 35, 6200
    for i,did in enumerate(['research_station','shipyard']+SHIPS):
        pos = [(-600,0,-500),(600,0,-500),(-1450,0,1700),
               (-600,0,1500),(-1200,0,100),(1900,0,-1600),(800,0,1500)][i]
        e = entity(did,i, i%2,pos)
        st.entities[e.id]=e
    original=checksum(st)
    # Preserve standing shields in this tactical view, just as in the game.
    r.skip.discard('shields')
    a=capture()
    metrics['tactical']={'image':save(a,'tactical'),'lit':int((a.max(2)>45).sum()),'checksum':original}
    assert checksum(st)==original
    r.skip.add('shields')
    a=capture()
    metrics['tactical_hulls']={'image':save(a,'tactical_hulls'),'lit':int((a.max(2)>45).sum())}
    assert metrics['tactical_hulls']['lit']>300
    # Warm cached render benchmark includes stations as well as ships.
    st.entities.clear()
    cam.distance=16000
    for i in range(150):
        did = STATIONS[i%10] if i%5==0 else SHIPS[2]
        e=entity(did,i,i%2,((i%15-7)*700,0,(i//15-5)*850))
        st.entities[e.id]=e
    for _ in range(5): capture()
    cache_size=len(r.ship_lists)
    GL.glFinish()
    start=time.perf_counter()
    for _ in range(15):
        cam.apply(W,H)
        r.draw(0,set())
    GL.glFinish()
    metrics['bench_150_ms']=(time.perf_counter()-start)*1000/15
    assert len(r.ship_lists)==cache_size,'geometry cache grows with frames'
    metrics['display_lists']=cache_size
    if args.compare:
        old=json.loads(args.compare.read_text())
        changes={}
        for did,v in metrics['subjects'].items():
            before=np.asarray(Image.open(old['subjects'][did]['image']))
            after=np.asarray(Image.open(v['image']))
            changed=int((np.abs(after.astype(int)-before.astype(int)).max(2)>12).sum())
            assert changed>500,(did,'model upgrade not visible',changed)
            assert v['warm']>10,(did,'external illuminated windows not visible')
            assert v['checksum']==old['subjects'][did]['checksum']
            changes[did]=changed
        metrics['changed_pixels']=changes
        metrics['bench_delta_ms']=metrics['bench_150_ms']-old['bench_150_ms']
    (args.out/f'{args.label}_metrics.json').write_text(json.dumps(metrics,indent=2))
    r.close()
    pygame.quit()
    print('FLEET_DETAIL_DIAG_OK', json.dumps({k:v for k,v in metrics.items() if k!='subjects'}))

if __name__=='__main__': main()
