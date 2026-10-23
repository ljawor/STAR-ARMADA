"""CPU recordings of actual Legions hardware meshes, never Blender or GPU."""
from collections import Counter
import importlib.util
import inspect
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/art/legions_redesign_hardware_designs.py'
KINDS = ('defense_satellite', 'attack_satellite', 'planet_extractor', 'planet_trade_hub',
         'planet_shield_generator', 'planet_pulsar_cannon')
SIGNATURES = {
    'defense_satellite': ('tracking gimbal', 'gun cradle', 'interceptor barrel', 'sensor cheek'),
    'attack_satellite': ('lance accelerator', 'split capacitor', 'recoil spine', 'vector engine'),
    'planet_extractor': ('robot shoulder', 'drill spindle', 'ore hopper', 'sorting conveyor'),
    'planet_trade_hub': ('routing carousel', 'handling elbow', 'cargo jaw', 'freight cassette'),
    'planet_shield_generator': ('emitter array', 'rooted buttress', 'field winding', 'capacitor bank'),
    'planet_pulsar_cannon': ('articulated trunnion', 'heavy breech', 'pulsar barrel', 'recoil piston'),
}


class Recording:
    """Record exact authored closed surfaces; no approximation or mock primitive."""
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces):
        self.parts.append((name, role, list(verts), [tuple(f) for f in faces]))


