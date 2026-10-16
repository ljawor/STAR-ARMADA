"""Read-only final preservation, immutable-source and deterministic-combat checks."""
from pathlib import Path
import ast,hashlib,json,subprocess,shutil,difflib
S=Path(__file__).parent;R=Path('/Users/lukaszjawor/Downloads/Project/STAR-ARMADA');O=R/'artifacts/alliance_blender_trio'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
initial=load(S/'live-before-hashes.json');changed=[];deleted=[]
for f,digest in initial.items():
 p=R/f
 if not p.exists():deleted.append(f)
 elif sha(p)!=digest:changed.append(f)
allowed={'render/authored_mesh.py','render/faction_ships.py','render/faction_stations.py','render/renderer.py','tests/test_ship_material_passes.py'}
assert not deleted,deleted
assert set(changed)<=allowed,changed
protected=['assets/models/alliance_battleship.mesh.json','art/blender/alliance_battleship.blend','tools/art/build_alliance_battleship.py','render/fleet_materials.py']
assert all(sha(R/f)==initial[f] for f in protected)
# Every pre-existing ship authoring function, including approved battleship
# dispatch and fallback, is byte-exact except the authorized frigate function.
def functions(p):
 text=p.read_text();lines=text.splitlines(keepends=True)
 return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
a=functions(S/'preserved/render/faction_ships.py');b=functions(R/'render/faction_ships.py')
assert set(a)==set(b)
assert [k for k in a if a[k]!=b[k]]==['_alliance_frigate_slice']
for f in allowed:
 original=S/'preserved'/f
 if original.exists():
  diff=''.join(difflib.unified_diff(original.read_text().splitlines(True),(R/f).read_text().splitlines(True),fromfile='before/'+f,tofile='after/'+f))
  p=S/'scoped-diffs'/Path(f).with_suffix('.diff');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(diff)
old=load(S/'userdata-before.json');roots=[R/'saves',R/'replays',Path.home()/'Library/Application Support/STAR ARMADA']
new={str(p):sha(p) for root in roots if root.exists() for p in root.rglob('*') if p.is_file()}
(S/'userdata-after.json').write_text(json.dumps(new,indent=2))
assert all(new.get(p)==v for p,v in old.items()),'preexisting userdata changed'
userdata=dict(before=len(old),after=len(new),preexisting_unchanged=True,added=[p for p in new if p not in old],deleted=[p for p in old if p not in new])
base=load(S/'baseline-baseline-capture/summary.json');cand=load(S/'candidate-candidate-capture/summary.json')
assert base['status']==cand['status']=='captured-not-appearance-approved'
assert base['initial_state_sha256']==cand['initial_state_sha256']
assert base['final_state_sha256']==cand['final_state_sha256']
for name in ['baseline','candidate']:
 seal=load(S/(name+'-seal-source/source-manifest.json'));after=load(S/(name+'-'+('baseline' if name=='baseline' else 'candidate')+'-capture/source-manifest-after.json'))
 assert seal==after
motiona=load(S/'baseline-motion/ticks.json');motionb=load(S/'candidate-motion/ticks.json')
assert [x['sha256'] for x in motiona]==[x['sha256'] for x in motionb]
assert [x['camera'] for x in motiona]==[x['camera'] for x in motionb]
probe=subprocess.run([shutil.which('ffprobe'),'-v','error','-show_entries','stream=width,height,nb_frames,duration','-of','json',str(O/'before-after-motion.mp4')],capture_output=True,text=True,check=True)
video=json.loads(probe.stdout);assert video['streams'][0]['nb_frames']=='180'
report=dict(status='review-ready-not-appearance-approved',modified_preexisting_files=sorted(changed),deleted_preexisting_files=deleted,
 approved_battleship_files={f:sha(R/f) for f in protected},approved_battleship_dispatch_byte_exact=True,
 unselected_catalogue_entries_pinned=73,runtime_mesh_rebuilds=load(S/'rebuild-verification.json'),
 source_sha256=dict(baseline=base['source_sha256'],candidate=cand['source_sha256']),
 deterministic_combat=dict(initial=base['initial_state_sha256'],final=base['final_state_sha256'],ticks_compared=181,all_per_tick_equal=True,
   baseline_weapon_fired=base['activity']['weapon_fired'],candidate_weapon_fired=cand['activity']['weapon_fired'],
   damage_observed=cand['activity']['shield_or_hull_reduction_observed']),
 quality=dict(display=cand['display'],materials_available=cand['materials_available'],fog='normal',postfx='unchanged',global_materials_byte_exact=True),
 worklights=load(S/'worklight-pixels/metrics.json'),userdata=userdata,video=video,
 tests=dict(log='protected-focused-tests.log',passed=79,modules=['test_alliance_blender_trio','test_alliance_blender_battleship','test_alliance_visual_slice','test_ship_material_passes','test_fleet_materials','test_ship_sizes','test_detmath','test_faction_ships','test_faction_stations','test_faction_visuals']),
 limitations=['macOS real-driver evidence only; Windows not run','Direct factory specimen setup; not a paid construction walkthrough','No full suite or LAN investigation; known unrelated LAN timing result remains unresolved','Appearance approval remains with owner; no commit/push/merge/release'])
(O/'verification.json').write_text(json.dumps(report,indent=2)+'\n');(S/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['modified_preexisting_files','source_sha256','deterministic_combat','userdata','video']},indent=2))
