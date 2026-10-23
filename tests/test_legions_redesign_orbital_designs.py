"""Pure CPU contracts for ten newly authored machine orbital installations."""
import collections
import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('command_station', 'shipyard', 'mining_station', 'research_station',
         'defense_platform', 'sensor_station', 'trade_station', 'fighter_platform',
         'repair_dock', 'energy_relay')
CAPS = dict(command_station=6000, shipyard=11000, mining_station=4500,
            research_station=5000, defense_platform=4500, sensor_station=4500,
            trade_station=4500, fighter_platform=4500, repair_dock=5000, energy_relay=4000)
ROLES = {'base', 'dark', 'trim', 'accent', 'lit', 'cool'}
FRAME = dict(lo=(-7., -3., -11.), hi=(9., 7., 13.), span=(16., 10., 24.), center=(1., 2., 1.))


class RecordingGeometry:
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces):
        self.parts.append((name, role, list(verts), [tuple(f) for f in faces]))


def module():
    path = ROOT / 'tools/art/legions_redesign_orbital_designs.py'
    assert path.exists(), 'Ten Legions orbital designs are not implemented'
    spec = importlib.util.spec_from_file_location('legions_orbital_cpu', path)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def specimen(kind, frame=FRAME):
    g = RecordingGeometry()
    module().build(kind, g, frame)
    return g


def bounds(g):
    return [(tuple(min(v[i] for v in vv) for i in range(3)),
             tuple(max(v[i] for v in vv) for i in range(3))) for _, _, vv, _ in g.parts]


def normalized(v):
    return tuple((v[i]-FRAME['center'][i]) / (.4995*FRAME['span'][i]) for i in range(3))


def test_exact_ten_kind_interface():
    assert set(module().KINDS) == set(KINDS)


@pytest.mark.parametrize('kind', KINDS)
def test_native_scale_panel_banks_recesses_and_layered_machine_faces(kind):
    m = module()
    d = m._Design()
    m._BUILDERS[kind](d)
    # A native-sized process casing gets broad segmented roof armor, a race
    # below its lips, and a socket/processor/lens stack, not repeated microbars.
    for casing, role, vs, _ in list(d.parts):
        if ' armor bank ' not in casing:
            continue
        stem = casing.split(' armor bank ')[0]
        parts = [p for p in d.parts if p[0].startswith(stem+' ')]
        panels = [p for p in parts if 'segmented armor panel' in p[0]]
        races = [p for p in parts if 'recessed service race' in p[0]]
        heads = [p for p in parts if 'machine head' in p[0]]
        assert len(panels) >= 2, (kind, stem, 'blank process roof')
        assert races and len(heads) >= 2, (kind, stem, 'missing functional layers')
        dims = [max(v[i] for v in vs)-min(v[i] for v in vs) for i in range(3)]
        for _, _, pv, _ in panels:
            pd = [max(v[i] for v in pv)-min(v[i] for v in pv) for i in range(3)]
            assert pd[0] >= dims[0]*.20 and pd[2] >= dims[2]*.60
        assert max(v[1] for v in races[0][2]) < max(v[1] for v in panels[0][2])
    assert any('segmented armor panel' in p[0] for p in d.parts)


@pytest.mark.parametrize('kind', KINDS)
def test_geometry_contract(kind):
    g = specimen(kind)
    vv = [v for _, _, vs, _ in g.parts for v in vs]
    triangles = sum(len(f)-2 for _, _, _, fs in g.parts for f in fs)
    assert 1800 < triangles <= CAPS[kind]
    assert len(vv) < 9500
    assert {r for _, r, _, _ in g.parts} == ROLES
    assert len({n for n, _, _, _ in g.parts}) == len(g.parts)
    for axis in range(3):
        lo, hi = min(v[axis] for v in vv), max(v[axis] for v in vv)
        assert FRAME['lo'][axis] <= lo < hi <= FRAME['hi'][axis]
        assert math.isclose(hi-lo, .999*FRAME['span'][axis], rel_tol=1e-8)
    for name, _, vs, fs in g.parts:
        edges = collections.Counter()
        directed = collections.Counter()
        volume = 0.
        for f in fs:
            assert len(f) >= 3 and len(set(f)) == len(f), name
            assert all(0 <= i < len(vs) for i in f), name
            for a, b in zip(f, f[1:]+f[:1]):
                edges[tuple(sorted((a, b)))] += 1
                directed[(a, b)] += 1
            for j in range(1, len(f)-1):
                a, b, c = (vs[f[q]] for q in (0, j, j+1))
                u, v = ([b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)])
                cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                assert sum(x*x for x in cross) > 1e-18, name
                volume += sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6
        assert set(edges.values()) == {2}, name
        assert all(directed[(a,b)] == directed[(b,a)] for a,b in edges), name
        assert volume > 0, (name, volume)
    print(f'{kind}: {triangles} triangles, {len(vv)} vertices, {len(g.parts)} closed solids')


