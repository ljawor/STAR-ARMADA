"""Focused S06 B3b batch guards for the pending, unapproved small station kinds.

Nine specimens, one batch: the mining station, sensor station and energy relay across the
three families that have a `mesh_for` seam. Cheap per-asset guards only - geometry, budget,
envelope, export-only source safety, the seed's refusal to overwrite a master, the station
seam's legacy dispatch, the proof that every declared ring is a hollow ring, and the proof
that nothing pending leaked into a production registry, an approval record or a runtime
manifest. The deep actual-renderer matrix is a batch-milestone check in
`tools/diag_alliance_batch_review.py`, not a per-station test.

Three rules in here were paid for on this batch, so they are guards rather than comments:

* a station binding has no `ship_size` class - `render.camera_geometry.station_bounds` is the
  measure its render, contact and camera helpers read, so the authored mesh is compared
  against the *legacy station mesh* extent, axis by axis, and must reach it
  (`test_authored_mesh_fills_the_binding_legacy_station_extent`);
* the export wrapper refuses any mesh at or under 1,800 triangles, so a small station whose
  parts are too few cannot be exported at all - a design that fails that floor has not been
  authored yet, and the floor must not be relaxed to admit it
  (`test_every_station_clears_the_pipeline_triangle_floor`);
* a part named with an encirclement noun (rim, band, collar, port) must actually be an
  annulus. A block wearing that noun is either wrongly declared as a ring or has to be
  exempted by name, which is how `09 Drill collar` became `09 Drill clamp`
  (`test_every_declared_ring_is_an_annulus_and_no_port_is_a_capped_disc`).
"""
import ast
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'art/manifests/pending/S06-BATCH-B3B-STATIONS.json'
BATCH = 's06-b3b-stations-slice-1'
# The owner's appearance approval of this batch, recorded in art/manifests/approvals.json and
# bound to the exact revisions this module guards. It authorizes no landing.
APPEARANCE_DECISION = 's06-b3b-stations-2026-10-17'
BATCH_STATUS = 'appearance_approved_pending_landing'
SEED = 'tools/art/build_b3b_stations.py'


def seed_self_check():
    """Load the seed's pure extent self-check without importing Blender.

    The seed refuses an existing master at module level, so it cannot be exec'd whole; the
    helper and its tolerance are taken from its AST and compiled on their own.
    """
    tree = ast.parse((ROOT / SEED).read_text(encoding='utf-8'))
    keep = [node for node in tree.body
            if (isinstance(node, ast.FunctionDef) and node.name == 'breach_lines')
            or (isinstance(node, ast.Assign)
                and any(getattr(t, 'id', '') == 'BREACH_TOLERANCE' for t in node.targets))]
    namespace = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), '<seed-self-check>', 'exec'), namespace)
    return namespace['breach_lines'], namespace['BREACH_TOLERANCE']
