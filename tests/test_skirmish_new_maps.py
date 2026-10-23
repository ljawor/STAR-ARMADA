"""CPU-only safety, expansion and deterministic simulation for new skirmishes.

Reuse the established real-simulation acceptance contract without collecting the
legacy test cases again. No renderer, display or window is initialized here.
"""
import json
import unittest

# Keep the application's import order before the baseline imports DataStore.
import game.core.manager  # noqa: F401
import test_skirmish_maps as baseline


class NewSkirmishMapsTests(unittest.TestCase):
    check_map = baseline.SkirmishMapsTests.check_map

    def test_skirmish05_eight_player_crown(self):
        self.check_map('skirmish05', 8)

    def test_skirmish06_two_player_divide(self):
        self.check_map('skirmish06', 2)

    def test_skirmish07_two_player_corridors(self):
        self.check_map('skirmish07', 2)

    def test_skirmish08_three_player_spiral(self):
        self.check_map('skirmish08', 3)

    def test_authored_layouts_are_distinct_with_concise_descriptions(self):
        signatures = []
        names = []
        for number in range(5, 9):
            path = baseline.ROOT / f'assets/data/maps/skirmish{number:02}.json'
            self.assertTrue(path.is_file(), f'Missing playable skirmish map: {path.name}')
            data = json.loads(path.read_text())
            self.assertEqual(data['id'], path.stem)
            self.assertGreater(len(data['description']), 80)
            self.assertLessEqual(len(data['description']), 500)
            names.append(data['name'])
            signatures.append(json.dumps({key: data.get(key, []) for key in
                                          ('bounds', 'asteroid_fields', 'planets',
                                           'gas_giants', 'nebulas')}, sort_keys=True))
        self.assertEqual(len(set(names)), 4)
        self.assertEqual(len(set(signatures)), 4)


if __name__ == '__main__':
    unittest.main()
