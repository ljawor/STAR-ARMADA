"""Ownership regressions: mock GL entry points, not allocating wrappers."""
import os
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from OpenGL import GL
from OpenGL.GL import shaders
from render.fleet_materials import FleetMaterials


class ShaderOwnershipTests(unittest.TestCase):
    def test_failed_allocations_are_all_released(self):
        # Exercise actual PyOpenGL wrappers on the old implementation, and the
        # explicit entry points on the replacement, with the same fake driver.
        for failure in ('vertex', 'fragment', 'link', 'second_fragment', 'source'):
            with self.subTest(failure=failure), ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'STAR_ARMADA_FIXED_MATERIALS': '0'}))
                allocated_shaders, allocated_programs = set(), set()
                def shader_alloc(kind):
                    value = shader_alloc.count + 11
                    shader_alloc.count += 1
                    allocated_shaders.add(value)
                    return value
                shader_alloc.count = 0
                def program_alloc():
                    value = program_alloc.count + 99
                    program_alloc.count += 1
                    allocated_programs.add(value)
                    return value
                program_alloc.count = 0
                failed_shader = {'vertex': 11, 'fragment': 12, 'second_fragment': 14}.get(failure)
                funcs = {
                    'glCreateShader': Mock(side_effect=shader_alloc),
                    'glCreateProgram': Mock(side_effect=program_alloc),
                    'glShaderSource': Mock(side_effect=RuntimeError('source failure') if failure == 'source' else None),
                    'glCompileShader': Mock(), 'glAttachShader': Mock(),
                    'glDetachShader': Mock(), 'glLinkProgram': Mock(),
                    'glValidateProgram': Mock(),
                    'glGetShaderiv': Mock(side_effect=lambda shader, flag: shader != failed_shader),
                    'glGetProgramiv': Mock(side_effect=lambda program, flag: not (failure == 'link' and flag == GL.GL_LINK_STATUS)),
                    'glGetShaderInfoLog': Mock(return_value=b'compile failure'),
                    'glGetProgramInfoLog': Mock(return_value=b'link failure'),
                    'glGetUniformLocation': Mock(return_value=1),
                    'glDeleteShader': Mock(side_effect=allocated_shaders.remove),
                    'glDeleteProgram': Mock(side_effect=allocated_programs.remove),
                }
                for name, fn in funcs.items():
                    stack.enter_context(patch.object(GL, name, fn))
                    if hasattr(shaders, name):
                        stack.enter_context(patch.object(shaders, name, fn))
                stack.enter_context(self.assertLogs('render.fleet_materials', level='WARNING'))
                material = FleetMaterials()
                self.assertFalse(material.available)
                self.assertTrue(material.error)
                self.assertEqual(allocated_shaders, set(), 'shader allocated before failure leaked')
                self.assertEqual(allocated_programs, set(), 'program allocated before failure leaked')


class RendererOwnershipTests(unittest.TestCase):
    def test_close_deletes_each_owned_resource_once(self):
        from render.renderer import Renderer
        r = Renderer.__new__(Renderer)
        r.materials = FleetMaterials.__new__(FleetMaterials)
        r.materials.programs = {'hull': 71, 'planet': 72}
        r.materials.locations = {}
        r.ship_lists = {'wedge': 11, 'wedge_base': 11, 'sphere': 12}
        r._star_list = 13
        r._unit_sphere_tex = 14
        r._planet_tex_cache = {'earth': 21, 'alias': 21}
        r._hull_tex, r._space_tex, r._star_tex, r._nebula_tex = 22, 23, 24, 25
        self.assertTrue(callable(getattr(r, 'close', None)), 'Renderer needs explicit close')
        with patch.object(GL, 'glDeleteLists') as lists, \
             patch.object(GL, 'glDeleteTextures') as textures, \
             patch.object(GL, 'glDeleteProgram') as programs:
            r.close()
            r.close()
        self.assertCountEqual([c.args for c in lists.call_args_list], [(11, 1), (12, 1), (13, 1), (14, 1)])
        self.assertEqual(textures.call_count, 1)
        self.assertCountEqual(textures.call_args.args[0], [21, 22, 23, 24, 25])
        self.assertCountEqual([c.args[0] for c in programs.call_args_list], [71, 72])
        self.assertEqual(r.ship_lists, {})
        self.assertEqual(r._planet_tex_cache, {})
        self.assertIsNone(r._unit_sphere_tex)

    def test_hud_close_is_idempotent_before_and_after_upload(self):
        from render.hud import HUD
        hud = HUD.__new__(HUD)
        self.assertTrue(callable(getattr(hud, 'close', None)), 'HUD needs explicit close')
        with patch.object(GL, 'glDeleteTextures') as delete:
            hud.tex = None
            hud.close()
            delete.assert_not_called()
            hud.tex = 42
            hud.close()
            hud.close()
        delete.assert_called_once_with([42])
        self.assertIsNone(hud.tex)


