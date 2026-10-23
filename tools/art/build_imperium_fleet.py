#!/usr/bin/env python3
"""Build the seven remaining Imperium models; never rebuild accepted neighbours.

Blender --background --python-exit-code 1 --python this_file -- [--only frigate]
This creates only new editable masters and a new optional, data-only review pack.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
ROWS=(('bomber','hammer','imperial_tie_bomber_squadron','Hammer Torpedo Squadron'),
      ('frigate','lancer','imperial_frigate','Lancer Frigate'),
      ('cruiser','gladiator','imperial_cruiser','Gladiator Cruiser'),
      ('battleship','executor','imperial_battleship','Executor-class Dreadnought'),
      ('supercapital','sovereign','imperial_supercapital','Sovereign-class Star Dreadnought'),
      ('colonizer','colonial','imperial_colonizer','Colonial Outreach Frigate'),
      ('convoy','transport','imperial_convoy','Imperial Crew Transport / Trade Convoy'))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output-root',type=Path,default=REPO)
    p.add_argument('--only',choices=[r[0] for r in ROWS])
    p.add_argument('--replace-own',action='store_true',help='Rebuild only these new unapproved fleet masters')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    root=a.output_root.resolve()
    rows=[r for r in ROWS if not a.only or r[0]==a.only]
    for _,stem,_,_ in rows:
        if not a.replace_own:
            for path in (root/f'art/blender/imperium_{stem}_prototype.blend',
                         root/f'visual_packs/imperium-fleet-prototypes/assets/models/{stem}.mesh.json'):
                if path.exists():raise FileExistsError(path)
    sys.path.insert(0,str(REPO))
    import bpy
    from tools.art import imperium_fleet_geometry as g
    from tools.art import imperium_capital_designs as capital
    from tools.art import imperium_support_designs as support
    reports=[]
    for kind,stem,template,_ in rows:
        baseline=json.loads((REPO/f'assets/models/manifests/{template}.json').read_text())
        lo=baseline['bounds']['min'];hi=baseline['bounds']['max']
        frame={'lo':lo,'hi':hi,'span':[b-a for a,b in zip(lo,hi)],
               'center':[(a+b)/2 for a,b in zip(lo,hi)]}
        g.initialize()
        (capital if kind in ('frigate','cruiser','battleship','supercapital') else support).build(kind,g,frame)
        report=g.export(root,kind,stem,tuple(zip(lo,hi)),replace_own=a.replace_own)
        report['blender_version']=bpy.app.version_string
        report['source_sha256']={str(path.relative_to(REPO)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__),REPO/'tools/art/imperium_fleet_geometry.py',
                         REPO/'tools/art/imperium_capital_designs.py',REPO/'tools/art/imperium_support_designs.py']}
        reports.append(report)
    out=root/'artifacts/imperium-fleet/build'
    out.mkdir(parents=True,exist_ok=True)
    path=out/(f'{a.only}.json' if a.only else 'all.json')
    path.write_text(json.dumps(reports,indent=2)+'\n')
    print('IMPERIUM_FLEET_BUILD_OK',len(reports),path,flush=True)

if __name__=='__main__':main()
