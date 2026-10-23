#!/usr/bin/env python3
"""Author the first ship/station specimens of the complete Alliance redesign.

Accepted masters/helpers are never rebuilt. Blender is an offline authoring tool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
ROWS=(('frigate','alliance_frigate','rebel_frigate','Escort Frigate'),
      ('shipyard','alliance_shipyard','shipyard','Alliance Shipyard'))

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
    sys.path.insert(0,str(ROOT))
    import bpy
    from tools.art import alliance_redesign_geometry as g
    from tools.art import alliance_redesign_ship_designs as ships
    from tools.art import alliance_redesign_station_designs as stations
    sources=[Path(__file__),ROOT/'tools/art/alliance_redesign_geometry.py',
             ROOT/'tools/art/alliance_redesign_ship_designs.py',ROOT/'tools/art/alliance_redesign_station_designs.py']
    reports=[]
    for kind,template,_,_ in rows:
        baseline=json.loads((ROOT/f'assets/models/manifests/{template}.json').read_text())
        lo=baseline['bounds']['min'];hi=baseline['bounds']['max']
        frame={'lo':lo,'hi':hi,'span':[b-a for a,b in zip(lo,hi)],
               'center':[(a+b)/2 for a,b in zip(lo,hi)]}
        g.initialize()
        (ships if kind=='frigate' else stations).build(kind,g,frame)
        report=g.export(root,kind,kind,tuple(zip(lo,hi)),replace_own=args.replace_own)
        report['blender_version']=bpy.app.version_string
        report['source_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sources}
        reports.append(report)
    out=root/'artifacts/alliance-redesign/build';out.mkdir(parents=True,exist_ok=True)
    target=out/(args.only+'.json' if args.only else 'specimens.json')
    target.write_text(json.dumps(reports,indent=2)+'\n')
    print('ALLIANCE_REDESIGN_BUILD_OK',len(reports),target,flush=True)

if __name__=='__main__':main()
