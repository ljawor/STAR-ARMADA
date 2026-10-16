"""Authored asset contract; appearance is judged separately from real-GL captures."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets/models/alliance_battleship.mesh.json'


class AuthoredBattleshipTests(unittest.TestCase):
    def setUp(self):
        from render.asset_selection import configure
        configure({"model_preview": True}, asset_root=ROOT)
        self.addCleanup(configure, {})

    def test_evaluated_blender_mesh_is_the_live_battleship(self):
        self.assertTrue(ASSET.is_file(), 'missing Blender-exported gameplay mesh')
        from render.faction_ships import ship_mesh
        asset = json.loads(ASSET.read_text(encoding='utf-8'))
        mesh = ship_mesh('rebel', 'battleship')
        self.assertEqual(asset['schema'], 1)
        self.assertEqual(asset['asset'], 'alliance_battleship')
        self.assertEqual(tuple(mesh), ('base', 'dark', 'trim', 'accent', 'lit', 'cool'))
        self.assertEqual({k: len(v) for k, v in mesh.items()},
                         {k: len(v) for k, v in asset['batches'].items()})
        for role, faces in asset['batches'].items():
            for (normal, tri), face in zip(mesh[role], faces):
                self.assertEqual(normal, tuple(face[:3]))
                self.assertEqual(tri, tuple(tuple(asset['vertices'][i]) for i in face[3:]))
        self.assertTrue((ROOT / 'art/blender/alliance_battleship.blend').is_file())
        self.assertTrue((ROOT / 'tools/art/build_alliance_battleship.py').is_file())

    def test_loader_rejects_normal_not_matching_evaluated_face(self):
        import tempfile
        from render.authored_mesh import load_battleship
        asset = json.loads(ASSET.read_text(encoding='utf-8'))
        # A normalized but skewed face normal still has positive winding;
        # accepting it would silently ship incorrect bevel lighting.
        face = asset['batches']['base'][0]
        face[:3] = [0.6, 0.8, 0.0] if abs(face[1]) > .5 else [0.0, 0.6, 0.8]
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'bad.mesh.json'
            p.write_text(json.dumps(asset), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_battleship(p)

    def test_loader_rejects_corrupt_and_over_budget_payloads(self):
        import copy
        import tempfile
        from render.authored_mesh import load_battleship, MAX_BYTES
        original = json.loads(ASSET.read_text(encoding='utf-8'))
        def mutate(key, value):
            data = copy.deepcopy(original)
            data[key] = value
            return data
        cases = [mutate('schema', 2), mutate('asset', 'other'),
                 mutate('vertices', []), mutate('batches', {}),
                 mutate('triangle_count', -1), mutate('bounds', [[0,0,0],[0,0,0]])]
        bad_index = copy.deepcopy(original)
        bad_index['batches']['base'][0][3] = len(original['vertices'])
        cases.append(bad_index)
        nan_vertex = copy.deepcopy(original)
        nan_vertex['vertices'][0][0] = float('nan')
        cases.append(nan_vertex)
        bool_index = copy.deepcopy(original)
        bool_index['batches']['base'][0][3] = True
        cases.append(bool_index)
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'bad.mesh.json'
            for i, data in enumerate(cases):
                with self.subTest(case=i):
                    p.write_text(json.dumps(data), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_battleship(p)
            p.write_bytes(b' ' * (MAX_BYTES + 1))
            with self.assertRaisesRegex(ValueError, 'file budget'):
                load_battleship(p)

    def test_missing_asset_falls_back_once_without_affecting_other_hulls(self):
        from render import asset_selection as selection, faction_ships
        from test_asset_registry import isolated_assets
        expected = faction_ships.ship_mesh('rebel', 'battleship')
        frigate = faction_ships.ship_mesh('rebel', 'frigate')
        root = isolated_assets(self)
        (root / 'assets/models/alliance_battleship.mesh.json').unlink()
        selection.configure({'model_preview': True}, asset_root=root)
        fallback = faction_ships.ship_mesh('rebel', 'battleship')
        self.assertIs(fallback, faction_ships.ship_mesh('rebel', 'battleship'))
        self.assertEqual(len(selection.diagnostics()['issues']), 1)
        self.assertEqual(selection.diagnostics()['issues'][0]['code'], 'E_FILE_MISSING')
        self.assertTrue(all(fallback.values()))
        self.assertTrue(fallback != expected)
        self.assertEqual(frigate, faction_ships.ship_mesh('rebel', 'frigate'))
        selection.configure({'model_preview': True}, asset_root=ROOT)
        self.assertEqual(faction_ships.ship_mesh('rebel', 'battleship'), expected)

    def test_loaded_asset_is_deeply_immutable_with_single_bounded_cache(self):
        from render.authored_mesh import battleship_mesh
        mesh = battleship_mesh()
        self.assertIs(mesh, battleship_mesh())
        self.assertEqual(battleship_mesh.cache_info().maxsize, 1)
        with self.assertRaises(TypeError):
            mesh['base'] = ()
        with self.assertRaises(TypeError):
            mesh['base'][0][1][0][0] = 1