@pytest.mark.parametrize('kind', KINDS)
def test_connected_machinery_and_substantial_surface_features(kind):
    g = specimen(kind)
    boxes = bounds(g)
    reached = {0}
    while True:
        additions = {j for j, (lo, hi) in enumerate(boxes) if j not in reached
                     and any(all(lo[a] <= boxes[k][1][a]+1e-8 and hi[a] >= boxes[k][0][a]-1e-8
                                 for a in range(3)) for k in reached)}
        if not additions:
            break
        reached.update(additions)
    assert len(reached) == len(boxes), [g.parts[i][0] for i in range(len(boxes)) if i not in reached]
    # A necessary attachment guard, not a Boolean-union proof. All detail is
    # volumetric and mounted; no flat decals or floating per-face microbars.
    substantial = []
    for (name, _, vs, _), (lo, hi) in zip(g.parts, boxes):
        dims = sorted((hi[i]-lo[i])/(.4995*FRAME['span'][i]) for i in range(3))
        if any(s in name for s in ('armor', 'manifold', 'drive', 'vent', 'processor', 'switchgear')):
            if dims[0] >= .065 and dims[1] >= .15 and dims[2] >= .23:
                substantial.append(name)
    assert len(substantial) >= 8, (kind, substantial)


@pytest.mark.parametrize('kind', ('shipyard', 'repair_dock', 'fighter_platform'))
def test_genuine_open_working_corridors(kind):
    g = specimen(kind)
    boxes = [(normalized(lo), normalized(hi)) for lo, hi in bounds(g)]
    for x in (-.20, 0., .20):
        for y in (-.15, .05, .25):
            for z in (-.25, .1, .45, .75):
                assert not any(all(lo[i] < p < hi[i] for i,p in enumerate((x,y,z))) for lo,hi in boxes), (kind,x,y,z)


def test_distinct_architectures_and_real_annular_bores():
    fingerprints = set()
    for kind in KINDS:
        g = specimen(kind)
        fingerprint = tuple((r, tuple(round(c, 5) for c in normalized(vs[0])), len(vs)) for _,r,vs,_ in g.parts)
        assert fingerprint not in fingerprints
        fingerprints.add(fingerprint)
        rings = [(n, vs, fs) for n, _, vs, fs in g.parts
                 if n.rsplit(' ',2)[-2] in ('bore','coil')]
        if kind in ('mining_station', 'research_station', 'energy_relay', 'defense_platform'):
            assert rings, kind
            for n, vs, fs in rings:
                edges = {tuple(sorted((a,b))) for f in fs for a,b in zip(f,f[1:]+f[:1])}
                assert len(vs)-len(edges)+len(fs) == 0, (kind,n,'capped rather than annular')


def _sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def _dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _directions(vectors):
    result = {}
    for v in vectors:
        length = math.sqrt(_dot(v,v))
        if length < 1e-10:
            continue
        v = tuple(t/length for t in v)
        if next(t for t in v if abs(t)>1e-10) < 0:
            v = tuple(-t for t in v)
        result[tuple(round(t,7) for t in v)] = v
    return list(result.values())


def _convex(vs,fs):
    normals = _directions(_cross(_sub(vs[f[1]],vs[f[0]]),_sub(vs[f[2]],vs[f[0]])) for f in fs)
    edges = _directions(_sub(vs[a],vs[b]) for f in fs for a,b in zip(f,f[1:]+f[:1]))
    box = tuple((min(v[i] for v in vs),max(v[i] for v in vs)) for i in range(3))
    return vs,normals,edges,box


