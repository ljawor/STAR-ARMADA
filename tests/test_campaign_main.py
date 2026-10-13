"""Headless execution of the actual campaign load and completion readers."""
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_lan_main import factories, ROOT
from test_campaign_lifecycle import campaign, precise


class CampaignMainTests(unittest.TestCase):
    def test_load_and_quickload_use_restored_campaign_for_hud_and_progression(self):
        gm = campaign([{'type': 'survive_time', 'time': 0.}])
        gm.mission.mission.update(id='restored', name='Restored campaign')
        gm.step(1 / 30)
        tree = ast.parse((ROOT / 'main.py').read_text())
        # Execute the real HUD reader; the terminal-result behaviour is the real
        # escape_from_decided_match() below (#69 moved it out of the loop).
        hud_reader = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                          and any(isinstance(x, ast.Assign) and any(
                              isinstance(t, ast.Attribute) and t.attr == 'mission_progress'
                              for t in x.targets) for x in n.body))
        scratch = Path.home() / '.hermes/cache/scratch'
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            save = Path(directory) / 'campaign.json'
            save.write_text(json.dumps(precise(gm.state)))
            for quickload in (False, True):
                with self.subTest(quickload=quickload):
                    ns = factories()
                    ns.update(json=json, mission_def={'id': 'old'} if quickload else None)
                    if quickload:
                        ns['rebuild'](str(save))
                    else:
                        ns['start_game'](load_path=str(save))
                    self.assertEqual(ns['mission_def'], ns['gm'].mission.mission)
                    self.assertEqual(ns['mission_def']['id'], 'restored')
                    ns['menu'].campaign = {'missions': [{'id': 'old'}, {'id': 'restored'}, {'id': 'next'}]}
                    progress = SimpleNamespace(unlock_campaign_mission=Mock(),
                                               complete_campaign_mission=Mock())
                    with patch.dict(sys.modules, {'render.menus': progress}):
                        code = ast.fix_missing_locations(ast.Module(
                            body=[hud_reader], type_ignores=[]))
                        exec(compile(code, str(ROOT / 'main.py'), 'exec'), ns)
                        # #69: the terminal Escape branch is a real function now,
                        # so call it instead of executing a copied branch.
                        self.assertIn('escape_from_decided_match', ns)
                        self.assertTrue(ns['escape_from_decided_match']())
                    self.assertEqual(ns['hud'].mission_name, 'Restored campaign')
                    self.assertEqual(ns['hud'].mission_progress, ns['gm'].mission.progress_text())
                    self.assertTrue(ns['hud'].mission_done)
                    self.assertFalse(ns['hud'].mission_failed)
                    self.assertEqual(ns['mode'], 'menu')
                    self.assertEqual(ns['menu'].screen, 'campaign')   # #89
                    progress.unlock_campaign_mission.assert_called_once_with('next')
                    progress.complete_campaign_mission.assert_called_once_with('restored')


if __name__ == '__main__':
    unittest.main()