# Every binding this module guards. `envelope` is the binding's legacy extent as
# `(low, high)` per axis; the spec carries the same numbers transposed, and
# `test_batch_spec_lists_exactly_the_guarded_bindings` compares the two so neither can
# drift alone. `rings` names every part the seed builds with a torus or an annulus: those
# must stay hollow in the export. `legacy_triangles` is the faction station mesh this
# specimen would replace through the seam.
ASSETS = (
    dict(binding='rebel:mining_station', identifier='alliance_mining_station',
         label='alliance mining station', data_id='mining_station', faction='rebel',
         envelope=((-44.8, 44.8), (-15.6, 10.12), (-26.0, 22.8294)), min_length=48.6,
         legacy_triangles=2416, max_triangles=11500, max_vertices=8000,
         rings=('01 processing band', '02 band rail', '04 deploy ring', '90 inner band')),
    dict(binding='confederacy:mining_station', identifier='legion_mining_station',
         label='legion mining station', data_id='mining_station', faction='confederacy',
         envelope=((-40.6686, 40.6686), (-31.44, 11.08), (-29.36, 46.96)), min_length=76.1,
         legacy_triangles=2032, max_triangles=11500, max_vertices=8000,
         rings=('01 keel hull', '90 inner band')),
    dict(binding='syndicate:mining_station', identifier='syndicate_mining_station',
         label='syndicate mining station', data_id='mining_station', faction='syndicate',
         envelope=((-33.9322, 42.4), (-32.4, 39.6), (-25.0848, 41.4431)), min_length=66.3,
         legacy_triangles=1696, max_triangles=11500, max_vertices=8000,
         rings=('09 drum band', '90 inner band')),
    dict(binding='rebel:sensor_station', identifier='alliance_sensor_station',
         label='alliance sensor station', data_id='sensor_station', faction='rebel',
         envelope=((-46.4, 46.4), (-12.8, 30.48), (-24.8, 16.24)), min_length=40.8,
         legacy_triangles=3344, max_triangles=11500, max_vertices=8000,
         rings=('02 disc rim', '03 feed band', '06 dish', '90 inner band')),
    dict(binding='confederacy:sensor_station', identifier='legion_sensor_station',
         label='legion sensor station', data_id='sensor_station', faction='confederacy',
         envelope=((-36.1913, 36.1913), (-14.0, 38.4), (-28.2851, 34.8)), min_length=62.9,
         legacy_triangles=1200, max_triangles=11500, max_vertices=8000,
         rings=('06 forward dish', '90 inner band')),
    dict(binding='syndicate:sensor_station', identifier='syndicate_sensor_station',
         label='syndicate sensor station', data_id='sensor_station', faction='syndicate',
         envelope=((-47.2, 26.3565), (-17.6, 43.857), (-31.137, 21.1423)), min_length=52.1,
         legacy_triangles=1248, max_triangles=11500, max_vertices=8000,
         rings=('04 bolted dish', '90 inner band')),
    dict(binding='rebel:energy_relay', identifier='alliance_energy_relay',
         label='alliance energy relay', data_id='energy_relay', faction='rebel',
         envelope=((-50.4, 50.4), (-8.4078, 13.2078), (-29.36, 20.9846)), min_length=50.1,
         legacy_triangles=2208, max_triangles=11500, max_vertices=8000,
         rings=('01 collector band', '02 band rim', '03 inner band', '90 inner band')),
    dict(binding='confederacy:energy_relay', identifier='legion_energy_relay',
         label='legion energy relay', data_id='energy_relay', faction='confederacy',
         envelope=((-41.4372, 41.4372), (-16.0, 31.6), (-25.7713, 46.4)), min_length=71.9,
         legacy_triangles=976, max_triangles=11500, max_vertices=8000,
         rings=('90 inner band',)),
    dict(binding='syndicate:energy_relay', identifier='syndicate_energy_relay',
         label='syndicate energy relay', data_id='energy_relay', faction='syndicate',
         envelope=((-47.5594, 46.5284), (-11.2, 23.36), (-46.5402, 34.4011)), min_length=80.7,
         legacy_triangles=2144, max_triangles=11500, max_vertices=8000,
         rings=('02 cell band', '90 inner band')),
)
# The gameplay radius each kind's helpers scale by. A station's footprint is authored in
# nominal radius-50 space, so these numbers and the mesh extents move together or not at all.
STATION_RADII = {'mining_station': 70, 'sensor_station': 45, 'energy_relay': 55}
# Deliberately not in this batch, and the spec must say so rather than fall silent.
OMITTED = ('imperial:mining_station', 'imperial:sensor_station', 'imperial:energy_relay',
           'rebel:shipyard')
BATCH_MATES = ('rebel:command_station', 'confederacy:command_station',
               'syndicate:command_station')
# The floor the export wrapper enforces. Read from the template below, never assumed.
TRIANGLE_FLOOR = 1800
# Every role the batch review ablates on its own, per station. A small station whose parts
# are too few to move one of these numbers contributes no ablation evidence for that role.
ABLATED_ROLES = ('accent', 'dark', 'cool')


def asset_mesh(asset):
    return ROOT / f"assets/models/{asset['identifier']}.mesh.json"


def payload_of(asset):
    return json.loads(asset_mesh(asset).read_text(encoding='utf-8'))


def load(asset, path=None):
    from render.authored_mesh import _load_profile
    return _load_profile(path or asset_mesh(asset), asset['identifier'], asset['envelope'],
                         asset['min_length'])


def legacy_bounds(asset):
    """The legacy station extent the authored mesh must keep, read from live render code.

    The application package is imported first: `render.faction_visuals` reaches back into
    `game.systems`, and going straight to the data store raises
    `ImportError: cannot import name 'UnitFactory' from partially initialized module`.
    """
    import game.core.manager  # noqa: F401  (import order, see docstring)
    from render import asset_selection
    from render.camera_geometry import station_bounds
    assert asset_selection.mesh_for(asset['binding']) is None, (
        f"{asset['binding']} must not be selectable in production")
    return station_bounds(asset['data_id'], asset['faction'])


def measured_bounds(payload):
    points = payload['vertices']
    return ([min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)])


