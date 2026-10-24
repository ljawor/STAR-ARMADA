"""Execute the real main boundary without bootstrapping SDL or a GPU."""
import ast
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from render_bridge import embedded
from tests import test_native_worker as worker_tests

ROOT = worker_tests.ROOT


class NativeMainBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        worker_tests.NativeWorkerTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    window = worker_tests.NativeWorkerTests.window

    def exercise_poll_failure(self, mode):
        window = self.window(mode)
        process = window._process
        # A completed native frame precedes the failed next loop poll.
        self.assertEqual(window._request('frame')['count'], 320 * 240 * 4)
        resources = [Mock(), Mock()]
        directory = Mock()
        controller = SimpleNamespace(keys={'w'}, dragging=True, drag_start=(1, 1),
            drag_cur=(2, 2), right_drag=(3, 3), remote_pointer=(4, 4))
        tree = ast.parse((ROOT / 'main.py').read_text())
        initializer = next(node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == 'CPP'
                                   for target in node.targets))
        initial = {}
        exec(compile(ast.Module(body=[initializer], type_ignores=[]), 'main.py', 'exec'), initial)
        state = initial['CPP']
        state.update(window=window, input=resources[0], session=resources[1],
                     directory=directory, camera=object(), view_mark=object(),
                     seen={1}, seen_tick=9, selection={1})
        messages = []
        namespace = dict(CPP=state, inputc=controller, flash_print=messages.append,
                         cpp_restore_window=Mock())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {'cpp_drawing', 'cpp_fatal', 'cpp_reset'}]
        self.assertEqual(len(functions), 3)
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'main.py', 'exec'), namespace)
        drawing = next(node for node in functions if node.name == 'cpp_drawing')
        calls = {ast.unparse(node.func) for node in ast.walk(drawing) if isinstance(node, ast.Call)}
        self.assertLessEqual(calls, {'window.poll', 'cpp_fatal', 'str'}, 'no legacy draw path')
        with patch.object(embedded, 'FRAME_TIMEOUT', .15):
            self.assertFalse(namespace['cpp_drawing']())
        self.assertTrue(state['failed'])
        self.assertTrue(state['quit'])
        self.assertIn('Native renderer failed', state['failed'])
        self.assertEqual(len(messages), 1)
        self.assertIn('no legacy fallback', messages[0])
        reason = state['failed']
        self.assertFalse(namespace['cpp_drawing']())
        namespace['cpp_fatal']('second fault')
        self.assertEqual(state['failed'], reason)
        self.assertEqual(len(messages), 1)
        for name in ('input', 'window', 'session'):
            self.assertIsNone(state[name])
        for resource in resources:
            resource.close.assert_called_once_with()
        directory.cleanup.assert_called_once_with()
        namespace['cpp_restore_window'].assert_called_once_with()
        self.assertFalse(controller.keys)
        self.assertFalse(controller.dragging)
        self.assertIsNone(controller.remote_pointer)
        self.assertNotIn('camera', state)
        self.assertNotIn('directory', state)
        self.assertIsNotNone(process.poll())
        self.assertIsNone(window._mapping)


    def test_child_exit_after_frame_returns_to_menu_once(self):
        self.exercise_poll_failure(9)

    def test_blocked_poll_returns_to_menu_once(self):
        self.exercise_poll_failure(8)


if __name__ == '__main__':
    unittest.main()