def _convex_pieces(part):
    _,_,vs,fs = part
    edges = {tuple(sorted((a,b))) for f in fs for a,b in zip(f,f[1:]+f[:1])}
    if len(vs)-len(edges)+len(fs) == 0:
        # Decompose a true annulus into convex sectors: never treat its empty
        # bore as solid, which would incorrectly validate floating central nodes.
        n = len(vs)//4
        faces = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        return [_convex([vs[k*n+j] for k in range(4) for j in (i,(i+1)%n)],faces)
                for i in range(n)]
    return [_convex(vs,fs)]


def _intersects(a,b):
    av,an,ae,ab = a
    bv,bn,be,bb = b
    if any(ab[i][0]>bb[i][1]+1e-8 or bb[i][0]>ab[i][1]+1e-8 for i in range(3)):
        return False
    axes = an+bn+[_cross(x,y) for x in ae for y in be]
    for axis in axes:
        if _dot(axis,axis) < 1e-16:
            continue
        ap,bp = [_dot(p,axis) for p in av],[_dot(p,axis) for p in bv]
        if min(ap)>max(bp)+1e-8 or min(bp)>max(ap)+1e-8:
            return False
    return True


@pytest.mark.parametrize('kind', KINDS)
def test_actual_surface_attachment_not_just_overlapping_bounding_boxes(kind):
    g = specimen(kind)
    hulls = [_convex_pieces(p) for p in g.parts]
    boxes = bounds(g)
    reached = {0}
    remaining = set(range(1,len(g.parts)))
    frontier = [0]
    while frontier:
        i = frontier.pop()
        lo,hi = boxes[i]
        for j in list(remaining):
            jl,jh = boxes[j]
            if any(lo[k]>jh[k]+1e-8 or jl[k]>hi[k]+1e-8 for k in range(3)):
                continue
            if any(_intersects(a,b) for a in hulls[i] for b in hulls[j]):
                reached.add(j)
                remaining.remove(j)
                frontier.append(j)
    assert not remaining, [g.parts[i][0] for i in sorted(remaining)]


def test_invalid_kind_and_frame_rejected_before_emission():
    m = module()
    for kind, frame in [('bogus', FRAME), ('command_station', {}),
                        ('command_station', dict(FRAME, span=(16,0,24))),
                        ('command_station', dict(FRAME, center=(1,float('nan'),1)))]:
        g = RecordingGeometry()
        with pytest.raises(ValueError):
            m.build(kind,g,frame)
        assert not g.parts


def test_translated_anisotropic_frame_and_determinism():
    m = module()
    frame = dict(lo=(9,20,30), hi=(11,26,40), span=(2,6,10), center=(10,23,35))
    for kind in KINDS:
        a, b = specimen(kind), specimen(kind, frame)
        assert a.parts == specimen(kind).parts
        for pa, pb in zip(a.parts,b.parts):
            assert pa[:2] == pb[:2] and pa[3] == pb[3]
            for va,vb in zip(pa[2],pb[2]):
                assert all(math.isclose((va[i]-FRAME['center'][i])/FRAME['span'][i],
                                        (vb[i]-frame['center'][i])/frame['span'][i],abs_tol=1e-12) for i in range(3))


# Original machine-coordinate bounds: retaining the output frame alone would
# conceal a scale/silhouette change if a new attachment extended the raw model.
ENVELOPES = {
    'command_station': ((-.975,-.843,-.9),(1.0158,.8712,.96)),
    'shipyard': ((-1.04,-.76,-1.01),(1.0752,.958,1.0114)),
    'mining_station': ((-.91,-1.085,-.655),(.9468,.55,1.059)),
    'research_station': ((-1.,-.7382,-.8),(1.,.9714,1.0586)),
    'defense_platform': ((-1.06,-.723,-.84),(1.06,.434,1.19)),
    'sensor_station': ((-.815,-.9204,-.785),(.8542,1.0578,.2768)),
    'trade_station': ((-1.01,-.673,-1.02),(1.0468,.79,1.0776)),
    'fighter_platform': ((-1.055,-.7788,-1.03),(1.0862,.84,1.)),
    'repair_dock': ((-1.17,-.561,-1.11),(1.17,.71297979,.9866)),
    'energy_relay': ((-.935,-.95,-.595),(.9694,.975,.515)),
}


