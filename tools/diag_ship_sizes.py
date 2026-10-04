"""Same-camera real SDL/GL size regression against the committed renderer.

SDL_AUDIODRIVER=dummy .venv/bin/python tools/diag_ship_sizes.py --out saves/ship_sizes
No per-hull autozoom: every catalogue subject shares the exact camera.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import types
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
from render.fleet_geometry import ship_mesh
from render.ship_sizes import ship_size, RATIOS
import render.renderer as current

W, H = 1280, 960
SKIP = {'starfield','star','planets','nebulas','jumppoints','rings','sites','effects','projectiles','shields'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'saves/ship_sizes')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # Pin the pre-fix renderer: committing this diagnostic must not silently
    # replace its control with the fixed renderer.
    baseline_commit = '6a7505bd96e059258026e7ef401c5dbae9eeb354'
    source = subprocess.check_output(['git','show',f'{baseline_commit}:render/renderer.py'], cwd=ROOT, text=True)
    baseline = types.ModuleType('render.ship_sizes_baseline')
    baseline.__file__ = str(ROOT/'render/renderer.py')
    sys.modules[baseline.__name__] = baseline
    exec(compile(source, baseline.__file__, 'exec'), baseline.__dict__)
    pygame.display.init()
    pygame.display.set_mode((W,H), pygame.OPENGL | pygame.DOUBLEBUF)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(20)
    ds = DataStore.get()
    st = GameManager.start_skirmish(ds.maps['skirmish01']).state
    st.entities.clear()
    cam = Camera(W,H)
    cam.target, cam.yaw, cam.pitch, cam.distance = [0,0,0], 0, 90, 900
    metrics = {'gl_renderer':GL.glGetString(GL.GL_RENDERER).decode(),
               'baseline_commit':baseline_commit,
               'geometry':{}, 'pixels':{}, 'corvette_baseline':{}, 'shields':{}}
    def entity(did, i=0, x=0, z=0):
        station = did in ds.stations
        data = ds.stations[did] if station else ds.ships.get(did)
        e = Entity(id=9000+i, kind='station' if station else 'ship', owner=0, data_id=did,
                   radius=data.radius if data else 42., pos=Vec3(x,0,z))
        e.is_ship, e.is_station = not station, station
        e.sensor_range = data.sensor_range if data else 1000.
        e.max_shield_quad = 100.
        e.shields = {q:100. for q in QUADRANTS}
        return e
    def precise(): return json.dumps(st.to_dict(precise=True), sort_keys=True)
    def frame(r, selected=set()):
        original = precise()
        cam.apply(W,H)
        r.draw(0,selected)
        GL.glFinish()
        assert GL.glGetError()==0
        pixels=np.flipud(np.frombuffer(GL.glReadPixels(0,0,W,H,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),np.uint8).reshape(H,W,3)).copy()
        assert original == precise(), 'render mutated precise save/state'
        return pixels
    def settled(r):
        for _ in range(3): a=frame(r)
        assert np.array_equal(a, frame(r)), 'frozen frame unstable'
        return a
    def mask(a): return a.max(2)>40
    def span(a):
        yy,xx=np.where(mask(a))
        assert len(yy)>5, 'empty hull'
        return dict(length=int(yy.max()-yy.min()+1),width=int(xx.max()-xx.min()+1),pixels=int(len(yy)))
    def save(a, name, label=None):
        image=Image.fromarray(a)
        if label: ImageDraw.Draw(image).text((16,16),label,fill='white')
        path=args.out/(name+'.png'); image.save(path); return str(path.resolve())
    ids=list(ds.ships)+['trade_convoy','unknown_mod_ship']
    reference=ship_size(ds,'imperial_corvette').length
    for did in ids:
        size=ship_size(ds,did)
        pts=[p for mesh in ship_mesh(size.shape).values() for _,tri in mesh for p in tri]
        measured=(max(p[2] for p in pts)-min(p[2] for p in pts))*size.scale
        assert measured<=5*reference+1e-8,(did,measured,reference)
        metrics['geometry'][did]=dict(length=measured,ratio=measured/reference)
    # Frozen baseline: centered corvette at BOTH ordinary and readability zoom.
    old = baseline.Renderer(st,cam)
    old.skip=set(SKIP); old.time=3.; old.diff_render=True
    controls={}
    for distance in (900,6200,22000):
        cam.distance=distance
        st.entities={9000:entity('imperial_corvette')}
        controls[distance]=settled(old)
        save(controls[distance],f'before_corvette_{distance}')
    cam.distance=6200
    st.entities={9000:entity('command_station')}
    station_control=settled(old)
    cam.distance=900
    st.entities={9000:entity('imperial_supercapital')}
    capital_before=settled(old)
    save(capital_before,'before_capital_900')
    fleet_ids=['imperial_tie_squadron','imperial_corvette','imperial_frigate',
               'imperial_cruiser','imperial_battleship','imperial_supercapital','imperial_constructor']
    def fleet(r,label):
        cam.distance,cam.pitch,cam.yaw=6200,90,0
        st.entities={9000+i:entity(did,i,(i-3)*720) for i,did in enumerate(fleet_ids)}
        r.skip.discard('shields')
        a=settled(r)
        image=Image.fromarray(a); draw=ImageDraw.Draw(image)
        draw.text((16,16),label+' — same frozen camera, distance 6200; labels are post-capture',fill='white')
        for e in st.entities.values():
            sp=cam.world_to_screen(e.pos.x,e.pos.y,e.pos.z)
            draw.text((int(sp[0])-65,H-80),e.data_id.replace('imperial_',''),fill='white')
        path=args.out/(label+'_fleet.png');image.save(path)
        r.skip.add('shields')
        return str(path.resolve())
    metrics['before_fleet']=fleet(old,'before')
    old.close()
    r=current.Renderer(st,cam)
    r.skip=set(SKIP);r.time=3.;r.diff_render=True
    for distance, control in controls.items():
        cam.distance=distance
        st.entities={9000:entity('imperial_corvette')}
        a=settled(r)
        diff=int((a!=control).any(2).sum())
        metrics['corvette_baseline'][distance]=dict(changed_pixels=diff,**span(a))
        save(a,f'after_corvette_{distance}')
        assert diff==0, ('standard corvette changed',distance,diff)
    cam.distance=6200
    st.entities={9000:entity('command_station')}
    station_after=settled(r)
    assert np.array_equal(station_control,station_after), 'station visual changed'
    metrics['station_changed_pixels']=0
    # All classes rendered separately, SAME camera and depth; no auto-framing.
    for distance in (900,6200,22000):
        cam.distance=distance
        lengths={}
        for did in ids:
            st.entities={9000:entity(did)}
            a=settled(r)
            values=span(a);lengths[did]=values['length']
            metrics['pixels'][f'{distance}:{did}']=values
            assert values['pixels']<W*H*.20,(did,'pixel budget',values)
            if distance==900: save(a,'after_'+did+'_900')
        ref=lengths['imperial_corvette']
        for did in ids:
            ratio=RATIOS.get(ds.ships[did].category,1.) if did in ds.ships else 1.
            assert abs(lengths[did]/ref-ratio)<.18,(distance,did,lengths[did]/ref,ratio)
        # Perspective foreshortening includes dorsal hardware closer to the eye;
        # center depths and LOD ratios are identical, raster lengths tolerate 4%.
        assert max(lengths.values())<=5*ref*1.04+2, ('projected LOD cap',distance,lengths)
    cam.distance=900
    st.entities={9000:entity('imperial_supercapital')}
    capital_after=settled(r)
    metrics['capital']=dict(before=span(capital_before),after=span(capital_after))
    assert metrics['capital']['after']['pixels']<metrics['capital']['before']['pixels']*.5
    # Shield enclosure verified in model space AND actual same-camera pixels.
    for did in ('imperial_corvette','imperial_supercapital','imperial_constructor'):
        e=entity(did);st.entities={e.id:e}
        hull=settled(r)
        r.skip.discard('shields');bubble=settled(r);r.skip.add('shields')
        radius=r._shield_radius(e);size=r._ship_size(e)
        pts=[p for mesh in ship_mesh(size.shape).values() for _,tri in mesh for p in tri]
        assert all(math.sqrt(sum(x*x for x in p))*size.scale<radius for p in pts)
        changed=np.abs(bubble.astype(int)-hull.astype(int)).max(2)>4
        hy,hx=np.where(mask(hull)); sy,sx=np.where(changed)
        assert sx.min()<=hx.min() and sx.max()>=hx.max() and sy.min()<=hy.min() and sy.max()>=hy.max(),(did,'shield fails pixel enclosure')
        assert changed.sum()<W*H*.25,(did,'shield pixel budget')
        metrics['shields'][did]=dict(radius=radius,changed_pixels=int(changed.sum()))
        save(bubble,'after_'+did+'_shield_900')
    metrics['after_fleet']=fleet(r,'after')
    # Also measure all seven hulls concurrently on one equal-depth plane.
    row=settled(r)
    row_lengths={}
    centers=[cam.world_to_screen(e.pos.x,e.pos.y,e.pos.z)[0] for e in st.entities.values()]
    for i,did in enumerate(fleet_ids):
        left=0 if i==0 else int((centers[i-1]+centers[i])/2)
        right=W if i==len(fleet_ids)-1 else int((centers[i]+centers[i+1])/2)
        row_lengths[did]=span(row[:,left:right])['length']
    ref=row_lengths['imperial_corvette']
    for did,length in row_lengths.items():
        assert abs(length/ref-RATIOS[ds.ships[did].category])<.2,(did,'same-scene row',row_lengths)
    metrics['equal_depth_fleet_lengths']=row_lengths
    save(row,'after_fleet_hulls')
    # Actual renderer contact pixels must remain localized to the resized hull.
    cam.distance=900
    e=entity('imperial_supercapital');st.entities={e.id:e}
    clean=settled(r)
    r.skip.discard('effects')
    st.effects=[dict(kind='hull_hit',target_id=e.id,pos=(0.,0.,e.radius),
                     center=(0.,0.,0.),normal=(0.,0.,1.),direction=(0.,0.,-1.),
                     radius=e.radius,size=18.,t=.03,seed=41)]
    contact=settled(r)
    changed=np.abs(contact.astype(int)-clean.astype(int)).max(2)>4
    assert 0<changed.sum()<3000, ('resized contact pixel budget',changed.sum())
    metrics['hull_contact_changed_pixels']=int(changed.sum())
    save(contact,'after_capital_hull_contact')
    st.effects=[]
    r.skip.discard('shields')
    clean_shell=settled(r)
    st.effects=[dict(kind='shield_hit',target_id=e.id,pos=(0.,0.,e.radius*1.35),
                     center=(0.,0.,0.),normal=(0.,0.,1.),direction=(0.,0.,-1.),
                     radius=e.radius*1.35,size=18.,t=.06,seed=41)]
    shield_contact=settled(r)
    changed=np.abs(shield_contact.astype(int)-clean_shell.astype(int)).max(2)>4
    assert 0<changed.sum()<3000, ('shield contact pixel budget',changed.sum())
    metrics['shield_contact_changed_pixels']=int(changed.sum())
    save(shield_contact,'after_capital_shield_contact')
    st.effects=[];r.skip.update({'effects','shields'})
    # A selected shieldless ship needs an actual ground-plane enclosure.
    e.shields={q:0. for q in QUADRANTS}
    clean=settled(r)
    r.skip.discard('rings')
    marked=frame(r,{e.id})
    delta=np.abs(marked.astype(int)-clean.astype(int)).max(2)>4
    hy,hx=np.where(mask(clean)); ry,rx=np.where(delta)
    assert len(ry)>0 and ry.min()<=hy.min() and ry.max()>=hy.max(), 'selection circle does not enclose resized hull'
    metrics['selection_circle_changed_pixels']=int(delta.sum())
    save(marked,'after_capital_selection')
    r.skip.add('rings')
    # Pick the visible bow through the real camera, not the old collision sphere.
    from render.input import InputController
    ctl=InputController(st,cam,None,None)
    bow=cam.world_to_screen(0.,0.,r._ship_size(e).length*.4)
    assert ctl._pick_target(bow) is e
    metrics['visual_bow_picking']=True
    # Real framebuffer fog boundary: retain sensed ballistic history, never
    # follow a hidden live target, and reject a sensed-center remap into fog.
    import copy
    from game.systems.damage import DamageSystem
    from render.fog import effect_visible
    cam.target, cam.distance = [1000., 0., 0.], 900
    r.skip = set(SKIP) - {'effects'}
    observer = entity('imperial_corvette', 100)
    observer.sensor_range = 1000.
    target = entity('imperial_supercapital', 101, x=1100)
    target.owner, target.sensor_range, target.radius = 1, 0., 260.
    st.entities = {observer.id: observer, target.id: target}
    st.effects = []
    DamageSystem(st)._spawn_hit('hull_hit', target, Vec3(944,0,0), observer, 14., effect_seed=41)
    st.effects[0]['t'] = .03
    historical = copy.deepcopy(st.effects)
    assert not st.can_see(0, target.id) and effect_visible(st, 0, historical[0])
    hidden_frames = {}
    for label, x in (('present',1100.), ('moved',1400.), ('removed',None)):
        if x is None:
            st.entities.pop(target.id)
        else:
            target.pos.x = x
        hidden_frames[label] = settled(r)
        assert st.effects == historical, 'cached historical FX mutated'
        save(hidden_frames[label], 'fog_hit_hidden_'+label)
    deltas = {label:int((a!=hidden_frames['present']).any(2).sum())
              for label,a in hidden_frames.items()}
    assert all(value==0 for value in deltas.values()), ('hidden hit followed target', deltas)
    st.effects = []
    no_contact = settled(r)
    static_pixels = int((hidden_frames['removed']!=no_contact).any(2).sum())
    assert static_pixels>0, 'legal static ballistic impact was blanked'
    save(no_contact, 'fog_hit_no_contact')
    # Same original sensed contact, now a detected target whose visual contact
    # lands outside the observer sphere. Compare clean/FX in identical state.
    target.pos.x = 800.; st.entities[target.id] = target
    DamageSystem(st)._spawn_hit('hull_hit', target, Vec3(956,0,0), observer, 14., effect_seed=41)
    st.effects[0]['t'] = .03
    target.pos.x = 990.
    assert st.can_see(0,target.id) and effect_visible(st,0,st.effects[0])
    assert not effect_visible(st,0,r._visual_hit(st.effects[0]))
    boundary = settled(r); save(boundary, 'fog_hit_visible_remap_outside')
    st.effects = []
    boundary_clean = settled(r)
    boundary_pixels = int((boundary!=boundary_clean).any(2).sum())
    assert boundary_pixels==0, ('remapped contact escaped sensor',boundary_pixels)
    # Allied live contacts remain known even with zero target sensors. Their
    # effects still use the same position-sensor contract, not an ally bypass.
    st.players[0].team = st.players[1].team = 7
    target.pos.x = 1100.
    st.effects = copy.deepcopy(historical)
    assert st.can_see(0,target.id)
    assert r._visual_hit(st.effects[0])['visual_contact']
    ally_outside = settled(r)
    st.effects = []; ally_clean = settled(r)
    ally_outside_pixels = int((ally_outside!=ally_clean).any(2).sum())
    assert ally_outside_pixels==0
    target.pos.x = 900.
    ally_clean = settled(r)
    st.effects = copy.deepcopy(historical)
    ally_inside = settled(r);save(ally_inside, 'fog_hit_allied_visible')
    ally_inside_pixels = int((ally_inside!=ally_clean).any(2).sum())
    assert ally_inside_pixels>0
    st.players[0].team, st.players[1].team = None, None
    st.effects = []
    cam.target = [0.,0.,0.]
    metrics['fog_hit_boundary'] = dict(hidden_changed_pixels=deltas,
        static_impact_pixels=static_pixels, visible_remap_outside_pixels=boundary_pixels,
        allied_outside_pixels=ally_outside_pixels, allied_inside_pixels=ally_inside_pixels,
        cached_fx_unchanged=True, precise_save_unchanged=True)
    # Restored collision radii cannot inflate the frozen hull or mutate saves.
    from game.core.state import GameState
    st.entities={9000:entity('imperial_corvette')};cam.distance=900
    original=settled(r)
    saved=json.loads(precise())
    restored=GameState.from_dict(saved)
    r.state=restored
    restored.entities[9000].radius=3400.
    # frame() compares original st; also independently verify restored state.
    before=json.dumps(restored.to_dict(precise=True),sort_keys=True)
    assert np.array_equal(original,settled(r))
    assert before==json.dumps(restored.to_dict(precise=True),sort_keys=True)
    r.state=st
    metrics['restored_radius_pixels_unchanged']=True
    cache=len(r.ship_lists)
    for _ in range(10):frame(r)
    assert len(r.ship_lists)==cache
    metrics['display_lists_stable']=cache
    path=args.out/'metrics.json';path.write_text(json.dumps(metrics,indent=2))
    r.close();pygame.quit()
    print('SHIP_SIZES_DIAG_OK',json.dumps(dict(catalogue=len(ids),reference_length=reference,
          corvette=metrics['corvette_baseline'],capital=metrics['capital'],
          metrics=str(path.resolve()),before=metrics['before_fleet'],after=metrics['after_fleet'])))


if __name__=='__main__':main()
