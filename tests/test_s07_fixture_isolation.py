"""Regression for a pre-existing order leak exposed by the S07 route union."""
from pathlib import Path
import unittest
import game.core.manager
from game.data.store import DataStore

ROOT=Path(__file__).resolve().parents[1]

class PreviewFixtureIsolation(unittest.TestCase):
    def test_addon_preview_case_restores_original_catalogue_singleton(self):
        from test_generic_model_preview import GenericPreviewIntegrationTests
        previous=DataStore._instance
        self.addCleanup(setattr,DataStore,'_instance',previous)
        baseline=DataStore(assets_dir=str(ROOT/'assets/data'),mods=[],balance={})
        before=set(baseline.ships)
        result=unittest.TestResult()
        GenericPreviewIntegrationTests('test_additive_gameplay_fixture_reaches_ship_size_and_fleet_mesh').run(result)
        self.assertEqual(result.errors,[])
        self.assertEqual(result.failures,[])
        self.assertIs(DataStore._instance,baseline,'addon preview test leaked its private catalogue into later tests')
        self.assertEqual(set(DataStore.get().ships),before)
        self.assertNotIn('raiders_scout',DataStore.get().ships)

if __name__=='__main__': unittest.main()
