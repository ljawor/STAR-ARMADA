"""Read-only B6 preservation/delta receipt; no authoring or Blender execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
old = json.loads((ROOT / 'artifacts/s06-completion/sidecar-preservation-before.json').read_text())
changed = [p for p, h in old.items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
print('Protected existing files:', len(old))
print('Protected files modified/deleted:', len(changed))
print('Protected differences:', changed)
assert not changed
sheet = json.loads((ROOT / 'art/manifests/pending/S06-BATCH-B6-IMPERIAL-SHIPS.json').read_text())
print('B6 authored bindings:', len(sheet['assets']))
for asset in sheet['assets']:
    path = 'art/manifests/pending/S06-' + asset['identifier'].upper().replace('_', '-') + '.json'
    before = json.loads(subprocess.check_output(['git', 'show', 'HEAD:' + path], cwd=ROOT))
    after = json.loads((ROOT / path).read_text())
    keys = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    print(path + ': changed fields=' + ', '.join(keys))
    for key in ('source', 'export_script', 'runtime', 'evidence', 'motion', 'envelope',
                'gameplay_entity', 'appearance_decision', 'owner_decision', 'activation'):
        assert before[key] == after[key], (path, key)
print('B6 per-asset model/review/approval fields preserved: 8/8')
print('Seed SHA256:', hashlib.sha256((ROOT / 'tools/art/build_b6_imperial_ships.py').read_bytes()).hexdigest())
paths = subprocess.check_output(['git', 'ls-files', 'art/manifests/pending/S06-BATCH-*.json'], cwd=ROOT, text=True).splitlines()
failed = 0
for path in paths:
    batch = json.loads((ROOT / path).read_text())['batch']
    result = subprocess.run([sys.executable, 'tools/art/write_pending_sidecars.py', '--batch', batch, '--check'], cwd=ROOT, capture_output=True, text=True)
    print(batch + ': exit=' + str(result.returncode) + ' ' + result.stdout.strip())
    if result.returncode:
        failed += 1
        print(result.stderr)
print('Pre-existing batch checks:', len(paths), 'failed:', failed)
assert not failed
