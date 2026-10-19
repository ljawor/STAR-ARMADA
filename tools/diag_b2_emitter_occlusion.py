"""Diagnostic: which part occludes each B2 emitter as the guard test casts its ray."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, 'tests')
from test_alliance_blender_b2_squadron import ASSETS, load, measured_emitters  # noqa: E402

for asset in ASSETS:
    mesh = load(asset)
    payload = json.loads(Path(f"assets/models/{asset['identifier']}.mesh.json").read_text())
    names, tris = [], []
    for role in ('base', 'dark', 'trim', 'accent'):
        for name, tri in mesh[role]:
            names.append(name)
            tris.append(tri)
    names = np.array(names)
    T = np.array(tris)
    a, e1, e2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    d = np.array([0., 0., -1.])
    p = np.cross(d, e2)
    det = np.einsum('ij,ij->i', e1, p)
    safe = np.abs(det) > 1e-9
    inv = np.divide(1., det, out=np.zeros_like(det), where=safe)
    print(f'== {asset["identifier"]}')
    for name, (x, y, z), radius, face_z in measured_emitters(asset):
        o = np.array([x, y, face_z - .01])
        t = o - a
        u = np.einsum('ij,ij->i', t, p) * inv
        q = np.cross(t, e1)
        v = np.einsum('j,ij->i', d, q) * inv
        dist = np.einsum('ij,ij->i', e2, q) * inv
        hit = safe & (u >= 0) & (v >= 0) & (u + v <= 1) & (dist > 1e-5)
        who = ', '.join(f'{names[i]}@{o[2] - dist[i]:.2f}' for i in np.flatnonzero(hit)[:3])
        print(f'   {name:28s} face_z={face_z:9.3f} hits={hit.sum():3d}  {who}')
