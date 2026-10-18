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
    def test_registered_catalogue_lists_close_and_rebuild_across_preview_cycles(self):
        """Actual 102-revision GPU closure, not a pixel/LOD acceptance claim."""
        # set_mode replaces even an initialized caller display/context. This
        # native probe must run at an exclusive display AND renderer boundary.
        if pygame.display.get_init() or asset_selection._renderer_owners:
            self.skipTest('Catalogue lifecycle probe requires an isolated display/renderer boundary')
        import json
        from pathlib import Path
        from game.benchmark import state_hash
        rows = [row for row in json.loads((Path(__file__).resolve().parents[1] /
                'assets/models/registry.json').read_text())['bindings']
                if row['status'] == 'core']
        self.assertEqual(len(rows), 102)
        previous_store = DataStore._instance
        previous_selection = asset_selection._selection
        previous_resolver = asset_selection._resolver
        previous_generation = asset_selection._generation
        owned_display = not pygame.display.get_init()
        renderer = None
        pygame.display.init()
        try:
            pygame.display.set_mode((320, 240), pygame.OPENGL | pygame.DOUBLEBUF)
            gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
            initial = state_hash(gm.state)
            for preview in (True, False, True):
                asset_selection.configure({'model_preview': preview})
                renderer = Renderer(gm.state, Camera(320, 240))
                self.assertTrue(renderer.materials.available, renderer.materials.error)
                if preview:
                    seen = set()
                    for row in rows:
                        binding = row['binding']
                        self.assertIsNotNone(asset_selection.mesh_for(binding), binding)
                        if row['category'] == 'environment_prop':
                            first = renderer._asteroid_prop_lists()
                            self.assertTrue(first)
                            self.assertEqual(first, renderer._asteroid_prop_lists())
                        elif row['category'] in ('station', 'satellite', 'planet_installation'):
                            faction, data_id = binding.split(':')
                            for role in ('base', 'dark', 'trim', 'accent', 'lit', 'cool'):
                                first = renderer._station_detail_list(data_id, role, faction)
                                self.assertEqual(first, renderer._station_detail_list(data_id, role, faction))
                                self.assertTrue(GL.glIsList(first), (binding, role))
                        else:
                            for suffix in ('', '_dark', '_trim', '_accent', '_lit', '_cool'):
                                first = renderer._ship_display_list(binding + suffix)
                                self.assertEqual(first, renderer._ship_display_list(binding + suffix))
                                self.assertTrue(GL.glIsList(first), (binding, suffix))
                        seen.add(binding)
                    self.assertEqual(seen, {row['binding'] for row in rows})
                else:
                    self.assertIsNone(asset_selection.mesh_for('imperial:shipyard'))
                    self.assertIsNone(renderer._asteroid_prop_lists())
                    self.assertTrue(GL.glIsList(renderer._ship_display_list('rebel:frigate')))
                    self.assertTrue(GL.glIsList(renderer._station_detail_list('shipyard', 'base', 'imperial')))
                owned_lists = set(renderer.ship_lists.values())
                self.assertTrue(owned_lists)
                with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                    asset_selection.configure({'model_preview': not preview})
                self.assertEqual(GL.glGetError(), GL.GL_NO_ERROR)
                renderer.close()
                renderer = None
                self.assertFalse(any(GL.glIsList(lst) for lst in owned_lists))
                self.assertEqual(state_hash(gm.state), initial)
        finally:
            try:
                if renderer is not None:
                    renderer.close()
            finally:
                try:
                    # Restore the actual resolver (including external packs), not
                    # configure({}), which silently replaces a caller's preview.
                    current_resolver = asset_selection._resolver
                    asset_selection._selection = previous_selection
                    asset_selection._resolver = previous_resolver
                    asset_selection._generation = previous_generation
                    if current_resolver is not None and current_resolver is not previous_resolver:
                        current_resolver.cache_clear()
                    if previous_resolver is not None:
                        previous_resolver.cache_clear()
                    # Restoring a generation is safe only with derived data gone.
                    asset_selection.invalidate_geometry_helpers()
                finally:
                    DataStore._instance = previous_store
                    if owned_display:
                        pygame.display.quit()

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
