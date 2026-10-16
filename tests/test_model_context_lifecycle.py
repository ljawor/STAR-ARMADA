"""Real-context ownership for session-bound visual selection."""
import unittest
from unittest.mock import patch

import pygame
from OpenGL import GL
import game.core
from game.core.manager import GameManager
from game.data.store import DataStore
from render import asset_selection
from render.camera import Camera
from render.renderer import Renderer


class ModelContextLifecycleTests(unittest.TestCase):
    def test_display_lists_are_content_keyed_for_additive_assets(self):
        from render.asset_registry import AssetResolver
        from render import asset_selection as selection
        from test_asset_registry import PackTests, ROOT
        path = PackTests.pack(self, 'test:addon', 'raiders:scout', adds=True)
        resolver = AssetResolver(ROOT, gameplay_entities={'gameplay:raiders': {'raiders:scout'}})
        resolver.activate_packs([path])
        owned_display = not pygame.display.get_init()
        pygame.display.init()
        renderer = None
        try:
            pygame.display.set_mode((320, 240), pygame.OPENGL | pygame.DOUBLEBUF)
            gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
            with patch.object(selection, '_resolver', resolver):
                renderer = Renderer(gm.state, Camera(320, 240))
                with patch.object(renderer, '_emit_detail_mesh', wraps=renderer._emit_detail_mesh) as emit:
                    first = renderer._ship_display_list('raiders:scout')
                    self.assertEqual(first, renderer._ship_display_list('raiders:scout'))
                    self.assertEqual(len(emit.call_args_list), 6)
                    self.assertEqual(sum(len(call.args[0]) for call in emit.call_args_list), 1)
                revision = resolver.resolve('raiders:scout').revision
                self.assertTrue(any(isinstance(key, tuple) and revision in key
                                    for key in renderer.ship_lists),
                                'GPU cache keyed only by entity type instead of revision')
        finally:
            if renderer is not None:
                renderer.close()
            if owned_display:
                pygame.display.quit()

    def test_real_renderer_blocks_switch_until_teardown_and_context_recreation(self):
        asset_selection.configure({})
        owned_display = not pygame.display.get_init()
        previous_store = DataStore._instance
        renderer = None
        pygame.display.init()
        try:
            pygame.display.set_mode((320, 240), pygame.OPENGL | pygame.DOUBLEBUF)
            gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
            renderer = Renderer(gm.state, Camera(320, 240))
            list_id = renderer._unit_sphere_tex
            self.assertTrue(GL.glIsList(list_id))
            with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                asset_selection.configure({})
            renderer.close()
            renderer.close()
            self.assertFalse(GL.glIsList(list_id))
            renderer = None
            asset_selection.configure({})
            pygame.display.set_mode((320, 240), pygame.OPENGL | pygame.DOUBLEBUF)
            renderer = Renderer(gm.state, Camera(320, 240))
            self.assertTrue(GL.glIsList(renderer._unit_sphere_tex))
            renderer.close()
            renderer = None
            asset_selection.configure({})
            with patch.object(Renderer, '_initialize', side_effect=RuntimeError('injected init')):
                with self.assertRaisesRegex(RuntimeError, 'injected init'):
                    Renderer(gm.state, Camera(320, 240))
            # Constructor rollback must release selection ownership as well as GL.
            asset_selection.configure({})
        finally:
            if renderer is not None:
                renderer.close()
            DataStore._instance = previous_store
            if owned_display:
                pygame.display.quit()
