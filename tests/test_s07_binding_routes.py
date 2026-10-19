"""GL-free route evidence: actual CPU dispatch is not renderer acceptance."""
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BindingRouteAuditTests(unittest.TestCase):
    def audit(self):
        name = 'tools.art.audit_s07_routes'
        self.assertIsNotNone(importlib.util.find_spec(name), 'S07 route audit is not implemented')
        return importlib.import_module(name)

    def test_all_historical_identities_have_deterministic_current_routes(self):
        tool = self.audit()
        report = tool.build_report(ROOT)
        self.assertEqual(report, tool.build_report(ROOT))
        inventory = json.loads((ROOT / 'art/manifests/model_inventory.json').read_text())
        self.assertEqual(len(report['rows']), 120)
        self.assertEqual({r['canonical_binding'] for r in report['rows']},
                         {r['canonical_binding'] for r in inventory['rows']})
        rows = {r['canonical_binding']: r for r in report['rows']}
        bomber = rows['ship:confederacy:bomber_squadron']
        self.assertEqual(bomber['data_id'], 'confed_bomber_squadron')
        self.assertEqual(bomber['runtime_binding'], 'confederacy:bomber')
        self.assertEqual(bomber['legacy_visual_key'], 'confederacy:bomber')
        self.assertEqual(bomber['dispatch_entry'], 'render.fleet_geometry:ship_mesh')
        self.assertEqual(rows['station:imperial:shipyard']['runtime_binding'], 'imperial:shipyard')
        self.assertEqual(rows['hardware:construction:rebel:planet_extractor']['data_id'],
                         'planet_extractor')
        self.assertEqual(report['counts'], {'selected': 107, 'deferred_texture_pipeline': 10,
                                             'outside_mesh_catalogue': 3})
        self.assertEqual(report['errors'], [])
        self.assertTrue(all(not r['runtime_integration_proven'] for r in report['rows']))


    def test_selection_is_separate_from_actual_geometry_dispatch(self):
        from unittest.mock import patch
        from render import fleet_geometry
        tool = self.audit()
        report = tool.build_report(ROOT)
        rows = {r['canonical_binding']: r for r in report['rows']}
        selected = rows['ship:rebel:frigate']
        self.assertEqual(selected['disposition'], 'selected')
        self.assertTrue(selected['geometry_dispatch_proven'])
        self.assertEqual(selected['geometry_dispatch_identity'], 'rebel:frigate')
        self.assertGreater(selected['triangles'], 0)
        scaffold = rows['construction:site:scaffold']
        self.assertEqual(scaffold['disposition'], 'selected')
        # This CPU audit does not exercise the construction renderer's dispatch.
        self.assertFalse(scaffold['geometry_dispatch_proven'])
        self.assertFalse(scaffold['cpu_dispatch_exercised'])
        self.assertIsNone(scaffold['geometry_dispatch_identity'])
        self.assertTrue(scaffold['approval_mesh_match'])
        self.assertEqual(rows['environment:temperate']['disposition'], 'deferred_texture_pipeline')
        self.assertEqual(rows['menu:cinematic:backdrop']['disposition'], 'outside_mesh_catalogue')
        # Deliberately break the real consumer, not the selection predicate.
        with patch.object(fleet_geometry, 'ship_mesh', return_value={}):
            broken = tool.build_report(ROOT)
        row = next(r for r in broken['rows'] if r['canonical_binding'] == 'ship:rebel:frigate')
        self.assertEqual(row['disposition'], 'selected')
        self.assertFalse(row['geometry_dispatch_proven'])
        self.assertIn('rebel:frigate: selected metadata did not reach geometry dispatch', broken['errors'])


    def test_live_data_role_overrides_historical_identity_and_shape(self):
        from dataclasses import replace
        from types import SimpleNamespace
        import game.core.manager
        from game.data.store import DataStore
        ds = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=[], balance={})
        # Historical suffix still says frigate; the current catalogue says cruiser.
        data = replace(ds.ships['rebel_frigate'], category='cruiser')
        fixture = SimpleNamespace(ships={'rebel_frigate': data}, stations=ds.stations)
        tool = self.audit()
        self.assertTrue(hasattr(tool, 'route_identity'), 'live route identity helper missing')
        self.assertEqual(tool.route_identity(fixture, 'ship:rebel:frigate'),
                         ('rebel:cruiser', 'rebel_frigate', 'render.fleet_geometry:ship_mesh'))
        for identity in ('ship:unknown:frigate', 'station:rebel:no_station', 'garbage:identity'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                tool.route_identity(ds, identity)


    def test_cli_is_read_only_and_runs_without_pythonpath(self):
        import os
        import subprocess
        import sys
        tool = self.audit()
        expected = tool.build_report(ROOT)
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        run = subprocess.run([sys.executable, str(ROOT / 'tools/art/audit_s07_routes.py'),
                              '--root', str(ROOT), '--summary'], cwd=ROOT,
                             env=environment, text=True, capture_output=True)
        self.assertNotIn('Traceback', run.stderr)
        self.assertTrue(run.stdout.strip(), 'audit CLI produced no report')
        actual = json.loads(run.stdout)
        self.assertEqual(actual['inventory_rows'], 120)
        self.assertEqual(actual['counts'], expected['counts'])
        self.assertEqual(run.returncode, int(bool(expected['errors'] or expected['approval_integrity_errors'])))

    def test_real_configured_resolver_routes_convoy_aliases_and_imperial_station(self):
        """Synthetic core fixture proves seams, NOT candidate revision/appearance acceptance."""
        import game.core.manager
        from game.data.store import DataStore
        from render import asset_selection as selection
        from render.faction_visuals import FACTIONS, ship_visual_key
        from render.fleet_geometry import ship_mesh, station_mesh
        from test_asset_registry import GenericGeometryTests
        ds = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=[], balance={})
        fixture = GenericGeometryTests.fixture(self)
        registry_path = fixture / 'assets/models/registry.json'
        registry = json.loads(registry_path.read_text())
        template = next(r for r in registry['bindings'] if r['binding'] == 'rebel:frigate')
        bindings = [f'{f}:convoy' for f in FACTIONS] + ['imperial:shipyard', 'imperial:fighter']
        # Only the disposable fixture registry changes; production candidates remain unregistered.
        for row in registry['bindings']:
            if row['binding'] in bindings:
                # Copy the synthetic fixture's full binding contract, not production
                # approval/envelope fields belonging to a different real asset.
                row.pop('legacy_identifiers', None)  # Modern shared fixture needs no legacy alias.
                for field in ('manifest', 'status', 'envelope', 'envelope_decision'):
                    if field in template:
                        row[field] = template[field]
                    else:
                        row.pop(field, None)
        registry_path.write_text(json.dumps(registry), encoding='utf-8')
        selection.configure({})
        self.addCleanup(selection.configure, {})
        legacy_station = station_mesh('shipyard', 'imperial')
        legacy_unknown = station_mesh('no_station', 'unknown')
        legacy_fighter = ship_visual_key(ds, 'imperial_tie_squadron')
        selection.configure({'model_preview': True}, asset_root=fixture)
        for faction in FACTIONS:
            binding = f'{faction}:convoy'
            crew = next(k for k, d in ds.ships.items()
                        if d.faction == faction and d.category == 'crew_transport')
            authored = selection.mesh_for(binding)
            self.assertIsNotNone(authored)
            for data_id in (crew, 'trade_convoy'):
                with self.subTest(faction=faction, data_id=data_id):
                    self.assertEqual(selection.ship_binding(ds, data_id, faction), binding)
                    self.assertEqual(ship_visual_key(ds, data_id, faction), binding)
                    self.assertIs(ship_mesh(ship_visual_key(ds, data_id, faction)), authored)
            # Ownership faction does not repaint/rebind a captured catalogue ship.
            self.assertEqual(selection.ship_binding(ds, crew, 'unknown'), binding)
        self.assertEqual(selection.ship_binding(ds, 'imperial_tie_squadron'), 'imperial:fighter')
        self.assertIs(ship_mesh(ship_visual_key(ds, 'imperial_tie_squadron')),
                      selection.mesh_for('imperial:fighter'))
        self.assertIs(station_mesh('shipyard', 'imperial'), selection.mesh_for('imperial:shipyard'))
        for faction in (None, 'unknown'):
            self.assertIsNone(selection.ship_binding(ds, 'trade_convoy', faction))
            self.assertEqual(ship_visual_key(ds, 'trade_convoy', faction), 'box')
        self.assertIsNone(selection.ship_binding(ds, 'unknown_ship', 'rebel'))
        self.assertIsNone(selection.mesh_for('unknown:station'))
        self.assertIs(station_mesh('no_station', 'unknown'), legacy_unknown)
        selection.configure({})
        self.assertEqual(ship_visual_key(ds, 'imperial_tie_squadron'), legacy_fighter)
        self.assertIs(station_mesh('shipyard', 'imperial'), legacy_station)


    def test_selected_revision_must_match_approved_runtime_bytes(self):
        from unittest.mock import patch
        from render.asset_registry import AssetResolver
        tool = self.audit()
        resolver = AssetResolver(ROOT)
        # A real valid mesh under the wrong binding is not approval correspondence.
        resolver._bindings['rebel:frigate']['manifest'] = resolver._bindings['rebel:battleship']['manifest']
        resolver._bindings['rebel:frigate'].pop('envelope', None)
        resolver._bindings['rebel:frigate'].pop('envelope_decision', None)
        self.assertIsNotNone(resolver.resolve('rebel:frigate'), 'negative fixture must actually resolve')
        with patch.object(tool, 'AssetResolver', return_value=resolver):
            report = tool.build_report(ROOT)
        self.assertIn('rebel:frigate: selected mesh differs from approved revision', report['errors'])


    def test_broken_registered_binding_is_not_reported_as_unregistered(self):
        from unittest.mock import patch
        from render.asset_registry import AssetResolver
        tool = self.audit()
        resolver = AssetResolver(ROOT)
        resolver._bindings['rebel:frigate']['manifest'] = 'missing:manifest'
        with patch.object(tool, 'AssetResolver', return_value=resolver):
            report = tool.build_report(ROOT)
        self.assertIn('rebel:frigate: registered core binding failed to resolve', report['errors'])
        row = next(r for r in report['rows'] if r['canonical_binding'] == 'ship:rebel:frigate')
        self.assertEqual(row['disposition'], 'registered_unresolved')


if __name__ == '__main__':
    unittest.main()
