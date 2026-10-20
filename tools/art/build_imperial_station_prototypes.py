#!/usr/bin/env python3
"""Original Galactic Imperium station trio: Research Station, Defence Platform, Sensor Station.

One Blender run writes three editable masters and three runtime meshes. Rows are keyed by
binding; every station is fitted into its binding's approved envelope, so gameplay length,
collision radii and simulation hashes are untouched. Nothing outside the three pack
directories and the three .blend masters is written.

Blender --background --python-exit-code 1 --python this_file [-- --only research --render DIR]
"""
import argparse
import json
import os
import math
import struct
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
COLORS = {'base': (.32, .36, .40, 1), 'dark': (.065, .085, .11, 1),
          'trim': (.56, .60, .63, 1), 'accent': (.65, .16, .055, 1),
          'lit': (1, .65, .23, 1), 'cool': (.10, .78, 1, 1)}
MATS = {}
OBJECTS = []


def materials():
    for role in ROLES:
        m = bpy.data.materials.new(role)
        m.diffuse_color = COLORS[role]
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = COLORS[role]
        bsdf.inputs['Metallic'].default_value = .5
        bsdf.inputs['Roughness'].default_value = .4
        if role in ('lit', 'cool'):
            bsdf.inputs['Emission Color'].default_value = COLORS[role]
            bsdf.inputs['Emission Strength'].default_value = 2.2
        MATS[role] = m


def new_object(name, role, verts, faces, bevel=0.0, matrix=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj['role'] = role
    data.materials.append(MATS[role])
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    if bevel:
        mod = obj.modifiers.new('Manufactured broad-edge chamfer', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
    if matrix is not None:
        obj.matrix_world = matrix
    OBJECTS.append(obj)
    return obj


# Tiny trim, vents and fittings stay flat-edged; bevel budget belongs to masses.
def chamfer_for(size):
    dims = sorted(size)
    return 0.35 if dims[0] >= 2.4 and dims[1] * dims[2] >= 110 else 0.0


def box(name, role, loc, size, bevel=None):
    x, y, z = loc
    a, b, c = [v / 2 for v in size]
    verts = [(x + sx * a, y + sy * b, z + sz * c)
             for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return new_object(name, role, verts, faces, chamfer_for(size) if bevel is None else bevel)


def octagon(w, d, c):
    return [(-w + c, -d), (w - c, -d), (w, -d + c), (w, d - c),
            (w - c, d), (-w + c, d), (-w, d - c), (-w, -d + c)]


def octagon_radius(w, d, c, theta):
    """Radius of the eight-sided section along `theta`.

    Surface detail has to be placed with this rather than at a remembered radius: the
    section narrows with height and the chamfer cuts the corners in, so a fixed radius
    that touches the hull at mid height hangs in space near the top or the corner.
    """
    ca, sa = math.cos(theta), math.sin(theta)
    best = float('inf')
    verts = octagon(w, d, c)
    for i in range(len(verts)):
        x1, z1 = verts[i]
        x2, z2 = verts[(i + 1) % len(verts)]
        ex, ez = x2 - x1, z2 - z1
        det = -ca * ez + ex * sa
        if abs(det) < 1e-12:
            continue
        t = (-x1 * ez + ex * z1) / det
        u = (ca * z1 - sa * x1) / det
        if t > 1e-9 and -1e-9 <= u <= 1 + 1e-9 and t < best:
            best = t
    return best


def section(levels, y):
    """Interpolate a stacked section's (half-x, half-z, chamfer) at height `y`."""
    if y <= levels[0][0]:
        return levels[0][1], levels[0][2], levels[0][3]
    if y >= levels[-1][0]:
        return levels[-1][1], levels[-1][2], levels[-1][3]
    for low, high in zip(levels, levels[1:]):
        if low[0] <= y <= high[0]:
            f = (y - low[0]) / (high[0] - low[0]) if high[0] > low[0] else 0.0
            return tuple(a + (b - a) * f for a, b in zip(low[1:], high[1:]))
    return levels[-1][1], levels[-1][2], levels[-1][3]


def hull_point(levels, y, theta, loc=(0.0, 0.0), inset=0.0):
    """A point on, or `inset` inside, the hull surface at height `y` and bearing `theta`."""
    w, d, c = section(levels, y)
    r = octagon_radius(w, d, c, theta) - inset
    return (loc[0] + r * math.cos(theta), y, loc[1] + r * math.sin(theta))


def tier(name, role, levels, loc=(0.0, 0.0), bevel=0.0):
    """Eight-sided chamfered stack; each level is (y, half-x, half-z, chamfer)."""
    verts = []
    for y, w, d, c in levels:
        verts.extend((x + loc[0], y, z + loc[1]) for x, z in octagon(w, d, c))
    faces = []
    for level in range(len(levels) - 1):
        base, top = level * 8, (level + 1) * 8
        faces.extend((base + i, base + (i + 1) % 8, top + (i + 1) % 8, top + i) for i in range(8))
    faces.append(tuple(range(7, -1, -1)))
    faces.append(tuple(range((len(levels) - 1) * 8, len(levels) * 8)))
    return new_object(name, role, verts, faces, bevel)


def cylinder(name, role, center, radius, height, segments=12, bevel=0.0):
    x, y, z = center
    low, high = y - height / 2, y + height / 2
    verts, faces = [], []
    for ring_y in (low, high):
        for i in range(segments):
            a = 2 * math.pi * i / segments
            verts.append((x + radius * math.cos(a), ring_y, z + radius * math.sin(a)))
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j, segments + i))
    faces.append(tuple(range(segments - 1, -1, -1)))
    faces.append(tuple(range(segments, 2 * segments)))
    return new_object(name, role, verts, faces, bevel)


def frustum(name, role, center, r0, r1, height, segments=16, axis='y', bevel=0.0):
    """Closed cone/cylinder between two radii; a horn, dish or engine bell."""
    verts, faces = [], []
    for level, radius in ((-height / 2, r0), (height / 2, r1)):
        for i in range(segments):
            a = 2 * math.pi * i / segments
            verts.append((radius * math.cos(a), level, radius * math.sin(a)))
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j, segments + i))
    faces.append(tuple(range(segments - 1, -1, -1)))
    faces.append(tuple(range(segments, 2 * segments)))
    rot = Matrix.Identity(4)
    if axis == 'z':
        rot = Matrix.Rotation(math.radians(90), 4, 'X')
    elif axis == 'x':
        rot = Matrix.Rotation(math.radians(90), 4, 'Y')
    matrix = Matrix.Translation(Vector(center)) @ rot
    return new_object(name, role, verts, faces, bevel, matrix=matrix)


