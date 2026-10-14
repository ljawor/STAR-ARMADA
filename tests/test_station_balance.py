"""Station balance (#106): the player-editable overlay, its gates and its file.

The issue asks for a Game Balance screen where each station of a chosen faction can be
retuned (how much a refit gains per level) and where a station level can be required
before a given hull may be built, with the configuration surviving application updates.

These tests hold the overlay's schema (lenient from disk, strict from the wire), its
fold into the live rules a match reads, the per-station gains reaching both the capacity
a refit actually grants and the panel that describes it, the per-level build gate, and
the file that survives an update because it lives in the user data directory.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import make_game
from game.core.commands import PlayerCommand, UpgradeStationCommand
from game.data import balance
from game.data.store import DataStore
from game.systems import construction, upgrades
from render import menus

DT = 1 / 30

YARD_KINDS = ('command_station', 'mining_station', 'shipyard', 'research_station',
              'defense_platform', 'sensor_station', 'trade_station', 'fighter_platform',
              'repair_dock', 'energy_relay')


def tuned(**sections) -> dict:
    config = balance.defaults()
    config.update(sections)
    return config


class BalanceSchemaTests(unittest.TestCase):
    """The two readers of one shape: forgiving on disk, strict over the wire."""

    def test_an_empty_or_absent_file_reads_as_shipped_values(self):
        for raw in ({}, balance.defaults(), None, [], 'nonsense', 3):
            with self.subTest(raw=raw):
                self.assertEqual(balance.normalize(raw), balance.defaults())
                self.assertTrue(balance.is_default(balance.normalize(raw)))

    def test_a_newer_schema_is_not_guessed_at(self):
        """A file from a future build is ignored whole, never half-read."""
        future = {'version': 99, 'station_upgrades': {'shipyard': {'hull_bonus': 0.5}},
                  'build_levels': {'shipyard': {'imperial_corvette': 2}}}
        self.assertEqual(balance.normalize(future), balance.defaults())
        with self.assertRaisesRegex(ValueError, 'version'):
            balance.validate(future)

    def test_a_hand_edit_drops_only_the_entry_it_could_not_read(self):
        raw = {'version': 1,
               'station_upgrades': {'shipyard': {'hull_bonus': 0.2, 'nonsense': 1,
                                                 'shield_bonus': -1, 'damage_bonus': 'high'},
                                     'sensor_station': 'not an object'},
               'build_levels': {'shipyard': {'imperial_corvette': 3, 'imperial_frigate': 1,
                                             'imperial_cruiser': 9, 'imperial_battleship': 'two'}}}
        clean = balance.normalize(raw)
        self.assertEqual(clean['station_upgrades'], {'shipyard': {'hull_bonus': 0.2}})
        self.assertEqual(clean['build_levels'], {'shipyard': {'imperial_corvette': 3}})

    def test_the_strict_reader_refuses_what_the_lenient_one_drops(self):
        for raw, pattern in (
                ({'version': 1, 'station_upgrades': {'x': {'hull_bonus': -0.5}}}, 'hull_bonus'),
                ({'version': 1, 'station_upgrades': {'x': {'nonsense': 1}}}, 'unknown upgrade gain'),
                ({'version': 1, 'station_upgrades': {'x': {'volley_shots_per_level': 1.5}}},
                 'volley_shots_per_level'),
                ({'version': 1, 'build_levels': {'x': {'ship': 1}}}, 'from 2 to 5'),
                ({'version': 1, 'build_levels': {'x': {'ship': 6}}}, 'from 2 to 5'),
                ({'version': 1, 'build_levels': {'x': {'ship': True}}}, 'from 2 to 5'),
                ({'version': 1, 'station_upgrades': {'x': {'hull_bonus': float('inf')}}},
                 'hull_bonus')):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, pattern):
                    balance.validate(raw)

    def test_a_gain_above_the_ceiling_is_not_a_win_button(self):
        """A typo must not turn a refit into an instant win; the bound is enforced."""
        self.assertEqual(balance.normalize(
            {'version': 1, 'station_upgrades': {'x': {'hull_bonus': 11.0}}})['station_upgrades'], {})
        self.assertEqual(balance.normalize(
            {'version': 1, 'station_upgrades': {'x': {'hull_bonus': 10.0}}})['station_upgrades'],
            {'x': {'hull_bonus': 10.0}})
        self.assertEqual(balance.normalize(
            {'version': 1, 'station_upgrades': {'x': {'volley_shots_per_level': 101}}}
        )['station_upgrades'], {})
        self.assertEqual(balance.normalize(
            {'version': 1, 'station_upgrades': {'x': {'volley_shots_per_level': 4}}})['station_upgrades'],
            {'x': {'volley_shots_per_level': 4}})

    def test_reading_never_mutates_the_caller_s_config(self):
        raw = tuned(station_upgrades={'shipyard': {'hull_bonus': 0.2, 'junk': 1}})
        before = json.dumps(raw, sort_keys=True)
        balance.validate(balance.normalize(raw))
        self.assertEqual(json.dumps(raw, sort_keys=True), before)

    def test_the_digest_identity_follows_the_readable_config_only(self):
        self.assertEqual(balance.digest(tuned(station_upgrades={'a': {'hull_bonus': 0.2}})),
                         balance.digest({'station_upgrades': {'a': {'hull_bonus': 0.2}},
                                         'build_levels': {}, 'version': 1}))
        self.assertEqual(balance.digest({}), balance.digest(balance.defaults()))
        self.assertNotEqual(balance.digest({}),
                            balance.digest(tuned(station_upgrades={'a': {'hull_bonus': 0.2}})))


class BalanceRuleTests(unittest.TestCase):
    """The overlay reaching the numbers a match actually reads."""

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = self.gm.ds
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = self.player.energy = self.player.crew = 100000
        self.observer = next(e for e in self.st.entities.values()
                             if e.owner == 0 and e.is_ship)
        self.addCleanup(balance.set_active, None)

    def spawn(self, kind, away=400):
        from game.core.vectors import Vec3
        return self.gm.factory.spawn_station(kind, 0, self.observer.pos + Vec3(0, 0, away))

    # ---------------------------------------------------------------- the fold
    def test_a_catalogue_carries_both_overlay_sections_even_when_empty(self):
        """An absent key and an empty one must hash identically, or identical peers differ."""
        self.assertEqual(self.ds.rules[balance.RULES_KEY], {})
        self.assertEqual(self.ds.rules[balance.BUILD_LEVEL_RULES_KEY], {})
        self.assertNotIn(balance.RULES_KEY, self.ds.base_rules)

    def test_the_shipped_catalogue_is_untouched_when_nothing_is_tuned(self):
        self.assertTrue(balance.is_default(self.ds.balance))
        self.assertEqual(upgrades.station_rules(self.spawn('shipyard'), ds=self.ds)['hull_bonus'],
                         upgrades.DEFAULTS['hull_bonus'])

    def test_an_overlay_reaches_the_live_rules_it_was_built_with(self):
        DataStore.reset()
        store = DataStore(balance=tuned(station_upgrades={'shipyard': {'hull_bonus': 0.2}}))
        self.addCleanup(DataStore.reset)
        self.assertEqual(store.rules[balance.RULES_KEY], {'shipyard': {'hull_bonus': 0.2}})
        self.assertEqual(upgrades.station_rules(self.spawn('shipyard'), ds=store)['hull_bonus'], 0.2)
        # The sibling station keeps the shipped gain: overrides are per type, not global.
        self.assertEqual(upgrades.station_rules(self.spawn('mining_station'), ds=store)['hull_bonus'],
                         upgrades.DEFAULTS['hull_bonus'])

    def test_an_explicit_table_is_never_folded_with_file_overrides(self):
        """The established way to retune under test must stay in control of the numbers."""
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.9}}
        station = self.spawn('shipyard')
        patched = dict(upgrades.upgrade_rules(self.ds), hull_bonus=0.01)
        self.assertEqual(upgrades.station_rules(station, patched, self.ds)['hull_bonus'], 0.01)

    def test_a_retuned_gain_is_what_the_refit_actually_grants(self):
        """Hull capacity is scaled on completion — by the player's gain, not the shipped one."""
        station = self.spawn('shipyard')
        station.max_hull = station.hull = 10000.0
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.5}}
        self.assertTrue(upgrades.apply_level(self.st, station, {'level': 2}))
        self.assertAlmostEqual(station.max_hull, 15000.0, places=3)
        self.assertAlmostEqual(upgrades.hull_multiplier(station, ds=self.ds), 1.5, places=6)

    def test_the_panel_describes_the_same_gain_the_simulation_applies(self):
        station = self.spawn('shipyard')
        station.max_hull = station.hull = 10000.0
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.5,
                                                         'volley_shots_per_level': 3}}
        self.assertTrue(upgrades.apply_level(self.st, station, {'level': 3}))
        table = upgrades.bonus_table(station, self.ds)
        self.assertAlmostEqual(table['hull_bonus'], 1.0, places=6)      # two steps of +50%
        self.assertEqual(table['extra_shots'], 6)                       # two steps of three
        self.assertAlmostEqual(station.max_hull / 10000.,
                               upgrades.hull_multiplier(station, ds=self.ds), places=6)

    def test_a_ship_and_a_planet_are_unaffected_by_a_station_overlay(self):
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.5}}
        ship = self.observer
        self.assertEqual(upgrades.hull_multiplier(ship, ds=self.ds), 1.0)
        self.assertEqual(upgrades.extra_shots(ship, ds=self.ds), 0)

    # ------------------------------------------------------------ the row sets
    def test_the_rows_offered_match_what_the_hull_uses(self):
        self.assertEqual(balance.bonus_rows(self.ds, 'shipyard'),
                         ('hull_bonus', 'shield_bonus', 'shield_regen_bonus',
                          'damage_bonus', 'volley_shots_per_level'))
        self.assertEqual(balance.bonus_rows(self.ds, 'sensor_station'),
                         ('hull_bonus', 'shield_bonus', 'shield_regen_bonus'))
        self.assertEqual(balance.bonus_rows(self.ds, 'mining_station'),
                         ('hull_bonus', 'shield_bonus', 'shield_regen_bonus',
                          'production_bonus', 'convoy_cargo_bonus', 'convoy_per_two_levels'))

    def test_a_faction_lists_the_stations_its_builders_can_lay_down(self):
        imperial = balance.faction_station_types(self.ds, 'imperial')
        self.assertEqual(set(imperial), set(YARD_KINDS))
        self.assertNotIn('defense_satellite', imperial)
        self.assertNotIn('planet_extractor', imperial)
        # A reduced catalogue is not a full one: the syndicate fields four of the ten.
        self.assertEqual(set(balance.faction_station_types(self.ds, 'syndicate')),
                         {'mining_station', 'trade_station', 'defense_platform', 'energy_relay'})
        self.assertEqual(imperial, tuple(s for s in self.ds.stations if s in imperial))

    # ------------------------------------------------------------- the build gate
    def test_the_panel_expansion_and_the_simulation_gate_agree(self):
        """One expansion: nothing the sim refuses may be offered, nothing offered refused."""
        for station_id in self.ds.stations:
            holder = type('S', (), {'data_id': station_id, 'owner': 0})()
            offered = set(construction.buildable_ship_ids(self.ds, station_id, self.player.faction))
            accepted = {sid for sid in self.ds.ships
                        if self.gm.construction.station_can_build_ship(holder, sid)}
            with self.subTest(station=station_id):
                self.assertEqual(offered, accepted)

    def test_the_catalogue_gate_still_refuses_what_it_always_refused(self):
        player = self.gm.construction
        yard = type('S', (), {'data_id': 'shipyard', 'owner': 0})()
        command = type('S', (), {'data_id': 'command_station', 'owner': 0})()
        self.assertTrue(player.station_can_build_ship(yard, 'imperial_corvette'))
        self.assertFalse(player.station_can_build_ship(yard, 'rebel_corvette'))
        self.assertFalse(player.station_can_build_ship(yard, 'imperial_constructor'))
        self.assertTrue(player.station_can_build_ship(command, 'imperial_constructor'))
        self.assertTrue(player.station_can_build_ship(command, 'imperial_colonizer'))
        self.assertFalse(player.station_can_build_ship(yard, 'imperial_colonizer'))
        self.assertFalse(player.station_can_build_ship(
            type('S', (), {'data_id': 'mining_station', 'owner': 0})(), 'imperial_corvette'))

    def test_a_gain_override_never_moves_a_build_gate(self):
        holder = type('S', (), {'data_id': 'shipyard', 'owner': 0})()
        before = [sid for sid in self.ds.ships
                  if self.gm.construction.station_can_build_ship(holder, sid)]
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.5, 'damage_bonus': 1.0}}
        after = [sid for sid in self.ds.ships
                 if self.gm.construction.station_can_build_ship(holder, sid)]
        self.assertEqual(before, after)

    def test_a_configured_level_gates_the_hull_until_the_refit_lands(self):
        station = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        self.assertEqual(construction.required_level(self.ds, 'shipyard', 'imperial_cruiser'), 2)
        self.assertEqual(construction.required_level(self.ds, 'shipyard', 'imperial_corvette'), 1)
        self.assertFalse(self.gm.construction.station_can_build_ship(station, 'imperial_cruiser'))
        self.assertTrue(self.gm.construction.station_can_build_ship(station, 'imperial_corvette'))
        # Still offered as a row — the level is stated, not hidden — but not buildable.
        self.assertIn('imperial_cruiser',
                      construction.buildable_ship_ids(self.ds, 'shipyard', 'imperial'))
        station.upgrade_level = 2
        self.assertTrue(self.gm.construction.station_can_build_ship(station, 'imperial_cruiser'))

    def test_the_gated_hull_cannot_be_queued_and_nothing_is_paid_for_it(self):
        station = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 3}}
        before = (self.player.credits, self.player.materials, self.player.energy)
        self.assertEqual(self.gm.construction.start_ship(station.id, 'imperial_cruiser', 0), 0)
        self.assertEqual((self.player.credits, self.player.materials, self.player.energy), before)
        self.assertEqual(station.build_queue, [])

    def test_the_gate_reaches_the_queued_human_intent(self):
        """The command seam pays the same price the panel quoted, so it must gate identically."""
        station = self.spawn('shipyard')
        self.player.credits = self.player.materials = self.player.energy = 100000
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        self.st.queue_command(PlayerCommand("build_ship", 0, unit_ids=(station.id,),
                                             ship_id='imperial_cruiser', name='1'))
        self.gm.step(DT)
        self.assertEqual(station.build_queue, [])
        station.upgrade_level = 2
        self.st.queue_command(PlayerCommand("build_ship", 0, unit_ids=(station.id,),
                                             ship_id='imperial_cruiser', name='1'))
        self.gm.step(DT)
        self.assertEqual([w['item'] for w in station.build_queue], ['imperial_cruiser'])

    def test_a_gate_above_the_ladder_is_unrepresentable(self):
        self.assertNotIn('shipyard', balance.normalize(
            {'version': 1, 'build_levels': {'shipyard': {'imperial_cruiser': 6}}})['build_levels'])
        self.assertEqual(balance.normalize(
            {'version': 1, 'build_levels': {'shipyard': {'imperial_cruiser': 5}}})['build_levels'],
            {'shipyard': {'imperial_cruiser': 5}})

    def test_the_store_refuses_an_overlay_no_screen_could_have_produced(self):
        """A mod ships rules through the same key; the ceilings apply to it too."""
        for overlay, pattern in (({'shipyard': {'hull_bonus': 99.0}}, 'hull_bonus'),
                                 ({'shipyard': {'nonsense': 1}}, 'unknown upgrade gain')):
            with self.subTest(overlay=overlay):
                self.ds.rules[balance.RULES_KEY] = overlay
                with self.assertRaisesRegex(ValueError, pattern):
                    self.ds._validate()
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.2}}
        self.ds._validate()

    def test_a_refit_still_costs_the_shipped_price_when_a_gain_is_retuned(self):
        """Gains are the player's to tune; the ladder's cost and time are not (this change)."""
        station = self.spawn('shipyard')
        before = upgrades.upgrade_cost(station, self.ds)
        self.ds.rules[balance.RULES_KEY] = {'shipyard': {'hull_bonus': 0.5}}
        self.assertEqual(upgrades.upgrade_cost(station, self.ds), before)


