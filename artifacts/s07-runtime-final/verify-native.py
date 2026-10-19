import hashlib,json
from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
folder=Path(__file__).parent/'native-attempt3'
r=json.loads((folder/'report.json').read_text()); assert r['status']=='passed' and len(r['rows'])==24
assert len({row['key'] for row in r['rows']})==24
assert r['harness_sha256']==sha(folder.parent/'native-matrix.py')
count=0
for row in r['rows']:
 assert len(row['captures'])==9
 for record in row['captures'].values():
  assert sha(folder/record['file'])==record['sha256'] and record['repeat_equal']; count+=1
 assert all(v>0 for v in row['metrics'].values())
assert not r['protected_changed'] and r['shipped_movie_unchanged']
pins=json.loads((ROOT/'artifacts/s07-integration/S07-PROTECTED-INPUTS.json').read_text())['sha256']
assert all(sha(ROOT/p)==h for p,h in pins.items())
rows=[row for row in r['rows'] if row['preview'] and row['binding'].endswith(':frigate')]; assert len(rows)==4
sheet=Image.new('RGB',(1280,4*285),(12,17,25)); draw=ImageDraw.Draw(sheet)
for i,row in enumerate(rows):
 for j,color in enumerate(('red','blue')):
  im=Image.open(folder/row['captures'][color]['file']).crop((330,180,950,620)); im.thumbnail((620,250))
  sheet.paste(im,(j*640,i*285+28)); draw.text((j*640+12,i*285+8),row['binding']+' | '+color+' owner | selected',fill='white')
path=folder/'selected-owner-sheet.jpg'; sheet.save(path,quality=94)
receipt={'status':'passed','rows':len(r['rows']),'verified_captures':count,'protected_count':len(pins),'protected_preserved':True,'harness_sha256':r['harness_sha256'],'report_sha256':sha(folder/'report.json'),'sheet_sha256':sha(path),'limits':'12 representative subjects x legacy/preview. No catalogue-wide, hidden raster, motion, construction or LOD closure.'}
(folder/'readback.json').write_text(json.dumps(receipt,indent=2)+'\n'); print(json.dumps(receipt))