def load():
    assert SOURCE.exists(), 'Missing dedicated Legions hardware designs'
    spec = importlib.util.spec_from_file_location('legions_hardware', SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame_for(kind, transformed=False):
    bounds = json.loads((ROOT / f'assets/models/manifests/legion_{kind}.json').read_text())['bounds']
    lo, hi = bounds['min'], bounds['max']
    if transformed:
        lo = [v*s+t for v,s,t in zip(lo,(1.7,.63,2.1),(93,-21,47))]
        hi = [v*s+t for v,s,t in zip(hi,(1.7,.63,2.1),(93,-21,47))]
    return dict(lo=lo, hi=hi, span=[b-a for a,b in zip(lo,hi)],
                center=[(a+b)/2 for a,b in zip(lo,hi)])


def extent(part):
    return [(min(v[i] for v in part[2]),max(v[i] for v in part[2])) for i in range(3)]


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('transformed', (False,True))
def test_hardware_closed_supported_functional_and_budgeted(kind, transformed):
    m = load()
    assert tuple(inspect.signature(m.build).parameters) == ('kind','g','frame')
    g, frame = Recording(), frame_for(kind, transformed)
    m.build(kind,g,frame)
    caps = {'defense_satellite':2500, 'attack_satellite':2500, 'planet_extractor':3000,
            'planet_trade_hub':3000, 'planet_shield_generator':3500, 'planet_pulsar_cannon':3500}
    vertices = [v for p in g.parts for v in p[2]]
    triangles = sum(len(f)-2 for p in g.parts for f in p[3])
    assert 1800 < triangles <= caps[kind], (kind,triangles)
    assert len(vertices) < 9500
    assert {p[1] for p in g.parts} == {'base','dark','trim','accent','lit','cool'}
    assert len({p[0] for p in g.parts}) == len(g.parts)
    for axis in range(3):
        low, high = min(v[axis] for v in vertices), max(v[axis] for v in vertices)
        assert frame['lo'][axis] <= low < high <= frame['hi'][axis]
        assert (high-low)/frame['span'][axis] == pytest.approx(.998)
        assert (low+high)/2 == pytest.approx(frame['center'][axis])
    for name,role,vs,faces in g.parts:
        assert all(math.isfinite(c) for v in vs for c in v), name
        edges, directed = Counter(), Counter()
        for face in faces:
            assert len(set(face)) == len(face) >= 3
            assert all(0 <= i < len(vs) for i in face)
            for a,b in zip(face,face[1:]+face[:1]):
                edges[tuple(sorted((a,b)))] += 1
                directed[(a,b)] += 1
            for j in range(1,len(face)-1):
                a,b,c = (vs[i] for i in (face[0],face[j],face[j+1]))
                u,v = [b[i]-a[i] for i in range(3)],[c[i]-a[i] for i in range(3)]
                cross = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                assert sum(x*x for x in cross) > 1e-14, (name,face)
        assert set(edges.values()) == {2}, name
        assert all(directed[(a,b)] == directed[(b,a)] for a,b in directed), name
    for signature in SIGNATURES[kind]:
        matching = [p for p in g.parts if signature in p[0]]
        assert matching, (kind,signature)
        assert any(max((b-a)/s for (a,b),s in zip(extent(p),frame['span'])) >= .12
                   for p in matching), (kind,signature,'not camera scale')
    # Broad-phase rooted structure check, not a claim of fused manifold unions.
    bounds = [extent(p) for p in g.parts]
    connected = {0}
    while True:
        added = {j for j,b in enumerate(bounds) if j not in connected and any(
            all(b[k][0] <= bounds[i][k][1]+1e-7 and bounds[i][k][0] <= b[k][1]+1e-7
                for k in range(3)) for i in connected)}
        if not added:
            break
        connected.update(added)
    assert len(connected) == len(g.parts), [g.parts[i][0] for i in range(len(g.parts)) if i not in connected]
    # Large raised plates and dark machinery recesses, not budget-filling bolts.
    armor = [p for p in g.parts if 'plate bank' in p[0]]
    assert len(armor) >= 12
    assert all(len(p[2]) == 16 for p in armor)
    assert all(max((b-a)/s for (a,b),s in zip(extent(p),frame['span'])) > .10 for p in armor)
    assert len([p for p in g.parts if 'radiator fin' in p[0]]) >= 8
    print(kind, 'triangles=',triangles,'vertices=',len(vertices),'parts=',len(g.parts))


def top_visible(part, parts):
    """Exact upward ray at the center of a plate/fin, including coplanar cover."""
    px = sum(v[0] for v in part[2])/len(part[2])
    pz = sum(v[2] for v in part[2])/len(part[2])
    py = max(v[1] for v in part[2])
    for other in parts:
        if other is part or other[1] in ('lit','cool'):
            continue
        vs = other[2]
        for face in other[3]:
            for j in range(1,len(face)-1):
                a,b,c = (vs[k] for k in (face[0],face[j],face[j+1]))
                den = (b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
                if abs(den) < 1e-10:
                    continue
                u = ((b[2]-c[2])*(px-c[0])+(c[0]-b[0])*(pz-c[2]))/den
                v = ((c[2]-a[2])*(px-c[0])+(a[0]-c[0])*(pz-c[2]))/den
                w = 1-u-v
                if min(u,v,w) > -1e-8 and u*a[1]+v*b[1]+w*c[1] >= py-1e-7:
                    return False
    return True


@pytest.mark.parametrize('kind', KINDS)
def test_radiator_banks_are_exposed_not_buried_budget_fill(kind):
    g = Recording()
    load().build(kind,g,frame_for(kind))
    fins = [p for p in g.parts if 'radiator fin' in p[0]]
    visible = [p for p in fins if top_visible(p,g.parts)]
    assert len(visible) >= 8, (kind,[p[0] for p in visible])
    for p in g.parts:
        if ('processor dorsal plate bank' in p[0] or 'compressor armor plate bank' in p[0]):
            assert top_visible(p,g.parts), p[0]


# Camera-scale functional architecture must sit ON the broad pressure faces,
# not count roof tiles or disconnected ornaments as side-face machinery.
FACE_HOSTS = {
    'defense_satellite': ('shoulder armor', 2, (1,)),
    'attack_satellite': ('split capacitor', 2, (1,)),
    'planet_extractor': ('central robotic process tower', 2, (1,)),
    'planet_trade_hub': ('handling root column', 2, (1,)),
    'planet_shield_generator': ('emitter array pressure shell', 0, (-1, 1)),
    'planet_pulsar_cannon': ('heavy breech', 0, (-1, 1)),
}


def normalized_parts(kind):
    g = Recording()
    load().build(kind, g, dict(center=(0, 0, 0), span=(2/.998,)*3))
    return g.parts


def face_architecture(host, parts, axis, sign):
    """Measure substantial attached layers, excluding rear/roof-only details."""
    hb = extent(host)
    uv = [i for i in range(3) if i != axis]
    plane = hb[axis][sign > 0]
    layers = []
    for p in parts:
        if p is host:
            continue
        b = extent(p)
        outward = sign * (b[axis][sign > 0] - plane)
        root = sign * (b[axis][sign < 0] - plane)
        overlaps = [max(0, min(b[i][1], hb[i][1])-max(b[i][0], hb[i][0])) for i in uv]
        # A generous overlap tolerance permits a raised layer on a real backplane;
        # the independent host-mount test below requires a continuous root chain.
        if .04 <= outward <= .42 and -.10 <= root <= .30 and min(overlaps) >= .10:
            if overlaps[0]*overlaps[1] >= .035:
                layers.append(p)
    covered = 0
    for a in range(12):
        for b in range(12):
            point = [hb[i][0]+(hb[i][1]-hb[i][0])*(k+.5)/12 for i,k in zip(uv,(a,b))]
            covered += any(all(extent(p)[i][0] <= q <= extent(p)[i][1]
                               for i,q in zip(uv,point)) for p in layers)
    return layers, covered/144


@pytest.mark.parametrize('kind', KINDS)
def test_broad_faces_carry_camera_scale_layered_functional_machinery(kind):
    parts = normalized_parts(kind)
    prefix, axis, signs = FACE_HOSTS[kind]
    hosts = [p for p in parts if p[0].startswith(prefix+' ')]
    assert hosts
    for host in hosts:
        for sign in signs:
            layers, coverage = face_architecture(host, parts, axis, sign)
            assert len(layers) >= 3, (kind, host[0], sign, 'blank broad face', [p[0] for p in layers])
            assert coverage >= (.55 if kind == 'planet_shield_generator' else .35), (kind, host[0], sign, coverage)
            assert len({p[1] for p in layers}) >= 2
            depths = [sign*extent(p)[axis][sign > 0] for p in layers]
            assert max(depths)-min(depths) >= .045, (kind, 'flat applique, not layered machinery')


MACHINERY = {
    'defense_satellite': ('interceptor bank',),
    'attack_satellite': ('capacitor feed bank', 'capacitor forward plate bank'),
    'planet_extractor': ('process crusher mount', 'process crusher jaw', 'process crusher sorting sensor'),
    'planet_trade_hub': ('handling lift',),
    'planet_shield_generator': ('emitter power face',),
    'planet_pulsar_cannon': ('breech power drive',),
}
EXPOSED = {
    'defense_satellite': ('interceptor bank rotary feed', 'interceptor bank sensor lens'),
    'attack_satellite': ('capacitor feed bank terminal', 'capacitor feed bank interlock'),
    'planet_extractor': ('process crusher jaw', 'process crusher sorting sensor'),
    'planet_trade_hub': ('handling lift servo',),
    'planet_shield_generator': ('emitter power face vent louvre', 'emitter power face pod interlock'),
    'planet_pulsar_cannon': ('breech power drive vent cover', 'breech power drive conductor'),
}


def midpoint(part):
    return [sum(v[i] for v in part[2])/len(part[2]) for i in range(3)]


def assert_host_mounts(kind, parts):
    """Backplanes penetrate their actual host; attached layers have no AABB gaps.

    This is a CPU attachment guard, not a manifold union or visual approval.
    Unlike global connectivity it cannot attach a floating face to a nearby foot.
    """
    prefix, axis, signs = FACE_HOSTS[kind]
    hosts = [p for p in parts if p[0].startswith(prefix+' ')]
    family = [p for p in parts if any(p[0].startswith(s) for s in MACHINERY[kind])]
    mounts = [p for p in family if 'mount ' in p[0]]
    assert len(mounts) == len(hosts)*len(signs), (kind, 'missing functional backplane')
    groups = {p[0]: [] for p in mounts}
    for p in family:
        mount = min(mounts, key=lambda q: sum((a-b)**2 for a,b in zip(midpoint(p),midpoint(q))))
        groups[mount[0]].append(p)
    for mount in mounts:
        host = min(hosts, key=lambda p: sum((a-b)**2 for a,b in zip(midpoint(p),midpoint(mount))))
        sign = 1 if midpoint(mount)[axis] > midpoint(host)[axis] else -1
        hb, mb = extent(host), extent(mount)
        penetration = sign*(mb[axis][sign < 0]-hb[axis][sign > 0])
        assert -.07 <= penetration <= -.005, (mount[0], 'not embedded in host face', penetration)
        group = groups[mount[0]]
        connected = {mount[0]}
        while True:
            added = {p[0] for p in group if p[0] not in connected and any(
                all(extent(p)[i][0] <= extent(q)[i][1]+1e-8 and
                    extent(q)[i][0] <= extent(p)[i][1]+1e-8 for i in range(3))
                for q in group if q[0] in connected)}
            if not added:
                break
            connected.update(added)
        assert connected == {p[0] for p in group}, (kind, 'unmounted face layers', connected)


def outward_visible(part, parts, axis, sign):
    uv = [i for i in range(3) if i != axis]
    oriented = [(p[0],p[1],[(v[uv[0]],sign*v[axis],v[uv[1]]) for v in p[2]],p[3]) for p in parts]
    return top_visible(oriented[parts.index(part)], oriented)


@pytest.mark.parametrize('kind', KINDS)
def test_functional_face_backplanes_are_embedded_in_their_hosts(kind):
    parts = normalized_parts(kind)
    assert_host_mounts(kind, parts)
    # Negative control: translating machinery cannot pass by touching some
    # unrelated member of the globally connected machine.
    axis = FACE_HOSTS[kind][1]
    detached = [(name,role,[tuple(v[i]+(3 if i == axis else 0) for i in range(3)) for v in vs],faces)
                if any(name.startswith(s) for s in MACHINERY[kind]) else (name,role,vs,faces)
                for name,role,vs,faces in parts]
    with pytest.raises(AssertionError):
        assert_host_mounts(kind, detached)


@pytest.mark.parametrize('kind', KINDS)
def test_functional_controls_are_exposed_on_the_outward_faces(kind):
    parts = normalized_parts(kind)
    axis = FACE_HOSTS[kind][1]
    features = [p for p in parts if any(p[0].startswith(s+' ') for s in EXPOSED[kind])]
    assert features
    for p in features:
        sign = 1 if axis == 2 or midpoint(p)[0] > 0 else -1
        # Shield inward faces intentionally face the reactor/other wall; only
        # the external faces have an unobstructed ray to the production camera.
        if kind == 'planet_shield_generator' and abs(midpoint(p)[0]) < .6:
            continue
        assert outward_visible(p, parts, axis, sign), (kind, p[0], 'buried functional control')
        # An opaque cover of the same footprint must actually defeat the ray.
        b = extent(p)
        center = midpoint(p)
        center[axis] = b[axis][sign > 0]+sign*.06
        size = [max(.06, hi-lo) for lo,hi in b]
        cover_g = Recording()
        load()._Machine(cover_g,dict(center=(0,0,0),span=(2/.998,)*3)).panel('opaque cover','base',center,size)
        assert not outward_visible(p,parts+cover_g.parts,axis,sign)


def test_exact_hardware_scope_and_rejection_without_partial_emission():
    m = load()
    assert tuple(m.KINDS) == KINDS
    for invalid in ('fighter','shipyard','planet_fake','',None):
        g = Recording()
        with pytest.raises(ValueError):
            m.build(invalid,g,frame_for('defense_satellite'))
        assert not g.parts


@pytest.mark.parametrize('kind', KINDS)
def test_entire_geometry_obeys_affine_frame_not_only_its_bounds(kind):
    m = load()
    a,b = Recording(),Recording()
    fa,fb = frame_for(kind),frame_for(kind,True)
    m.build(kind,a,fa)
    m.build(kind,b,fb)
    assert len(a.parts) == len(b.parts)
    for pa,pb in zip(a.parts,b.parts):
        assert pa[:2] == pb[:2] and pa[3] == pb[3]
        for va,vb in zip(pa[2],pb[2]):
            for i in range(3):
                assert (va[i]-fa['center'][i])/fa['span'][i] == pytest.approx(
                    (vb[i]-fb['center'][i])/fb['span'][i])
