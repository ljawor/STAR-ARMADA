"""Blender-free placement gate: fittings must not hide scaffold-sized daylight.

Ignore generated weld members and measure connectivity of the authored part boxes.
This is an AABB placement guard, not a surface-intersection proof; the batch's
floating_parts guard and real Blender refusal/export checks complement it.
"""
import ast
import copy


def carrier_recipe_glazing():
    """Execute the live recipe coordinates, without importing bpy or building a scene."""
    recipe = ast.parse((ROOT / 'tools/art/build_alliance_carrier.py').read_text())
    helpers = ast.parse((ROOT / 'tools/art/hull_detail.py').read_text())
    captured = {}

    def mesh_object(name, role, verts, faces, bevel=0):
        captured[name] = [tuple(p) for p in verts]

    namespace = {'mesh_object': mesh_object}
    definitions = [n for n in helpers.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('surface', 'panel')]
    definitions += [n for n in recipe.body if isinstance(n, ast.FunctionDef)]
    definitions += [n for n in recipe.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'ISLAND' for t in n.targets)]
    definitions += [n for n in recipe.body if isinstance(n, ast.For)
                    and any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                            and c.value.startswith(('42 Island', '43 Island')) for c in ast.walk(n))]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<carrier recipe>', 'exec'), namespace)
    return captured


def payload_glazing(payload):
    offsets, result = {}, {}
    for part in payload['parts']:
        role = part['role']
        start = offsets.get(role, 0)
        offsets[role] = start + part['triangles']
        if part['name'].startswith(('42 Island', '43 Island')):
            indices = {i for t in payload['batches'][role][start:offsets[role]] for i in t[3:]}
            result[part['name']] = [payload['vertices'][i] for i in indices]
    return result


def assert_external_glazing(test, parts):
    # Independent loft math: interpolate the actual endpoint chamfers, NOT the
    # min of interpolated dimensions (which differs where its limiting axis changes).
    frames = ((-42, 16, 38, 26), (-20, 20, 46, 26),
              (4, 18, 50, 26), (28, 13, 42, 26))

    def flank(z):
        a, b = next((a, b) for a, b in zip(frames, frames[1:])
                    if a[0] - 1e-5 <= z <= b[0] + 1e-5)
        t = (z - a[0]) / (b[0] - a[0])
        c0, c1 = (min(f[1] * .25, (f[2] - f[3]) * .28) for f in (a, b))
        return tuple(a[k] + (b[k] - a[k]) * t for k in (1, 2, 3)) + (c0 + (c1 - c0) * t,)

    test.assertEqual(set(parts), {*(f'42 Island window band {i}' for i in range(4)),
                                  '43 Island glazing -1', '43 Island glazing 1'})
    for name, points in parts.items():
        side = -1 if name == '43 Island glazing -1' else 1
        zs = sorted({p[2] for p in points})
        test.assertGreaterEqual(len(zs), 2)
        test.assertGreater(zs[0], frames[0][0])
        test.assertLess(zs[-1], frames[-1][0])
        # A segment must end at every crossed frame: no chord cutting through taper.
        for frame in frames:
            if zs[0] < frame[0] < zs[-1]:
                test.assertIn(frame[0], zs, name)
        rings = []
        for z in zs:
            ring = [p for p in points if p[2] == z]
            rings.append((min(side*p[0] for p in ring), max(side*p[0] for p in ring),
                          min(p[1] for p in ring), max(p[1] for p in ring)))
        # Linear faces between section rings: these samples cover the entire run,
        # including both ends, not merely an AABB overlap or midpoint contact.
        for j in range(len(zs)-1):
            for t in (0., .1, .5, .9, 1.):
                z = zs[j] + (zs[j+1]-zs[j])*t
                inner, outer, low, high = (a+(b-a)*t for a,b in zip(rings[j], rings[j+1]))
                w, top, bottom, c = flank(z)
                test.assertGreater(outer-w, .15, (name, z, 'buried exterior', outer-w))
                test.assertLess(outer-w, .5, (name, z, 'excessive projection'))
                test.assertLess(inner-w, -.1, (name, z, 'no host penetration'))
                test.assertGreater(inner-w, -.4, (name, z, 'excessive burial'))
                test.assertLessEqual(high, top-c-.35+1e-5, (name, z, 'above flank'))
                test.assertGreaterEqual(low, bottom+c+.35-1e-5, (name, z, 'below flank'))
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ('syndicate_sensor_station', 'syndicate_mining_station',
          'syndicate_energy_relay', 'legion_mining_station', 'alliance_carrier')


