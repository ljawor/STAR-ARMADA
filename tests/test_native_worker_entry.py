"""The renderer worker must dispatch before game/window initialization."""
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class NativeWorkerEntryTests(unittest.TestCase):
    def test_real_entry_point_dispatches_worker_before_sdl_or_game(self):
        import builtins
        source = Path(__file__).resolve().parents[1] / 'main.py'
        worker = ModuleType('render_bridge.native_worker')
        cli = Mock(return_value=17)
        setattr(worker, 'cli', cli)
        original_import = builtins.__import__

        def forbid_game_initialization(name, *args, **kwargs):
            if name == 'pygame' or name.startswith(('OpenGL', 'game.core', 'render.menus')):
                raise AssertionError('Worker entry initialized application module: ' + name)
            return original_import(name, *args, **kwargs)

        config = '/isolated renderer/worker-config.json'
        with patch.object(sys, 'argv', [str(source), '--native-render-worker', config]), \
                patch.dict(sys.modules, {'render_bridge.native_worker': worker}), \
                patch('builtins.__import__', side_effect=forbid_game_initialization):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(str(source), run_name='__main__')
        self.assertEqual(raised.exception.code, 17)
        cli.assert_called_once_with([config])

    def test_probe_arguments_are_forwarded_literally_without_game_startup(self):
        import builtins
        source = Path(__file__).resolve().parents[1] / 'main.py'
        worker = ModuleType('render_bridge.native_worker')
        cli = Mock(return_value=0)
        setattr(worker, 'cli', cli)
        original_import = builtins.__import__

        def forbid_sdl(name, *args, **kwargs):
            if name == 'pygame' or name.startswith('OpenGL'):
                raise AssertionError('Probe initialized SDL/OpenGL')
            return original_import(name, *args, **kwargs)

        args = ['--probe', '--output', '/isolated renderer/ABI report.json']
        with patch.object(sys, 'argv', [str(source), '--native-render-worker', *args]), \
                patch.dict(sys.modules, {'render_bridge.native_worker': worker}), \
                patch('builtins.__import__', side_effect=forbid_sdl):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(str(source), run_name='__main__')
        self.assertEqual(raised.exception.code, 0)
        cli.assert_called_once_with(args)


if __name__ == '__main__':
    unittest.main()
