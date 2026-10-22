"""One renderer, and it is the window (#160).

The legacy renderer used to stay loaded as the rollback control and as the automatic fallback when
the native window could not start. That made "renderer" a runtime choice again, which is exactly
what the issue asked to end: these tests pin the game to a single drawing path and pin the refusal
that replaces the fallback.
"""
import ast
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / 'main.py'


def helpers(*names, **env):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env


class SingleRenderPathTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(SOURCE.read_text())
        self.text = SOURCE.read_text()

    def test_renderer_is_not_a_choice_any_more(self):
        # No launch switch, no settings value: the module-level RENDERER is the literal 'cpp' and
        # nothing reassigns it.
        assigns = [n for n in self.tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'RENDERER' for t in n.targets)]
        self.assertEqual(len(assigns), 1, 'RENDERER is assigned exactly once, at module level')
        self.assertEqual(ast.literal_eval(assigns[0].value), 'cpp')
        self.assertNotIn("'--renderer'", self.text)
        self.assertNotIn('"--renderer"', self.text)
        self.assertNotIn('fell_back', self.text)

    def test_the_loop_never_draws_a_legacy_frame(self):
        # The module-level frame loop and every helper may publish, resize and report; they may not
        # call the legacy drawing API. Projecting floating text is not drawing: that stays until the
        # renderer module itself goes.
        body = ast.unparse(self.tree)
        self.assertNotIn('renderer.draw(', body, 'something still draws a legacy frame')
        self.assertNotIn('renderer.placement =', body,
                         'something still hands placement to the legacy renderer')

    def test_the_game_refuses_to_start_without_a_window(self):
        guards = [n for n in self.tree.body if isinstance(n, ast.If)
                  and 'cpp_unavailable()' in ast.unparse(n) and 'SystemExit' in ast.unparse(n)]
        self.assertEqual(len(guards), 1, 'the module must check for the window before it starts and stop')

    def test_missing_binary_is_named_with_the_build_command(self):
        env = helpers('cpp_unavailable', ROOT='/nonexistent-root', flash_print=Mock())
        message = env['cpp_unavailable']()
        self.assertIsNotNone(message)
        self.assertIn('cmake -S render_cpp', message)
        self.assertIn('#160', message)

    def test_present_binary_needs_no_message(self):
        from render_bridge import cpp_window
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
            binary = Path(directory) / cpp_window.DEFAULT_BINARY
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b'#!/bin/sh\nexit 0\n')
            binary.chmod(0o755)
            env = helpers('cpp_unavailable', ROOT=directory, flash_print=Mock())
            self.assertIsNone(env['cpp_unavailable']())

    def test_a_fault_is_reported_once_and_leaves_the_match(self):
        cpp = {'failed': False, 'quit': False}
        env = helpers('cpp_fatal', CPP=cpp, cpp_reset=Mock(), flash_print=Mock())
        env['cpp_fatal']('window died')
        env['cpp_fatal']('window died again')  # second fault in the same frame
        self.assertEqual(env['cpp_reset'].call_count, 1, 'reset the window once, not per call site')
        self.assertEqual(cpp['failed'], 'window died')
        self.assertTrue(cpp['quit'], 'the match must be left, not silently unrendered')
        self.assertEqual(env['flash_print'].call_count, 1)


if __name__ == '__main__':
    unittest.main()
