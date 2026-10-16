#!/usr/bin/env python3
"""Publish compact S05 evidence from an actual serial run (no GL or simulation)."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    run,out=args.run.resolve(),args.out.resolve()
    out.mkdir(exist_ok=True,parents=True)
    for name in ('summary.json','commands.json','source-receipts.json','user-before.json','user-after.json','user-preservation.json'):
        shutil.copyfile(run/name,out/name)
    reports={k:json.loads((run/k/'summary.json').read_text()) for k in ('control','candidate','legacy')}
    for variant,report in reports.items():
        target=out/variant; target.mkdir(exist_ok=True)
        shutil.copyfile(run/variant/'summary.json',target/'summary.json')
        shutil.copyfile(run/(variant+'-execution.txt'),out/(variant+'-execution.txt'))
        for image in sorted((run/variant).glob('*.png')):
            if variant=='candidate' or image.name.startswith(('initial-','features-')):
                shutil.copyfile(image,target/image.name)
    shutil.copyfile(run/'candidate/paired-motion.mp4',out/'paired-motion.mp4')
    shutil.copyfile(run/'candidate/encode.txt',out/'encode.txt')
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,nb_read_frames,duration','-of','json',str(out/'paired-motion.mp4')],capture_output=True,text=True,check=True)
    (out/'video-probe.json').write_text(probe.stdout,encoding='utf-8')
    stream=json.loads(probe.stdout)['streams'][0]
    assert stream['nb_read_frames']=='60' and stream['width']==1280 and stream['height']==400
    subprocess.run(['ffmpeg','-v','error','-i',str(out/'paired-motion.mp4'),'-f','null','-'],stdout=(out/'video-decode.txt').open('wb'),stderr=subprocess.STDOUT,check=True)
    for second in (0,2,4):
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(second),'-i',str(out/'paired-motion.mp4'),'-frames:v','1',str(out/f'video-{second}s.png')],check=True)
    import pygame
    import numpy as np
    pygame.font.init()
    font=pygame.font.Font(None,25)
    views=('capital-close','escort-close','yard-close')
    sheet=pygame.Surface((1920,1260));sheet.fill('#101723')
    for col,variant in enumerate(reports):
        for row,view in enumerate(views):
            image=pygame.image.load(str(out/variant/('initial-'+view+'.png')))
            sheet.blit(pygame.transform.smoothscale(image,(640,400)),(col*640,row*420+20))
            sheet.blit(font.render(variant.upper()+' / '+view,True,'white'),(col*640+8,row*420))
    pygame.image.save(sheet,str(out/'review-sheet.png'))
    palette=list(reports['control']['palette'])
    colors=pygame.Surface((320*len(palette),880));colors.fill('#101723')
    for row,view in enumerate(('capital-close','escort-close','yard-close','common-scale')):
        for col,color in enumerate(palette):
            name='palette-'+color+'-'+view
            index=next(i for i,f in enumerate(reports['control']['frames']) if f['name']==name)
            a=np.load(run/'control/frames'/f'{index:04d}.npy')
            image=pygame.image.frombuffer(a.tobytes(),(1280,800),'RGB')
            colors.blit(pygame.transform.smoothscale(image,(320,200)),(col*320,row*220+20))
            colors.blit(font.render(color+' / '+view,True,'white'),(col*320+4,row*220))
    pygame.image.save(colors,str(out/'owner-palette-sheet.png'))
    pygame.font.quit()
    failures=out/'attempts';failures.mkdir(exist_ok=True)
    for prior in ('s05-equivalence-run01','s05-equivalence-run02','s05-equivalence-run03'):
        source=run.parent/prior
        target=failures/prior;target.mkdir(exist_ok=True)
        for name in ('failure.json','summary.json','commands.json','user-preservation.json','control-execution.txt','candidate-execution.txt','legacy-execution.txt'):
            if (source/name).exists():shutil.copyfile(source/name,target/name)
        for variant in ('control','candidate','legacy'):
            if (source/variant/'summary.json').exists():shutil.copyfile(source/variant/'summary.json',target/(variant+'-summary.json'))
    manifest={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.rglob('*')) if f.is_file() and f.name not in ('file-hashes.json','publish.py')}
    (out/'file-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(files=len(manifest),video=stream,output=str(out))))


if __name__=='__main__':main()
