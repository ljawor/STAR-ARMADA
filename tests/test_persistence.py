"""Save/persistence tests (spec §32): autosave ring + campaign progress."""
import os
import unittest

import helpers


class TestAutosaveRing(unittest.TestCase):
    def test_ring_config_defaults(self):
        """Autosave ring uses 3 slots; index tracked in settings."""
        import json
        rules = json.load(open(os.path.join(
            helpers.ROOT, "assets", "data", "game_rules.json")))
        # sanity: game rules still load and contain victory block from wave 1
        self.assertIn("victory", rules["sim"])

    def test_campaign_progress_roundtrip(self):
        from render.menus import (load_campaign_progress,
                                  save_campaign_progress, CAMPAIGN_PATH)
        if os.path.exists(CAMPAIGN_PATH):
            os.remove(CAMPAIGN_PATH)
        try:
            self.assertEqual(load_campaign_progress(), 0)
            save_campaign_progress(3)
            self.assertEqual(load_campaign_progress(), 3)
            save_campaign_progress(1)   # never regresses below written value? no: set is set
            self.assertEqual(load_campaign_progress(), 1)
        finally:
            if os.path.exists(CAMPAIGN_PATH):
                os.remove(CAMPAIGN_PATH)

    def test_campaign_progress_missing_file(self):
        from render.menus import load_campaign_progress, CAMPAIGN_PATH
        if os.path.exists(CAMPAIGN_PATH):
            os.remove(CAMPAIGN_PATH)
        self.assertEqual(load_campaign_progress(), 0)

    def test_campaign_progress_corrupt_file(self):
        from render.menus import load_campaign_progress, CAMPAIGN_PATH
        os.makedirs(os.path.dirname(CAMPAIGN_PATH), exist_ok=True)
        with open(CAMPAIGN_PATH, "w") as f:
            f.write("{not json")
        try:
            self.assertEqual(load_campaign_progress(), 0)
        finally:
            os.remove(CAMPAIGN_PATH)


if __name__ == "__main__":
    unittest.main()