"""Real-context constructor rollback: faults occur after driver allocation."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pygame
from OpenGL import GL
import render.renderer as module
from render.camera import Camera
from game.core.manager import GameManager
from game.data.store import DataStore
from game.net.lan import precise_checksum


class ConstructorCleanupTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import render.menus as menus
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        scopes = ExitStack()
        self.addCleanup(scopes.close)
        for name, value in dict(USER_DIR=directory.name,
                                SAVES_DIR=str(Path(directory.name) / 'saves'),
                                SETTINGS_PATH=str(Path(directory.name) / 'settings.json'),
                                CAMPAIGN_PATH=str(Path(directory.name) / 'campaign.json'),
                                BALANCE_PATH=str(Path(directory.name) / 'balance.json')).items():
            scopes.enter_context(patch.object(menus, name, value))
        self.display_owned = not pygame.display.get_init()
        pygame.display.init()
        pygame.display.set_mode((320, 240), pygame.OPENGL | pygame.DOUBLEBUF)
        self.addCleanup(self.release_display)
        store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', store)
        self.manager = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        self.old = module.Renderer(self.manager.state, Camera(320, 240))
        self.addCleanup(self.old.close)
        self.assertTrue(self.old.materials.available, 'real GLSL context required')
        self.digest = precise_checksum(self.manager)

    def release_display(self):
        if self.display_owned:
            pygame.display.quit()

    def frame(self):
        self.old.diff_render = True
        GL.glViewport(0, 0, 320, 240)
        self.old.draw(0, set())
        GL.glFinish()
        return bytes(GL.glReadPixels(0, 0, 320, 240, GL.GL_RGB, GL.GL_UNSIGNED_BYTE))

    def fault(self, target, name, after=None, construct=None, cleanup_failure=False):
        """Track actual allocations, then throw the same exception at a seam."""
        allocations = {'programs': [], 'shaders': [], 'lists': [], 'textures': []}
        deleted_lists = []
        original_error = RuntimeError('after allocation: ' + name)
        before = self.frame()
        with ExitStack() as stack:
            if cleanup_failure:
                end = module.glEnd
                def failed_end():
                    end()
                    raise ValueError('geometry cleanup also failed')
                stack.enter_context(patch.object(module, 'glEnd', new=failed_end))
            for fn, kind in [('glCreateProgram', 'programs'), ('glCreateShader', 'shaders'),
                             ('glGenLists', 'lists'), ('glGenTextures', 'textures')]:
                original = getattr(GL, fn)
                def track(*args, original=original, kind=kind, **kwargs):
                    value = original(*args, **kwargs)
                    allocations[kind].append(int(value))
                    return value
                stack.enter_context(patch.object(GL, fn, side_effect=track))
            delete = GL.glDeleteLists
            def record_delete(value, count):
                deleted_lists.extend(range(int(value), int(value) + count))
                return delete(value, count)
            stack.enter_context(patch.object(GL, 'glDeleteLists', side_effect=record_delete))
            original = getattr(target, name)
            def fail(*args, **kwargs):
                if after:
                    original(*args, **kwargs)
                raise original_error
            stack.enter_context(patch.object(target, name, new=fail))
            with self.assertRaises(Exception) as caught:
                if construct is None:
                    module.Renderer(self.manager.state, Camera(320, 240))
                else:
                    construct()
            self.assertIs(caught.exception, original_error)
        self.assertTrue(allocations['programs'], 'fault must follow shader allocations')
        for kind, predicate in [('programs', GL.glIsProgram), ('shaders', GL.glIsShader),
                                ('lists', GL.glIsList), ('textures', GL.glIsTexture)]:
            self.assertEqual([value for value in allocations[kind] if predicate(value)], [],
                             kind + ' leaked at ' + name)
        self.assertCountEqual(deleted_lists, allocations['lists'], 'reserved list IDs must be released')
        self.assertTrue(all(GL.glIsProgram(p) for p in self.old.materials.programs.values()))
        self.assertTrue(GL.glIsList(self.old._unit_sphere_tex))
        self.assertEqual(precise_checksum(self.manager), self.digest)
        self.assertEqual(int(GL.glGetIntegerv(GL.GL_LIST_INDEX)), 0)
        self.assertEqual(GL.glGetError(), GL.GL_NO_ERROR)
        self.assertEqual(self.frame(), before, 'active renderer framebuffer changed')

    def test_real_shader_stage_failures_keep_fixed_pipeline_fallback_leak_free(self):
        # FleetMaterials owns shader compilation/linking and intentionally falls
        # back rather than rejecting Renderer. Exercise every allocated stage.
        for seam, occurrence in [('glShaderSource', 1), ('glShaderSource', 2),
                                 ('glShaderSource', 3), ('glShaderSource', 4),
                                 ('glLinkProgram', 1), ('glLinkProgram', 2),
                                 ('glGetUniformLocation', 1)]:
            with self.subTest(seam=seam, occurrence=occurrence), ExitStack() as stack:
                shaders, programs = [], []
                for name, owned in [('glCreateShader', shaders), ('glCreateProgram', programs)]:
                    allocate = getattr(GL, name)
                    def track(*args, allocate=allocate, owned=owned):
                        value = allocate(*args)
                        owned.append(int(value))
                        return value
                    stack.enter_context(patch.object(GL, name, new=track))
                call = getattr(GL, seam)
                calls = []
                error = RuntimeError('real GL stage fault')
                def fail_after(*args):
                    result = call(*args)
                    calls.append(args)
                    if len(calls) == occurrence:
                        raise error
                    return result
                stack.enter_context(patch.object(GL, seam, new=fail_after))
                with self.assertLogs('render.fleet_materials', level='WARNING'):
                    candidate = module.Renderer(self.manager.state, Camera(320, 240))
                try:
                    self.assertEqual(len(calls), occurrence)
                    self.assertTrue(shaders)
                    self.assertFalse(candidate.materials.available)
                    self.assertEqual(candidate.materials.error, str(error))
                    self.assertFalse(any(GL.glIsShader(s) for s in shaders))
                    self.assertFalse(any(GL.glIsProgram(p) for p in programs))
                    self.assertTrue(GL.glIsList(candidate._unit_sphere_tex))
                finally:
                    candidate.close()
                self.assertEqual(precise_checksum(self.manager), self.digest)
                self.assertTrue(all(GL.glIsProgram(p) for p in self.old.materials.programs.values()))

    def test_real_installer_partial_constructor_failure_keeps_live_graph(self):
        import ast
        from pathlib import Path
        from render.hud import HUD
        from render.input import InputController
        from render.audio import Audio
        from game.net.replay import MatchRecording
        from test_lan_recovery_handoff import restored
        font_owned = not pygame.font.get_init()
        pygame.font.init()
        if font_owned:
            def close_font():
                from render.clean_classic import font
                font.cache_clear()
                pygame.font.quit()
            self.addCleanup(close_font)
        hud = HUD(320, 240, self.manager.state)
        self.addCleanup(hud.close)
        hud.set_camera_ref(self.old.camera)
        controller = InputController(self.manager.state, self.old.camera, hud, None)
        audio = Audio(self.manager.state, muted=True)
        self.addCleanup(audio.cleanup)
        recording = MatchRecording(self.manager, mode='lan')
        self.addCleanup(recording.close)
        source = Path(__file__).resolve().parents[1] / 'main.py'
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'install_recovered_manager')
        ns = dict(gm=self.manager, state=self.manager.state, camera=self.old.camera,
                  renderer=self.old, hud=hud, inputc=controller, audio=audio,
                  recording=recording, net_session=object(), local_player=0,
                  DataStore=DataStore, W=320, H=240, SETTINGS={}, accumulator=0,
                  last_autosave=0, mission_def=None, Camera=Camera,
                  Renderer=module.Renderer, HUD=HUD, InputController=InputController,
                  _AppGlue=lambda: object())
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), ns)
        candidate = restored(self.manager)
        fields = ('gm', 'state', 'camera', 'renderer', 'hud', 'inputc', 'audio', 'recording')
        before = tuple(ns[name] for name in fields)
        self.fault(module.Renderer, '_reset_frame_cache',
                   construct=lambda: ns['install_recovered_manager'](candidate))
        self.assertEqual(tuple(ns[name] for name in fields), before)
        self.assertIs(DataStore._instance, self.manager.ds)
        self.assertIs(recording.gm, self.manager)
        self.assertIs(audio.state, self.manager.state)
        self.assertIs(self.old.camera._scene, self.manager.state)

    def test_program_only_stages_release_allocations(self):
        for target, name, after in [(module, 'make_starfield', False),
                                    (Camera, 'bind_scene', True),
                                    (module, 'glNewList', False)]:
            with self.subTest(stage=name):
                self.fault(target, name, after=after)

    def test_normal_close_releases_real_lazy_textures_and_lists_once(self):
        self.frame()
        renderer = self.old
        lists = set(renderer.ship_lists.values()) | {renderer._star_list, renderer._unit_sphere_tex}
        textures = set(renderer._planet_tex_cache.values()) | {
            renderer._hull_tex, renderer._space_tex, renderer._star_tex,
            renderer._nebula_tex, renderer.fog.texture}
        lists.discard(None)
        textures.discard(None)
        programs = list(renderer.materials.programs.values())
        self.assertTrue(textures, 'production draw must allocate lazy textures')
        self.assertTrue(all(GL.glIsTexture(t) for t in textures))
        with patch.object(GL, 'glDeleteLists', wraps=GL.glDeleteLists) as delete_lists, \
             patch.object(GL, 'glDeleteTextures', wraps=GL.glDeleteTextures) as delete_textures, \
             patch.object(GL, 'glDeleteProgram', wraps=GL.glDeleteProgram) as delete_programs:
            renderer.close()
            counts = (delete_lists.call_count, delete_textures.call_count, delete_programs.call_count)
            renderer.close()
            self.assertEqual(counts, (delete_lists.call_count, delete_textures.call_count, delete_programs.call_count))
        self.assertFalse(any(GL.glIsList(x) for x in lists))
        self.assertFalse(any(GL.glIsTexture(x) for x in textures))
        self.assertFalse(any(GL.glIsProgram(x) for x in programs))
        self.assertEqual(precise_checksum(self.manager), self.digest)

    def test_failure_after_geometry_primitive_begins(self):
        self.fault(module, 'glBegin', after=True)

    def test_failure_before_geometry_primitive_ends(self):
        self.fault(module, 'glEnd')

    def test_failure_after_list_compilation_begins(self):
        self.fault(module, 'glNewList', after=True)

    def test_failure_inside_sphere_geometry(self):
        self.fault(module, 'glVertex3f')

    def test_failure_after_list_compilation_ends(self):
        self.fault(module, 'glEndList', after=True)

    def test_sphere_helper_failure_after_return_value_allocated(self):
        self.fault(module.Renderer, '_build_textured_sphere_list', after=True)

    def test_geometry_cleanup_error_preserves_original_failure(self):
        self.fault(module, 'glVertex3f', cleanup_failure=True)

    def test_cleanup_error_does_not_stop_other_resource_release(self):
        close = module.FleetMaterials.close
        def failed_close(material):
            close(material)
            raise ValueError('cleanup also failed')
        with patch.object(module.FleetMaterials, 'close', new=failed_close):
            self.fault(module.Renderer, '_reset_frame_cache')

    def test_material_helper_failure_after_allocation_releases_programs(self):
        self.fault(module.FleetMaterials, '__init__', after=True)

    def test_late_constructor_failure_releases_all_allocations(self):
        self.fault(module.Renderer, '_reset_frame_cache')


if __name__ == '__main__':
    unittest.main()
