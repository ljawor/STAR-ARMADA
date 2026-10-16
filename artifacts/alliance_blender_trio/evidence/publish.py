"""Publish honest side-by-side actual-game evidence, never Blender beauty renders."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,shutil,subprocess,hashlib
S=Path(__file__).parent;R=Path('/Users/lukaszjawor/Downloads/Project/STAR-ARMADA');O=R/'artifacts/alliance_blender_trio';O.mkdir(parents=True,exist_ok=True)
fontpath='/System/Library/Fonts/Supplemental/Arial.ttf'
def font(size):return ImageFont.truetype(fontpath,size) if Path(fontpath).exists() else ImageFont.load_default(size=size)
def sheet(name,rows):
 im=Image.new('RGB',(1800,120+sum(row[3]+72 for row in rows)),(10,16,27));d=ImageDraw.Draw(im)
 d.text((28,18),'ALLIANCE / BLENDER-AUTHORED ESCORT + SHIPYARD',font=font(30),fill=(225,235,245))
 d.text((28,60),'Actual game renderer | same cameras + state | normal fog / postfx / 4x MSAA',font=font(22),fill=(145,167,186))
 y=120
 for title,view,crop,height in rows:
  for col,label in enumerate(['baseline','candidate']):
   folder=S/(label+'-baseline-capture' if label=='baseline' else 'candidate-candidate-capture')
   if view=='initial-escort-engine':folder=S/('baseline-extra-baseline-capture' if label=='baseline' else 'candidate-extra-candidate-capture')
   tile=Image.open(folder/(view+'.png')).crop(crop)
   tile.thumbnail((860,height),Image.Resampling.LANCZOS)
   x=20+col*900;d.text((x,y),title+' / '+('BEFORE' if col==0 else 'AFTER'),font=font(26),fill=(224,236,248))
   im.paste(tile,(x+(860-tile.width)//2,y+46+(height-tile.height)//2))
  y+=height+72
 im.save(O/name,quality=94)
sheet('before-after-contact-sheet.jpg',[
 ('TERN FRIGATE','initial-escort-close',(330,240,960,560),440),
 ('ANCHORAGE SHIPYARD','initial-yard-close',(330,180,960,680),660)])
sheet('before-after-aft-drives.jpg',[
 ('TERN / RECESSED CYAN DRIVES','initial-escort-engine',(435,285,840,555),550)])
# Full uncropped originals alongside cropped editorial comparisons.
for label in ['baseline','candidate']:
 dest=O/label;dest.mkdir(exist_ok=True)
 main=S/('baseline-baseline-capture' if label=='baseline' else 'candidate-candidate-capture')
 extra=S/('baseline-extra-baseline-capture' if label=='baseline' else 'candidate-extra-candidate-capture')
 for src in [main,extra]:
  for p in src.glob('*.png'):shutil.copy2(p,dest/p.name)
 for n in ['summary.json','ticks.jsonl','recipe.json','geometry.json']:
  shutil.copy2(main/n,dest/n)
 shutil.copy2(S/(label+'-seal-source/source-manifest.json'),dest/'source-manifest.json')
shutil.copy2(S/'candidate-candidate-capture/initial-common-scale.png',O/'trio-in-game.png')
shutil.copy2(S/'candidate-plan-cameras/camera-plan.json',O/'camera-plan.json')
shutil.copy2(S/'worklight-pixels/metrics.json',O/'worklight-pixels.json')
shutil.copy2(S/'rebuild-verification.json',O/'rebuild-verification.json')
# Individual large panels keep all three subjects judgeable, explicitly NOT common scale.
views=[('PELAGIC / approved battleship','initial-capital-detail',(200,150,1080,670)),
       ('TERN / new frigate','initial-escort-close',(330,240,960,560)),
       ('ANCHORAGE / new shipyard','initial-yard-close',(330,180,960,680))]
im=Image.new('RGB',(2250,710),(10,16,27));d=ImageDraw.Draw(im)
d.text((22,20),'THREE-ASSET SLICE / actual game detail views (individual framing)',font=font(30),fill=(225,235,245))
for i,(title,view,crop) in enumerate(views):
 tile=Image.open(S/'candidate-candidate-capture'/(view+'.png')).crop(crop);tile.thumbnail((720,570),Image.Resampling.LANCZOS)
 x=i*750;d.text((x+20,90),title,font=font(22),fill=(180,205,226));im.paste(tile,(x+(750-tile.width)//2,140+(550-tile.height)//2))
im.save(O/'three-asset-review.jpg',quality=94)
# Synchronized film: crop neither input, put readable labels above the live frames.
ffmpeg=shutil.which('ffmpeg');assert ffmpeg,'ffmpeg unavailable'
filtergraph="[0:v]pad=1280:840:0:40:color=0x0a101b,drawtext=text='BEFORE / actual game':x=20:y=8:fontsize=25:fontcolor=white[a];[1:v]pad=1280:840:0:40:color=0x0a101b,drawtext=text='AFTER / Blender-authored geometry':x=20:y=8:fontsize=25:fontcolor=white[b];[a][b]hstack=inputs=2[v]"
cmd=[ffmpeg,'-hide_banner','-y','-framerate','30','-i',str(S/'baseline-motion/frame-%04d.png'),'-framerate','30','-i',str(S/'candidate-motion/frame-%04d.png'),'-filter_complex',filtergraph,'-map','[v]','-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(O/'before-after-motion.mp4')]
with (S/'ffmpeg.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
print(O)
