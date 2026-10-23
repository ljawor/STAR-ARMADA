#!/usr/bin/env python3
"""Package Alliance redesign specimens, preserving original assets and normal defaults until review."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.art.build_alliance_redesign import ROWS


def main():
    pack=ROOT/'visual_packs/alliance-redesign'
    replacements=[];manifests=[]
    # Read/check every actual export before emitting any metadata.
    for kind,template,live_id,name in ROWS:
        stem=kind
        relative=f'assets/models/{stem}.mesh.json'
        raw=(pack/relative).read_bytes();payload=json.loads(raw)
        asset='prototype:alliance_redesign/'+kind
        if payload.get('asset')!=asset:raise ValueError(f'Wrong export identity: {kind}')
        if not 1800<payload['triangle_count']<=(6000 if kind=='bomber' else 11888):
            raise ValueError(f'Triangle budget: {kind}')
        digest=hashlib.sha256(raw).hexdigest()
        manifest=deepcopy(json.loads((ROOT/f'assets/models/manifests/{template}.json').read_text()))
        baseline_asset=manifest['asset']
        manifest.pop('approval',None);manifest['export'].pop('legacy_schema_int',None)
        manifest.update(asset=asset,display_name=name+' — pending appearance review',
                        revision=hashlib.sha256((asset+'\nmesh:'+digest).encode()).hexdigest())
        manifest['files']={'mesh':{'path':relative,'sha256':digest,'bytes':len(raw)}}
        manifest['bounds']={'min':payload['bounds'][0],'max':payload['bounds'][1]}
        manifest['roles']=sorted(payload['batches'])
        manifest['budgets']={'triangles':payload['triangle_count'],'draw_calls':6,'texture_bytes':0}
        manifest['provenance']={'author':'Lukasz Jawor / STAR ARMADA',
            'tool':'Blender','tool_version':'5.0.1','license':'original',
            'notes':'Original Alliance redesign. Script-authoritative build_alliance_redesign.py and dedicated design modules; editable masters in art/blender. Style specimens pending owner appearance approval. No simulation, scale or balance changes.'}
        manifest_path=f'assets/models/manifests/{stem}.json'
        manifests.append((manifest_path,manifest))
        replacements.append({'binding':'rebel:'+kind,'replace_of':baseline_asset,'manifest':manifest_path})
    descriptor={'contract':'star-armada/visual-pack','contract_major':1,
        'id':'prototype:alliance_redesign','version':'0.1.0',
        'requires':{'min_engine':'0.15.1','contracts':['star-armada/model-manifest/v1']},
        'content':{'replaces':replacements},
        'notes':'Alliance frigate/shipyard style specimens for a complete faction redesign. All existing meshes and normal settings preserved. Appearance review pending; final delivery must activate the complete approved set in normal main.py.'}
    for relative,value in manifests+[('visual-pack.json',descriptor)]:
        target=pack/relative;target.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.'+target.name+'-',dir=target.parent)
        stage=Path(name)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')
            os.replace(stage,target)
        finally:stage.unlink(missing_ok=True)
    # Actual transactional runtime validation, including geometry and binding envelopes.
    from render.asset_registry import AssetResolver
    resolver=AssetResolver(ROOT)
    active=resolver.activate_packs([pack/'visual-pack.json'],pack_root=ROOT/'visual_packs')
    if active!=('prototype:alliance_redesign',):raise ValueError(resolver.diagnostics)
    for kind,_,_,_ in ROWS:
        resolved=resolver.resolve('rebel:'+kind)
        if resolved is None or resolved.asset!='prototype:alliance_redesign/'+kind:
            raise ValueError((kind,resolver.diagnostics))
    print('ALLIANCE_REDESIGN_PACK_OK',len(replacements),'strict runtime-validated bindings')

if __name__=='__main__':main()