def scaffold_gaps(payload, limit=10.0):
    offsets = {role: 0 for role in payload['batches']}
    boxes = []
    for part in payload['parts']:
        role = part['role']
        start = offsets[role]
        offsets[role] += part['triangles']
        if part['name'].startswith('95 Weld '):
            continue
        indices = {i for tri in payload['batches'][role][start:offsets[role]] for i in tri[3:]}
        if not indices:
            continue
        points = [payload['vertices'][i] for i in indices]
        boxes.append((part['name'], [min(p[k] for p in points) for k in range(3)],
                      [max(p[k] for p in points) for k in range(3)]))
    if not boxes:
        raise ValueError('no authored geometry')
    # Prim's minimum spanning tree: every component must reach the rest using
    # fitting-sized gaps, independently of the seed's generated bridging members.
    reached = {0}
    gaps = []
    while len(reached) < len(boxes):
        gap, a, b = min((max(max(boxes[a][1][k] - boxes[b][2][k],
                                 boxes[b][1][k] - boxes[a][2][k], 0.) for k in range(3)), a, b)
                        for a in reached for b in range(len(boxes)) if b not in reached)
        if gap > limit:
            gaps.append((boxes[a][0], boxes[b][0], round(gap, 6)))
        reached.add(b)
    return gaps


