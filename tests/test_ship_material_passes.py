"""Real-driver material-role regression; run with a real SDL/OpenGL display."""
import os
import unittest
from unittest.mock import patch

import pygame
from OpenGL import GL


@unittest.skipIf(os.environ.get('SDL_VIDEODRIVER') == 'dummy', 'requires real OpenGL')
class ShipMaterialPassTests(unittest.TestCase):
    def setUp(self):
        from render.asset_selection import configure
        configure({"model_preview": True})
        self.addCleanup(configure, {})
        from game.core.manager import GameManager
        from game.core.state import PlayerState
        from game.core.vectors import Vec3
        from render.camera import Camera
        from render.renderer import Renderer
        self.owns_display = not pygame.display.get_init()
        if self.owns_display:
            pygame.display.init()
            self.addCleanup(pygame.display.quit)
            pygame.display.set_mode((640, 480), pygame.OPENGL | pygame.DOUBLEBUF)
        self.gm = GameManager()
        self.st = self.gm.state
        self.st.players = {0: PlayerState(0, faction='rebel', team=0, is_ai=False,
                                         color=(.35, .65, 1.))}
        self.capital = self.gm.factory.spawn_ship('rebel_battleship', 0, Vec3(0, 0, 0))
        self.escort = self.gm.factory.spawn_ship('rebel_frigate', 0, Vec3(0, 0, 350))
        self.sibling = self.gm.factory.spawn_ship('rebel_corvette', 0, Vec3(300, 0, 0))
        self.yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(0, 0, -600))
        self.st.grid.rebuild(self.st.entities)
        self.gm.visibility.update()
        self.cam = Camera(640, 480)
        self.cam.target = [0, 0, 0]
        self.cam.distance, self.cam.yaw, self.cam.pitch = 1100., 55., 35.
        self.r = Renderer(self.st, self.cam)
        self.addCleanup(self.r.close)
        self.r.diff_render, self.r.time = True, 3.
        self.assertTrue(self.r.materials.available, self.r.materials.error)

    def test_legacy_selection_never_claims_authored_material_treatment(self):
        from render.asset_selection import configure
        from render.renderer import Renderer
        self.r.close()
        configure({})
        self.r = Renderer(self.st, self.cam)
        self.addCleanup(self.r.close)
        self.r.diff_render, self.r.time = True, 3.
        with patch.object(self.r.materials, 'hull_pass', wraps=self.r.materials.hull_pass) as calls:
            self.r.draw(0., set())
        self.assertTrue(calls.call_args_list)
        self.assertFalse(any(len(call.args) > 1 and call.args[1]
                             for call in calls.call_args_list),
                         'hardcoded identity still selects authored treatment in legacy mode')

    def test_authored_surface_removes_hatch_without_changing_default_material(self):
        """Rasterize the actual hull shader; baseline has identical noisy panels."""
        import numpy as np
        materials = self.r.materials
        GL.glViewport(0, 0, 256, 256)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(-40, 40, -40, 40, 1, 100)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslatef(0, 0, -50)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, (0, 0, 100, 1))
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_DEPTH_TEST)
        def pixels(authored):
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            with materials.use('hull', materialPass=0.):
                location = GL.glGetUniformLocation(materials.programs['hull'], 'authoredSurface')
                if location >= 0:
                    GL.glUniform1f(location, float(authored))
                GL.glColor3f(.35, .65, 1.)
                GL.glNormal3f(0, 0, 1)
                GL.glBegin(GL.GL_QUADS)
                for x, y in ((-40, -40), (40, -40), (40, 40), (-40, 40)):
                    GL.glVertex3f(x, y, 0)
                GL.glEnd()
            GL.glFinish()
            return np.frombuffer(GL.glReadPixels(0, 0, 256, 256, GL.GL_RGB, GL.GL_UNSIGNED_BYTE),
                                 np.uint8).reshape(256, 256, 3).astype(float)
        default = pixels(False)
        authored = pixels(True)
        repeated_default = pixels(False)
        self.assertTrue(np.array_equal(default, repeated_default), 'authored treatment leaked into sibling')
        def edge_energy(a):
            return float(np.abs(np.diff(a[16:-16, 16:-16], axis=1)).mean())
        self.assertLess(edge_energy(authored), edge_energy(default) * .5,
                        'authored armor must not inherit the catalogue hatch')
        self.assertEqual(GL.glGetError(), GL.GL_NO_ERROR)

    def test_cached_roles_use_their_actual_shader_and_emissive_state(self):
        self._assert_cached_role_state(mixed_legacy=False)

    def test_cached_roles_preserve_explicit_unselected_sibling(self):
        # The stock preview catalogue now authors the corvette too. Preserve the
        # mixed-mode regression with explicit temporary metadata, not stale IDs.
        import json
        from test_asset_registry import isolated_assets
        from render.asset_selection import configure, mesh_for
        from render.renderer import Renderer
        root = isolated_assets(self)
        registry_path = root / 'assets/models/registry.json'
        registry = json.loads(registry_path.read_text())
        row = next(row for row in registry['bindings']
                   if row['binding'] == 'rebel:corvette')
        # Procedural rows retain their declared manifest identity in this schema.
        row['status'] = 'procedural_legacy'
        registry_path.write_text(json.dumps(registry), encoding='utf-8')
        self.r.close()
        configure({'model_preview': True}, asset_root=root)
        self.assertIsNone(mesh_for('rebel:corvette'))
        self.assertIsNotNone(mesh_for('rebel:frigate'))
        self.r = Renderer(self.st, self.cam)
        self.addCleanup(self.r.close)
        self.r.diff_render, self.r.time = True, 3.
        self._assert_cached_role_state(mixed_legacy=True)

    def _assert_cached_role_state(self, mixed_legacy):
        from render import renderer as module
        from game.benchmark import state_hash
        seen = []
        role = [None]
        original_batch = self.r._draw_ship_role_batch
        original_call = module.glCallList
        def batch(name, *args, **kwargs):
            role[0] = name
            try:
                return original_batch(name, *args, **kwargs)
            finally:
                role[0] = None
        capital_lists = {self.r._ship_display_list('rebel:battleship' + suffix)
                         for suffix in ('', '_dark', '_trim')}
        authored_lists = capital_lists | {
            self.r._ship_display_list('rebel:frigate' + suffix)
            for suffix in ('', '_dark', '_trim')} | {
            self.r._station_detail_list('shipyard', name, 'rebel')
            for name in ('base', 'dark', 'trim')}
        sibling_lists = {self.r._ship_display_list('rebel:corvette' + suffix)
                         for suffix in ('', '_dark', '_trim')}
        self.assertTrue(sibling_lists.isdisjoint(authored_lists))
        if not mixed_legacy:
            authored_lists |= sibling_lists
        capital_accent = self.r._ship_display_list('rebel:battleship_accent')
        surface_seen, paint_seen = [], []
        def call(lst):
            if role[0] in ('base', 'dark', 'trim'):
                location = self.r.materials.locations['hull', 'authoredSurface']
                import ctypes
                value = ctypes.c_float()
                GL.glGetUniformfv(self.r.materials.programs['hull'], location, value)
                surface_seen.append((value.value, float(lst in authored_lists)))
            if role[0] == 'accent' and lst == capital_accent:
                paint_seen.append(tuple(float(v) for v in GL.glGetFloatv(GL.GL_CURRENT_COLOR)[:3]))
            if role[0] is not None:
                seen.append((role[0], int(GL.glGetIntegerv(GL.GL_CURRENT_PROGRAM)),
                             bool(GL.glIsEnabled(GL.GL_LIGHTING)),
                             bool(GL.glIsEnabled(GL.GL_TEXTURE_2D))))
            return original_call(lst)
        before = state_hash(self.st)
        with patch.object(self.r, '_draw_ship_role_batch', side_effect=batch), \
             patch.object(module, 'glCallList', side_effect=call):
            self.r.draw(0., set())
        self.assertEqual(before, state_hash(self.st))
        self.assertEqual(GL.glGetError(), GL.GL_NO_ERROR)
        self.assertEqual({x[0] for x in seen}, {'base', 'dark', 'trim', 'accent', 'lit', 'cool'})
        failures = []
        for name, program, lighting, texture in seen:
            if name in ('base', 'dark', 'trim'):
                expected = (self.r.materials.programs['hull'], True, True)
            elif name == 'accent':
                expected = (0, True, False)
            else:
                expected = (0, False, False)
            if (program, lighting, texture) != expected:
                failures.append((name, (program, lighting, texture), expected))
        self.assertEqual(failures, [], 'actual GL role state differs: observed vs expected')
        self.assertTrue(surface_seen)
        self.assertEqual({expected for _, expected in surface_seen},
                         {0.0, 1.0} if mixed_legacy else {1.0},
                         'must exercise the declared full or mixed catalogue')
        self.assertTrue(any(expected == float(not mixed_legacy)
                            for _, expected in surface_seen))
        self.assertTrue(all(actual == expected for actual, expected in surface_seen), surface_seen)
        self.assertEqual(len(paint_seen), 1)
        for actual, expected in zip(paint_seen[0], self.st.players[0].color):
            self.assertAlmostEqual(actual, expected, places=6)


if __name__ == '__main__':
    unittest.main()