def part_spans(payload, name_fragment):
    """Exported vertices per part whose name contains `name_fragment`, in export order."""
    offsets = {role: 0 for role in payload['batches']}
    for part in payload['parts']:
        role = part['role']
        start = offsets[role]
        end = start + part['triangles']
        offsets[role] = end
        if name_fragment not in part['name'].lower():
            continue
        rows = payload['batches'][role][start:end]
        assert rows, f'{part["name"]} is a named part with no geometry'
        yield part, [payload['vertices'][i] for row in rows for i in row[3:]]


def floating_parts(payload, tolerance=.25):
    """Groups of welded parts that stand clear of every other group, with their daylight.

    The exporter indexes vertices by quantised position, so parts that touch share vertices and
    fall into one group; a group that is nowhere near another one is a part - or a cluster of
    parts - floating in space. The S06 batch shipped a sensor-station dish 23.75 units clear of
    its body and a marker-light ring 1.4 units above the deck of every station, and both read as
    detached hardware in their own captures. This measures that without opening Blender, which
    is what lets it be a gate instead of a habit.
    """
    parent = {}

    def find(index):
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    for role in payload['batches'].values():
        for triangle in role:
            for a, b in ((triangle[3], triangle[4]), (triangle[4], triangle[5])):
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    groups = {}
    for index in list(parent):
        groups.setdefault(find(index), []).append(index)
    entries = []
    for members in groups.values():
        points = [payload['vertices'][i] for i in members]
        entries.append((len(members),
                        [min(p[i] for p in points) for i in range(3)],
                        [max(p[i] for p in points) for i in range(3)]))
    floating = []
    for index, (count, lo, hi) in enumerate(entries):
        nearest = min((max(max(lo[k] - other_hi[k], other_lo[k] - hi[k]) for k in range(3))
                       for other, (_, other_lo, other_hi) in enumerate(entries) if other != index),
                      default=0.0)
        if nearest > tolerance:
            floating.append((round(nearest, 2), count,
                             [round((lo[k] + hi[k]) / 2, 2) for k in range(3)]))
    return floating