class PlacementRepairs(unittest.TestCase):
    def test_carrier_live_recipe_glazing_straddles_external_flank_for_whole_run(self):
        assert_external_glazing(self, carrier_recipe_glazing())

    def test_carrier_export_glazing_straddles_external_flank_for_whole_run(self):
        payload = json.loads((ROOT / 'assets/models/alliance_carrier.mesh.json').read_text())
        assert_external_glazing(self, payload_glazing(payload))

    def test_carrier_each_outer_glazing_face_is_clear_of_exported_opaque_geometry(self):
        payload = json.loads((ROOT / 'assets/models/alliance_carrier.mesh.json').read_text())
        points = payload_glazing(payload)
        offsets, glazing, opaque = {}, {}, []
        for part in payload['parts']:
            role = part['role']
            start = offsets.get(role, 0)
            offsets[role] = start + part['triangles']
            triangles = [[payload['vertices'][i] for i in tri[3:]]
                         for tri in payload['batches'][role][start:offsets[role]]]
            if part['name'] in points:
                glazing[part['name']] = triangles
            elif role not in ('lit', 'cool'):
                opaque.extend(triangles)

        def hits(triangles, y, z, side):
            # Horizontal beam-axis ray, barycentric intersection in YZ. These
            # are actual evaluated triangles, including the host's bevel, not boxes.
            result = []
            for a, b, c in triangles:
                by, bz, cy, cz = b[1]-a[1], b[2]-a[2], c[1]-a[1], c[2]-a[2]
                det = by*cz-bz*cy
                if abs(det) < 1e-9:
                    continue
                u = ((y-a[1])*cz-(z-a[2])*cy)/det
                v = (by*(z-a[2])-bz*(y-a[1]))/det
                if u >= -1e-6 and v >= -1e-6 and u+v <= 1+1e-6:
                    result.append(side*(a[0]+u*(b[0]-a[0])+v*(c[0]-a[0])))
            return result

        for name, vertices in points.items():
            side = -1 if name == '43 Island glazing -1' else 1
            zs = sorted({p[2] for p in vertices})
            for z0, z1 in zip(zs, zs[1:]):
                for t in (.05, .5, .95):
                    z = z0+(z1-z0)*t
                    ends = [[p for p in vertices if p[2] == end] for end in (z0, z1)]
                    low, high = (f(p[1] for p in ends[0])*(1-t)+f(p[1] for p in ends[1])*t
                                 for f in (min, max))
                    for fy in (.1, .5, .9):
                        y = low+(high-low)*fy
                        glass_hits = hits(glazing[name], y, z, side)
                        host_hits = hits(opaque, y, z, side)
                        with self.subTest(part=name, y=y, z=z):
                            self.assertGreaterEqual(len(glass_hits), 2, 'closed glazing solid')
                            self.assertTrue(host_hits, 'must reach opaque host')
                            self.assertGreater(max(glass_hits)-max(host_hits), .15, 'outer face buried')
                            self.assertLess(min(glass_hits)-max(host_hits), -.1, 'inner face floats')

    def test_surface_guard_rejects_each_buried_or_midpoint_only_panel(self):
        good = carrier_recipe_glazing()
        assert_external_glazing(self, good)
        for name in good:
            side = -1 if name.endswith('glazing -1') else 1
            for defect in ('buried', 'midpoint_only'):
                bad = copy.deepcopy(good)
                if defect == 'buried':
                    bad[name] = [(x-side*1., y, z) for x,y,z in bad[name]]
                else:
                    # Keep middle contact but flatten the taper across the run.
                    middle = (min(p[0] for p in bad[name])+max(p[0] for p in bad[name]))/2
                    bad[name] = [(middle + side*(.275 if side*x > side*middle else -.275), y, z)
                                 for x,y,z in bad[name]]
                with self.subTest(part=name, defect=defect):
                    with self.assertRaises(AssertionError):
                        assert_external_glazing(self, bad)

    def test_all_six_exported_bounds_stay_exactly_at_the_baseline(self):
        # Read from a5f3312, not from the looser declared envelopes.
        expected = (
            [[-47.2, -17.6, -31.137], [26.3565, 43.556999, 21.1423]],
            [[-33.9322, -32.4, -25.0848], [42.4, 39.6, 41.4431]],
            [[-47.5594, -11.2, -46.5402], [46.5284, 23.36, 34.4011]],
            [[-40.418598, -31.44, -29.36], [40.418598, 11.08, 46.96]],
            [[-146.51, -30.5, -204.8], [146.51, 56.95528, 190.0]],
        )
        for identifier, bounds in zip(ASSETS, expected):
            with self.subTest(asset=identifier):
                payload = json.loads((ROOT / f'assets/models/{identifier}.mesh.json').read_text())
                self.assertEqual(payload['bounds'], bounds)
                self.assertEqual([[min(p[k] for p in payload['vertices']) for k in range(3)],
                                  [max(p[k] for p in payload['vertices']) for k in range(3)]], bounds)

    def test_five_assets_need_no_scaffold_to_reach_their_host(self):
        for identifier in ASSETS:
            with self.subTest(asset=identifier):
                payload = json.loads((ROOT / f'assets/models/{identifier}.mesh.json').read_text())
                self.assertEqual(scaffold_gaps(payload), [])

    def test_guard_rejects_displacement_even_with_a_weld_between_parts(self):
        payload = {'vertices': [[0, 0, 0], [1, 1, 1], [2, 0, 0], [3, 1, 1],
                                [1, 0, 0], [40, 1, 1]],
                   'batches': {'base': [[0, 1, 0, 0, 1, 0], [0, 1, 0, 2, 3, 2],
                                         [0, 1, 0, 4, 5, 4]]},
                   'parts': [{'name': 'host', 'role': 'base', 'triangles': 1},
                             {'name': 'detail', 'role': 'base', 'triangles': 1},
                             {'name': '95 Weld 1', 'role': 'base', 'triangles': 1}]}
        self.assertEqual(scaffold_gaps(payload), [])
        bad = copy.deepcopy(payload)
        for i in (2, 3):
            bad['vertices'][i][0] += 30
        self.assertEqual(scaffold_gaps(bad), [('host', 'detail', 31)])
        with self.assertRaises(ValueError):
            scaffold_gaps({'vertices': [], 'parts': [], 'batches': {}})


if __name__ == '__main__':
    unittest.main()
