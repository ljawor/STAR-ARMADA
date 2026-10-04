"""Combat rank vertical regressions (real systems, deterministic fixtures)."""
import unittest

from helpers import make_game
from game.core.vectors import Vec3


class TestShipExperience(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.a = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(0, 0, 0))
        self.t = self.gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 100))

    def hit(self, damage, **kwargs):
        self.gm.damage._apply_damage(self.t, damage, kwargs.pop('shield_mult', 1),
                                    kwargs.pop('armor_mult', 1), 1,
                                    attacker=kwargs.pop('attacker', self.a), **kwargs)

    def test_invalid_xp_sources_and_targets(self):
        for case in ('own', 'allied', 'environment', 'dead', 'station', 'neutral_source'):
            with self.subTest(case=case):
                self.setUp()
                if case == 'own': self.t.owner = 0
                if case == 'allied': self.st.players[1].team = self.st.players[0].team
                if case == 'environment': self.t.owner = -1
                if case == 'dead': self.a.alive = False
                if case == 'station': self.a.is_ship = False; self.a.is_station = True
                if case == 'neutral_source': self.a.owner = -1
                self.hit(10 ** 9)
                self.assertEqual(self.a.xp, 0)

    def test_promotions_share_capped_rank_and_five_percent_power(self):
        from game.systems import stats
        self.gm.ds.rules['experience']['levels'] = [0, 1, 2, 3, 4, 5, 6]
        self.a.xp = 10000
        self.gm.damage._update_level(self.a)
        self.assertEqual(self.a.level, 5)
        self.assertAlmostEqual(stats.effective_weapon_damage(self.st, self.a, 100), 120)
        from game.systems.experience import rank_info, rank_for, max_rank, rank_progress
        info = rank_info(self.a)
        self.assertEqual((rank_for(self.a), max_rank(self.a)), (5, 5))
        self.assertEqual(rank_progress(self.a), 1)
        self.assertIsNone(info['next_threshold'])
        self.gm.ds.rules['experience']['max_effective_level'] = 3
        self.assertEqual(rank_for(self.a), 3)
        self.assertAlmostEqual(stats.effective_weapon_damage(self.st, self.a, 100), 110)

    def test_each_rank_increases_real_attack_and_reduces_incoming_damage(self):
        from game.systems.experience import attack_multiplier, defense_multiplier, rank_for
        from game.systems.stats import effective_weapon_damage
        cfg = self.gm.ds.rules['experience']
        cfg['per_level']['attack_bonus'] = .05
        cfg['per_level']['defense_bonus'] = .05
        scale = self.gm.ds.ships[self.t.data_id].veteran_xp / 100
        for rank, threshold in enumerate(cfg['levels'], 1):
            self.t.xp = threshold * scale
            self.a.xp = threshold * scale
            self.assertEqual(rank_for(self.t), rank)
            self.assertAlmostEqual(attack_multiplier(self.a), 1 + .05 * (rank - 1))
            self.assertAlmostEqual(defense_multiplier(self.t), 1 - .05 * (rank - 1))
            self.assertAlmostEqual(effective_weapon_damage(self.st, self.a, 100),
                                   100 * (1 + .05 * (rank - 1)))
            self.t.shields['front'] = 1000
            before = self.t.shields['front']
            self.hit(10)
            self.assertAlmostEqual(before - self.t.shields['front'], 10 * (1 - .05 * (rank - 1)))
            self.t.shields['front'] = 0
            self.t.hull = self.t.max_hull
            before = self.t.hull
            self.hit(10)
            self.assertAlmostEqual(before - self.t.hull, 10 * (1 - .05 * (rank - 1)))
            # Avoid subsystem damage affecting the next isolated power comparison.
            for sub in self.t.systems.values(): sub.hp = sub.max_hp

    def test_real_projectile_launch_retains_shooter_and_grants_xp(self):
        wd = next(w for w in self.gm.ds.weapons.values() if not w.is_beam)
        self.st.grid.rebuild(self.st.entities)
        self.gm.weapons._launch_projectiles(self.a, self.t, wd, 1)
        self.assertEqual(len(self.st.projectiles), 1)
        projectile = next(iter(self.st.projectiles.values()))
        projectile.pos = self.t.pos.copy()
        projectile.vel = Vec3()
        self.gm.projectiles.update(0)
        self.gm.damage.update(0)
        self.assertGreater(self.a.xp, 0)
        self.assertEqual(projectile.attacker_entity_id, self.a.id)

    def test_json_restore_preserves_projectile_shooter_precision_and_legacy_rank(self):
        import json
        from game.core.state import GameState
        from game.core.world import Projectile
        self.a.xp = 123.456789012345
        self.gm.damage._update_level(self.a)
        self.a.weapon_cooldowns[0] = .123456789012345
        self.a.last_hit_time = .123456789012345
        wd = next(w for w in self.gm.ds.weapons.values() if not w.is_beam)
        self.gm.weapons._launch_projectiles(self.a, self.t, wd, 1)
        data = json.loads(json.dumps(self.st.to_dict(precise=True)))
        restored = GameState.from_dict(data)
        self.assertEqual(restored.entities[self.a.id].weapon_cooldowns,
                         self.a.weapon_cooldowns)
        self.assertEqual(restored.entities[self.a.id].last_hit_time, self.a.last_hit_time)
        p = next(iter(restored.projectiles.values()))
        self.assertEqual(p.attacker_entity_id, self.a.id)
        self.assertEqual(json.loads(json.dumps(restored.to_dict(precise=True))), data)
        legacy = dict(data['entities'][str(self.a.id)])
        legacy['level'] = 99
        self.assertEqual(GameState._entity_from_dict(legacy).level, 2)
        legacy.pop('xp'); legacy.pop('level')
        self.assertEqual(GameState._entity_from_dict(legacy).level, 1)
        old_projectile = p.to_dict(True)
        old_projectile.pop('attacker_entity_id')
        self.assertIsNone(Projectile.from_dict(old_projectile).attacker_entity_id)

    def test_catalogue_caps_are_explicit_loaded_validated_and_default_compatible(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from dataclasses import replace
        from game.systems.experience import max_rank, rank_for
        for path in Path(self.gm.ds.assets_dir, 'ships').glob('*.json'):
            for definition in json.loads(path.read_text())['ships'].values():
                self.assertEqual(definition.get('max_rank'), 5)
        ship = self.gm.ds.ships[self.a.data_id]
        self.a.xp = 1e9
        self.gm.ds.ships[ship.id] = replace(ship, max_rank=2)
        self.assertEqual((rank_for(self.a), max_rank(self.a)), (2, 2))
        for invalid in (0, 6, 2.5, True, '3'):
            self.gm.ds.ships[ship.id] = replace(ship, max_rank=invalid)
            with self.assertRaisesRegex(ValueError, 'max_rank'):
                self.gm.ds._validate()
        self.gm.ds.ships[ship.id] = ship
        raw = json.loads(Path(self.gm.ds.assets_dir, 'ships/imperial.json').read_text())
        raw['ships'][ship.id]['max_rank'] = 2
        with TemporaryDirectory() as tmp:
            path = Path(tmp, 'ships.json')
            path.write_text(json.dumps(raw))
            self.gm.ds._load_ship_file(str(path))
            self.assertEqual(self.gm.ds.ships[ship.id].max_rank, 2)
            raw['ships'][ship.id].pop('max_rank')
            path.write_text(json.dumps(raw))
            self.gm.ds._load_ship_file(str(path))
            self.assertEqual(self.gm.ds.ships[ship.id].max_rank, 5)
            raw['ships'][ship.id]['max_rank'] = 2.5
            path.write_text(json.dumps(raw))
            self.gm.ds._load_ship_file(str(path))
            with self.assertRaisesRegex(ValueError, 'max_rank'):
                self.gm.ds._validate()

    def test_experience_config_rejects_invalid_thresholds_caps_and_bonuses(self):
        from copy import deepcopy
        base = deepcopy(self.gm.ds.rules['experience'])
        for key, value in [('levels', [1, 2]), ('levels', [0, 0]),
                           ('levels', [0, float('nan')]), ('levels', []),
                           ('max_effective_level', True), ('max_effective_level', 6),
                           ('xp_per_damage', -1), ('xp_per_kill_fraction', float('inf'))]:
            self.gm.ds.rules['experience'] = deepcopy(base)
            self.gm.ds.rules['experience'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.gm.ds._validate()
        for key, value in [('attack_bonus', -1), ('defense_bonus', .26), ('attack_bonus', float('nan'))]:
            self.gm.ds.rules['experience'] = deepcopy(base)
            self.gm.ds.rules['experience']['per_level'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.gm.ds._validate()
        self.gm.ds.rules['experience'] = base
        ship = self.gm.ds.ships[self.a.data_id]
        ship.veteran_xp = 0
        with self.assertRaisesRegex(ValueError, 'veteran_xp'):
            self.gm.ds._validate()

    def test_sensor_cache_reacts_immediately_to_per_ship_cap_change(self):
        from game.systems.visibility import SensorQueries
        self.a.xp = 1e9
        queries = SensorQueries(self.st)
        before = queries.radius(self.a)
        self.gm.ds.ships[self.a.data_id].max_rank = 1
        after = queries.radius(self.a)
        self.assertLess(after, before)
        self.assertAlmostEqual(after, self.a.sensor_range)

    def test_real_beam_combat_promotion_matches_exact_json_replay_every_tick(self):
        import json
        from game.core.manager import GameManager
        from game.core.state import GameState
        from game.net.replay import ReplayRecorder, ReplayPlayer, state_checksum
        self.a = self.gm.factory.spawn_ship('imperial_supercapital', 0, Vec3())
        self.t.pos = Vec3(0, 0, 800)
        self.st.entities = {self.a.id: self.a, self.t.id: self.t}
        self.a.order_type = self.t.order_type = 'hold'
        self.a.xp = 480 - .000000123456
        self.a.retarget_cooldown = .234567891234
        self.t.retarget_cooldown = .345678912345
        recorder = ReplayRecorder(self.st)
        replay = json.loads(json.dumps(recorder.to_dict()))
        playback = ReplayPlayer(replay)
        restored = GameManager(GameState.from_dict(replay['initial_state']))
        for tick in range(90):
            for cmd in playback.commands_for_tick(tick): restored.state.queue_command(cmd)
            self.gm.step(1/30)
            restored.step(1/30)
            self.assertEqual(json.loads(json.dumps(self.st.to_dict(precise=True))),
                             json.loads(json.dumps(restored.state.to_dict(precise=True))),
                             f'exact state diverged at tick {tick}')
            self.assertEqual(state_checksum(self.st), state_checksum(restored.state))
        self.assertGreater(self.a.xp, 480)
        self.assertGreaterEqual(self.a.level, 2)

    def test_beam_queue_awards_xp_promotes_and_publishes_one_multi_rank_event(self):
        self.a = self.gm.factory.spawn_ship('imperial_supercapital', 0, Vec3())
        self.gm.ds.rules['experience']['levels'] = [0, .01, .02, .03, .04]
        self.t.pos = Vec3(0, 0, 800)
        self.a.current_target = self.t.id
        self.st.grid.rebuild(self.st.entities)
        self.gm.weapons._ship_weapons(self.a, 0)
        beams = [hit for hit in self.st.damage_queue if hit.get('attacker') is self.a]
        self.assertGreater(len(beams), 0)
        self.gm.damage.update(0)
        self.assertGreater(self.a.xp, 0)
        self.assertEqual(self.a.level, 5)
        promotions = [event for event in self.st.events.log if event.type == 'unit_leveled'
                      and event.data['entity_id'] == self.a.id]
        self.assertEqual(len(promotions), 1)
        self.assertEqual(promotions[0].data['level'], 5)

    def test_projectile_damage_survives_shooter_death_without_awarding_xp(self):
        for case in ('dead', 'removed', 'allied', 'station'):
            with self.subTest(case=case):
                self.setUp()
                wd = next(w for w in self.gm.ds.weapons.values() if not w.is_beam)
                self.gm.weapons._launch_projectiles(self.a, self.t, wd, 1)
                projectile = next(iter(self.st.projectiles.values()))
                projectile.damage = 1e9
                projectile.pos = self.t.pos.copy()
                projectile.vel = Vec3()
                if case == 'dead': self.a.alive = False
                if case == 'removed': self.st.entities.pop(self.a.id)
                if case == 'allied': self.st.players[1].team = self.st.players[0].team
                if case == 'station': self.a.is_ship = False; self.a.is_station = True
                self.st.grid.rebuild(self.st.entities)
                self.gm.projectiles.update(0)
                self.gm.damage.update(0)
                self.assertEqual(self.a.xp, 0)
                self.assertEqual(self.t.alive, case == 'allied')

    def test_rank_progress_scales_thresholds_and_squadron_caps(self):
        from game.systems.experience import rank_info, rank_progress, rank_for, max_rank
        squadron = self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3())
        squadron.xp = 48
        self.assertEqual(rank_for(squadron), 1)
        self.assertEqual(max_rank(squadron), 5)
        self.assertAlmostEqual(rank_progress(squadron), .5)
        self.assertEqual(rank_info(squadron)['next_threshold'], 96)
        squadron.xp = 96
        self.gm.damage._update_level(squadron)
        self.assertEqual(squadron.level, 2)
        self.assertEqual(rank_progress(squadron), 0)
        squadron.xp = 1e9
        self.gm.damage._update_level(squadron)
        self.assertEqual(squadron.level, 5)
        station = self.gm.factory.spawn_station('command_station', 0, Vec3())
        station.xp = 1e9
        self.assertEqual(rank_info(station)['rank'], 1)
        self.assertEqual(rank_info(station)['attack_bonus'], 0)
        self.assertEqual(rank_info(station)['defense_bonus'], 0)

    def test_mod_merge_validates_ship_caps_and_rules_with_legacy_defaults(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch as mock_patch
        from game.data.store import DataStore
        raw = json.loads(Path(self.gm.ds.assets_dir, 'ships/imperial.json').read_text())
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp, 'mods/ranks/data')
            ship_file = data_dir / 'ships/imperial.json'
            ship_file.parent.mkdir(parents=True)
            raw['ships'][self.a.data_id]['max_rank'] = 3
            ship_file.write_text(json.dumps(raw))
            with mock_patch('game.data.store.ROOT', tmp):
                ds = DataStore(assets_dir=self.gm.ds.assets_dir, mods=['ranks'])
                self.assertEqual(ds.ships[self.a.data_id].max_rank, 3)
                raw['ships'][self.a.data_id]['max_rank'] = True
                ship_file.write_text(json.dumps(raw))
                with self.assertRaisesRegex(ValueError, 'max_rank'):
                    DataStore(assets_dir=self.gm.ds.assets_dir, mods=['ranks'])
                raw['ships'][self.a.data_id].pop('max_rank')
                ship_file.write_text(json.dumps(raw))
                ds = DataStore(assets_dir=self.gm.ds.assets_dir, mods=['ranks'])
                self.assertEqual(ds.ships[self.a.data_id].max_rank, 5)
                rules = json.loads(Path(self.gm.ds.assets_dir, 'game_rules.json').read_text())
                rules['experience']['levels'] = [0, 1, 1]
                (data_dir / 'game_rules.json').write_text(json.dumps(rules))
                with self.assertRaisesRegex(ValueError, 'levels'):
                    DataStore(assets_dir=self.gm.ds.assets_dir, mods=['ranks'])

    def test_xp_counts_actual_shield_and_capped_hull_loss(self):
        self.t.shields['front'] = 10
        self.t.hull = 20
        self.hit(1000, shield_mult=2, armor_mult=3)
        cfg = self.gm.ds.rules['experience']
        self.assertAlmostEqual(self.a.xp, 30 * cfg['xp_per_damage'] +
                               self.t.max_hull * cfg['xp_per_kill_fraction'])