def ring(name, role, center, radius, tube, segments=40, sides=8, axis='z'):
    """Torus; axis names the ring normal. Vertical rings read as sensor hoops."""
    verts, faces = [], []
    for i in range(segments):
        u = 2 * math.pi * i / segments
        for j in range(sides):
            v = 2 * math.pi * j / sides
            rr = radius + tube * math.cos(v)
            if axis == 'z':
                verts.append((rr * math.cos(u), rr * math.sin(u), tube * math.sin(v)))
            else:
                verts.append((rr * math.cos(u), tube * math.sin(v), rr * math.sin(u)))
    for i in range(segments):
        ni = (i + 1) % segments
        for j in range(sides):
            nj = (j + 1) % sides
            faces.append((i * sides + j, ni * sides + j, ni * sides + nj, i * sides + nj))
    matrix = Matrix.Translation(Vector(center))
    return new_object(name, role, verts, faces, 0.0, matrix=matrix)


def beam(name, role, a, b, thickness, bevel=0.0):
    a, b = Vector(a), Vector(b)
    direction = b - a
    length = direction.length
    t = thickness / 2
    verts = [(-t, -t, 0), (t, -t, 0), (t, t, 0), (-t, t, 0),
             (-t, -t, length), (t, -t, length), (t, t, length), (-t, t, length)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    matrix = Matrix.Translation(a) @ direction.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return new_object(name, role, verts, faces, bevel, matrix=matrix)


def louvres(name, role, start, count, step, size, axis='x'):
    """A bank of vent slots; the axis says which way the bank runs."""
    x, y, z = start
    for i in range(count):
        if axis == 'x':
            box(name, role, (x + i * step, y, z), size)
        else:
            box(name, role, (x, y, z + i * step), size)


def windows(name, start, count, step, size, axis='x', role='lit'):
    louvres(name, role, start, count, step, size, axis)


RESEARCH_KEEL = [(-14.6, 24, 28, 5), (-9, 30, 33, 5), (-2, 31, 34, 5), (4, 28, 31, 4)]
RESEARCH_KEEL_DECK = [(4, 26, 29, 4), (7, 21, 24, 3.4), (9, 17, 20, 3)]
RESEARCH_DRUM = [(-8, 21, 20, 3.5), (-3, 26, 24, 4.5), (7, 26, 24, 4.5), (13, 22, 21, 3.5)]
RESEARCH_POD = [(2, 8, 11, 2), (8, 10, 13, 2.4), (16, 10, 13, 2.4), (21, 7, 9.6, 1.8)]
SENSOR_BASE = [(-22.8, 24, 21, 5), (-16, 29, 26, 6), (-9, 30, 27, 6), (-4, 27, 24, 5)]
SENSOR_MAST = [(-1, 9, 8, 2.6), (10, 7.4, 6.6, 2.2), (22, 6, 5.4, 1.8), (34, 4.6, 4.2, 1.4)]
DEFENCE_SKIRT = [(-13.6, 29, 29, 8), (-9, 36, 36, 10), (-4, 38.5, 38.5, 10), (-1, 35, 35, 8)]
DEFENCE_DECK = [(-2.4, 29, 29, 7), (1.0, 27, 27, 6), (5.4, 22, 22, 5), (8.0, 17, 17, 4)]
DEFENCE_CORE = [(6, 15, 15, 3.4), (12, 13, 13, 3), (17, 10, 10, 2.4)]


# ---------------------------------------------------------------- research station

def build_research():
    """A laboratory citadel: armoured keel, forward research drum with an observation
    cupola, two outrigger science pods on spars, and an aft comms/radiator array."""
    tier('Research armoured keel', 'base', RESEARCH_KEEL, loc=(0, 4))
    tier('Research keel upper deck', 'base', RESEARCH_KEEL_DECK, loc=(0, 4))
    # Keel plating, vent banks and deck lighting, all seated on the hull surface.
    keel_face = section(RESEARCH_KEEL, -6)[0]
    for s in (-1, 1):
        for i in range(6):
            box('Keel flank armour panel', 'trim', (s * (keel_face - .4), -6 + i * 2.6, 4), (.8, 2.2, 44))
        box('Keel owner stripe', 'accent', (s * (keel_face - .2), -1.5, 4), (.5, 1.1, 30))
    for i in range(9):
        box('Keel dorsal vent slot', 'dark', (-15.2 + i * 3.8, 9.1, 4), (3.1, .6, 3.2))
    for i in range(6):
        box('Keel deck work light', 'lit', (-14.5 + i * 5.8, 9.2, 21), (2.6, .5, .9))
    for i in range(4):
        box('Keel machinery housing', 'trim', (-13 + i * 9, 10.2, -6), (6.4, 2.6, 8))
        box('Keel machinery shadow', 'dark', (-13 + i * 9, 11.6, -6), (4.6, .4, 6))

    # Forward research drum.
    tier('Research laboratory drum', 'base',
         [(-8, 21, 20, 3.5), (-3, 26, 24, 4.5), (7, 26, 24, 4.5), (13, 22, 21, 3.5)], loc=(0, 38))
    tier('Drum collar', 'trim', [(13, 18, 17, 3), (16, 15, 14, 2.4)], loc=(0, 38))
    drum_forward = 38 + section(RESEARCH_DRUM, 9.4)[1]
    drum_aft = 38 - section(RESEARCH_DRUM, 6.4)[1]
    windows('Drum forward observation band', (-17, 9.4, drum_forward - .25), 9, 4.2, (3.2, 1.1, .5))
    windows('Drum rear observation band', (-17, 6.4, drum_aft + .35), 9, 4.2, (3.2, 1.1, .5))
    for s in (-1, 1):
        drum_side = section(RESEARCH_DRUM, 8.4)[0]
        windows('Drum flank observation band', (s * (drum_side - .2), 8.4, 26), 5, 4.6, (.5, 1.1, 3.2), axis='z')
        box('Drum flank service arm', 'trim', (s * (drum_side - 1.4), 1.5, 38), (3.0, 4.2, 10))
    box('Drum frontal owner chevron', 'accent', (0, 4.0, drum_forward - .3), (14, 2.6, .5))
    vent_y = 10.6
    vent_forward = 38 + section(RESEARCH_DRUM, vent_y)[1]
    for i in range(5):
        box('Drum frontal vent bank', 'dark', (-8 + i * 4, vent_y, vent_forward - .3), (3.1, 2.6, .5))

    # Observation cupola above the drum.
    tier('Observation cupola', 'trim',
         [(16, 12, 11, 2.6), (24, 9.5, 8.5, 2.2), (31, 6.5, 5.8, 1.6), (36, 3.4, 3.2, .8)], loc=(0, 38))
    windows('Cupola warm window ring', (-4.6, 24.5, 46.6), 5, 2.3, (1.5, .5, .5))
    windows('Cupola warm window ring aft', (-4.6, 24.5, 29.6), 5, 2.3, (1.5, .5, .5))
    beam('Cupola signal mast', 'trim', (0, 36, 38), (0, 40.2, 38), .9)
    box('Cupola mast beacon', 'cool', (0, 40.2, 38), (.9, .9, .9), .1)
    box('Cupola dish bracket', 'dark', (0, 33, 31), (2.4, 1.6, 3.2))

    # Outrigger science pods on spars.
    for s in (-1, 1):
        box('Science spar main', 'base', (s * 40, -1, 14), (22, 3.6, 5.2))
        box('Science spar brace', 'trim', (s * 30, 2.4, 14), (2.2, 5.4, 4))
        tier('Outrigger science pod', 'base', RESEARCH_POD, loc=(s * 51, 14))
        tier('Pod lower keel pod', 'base',
             [(-9, 6, 9, 1.6), (-4, 7.4, 11, 2.0), (1, 6, 9, 1.6)], loc=(s * 51, 14))
        aperture_y = 3.2
        aperture_face = section(RESEARCH_POD, aperture_y)[0]
        pod_flat = section(RESEARCH_POD, 4.0)[1] - section(RESEARCH_POD, 4.0)[2]
        for i in range(4):
            box('Pod flank sensor aperture', 'cool',
                (s * (51 + aperture_face - .15), aperture_y, 8 + i * 4.0), (.6, 1.3, 3.0))
        for i in range(4):
            box('Pod deck light row', 'lit', (s * (51 - 4 + i * 2.6), 21.2, 8), (2.2, .5, 3.0))
        box('Pod owner stripe', 'accent', (s * 51, 9.5, 14 + pod_flat - .3), (12, .5, .9))
        for i in range(3):
            fin_face = section(RESEARCH_POD, 6.5)[0]
            box('Pod radiator bank', 'dark', (s * (51 + fin_face - .15), 6.6, 19.5), (.5, 4.2, 8.0))
            box('Pod radiator bank lip', 'trim', (s * (51 + fin_face - .1), 8.8, 19.5), (.4, .5, 8.0))
        for i in range(3):
            box('Pod machinery cassette', 'trim', (s * 47, 13.4, 3 + i * 9), (5.6, 2.4, 7))
        cylinder('Pod sensor drum', 'dark', (s * 51, 15.4, 24), 3.4, 5.4, 14)
        frustum('Pod sensor horn', 'trim', (s * 51, 19.4, 24), 3.2, 1.5, 3.2, 14)
        box('Pod sensor glow', 'cool', (s * 51, 21.05, 24), (2.6, .3, 1.4))

    # Aft comms and radiator array.
    for i, (dx, dz) in enumerate(((-14, -30), (0, -34), (14, -30))):
        tier(f'Aft comms pedestal {i}', 'trim',
             [(2, 6, 5, 1.4), (12, 4.6, 4, 1.1), (20, 3.2, 2.8, .8)], loc=(dx, dz))
        bowl(f'Aft comms dish {i}', 'base', (dx, 22.2, dz - 2.4), 6.4, 3.6, 18, axis='-z')
        cylinder(f'Aft comms dish throat {i}', 'dark', (dx, 22.0, dz - 2.6), 2.0, 1.2, 12)
        box(f'Aft comms dish yoke {i}', 'dark', (dx, 21.2, dz - .6), (2.4, 2.4, 3.4))
        box(f'Aft comms dish feed glow {i}', 'cool', (dx, 22.2, dz - 3.4), (1.0, 1.0, .4))
    for s in (-1, 1):
        box('Aft radiator mast', 'dark', (s * 24, 10, -32), (1.6, 26, 12))
        beam('Aft radiator mast brace', 'trim', (s * 24, 21.6, -30), (s * 21.2, 8.4, -18), 1.0)
        box('Aft radiator mast root', 'trim', (s * 24, -1.4, -32), (3.2, 4.0, 13))
        for i in range(4):
            box('Aft radiator blade', 'trim', (s * 24, 1 + i * 6.4, -32), (.5, 4.6, 11))
        box('Aft radiator mast owner stripe', 'accent', (s * 24, 20, -32), (.5, 1.2, 11))
    box('Aft sensor bus', 'base', (0, 4, -34), (34, 8, 8))
    louvres('Aft bus louvre', 'dark', (-13, 8.4, -34), 7, 4.4, (3.2, .5, 7.2))
    for s in (-1, 1):
        beam('Aft outrigger strut', 'trim', (s * 18, 6, -26), (s * 30, 4, -18), 1.1)
        box('Aft docking clamp', 'dark', (s * 33, -8, -20), (5, 3.4, 12))
        box('Aft docking clamp trim', 'trim', (s * 35.4, -8, -20), (1.2, 3.6, 8))
    # Docking arms forward of the keel, one per side.
    for s in (-1, 1):
        tier('Forward docking arm', 'trim',
             [(-10, 4, 4, 1), (-4, 3.4, 3.4, .9), (4, 2.6, 2.6, .7)], loc=(s * 24, 26))
        box('Forward docking clamp jaw', 'dark', (s * 24, 4, 32), (3.4, 5, 3))

    # Second pass: layered plating, spine structure and instrument detail.
    plate_face = section(RESEARCH_KEEL, -9)[0]
    panel_face = section(RESEARCH_KEEL, -3)[0]
    for s in (-1, 1):
        for i in range(12):
            box('Spine flank armour plate', 'trim', (s * (plate_face - .4), -9.0, -26 + i * 4.6), (.8, 7.0, 3.8))
        for i in range(10):
            box('Spine flank recessed panel', 'dark', (s * (panel_face - .2), -3.0, -24 + i * 5.4), (.6, 4.0, 3.0))
        box('Spine keel rail', 'dark', (s * 16.2, -13.9, 4), (3.2, 2.2, 58))
        for i in range(5):
            rib_y = -12 + i * 1.6
            box('Spine frame rib', 'trim', (s * (section(RESEARCH_KEEL, rib_y)[0] - .5), rib_y, -24 + i * 13), (.9, 3.0, .9))
        beam('Science spar cable run', 'dark', (s * 22, .9, 12), (s * 47, .9, 12), .7)
        beam('Outrigger under-brace', 'trim', (s * 21, -6, 18), (s * 46, -5, 20), 1.0)
        pod_face = section(RESEARCH_POD, 11.6)[0]
        for i in range(4):
            box('Pod hull plate', 'trim', (s * (51 + pod_face - .2), 11.6, 8 + i * 4.0), (.8, .6, 4.6))
        box('Pod antenna housing', 'trim', (s * 54, 21.75, 8), (2.6, 1.8, 2.6))
        box('Pod antenna lens', 'cool', (s * 54, 22.75, 8), (1.4, .3, 1.4))
        frustum('Pod forward scanner', 'trim', (s * 51, 8.0, 26.4), 2.6, 1.2, 3.0, 12, axis='z')
        box('Pod scanner lens', 'cool', (s * 51, 8.0, 27.6), (1.6, 1.6, .4))
        box('Spine dorsal machinery', 'trim', (s * 12, 10.2, -22), (6.4, 3.2, 9.0))
    # Cupola observation dome cap and its lit ring.
    tier('Cupola dome cap', 'trim', [(33, 4.6, 4.2, 1.1), (36.0, 2.6, 2.4, .6)], loc=(0, 38))
    tier('Survey spire', 'trim', [(36.0, 2.4, 2.2, .5), (39.4, 1.3, 1.2, .3)], loc=(0, 38))
    for i in range(4):
        a = math.radians(45 + i * 90)
        beam('Spire stay', 'dark', (0, 30.5, 38),
             (4.4 * math.cos(a), 36.4, 38 + 4.0 * math.sin(a)), .45)
    for i in range(6):
        a = math.radians(i * 60)
        box('Cupola dome window', 'lit', (6.1 * math.cos(a) + 0, 31.4, 6.1 * math.sin(a) + 38), (1.3, 1.5, .5))
    for i in range(7):
        box('Drum crown plate', 'trim', (-14.4 + i * 4.8, 15.7, 30), (3.4, .6, 12))
    louvres('Drum machinery louvre', 'dark', (-16, 3.0, drum_forward - .4), 8, 4.4, (3.2, 3.0, .6))
    box('Drum forward hazard bar', 'accent', (0, 13.2, 61.8), (30, .6, .5))
    box('Drum forward hazard bar lower', 'accent', (0, 3.8, 61.8), (30, .6, .5))
    # Aft radiator wings read as broad panels, not sticks.
    for s in (-1, 1):
        box('Aft radiator wing', 'trim', (s * 26, 6, -33), (14, 26, 1.6))
        for i in range(4):
            box('Aft radiator wing rib', 'dark', (s * 26, -5 + i * 7.0, -33), (14.4, 1.0, 2.0))
        box('Aft radiator wing stripe', 'accent', (s * 26, 17, -33), (14, 1.2, .6))
    for i in range(3):
        box('Aft array bus housing', 'trim', (-10 + i * 9, 2.4, -37), (7.4, 6.0, 7.0))
    box('Dorsal survey boom', 'trim', (0, 9.9, 12), (2.2, 2.2, 26))
    for s in (-1, 1):
        tier('Spine outrigger buttress', 'base',
             [(-13.0, 7.5, 9.0, 2.0), (-8.0, 6.0, 7.0, 1.6), (-3.0, 4.4, 5.0, 1.2)],
             loc=(s * 13.0, 8))
        beam('Buttress to spine tie', 'trim', (s * 13.0, -13.4, 8), (s * 19.0, -9.0, 8), 1.2)
    box('Ventral sensor keel', 'dark', (0, -14.6, 4), (26, 3.0, 46))
    windows('Ventral lit conduit', (-11, -13.0, 18), 6, 4.4, (2.6, .5, .9))
    box('Dorsal survey lens', 'cool', (0, 9.9, 22), (2.0, 2.0, .6))


# ---------------------------------------------------------------- defence platform

def build_defence():
    """A squat armoured gun pad: octagonal skirt, four corner bastions with twin
    batteries, an ammunition core under lit bands and a compact fire-control mast."""
    tier('Platform armoured skirt', 'base',
         [(-13.6, 29, 29, 8), (-9, 36, 36, 10), (-4, 38.5, 38.5, 10), (-1, 35, 35, 8)], loc=(0, 0))
    tier('Platform fighting deck', 'base',
         [(-2.4, 29, 29, 7), (1.0, 27, 27, 6), (5.4, 22, 22, 5), (8.0, 17, 17, 4)], loc=(0, 0))
    # Skirt plating, hazard stripes and under-skirt machinery.
    for i in range(8):
        a = math.radians(22.5 + i * 45)
        box('Skirt armour buttress', 'trim',
            (32 * math.cos(a), -8, 32 * math.sin(a)), (7, 8.4, 7))
    for s in (-1, 1):
        box('Platform owner stripe', 'accent', (s * 38.9, -6, 0), (.5, 1.4, 37))
        box('Platform owner stripe forward', 'accent', (0, -6, s * 38.9), (37, 1.4, .5))
    for i in range(10):
        a = math.radians(i * 36)
        box('Skirt vent bank', 'dark', (36.6 * math.cos(a), -12.4, 36.6 * math.sin(a)), (3.4, .6, 5.4))
    for i in range(4):
        a = math.radians(45 + i * 90)
        box('Under-skirt machinery pod', 'trim', (30 * math.cos(a), -12.8, 30 * math.sin(a)), (8, 3.4, 8))
        box('Under-skirt machinery shadow', 'dark', (30 * math.cos(a), -14.4, 30 * math.sin(a)), (6, .5, 6))

    # Four corner bastions with twin batteries.
    for sx in (-1, 1):
        for sz in (-1, 1):
            cx, cz = sx * 26, sz * 26
            tier('Bastion tower', 'base',
                 [(0, 11.5, 11.5, 2.6), (6, 10, 10, 2.2), (12.4, 8.6, 8.6, 1.8)], loc=(cx, cz))
            cylinder('Bastion rotation race', 'dark', (cx, 13.2, cz), 7.2, 1.4, 14)
            tier('Bastion turret housing', 'base',
                 [(14.0, 7.8, 7.8, 1.8), (17.0, 7.0, 7.0, 1.6)], loc=(cx, cz))
            box('Bastion turret roof', 'trim', (cx, 17.4, cz), (10.6, .8, 10.6))
            box('Bastion owner chevron', 'accent', (cx, 17.6, cz + sz * 3.4), (7, .4, 1.1))
            for s in (-1, 1):
                beam('Twin battery barrel sleeve', 'dark',
                     (cx + s * 2.5, 16.4, cz + sz * 4.4), (cx + s * 2.5, 19.9, cz + sz * 16.0), 2.6)
                beam('Twin battery recoil collar', 'trim',
                     (cx + s * 2.5, 17.4, cz + sz * 7.0), (cx + s * 2.5, 18.2, cz + sz * 9.6), 3.4)
                beam('Twin battery muzzle brake', 'trim',
                     (cx + s * 2.5, 19.7, cz + sz * 14.4), (cx + s * 2.5, 20.0, cz + sz * 16.6), 3.2)
                box('Twin battery bore', 'dark', (cx + s * 2.5, 20.0, cz + sz * 16.9), (1.3, 1.3, .4))
                box('Bastion ammunition feed', 'trim', (cx + s * 5.4, 6.0, cz + sz * 4), (3.4, 4.4, 4.4))
            windows('Bastion ready light', (cx - 3.4, 8.8, cz + sz * 9.2), 3, 3.4, (1.6, .5, .5))

    # Central ammunition and power core.
    tier('Platform power core', 'base',
         [(6, 15, 15, 3.4), (12, 13, 13, 3), (17, 10, 10, 2.4)], loc=(0, 0))
    tier('Core cap', 'trim', [(17, 7.4, 7.4, 1.8), (19.4, 5.4, 5.4, 1.3)], loc=(0, 0))
    for i in range(8):
        a = math.radians(i * 45)
        vx, _, vz = hull_point(DEFENCE_CORE, 9.0, a, inset=.3)
        box('Core lit vent band', 'lit', (vx, 9.0, vz), (2.4, 4.4, .8))
        lx, _, lz = hull_point(DEFENCE_CORE, 12.4, a, inset=.2)
        box('Core louvre shadow', 'dark', (lx, 12.4, lz), (2.6, .6, 2.2))
    box('Core owner chevron', 'accent', (0, 17.1, 10.2), (9, .5, 1.4))
    beam('Fire control mast', 'trim', (0, 19, 0), (0, 20.2, 0), .8)
    box('Fire control radar face', 'cool', (0, 20.3, 1.8), (3.2, 1.1, .5))

    # Missile hatch banks between the bastions.
    for i in range(4):
        a = math.radians(45 + i * 90)
        cx, cz = 20 * math.cos(a), 20 * math.sin(a)
        box('Missile hatch bank', 'dark', (cx, 7.2, cz), (9, 2.2, 9))
        box('Missile hatch bank frame', 'trim', (cx, 8.6, cz), (10, .6, 10))
        for gx in (-2.6, 2.6):
            for gz in (-2.6, 2.6):
                box('Missile hatch cover', 'trim', (cx + gx, 9.2, cz + gz), (3.4, .5, 3.4))
                box('Missile hatch hazard', 'accent', (cx + gx, 8.95, cz + gz), (1.4, .3, .6))
    # Deck machinery and ammunition feeds.
    for i in range(6):
        a = math.radians(i * 60)
        bx, _, bz = hull_point(DEFENCE_DECK, 4.4, a, inset=3.0)
        box('Deck machinery cassette', 'trim', (bx, 4.4, bz), (6, 3.2, 5))
        sx, _, sz = hull_point(DEFENCE_DECK, 6.2, a, inset=2.4)
        box('Deck cassette shadow slot', 'dark', (sx, 6.2, sz), (4.2, .5, 3.4))
    for i in range(4):
        a = math.radians(45 + i * 90)
        beam('Deck ammunition conduit', 'trim',
             (12 * math.cos(a), 6.6, 12 * math.sin(a)), (24 * math.cos(a), 6.6, 24 * math.sin(a)), 1.3)

    # Second pass: close-defence mounts, plating fields, blast shields, radar.
    for i in range(4):
        a = math.radians(i * 90)
        point_turret('Close defence mount', (21 * math.cos(a), 6.4, 21 * math.sin(a)), .85, a)
    for i in range(8):
        a = math.radians(22.5 + i * 45)
        for row in range(3):
            py = -11.4 + row * 3.2
            px, _, pz = hull_point(DEFENCE_SKIRT, py, a, inset=.6)
            box('Skirt plating tile', 'trim', (px, py, pz), (5.4, 2.6, 1.0))
        hx, _, hz = hull_point(DEFENCE_SKIRT, -1.6, a, inset=1.0)
        box('Skirt blast shield', 'base', (hx, -1.6, hz), (9.0, 5.0, 1.4))
        beam('Skirt frame rib', 'dark',
             (34.4 * math.cos(a), -13.4, 34.4 * math.sin(a)), (30.4 * math.cos(a), 1.0, 30.4 * math.sin(a)), .9)
    for i in range(6):
        a = math.radians(i * 60)
        beam('Ammunition lift tube', 'dark',
             (10 * math.cos(a), 12.0, 10 * math.sin(a)), (26 * math.cos(a), 4.0, 26 * math.sin(a)), 1.6)
    tier('Fire control tower upper', 'trim', [(18.6, 4.6, 4.6, 1.2), (20.4, 3.4, 3.4, .9)], loc=(0, 0))
    for i in range(8):
        a = math.radians(i * 45)
        box('Core lit service window', 'lit', (11.4 * math.cos(a), 15.0, 11.4 * math.sin(a)), (2.0, 1.6, .6))
    for i in range(4):
        a = math.radians(45 + i * 90)
        box('Deck cable trunking', 'dark', (17 * math.cos(a), 6.4, 17 * math.sin(a)), (10, 1.0, 1.6))
        tx, _, tz = hull_point(DEFENCE_DECK, 3.6, a, inset=5.0)
        box('Deck plate tile', 'trim', (tx, 3.6, tz), (12, .6, 6))
    box('Radar face port', 'cool', (-2.6, 20.5, 0), (1.6, 1.0, .5))
    box('Radar face starboard', 'cool', (2.6, 20.5, 0), (1.6, 1.0, .5))


# ---------------------------------------------------------------- sensor station

def build_sensor():
    """A listening post: armoured base with two sensor drums, a braced lattice mast,
    a great vertical scanner hoop and a dish/antenna crown."""
    tier('Sensor base armoured hull', 'base',
         [(-22.8, 24, 21, 5), (-16, 29, 26, 6), (-9, 30, 27, 6), (-4, 27, 24, 5)], loc=(0, 0))
    tier('Sensor base deck', 'trim', [(-4, 26, 23, 4.6), (-1, 21, 19, 3.6)], loc=(0, 0))
    # Base plating, hazard bands and under-hull machinery.
    for i in range(8):
        a = math.radians(22.5 + i * 45)
        ax, _, az = hull_point(SENSOR_BASE, -14, a, inset=2.6)
        box('Base flank armour plate', 'base', (ax, -14, az), (6, 12, 6))
    for s in (-1, 1):
        box('Sensor owner stripe', 'accent', (s * 29.9, -13, 0), (.5, 1.3, 40))
        box('Sensor owner stripe forward', 'accent', (0, -13, s * 27.2), (44, 1.3, .5))
    for i in range(8):
        a = math.radians(i * 45)
        vx, _, vz = hull_point(SENSOR_BASE, -21.4, a, inset=.4)
        box('Base vent bank', 'dark', (vx, -21.4, vz), (3.2, .6, 4.8))
    for s in (-1, 1):
        box('Base docking clamp', 'dark', (s * 33, -14, 0), (6.4, 5.4, 13))
        box('Base docking clamp arm', 'trim', (s * 30, -14, 0), (1.6, 6, 9))

    # Two flanking sensor drums.
    for s in (-1, 1):
        cylinder('Flank sensor drum', 'base', (s * 18, 4, 0), 8.6, 14, 16)
        cylinder('Flank drum collar', 'trim', (s * 18, 10.6, 0), 9.2, 2.2, 16)
        for i, deg in enumerate((-46, -16, 16, 46)):
            ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            box('Flank drum aperture', 'cool',
                (s * 18 + 7.9 * ca, 6.4, 7.9 * sa), (1.6, 1.4, 1.6))
            box('Flank drum aperture aft', 'cool',
                (s * 18 + 7.9 * ca, 2.0, 7.9 * sa), (1.6, 1.4, 1.6))
        box('Flank drum owner band', 'accent', (s * 18, 11.1, 0), (5.4, .5, 12))
        box('Flank drum machinery', 'trim', (s * 18, -0.4, 6.4), (5.6, 5.0, 4.4))
        for i in range(4):
            box('Flank drum louvre', 'dark', (s * 18 - 4.2 + i * 2.8, 1.6, 8.4), (2.0, 7.0, .6))

    # Central lattice mast.
    tier('Sensor mast lower', 'base',
         [(-1, 9, 8, 2.6), (10, 7.4, 6.6, 2.2), (22, 6, 5.4, 1.8), (34, 4.6, 4.2, 1.4)], loc=(0, 0))
    for i in range(3):
        cy = 3 + i * 11
        cx_, _, cz_ = hull_point(SENSOR_MAST, cy, math.pi / 2, inset=1.6)
        box('Mast housing cassette', 'trim', (0, cy, cz_), (12, 5.6, 3.6))
        box('Mast housing shadow', 'dark', (0, cy + 1.8, cz_ + .9), (8.6, 2.4, .5))
    for i in range(6):
        sy = 1 + i * 6.4
        sx, _, sz = hull_point(SENSOR_MAST, sy, -math.pi / 2, inset=.5)
        box('Mast strake', 'trim', (sx, sy, sz), (9.4, 4.0, 1.4))
    fxp, _, fzp = hull_point(SENSOR_MAST, 27.0, math.pi / 2, inset=.15)
    box('Mast forward sensor slot', 'cool', (0, 27.0, fzp), (4.6, 1.6, .5))
    axp, _, azp = hull_point(SENSOR_MAST, 27.0, -math.pi / 2, inset=.15)
    box('Mast aft sensor slot', 'cool', (0, 27.0, azp), (4.6, 1.6, .5))
    for s in (-1, 1):
        beam('Mast lattice brace', 'trim', (s * 8, 2, 8), (s * 3.4, 30, 4.4), .9)
        beam('Mast lattice brace low', 'trim', (s * 7.4, 8, -6), (s * 3.4, 26, -4.4), .9)
        mx, _, mz = hull_point(SENSOR_MAST, 16, 0.0 if s > 0 else math.pi, inset=.2)
        box('Mast owner stripe', 'accent', (mx, 16, mz), (.5, 16, 1.2))
    windows('Mast warm aperture', (-2.4, 21, 5.6), 3, 2.4, (1.4, 1.6, .5))

    # Great vertical scanner hoop.
    ring('Scanner hoop', 'trim', (0, 34, 0), 22, 2.6, 44, 8, axis='z')
    ring('Scanner hoop inner glow', 'cool', (0, 34, 0), 19.2, .7, 44, 6, axis='z')
    for s in (-1, 1):
        box('Hoop mount block', 'dark', (0, 34, s * 2.4), (7.4, 7.4, 5.4))
    for i in range(12):
        a = math.radians(i * 30)
        box('Hoop clamp rib', 'dark', (21.6 * math.cos(a), 34 + 21.6 * math.sin(a), 0), (2.2, 2.2, 6.4))
        if i % 3 == 0:
            beam('Hoop brace', 'trim', (0, 34, 0), (20.0 * math.cos(a), 34 + 20.0 * math.sin(a), 0), .8)
    box('Hoop hub', 'base', (0, 34, 0), (10, 10, 6))

    # Crown: dishes, spikes and emitters.
    tier('Crown pedestal', 'trim', [(34, 5.4, 5, 1.6), (40, 4.2, 3.8, 1.2)], loc=(0, 0))
    for s in (-1, 1):
        bowl('Crown comms dish', 'base', (s * 8.4, 42.4, 2.0), 6.2, 3.2, 18, axis='x' if s > 0 else '-x')
        cylinder('Crown dish throat', 'dark', (s * 8.6, 42.4, 2.0), 1.8, 1.0, 12, )
        box('Crown dish feed glow', 'cool', (s * 9.9, 42.4, 2.0), (.4, 1.2, 1.2))
        beam('Crown dish arm', 'trim', (s * 3.4, 40, 0), (s * 8.4, 42, 0), .8)
        beam('Crown antenna spike', 'trim', (s * 3.2, 40, -3.2), (s * 5.4, 61.4, -5.2), .7)
        box('Crown spike tip', 'cool', (s * 5.4, 61.4, -5.2), (.9, 1.6, .9), .1)
        box('Crown emitter pod', 'dark', (s * 12, 38, 6), (4.4, 5.4, 4.4))
        box('Crown emitter face', 'cool', (s * 12, 38, 8.4), (2.6, 3.4, .4))
    beam('Crown centre mast', 'trim', (0, 40, 0), (0, 62.2, 0), .9)
    box('Crown centre beacon', 'cool', (0, 62.2, 0), (1.1, 1.1, 1.1), .1)
    for i in range(3):
        box('Crown equipment pod', 'base', (-4 + i * 4, 36.6, -3.4), (3.2, 3.4, 3.2))

    # Second pass: hoop yoke, lattice bracing, plating fields, cable runs.
    for i in range(4):
        a = math.radians(45 + i * 90)
        beam('Hoop yoke strut', 'trim',
             (0, 34, 0), (18.4 * math.cos(a), 34 + 18.4 * math.sin(a), 0), 1.1)
        beam('Hoop rim tie', 'dark',
             (19 * math.cos(a), 34 + 19 * math.sin(a), 0),
             (19 * math.cos(a + math.pi / 4), 34 + 19 * math.sin(a + math.pi / 4), 0), .6)
    for i in range(5):
        y = 4 + i * 7.0
        for s in (-1, 1):
            beam('Mast lattice diagonal', 'trim', (s * 6.4, y, 3.0), (-s * 5.2, y + 7.0, -3.0), .55)
            beam('Mast lattice diagonal aft', 'trim', (s * 6.4, y, -3.0), (-s * 5.2, y + 7.0, 3.0), .55)
    for i in range(6):
        a = math.radians(22.5 + i * 45) if i < 4 else math.radians(i * 60)
        px, _, pz = hull_point(SENSOR_BASE, -11.0, a, inset=2.8)
        box('Base plating tile', 'trim', (px, -11.0, pz), (5.6, 9.0, 1.0))
    for s in (-1, 1):
        beam('Drum cable run', 'dark', (s * 18, 12.4, 6.0), (s * 6.0, 18.0, 2.0), .8)
        box('Drum radiator plate', 'trim', (s * 26.6, 2.0, 0), (1.2, 13.0, 15.0))
        box('Drum radiator rib', 'dark', (s * 27.4, 2.0, 0), (.6, 12.0, 1.6))
        for i in range(3):
            box('Drum service hatch', 'trim', (s * 18, 6.0, 8.6 + i * .2), (4.4, 3.6, .5))
        beam('Base gantry rail', 'trim', (s * 26, -6.0, -20), (s * 12, -2.0, 18), .7)
    for i in range(8):
        a = math.radians(i * 45)
        lx, _, lz = hull_point(SENSOR_BASE, -21.0, a, inset=.4)
        box('Base lower vent', 'dark', (lx, -21.0, lz), (3.0, .8, 4.4))
    box('Base forward sensor lens', 'cool', (0, -14.0, 27.4), (7.0, 2.2, .5))
    box('Base aft docking throat', 'dark', (0, -14.0, -27.4), (9.0, 4.0, .8))


# ---------------------------------------------------------------- build + export

SCALE_LIMIT = 0.05


def fit_and_export(row, build, render_dir=None):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    OBJECTS.clear()
    build()
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in OBJECTS:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        points.extend(tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices)
        evaluated.to_mesh_clear()
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    envelope_low, envelope_high = row['envelope']
    # Land a hair inside the envelope: coordinates are written at 7 decimals and the
    # runtime rejects a replacement that exceeds the binding by any amount at all.
    scales = []
    for i in range(3):
        span = high[i] - low[i]
        target = envelope_high[i] - envelope_low[i]
        scales.append(min(target / span, 1.0 + SCALE_LIMIT) * 0.9995)
    root = bpy.data.objects.new(row['label'] + ' — complete editable prototype', None)
    bpy.context.collection.objects.link(root)
    for obj in OBJECTS:
        obj.parent = root
    root.scale = scales
    for i in range(3):
        root.location[i] = (envelope_low[i] + envelope_high[i] - (low[i] + high[i]) * scales[i]) / 2

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, indices, batches, parts = [], {}, {r: [] for r in ROLES}, []
    boxes = []
    skipped = 0
    for obj in OBJECTS:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        local = []
        corners = []
        for v in mesh.vertices:
            p = tuple(round(struct.unpack('f', struct.pack('f', float(c)))[0], 7)
                      for c in evaluated.matrix_world @ v.co)
            corners.append(p)
            if p not in indices:
                indices[p] = len(verts)
                verts.append(list(p))
            local.append(indices[p])
        if corners:
            boxes.append((obj.name,
                          [min(c[i] for c in corners) for i in range(3)],
                          [max(c[i] for c in corners) for i in range(3)]))
        role = obj['role']
        count = 0
        for tri in mesh.loop_triangles:
            ids = [local[k] for k in tri.vertices]
            a, b, c = (verts[k] for k in ids)
            u = [b[i] - a[i] for i in range(3)]
            v = [c[i] - a[i] for i in range(3)]
            n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            length = math.sqrt(sum(q * q for q in n))
            if length < 1e-12:
                skipped += 1
                continue
            batches[role].append([round(q / length, 15) for q in n] + ids)
            count += 1
        parts.append({'name': obj.name, 'role': role, 'triangles': count})
        evaluated.to_mesh_clear()
    # A part must touch something. Every greeble placed at a remembered radius instead of
    # the hull section at its own height hangs in space, which reads in game as loose blue
    # and black squares; measure contact rather than trusting the coordinates.
    floating = []
    for i, (name, lo, hi) in enumerate(boxes):
        for j, (_, olo, ohi) in enumerate(boxes):
            if i == j:
                continue
            if all(lo[a] - .6 <= ohi[a] and olo[a] - .6 <= hi[a] for a in range(3)):
                break
        else:
            floating.append(name)
    if os.environ.get('STATION_DUMP'):
        role_of = {o.name: o.get('role', '?') for o in OBJECTS}
        for name, lo, hi in boxes:
            print('PART %-10s %-30s x[%7.2f %7.2f] y[%6.2f %6.2f] z[%7.2f %7.2f]'
                  % (role_of.get(name, '?'), name.split('.')[0],
                     lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]), flush=True)
    if floating:
        from collections import Counter
        print('FLOATING ' + json.dumps(Counter(floating).most_common()), flush=True)
    assert not floating, f'{len(floating)} parts touch no other part: {sorted(set(floating))[:6]}'
    bounds = [[min(v[i] for v in verts) for i in range(3)], [max(v[i] for v in verts) for i in range(3)]]
    total = sum(len(v) for v in batches.values())
    data = {'contract': 'star-armada/mesh-export', 'contract_major': 1, 'asset': row['asset'],
            'authoring': 'Blender evaluated mesh', 'coordinates': 'X beam; Y up; +Z forward',
            'vertices': verts, 'batches': batches, 'bounds': bounds, 'parts': parts,
            'triangle_count': total}
    payload = json.dumps(data, separators=(',', ':')) + '\n'
    stats = {'binding': row['binding'], 'triangles': total, 'vertices': len(verts),
             'parts': len(parts), 'roles': {r: len(batches[r]) for r in ROLES},
             'bounds': bounds, 'bytes': len(payload.encode()), 'degenerate_skipped': skipped,
             'fit_scale': [round(s, 4) for s in scales]}
    print('GEOMETRY ' + json.dumps(stats), flush=True)
    assert total <= 11888 and len(verts) <= 9500, (total, len(verts))
    assert 1800 < total, total
    assert len(payload.encode()) <= 2000000
    assert all(batches[r] for r in ROLES), {r: len(batches[r]) for r in ROLES}
    for i in range(3):
        assert envelope_low[i] - 1e-4 <= bounds[0][i] and bounds[1][i] <= envelope_high[i] + 1e-4, bounds
        fill = (bounds[1][i] - bounds[0][i]) / (envelope_high[i] - envelope_low[i])
        assert fill >= 0.85, (i, round(fill, 3))

    master = row['master']
    export = row['export']
    master.parent.mkdir(parents=True, exist_ok=True)
    export.parent.mkdir(parents=True, exist_ok=True)

    if render_dir is not None:
        review_camera(root, row)
        render_dir.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(render_dir / f"{row['key']}.png")
        bpy.ops.render.render(write_still=True)

    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.wm.save_as_mainfile(filepath=str(master))
    export.write_text(payload)
    print('MASTER ' + str(master), flush=True)
    print('MESH ' + str(export), flush=True)
    return stats