class BalanceRecordingTests(unittest.TestCase):
    """A recording pins the numbers it was made with, so it cannot be replayed differently."""

    def test_a_replay_digest_separates_two_different_overlays(self):
        from game.net.replay import content_digest
        DataStore.reset()
        plain = DataStore()
        self.addCleanup(DataStore.reset)
        self.assertEqual(content_digest(plain), content_digest(DataStore()))
        DataStore.reset()
        tuned_store = DataStore(balance=tuned(station_upgrades={'shipyard': {'hull_bonus': 0.2}}))
        self.assertNotEqual(content_digest(plain), content_digest(tuned_store))

    def test_the_lan_content_hash_ignores_the_overlay_it_exchanges_separately(self):
        """Two peers with different balance files must still recognise the same catalogue."""
        from game.net.lan import content_hash
        DataStore.reset()
        plain = DataStore()
        self.addCleanup(DataStore.reset)
        self.assertEqual(content_hash(plain), content_hash(DataStore()))
        DataStore.reset()
        other = DataStore(balance=tuned(station_upgrades={'shipyard': {'hull_bonus': 0.2}}))
        self.assertEqual(content_hash(plain), content_hash(other))

    def test_an_installed_overlay_is_what_later_catalogues_carry(self):
        config = tuned(build_levels={'shipyard': {'imperial_cruiser': 2}})
        balance.set_active(config)
        self.addCleanup(balance.set_active, None)
        DataStore.reset()
        store = DataStore()
        self.addCleanup(DataStore.reset)
        self.assertEqual(store.rules[balance.BUILD_LEVEL_RULES_KEY],
                         {'shipyard': {'imperial_cruiser': 2}})
        self.assertEqual(store.balance, config)

    def test_an_explicit_overlay_wins_over_the_installed_one_for_one_catalogue(self):
        """A LAN client adopting the host's numbers must not change its own file."""
        balance.set_active(tuned(station_upgrades={'shipyard': {'hull_bonus': 0.9}}))
        self.addCleanup(balance.set_active, None)
        DataStore.reset()
        adopted = DataStore(balance=tuned(station_upgrades={'shipyard': {'hull_bonus': 0.1}}))
        self.addCleanup(DataStore.reset)
        self.assertEqual(adopted.rules[balance.RULES_KEY], {'shipyard': {'hull_bonus': 0.1}})
        self.assertEqual(balance.active()['station_upgrades'], {'shipyard': {'hull_bonus': 0.9}})


