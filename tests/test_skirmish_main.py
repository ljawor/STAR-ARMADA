"""Exercise trusted main factory functions without entering the SDL loop."""
import ast
import inspect
from pathlib import Path
import unittest


class SkirmishMainTests(unittest.TestCase):
    def factory(self):
        from game.data.store import DataStore
        from game.core.manager import GameManager
        from game.core.state import GameState
        import json
        tree = ast.parse(Path('main.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'make_game')
        ns = dict(DataStore=DataStore, GameManager=GameManager, GameState=GameState,
                  json=json, MODS=[])
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'main.py', 'exec'), ns)
        return ns['make_game']

    def test_factory_accepts_setup_options(self):
        self.assertIn('skirmish_options', inspect.signature(self.factory()).parameters)

    def test_menu_launch_forwards_payload(self):
        tree = ast.parse(Path('main.py').read_text())
        launches = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == 'start_game'
                    and any(k.arg == 'skirmish_options' and isinstance(k.value, ast.Name)
                            and k.value.id == 'payload' for k in n.keywords)]
        self.assertTrue(launches, 'setup launch must pass the actual menu payload')

    def test_factory_uses_selected_map_and_players(self):
        from game.data.store import DataStore
        from game.core.skirmish import default_skirmish_options
        options = default_skirmish_options(DataStore.get())
        options.update(map_id='skirmish03', ai_count=3,
                       colors=['cyan', 'red', 'yellow', 'purple'])
        gm = self.factory()(None, skirmish_options=options)
        self.assertEqual(gm.state.map_info.name, 'skirmish03')
        self.assertEqual(len(gm.state.players), 4)
        self.assertEqual(sum(p.is_ai for p in gm.state.players.values()), 3)


if __name__ == '__main__':
    unittest.main()
