"""Find the stray low-Z triangle in the syndicate convoy export and name its part."""
import json
from pathlib import Path

payload = json.loads(Path('assets/models/syndicate_convoy.mesh.json').read_text())
verts = payload['vertices']
limits = {p['name']: p for p in payload['parts']}
offsets = {role: 0 for role in payload['batches']}
print('parts whose triangles reach below z=-76.4:')
for part in payload['parts']:
    role = part['role']
    start = offsets[role]
    end = start + part['triangles']
    offsets[role] = end
    rows = payload['batches'][role][start:end]
    zs = [verts[i][2] for r in rows for i in r[3:]]
    if min(zs) < -76.4:
        lowest = sorted({round(z, 4) for z in zs})[:3]
        print(f"  {part['name']:32s} role={role:7s} tris={part['triangles']:4d} minz={min(zs):9.4f} zs={lowest}")
        for r in rows:
            if min(verts[i][2] for i in r[3:]) < -76.5:
                pts = [tuple(round(c, 3) for c in verts[i]) for i in r[3:]]
                print(f"        tri {r[3:]}: {pts}")
