"""Create labelled, individually framed review boards from actual native captures."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.art.legions_redesign_catalogue import ROWS

def make_boards(source,output):
    output.mkdir(parents=True,exist_ok=True)
    try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',21)
    except OSError:font=ImageFont.load_default()
    for group,rows in [('fleet',ROWS[:10]),('stations',ROWS[10:20]),('hardware',ROWS[20:])]:
        width=1200;tilew=600;tileh=350
        board=Image.new('RGB',(width,((len(rows)+1)//2)*tileh),(12,18,27))
        draw=ImageDraw.Draw(board)
        for n,(kind,_,_,name) in enumerate(rows):
            image=Image.open(source/f'{kind}-after-close/capture.png').convert('RGB')
            mask=np.max(np.asarray(image),axis=2)>65
            xs=np.flatnonzero(np.sum(mask,axis=0)>4);ys=np.flatnonzero(np.sum(mask,axis=1)>4)
            if len(xs) and len(ys):
                image=image.crop((max(0,int(xs[0])-18),max(0,int(ys[0])-18),min(image.width,int(xs[-1])+19),min(image.height,int(ys[-1])+19)))
            image.thumbnail((tilew-24,tileh-58),Image.Resampling.LANCZOS)
            x=(n%2)*tilew;y=(n//2)*tileh
            draw.text((x+14,y+10),name,fill=(230,236,242),font=font)
            board.paste(image,(x+(tilew-image.width)//2,y+45+(tileh-50-image.height)//2))
        board.save(output/f'{group}-review.png',optimize=True)
        print(group,len(rows),output/f'{group}-review.png')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    make_boards(a.source,a.out)