class BalanceFileTests(unittest.TestCase):
    """The file that survives an update: written to user data, never to the bundle."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='star_armada_balance_')
        self.path = os.path.join(self.root, 'saves', 'balance.json')
        patch = mock.patch.multiple(menus, BALANCE_PATH=self.path)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(balance.set_active, None)

    def test_an_absent_file_reads_as_shipped_values_and_writes_nothing(self):
        self.assertEqual(menus.load_balance(), balance.defaults())
        self.assertFalse(os.path.exists(self.path))

    def test_a_round_trip_survives_a_new_catalogue_with_the_same_numbers(self):
        config = tuned(station_upgrades={'shipyard': {'hull_bonus': 0.25}},
                       build_levels={'shipyard': {'imperial_cruiser': 2}})
        self.assertTrue(menus.save_balance(config))
        self.assertEqual(menus.load_balance(), config)
        DataStore.reset()
        store = DataStore()
        self.addCleanup(DataStore.reset)
        self.assertEqual(store.rules[balance.RULES_KEY], {'shipyard': {'hull_bonus': 0.25}})
        self.assertEqual(construction.required_level(store, 'shipyard', 'imperial_cruiser'), 2)

    def test_a_save_installs_the_overlay_for_the_next_match_without_a_restart(self):
        self.assertTrue(menus.save_balance(tuned(station_upgrades={'shipyard': {'hull_bonus': 0.3}})))
        self.assertEqual(balance.active()['station_upgrades'], {'shipyard': {'hull_bonus': 0.3}})

    def test_a_corrupt_file_reads_as_shipped_values_rather_than_stopping_the_game(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for text in ('{ not json', '[]', '{"version": 42}', '{"station_upgrades": 7}'):
            with self.subTest(text=text):
                with open(self.path, 'w') as f:
                    f.write(text)
                self.assertEqual(menus.load_balance(), balance.defaults())

    def test_a_config_that_could_not_have_come_from_the_screen_is_refused_unwritten(self):
        self.assertTrue(menus.save_balance(tuned(station_upgrades={'shipyard': {'hull_bonus': 0.2}})))
        with open(self.path) as f:
            good = json.load(f)
        self.assertFalse(menus.save_balance(tuned(station_upgrades={'shipyard': {'hull_bonus': 99.0}})))
        self.assertFalse(menus.save_balance('not a config'))
        with open(self.path) as f:
            self.assertEqual(json.load(f), good)               # the last good file stands


class BalancePathTests(unittest.TestCase):
    """The rule the update-safety requirement rests on: writable is never the bundle.

    Deliberately outside the patched fixture above: this is about the real constants, and a
    temporary path would make the assertion vacuous.
    """

    def test_the_file_lives_beside_settings_and_campaign_in_user_data(self):
        self.assertEqual(menus.BALANCE_PATH, os.path.join(menus.SAVES_DIR, 'balance.json'))
        self.assertEqual(menus.SAVES_DIR, os.path.join(menus.USER_DIR, 'saves'))
        self.assertEqual(os.path.dirname(menus.SETTINGS_PATH), menus.SAVES_DIR)
        self.assertEqual(os.path.dirname(menus.CAMPAIGN_PATH), menus.SAVES_DIR)


class BalanceRefitFlowTests(unittest.TestCase):
    """A tuned station still buys, completes and saves like an untuned one."""

    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = self.gm.ds
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = self.player.energy = self.player.crew = 100000
        self.observer = next(e for e in self.st.entities.values()
                             if e.owner == 0 and e.is_ship)
        self.addCleanup(balance.set_active, None)

    def test_a_tuned_station_completes_a_refit_and_persists_its_level(self):
        from game.core.vectors import Vec3
        from helpers import run_until
        station = self.gm.factory.spawn_station('mining_station', 0,
                                                self.observer.pos + Vec3(0, 0, 400))
        self.ds.rules[balance.RULES_KEY] = {'mining_station': {'production_bonus': 0.3}}
        self.st.queue_command(UpgradeStationCommand(0, station.id))
        run_until(self.gm, lambda: upgrades.station_level(station) >= 2, limit_seconds=300)
        self.assertEqual(station.upgrade_level, 2)
        self.assertAlmostEqual(upgrades.production_multiplier(station, ds=self.ds), 1.3, places=6)
        graph = self.st.to_dict(precise=True)
        self.assertIn('upgrade_level', json.dumps(graph))