def bowl(name, role, center, radius, depth, segments=20, axis='y', feed=True):
    """Concave dish: outer shell, rim band and a feed horn. Reads as a dish, not a flower."""
    verts, faces = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append((radius * math.cos(a), 0.0, radius * math.sin(a)))          # rim
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append((radius * .34 * math.cos(a), -depth, radius * .34 * math.sin(a)))  # throat
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append((radius * .93 * math.cos(a), .55, radius * .93 * math.sin(a)))    # rim lip
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j, segments + i))
        faces.append((segments + i, segments + j, 2 * segments + j, 2 * segments + i))
    faces.append(tuple(range(2 * segments, 3 * segments)))
    faces.append(tuple(range(segments - 1, -1, -1)))
    if feed:
        verts.append((0.0, .3 + depth * .8, 0.0))
        tip = len(verts) - 1
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((2 * segments + i, 2 * segments + j, tip))
    rot = Matrix.Identity(4)
    if axis == 'z':
        rot = Matrix.Rotation(math.radians(90), 4, 'X')
    elif axis == '-z':
        rot = Matrix.Rotation(math.radians(-90), 4, 'X')
    elif axis == 'x':
        rot = Matrix.Rotation(math.radians(90), 4, 'Y')
    elif axis == '-x':
        rot = Matrix.Rotation(math.radians(-90), 4, 'Y')
    matrix = Matrix.Translation(Vector(center)) @ rot
    return new_object(name, role, verts, faces, 0.0, matrix=matrix)