class GeometryContract(unittest.TestCase):
    def test_each_pending_asset_satisfies_the_loader_contract(self):
        """The production loader, not this test, is the authority on the mesh."""
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                mesh = load(asset)
                self.assertTrue(mesh, 'the production loader must accept the export')
                payload = payload_of(asset)
                counted = sum(len(role) for role in payload['batches'].values())
                self.assertEqual(counted, payload['triangle_count'])
                self.assertLessEqual(counted, asset['max_triangles'])
                self.assertLessEqual(len(payload['vertices']), asset['max_vertices'])
                for role, batch in payload['batches'].items():
                    self.assertTrue(batch, f'{asset["binding"]}: role {role} is empty')

    def test_authored_mesh_fills_the_binding_legacy_station_extent(self):
        """Same footprint as the legacy station, not merely inside its box.

        `stations.json` still carries a gameplay radius per kind, and the camera and contact
        helpers scale the station by that number over the mesh extent, so a station that only
        fits inside the legacy box would quietly frame and collide differently.
        """
        stations = json.loads((ROOT / 'assets/data/stations/stations.json')
                              .read_text(encoding='utf-8'))['stations']
        for kind, radius in STATION_RADII.items():
            self.assertEqual(stations[kind]['radius'], radius, kind)
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                lo, hi = measured_bounds(payload_of(asset))
                for axis, (low, high) in enumerate(asset['envelope']):
                    self.assertGreaterEqual(lo[axis], low - 1e-6)
                    self.assertLessEqual(hi[axis], high + 1e-6)
                legacy_lo, legacy_hi = legacy_bounds(asset)
                for axis in range(3):
                    self.assertAlmostEqual(legacy_lo[axis], asset['envelope'][axis][0],
                                           places=3)
                    self.assertAlmostEqual(legacy_hi[axis], asset['envelope'][axis][1],
                                           places=3)
                    span = legacy_hi[axis] - legacy_lo[axis]
                    self.assertLessEqual(abs(hi[axis] - legacy_hi[axis]), span * .01,
                                         f'axis {axis} high drifted from the legacy extent')
                    self.assertLessEqual(abs(lo[axis] - legacy_lo[axis]), span * .01,
                                         f'axis {axis} low drifted from the legacy extent')
                self.assertGreaterEqual(hi[2] - lo[2], asset['min_length'])

    def test_every_station_clears_the_pipeline_triangle_floor(self):
        """A design under the export floor cannot be exported at all, so it is not authored.

        Eight of these nine came in between 676 and 1,760 triangles, which the wrapper refused
        with a bare `AssertionError: <count>`. The floor is what stops a hull shipping as a
        degenerate box, so the batch gained a real detail layer instead of a relaxed guard.
        """
        # The floor is generated into each wrapper from the template's default expansion - the
        # template itself carries a slot, so that a declared small prop can carry a floor of its own
        # without moving this one. What matters here is that the wrapper these rows are exported by
        # still refuses at 1,800.
        generator = (ROOT / 'tools/art/gen_export_wrappers.py').read_text(encoding='utf-8')
        self.assertIn("assert 1_800 < asset['triangle_count']", generator,
                      'the floor moved: re-check what this batch was authored against')
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                wrapper = (ROOT / f"tools/art/export_{asset['binding'].split(':')[1]}.py")
                if wrapper.exists():
                    self.assertIn("assert 1_800 < asset['triangle_count']",
                                  wrapper.read_text(encoding='utf-8'),
                                  'this row is exported by a wrapper with a moved floor')
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = payload_of(asset)
                self.assertGreater(payload['triangle_count'], TRIANGLE_FLOOR,
                                   f'{asset["binding"]} would be refused by the exporter')
                self.assertGreater(payload['triangle_count'], asset['legacy_triangles'] * .5,
                                   'a specimen far below the station it replaces reads thin')

    def test_every_station_fills_every_material_role(self):
        """Two contracts at once: the loader rejects an empty role, and the review ablates three.

        `render.authored_mesh._load_profile` requires `set(batches) == set(ROLES)` with every
        batch non-empty, so a design that never used `base` cannot load at all - nine meshes
        here failed with `ValueError: empty authored battleship role` before the detail layer
        carried one. Separately, a role the review ablates but no station part uses reports a
        zero-pixel ablation, which measures nothing.
        """
        from render.authored_mesh import ROLES
        self.assertTrue(set(ABLATED_ROLES) <= set(ROLES), 'the review ablates an unknown role')
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = payload_of(asset)
                self.assertEqual(set(payload['batches']), set(ROLES),
                                 f'{asset["binding"]} does not declare exactly the loader roles')
                for role in ROLES:
                    self.assertTrue(payload['batches'][role],
                                    f'{asset["binding"]}: empty {role} batch cannot load')
                load(asset)

    def test_each_kind_is_three_distinct_designs(self):
        """A kit of station primitives, not one body with different paint.

        The three families of a kind share a footprint by contract, so the comparison is
        between their geometry: role distribution, vocabulary and stance.
        """
        for kind in STATION_RADII:
            same_kind = [a for a in ASSETS if a['data_id'] == kind]
            self.assertEqual(len(same_kind), 3, kind)
            shapes = {}
            for asset in same_kind:
                payload = payload_of(asset)
                lo, hi = measured_bounds(payload)
                # The shared detail layer (`9x` parts) is deliberately identical on every
                # station in the catalogue, so the design comparison is over the parts the
                # author chose: the layer is a floor, not the design.
                design = {p['name'].lower() for p in payload['parts']
                          if not p['name'].startswith('9')}
                shapes[asset['binding']] = dict(
                    triangles=payload['triangle_count'],
                    aspect=(hi[1] - lo[1]) / (hi[0] - lo[0]),
                    vocabulary=design,
                    roles={r: len(b) for r, b in payload['batches'].items()})
            bindings = [a['binding'] for a in same_kind]
            for i, left in enumerate(bindings):
                for right in bindings[i + 1:]:
                    with self.subTest(pair=(left, right)):
                        a, b = shapes[left], shapes[right]
                        self.assertNotEqual(a['roles'], b['roles'],
                                            'the two role distributions are identical')
                        shared = a['vocabulary'] & b['vocabulary']
                        self.assertLess(len(shared) / len(a['vocabulary'] | b['vocabulary']), .6,
                                        f'{left} and {right} share too much vocabulary')
                        self.assertGreater(abs(a['aspect'] - b['aspect']), .05,
                                           'the two stations are the same shape')
                        self.assertNotEqual(a['triangles'], b['triangles'],
                                            'two families built the same amount of geometry')

    def test_every_declared_ring_is_an_annulus_and_no_port_is_a_capped_disc(self):
        """A ring that encircles a member must stay hollow, and a port must be declared.

        Measured off the export: every vertex of a ring part sits away from the part's own
        vertical axis, so a capped disc - which has vertices down to the centre - fails here
        rather than in a screenshot. The name check runs the other way too: a part wearing an
        encirclement noun without being declared is a ring nobody reviewed.
        """
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = payload_of(asset)
                declared = asset['rings']
                for part, points in part_spans(payload, ''):
                    name = part['name'].lower()
                    # `ring` is deliberately not a noun here: `05 Drill string` contains it.
                    if not any(word in name for word in ('collar', 'port', 'rim', 'band')):
                        continue
                    self.assertTrue(any(word in name for word in declared),
                                    f'{part["name"]} names a ring/port but is not declared')
                for fragment in declared:
                    spans = list(part_spans(payload, fragment))
                    self.assertTrue(spans, f'{asset["binding"]}: no part named {fragment!r}')
                    for part, points in spans:
                        # Normalised per axis: a habitat band is an ellipse (89.6 wide, 48.8
                        # deep on the Alliance station), so an unscaled radius test would call
                        # a real ring a disc.
                        cx = (max(p[0] for p in points) + min(p[0] for p in points)) / 2
                        cz = (max(p[2] for p in points) + min(p[2] for p in points)) / 2
                        hx = max(abs(p[0] - cx) for p in points) or 1e-9
                        hz = max(abs(p[2] - cz) for p in points) or 1e-9
                        hole = min(max(abs(p[0] - cx) / hx, abs(p[2] - cz) / hz)
                                   for p in points)
                        self.assertGreaterEqual(
                            hole, .25,
                            f'{part["name"]} has geometry at its own axis: a disc, not a ring')

    def test_every_part_name_is_unique_within_its_station(self):
        """A duplicated part name aliases two parts: the review's part lookups hit one of them.

        The bay detail layer is a loop over two rows, so a name template that forgets its index
        would collide silently rather than fail.
        """
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                names = [p['name'] for p in payload_of(asset)['parts']]
                duplicates = sorted({n for n in names if names.count(n) > 1})
                self.assertEqual(duplicates, [], f'{asset["binding"]}: {duplicates}')

    def test_no_station_claims_a_drive_or_a_weapon_part(self):
        """A station has no drive plume; an emitter part here would be an unowned claim."""
        banned = re.compile(r'emitter|nozzle|exhaust|gun|cannon|turret|missile|torpedo')
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = payload_of(asset)
                for part in payload['parts']:
                    self.assertIsNone(banned.search(part['name'].lower()), part['name'])
                self.assertNotIn('emitters', payload.get('features', {}))


