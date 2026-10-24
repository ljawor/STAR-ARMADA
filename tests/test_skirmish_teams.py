"""Skirmish team selection contracts, including legacy and LAN options."""
import copy
import unittest
from game.data.store import DataStore
from game.core.skirmish import build_skirmish_map, default_skirmish_options


class SkirmishTeamTests(unittest.TestCase):
    def setUp(self):
        self.ds = DataStore()

    def test_defaults_are_independent_four_slot_ffa_and_legacy_options_work(self):
        first = default_skirmish_options(self.ds)
        self.assertEqual(first['teams'], [0, 1, 2, 3])
        first['teams'][0] = 3
        self.assertEqual(default_skirmish_options(self.ds)['teams'], [0, 1, 2, 3])
        del first['teams']
        self.assertEqual([p['team'] for p in build_skirmish_map(self.ds, first)['players']], [0, 1])

    def test_active_teams_require_four_to_eight_slots_integer_ids_and_an_enemy(self):
        for teams in (None, '0123', [0, 1], list(range(9)),
                      [True, 1, 2, 3], [-1, 1, 2, 3], [8, 1, 2, 3],
                      [0.0, 1, 2, 3], ['0', 1, 2, 3], [[], 1, 2, 3],
                      [3, 3, 0, 1]):
            options = default_skirmish_options(self.ds)
            options['teams'] = teams
            with self.subTest(teams=teams), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, options)
        options['teams'] = [3, 0, None, -10]
        self.assertEqual([p['team'] for p in build_skirmish_map(self.ds, options)['players']], [3, 0])
        self.assertEqual(options['teams'], [3, 0, None, -10])
        for teams in ([7, 4, 0, 0], [0, 1, 2, 3, 0], list(range(8))):
            options['teams'] = teams
            self.assertEqual([p['team'] for p in build_skirmish_map(self.ds, options)['players']], teams[:2])

    def test_lan_api_keeps_cooperative_and_ffa_despite_inherited_skirmish_teams(self):
        from game.net.lan import build_lan_map
        options = default_skirmish_options(self.ds)
        options.update(map_id='skirmish03', human_count=2, ai_count=2, teams=[3] * 4)
        for cooperative, expected in ((True, [0, 0, 1, 1]), (False, [0, 1, 2, 3])):
            options['cooperative'] = cooperative
            with self.subTest(cooperative=cooperative):
                result = build_lan_map(self.ds, options)
                self.assertEqual([p['team'] for p in result['players']], expected)
                self.assertEqual([p['is_ai'] for p in result['players']], [False, False, True, True])
                self.assertEqual(options['teams'], [3] * 4)
        options.update(ai_count=0, cooperative=True)
        self.assertEqual([p['team'] for p in build_lan_map(self.ds, options)['players']], [0, 0])

    def test_selected_2v2_teams_reach_real_players_without_mutating_inputs(self):
        from game.core.manager import GameManager
        options = default_skirmish_options(self.ds)
        options.update(map_id='skirmish03', ai_count=3, teams=[2, 2, 0, 0])
        original_options, original_maps = copy.deepcopy(options), copy.deepcopy(self.ds.maps)
        result = build_skirmish_map(self.ds, options)
        self.assertEqual([p['team'] for p in result['players']], [2, 2, 0, 0])
        gm = GameManager.start_skirmish(result)
        self.assertEqual([p.team for p in gm.state.players.values()], [2, 2, 0, 0])
        self.assertEqual(gm.state.allied_player_ids(0), [0, 1])
        self.assertTrue(all(gm.state.can_see(0, e.id) for e in gm.state.entities.values() if e.owner == 1))
        self.assertFalse(gm.state.players[0].is_ai)
        self.assertTrue(gm.state.players[1].is_ai)
        self.assertEqual(options, original_options)
        self.assertEqual(self.ds.maps, original_maps)


if __name__ == '__main__':
    unittest.main()
