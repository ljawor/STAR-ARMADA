"""S06 batch B4 guards - the satellite and planet-installation rows.

The rows are the satellite and planet-installation kinds `assets/data/stations/stations.json`
holds beside the station kinds, across the four factions: 24 bindings. They are script-authoritative
per the S03 source-authority policy, so `tools/art/build_b4_hardware.py` is the master recipe and the
`.blend` is a derived artifact.

The envelope table here is duplicated from the probe's live-code measurements on purpose - a guard
that imported the seed would import Blender with it - and `SeedTable` re-derives it from the seed's
own AST, so the two cannot drift apart unnoticed.

Run:  PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b4_hardware
"""

import ast
import hashlib
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / 'art/manifests/pending'
SPEC = PENDING / 'S06-BATCH-B4-HARDWARE.json'
EVIDENCE = ROOT / 'artifacts/s06_alliance_batch_review/b4-hardware'

BATCH = 's06-b4-hardware'
SEED = 'tools/art/build_b4_hardware.py'
SCENE = 'tools/art/probe_b4_scope.py'
# The owner's approval of this batch, recorded in art/manifests/approvals.json and bound to the exact
# revisions this module guards. It authorizes no landing: every binding stays unregistered.
APPEARANCE_DECISION = 's06-b4-hardware-2026-10-17'
BATCH_STATUS = 'appearance_approved_pending_landing'

# The probe's measurements. Per kind and faction-independent: the legacy hardware differs in ring
# side count, not extent.
# As every S06 sheet carries them: [lo, hi] per axis, vectors not pairs, because the harness
# transposes them into the loader's per-axis limits.
# Two rows are not faction-independent, and the guard says so rather than smoothing them over:
# the legacy satellite mesh is parameterised by the faction's ring side count, so the syndicate's
# five-sided ring stops short at the rear.
FACTION_Z_LOW = {('syndicate', 'defense_satellite'): -27.5066,
                 ('syndicate', 'attack_satellite'): -30.299}
LIMITS = {
    'defense_satellite': ((-41.1051, -9.0, -34.0), (41.1051, 19.5, 44.0)),
    'attack_satellite': ((-50.9795, -9.0, -34.0), (50.9795, 21.5, 58.0)),
    'planet_extractor': ((-34.0, 0.0, -32.0), (34.0, 43.0, 32.0)),
    'planet_trade_hub': ((-34.0, 0.0, -32.0), (34.0, 49.5, 32.0)),
    'planet_shield_generator': ((-34.0, 0.0, -32.0), (34.0, 46.5, 32.0)),
    'planet_pulsar_cannon': ((-34.0, 0.0, -32.0), (34.0, 42.4, 46.0)),
}
FACTION_PREFIX = {'rebel': 'alliance', 'confederacy': 'legion', 'syndicate': 'syndicate',
                  'imperial': 'imperial'}
FACTIONS = ('rebel', 'confederacy', 'syndicate', 'imperial')
SHARED_LEGACY = ('defense_satellite', 'attack_satellite')
OWN_CAPS = dict(triangles=11500, vertices=8000, bytes=2_000_000)
LOADER_CAPS = dict(triangles=12000, vertices=10000, bytes=2_000_000)
ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


def assets():
    out = []
    for faction in FACTIONS:
        for kind, limits in LIMITS.items():
            identifier = f'{FACTION_PREFIX[faction]}_{kind}'
            lo = list(limits[0])
            if (faction, kind) in FACTION_Z_LOW:
                lo[2] = FACTION_Z_LOW[(faction, kind)]
            out.append(dict(binding=f'{faction}:{kind}', identifier=identifier, faction=faction,
                            data_id=kind, envelope=(tuple(lo), limits[1]),
                            min_length=round(limits[1][2] - lo[2] - 0.2, 1)))
    return tuple(out)


ASSETS = assets()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def mesh(asset):
    return load(ROOT / f"assets/models/{asset['identifier']}.mesh.json")


