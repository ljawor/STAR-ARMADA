"""Issue #159: the console is quiet on the way out of a match.

Two things used to write into the player's terminal: the native viewer dumped its whole JSON
report (the frame-time sample arrays are one float per frame) to stdout on exit, and
`main.cpp_restore_window` called pygame's deprecated `Window.from_display_module()` on every
return to the menu even though the embedded renderer never iconifies the window.

The viewer half is verified against the built binary (see the PR receipt: 9,795 bytes of report
on stdout before, 0 after, and `--stdout-report` restores it on request). These tests pin the
application half: the window is raised only when a match really iconified it, through one module,
without a deprecation notice escaping.
"""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
import warnings

from render import host_window

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'main.py'


class HostWindowTests(unittest.TestCase):
    def test_no_display_means_no_attempt(self):
        with patch('pygame.display.get_init', return_value=False):
            self.assertFalse(host_window.restore())

    def test_the_window_is_restored_shown_and_focused_in_that_order(self):
        calls = []

        class Window:
            def restore(self):
                calls.append('restore')

            def show(self):
                calls.append('show')

            def focus(self):
                calls.append('focus')

        class Bridge:
            @staticmethod
            def from_display_module():
                return Window()

        with patch('pygame.display.get_init', return_value=True), \
                patch('pygame._sdl2.video.Window', Bridge):
            self.assertTrue(host_window.restore())
        self.assertEqual(calls, ['restore', 'show', 'focus'])

    def test_the_deprecation_notice_does_not_escape_into_the_console(self):
        class Window:
            def restore(self):
                pass

            def show(self):
                pass

            def focus(self):
                pass

        class Bridge:
            @staticmethod
            def from_display_module():
                warnings.warn('Please use Window.get_surface and Window.flip to use '
                              'surface-rendering with Window. This method will be removed in a '
                              'future version.', DeprecationWarning, stacklevel=2)
                return Window()

        with patch('pygame.display.get_init', return_value=True), \
                patch('pygame._sdl2.video.Window', Bridge), \
                warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            self.assertTrue(host_window.restore())
        self.assertEqual([str(w.message) for w in caught], [])

    def test_a_failing_bridge_is_reported_and_never_raised_on_exit(self):
        class Bridge:
            @staticmethod
            def from_display_module():
                raise RuntimeError('no window to wrap')

        with patch('pygame.display.get_init', return_value=True), \
                patch('pygame._sdl2.video.Window', Bridge):
            self.assertFalse(host_window.restore())

    def test_the_deprecated_bridge_has_exactly_one_call_site_in_the_application(self):
        offenders = []
        for path in [MAIN] + sorted((ROOT / 'render').glob('*.py')) + \
                sorted((ROOT / 'render_bridge').glob('*.py')) + sorted((ROOT / 'game').rglob('*.py')):
            tree = ast.parse(path.read_text())
            # Read the code, not the prose: several docstrings explain why this API is deprecated.
            if any(isinstance(node, ast.Attribute) and node.attr == 'from_display_module'
                   for node in ast.walk(tree)):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, ['render/host_window.py'],
                         'one call site, so the migration has one place to delete')


class MainWindowStateTests(unittest.TestCase):
    """`cpp_restore_window` is driven by an actual iconification, not by a non-None window."""

    def env(self, **state):
        tree = ast.parse(MAIN.read_text())
        nodes = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == 'cpp_restore_window']
        namespace = {'CPP': dict(state)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN), 'exec'), namespace)
        return namespace

    def test_leaving_a_match_that_kept_the_window_does_not_touch_window_state(self):
        with patch('render.host_window.restore') as restore:
            self.env(iconified=False)['cpp_restore_window']()
        restore.assert_not_called()

    def test_an_iconified_window_is_raised_once(self):
        namespace = self.env(iconified=True)
        with patch('render.host_window.restore', return_value=True) as restore:
            namespace['cpp_restore_window']()
            namespace['cpp_restore_window']()
        self.assertEqual(restore.call_count, 1, 'the repair belongs to the iconification, once')
        self.assertFalse(namespace['CPP']['iconified'])

    def test_the_iconification_is_recorded_where_the_native_window_takes_the_display(self):
        source = MAIN.read_text()
        iconify = source.index('pygame.display.iconify()')
        self.assertIn('CPP["iconified"] = True', source[iconify:iconify + 200])


if __name__ == '__main__':
    unittest.main()
