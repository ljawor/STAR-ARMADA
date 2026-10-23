"""Read-only cinematic planning contracts; no Blender, SDL context or simulation."""
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CinematicSceneTests(unittest.TestCase):
    def spec(self):
        self.assertIsNotNone(importlib.util.find_spec('tools.cinematics.scene_spec'),
                             'HD cinematic has no reproducible, pinned scene plan')
        from tools.cinematics import scene_spec
        return scene_spec

    def test_scene_is_native_1440p_and_reuses_only_verified_shipped_meshes(self):
        module = self.spec()
        plan = module.build_plan(ROOT)
        self.assertEqual(plan['resolution'], [2560, 1440])
        self.assertEqual(plan['fps'], 24)
        self.assertEqual(plan['source_seconds'], 16)
        self.assertEqual(plan['scope'], 'offline menu movie only; no gameplay or runtime renderer changes')
        self.assertGreaterEqual(len(plan['ships']), 5)
        self.assertEqual({row['faction'] for row in plan['ships']}, {'imperial', 'rebel'})
        for row in plan['ships']:
            path = ROOT / row['runtime_path']
            self.assertTrue(path.resolve().is_relative_to(ROOT / 'visual_packs'))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['runtime_sha256'])
            self.assertTrue(row['binding'].startswith(row['faction'] + ':'))
            self.assertGreater(row['length'], 0)
            self.assertGreater(row['triangle_count'], 1000)
            self.assertGreater(row['scale'], 0)
        pins = {row['runtime_path']: row['runtime_sha256'] for row in plan['ships']}
        module.build_plan(ROOT)
        self.assertTrue(all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p,h in pins.items()))

    def test_scene_uses_the_same_redesigned_ships_as_normal_game_defaults(self):
        import json
        from render import menus
        from render.asset_registry import AssetResolver
        plan = self.spec().build_plan(ROOT)
        packs = ROOT / 'visual_packs'
        resolver = AssetResolver(ROOT)
        resolver.activate_packs([packs / name / 'visual-pack.json'
                                 for name in menus.DEFAULT_SETTINGS['visual_packs']], pack_root=packs)
        for row in plan['ships']:
            with self.subTest(binding=row['binding']):
                selected = resolver.resolve(row['binding'])
                self.assertEqual(row['revision'], selected.revision,
                                 'Movie still uses the old core hull, not the shipped redesign')
                self.assertEqual(row['asset'], selected.asset)
                self.assertTrue((ROOT / row['runtime_path']).is_relative_to(packs))

    def test_rejected_shipped_pack_refuses_to_bake_a_fallback_movie(self):
        from unittest.mock import patch
        from render import menus
        with patch.dict(menus.DEFAULT_SETTINGS, visual_packs=['missing-shipped-pack']):
            with self.assertRaisesRegex(ValueError, 'shipped visual pack rejected'):
                self.spec().build_plan(ROOT)

    def test_blender_input_accepts_pinned_shipped_pack_meshes_but_rejects_stale_bytes(self):
        from copy import deepcopy
        from tools.cinematics import blender_scene
        loader = getattr(blender_scene, 'load_payloads', None)
        self.assertTrue(callable(loader), 'Blender needs shared read-only input validation for shipped packs')
        plan = self.spec().build_plan(ROOT)
        self.assertEqual(set(loader(plan, ROOT)), {r['runtime_path'] for r in plan['ships']})
        stale = deepcopy(plan)
        stale['ships'][0]['runtime_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'differs'):
            loader(stale, ROOT)
        escaped = deepcopy(plan)
        escaped['ships'][0]['runtime_path'] = '../outside.mesh.json'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            loader(escaped, ROOT)

    def test_camera_and_ship_motion_are_periodic_without_state_or_random_side_effects(self):
        module = self.spec()
        plan = module.build_plan(ROOT)
        for func, args in [(module.camera_pose, ()),
                           (module.ship_pose, (plan['ships'][0],))]:
            start = func(*args, 0)
            end = func(*args, 16)
            for key in start:
                for a,b in zip(start[key],end[key]):
                    self.assertAlmostEqual(a,b,places=9)
            self.assertEqual(start,func(*args,0))

    def test_existing_movie_is_not_written_by_planning(self):
        module = self.spec()
        movie = ROOT / 'assets/menu/battle.zip'
        before = hashlib.sha256(movie.read_bytes()).digest()
        module.build_plan(ROOT)
        self.assertEqual(hashlib.sha256(movie.read_bytes()).digest(), before)


if __name__ == '__main__':
    unittest.main()