def spec():
    return load(SPEC)


class SeedTable(unittest.TestCase):
    def test_the_seed_declares_exactly_the_guarded_rows(self):
        """A guard that drifts from the seed's own table guards a batch that is not the batch."""
        tree = ast.parse((ROOT / SEED).read_text(encoding='utf-8'))
        limits, prefixes = {}, {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'LIMITS':
                limits = ast.literal_eval(node.value)
            if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FACTION_PREFIX':
                prefixes = ast.literal_eval(node.value)
        self.assertEqual(prefixes, FACTION_PREFIX)
        self.assertEqual({k: tuple(zip(*[tuple(a) for a in v])) for k, v in limits.items()},
                         LIMITS, 'the seed\'s per-axis extents and this table disagree')
        overrides = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'FACTION_Z_LOW':
                overrides = {tuple(k): v for k, v in ast.literal_eval(node.value).items()}
        self.assertEqual(overrides, FACTION_Z_LOW,
                         'the seed\'s per-faction overrides and this table disagree')

    def test_the_seed_keeps_the_legacy_ring_side_count_per_faction(self):
        """The authored silhouette keeps the family's base polygon, so a row still reads as the
        hardware it replaces."""
        tree = ast.parse((ROOT / SEED).read_text(encoding='utf-8'))
        sides = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'SIDES':
                sides = ast.literal_eval(node.value)
        self.assertEqual(sides, {'imperial': 6, 'rebel': 12, 'confederacy': 8, 'syndicate': 5})

    def test_the_seed_refuses_to_overwrite_an_existing_master(self):
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn('is the editable master', text)
        self.assertIn("'--replace-seed' not in argv", text)
        # The refusal runs before Blender is imported, so a half-run cannot start.
        self.assertLess(text.index('_refuse_existing_masters(_ARGV)'), text.index('import bpy'))

    def test_the_seed_welds_the_scene_before_it_reports_the_extent(self):
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertLess(text.index('weld_scene()'), text.index('report_bounds(limits, identifier)'))

    def test_the_seed_extent_check_ignores_float_noise_and_catches_a_real_shortfall(self):
        """The self-check is a pure function, so it is driven here without Blender."""
        tree = ast.parse((ROOT / SEED).read_text(encoding='utf-8'))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == 'breach_lines')
        const = next(n for n in tree.body
                     if isinstance(n, ast.Assign)
                     and getattr(n.targets[0], 'id', '') == 'BREACH_TOLERANCE')
        # The function's default tolerance comes from the module constant, so both travel together.
        module = ast.Module(body=[const, fn], type_ignores=[])
        namespace = {}
        exec(compile(ast.fix_missing_locations(module), '<seed>', 'exec'), namespace)
        breach_lines = namespace['breach_lines']
        limits = [[-10.0, 10.0], [-5.0, 5.0], [-10.0, 10.0]]
        self.assertEqual(breach_lines('x', [-10.0, -5.0, -10.0], [10.0, 5.0, 10.0], limits,
                                       [['', '']] * 3), [])
        self.assertEqual(breach_lines('x', [-10.0001, -5.0, -10.0], [10.0, 5.0, 10.0], limits,
                                       [['', '']] * 3), [])
        # The check is one-sided on purpose: it refuses an overrun, while *reaching* the envelope
        # is the review harness's comparison, not this function's job.
        over = breach_lines('x', [-10.5, -5.0, -10.0], [10.0, 5.0, 10.0], limits,
                            [['', '']] * 3)
        self.assertEqual(len(over), 1)
        self.assertIn('X low', over[0])
        self.assertEqual(breach_lines('x', [-10.0, -5.0, -10.0], [10.0, 5.0, 10.0004], limits,
                                       [['', '']] * 3), [])


