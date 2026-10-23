"""Pure CPU authoring contract; intentionally never imports Blender or the game."""
from collections import Counter
import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'tools' / 'art'
KINDS = ('fighter', 'bomber', 'corvette', 'frigate', 'cruiser', 'battleship',
         'supercapital', 'constructor', 'colonizer', 'convoy')
ROLES = {'base', 'dark', 'trim', 'accent', 'lit', 'cool'}


def module(name):
    spec = importlib.util.spec_from_file_location(name, ART / (name + '.py'))
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Recording:
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces, bevel=0):
        self.parts.append((name, role, tuple(map(tuple, verts)), tuple(map(tuple, faces))))

    @property
    def vertices(self):
        return [v for _, _, vs, _ in self.parts for v in vs]

    @property
    def triangles(self):
        return sum(len(f) - 2 for _, _, _, fs in self.parts for f in fs)


def frame(center=(0., 0., 0.), span=(2., 2., 2.)):
    return {'center': center, 'span': span,
            'lo': tuple(c - s / 2 for c, s in zip(center, span)),
            'hi': tuple(c + s / 2 for c, s in zip(center, span))}


def record(kind, f=None):
    path = ART / 'legions_redesign_fleet_designs.py'
    assert path.exists(), 'fleet geometry authoring module must exist'
    g = Recording()
    module('legions_redesign_fleet_designs').build(kind, g, f or frame())
    return g


def assert_geometry(kind, g, f):
    limits = module('legions_redesign_catalogue').TRIANGLE_LIMITS
    assert 1800 < g.triangles <= limits[kind], (kind, g.triangles)
    assert len(g.vertices) < 9500
    assert {p[1] for p in g.parts} == ROLES
    for role in ROLES:
        assert sum(len(fs) for _, r, _, fs in g.parts if r == role) >= 6
    for axis in range(3):
        lo = min(v[axis] for v in g.vertices)
        hi = max(v[axis] for v in g.vertices)
        assert f['lo'][axis] <= lo < hi <= f['hi'][axis]
        assert abs(lo - f['lo'][axis]) < f['span'][axis] * .01
        assert abs(hi - f['hi'][axis]) < f['span'][axis] * .01
    assert len({p[0] for p in g.parts}) == len(g.parts), 'unambiguous part names'
    for name, role, vs, fs in g.parts:
        assert vs and fs and all(math.isfinite(x) for v in vs for x in v)
        assert len(vs) == len(set(vs)), name
        edges = Counter()
        for face in fs:
            assert len(set(face)) == len(face) >= 3, name
            assert all(0 <= i < len(vs) for i in face), name
            for a, b in zip(face, face[1:] + face[:1]):
                edges[tuple(sorted((a, b)))] += 1
            # Every triangulation triangle must have actual area.
            a = vs[face[0]]
            for i in range(1, len(face) - 1):
                u = [vs[face[i]][j] - a[j] for j in range(3)]
                v = [vs[face[i + 1]][j] - a[j] for j in range(3)]
                cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                assert sum(t*t for t in cross) > 1e-20, (name, face)
        assert set(edges.values()) == {2}, (name, edges)


def test_fighter_closed_six_role_geometry_inside_native_bounds():
    f = frame((4., -3., 8.), (7., 1.7, 12.))
    assert_geometry('fighter', record('fighter', f), f)


def test_exact_catalogue_ship_scope():
    designs = module('legions_redesign_fleet_designs')
    assert tuple(designs.KINDS) == KINDS
    assert set(designs.KINDS) == module('legions_redesign_catalogue').SHIP_KINDS


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('native', [frame(), frame((2.3,-7.1,11.4),(8.1,1.3,14.8))])
def test_all_fleet_meshes_closed_budgeted_and_six_roles(kind, native):
    assert_geometry(kind, record(kind, native), native)


def bounds(part):
    vs = part[2]
    return tuple(min(v[i] for v in vs) for i in range(3)), tuple(max(v[i] for v in vs) for i in range(3))


def overlaps(a, b):
    return all(a[0][i] <= b[1][i]+1e-9 and b[0][i] <= a[1][i]+1e-9 for i in range(3))


@pytest.mark.parametrize('kind', KINDS)
def test_every_component_has_a_supported_path_to_the_hull(kind):
    # Conservative CPU attachment guard, not a substitute for a Boolean union.
    g = record(kind)
    boxes = [bounds(p) for p in g.parts]
    reached = {0}
    pending = set(range(1, len(boxes)))
    while True:
        attached = {j for j in pending if any(overlaps(boxes[i], boxes[j]) for i in reached)}
        if not attached:
            break
        reached |= attached
        pending -= attached
    assert not pending, [g.parts[j][0] for j in sorted(pending)]


def z_hits(part, x, y):
    """Ray intersections with the actual faces, not their bounding boxes."""
    verts, faces = part[2:]
    hits = []
    for f in faces:
        for j in range(1, len(f)-1):
            a,b,c = (verts[k] for k in (f[0],f[j],f[j+1]))
            ux,uy = b[0]-a[0],b[1]-a[1]
            vx,vy = c[0]-a[0],c[1]-a[1]
            det = ux*vy-uy*vx
            if abs(det) < 1e-12:
                continue
            px,py = x-a[0],y-a[1]
            s,t = (px*vy-py*vx)/det,(ux*py-uy*px)/det
            if s >= -1e-8 and t >= -1e-8 and s+t <= 1+1e-8:
                hits.append(a[2]+s*(b[2]-a[2])+t*(c[2]-a[2]))
    return hits


