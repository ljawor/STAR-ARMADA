"""Ensure acceptance evidence counts real ticks, never frozen step calls."""
import importlib.util
import unittest
from pathlib import Path


class AcceptanceDiagnosticTests(unittest.TestCase):
    def test_ai_pending_sites_are_json_serializable(self):
        from tools.diag_gameplay_acceptance import scenario
        import json
        result = scenario('imperial', 'skirmish01', 'normal', 390001, 3, 10)
        self.assertEqual(result['actual_ticks'], 90)
        self.assertTrue(any(p['pending_sites'] for p in result['checkpoints'][-1]['players'].values()))
        json.dumps(result)

    def test_terminal_simulation_reports_real_ticks_not_requested_ticks(self):
        path = Path(__file__).resolve().parents[1] / 'tools/diag_gameplay_acceptance.py'
        self.assertTrue(path.exists(), 'Reusable gameplay acceptance diagnostic is missing')
        spec = importlib.util.spec_from_file_location('acceptance_diag', path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        from game.core.manager import GameManager
        gm = GameManager.start_skirmish({'id': 'one_coalition', 'players': [
            {'slot': 0, 'team': 0, 'start_units': {'constructor': 1}}]})
        result = module.run_simulation(gm, seconds=10, wall_limit=10)
        self.assertEqual(result['actual_ticks'], gm.state.tick)
        self.assertLess(result['actual_ticks'], result['requested_ticks'])
        self.assertTrue(result['game_over'])
        self.assertEqual(result['stop_reason'], 'game_over')
        self.assertAlmostEqual(result['simulated_seconds'], result['actual_ticks'] / 30)
        self.assertNotEqual(result['acceptance_status'], 'full_match_accepted')


if __name__ == '__main__':
    unittest.main()
