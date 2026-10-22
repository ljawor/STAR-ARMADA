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

    def test_scene_is_native_1440p_and_reuses_only_verified_core_meshes(self):
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
            self.assertTrue(path.resolve().is_relative_to(ROOT / 'assets/models'))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['runtime_sha256'])
            self.assertTrue(row['binding'].startswith(row['faction'] + ':'))
            self.assertGreater(row['length'], 0)
            self.assertGreater(row['triangle_count'], 1000)
            self.assertGreater(row['scale'], 0)
        pins = {row['runtime_path']: row['runtime_sha256'] for row in plan['ships']}
        module.build_plan(ROOT)
        self.assertTrue(all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p,h in pins.items()))

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