def plate_rows(name, role, start, count, step, size, axis='x'):
    """A field of thin raised armour plates: cheap triangles, strong manufactured read."""
    x, y, z = start
    for i in range(count):
        if axis == 'x':
            box(name, role, (x + i * step, y, z), size)
        else:
            box(name, role, (x, y, z + i * step), size)


def point_turret(name, center, scale=1.0, yaw=0.0):
    """Small close-defence mount: race, mantlet, twin stub barrels."""
    cx, cy, cz = center
    cylinder(name + ' race', 'dark', (cx, cy, cz), 3.4 * scale, 1.1 * scale, 10)
    tier(name + ' mantlet', 'base',
         [(cy + .5, 2.9 * scale, 2.9 * scale, .7 * scale), (cy + 2.4 * scale, 2.4 * scale, 2.4 * scale, .6 * scale)],
         loc=(cx, cz))
    for s in (-1, 1):
        dx = s * 1.15 * scale * math.cos(yaw)
        dz = s * 1.15 * scale * math.sin(yaw)
        box(name + ' barrel', 'dark',
            (cx + dx + 3.6 * scale * math.sin(yaw), cy + 1.7 * scale, cz + dz + 3.6 * scale * math.cos(yaw)),
            (0.9 * scale, 0.9 * scale, 7.2 * scale))
    box(name + ' sight', 'cool', (cx, cy + 3.1 * scale, cz), (1.1 * scale, .4 * scale, 1.1 * scale))


