"""Focused S06 B3c batch guards for the pending, unapproved faction station rows.

Seventeen specimens, one batch: research station / defense platform / trade station /
fighter platform / repair dock across the three families that have a `mesh_for` seam, plus the
Legion and Syndicate shipyards. These are the remaining faction station rows after B3a (the
three command stations, owner-approved) and B3b (mining / sensor / relay, pending).

Cheap per-asset guards only - geometry, budget, envelope, export-only source safety, the
seed's refusal to overwrite a master, the station seam's legacy dispatch, the proof that every
declared ring is a hollow ring, the proof that nothing pending leaked into a production
registry, and the proof that the whole faction station table is accounted for. The deep
actual-renderer matrix is a batch-milestone check in `tools/diag_alliance_batch_review.py`,
not a per-station test.

Four rules in here were paid for on this batch, so they are guards rather than comments:

* a station binding has no `ship_size` class - `render.camera_geometry.station_bounds` is the
  measure its render, contact and camera helpers read, so the authored mesh is compared against
  the *legacy station mesh* extent, axis by axis and side by side, and must reach it
  (`test_each_mesh_reaches_its_binding_legacy_station_extent`);
* `weld_scene` refuses a joint with more than ten units of clear space, and its brace/grow pass
  is order-sensitive, so a hardware row stepped wider than its own blocks fails the build even
  when the row sits next to the body - the batch's rows step by less than one block width
  (`test_no_part_of_any_station_floats_clear_of_the_rest`);
* the export wrapper refuses any mesh at or under 1,800 triangles, and a station whose design is
  far thinner than the station it replaces reads thin, so the floor and the half-of-legacy bar
  are both asserted (`test_every_station_clears_the_pipeline_triangle_floor`);
* a part named with an encirclement noun (rim, band, collar, port) must actually be an annulus:
  a block wearing that noun is either wrongly declared or has to be renamed
  (`test_every_declared_ring_is_an_annulus_and_no_port_is_a_capped_disc`).
"""
import ast
import hashlib
import importlib.util
import json
import math
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
SPEC = ROOT / 'art/manifests/pending/S06-BATCH-B3C-STATIONS.json'
BATCH = 's06-b3c-stations'
SEED = 'tools/art/build_b3c_stations.py'
# The owner's appearance approval of this batch, recorded in art/manifests/approvals.json and bound
# to the exact revisions below. It authorizes no landing: S07 registration needs separate execution authority.
APPEARANCE_DECISION = 's06-b3c-stations-2026-10-17'
BATCH_STATUS = 'appearance_approved_pending_landing'
EARLIER_BATCHES = ('art/manifests/pending/S06-BATCH-B3A-COMMAND-STATIONS.json',
                   'art/manifests/pending/S06-BATCH-B3B-STATIONS.json')


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


