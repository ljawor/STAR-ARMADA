"""Pure geometry/material contracts; no GL context is created here."""
import importlib.util
import unittest
import numpy as np


class ArmorMeshTests(unittest.TestCase):
    def test_beveled_loft_is_closed_outward_and_not_box_shaped(self):
        self.assertIsNotNone(importlib.util.find_spec('render.fleet_geometry'),
                             'beveled capital hull geometry is missing')
        from render.fleet_geometry import armor_loft
        triangles = armor_loft(((-75, 19, 10, -10), (35, 19, 10, -10),
                                (95, 3, 5, -5)), bevel=3)
        edges = {}
        for normal, verts in triangles:
            a, b, c = np.array(verts)
            cross = np.cross(b-a, c-a)
            self.assertGreater(np.linalg.norm(cross), 1e-6)
            self.assertAlmostEqual(np.linalg.norm(normal), 1, places=6)
            self.assertGreater(np.dot(cross, normal), 0)
            for x,y in ((a,b),(b,c),(c,a)):
                edge = tuple(sorted((tuple(x), tuple(y))))
                edges[edge] = edges.get(edge, 0) + 1
        self.assertTrue(all(v == 2 for v in edges.values()), 'mesh has holes')
        normals = np.array([n for n, _ in triangles])
        self.assertTrue(np.any(np.count_nonzero(np.abs(normals) > .01, axis=1) > 1),
                        'armor must have bevel facets, not only box faces')


    def test_actual_capital_hulls_have_outward_winding_and_paired_edges(self):
        from render.renderer import Renderer
        from render.fleet_geometry import armor_loft
        from unittest.mock import Mock
        for shape in ('cruiser', 'dagger'):
            renderer = Renderer.__new__(Renderer)
            renderer._lit_box = Mock()
            renderer._armor_loft = Mock()
            renderer._emit_hull(shape, 'base')
            self.assertGreaterEqual(renderer._armor_loft.call_count, 2)
            for args, kwargs in renderer._armor_loft.call_args_list:
                tris = armor_loft(*args, **kwargs)
                directed = {}
                volume = 0.0
                for normal, vertices in tris:
                    a, b, c = np.array(vertices)
                    volume += np.dot(a, np.cross(b, c)) / 6.0
                    for x, y in ((a, b), (b, c), (c, a)):
                        key = (tuple(x), tuple(y))
                        directed[key] = directed.get(key, 0) + 1
                self.assertGreater(volume, 0, f'{shape} hull points inward')
                for (a, b), count in directed.items():
                    self.assertEqual(count, directed.get((b, a), 0),
                                     f'{shape} edges have inconsistent winding')


class SpaceTextureTests(unittest.TestCase):
    def test_planet_texture_seam_is_closed_and_clouds_are_resolved(self):
        from render import textures
        import pygame
        a = pygame.surfarray.array3d(textures.planet_texture('temperate', 128, 9))
        self.assertTrue(np.array_equal(a[0], a[-1]), 'planet meridian is open')
        self.assertGreater(len(np.unique(a.reshape(-1, 3), axis=0)), 2000,
                           'planet needs coast/terrain/cloud variation')

    def test_planet_surface_is_cached_per_stable_identity(self):
        from render.renderer import Renderer
        from types import SimpleNamespace
        from unittest.mock import patch
        r = Renderer.__new__(Renderer)
        r._planet_tex_cache = {}
        self.assertTrue(hasattr(r, '_planet_texture_for'), 'planet cache helper missing')
        e = SimpleNamespace(data_id='temperate', name_override='Aster')
        with patch('render.renderer.tex.planet_texture', return_value='surface') as build, \
             patch('render.renderer.tex.surface_to_texture', return_value=123):
            self.assertEqual(r._planet_texture_for(e), 123)
            self.assertEqual(r._planet_texture_for(e), 123)
            self.assertEqual(build.call_count, 1, 'surface regenerated every frame')
            e.name_override = 'Other'
            r._planet_texture_for(e)
            self.assertEqual(build.call_count, 2, 'different worlds share a texture')

    def test_deep_space_is_seeded_seamless_dim_and_layered(self):
        from render import textures
        self.assertTrue(hasattr(textures, 'deep_space_texture'), 'deep-space backdrop missing')
        import pygame
        rng = np.random.get_state()
        a = pygame.surfarray.array3d(textures.deep_space_texture(128, 17))
        b = pygame.surfarray.array3d(textures.deep_space_texture(128, 17))
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.array_equal(a[0], a[-1]), 'longitude seam')
        self.assertLess(float(a.mean()), 35, 'background competes with ships')
        self.assertGreater(float(a.std()), 3, 'background is a flat clear color')
        self.assertTrue(np.array_equal(rng[1], np.random.get_state()[1]))


if __name__ == '__main__':
    unittest.main()