def review_camera(root, row):
    def aim(obj, target):
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

    def y_up_look_at(obj, location, target):
        """Screen-up must be the model's own +Y; Blender's world up is Z, so the
        basis is built directly instead of leaning on to_track_quat."""
        location, target = Vector(location), Vector(target)
        back = (location - target).normalized()          # camera local +Z
        right = Vector((0.0, 1.0, 0.0)).cross(back)
        if right.length < 1e-6:
            right = Vector((1.0, 0.0, 0.0))
        right.normalize()
        up = back.cross(right)
        basis = Matrix((right, up, back)).transposed().to_4x4()
        obj.matrix_world = Matrix.Translation(location) @ basis

    low, high = row['envelope']
    span = max(high[i] - low[i] for i in range(3))
    centre = [(low[i] + high[i]) / 2 for i in range(3)]
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.name = 'Prototype review three-quarter'
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = span * 1.6
    y_up_look_at(cam, (span * 0.95, centre[1] + span * 0.42, span * 0.86), centre)
    bpy.context.scene.camera = cam
    for name, offset, power, size in (('Key', (0.3, 1.6, 0.6), 300000, 120),
                                      ('Fill', (-1.3, 0.7, 0.2), 180000, 110),
                                      ('Rim', (0.2, 1.0, -1.3), 220000, 90)):
        bpy.ops.object.light_add(type='AREA', location=[centre[i] + offset[i] * span for i in range(3)])
        light = bpy.context.object
        light.name = name
        light.data.energy = power
        light.data.size = size
        aim(light, centre)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Dark navy authoring world')
    scene.world.color = (.045, .045, .045)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100