# Every binding this module guards. `envelope` is the binding's legacy extent as `(low, high)`
# per axis; the spec carries the same numbers transposed, and
# `test_batch_spec_lists_exactly_the_guarded_bindings` compares the two so neither can drift
# alone. `rings` names every part the seed builds with a torus or an annulus - those must stay
# hollow in the export. `faction` is the owner faction the review harness has to re-own the
# specimen to, because a station's faction comes from its owner.
ASSETS = (
    dict(binding='rebel:research_station', identifier='alliance_research_station',
         label='alliance research station', data_id='research_station', faction='rebel',
         envelope=((-40.0, 40.0), (-9.6, 39.28), (-25.6, 35.901)), min_length=61.3,
         rings=('04 habitat band', '05 band rail', '90 inner band')),
    dict(binding='confederacy:research_station', identifier='legion_research_station',
         label='legion research station', data_id='research_station', faction='confederacy',
         envelope=((-46.3156, 46.3156), (-12.4, 13.88), (-33.48, 52.68)), min_length=86.0,
         rings=('90 inner band',)),
    dict(binding='syndicate:research_station', identifier='syndicate_research_station',
         label='syndicate research station', data_id='research_station', faction='syndicate',
         envelope=((-40.0, 36.4), (-7.2, 37.68), (-27.572, 32.8)), min_length=60.2,
         rings=('90 inner band',)),
    dict(binding='rebel:defense_platform', identifier='alliance_defense_platform',
         label='alliance defense platform', data_id='defense_platform', faction='rebel',
         envelope=((-45.92, 45.92), (-4.8, 11.166), (-44.32, 44.32)), min_length=88.4,
         rings=('90 inner band',)),
    dict(binding='confederacy:defense_platform', identifier='legion_defense_platform',
         label='legion defense platform', data_id='defense_platform', faction='confederacy',
         envelope=((-50.2043, 50.2043), (-8.4, 16.544), (-31.2764, 55.68)), min_length=86.8,
         rings=('90 inner band',)),
    dict(binding='syndicate:defense_platform', identifier='syndicate_defense_platform',
         label='syndicate defense platform', data_id='defense_platform', faction='syndicate',
         envelope=((-45.9679, 30.3691), (-10.8, 22.1), (-28.5448, 28.0475)), min_length=56.4,
         rings=('90 inner band',)),
    dict(binding='rebel:trade_station', identifier='alliance_trade_station',
         label='alliance trade station', data_id='trade_station', faction='rebel',
         envelope=((-44.0, 44.0), (-5.948, 6.12), (-38.736, 39.36)), min_length=77.9,
         rings=('05 deck rail', '90 inner band')),
    dict(binding='confederacy:trade_station', identifier='legion_trade_station',
         label='legion trade station', data_id='trade_station', faction='confederacy',
         envelope=((-43.7668, 43.7668), (-6.552, 18.28), (-46.0532, 46.0532)), min_length=91.9,
         rings=('90 inner band',)),
    dict(binding='syndicate:trade_station', identifier='syndicate_trade_station',
         label='syndicate trade station', data_id='trade_station', faction='syndicate',
         envelope=((-52.3122, 45.2571), (-8.8, 24.5), (-48.6483, 46.5606)), min_length=95.0,
         rings=('90 inner band',)),
    dict(binding='rebel:fighter_platform', identifier='alliance_fighter_platform',
         label='alliance fighter platform', data_id='fighter_platform', faction='rebel',
         envelope=((-48.0, 48.0), (-9.2, 6.92), (-39.2, 39.2)), min_length=78.2,
         rings=('04 deck edge', '90 inner band')),
    dict(binding='confederacy:fighter_platform', identifier='legion_fighter_platform',
         label='legion fighter platform', data_id='fighter_platform', faction='confederacy',
         envelope=((-42.4021, 42.4021), (-8.8, 11.88), (-36.4, 36.0)), min_length=72.2,
         rings=('90 inner band',)),
    dict(binding='syndicate:fighter_platform', identifier='syndicate_fighter_platform',
         label='syndicate fighter platform', data_id='fighter_platform', faction='syndicate',
         envelope=((-39.6, 32.1135), (-15.2, 30.8), (-39.2, 39.2)), min_length=78.2,
         rings=('90 inner band',)),
    dict(binding='rebel:repair_dock', identifier='alliance_repair_dock',
         label='alliance repair dock', data_id='repair_dock', faction='rebel',
         envelope=((-38.4, 38.4), (-12.8, 23.6), (-33.6, 39.6)), min_length=73.0,
         rings=('04 cradle band', '05 cradle rim', '90 inner band')),
    dict(binding='confederacy:repair_dock', identifier='legion_repair_dock',
         label='legion repair dock', data_id='repair_dock', faction='confederacy',
         envelope=((-40.1472, 40.1472), (-14.8, 26.4), (-36.4, 36.4)), min_length=72.6,
         rings=('90 inner band',)),
    dict(binding='syndicate:repair_dock', identifier='syndicate_repair_dock',
         label='syndicate repair dock', data_id='repair_dock', faction='syndicate',
         envelope=((-37.4318, 39.7528), (-16.8, 34.8), (-38.931, 37.9495)), min_length=76.7,
         rings=('90 inner band',)),
    dict(binding='confederacy:shipyard', identifier='legion_shipyard',
         label='legion shipyard', data_id='shipyard', faction='confederacy',
         envelope=((-62.04, 62.04), (-5.6, 41.6), (-45.0564, 62.4)), min_length=107.3,
         rings=('90 inner band',)),
    dict(binding='syndicate:shipyard', identifier='syndicate_shipyard',
         label='syndicate shipyard', data_id='shipyard', faction='syndicate',
         envelope=((-52.1606, 46.9468), (-18.9928, 45.6), (-53.6606, 48.4056)), min_length=101.9,
         rings=('90 inner band',)),
)
# The gameplay radius each kind's helpers scale by. A station's footprint is authored in
# nominal radius-50 space, so these numbers and the mesh extents move together or not at all.
STATION_RADII = {'research_station': 85, 'defense_platform': 60, 'trade_station': 65,
                 'fighter_platform': 75, 'repair_dock': 70, 'shipyard': 110}
