#!/usr/bin/env python3
"""Author all 26 actual Alliance bindings without overwriting accepted baseline art.

Blender is offline-only. Real exports share the existing six-role native pipeline.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.art.alliance_redesign_catalogue import ROWS,TRIANGLE_LIMITS,design_module

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,default=ROOT)
    parser.add_argument('--only',choices=[row[0] for row in ROWS])
    parser.add_argument('--replace-own',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    root=args.output_root.resolve()
    rows=[row for row in ROWS if not args.only or row[0]==args.only]
    for kind,_,_,_ in rows:
        for path in (root/f'art/blender/alliance_redesign_{kind}.blend',
                     root/f'visual_packs/alliance-redesign/assets/models/{kind}.mesh.json'):
            if path.exists() and not args.replace_own:raise FileExistsError(path)
    import bpy
    from tools.art import alliance_redesign_geometry as g
    reports=[]
    out=root/'artifacts/alliance-redesign/build';out.mkdir(parents=True,exist_ok=True)
    for kind,template,_,_ in rows:
        module_name=design_module(kind)
        designer=importlib.import_module('tools.art.'+module_name)
        sources=[Path(__file__),ROOT/'tools/art/alliance_redesign_catalogue.py',
                 ROOT/'tools/art/alliance_redesign_geometry.py',ROOT/f'tools/art/{module_name}.py']
        baseline=json.loads((ROOT/f'assets/models/manifests/{template}.json').read_text())
        lo=baseline['bounds']['min'];hi=baseline['bounds']['max']
        frame={'lo':lo,'hi':hi,'span':[b-a for a,b in zip(lo,hi)],
               'center':[(a+b)/2 for a,b in zip(lo,hi)]}
        g.initialize()
        designer.build(kind,g,frame)
        report=g.export(root,kind,kind,tuple(zip(lo,hi)),replace_own=args.replace_own)
        assert report['triangles']<=TRIANGLE_LIMITS[kind],(kind,report['triangles'])
        report['blender_version']=bpy.app.version_string
        report['source_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sources}
        reports.append(report)
        (out/(kind+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    target=out/(args.only+'-run.json' if args.only else 'complete-faction.json')
    target.write_text(json.dumps(reports,indent=2)+'\n')
    print('ALLIANCE_REDESIGN_BUILD_OK',len(reports),target,flush=True)

if __name__=='__main__':main()