class SourceSafety(unittest.TestCase):
    def load_exporter(self, asset, output, blend):
        spec = importlib.util.spec_from_file_location(
            'export_' + asset['identifier'], ROOT / f"tools/art/export_{asset['identifier']}.py")
        exporter = importlib.util.module_from_spec(spec)
        stub = SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(
            open_mainfile=Mock(side_effect=RuntimeError('master opened before refusal')))))
        with patch.dict(sys.modules, {'bpy': stub}):
            spec.loader.exec_module(exporter)
            with patch.object(sys, 'argv', ['exporter', '--', '--blend', str(blend),
                                           '--output', str(output)]):
                with self.assertRaisesRegex(ValueError, 'master|source|input'):
                    exporter.main()
        return stub.ops.wm.open_mainfile

    def test_export_refuses_every_master_alias_before_open(self):
        """An exporter that writes over its own source destroys the editable master."""
        for asset in ASSETS:
            for alias in ('same', 'relative', 'symlink', 'hardlink'):
                with self.subTest(binding=asset['binding'], alias=alias), \
                        tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    master = root / 'master.blend'
                    master.write_bytes(b'protected master')
                    output = master
                    if alias == 'relative':
                        (root / 'child').mkdir()
                        output = root / 'child/../master.blend'
                    elif alias == 'symlink':
                        output = root / 'alias.blend'
                        output.symlink_to(master)
                    elif alias == 'hardlink':
                        output = root / 'alias.blend'
                        os.link(master, output)
                    opened = self.load_exporter(asset, output, master)
                    opened.assert_not_called()
                    self.assertEqual(master.read_bytes(), b'protected master')
                    self.assertEqual(output.read_bytes(), b'protected master')

    def test_exporters_open_the_declared_master_and_never_save_it(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                exporter = ROOT / f"tools/art/export_{asset['identifier']}.py"
                text = exporter.read_text(encoding='utf-8')
                tree = ast.parse(text)
                self.assertIn('open_mainfile', text)
                self.assertFalse(any(isinstance(n, ast.Attribute)
                                     and n.attr in ('save_as_mainfile', 'save_mainfile')
                                     for n in ast.walk(tree)))
                self.assertTrue((ROOT / f"art/blender/{asset['identifier']}.blend").is_file())
                self.assertEqual(payload_of(asset)['features']['authority'], 'blend')

    def test_the_seed_extent_self_check_ignores_float_noise_and_still_catches_a_real_shortfall(self):
        """A self-check that cries wolf is one nobody reads.

        The seed reports a breach when an authored extreme misses its declared limit, and the
        tolerance was 1e-6 world units - below the float hair the bevel evaluation leaves outside
        a 92.8-unit span (1.5e-06 measured on the keel strake, 1.6e-08 relative), which the
        exporter's edge quantiser snaps to the edge. Five of those printed as breaches. The
        smallest *real* under-reach this batch fixed was 0.03 units. Both directions are asserted
        here, so a later tightening of the tolerance fails this test rather than the owner.
        """
        helper, tolerance = seed_self_check()
        noise = ([-46.4000015, -32.4000015, -25.0848], [46.4000015, 39.6, 41.4431])
        limits = [[-46.4, 46.4], [-32.4, 39.6], [-25.0848, 41.4431]]
        extremes = (('10 Keel strake', '10 Keel strake'), ('02 Beam pad left', '02 Beam pad left'),
                    ('03 Keel', '03 Keel'))
        self.assertGreaterEqual(tolerance, 1e-3)
        self.assertEqual([], helper('sensor', *noise, limits, extremes),
                         'float noise must not print as a breach')
        real = ([-46.4, -32.4, -25.0848 - 0.03], [46.4, 39.6, 41.4431])
        caught = helper('relay', *real, limits, extremes)
        self.assertEqual(1, len(caught), caught)
        self.assertIn('BREACH', caught[0])
        # and the tolerance is what removes the noise: at the old value the same row reports
        self.assertEqual(3, len(helper('sensor', *noise, limits, extremes, tolerance=1e-6)),
                         'the 1e-6 tolerance is the defect this guards against')

    def test_the_batch_seed_refuses_to_overwrite_an_existing_master(self):
        """One seed authors all nine masters, so one refusal guards the whole batch."""
        masters = [ROOT / f"art/blender/{a['identifier']}.blend" for a in ASSETS]
        for master in masters:
            self.assertTrue(master.is_file(), 'the editable master must be committed')
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn('--replace-seed', text)
        spec = importlib.util.spec_from_file_location('seed_b3b_stations', ROOT / SEED)
        module = importlib.util.module_from_spec(spec)
        # The refusal sits above the Blender import, so this runs with no Blender runtime.
        with self.assertRaisesRegex(RuntimeError, 'replace-seed|master'):
            with patch.object(sys, 'argv', ['seed']):
                spec.loader.exec_module(module)
        for master in masters:
            self.assertGreater(master.stat().st_size, 0, 'a refusal must not truncate a master')

    def test_the_generated_export_wrappers_match_their_template(self):
        """One template renders every wrapper; a hand edit would drift silently."""
        script = ROOT / 'tools/art/gen_export_wrappers.py'
        self.assertTrue((ROOT / 'tools/art/templates/export_wrapper.tmpl').is_file())
        check = subprocess.run([sys.executable, str(script), '--check'], cwd=ROOT,
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        for asset in ASSETS:
            self.assertTrue((ROOT / f"tools/art/export_{asset['identifier']}.py").is_file())


class StationSeam(unittest.TestCase):
    def test_the_seam_is_what_dispatches_every_guarded_binding(self):
        """The pending specimen becomes selectable through `mesh_for`, nothing else."""
        from render import asset_selection
        from render.faction_stations import station_mesh
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertIsNone(asset_selection.mesh_for(asset['binding']),
                                  'the batch is pending: the seam must not select it yet')
                legacy = station_mesh(asset['faction'], asset['data_id'])
                self.assertEqual(sum(len(t) for t in legacy.values()),
                                 asset['legacy_triangles'],
                                 'the legacy faction station is what a selection replaces')

    def test_the_imperial_station_rows_still_have_no_seam(self):
        """The blocker is a fact about the tree, not a sentence in a document."""
        from render import asset_selection
        from render.faction_stations import station_mesh
        for kind in STATION_RADII:
            self.assertIsNone(asset_selection.mesh_for(f'imperial:{kind}'),
                              'an imperial station has no mesh_for seam to author into')
            self.assertTrue(station_mesh('imperial', kind))


class PendingRecords(unittest.TestCase):
    def batch_spec(self):
        return json.loads(SPEC.read_text(encoding='utf-8'))

    def test_batch_spec_lists_exactly_the_guarded_bindings(self):
        spec = self.batch_spec()
        self.assertEqual(spec['batch'], BATCH)
        self.assertEqual([a['binding'] for a in spec['assets']],
                         [a['binding'] for a in ASSETS])
        self.assertEqual(spec['status'], BATCH_STATUS)
        self.assertEqual(spec['appearance_decision'], APPEARANCE_DECISION)
        self.assertIn('not an approval record', spec['note'])
        rows = {a['binding']: a for a in spec['assets']}
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                row = rows[asset['binding']]
                self.assertEqual(row['identifier'], asset['identifier'])
                self.assertEqual(row['data_id'], asset['data_id'])
                self.assertEqual(row['station_kind'], asset['data_id'])
                self.assertEqual(row['faction'], asset['faction'])
                self.assertEqual(row['seed'], SEED)
                self.assertEqual(row['seed_arg'], f"--asset {asset['binding']}")
                self.assertEqual(tuple(zip(*row['envelope'])), asset['envelope'])
                self.assertAlmostEqual(row['min_length'], asset['min_length'], places=1)

    def test_every_row_label_is_unique_so_captures_cannot_overwrite(self):
        """A duplicated label silently overwrites another row's evidence on disk.

        The harness names every capture `f"{label}-{variant}-{view}.png"`; two rows with the
        same label leave the evidence directory holding only the last row's frames.
        """
        labels = [a['label'] for a in self.batch_spec()['assets']]
        self.assertEqual(len(set(labels)), len(labels), labels)

    def test_every_row_names_its_own_capture_and_the_batch_names_a_clip(self):
        spec = self.batch_spec()
        evidence = spec['evidence']
        self.assertEqual(sorted(evidence), sorted(a['binding'] for a in spec['assets']))
        self.assertEqual(len({row['sheet'] for row in evidence.values()}), 1,
                         'one contact sheet per batch')
        self.assertTrue(any('motion' in row for row in evidence.values()))
        for asset in spec['assets']:
            with self.subTest(binding=asset['binding']):
                row = evidence[asset['binding']]
                self.assertIn('-after-close.png', row['close'])
                # the frame is this row's own: its label appears, no other row's does
                self.assertIn(asset['label'], row['close'])
                for other in spec['assets']:
                    if other['binding'] != asset['binding']:
                        self.assertNotIn(other['label'], row['close'])

    def test_the_batch_declares_a_near_camera_floor_and_the_harness_honours_it(self):
        """A small station framed like a big one puts the near eye inside the context group.

        These stations scale to 65-146 units of framing where the B3a command stations scaled
        to 250, and the shared scene carries a context group, so the closest row failed with
        `camera not outside union`. The floor is a spec field, so it cannot be a harness
        constant that would move every earlier batch's committed frames.
        """
        spec = self.batch_spec()
        floor = spec['overview']['close_distance_floor']
        self.assertGreater(floor, 100)
        harness = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn("spec['overview'].get('close_distance_floor')", harness)
        self.assertIn('close_floor=None', harness, 'the floor must default to off')
        frames = []
        for asset in spec['assets']:
            lo, hi = asset['envelope']
            longest = max(hi[axis] - lo[axis] for axis in range(3))
            drawn = longest * STATION_RADII[asset['data_id']] / 50.  # radius-50 nominal space
            frames.append(drawn * 1.37)
        # The floor must lift the closest row (the one that failed) and must not pull any row
        # in past the widest framing this batch already gives itself.
        self.assertLessEqual(min(frames), floor, 'the floor must lift the closest row')
        self.assertLessEqual(floor, max(frames), 'the floor must not shrink every specimen')

    def test_the_review_harness_owns_a_station_with_a_player_of_its_own_faction(self):
        """The renderer takes a *station's* faction from its owner, not from the data row.

        A station row owned by the rebel player draws the Alliance design for every binding,
        the seam is then queried as `rebel:<kind>` - which no candidate matches - and the row
        reports a 0.0-pixel change that reads as a no-op instead of a defect. A ship row is
        immune, its visual key coming from the ship data row.
        """
        harness = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn("FACTION_OWNER[asset.get('faction', 'rebel')]", harness)
        self.assertIn("st.entities[ids['capital']].owner = owner", harness)
        self.assertIn('def players_for(', harness)

    def test_the_omitted_rows_and_this_batch_mates_are_named_by_the_spec(self):
        """A silent omission reads as an oversight; the spec must say why it is absent."""
        spec = self.batch_spec()
        bindings = {a['binding'] for a in spec['assets']}
        for binding in OMITTED + BATCH_MATES:
            self.assertNotIn(binding, bindings)
        self.assertIn('imperial', spec['note'])
        self.assertIn('alliance_shipyard', spec['note'])
        self.assertIn('no mesh_for seam', spec['note'])
        self.assertIn('command stations are absent', spec['note'])

    def test_only_authorized_s06_specimens_register_with_legacy_default(self):
        """S07 execution authority registers exact approved revisions, not pending rows."""
        from s07_registration_assertions import assert_opt_in_registration, assert_preview_boundary
        bindings = [asset['binding'] for asset in ASSETS]
        assert_opt_in_registration(self, ROOT, bindings)
        assert_preview_boundary(self, ROOT, bindings)

    def test_every_evidence_path_the_sheet_points_at_exists(self):
        """A pointer to a file that is not there is worse than no pointer.

        The sheet is what the owner opens to judge the specimens, so every path in its
        `evidence` block is resolved here - a path that matches nothing must fail, not read
        as a pass, and only the row the harness was given as its motion clip may claim one.
        """
        spec = self.batch_spec()
        evidence = spec['evidence']
        self.assertEqual({row['binding'] for row in spec['assets']}, set(evidence),
                         'every row needs an evidence entry of its own')
        clips = [b for b, entry in evidence.items() if 'motion' in entry]
        self.assertEqual(1, len(clips), 'the harness is given one clip for the batch')
        for binding, entry in evidence.items():
            for kind, value in entry.items():
                for path in ([value] if isinstance(value, str) else value):
                    with self.subTest(binding=binding, kind=kind, path=path):
                        self.assertTrue((ROOT / path).is_file(), f'missing evidence file: {path}')

    def test_every_specimen_has_a_pending_sidecar_bound_to_its_own_master(self):
        """One sidecar per specimen, naming the master, the seed that selected it and the mesh.

        The sidecar is what a future landing decision would read, so it must point at this
        specimen's own files: a shared seed carries the `--asset` argument that selects it.
        """
        import hashlib
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                name = 'S06-' + asset['identifier'].upper() + '.json'
                path = ROOT / 'art/manifests/pending' / name.replace('_', '-')
                self.assertTrue(path.is_file(), f'no sidecar at {path.name}')
                record = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(record['binding'], asset['binding'])
                self.assertEqual(record['status'], BATCH_STATUS)
                self.assertEqual(record['batch'], BATCH)
                self.assertEqual(record['appearance_decision'], APPEARANCE_DECISION)
                self.assertFalse(record['activation'], 'appearance approval is not activation')
                self.assertIsNone(record['owner_decision'],
                                  'appearance approval is not a landing decision')
                self.assertEqual(record['initial_seed']['selects'], f"--asset {asset['binding']}")
                self.assertEqual(record['initial_seed']['path'], SEED)
                for key, relative in (('source', f"art/blender/{asset['identifier']}.blend"),
                                      ('runtime', f"assets/models/{asset['identifier']}"
                                                  ".mesh.json")):
                    digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                    self.assertEqual(record[key]['path'], relative)
                    self.assertEqual(record[key]['sha256'], digest,
                                     f'{key} hash drifted from the file on disk')
                self.assertEqual(tuple(zip(*record['envelope'])), asset['envelope'])

    def test_the_batch_sheet_is_labelled_unreviewed(self):
        text = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn('UNAPPROVED REVIEW ONLY', text)
        self.assertIn('pending_owner_approval', text)

    def test_no_part_of_any_station_floats_clear_of_the_rest(self):
        """A station is one piece of hardware, not a constellation.

        Contact is not implied by authoring by centre and by reach. This batch first shipped a
        legion sensor dish 23.75 units off its body and a marker-light ring 1.4 units above the
        deck on all nine designs; the seed's weld pass closes both, and this measures the
        exported meshes, so a design that floats is caught here rather than by eye.
        """
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                floating = floating_parts(payload_of(asset))
                self.assertEqual(
                    floating, [],
                    f"{asset['identifier']} carries parts floating clear of their neighbours: "
                    f"{floating}")

    def test_the_seed_welds_the_scene_before_it_reports_the_extent(self):
        """The order is the guarantee: a joint made after the self-check is an unmeasured one."""
        seed = (ROOT / 'tools/art/build_b3b_stations.py').read_text(encoding='utf-8')
        self.assertIn('weld_scene()', seed)
        self.assertLess(seed.index('weld_scene()'),
                        seed.index('report_bounds(limits, identifier)'))


if __name__ == '__main__':
    unittest.main()