# The kinds this batch authors, and how many families each one spans: every kind except the
# shipyard, where the Alliance yard is already the approved trio's `core` asset.
KIND_FAMILIES = {'research_station': 3, 'defense_platform': 3, 'trade_station': 3,
                 'fighter_platform': 3, 'repair_dock': 3, 'shipyard': 2}
# The satellite and planet-installation rows live in the same catalogue file but are not
# stations; B4 is their batch.
NON_STATION_KINDS = ('defense_satellite', 'attack_satellite', 'planet_extractor',
                     'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon')
# The floor the export wrapper enforces. Read from the template below, never assumed.
TRIANGLE_FLOOR = 1800
# Every role the batch review ablates on its own, per station.
ABLATED_ROLES = ('accent', 'dark', 'cool')
# Rows deliberately absent, and the spec must say why rather than fall silent.
OMITTED = ('imperial:research_station', 'imperial:defense_platform', 'imperial:trade_station',
           'imperial:fighter_platform', 'imperial:repair_dock', 'imperial:shipyard',
           'rebel:shipyard', 'rebel:mining_station', 'rebel:command_station')
# The clip list the harness is given, one row per family; the sheet may claim no other.
MOTION = ('rebel:research_station', 'confederacy:shipyard', 'syndicate:defense_platform')


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


def design_parts(payload):
    """The parts the author chose: the shared `9x` detail layer is a floor, not the design."""
    return [part for part in payload['parts'] if not part['name'].startswith('9')]


def design_mass_centre(payload):
    """Where a design carries its mass, normalised to its own envelope box.

    A station footprint is set by the binding's legacy extent, so three families of one kind
    can share a bounding box while their structure sits in completely different places. This
    measures that: a triangle-count-weighted centroid over the design parts only, mapped into
    the payload's own bounds.
    """
    lo, hi = payload['bounds']
    verts = payload['vertices']
    offsets = {role: 0 for role in payload['batches']}
    total = 0
    mass = [0., 0., 0.]
    for part in payload['parts']:
        role = part['role']
        start = offsets[role]
        end = start + part['triangles']
        offsets[role] = end
        if part['name'].startswith('9'):
            continue
        for row in payload['batches'][role][start:end]:
            points = [verts[i] for i in row[3:]]
            for axis in range(3):
                mass[axis] += sum(p[axis] for p in points) / 3
            total += 1
    assert total, 'a station with no design triangles is a detail layer, not a design'
    return [(mass[axis] / total - lo[axis]) / (hi[axis] - lo[axis]) for axis in range(3)]


