"""Shader lifecycle unit checks. GL entry points are mocked: never require a window."""
import os
import unittest
from unittest.mock import patch, call

from render.fleet_materials import FleetMaterials


class FleetMaterialTests(unittest.TestCase):
    def test_forced_fallback_never_calls_gl(self):
        with patch.dict(os.environ, {'STAR_ARMADA_FIXED_MATERIALS': '1'}), \
             patch('render.fleet_materials.GL.glCreateShader') as compile_shader:
            material = FleetMaterials()
            self.assertFalse(material.available)
            with material.use('hull', materialPass=0.0):
                material.hull_pass(1.0)
            compile_shader.assert_not_called()

    def test_failed_second_program_falls_back_and_releases_first(self):
        with patch.dict(os.environ, {'STAR_ARMADA_FIXED_MATERIALS': '0'}), \
             patch('render.fleet_materials.GL.glCreateShader', side_effect=[11, 12, 13, 14]), \
             patch('render.fleet_materials.GL.glShaderSource'), \
             patch('render.fleet_materials.GL.glCompileShader'), \
             patch('render.fleet_materials.GL.glGetShaderiv', side_effect=[1, 1, 1, 0]), \
             patch('render.fleet_materials.GL.glGetShaderInfoLog', return_value=b'compile failed'), \
             patch('render.fleet_materials.GL.glCreateProgram', return_value=99), \
             patch('render.fleet_materials.GL.glAttachShader'), \
             patch('render.fleet_materials.GL.glDetachShader'), \
             patch('render.fleet_materials.GL.glLinkProgram'), \
             patch('render.fleet_materials.GL.glGetProgramiv', return_value=1), \
             patch('render.fleet_materials.GL.glDeleteShader') as delete_shader, \
             patch('render.fleet_materials.GL.glDeleteProgram') as delete_program, \
             self.assertLogs('render.fleet_materials', level='WARNING'):
            material = FleetMaterials()
        self.assertFalse(material.available)
        self.assertIn('compile failed', material.error or '')
        self.assertEqual(delete_shader.call_args_list, [call(11), call(12), call(13), call(14)])
        delete_program.assert_called_once_with(99)

    def test_program_scope_restores_caller_even_on_exception(self):
        material = FleetMaterials.__new__(FleetMaterials)
        material.programs = {'hull': 99}
        material.locations = {('hull', 'materialPass'): 3, ('hull', 'authoredSurface'): 4}
        for previous in (0, 7):
            with self.subTest(previous=previous), \
                 patch('render.fleet_materials.GL.glGetIntegerv', return_value=previous), \
                 patch('render.fleet_materials.GL.glUseProgram') as use, \
                 patch('render.fleet_materials.GL.glUniform1f') as uniform:
                with self.assertRaisesRegex(ValueError, 'draw failure'):
                    with material.use('hull', materialPass=0.0):
                        raise ValueError('draw failure')
                self.assertEqual(use.call_args_list, [call(99), call(previous)])
                self.assertEqual(uniform.call_args_list, [call(4, 0.), call(3, 0.)])


if __name__ == '__main__':
    unittest.main()