ROWS = (
    dict(key='research', label='IMPERIAL RESEARCH STATION', binding='imperial:research_station',
         asset='prototype:imperial/research_station',
         master=Path('art/blender/imperium_research_prototype.blend'),
         export=Path('visual_packs/imperium-research-prototype/assets/models/research.mesh.json'),
         envelope=((-60.925626, -15.0, -41.526279), (60.925626, 40.305438, 64.0)),
         build=build_research),
    dict(key='defence', label='IMPERIAL DEFENCE PLATFORM', binding='imperial:defense_platform',
         asset='prototype:imperial/defense_platform',
         master=Path('art/blender/imperium_defence_prototype.blend'),
         export=Path('visual_packs/imperium-defense-prototype/assets/models/defense.mesh.json'),
         envelope=((-44.258609, -13.5, -44.258609), (44.258609, 21.0, 44.258609)),
         build=build_defence),
    dict(key='sensor', label='IMPERIAL SENSOR STATION', binding='imperial:sensor_station',
         asset='prototype:imperial/sensor_station',
         master=Path('art/blender/imperium_sensor_prototype.blend'),
         export=Path('visual_packs/imperium-sensor-prototype/assets/models/sensor.mesh.json'),
         envelope=((-37.0, -23.0, -30.387721), (37.0, 62.355496, 30.387721)),
         build=build_sensor),
)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--only', choices=[row['key'] for row in ROWS])
    parser.add_argument('--render', type=Path)
    args = parser.parse_args(argv)
    root = args.output_root.resolve()
    results = {}
    for item in ROWS:
        if args.only and item['key'] != args.only:
            continue
        row = dict(item, master=root / item['master'], export=root / item['export'])
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.preferences.filepaths.save_version = 0
        MATS.clear()
        materials()
        results[item['key']] = fit_and_export(
            row, item['build'], (args.render / item['key']) if args.render else None)
    print('TRIO ' + json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