@pytest.mark.parametrize('kind', KINDS)
def test_drives_have_true_bores_and_exposed_aft_emitters(kind):
    g = record(kind)
    emitters = [p for p in g.parts if p[0].endswith(' visible emitter')]
    assert len(emitters) >= 2
    for emitter in emitters:
        tag = emitter[0].removesuffix(' visible emitter')
        ring = next(p for p in g.parts if p[0] == tag+' open annular aperture')
        cap = next(p for p in g.parts if p[0] == tag+' opaque machinery')
        lo,hi = bounds(emitter)
        x,y = (lo[0]+hi[0])/2,(lo[1]+hi[1])/2
        assert not z_hits(ring,x,y), 'the annular opening must be physically empty'
        assert hi[2] < bounds(cap)[0][2], 'glow must be aft of the opaque end cap'
        assert bounds(ring)[0][2] < lo[2] < hi[2] < bounds(ring)[1][2]
        for dx,dy in ((0,0),(.38,0),(-.38,0),(0,.38),(0,-.38)):
            xx,yy = x+dx*(hi[0]-lo[0])/2,y+dy*(hi[1]-lo[1])/2
            for part in g.parts:
                if part[1] in {'base','dark','trim','accent'}:
                    assert all(z > hi[2] for z in z_hits(part,xx,yy)), (kind,tag,part[0])


def test_supercapital_launch_channels_have_no_fake_floor():
    g = record('supercapital')
    # No mesh even has a bounding volume across either entire-through channel.
    for x in (-.33,.33):
        for z in (-.20,.10,.40,.65):
            for p in g.parts:
                lo,hi = bounds(p)
                assert not (lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2]), p[0]
    lances = [p for p in g.parts if p[0].startswith('forward lance jaw')]
    assert len(lances) == 2
    assert all(bounds(p)[1][2] > .98 for p in lances)


@pytest.mark.parametrize('kind,min_panels', [('cruiser',8),('battleship',10),('supercapital',12)])
def test_capital_detail_is_broad_raised_recessed_geometry(kind,min_panels):
    panels = [p for p in record(kind).parts if p[0].endswith(' raised carapace')]
    assert len(panels) >= min_panels
    for p in panels:
        lo,hi = bounds(p)
        assert hi[0]-lo[0] >= .22 and hi[2]-lo[2] >= .23
        assert hi[1]-lo[1] >= .14
        # Cavity floor ring is lower than, and strictly inside, the lip ring.
        lip,floor = p[2][24:32],p[2][32:40]
        assert max(v[1] for v in floor) < min(v[1] for v in lip)


def test_unknown_kind_rejected_without_emitting_geometry():
    g = Recording()
    with pytest.raises(ValueError):
        module('legions_redesign_fleet_designs').build('not-a-ship',g,frame())
    assert not g.parts


@pytest.mark.parametrize('kind', ['battleship','supercapital'])
def test_batteries_penetrate_their_actual_host_not_just_its_bbox(kind):
    g = record(kind)
    for mount in (p for p in g.parts if p[0].endswith(' rooted gun plinth')):
        lo,hi = bounds(mount)
        x,y,z = (lo[0]+hi[0])/2,lo[1]+.001,(lo[2]+hi[2])/2
        supported = False
        for p in g.parts:
            if p is mount or p[1] not in {'base','dark','trim'}:
                continue
            # Rotate coordinates to query a Y-directed ray with the same face solver.
            rotated = (p[0],p[1],tuple((v[0],v[2],v[1]) for v in p[2]),p[3])
            hits = sorted({round(h,8) for h in z_hits(rotated,x,z) if h > y})
            supported |= len(hits) % 2 == 1
        assert supported, mount[0]


@pytest.mark.parametrize('kind', ['bomber','frigate','cruiser','battleship','supercapital','colonizer','convoy'])
def test_side_machinery_is_exposed_not_buried_in_opaque_hull(kind):
    g = record(kind)
    visible = [p for p in g.parts if any(s in p[0] for s in
               ('deep radiator ', 'pod vertical radiator ', 'transport side broad registry '))]
    assert visible
    for fin in visible:
        lo,hi = bounds(fin)
        side = 1 if lo[0]+hi[0] > 0 else -1
        point = (hi[0] if side>0 else lo[0], (lo[1]+hi[1])/2, (lo[2]+hi[2])/2)
        for host in g.parts:
            if host is fin or host[1] not in {'base','dark','trim','accent'}:
                continue
            # Shoot along X from the outward face: odd crossings mean buried detail.
            rotated = (host[0],host[1],tuple((v[1],v[2],v[0]) for v in host[2]),host[3])
            hits = sorted({round(h,8) for h in z_hits(rotated,point[1],point[2]) if h > point[0]+1e-7})
            assert len(hits)%2 == 0, (fin[0],host[0])