class GeometryContract(unittest.TestCase):
    def test_each_pending_asset_satisfies_the_loader_contract(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                data = mesh(asset)
                self.assertEqual(data['asset'], asset['identifier'])
                self.assertEqual(data['triangle_count'], sum(len(v) for v in data['batches'].values()))
                self.assertLessEqual(data['triangle_count'], OWN_CAPS['triangles'])
                self.assertLessEqual(data['triangle_count'], LOADER_CAPS['triangles'])
                self.assertGreater(data['triangle_count'], 1800)
                self.assertLessEqual(len(data['vertices']), OWN_CAPS['vertices'])
                self.assertLessEqual(len(data['vertices']), LOADER_CAPS['vertices'])
                self.assertLessEqual((ROOT / f"assets/models/{asset['identifier']}.mesh.json")
                                     .stat().st_size, OWN_CAPS['bytes'])
                for role, rows in data['batches'].items():
                    self.assertIn(role, ROLES)
                    for row in rows:
                        self.assertEqual(len(row), 6, 'a batch row is a normal followed by three '
                                                      'vertex indices')
                        for index in row[3:]:
                            self.assertLess(index, len(data['vertices']))
                            self.assertGreaterEqual(index, 0)
                        self.assertAlmostEqual(math.sqrt(sum(c * c for c in row[:3])), 1.0, places=9)

    def test_each_mesh_reaches_its_binding_legacy_extent(self):
        """The harness compares the authored footprint against the legacy hardware mesh within
        1 percent per axis; the legacy hardware fills its declared box exactly."""
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                lo, hi = mesh(asset)['bounds']
                for axis in range(3):
                    low, high = asset['envelope'][0][axis], asset['envelope'][1][axis]
                    self.assertLessEqual(abs(lo[axis] - low), max(1e-3, abs(low) * .01),
                                         f'{asset["identifier"]} axis {axis} low {lo[axis]} vs {low}')
                    self.assertLessEqual(abs(hi[axis] - high), max(1e-3, abs(high) * .01),
                                         f'{asset["identifier"]} axis {axis} high {hi[axis]} vs {high}')
                self.assertGreaterEqual(hi[2] - lo[2], asset['min_length'])

    def test_every_row_fills_every_material_role(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                present = {role for role, rows in mesh(asset)['batches'].items() if rows}
                self.assertEqual(present, set(ROLES))

    def test_every_part_name_is_unique_within_its_row(self):
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                names = [part['name'] for part in mesh(asset)['parts']]
                self.assertEqual(len(names), len(set(names)))

    def test_no_two_rows_are_the_same_geometry(self):
        """Four factions are four designs, not one design with different paint."""
        seen = {}
        for asset in ASSETS:
            digest = hashlib.sha256(
                json.dumps(mesh(asset)['batches'], sort_keys=True).encode()).hexdigest()
            with self.subTest(binding=asset['binding']):
                self.assertNotIn(digest, seen,
                                 f'{asset["binding"]} is identical to {seen.get(digest)}')
            seen[digest] = asset['binding']

    def test_every_kind_is_the_same_kit_across_factions_but_not_the_same_parts(self):
        """Per kind the part vocabulary is shared and the sizes differ: that is what makes a row
        read as the family's hardware rather than as a different object."""
        for kind in LIMITS:
            rows = [a for a in ASSETS if a['data_id'] == kind]
            triangles = [mesh(a)['triangle_count'] for a in rows]
            with self.subTest(kind=kind):
                self.assertEqual(len(rows), 4)
                self.assertGreater(max(triangles) - min(triangles), 0,
                                   f'{kind} is byte-identical across factions')

    def test_the_runtime_never_reaches_the_loader_ceiling(self):
        headroom = []
        for asset in ASSETS:
            data = mesh(asset)
            headroom.append((asset['binding'], OWN_CAPS['triangles'] - data['triangle_count'],
                             LOADER_CAPS['triangles'] - data['triangle_count'],
                             OWN_CAPS['vertices'] - len(data['vertices'])))
        self.assertTrue(all(row[1] > 0 and row[2] > 0 and row[3] > 0 for row in headroom),
                        headroom)


class SourceSafety(unittest.TestCase):
    def test_exporters_open_the_declared_master_and_never_save_it(self):
        for asset in ASSETS:
            wrapper = ROOT / f"tools/art/export_{asset['identifier']}.py"
            with self.subTest(identifier=asset['identifier']):
                text = wrapper.read_text(encoding='utf-8')
                self.assertIn(f"IDENTIFIER = '{asset['identifier']}'", text)
                self.assertIn('open_mainfile', text)
                for forbidden in ('save_as_mainfile', 'save_mainfile', 'wm.save'):
                    self.assertNotIn(forbidden, text)

    def test_the_export_refuses_every_master_alias_before_open(self):
        for asset in ASSETS:
            text = (ROOT / f"tools/art/export_{asset['identifier']}.py").read_text(encoding='utf-8')
            with self.subTest(identifier=asset['identifier']):
                self.assertIn('must not overwrite the input Blender master', text)

    def test_the_generated_export_wrappers_match_their_template(self):
        """B4's wrappers come from the generator's loop, so the check reads the rendered file and
        the generator's own table rather than looking for an identifier literal that is not there."""
        text = (ROOT / 'tools/art/gen_export_wrappers.py').read_text(encoding='utf-8')
        self.assertIn('B4_KINDS', text)
        self.assertIn('B4_FACTION_Z_LOW', text)
        for asset in ASSETS:
            pairs = tuple((asset['envelope'][0][axis], asset['envelope'][1][axis])
                          for axis in range(3))
            with self.subTest(identifier=asset['identifier']):
                wrapper = (ROOT / f"tools/art/export_{asset['identifier']}.py").read_text(
                    encoding='utf-8')
                self.assertIn(f"IDENTIFIER = '{asset['identifier']}'", wrapper)
                self.assertIn(repr(pairs), wrapper)
                self.assertIn(repr(asset['min_length']), wrapper)

    def test_the_batch_declares_its_own_authority_and_review_state(self):
        text = (ROOT / SEED).read_text(encoding='utf-8')
        self.assertIn("authority='script'", text)
        self.assertIn("approval='pending_owner_approval'", text)
        self.assertIn('script-authoritative per the S03', text)


class HardwareSeam(unittest.TestCase):
    def test_the_seam_is_what_dispatches_every_guarded_binding(self):
        """`station_mesh` consults `mesh_for(f'{faction}:{data_id}')` ahead of every fallback -
        including the imperial branch and the planet-building builder."""
        source = (ROOT / 'render/fleet_geometry.py').read_text(encoding='utf-8')
        body = source[source.index('def station_mesh'):]
        body = body[:body.index('\n@lru_cache')]
        self.assertLess(body.index('mesh_for('), body.index('BUILDING_TYPES'))
        self.assertLess(body.index('mesh_for('), body.index("data_id in ('defense_satellite'"))
        self.assertLess(body.index('mesh_for('), body.index("if faction != 'imperial'"))

    def test_the_rows_resolve_to_legacy_hardware_until_they_are_registered(self):
        """Selection, not dispatch: with no registry entry the seam returns nothing and the
        procedural hardware still draws."""
        from render.asset_selection import mesh_for
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertIsNone(mesh_for(f"{asset['faction']}:{asset['data_id']}"))

    def test_the_satellite_and_building_builders_are_still_reachable_as_the_fallback(self):
        """The fallback stays reachable: activation is still the separate S10/S11 decision."""
        self.assertIn('def _satellite_mesh',
                      (ROOT / 'render/fleet_geometry.py').read_text(encoding='utf-8'))
        self.assertIn('def building_mesh',
                      (ROOT / 'render/planet building geometry.py'.replace(' ', '_'))
                      .read_text(encoding='utf-8'))


class PendingRecords(unittest.TestCase):
    def test_batch_spec_lists_exactly_the_guarded_bindings(self):
        sheet = spec()
        self.assertEqual(sheet['batch'], BATCH)
        self.assertEqual(sheet['status'], BATCH_STATUS)
        self.assertEqual(sheet['appearance_decision'], APPEARANCE_DECISION)
        self.assertIn('not an approval record', sheet['note'])
        rows = {a['binding']: a for a in sheet['assets']}
        self.assertEqual(sorted(rows), sorted(a['binding'] for a in ASSETS))
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                row = rows[asset['binding']]
                self.assertEqual(row['identifier'], asset['identifier'])
                self.assertEqual(row['faction'], asset['faction'])
                self.assertEqual(row['station_kind'], asset['data_id'])
                self.assertEqual(tuple(tuple(a) for a in row['envelope']), asset['envelope'])
                self.assertEqual(row['min_length'], asset['min_length'])
                self.assertEqual(row['seed'], SEED)
                self.assertEqual(row['seed_arg'], f"--asset {asset['binding']}")

    def test_no_pending_binding_is_registered_anywhere_in_production(self):
        registry = load(ROOT / 'assets/models/registry.json')
        status = {b['binding']: b['status'] for b in registry['bindings']}
        pipeline = load(ROOT / 'art/manifests/pipeline.json')
        registered = {a['binding'] for a in pipeline['assets']}
        approvals = load(ROOT / 'art/manifests/approvals.json')
        bound = json.dumps([e for e in approvals['approved_assets'] if isinstance(e, dict)])
        for asset in ASSETS:
            with self.subTest(binding=asset['binding']):
                self.assertEqual(status[asset['binding']], 'procedural_legacy',
                                 'an approved-appearance specimen must still not be selectable')
                self.assertNotIn(asset['binding'], registered)
                self.assertNotIn(asset['identifier'], bound)
                self.assertNotIn(asset['binding'], bound)

    def test_every_specimen_has_a_pending_sidecar_bound_to_its_own_master(self):
        for asset in ASSETS:
            sidecar = PENDING / f"S06-{asset['identifier'].upper().replace('_', '-')}.json"
            with self.subTest(binding=asset['binding']):
                record = load(sidecar)
                self.assertEqual(record['binding'], asset['binding'])
                self.assertEqual(record['status'], BATCH_STATUS)
                self.assertEqual(record['batch'], BATCH)
                self.assertEqual(record['appearance_decision'], APPEARANCE_DECISION)
                self.assertFalse(record['activation'], 'appearance approval is not activation')
                self.assertIsNone(record['owner_decision'],
                                  'appearance approval is not a landing decision')

    def test_every_evidence_path_the_sheet_points_at_exists(self):
        sheet = spec()
        for binding, entry in sheet['evidence'].items():
            self.assertIn(binding, {a['binding'] for a in ASSETS})
            for key, value in entry.items():
                paths = value if isinstance(value, list) else [value]
                for path in paths:
                    with self.subTest(binding=binding, key=key):
                        self.assertTrue((ROOT / path).exists(), path)

    def test_every_row_names_its_own_capture_and_only_the_listed_rows_claim_a_clip(self):
        sheet = spec()
        names = [a['identifier'] for a in sheet['assets']]
        self.assertEqual(len(names), len(set(names)))
        for binding, entry in sheet['evidence'].items():
            with self.subTest(binding=binding):
                self.assertIn('close', entry)
                if 'motion' in entry:
                    self.assertIn(binding, spec()['motion'],
                                  'a row that claims a clip must be listed in the sheet\'s motion list')

    def test_the_omitted_rows_are_named_by_the_spec(self):
        note = spec()['note']
        for expected in ('station kinds', 'ship_visual_key', 'no separate modular-hardware'):
            self.assertIn(expected, note)


if __name__ == '__main__':
    unittest.main()