def floating_parts(payload, tolerance=.25):
    """Groups of welded parts that stand clear of every other group, with their daylight.

    The exporter indexes vertices by quantised position, so parts that touch share vertices and
    fall into one group; a group that is nowhere near another one is a part - or a cluster of
    parts - floating in space.
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
                self.assertLessEqual(counted, 11500, 'the station advisory budget')
                self.assertLessEqual(len(payload['vertices']), 8000)
                for role, batch in payload['batches'].items():
                    self.assertTrue(batch, f'{asset["binding"]}: role {role} is empty')

    def test_each_mesh_reaches_its_binding_legacy_station_extent(self):
        """Same footprint as the legacy station, per axis and per side - not merely inside it.

        `stations.json` still carries a gameplay radius per kind, and the camera and contact
        helpers scale the station by that number over the mesh extent, so a station that only
        fits inside the legacy box quietly frames and collides differently. The legacy
        procedural station fills its declared box exactly, so reaching is the requirement.
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
                    self.assertAlmostEqual(legacy_lo[axis], asset['envelope'][axis][0], places=3)
                    self.assertAlmostEqual(legacy_hi[axis], asset['envelope'][axis][1], places=3)
                    span = legacy_hi[axis] - legacy_lo[axis]
                    self.assertLessEqual(abs(hi[axis] - legacy_hi[axis]), span * .01,
                                         f'axis {axis} high drifted from the legacy extent')
                    self.assertLessEqual(abs(lo[axis] - legacy_lo[axis]), span * .01,
                                         f'axis {axis} low drifted from the legacy extent')
                self.assertGreaterEqual(hi[2] - lo[2], asset['min_length'])

    def test_every_station_clears_the_pipeline_triangle_floor(self):
        """A design under the export floor cannot be exported at all, so it is not authored.

        The floor is what stops a station shipping as a degenerate box, and a specimen far
        below the station it replaces reads thin - so both bars are asserted, and the second
        one is measured against the live legacy mesh rather than a transcribed number.
        """
        # See the B3b module: the floor is generated into each wrapper from the template's default
        # expansion, which is what this batch was authored against.
        generator = (ROOT / 'tools/art/gen_export_wrappers.py').read_text(encoding='utf-8')
        self.assertIn("assert 1_800 < asset['triangle_count']", generator,
                      'the floor moved: re-check what this batch was authored against')
        from render.faction_stations import station_mesh
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                payload = payload_of(asset)
                legacy = sum(len(rows) for rows in
                             station_mesh(asset['faction'], asset['data_id']).values())
                self.assertGreater(payload['triangle_count'], TRIANGLE_FLOOR,
                                   f'{asset["binding"]} would be refused by the exporter')
                self.assertGreater(payload['triangle_count'], legacy * .5,
                                   'a specimen far below the station it replaces reads thin')

    def test_every_station_fills_every_material_role(self):
        """Two contracts at once: the loader rejects an empty role, and the review ablates three.

        `render.authored_mesh._load_profile` requires `set(batches) == set(ROLES)` with every
        batch non-empty, so a design that never used `base` cannot load at all. Separately, a
        role the review ablates but no station part uses reports a zero-pixel ablation, which
        measures nothing.
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

    def test_each_kind_is_a_kit_of_distinct_designs(self):
        """A kit of station primitives, not one body with different paint.

        The families of a kind share a footprint by contract here - several of them to the
        digit - so an envelope-aspect comparison cannot separate them the way it did in B3b.
        The comparison is over the parts the author chose: the `9x` detail layer is
        deliberately identical on every station in the catalogue, so it is excluded, and what
        is left is each design's own vocabulary, material-role mix, triangle count, part count
        and the place inside the shared box where its parts sit.
        """
        for kind, families in KIND_FAMILIES.items():
            same_kind = [a for a in ASSETS if a['data_id'] == kind]
            self.assertEqual(len(same_kind), families, kind)
            shapes = {}
            for asset in same_kind:
                payload = payload_of(asset)
                shapes[asset['binding']] = dict(
                    triangles=payload['triangle_count'],
                    vocabulary={p['name'].lower() for p in design_parts(payload)},
                    roles={r: len(b) for r, b in payload['batches'].items()},
                    parts=len(design_parts(payload)),
                    placement=design_mass_centre(payload))
            bindings = [a['binding'] for a in same_kind]
            for i, left in enumerate(bindings):
                for right in bindings[i + 1:]:
                    with self.subTest(kind=kind, pair=(left, right)):
                        a, b = shapes[left], shapes[right]
                        # Vocabulary is mandatory: the two designs may share a footprint and a
                        # stance, but they must not be assembled from the same parts.
                        shared = a['vocabulary'] & b['vocabulary']
                        self.assertLess(len(shared) / len(a['vocabulary'] | b['vocabulary']), .5,
                                        f'{left} and {right} share too much vocabulary')
                        self.assertNotEqual(a['roles'], b['roles'],
                                            'the two role distributions are identical')
                        self.assertNotEqual(a['triangles'], b['triangles'],
                                            'two families built the same amount of geometry')
                        # And they are not the same structure twice: either they are built from
                        # a different number of parts, or those parts sit in a different place
                        # inside the box they share.
                        placement = max(abs(x - y) for x, y in zip(a['placement'],
                                                                   b['placement']))
                        self.assertTrue(a['parts'] != b['parts'] or placement >= .03,
                                        f'{left} and {right} are the same structure twice: '
                                        f'{a["parts"]} parts at {placement:.3f} of the box')
            # A kind is not one silhouette: its designs do not all sit in the same place inside
            # the shared footprint.
            spread = max(max(abs(a[k] - b[k]) for k in range(3))
                         for a in (s['placement'] for s in shapes.values())
                         for b in (s['placement'] for s in shapes.values()))
            self.assertGreaterEqual(spread, .03,
                                    f'{kind}: the families sit in the same place in the box')

    def test_every_declared_ring_is_an_annulus_and_no_port_is_a_capped_disc(self):
        """A ring that encircles a member must stay hollow, and a port must be declared.

        Measured off the export: every vertex of a ring part sits away from the part's own
        vertical axis, so a capped disc - which has vertices down to the centre - fails here
        rather than in a screenshot. The name check runs the other way too: a part wearing an
        encirclement noun without being declared is a ring nobody reviewed. A wide deck whose
        aperture is a small hub is *not* an encirclement and stays out of the declared list -
        the rule is about parts a member passes through, and `03 Flight deck` / `04 Cargo deck`
        are the decks themselves, exactly as B3b treated its lattice disc.
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
                        # Normalised per axis: a habitat band is an ellipse, so an unscaled
                        # radius test would call a real ring a disc.
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
        """A duplicated part name aliases two parts: the review's part lookups hit one of them."""
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                names = [p['name'] for p in payload_of(asset)['parts']]
                duplicates = sorted({n for n in names if names.count(n) > 1})
                self.assertEqual(duplicates, [], f'{asset["binding"]}: {duplicates}')

    def test_no_station_claims_a_drive_or_a_weapon_part(self):
        """A station has no drive plume; an emitter or gun part here would be an unowned claim.

        A defense platform's battery reads as `battery`/`hardpoint`/`mantlet` because the
        renderer's own weapon paths are keyed on hull weapon entities, not on station part
        names - naming a station part `turret` would claim a binding the station does not have.
        """
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

    def test_no_station_master_carries_a_blender_backup_file(self):
        """`save_version = 0` in the seed: a `.blend1` beside a master is authored debris."""
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertFalse((ROOT / f"art/blender/{asset['identifier']}.blend1").exists())

    def test_the_seed_extent_self_check_ignores_float_noise_and_still_catches_a_real_shortfall(self):
        """A self-check that cries wolf is one nobody reads.

        The seed reports a breach when an authored extreme misses its declared limit and
        snapshots the tolerance so a later tightening fails this test rather than the owner.
        `plate` carries no bevel, so the tolerance only absorbs depsgraph float noise; both
        directions are asserted here.
        """
        helper, tolerance = seed_self_check()
        limits = [[-46.4, 46.4], [-32.4, 39.6], [-25.0848, 41.4431]]
        extremes = (('10 Keel strake', '10 Keel strake'), ('02 Beam pad left', '02 Beam pad left'),
                    ('03 Keel', '03 Keel'))
        noise = ([-46.4000015, -32.4000015, -25.0848], [46.4000015, 39.6, 41.4431])
        self.assertGreaterEqual(tolerance, 1e-3)
        self.assertEqual([], helper('sensor', *noise, limits, extremes),
                         'float noise must not print as a breach')
        real = ([-46.4, -32.4, -25.0848 - 0.03], [46.4, 39.6, 41.4431])
        caught = helper('relay', *real, limits, extremes)
        self.assertEqual(1, len(caught), caught)
        self.assertIn('BREACH', caught[0])
        self.assertEqual(3, len(helper('sensor', *noise, limits, extremes, tolerance=1e-6)),
                         'the 1e-6 tolerance is the defect this guards against')

    def test_the_batch_seed_refuses_to_overwrite_an_existing_master(self):
        """One seed authors all seventeen masters, so one refusal guards the whole batch."""
        masters = [ROOT / f"art/blender/{a['identifier']}.blend" for a in ASSETS]
        for master in masters:
            self.assertTrue(master.is_file(), 'the editable master must be committed')
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn('--replace-seed', text)
        spec = importlib.util.spec_from_file_location('seed_b3c_stations', ROOT / SEED)
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
            with self.subTest(binding=asset['binding']):
                wrapper = ROOT / f"tools/art/export_{asset['identifier']}.py"
                self.assertTrue(wrapper.is_file())
                # The wrapper's own declared bounds are the binding's legacy extent, not a
                # default: the export asserts each axis against these numbers, so a stale
                # envelope would let a mesh leave its frame.
                declared = {node.targets[0].id: ast.literal_eval(node.value)
                            for node in ast.parse(wrapper.read_text(encoding='utf-8')).body
                            if isinstance(node, ast.Assign)
                            and isinstance(node.targets[0], ast.Name)
                            and node.targets[0].id in ('ENVELOPE', 'MIN_LENGTH', 'MAX_TRIANGLES',
                                                       'MAX_VERTICES', 'MAX_BYTES')}
                self.assertEqual(declared['ENVELOPE'], asset['envelope'])
                span = asset['envelope'][2][1] - asset['envelope'][2][0]
                self.assertLessEqual(declared['MIN_LENGTH'], span)
                self.assertGreater(declared['MIN_LENGTH'], span - 1.5)
                self.assertLessEqual(declared['MAX_TRIANGLES'], 11500,
                                     'the station advisory budget')


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
                self.assertTrue(sum(len(t) for t in legacy.values()),
                                'the legacy faction station is what a selection replaces')

    def test_the_batch_completes_the_faction_station_table(self):
        """Every faction station row is now either authored, approved or explicitly a decision.

        Thirty rows exist across the three families (`stations.json` keys minus the satellite
        and planet-installation kinds). B3a authored three, B3b nine, this batch seventeen, and
        `rebel:shipyard` is the approved trio's `core` asset - so nothing is silently missing
        and the ten imperial rows are the only ones still blocked on the renderer seam.
        """
        stations = json.loads((ROOT / 'assets/data/stations/stations.json')
                              .read_text(encoding='utf-8'))['stations']
        kinds = [k for k in stations if k not in NON_STATION_KINDS]
        self.assertEqual(len(kinds), 10, sorted(kinds))
        authored = {a['binding'] for a in ASSETS}
        for earlier in EARLIER_BATCHES:
            authored |= {a['binding'] for a in
                         json.loads((ROOT / earlier).read_text(encoding='utf-8'))['assets']}
        factions = ('rebel', 'confederacy', 'syndicate')
        uncovered = {f'{faction}:{kind}' for faction in factions for kind in kinds
                     if f'{faction}:{kind}' not in authored}
        self.assertEqual(uncovered, {'rebel:shipyard'},
                         'exactly the approved trio shipyard may be outside the batches')
        self.assertTrue((ROOT / 'assets/models/manifests/alliance_shipyard.json').is_file(),
                        'the uncovered row is covered only by the approved runtime manifest')

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
                self.assertEqual(row['label'], asset['label'])
                self.assertEqual(row['data_id'], asset['data_id'])
                self.assertEqual(row['station_kind'], asset['data_id'])
                self.assertEqual(row['faction'], asset['faction'])
                self.assertEqual(row['seed'], SEED)
                self.assertEqual(row['seed_arg'], f"--asset {asset['binding']}")
                self.assertEqual(tuple(zip(*row['envelope'])), asset['envelope'])
                self.assertAlmostEqual(row['min_length'], asset['min_length'], places=1)
                span = asset['envelope'][2][1] - asset['envelope'][2][0]
                self.assertLessEqual(row['min_length'], span)
                self.assertGreater(row['min_length'], span - 1.)

    def test_every_row_label_is_unique_so_captures_cannot_overwrite(self):
        """A duplicated label silently overwrites another row's evidence on disk."""
        labels = [a['label'] for a in self.batch_spec()['assets']]
        self.assertEqual(len(set(labels)), len(labels), labels)

    def test_every_row_names_its_own_capture_and_only_the_listed_rows_claim_a_clip(self):
        spec = self.batch_spec()
        evidence = spec['evidence']
        self.assertEqual(sorted(evidence), sorted(a['binding'] for a in spec['assets']))
        self.assertEqual(len({row['sheet'] for row in evidence.values()}), 1,
                         'one contact sheet per batch')
        clips = sorted(b for b, row in evidence.items() if 'motion' in row)
        self.assertEqual(clips, sorted(MOTION),
                         'the sheet must claim exactly the clips the harness is given')
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

        These stations frame at 110-215 units and the shared scene carries a context group, so
        the closest rows failed with `camera not outside union`. The floor is a spec field, so
        it cannot be a harness constant that would move every earlier batch's committed frames.
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
        # The floor must lift the closest row and must not pull any row in past the widest
        # framing this batch already gives itself.
        self.assertLessEqual(min(frames), floor, 'the floor must lift the closest row')
        self.assertLessEqual(floor, max(frames), 'the floor must not shrink every specimen')

    def test_the_sheet_overview_file_comes_from_the_overview_draw(self):
        """`overview.png` must be the batch line-up, not a leftover row capture.

        The harness saved it from the `pixels` buffer the last row's last draw left behind, so
        the file that reads as the batch overview was a duplicate of one row's frame and did
        not move when the overview camera moved.
        """
        harness = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn("overview_frames['after']", harness)
        self.assertIn("str(out / 'overview.png')", harness)

    def test_the_row_line_cannot_overlap_and_fits_the_overview_frame(self):
        """Seventeen rows in one line: spacing above the widest radius pair, below the frame.

        The shared scene asserts every pair is clearer than the sum of its radii, and the
        overview frame has to hold the whole line or the outer rows fall out of the only scale
        view in the sheet.
        """
        spec = self.batch_spec()
        spacing = spec['overview']['spacing']
        widest = 2 * max(STATION_RADII[a['data_id']] for a in spec['assets'])
        self.assertGreater(spacing, widest, 'two adjacent rows would overlap')
        self.assertGreater(spacing, widest * 1.05, 'the non-overlap assertion needs clearance')
        # Every row has to land inside the overview frame, or the only scale view in the sheet
        # shows a subset of the batch and its changed-pixel count describes the middle rows.
        # The projection is reproduced here from the harness's own camera constants rather than
        # guessed: seventeen rows put the near end of the line further off-centre than the far
        # end, so a "frame about 1.67 x distance wide" estimate is not enough.
        harness = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        capture = (ROOT / 'artifacts/alliance_blender_trio/evidence/capture_slice.py'
                   ).read_text(encoding='utf-8')
        self.assertIn('W, H = 1280, 800', harness)
        self.assertIn('cam.fov, cam.near, cam.far = 55., 20., 60000.', capture)
        width, height, fov = 1280, 800, 55.
        tan_v = math.tan(math.radians(fov / 2))
        tan_h = tan_v * width / height
        rows = len(spec['assets'])
        target = [spec['overview']['first_x'], 0,
                  spec['overview']['first_z'] + (rows - 1) * spacing / 2]
        yaw = math.radians(spec['overview']['yaw'])
        pitch = math.radians(spec['overview']['pitch'])
        forward = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch),
                   -math.cos(pitch) * math.cos(yaw))
        right = [-forward[2], 0., forward[0]]
        norm = math.hypot(right[0], right[2])
        right = [c / norm for c in right]
        distance = spec['overview']['distance']
        eye = [target[i] - distance * forward[i] for i in range(3)]
        depths, offsets = [], []
        for index, asset in enumerate(spec['assets']):
            centre = [spec['overview']['first_x'], 0,
                      spec['overview']['first_z'] + index * spacing]
            view = [centre[i] - eye[i] for i in range(3)]
            depth = sum(view[i] * forward[i] for i in range(3))
            self.assertGreater(depth, 0., f"{asset['binding']} is behind the overview camera: at "
                                          f"this yaw the eye stands level with the far end of the "
                                          f"line and the row is not in the shot")
            x = sum(view[i] * right[i] for i in range(3)) / depth / tan_h
            depths.append(depth)
            offsets.append((asset['binding'], x))
            with self.subTest(binding=asset['binding']):
                self.assertLess(abs(x), .95,
                                f"{asset['binding']} projects at x_ndc {x:.2f}: outside the "
                                f"overview frame, raise overview.distance")
        # A scale lineup only means something if the rows are at comparable distances: a plan
        # where the near end is half as far as the far end is a perspective study, not a scale
        # comparison, and that is exactly what the 48-degree yaw produced on this batch.
        self.assertLessEqual(max(depths) / min(depths), 1.35,
                             'the overview rows are at too different distances to be one scale')

    def test_the_review_harness_owns_a_station_with_a_player_of_its_own_faction(self):
        """The renderer takes a *station's* faction from its owner, not from the data row.

        A station row owned by the rebel player draws the Alliance design for every binding,
        the seam is then queried as `rebel:<kind>` - which no candidate matches - and the row
        reports a 0.0-pixel change that reads as a no-op instead of a defect.
        """
        harness = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn("FACTION_OWNER[asset.get('faction', 'rebel')]", harness)
        self.assertIn("st.entities[ids['capital']].owner = owner", harness)
        self.assertIn('def players_for(', harness)

    def test_the_omitted_rows_and_this_batch_mates_are_named_by_the_spec(self):
        """A silent omission reads as an oversight; the spec must say why it is absent."""
        spec = self.batch_spec()
        bindings = {a['binding'] for a in spec['assets']}
        for binding in OMITTED:
            self.assertNotIn(binding, bindings)
        for phrase in ('imperial', 'alliance_shipyard', 'no mesh_for seam', 'earlier batches'):
            self.assertIn(phrase, spec['note'])

    def test_only_authorized_s06_specimens_register_with_legacy_default(self):
        """S07 execution authority registers exact approved revisions, not pending rows."""
        from s07_registration_assertions import assert_opt_in_registration, assert_preview_boundary
        bindings = [asset['binding'] for asset in ASSETS]
        assert_opt_in_registration(self, ROOT, bindings)
        assert_preview_boundary(self, ROOT, bindings)

    def test_every_evidence_path_the_sheet_points_at_exists(self):
        """A pointer to a file that is not there is worse than no pointer.

        The sheet is what the owner opens to judge the specimens, so every path in its
        `evidence` block is resolved here - a path that matches nothing must fail, not read as
        a pass, and only the rows the harness was given as motion clips may claim one.
        """
        spec = self.batch_spec()
        self.assertEqual({row['binding'] for row in spec['assets']}, set(spec['evidence']))
        for binding, entry in spec['evidence'].items():
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
                name = 'S06-' + asset['identifier'].upper().replace('_', '-') + '.json'
                path = ROOT / 'art/manifests/pending' / name
                self.assertTrue(path.is_file(), f'no sidecar at {name}')
                record = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(record['binding'], asset['binding'])
                self.assertEqual(record['status'], BATCH_STATUS)
                self.assertEqual(record['batch'], BATCH)
                self.assertEqual(record['appearance_decision'], APPEARANCE_DECISION)
                self.assertFalse(record['activation'],
                                 'appearance approval is not activation')
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

    def test_the_owner_appearance_approval_is_recorded_and_bound_to_these_revisions(self):
        """An approval binds to a revision: every hash the decision names must still be the file.

        The record is only worth reading if it is re-derivable. Touching any master, wrapper,
        seed, shared primitive or runtime export after the approval invalidates it here rather
        than in a reader's head - and the decision must also say, in the record, what it does
        *not* approve, because an approval that reads as a landing is the expensive mistake.
        """
        approvals = json.loads((ROOT / 'art/manifests/approvals.json').read_text(encoding='utf-8'))
        entries = [d for d in approvals['decision_log'] if d['id'] == APPEARANCE_DECISION]
        self.assertEqual(len(entries), 1, 'the batch decision must be recorded exactly once')
        decision = entries[0]
        self.assertEqual(decision['decision'], 'approved')
        self.assertEqual(decision['owner_words_verbatim'], 'yes')
        self.assertIn('look like the right direction', decision['question_answered'])
        self.assertIn('landing', ' '.join(decision['not_approved_by_this_decision']).lower(),
                      'the record must say that no landing is authorized')
        revisions = {row['gameplay_binding']: row for row in decision['revision']['assets']}
        self.assertEqual(sorted(revisions), sorted(a['binding'] for a in ASSETS))
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                row = revisions[asset['binding']]
                self.assertEqual(row['identifier'], asset['identifier'])
                self.assertEqual(row['faction'], asset['faction'])
                self.assertEqual(row['station_kind'], asset['data_id'])
                # the record stores the extent the way the batch sheet does ([lo, hi]),
                # so the comparison is transposed, exactly as the spec comparison above is
                self.assertEqual(tuple(zip(*row['legacy_extent'])), asset['envelope'])
                declared = {}
                for group in ('source', 'exporter', 'runtime'):
                    declared.update(row[group])
                self.assertIn(f"art/blender/{asset['identifier']}.blend", declared)
                self.assertIn(SEED, declared)
                self.assertIn(f"tools/art/export_{asset['identifier']}.py", declared)
                for path, digest in declared.items():
                    self.assertEqual(
                        digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                        f'{path} moved after the owner approved this revision: the approval no '
                        f'longer covers the bytes on disk')

    def test_the_batch_sheet_is_labelled_unreviewed(self):
        text = (ROOT / 'tools/diag_alliance_batch_review.py').read_text(encoding='utf-8')
        self.assertIn('UNAPPROVED REVIEW ONLY', text)
        self.assertIn('pending_owner_approval', text)

    def test_no_part_of_any_station_floats_clear_of_the_rest(self):
        """A station is one piece of hardware, not a constellation.

        Contact is not implied by authoring by centre and by reach, and `weld_scene` judges a
        joint by the clear space between the two parts' boxes - so a hardware row stepped wider
        than its own blocks leaves each block standing alone. The seed's weld pass closes the
        authored gaps and this measures the exported meshes, so a design that floats is caught
        here rather than by eye.
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
        seed = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn('weld_scene()', seed)
        self.assertLess(seed.index('weld_scene()'),
                        seed.index('report_bounds(limits, identifier)'))


if __name__ == '__main__':
    unittest.main()
