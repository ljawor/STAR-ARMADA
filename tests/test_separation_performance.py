"""Exact broad-phase/order preservation against the pre-change oracle."""
import json
import random
import unittest
from unittest.mock import patch
from game.benchmark import make_scene
from game.core.state import GameState
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.systems.separation import SeparationSystem
from reference_separation import ReferenceSeparationSystem


class CountingEntities(dict):
    def __init__(self, values):
        super().__init__(values)
        self.lookups = 0

    def get(self, *args):
        self.lookups += 1
        return super().get(*args)


class SeparationPerformanceTests(unittest.TestCase):
    def test_dense_scene_filters_irrelevant_pairs(self):
        gm = make_scene(200)
        gm.state.entities = CountingEntities(gm.state.entities)
        gm.separation.update(1 / 30)
        self.assertLess(gm.state.entities.lookups, 7000,
                        'coarse cells still examine every irrelevant ship pair')

    def test_live_sequential_pushes_match_reference_exactly(self):
        gm = make_scene(80)
        rng = random.Random(513)
        for i, entity in enumerate(gm.state.entities.values()):
            if entity.is_ship:
                entity.pos = Vec3(rng.uniform(-410, 410), rng.uniform(-80, 80),
                                  rng.uniform(-410, 410))
                entity.radius = (10, 34, 95, 210)[i % 4]
                entity.is_squadron = i % 5 == 0
        gm.factory.spawn_station('defense_platform', 0, Vec3(399, 0, 63))
        gm.factory.spawn_planet({'id': 'test_planet', 'pos': [-200, 0, -200],
                                'radius': 100, 'type': 'rocky'})
        gm.state.grid.rebuild(gm.state.entities)
        reference = GameManager(GameState.from_dict(gm.state.to_dict(precise=True)))
        for dt in (1 / 30, 2.0, 8.0):
            gm.state.grid.rebuild(gm.state.entities)
            reference.state.grid.rebuild(reference.state.entities)
            gm.separation.update(dt)
            ReferenceSeparationSystem(reference.state).update(dt)
            self.assertEqual(json.dumps(gm.state.to_dict(precise=True), sort_keys=True),
                             json.dumps(reference.state.to_dict(precise=True), sort_keys=True))

    def test_complete_manager_ticks_match_reference(self):
        current, reference = make_scene(80), make_scene(80)
        for tick in range(25):
            current.step(1 / 30)
            with patch.object(SeparationSystem, 'update', ReferenceSeparationSystem.update):
                reference.step(1 / 30)
            self.assertEqual(json.dumps(current.state.to_dict(precise=True), sort_keys=True),
                             json.dumps(reference.state.to_dict(precise=True), sort_keys=True),
                             f'precise manager state differs at {tick + 1}')


if __name__ == '__main__':
    unittest.main()
