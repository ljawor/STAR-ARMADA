"""Paired Legions redesign specimens through the production native viewer.

Isolated factory-spawned inspection, not organic construction or main-loop
acceptance. Same entity/cameras/tint per pair; no HUD/effects/fog. Runtime code,
approved model bytes and ordinary user settings are never modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.art.legions_redesign_catalogue import SHIP_KINDS
from tools.art.build_legions_redesign import ROWS as SOURCE_ROWS
ROWS=tuple((kind,kind,live,name) for kind,template,live,name in SOURCE_ROWS)
PACK_NAME='legions-redesign'
# Manifest stems are not necessarily live UnitFactory catalogue identifiers.
LIVE_IDS={kind:live for kind,_,live,_ in ROWS}


def camera_plan(*,length,center,heading_degrees):
    if not math.isfinite(length) or length<=0:raise ValueError('positive finite length required')
    return {name:dict(target=list(center),distance=max(75.,length*multiplier),
                      yaw=yaw+heading_degrees,pitch=pitch,fov=55.)
            for name,multiplier,yaw,pitch in
            [('close',1.65,48,28),('rear',1.65,220,18),('tactical',4.8,48,52)]}


def spawn_subject(fixture,kind,live_id):
    from game.core.vectors import Vec3
    factory=(fixture.manager.factory.spawn_ship if kind in SHIP_KINDS
             else fixture.manager.factory.spawn_station)
    return factory(live_id,0,Vec3())


def subject_snapshot(fixture):
    """Use production station ownership, not the Imperial-only benchmark helper assumption."""
    from tools.render import dump_snapshot as snapshot
    from render import asset_selection
    from render_bridge.collect import station_binding
    payload=snapshot.build_snapshot(fixture,all_visible=True)
    state=fixture.manager.state
    for row in payload['instances']:
        entity=state.entities[row['entity_id']]
        if entity.is_station:
            faction=state.players[entity.owner].faction
            row['binding']=station_binding(entity.data_id,faction)
    manifests=snapshot._manifest_map(asset_selection.diagnostics())
    payload['assets']=[snapshot._asset(binding,manifests)
                       for binding in sorted({row['binding'] for row in payload['instances']})]
    original=payload['metadata']
    kept=('asset_path_root','checksum','inventory','exported_inventory',
          'visual_selection','scale_policy','omitted_features','omitted_planets','visibility')
    payload['metadata']={key:original[key] for key in kept if key in original}
    payload['metadata'].update(
        name='legions-isolated-factory-subject-v1',
        source_fixture='four-player-close-v1 (entities removed and replaced)',
        profile='production native hull shader; isolated inspection, not main-loop acceptance',
        factions=[state.players[key].faction for key in sorted(state.players)],
        players=len(state.players),local_player=0,selection=[],ai=False,
        assumptions=['One completed factory-created subject; no paid construction or organic economy.',
                     'All entities from the benchmark seed removed before this subject is spawned.',
                     'Omniscient fixed-camera inspection; no HUD, fog or effects.',
                     'Same entity, owner tint, camera and lighting for each before/after pair.',
                     'Individually framed subjects do not establish relative fleet sizes.'])
    return payload


def seal_capture_evidence(out):
    """Hash retained PNG/snapshot/report bytes plus the exact capture implementation."""
    out=Path(out)
    receipt=out/'evidence-sha256.json'
    files={str(path.relative_to(out)):hashlib.sha256(path.read_bytes()).hexdigest()
           for path in sorted(out.rglob('*')) if path.is_file() and path!=receipt}
    sources=[Path(__file__),ROOT/'tools/art/build_legions_redesign.py',
             ROOT/'visual_packs/legions-redesign/visual-pack.json',
             ROOT/'render_cpp/build-w02/armada_viewer']
    receipt.write_text(json.dumps({'files':files,'sources':{
        str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources}},indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--only',choices=[r[0] for r in ROWS])
    p.add_argument('--include-control',action='store_true')
    a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    from PIL import Image,ImageChops,ImageStat,ImageDraw
    import numpy as np
    from game.graphics_benchmark import make_fixture
    from game.core.vectors import Vec3
    from game.benchmark import state_hash
    from render import asset_selection
    from render.ship_sizes import ship_size
    from render_bridge.protocol import encode,WORLD
    from tools.render import dump_snapshot as snapshot
    defaults=snapshot._default_selection()
    # Always exclude the candidate on BEFORE, including after its eventual default activation.
    defaults['visual_packs']=[name for name in defaults['visual_packs'] if name!=PACK_NAME]
    original_selection=snapshot._default_selection
    rows=[r for r in ROWS if not a.only or r[0]==a.only]
    if a.include_control:rows.append(('corvette','vigil-control','imperial_corvette','Vigil — unchanged control'))
    records=[];cards=[]
    try:
        for kind,stem,data_id,name in rows:
            # Both variants share this exact factory-created subject and source state.
            fixture=make_fixture('four-player-close-v1')
            state=fixture.manager.state
            state.entities.clear()
            is_control=stem=='vigil-control'
            state.players[0].faction='imperial' if is_control else 'confederacy'
            entity=spawn_subject(fixture,kind,data_id)
            faction='imperial' if is_control else 'confederacy'
            source_hash=state_hash(state)
            configurations={label:{**defaults,'visual_packs':list(defaults['visual_packs'])+
                ([PACK_NAME] if label=='after' else [])} for label in ('before','after')}
            payloads={}
            for label,settings in configurations.items():
                snapshot._default_selection=lambda settings=settings:settings
                payloads[label]=subject_snapshot(fixture)
                assert state_hash(state)==source_hash
                payloads[label]['fixture']='legions-redesign-specimen-inspection-v1'
                payloads[label]['metadata']['review_scope']='Factory-spawned single subject, normal native hull shader; no HUD/fog/effects. Individually framed, not a size-comparison board or organic build.'
                assert len(payloads[label]['instances'])==len(payloads[label]['assets'])==1
                assert payloads[label]['instances'][0]['binding']==faction+':'+kind
            # Union-safe fixed centre; equal old/new class length gives equal camera scale.
            lengths=[];allpoints=[]
            for label,payload in payloads.items():
                item=payload['assets'][0];raw=(ROOT/item['path']).read_bytes()
                assert hashlib.sha256(raw).hexdigest()==item['sha256']
                model=json.loads(raw);scale=payload['instances'][0]['scale']
                allpoints.extend([[c*scale for c in point] for point in model['bounds']])
                lengths.append(max((model['bounds'][1][i]-model['bounds'][0][i])*scale
                                  for i in ((2,) if kind in SHIP_KINDS else range(3))))
            assert abs(lengths[0]/lengths[1]-1)<.011,(kind,lengths)
            center=[(min(v[i] for v in allpoints)+max(v[i] for v in allpoints))/2 for i in range(3)]
            plan=camera_plan(length=max(lengths),center=center,heading_degrees=math.degrees(entity.yaw))
            metrics={'binding':faction+':'+kind,'name':name,'source_state_sha256':source_hash,
                     'drawn_lengths':lengths,'views':{},'meshes':{k:v['assets'][0] for k,v in payloads.items()}}
            for view,pose in plan.items():
                pair={}
                for label,payload in payloads.items():
                    folder=out/f'{stem}-{label}-{view}';folder.mkdir()
                    payload['camera']=pose
                    scene=folder/'scene.snap'
                    scene.write_bytes(encode(payload,kind=WORLD,tick=state.tick,frame_index=0))
                    image=folder/'capture.png';report=folder/'viewer.json'
                    command=[str(ROOT/'render_cpp/build-w02/armada_viewer'),'--snapshot',str(scene),
                        '--assets',str(ROOT),'--width','960','--height','600','--frames','24','--warmup','0',
                        '--focus',','.join(map(str,pose['target'])),'--distance',str(pose['distance']),
                        '--yaw',str(pose['yaw']),'--pitch',str(pose['pitch']),
                        '--screenshot',str(image),'--report',str(report)]
                    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,
                        env={**os.environ,'SDL_VIDEODRIVER':'cocoa'},timeout=60)
                    output=(result.stdout+'\n'+result.stderr).rstrip()
                    (folder/'stdout.txt').write_text(output+'\n' if output else '')
                    if result.returncode:raise RuntimeError(f'Native viewer failed: {folder}: {result.stderr[-2000:]}')
                    if not image.is_file() or not report.is_file():raise RuntimeError('Missing native capture/report')
                    with Image.open(image) as captured:pair[label]=captured.convert('RGB')
                difference=ImageChops.difference(pair['before'],pair['after'])
                changed=int(np.count_nonzero(np.max(np.asarray(difference),axis=2)>8))
                mean=sum(ImageStat.Stat(difference).mean)/3
                if is_control:assert changed==0,(kind,view,changed)
                else:assert changed>40,(kind,view,changed)
                metrics['views'][view]={'changed_pixels_gt8':changed,'mean_abs_rgb':mean,'camera':pose,
                    'before':f'{stem}-before-{view}/capture.png','after':f'{stem}-after-{view}/capture.png'}
                if view=='close':cards.append((name,pair['before'],pair['after']))
            records.append(metrics)
            with (out/'progress.jsonl').open('a') as progress:progress.write(json.dumps(metrics)+'\n')
        board=Image.new('RGB',(1920,len(cards)*644),(12,18,27));draw=ImageDraw.Draw(board)
        for index,(name,before,after) in enumerate(cards):
            y=index*644
            draw.text((12,y+10),name+' | BEFORE — accepted baseline',fill='white')
            draw.text((972,y+10),'AFTER — Legions redesign specimen (pending approval)',fill='white')
            board.paste(before,(0,y+36));board.paste(after,(960,y+36))
        board.save(out/'before-after.png')
        (out/'metrics.json').write_text(json.dumps({'scope':'production native renderer, isolated per-subject inspection; individually framed, not true-size fleet or main-loop acceptance',
            'count':len(records),'rows':records,'capture_code_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
        seal_capture_evidence(out)
        print('LEGIONS_NATIVE_PAIRED_SPECIMENS_OK',len(records),out)
    finally:
        snapshot._default_selection=original_selection
        asset_selection.configure(defaults,asset_root=ROOT,pack_root=ROOT/'visual_packs')

if __name__=='__main__':main()