class MainLifecycleTests(unittest.TestCase):
    @staticmethod
    def source_tree():
        import ast
        from pathlib import Path
        return ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())

    def test_start_game_closes_old_views_before_replacement(self):
        import ast
        from types import SimpleNamespace
        tree = self.source_tree()
        start = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'start_game')
        events = []
        old_renderer = Mock()
        old_renderer.close.side_effect = lambda: events.append('renderer.close')
        old_hud = Mock()
        old_hud.close.side_effect = lambda: events.append('hud.close')
        def create_renderer(*args):
            events.append('Renderer')
            return Mock()
        def create_hud(*args):
            events.append('HUD')
            return Mock()
        ns = dict(renderer=old_renderer, hud=old_hud, W=640, H=480,
                  net_session=None, audio=None, SETTINGS={},
                  make_game=lambda *args: SimpleNamespace(state=SimpleNamespace(entities={}, time=0.0)),
                  Camera=Mock(), Renderer=create_renderer, HUD=create_hud,
                  make_audio=Mock(), InputController=Mock(), _AppGlue=Mock())
        exec(compile(ast.Module(body=[start], type_ignores=[]), 'main.py', 'exec'), ns)
        ns['start_game']()
        self.assertEqual(events, ['renderer.close', 'hud.close', 'Renderer', 'HUD'])

    def test_shutdown_closes_views_before_quit_and_handles_menu_only(self):
        import ast
        tree = self.source_tree()
        loop_index = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.While))
        code = compile(ast.Module(body=tree.body[loop_index + 1:], type_ignores=[]), 'main.py', 'exec')
        for started in (False, True):
            with self.subTest(started=started):
                events = []
                renderer, hud, pygame = Mock(), Mock(), Mock()
                renderer.close.side_effect = lambda: events.append('renderer.close')
                hud.close.side_effect = lambda: events.append('hud.close')
                pygame.quit.side_effect = lambda: events.append('quit')
                exec(code, dict(audio=None, renderer=renderer if started else None,
                                hud=hud if started else None, pygame=pygame,
                                save_settings=Mock(), SETTINGS={}, SMOKE=False,
                                menu=Mock(), net_session=None))
                self.assertEqual(events, ['renderer.close', 'hud.close', 'quit'] if started else ['quit'])


class SkyStateTests(unittest.TestCase):
    def test_lazy_upload_preserves_callers_texture_binding(self):
        import render.renderer as module
        from types import SimpleNamespace
        r = module.Renderer.__new__(module.Renderer)
        r._space_tex = None
        r._star_list = 8
        r._unit_sphere_tex = 9
        r.camera = SimpleNamespace(eye_position=lambda: (0, 0, 0), target=(0, 0, 0))
        binding, saved = [77], []
        def upload(*args):
            binding[0] = 88
            return 88
        with ExitStack() as stack:
            # All GL calls are intercepted: never enter a real driver headlessly.
            for name in vars(module):
                if name.startswith('gl') and callable(getattr(module, name)):
                    stack.enter_context(patch.object(module, name))
            stack.enter_context(patch.object(GL, 'glPushAttrib', side_effect=lambda flags: saved.append(binding[0])))
            stack.enter_context(patch.object(GL, 'glPointSize'))
            stack.enter_context(patch.object(module, 'glPopAttrib', side_effect=lambda: binding.__setitem__(0, saved.pop())))
            stack.enter_context(patch.object(module, 'glBindTexture', side_effect=lambda target, value: binding.__setitem__(0, value)))
            stack.enter_context(patch.object(module.tex, 'deep_space_texture'))
            stack.enter_context(patch.object(module.tex, 'surface_to_texture', side_effect=upload))
            r._draw_starfield()
        self.assertEqual(binding[0], 77)


if __name__ == '__main__':
    unittest.main()
