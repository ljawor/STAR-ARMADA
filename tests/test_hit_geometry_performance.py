"""Exact legacy geometry plus a deterministic repeated-trigonometry budget."""
import hashlib
import json
import unittest
from unittest.mock import patch

from render import hit_effects as hits


def specimens():
    return [dict(kind=kind, t=t, normal=n, pos=(10.25, -7., 13.),
                 center=(1., 2., 3.), size=7.3, radius=92.5, seed=37)
            for kind in ('shield_hit', 'impact', 'unknown')
            for t in (0., .025, .026, .084, .085, .2, .419, .42, .549, .55)
            for n in ((0., 0., 1.), (1., 2., 3.), (0., 1., 0.), (0., 0., 0.))]


class TestHitGeometryPerformance(unittest.TestCase):
    def test_geometry_colors_and_vertex_order_are_exact_legacy_values(self):
        meshes = [hits.hit_geometry(fx, radius=103.2,
                  billboard_basis=((.8, .2, .1), (.1, .9, .3)), visual_size=8.7)
                  for fx in specimens()]
        digest = hashlib.sha256(json.dumps(meshes, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, '44a60d68a1c6dd385d60a438a69aefe9d00ae01eb555b9b615625707057ad643')

    def test_shield_does_not_repeat_trigonometry_for_each_coordinate(self):
        with patch.object(hits.math, 'sin', wraps=hits.math.sin) as sin, \
             patch.object(hits.math, 'cos', wraps=hits.math.cos) as cos:
            hits.hit_geometry(specimens()[20])
        self.assertLessEqual(sin.call_count + cos.call_count, 450)


if __name__ == '__main__':
    unittest.main()