@pytest.mark.parametrize('kind', KINDS)
def test_original_machine_envelope_and_direct_host_attachment(kind):
    m = module()
    d = m._Design()
    m._BUILDERS[kind](d)
    vs = [v for _,_,pv,_ in d.parts for v in pv]
    for axis in range(3):
        assert min(v[axis] for v in vs) == pytest.approx(ENVELOPES[kind][0][axis],abs=1e-8)
        assert max(v[axis] for v in vs) == pytest.approx(ENVELOPES[kind][1][axis],abs=1e-8)
    assert len(d.attachments) >= 40
    for child, host in d.attachments:
        assert child > host
        assert any(_intersects(a,b) for a in _convex_pieces(d.parts[child])
                   for b in _convex_pieces(d.parts[host])), (kind,d.parts[child][0],d.parts[host][0])
        # A fitting wholly buried in the declared parent has no visible purpose.
        center, span, basis = d.hosts[host]
        axes = basis or ((1,0,0),(0,1,0),(0,0,1))
        assert any(abs(_dot(_sub(v,center),axes[i])) > span[i]*.5+1e-6
                   for v in d.parts[child][2] for i in range(3)), (kind,d.parts[child][0],'buried')


def _surface_area(parts, roles):
    area = 0.
    for _, role, vs, fs in parts:
        if role not in roles:
            continue
        for f in fs:
            for j in range(1,len(f)-1):
                cross = _cross(_sub(vs[f[j]],vs[f[0]]),_sub(vs[f[j+1]],vs[f[0]]))
                area += math.sqrt(_dot(cross,cross))*.5
    return area


@pytest.mark.parametrize('kind', KINDS)
def test_power_color_is_localized_not_whole_module_faces(kind):
    g = specimen(kind)
    assert _surface_area(g.parts, {'cool','lit'}) / _surface_area(g.parts, ROLES) < .10


def test_shipyard_structural_faces_carry_large_process_stations():
    g = specimen('shipyard')
    for feature, minimum in [('portal sectional deck armor',9),
                             ('portal face machinery',6),
                             ('attached service gantry',6),
                             ('assembly head socket',6)]:
        assert sum(feature in n for n,_,_,_ in g.parts) >= minimum, feature
    for n,_,vs,_ in g.parts:
        if 'portal face machinery' in n:
            dims = sorted(max(v[i] for v in vs)-min(v[i] for v in vs) for i in range(3))
            assert dims[1] > .8 and dims[2] > 2., (n,'microdetail instead of machinery')


def test_sensor_has_cellular_recessed_phase_tiles_not_cyan_slabs():
    g = specimen('sensor_station')
    assert sum('phased cell socket' in n for n,_,_,_ in g.parts) == 24
    assert sum('phased cell emitter' in n for n,_,_,_ in g.parts) == 24
    assert not any('radiator tile' in n and r == 'cool' for n,r,_,_ in g.parts)


@pytest.mark.parametrize('kind', KINDS)
def test_broad_manifold_faces_are_segmented_functional_equipment(kind):
    m = module()
    d = m._Design()
    m._BUILDERS[kind](d)
    for i,(name,_,_,_) in enumerate(d.parts):
        if ' coolant manifold ' not in name:
            continue
        children = [d.parts[c] for c,h in d.attachments if h == i]
        assert sum('segmented manifold cheek' in n for n,_,_,_ in children) == 2
        assert any('manifold recessed race' in n for n,_,_,_ in children)
        assert any('manifold compressor stage' in n for n,_,_,_ in children)


@pytest.mark.parametrize('kind, feature, minimum', [
    ('command_station','quorum stepped compute cartridge',8),
    ('shipyard','keel sectional deck plate',6),
    ('mining_station','crusher feed roller housing',6),
    ('research_station','containment valve actuator',6),
    ('defense_platform','recoil servo cassette',4),
    ('trade_station','cargo gripper jaw',8),
    ('fighter_platform','launch rail service cassette',8),
    ('repair_dock','repair plasma tool jaw',8),
    ('energy_relay','relay coil transfer shoe',8),
])
def test_differentiated_supported_industrial_assemblies(kind, feature, minimum):
    assert sum(feature in n for n,_,_,_ in specimen(kind).parts) >= minimum
