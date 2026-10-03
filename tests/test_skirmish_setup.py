"""Pure setup validation and real headless skirmish integration."""
import copy
import unittest

from game.data.store import DataStore


class TestSkirmishSetup(unittest.TestCase):
    def setUp(self):
        self.ds = DataStore()

    def test_builder_deepcopies_map_and_applies_active_options(self):
        from game.core.skirmish import (PLAYER_COLORS, COLOR_NAMES,
                                       SKIRMISH_MAP_IDS, default_skirmish_options,
                                       build_skirmish_map)
        options = default_skirmish_options(self.ds)
        options.update(colors=['pink', 'cyan', 'green', 'purple'],
                       factions=['syndicate', 'rebel', 'imperial', 'confederacy'],
                       ai_difficulty='hard')
        original = copy.deepcopy(self.ds.maps)
        result = build_skirmish_map(self.ds, options)
        self.assertEqual(SKIRMISH_MAP_IDS, tuple(f'skirmish0{i}' for i in range(1, 5)))
        self.assertEqual(set(COLOR_NAMES), set(PLAYER_COLORS))
        self.assertEqual(len(result['players']), 2)
        for i, p in enumerate(result['players']):
            self.assertEqual(p['slot'], i)
            self.assertEqual(p['team'], i)
            self.assertEqual(p['is_ai'], i > 0)
            self.assertEqual(p['color'], PLAYER_COLORS[options['colors'][i]])
            self.assertEqual(p['faction'], options['factions'][i])
            self.assertIn(self.ds.factions[p['faction']].display_name, p['name'])
            self.assertEqual(p['ai_difficulty'], 'hard')
            self.assertEqual(p['start_units'], original['skirmish01']['players'][i]['start_units'])
        result['players'][0]['start'][0] = 123
        result['asteroid_fields'][0]['pos'][0] = 123
        self.assertEqual(self.ds.maps, original)

    def test_all_four_maps_every_valid_count_real_ai_sixty_ticks(self):
        from game.core.skirmish import (SKIRMISH_MAP_IDS, PLAYER_COLORS,
                                       build_skirmish_map, default_skirmish_options)
        from game.core.manager import GameManager
        capacities = dict(zip(SKIRMISH_MAP_IDS, (2, 3, 4, 4)))
        for map_id, capacity in capacities.items():
            self.assertIn(map_id, self.ds.maps)
            self.assertEqual(len(self.ds.maps[map_id]['players']), capacity)
            for ai_count in range(1, capacity):
                with self.subTest(map_id=map_id, ai_count=ai_count):
                    options = default_skirmish_options(self.ds)
                    options.update(map_id=map_id, ai_count=ai_count,
                                   factions=['imperial', 'rebel', 'confederacy', 'syndicate'])
                    m = build_skirmish_map(self.ds, options)
                    gm = GameManager.start_skirmish(m)
                    st = gm.state
                    self.assertEqual(len(st.players), ai_count + 1)
                    self.assertEqual(sum(p.is_ai for p in st.players.values()), ai_count)
                    self.assertEqual(len({p.color for p in st.players.values()}), ai_count + 1)
                    for pid, p in st.players.items():
                        self.assertEqual(st.allied_player_ids(pid), [pid])
                        self.assertEqual(p.color, PLAYER_COLORS[options['colors'][pid]])
                        own = [e for e in st.entities.values() if e.owner == pid]
                        self.assertTrue(own)
                        self.assertTrue(all(st.can_see(pid, e.id) for e in own))
                        enemies = [e for e in st.entities.values()
                                   if e.owner in st.players and e.owner != pid and e.is_station]
                        self.assertTrue(all(not st.can_see(pid, e.id) for e in enemies))
                    for _ in range(60):
                        gm.step(1 / 30)
                    self.assertEqual(st.tick, 60)
                    self.assertFalse(st.game_over)
                    self.assertEqual(set(gm.ai.ais), set(range(1, ai_count + 1)))
                    for pid, ai in gm.ai.ais.items():
                        self.assertEqual(ai.difficulty(), gm.ds.rules['ai']['difficulty']['normal'])
                        own = [e for e in st.entities.values() if e.owner == pid]
                        self.assertTrue(any(e.build_queue or e.order_type for e in own)
                                        or ai._pending_site,
                                        f'{map_id} AI {pid} never initiated production/expansion')
            if capacity < 4:
                options = default_skirmish_options(self.ds)
                options.update(map_id=map_id, ai_count=capacity)
                with self.assertRaises(ValueError):
                    build_skirmish_map(self.ds, options)

    def test_custom_colors_exact_json_restore_checksum(self):
        import json
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import state_checksum
        options = default_skirmish_options(self.ds)
        options['colors'] = ['orange', 'pink', 'yellow', 'cyan']
        gm = GameManager.start_skirmish(build_skirmish_map(self.ds, options))
        for _ in range(60):
            gm.step(1 / 30)
        restored = GameManager(state=GameState.from_dict(json.loads(
            json.dumps(gm.state.to_dict(precise=True)))))
        self.assertEqual([p.color for p in gm.state.players.values()],
                         [p.color for p in restored.state.players.values()])
        self.assertEqual(state_checksum(gm.state), state_checksum(restored.state))
        # Replay checksum omits cosmetic colors: explicitly check exact player
        # serialization as well, rather than allowing a checksum false positive.
        self.assertEqual(gm.state.to_dict(precise=True)['players'],
                         restored.state.to_dict(precise=True)['players'])

    def test_difficulty_changes_real_income_and_ai_decisions(self):
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        from game.core.manager import GameManager
        income = {}
        for difficulty in ['easy', 'normal', 'hard']:
            options = default_skirmish_options(self.ds)
            options['ai_difficulty'] = difficulty
            gm = GameManager.start_skirmish(build_skirmish_map(self.ds, options))
            gm.economy.update(1 / 30)
            income[difficulty] = gm.state.players[1].income_frame['credits']
            gm.ai.ensure()
            self.assertEqual(gm.ai.ais[1].difficulty(),
                             gm.ds.rules['ai']['difficulty'][difficulty])
        self.assertLess(income['easy'], income['normal'])
        self.assertLess(income['normal'], income['hard'])

    def test_all_factions_starting_loadout_and_missing_classes_graceful(self):
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        from game.core.manager import GameManager
        prefixes = {'imperial': 'imperial', 'rebel': 'rebel',
                    'confederacy': 'confed', 'syndicate': 'syndicate'}
        for faction, prefix in prefixes.items():
            options = default_skirmish_options(self.ds)
            options['factions'] = [faction] * 4
            m = build_skirmish_map(self.ds, options)
            gm = GameManager.start_skirmish(m)
            for pid in gm.state.players:
                units = [e for e in gm.state.entities.values() if e.owner == pid]
                self.assertEqual(len(units), sum(m['players'][pid]['start_units'].values()))
                self.assertEqual({e.data_id for e in units if e.is_station},
                                 {'command_station', 'shipyard'})
                self.assertTrue(all(e.data_id.startswith(prefix) for e in units if not e.is_station))
                self.assertEqual(sum(e.is_construction for e in units), 1)
            if faction == 'syndicate':
                m['players'][0]['start_units'].update(colonizer=1, battleship=1, supercapital=1)
                # Unavailable syndicate hull classes are deliberately skipped.
                gm = GameManager.start_skirmish(m)
                self.assertEqual(len([e for e in gm.state.entities.values() if e.owner == 0]), 7)

    def test_invalid_options_raise_valueerror_without_mutation(self):
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        original = copy.deepcopy(self.ds.maps)
        invalid = [
            {'map_id': 'campaign01'}, {'map_id': []},
            *({'ai_count': x} for x in [0, 4, True, 1.0, '1', None]),
            {'ai_count': 2}, {'ai_difficulty': 'legendary'}, {'ai_difficulty': []},
            {'colors': ['red']}, {'colors': 'blue'},
            {'colors': ['red', 'red', 'green', 'purple']},
            {'colors': ['unknown', 'red', 'green', 'purple']},
            {'colors': [[], 'red', 'green', 'purple']},
            {'factions': ['unknown', 'imperial', 'imperial', 'imperial']},
            {'factions': ['imperial']}, {'factions': [[], 'imperial', 'imperial', 'imperial']},
        ]
        for overrides in invalid:
            options = default_skirmish_options(self.ds)
            options.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, options)
        for options in [None, [], {}, {'map_id': 'skirmish01'}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, options)
        self.assertEqual(self.ds.maps, original)

    def test_inactive_choices_ignored_but_four_slots_required(self):
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        options = default_skirmish_options(self.ds)
        options['colors'][2:] = ['red', None]
        options['factions'][2:] = [None, 'missing']
        self.assertEqual(len(build_skirmish_map(self.ds, options)['players']), 2)

    def test_malformed_map_capacity_slots_spawns_bounds_loadouts_rejected(self):
        from game.core.skirmish import build_skirmish_map, default_skirmish_options
        original = copy.deepcopy(self.ds.maps['skirmish01'])
        mutations = [
            lambda m: m.update(bounds=0), lambda m: m.update(bounds=float('inf')),
            lambda m: m.update(bounds=True), lambda m: m.update(bounds=10 ** 1000),
            lambda m: m.update(players=[]),
            lambda m: m['players'][1].update(slot=0),
            lambda m: m['players'][1].update(slot=True),
            lambda m: m['players'][1].update(start=m['players'][0]['start'][:]),
            lambda m: m['players'][1].update(start=[999999, 0, 0]),
            lambda m: m['players'][1].update(start=[0, float('nan'), 0]),
            lambda m: m['players'][1].update(start=[0, 0]),
            lambda m: m['players'][1].update(start=['0', 0, 0]),
            lambda m: m['players'][1].update(start_units={'constructor': -1}),
            lambda m: m['players'][1].update(start_units={'missing': 1}),
            lambda m: m['players'][1].update(start_units={'constructor': True}),
        ]
        for mutate in mutations:
            self.ds.maps['skirmish01'] = copy.deepcopy(original)
            mutate(self.ds.maps['skirmish01'])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                build_skirmish_map(self.ds, default_skirmish_options(self.ds))

    def test_explicit_color_and_invalid_campaign_fallback(self):
        from game.core.manager import GameManager
        original = self.ds.maps['skirmish01']
        fallback = GameManager.start_skirmish(original).state.players[0].color
        for color in [(0.9, 0.1, 0.7), [0, 1, 0.5]]:
            m = copy.deepcopy(original)
            m['players'][0]['color'] = color
            self.assertEqual(GameManager.start_skirmish(m).state.players[0].color, tuple(color))
        for color in [None, [], [1, 2, 0], [10 ** 1000, 0, 0], [True, 0, 0], ['0', 0, 0],
                      [0, float('nan'), 0], [0, float('inf'), 0], [0, 0, 0, 0]]:
            m = copy.deepcopy(original)
            m['players'][0]['color'] = color
            with self.subTest(color=color):
                self.assertEqual(GameManager.start_skirmish(m).state.players[0].color, fallback)
