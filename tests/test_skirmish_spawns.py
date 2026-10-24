"""CPU-only eight-player setup, spawn assignment and real-state contracts."""
import copy
import json
import unittest

from game.core.manager import GameManager
from game.core.skirmish import PLAYER_COLORS, build_skirmish_map, default_skirmish_options
from game.core.state import GameState
from game.data.store import DataStore
from game.net.replay import state_checksum


class SkirmishSpawnTests(unittest.TestCase):
    def setUp(self):
        self.ds = DataStore()
        # Isolate the converter's capacity contract from authored-map delivery.
        source = copy.deepcopy(self.ds.maps['skirmish03'])
        source['players'] = [copy.deepcopy(source['players'][0]) for _ in range(8)]
        for slot, player in enumerate(source['players']):
            player.update(slot=slot, start=[-2800 + slot * 800, 0, -2000])
        self.ds.maps['skirmish03'] = source
        self.options = default_skirmish_options(self.ds)
        self.options.update(map_id='skirmish03', ai_count=7,
                            colors=list(PLAYER_COLORS), factions=['imperial'] * 8,
                            teams=list(range(8)))

    def test_four_slot_default_shape_is_unchanged(self):
        expected = dict(map_id='skirmish01', ai_count=1,
                        colors=['blue', 'red', 'green', 'purple'],
                        factions=['imperial'] * 4, ai_difficulty='normal', teams=[0, 1, 2, 3])
        actual = default_skirmish_options(self.ds)
        self.assertEqual(actual, expected)
        self.assertEqual(json.dumps(actual), json.dumps(expected))

    def test_two_through_eight_players_accept_capacity_sized_choices(self):
        source = self.ds.maps['skirmish03']
        for active in range(2, 9):
            source['players'] = [
                dict(copy.deepcopy(source['players'][0]), slot=i,
                     start=[-2800 + i * 800, 0, -2000]) for i in range(active)]
            for length in range(max(4, active), 9):
                options = copy.deepcopy(self.options)
                options['ai_count'] = active - 1
                for key in ('colors', 'factions', 'teams'):
                    options[key] = options[key][:length]
                with self.subTest(active=active, length=length):
                    result = build_skirmish_map(self.ds, options)
                    self.assertEqual(len(result['players']), active)
                    self.assertEqual([p['team'] for p in result['players']], list(range(active)))
                    self.assertEqual([p['start'] for p in result['players']],
                                     [p['start'] for p in source['players']])
                    self.assertEqual([p['is_ai'] for p in result['players']], [False] + [True] * (active - 1))
        del self.options['teams']
        self.assertEqual([p['team'] for p in build_skirmish_map(self.ds, self.options)['players']], list(range(8)))

    def test_spawn_selection_moves_only_anchor_and_is_a_deep_copy(self):
        source = self.ds.maps['skirmish03']
        for slot, player in enumerate(source['players']):
            player['start_units']['corvette'] = slot
            player['identity_marker'] = {'slot': slot}
        self.options.update(ai_count=2, spawn_slots=[7, 5, 3, 0, 1, 2, 4, 6])
        original_maps, original_options = copy.deepcopy(self.ds.maps), copy.deepcopy(self.options)
        result = build_skirmish_map(self.ds, self.options)
        for slot, player in enumerate(result['players']):
            self.assertEqual(player['start'], source['players'][self.options['spawn_slots'][slot]]['start'])
            self.assertEqual(player['start_units'], source['players'][slot]['start_units'])
            self.assertEqual(player['identity_marker'], {'slot': slot})
            self.assertEqual(player['slot'], slot)
            self.assertEqual(player['color'], PLAYER_COLORS[self.options['colors'][slot]])
        result['players'][0]['start'][0] = 999
        result['players'][0]['start_units']['corvette'] = 999
        result['players'][0]['identity_marker']['slot'] = 999
        self.assertEqual(self.ds.maps, original_maps)
        self.assertEqual(self.options, original_options)
        self.options['spawn_slots'] = [7, 5, 3]
        self.assertEqual(len(build_skirmish_map(self.ds, self.options)['players']), 3)

    def test_malformed_spawn_assignments_are_rejected_without_mutation(self):
        self.options['ai_count'] = 1
        original = copy.deepcopy(self.ds.maps)
        invalid = (None, (), '01', {}, [], [0], [0, 0], [True, 1], [0, False],
                   [0.0, 1], ['0', 1], [[], 1], [-1, 1], [0, 8],
                   [0, 1, 2, 2], [0, 1, 8], [0, 1, True])
        for slots in invalid:
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, dict(self.options, spawn_slots=slots))
        self.assertEqual(self.ds.maps, original)

    def test_real_eight_player_anchors_determinism_and_precise_restore(self):
        self.options['spawn_slots'] = [7, 2, 5, 0, 6, 1, 4, 3]
        result = build_skirmish_map(self.ds, self.options)
        first = GameManager.start_skirmish(result)
        second = GameManager.start_skirmish(build_skirmish_map(self.ds, self.options))
        for slot in range(8):
            stations = [e for e in first.state.entities.values()
                        if e.owner == slot and e.data_id == 'command_station']
            self.assertEqual(len(stations), 1)
            anchor = self.ds.maps['skirmish03']['players'][self.options['spawn_slots'][slot]]['start']
            self.assertEqual([stations[0].pos.x, stations[0].pos.y, stations[0].pos.z], anchor)
        for _ in range(15):
            first.step(1 / 30)
            second.step(1 / 30)
            self.assertEqual(state_checksum(first.state), state_checksum(second.state))
        self.assertEqual(set(first.ai.ais), set(range(1, 8)))
        restored = GameManager(state=GameState.from_dict(json.loads(json.dumps(first.state.to_dict(precise=True)))))
        self.assertEqual(state_checksum(first.state), state_checksum(restored.state))
        self.assertEqual(first.state.to_dict(precise=True), restored.state.to_dict(precise=True))
        for _ in range(15):
            first.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(state_checksum(first.state), state_checksum(restored.state))

    def test_inactive_source_slots_still_require_safe_spawns_and_loadouts(self):
        source = copy.deepcopy(self.ds.maps['skirmish03'])
        options = dict(self.options, ai_count=1, spawn_slots=[0, 1])
        mutations = (
            lambda p: p.update(slot=True),
            lambda p: p.update(start=[-2800, 0, -2000]),
            lambda p: p.update(start=[0, 0, float('nan')]),
            lambda p: p.update(start=[0, 0, source['bounds']]),
            lambda p: p.update(start_units={'constructor': True}),
        )
        for mutate in mutations:
            self.ds.maps['skirmish03'] = copy.deepcopy(source)
            mutate(self.ds.maps['skirmish03']['players'][7])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, options)

    def test_choice_lengths_and_capacity_bounds_stay_strict(self):
        for key in ('colors', 'factions', 'teams'):
            for length in (0, 3, 4, 7, 9):
                options = copy.deepcopy(self.options)
                options[key] = (options[key] * 2)[:length]
                with self.subTest(key=key, length=length), self.assertRaises(ValueError):
                    build_skirmish_map(self.ds, options)
        for count in (0, 8, True, 7.0, '7', None):
            options = dict(self.options, ai_count=count)
            with self.subTest(count=count), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, options)
        source = self.ds.maps['skirmish03']
        template = copy.deepcopy(source['players'][0])
        for capacity in (0, 1, 9):
            source['players'] = [dict(copy.deepcopy(template), slot=i,
                                      start=[-2800 + i * 600, 0, -2000]) for i in range(capacity)]
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, dict(self.options, ai_count=1))


if __name__ == '__main__':
    unittest.main()
