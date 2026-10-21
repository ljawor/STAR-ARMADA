"""The four damage contacts both renderers are asked to draw, defined once.

A contact is a parameter set: kind, where it sits, which way the armour faces, how big the damage
system made it, how old it is and its seed. The C++ fixture encodes exactly these numbers through
the bridge, and the Python capture hands the same numbers to the real `draw_hit`, so a mismatch in
the frame is a mismatch in the port rather than in the scene.

Two shield contacts (one fresh on a facing normal, one mid-life on a tilted normal) and two hull
contacts (one fresh, one old enough to have grown its smoke) - the four cases the port has branches
for.
"""
from __future__ import annotations

# A row across open space, high above the map so no hull shares the frame with a contact.
BASE_Y = 6000.0
SHELL_RADIUS = 260.0
CONTACTS = [
    # fresh contact, straight on: the cap and the first ripple
    dict(kind='shield_hit', x=-1200.0, normal=(0.0, 0.0, 1.0), radius=SHELL_RADIUS, size=12.0,
         age=0.06, seed=7),
    # mid-life contact on a tilted normal: both ripples, cap rotated away from the eye
    dict(kind='shield_hit', x=0.0, normal=(0.35, -0.25, 0.90), radius=SHELL_RADIUS, size=12.0,
         age=0.30, seed=11),
    # fresh hull contact: warm flash and sparks, no smoke yet
    dict(kind='hull_hit', x=1200.0, normal=(0.0, 0.0, 1.0), size=14.0, age=0.10, seed=3),
    # older hull contact: the smoky fragment has grown
    dict(kind='hull_hit', x=2400.0, normal=(0.2, 0.1, 0.97), size=14.0, age=0.30, seed=5),
]

# Both sides look at the row from here.
# The reference camera, chosen so a contact resolves to ~10 px on the Python side. The window cannot
# be asked for the same framing: its projection is handed degrees where bgfx wants radians
# (documented in docs/RENDER_W05_PLANES.md and still unfixed), so its apparent field of view is far
# wider and it will not frame a target at this pitch. That is why this slice's parity claim is made
# on geometry (tools/render/compare_hit_geometry.py) rather than on a pixel A/B.
CAMERA = dict(target=(600.0, BASE_Y, 0.0), distance=1100.0, pitch=20.0, yaw=8.0)


def effects():
    """The same contacts as simulation-style effect dicts, which is what the renderer consumes."""
    out = []
    for contact in CONTACTS:
        normal = contact['normal']
        if contact['kind'] == 'shield_hit':
            centre = (contact['x'], BASE_Y, 0.0)
            radius = contact['radius']
            point = tuple(centre[i] + normal[i] * radius for i in range(3))
            out.append({'kind': 'shield_hit', 'pos': point, 'center': centre, 'normal': normal,
                        'radius': radius, 'size': contact['size'], 't': contact['age'],
                        'seed': contact['seed']})
        else:
            point = (contact['x'], BASE_Y, 0.0)
            out.append({'kind': 'hull_hit', 'pos': point, 'normal': normal,
                        'size': contact['size'], 't': contact['age'], 'seed': contact['seed']})
    return out
