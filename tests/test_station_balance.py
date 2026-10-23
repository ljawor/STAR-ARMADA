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
import socket
import tempfile
import time
import unittest
from unittest import mock

import pygame

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
        # Every faction fields the full catalogue it can lay down; the Syndicate's
        # four-station list was a leftover restriction, not a faction trait (owner report:
        # "my constructor can only build those stations - where is the rest?").
        self.assertEqual(set(balance.faction_station_types(self.ds, 'syndicate')),
                         set(YARD_KINDS))
        self.assertEqual(imperial, tuple(s for s in self.ds.stations if s in imperial))

    # ------------------------------------------------------------- the build gate
    def test_the_panel_expansion_and_the_simulation_gate_agree(self):
        """One expansion: the panel offers the catalogue, the sim refuses the gates on top.

        Both halves are asserted with a gate in place, because a gate is the only thing that can
        make them disagree: the panel must keep offering the hull (it is drawn locked), while the
        simulation refuses it until the refit lands and accepts it the moment it does.
        """
        for station_id in self.ds.stations:
            holder = type('S', (), {'data_id': station_id, 'owner': 0, 'upgrade_level': 1})()
            offered = set(construction.buildable_ship_ids(self.ds, station_id, self.player.faction))
            accepted = {sid for sid in self.ds.ships
                        if self.gm.construction.station_can_build_ship(holder, sid)}
            with self.subTest(station=station_id):
                self.assertEqual(offered, accepted)
                self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {
                    station_id: {sid: 2 for sid in offered}}
                try:
                    self.assertEqual(
                        set(construction.buildable_ship_ids(self.ds, station_id,
                                                            self.player.faction)), offered)
                    self.assertEqual({sid for sid in self.ds.ships
                                      if self.gm.construction.station_can_build_ship(holder, sid)},
                                     set())
                    refitted = type('S', (), {'data_id': station_id, 'owner': 0,
                                              'upgrade_level': 2})()
                    self.assertEqual({sid for sid in self.ds.ships
                                      if self.gm.construction.station_can_build_ship(refitted, sid)},
                                     offered)
                finally:
                    self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {}

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
        # Installed *and* folded: the claim is that the next match runs these numbers, and the
        # match reads them off its own catalogue's rules, not off the process-wide overlay.
        DataStore.reset()
        self.addCleanup(DataStore.reset)
        store = DataStore()
        self.assertEqual(balance.station_overrides(store.rules, 'shipyard'), {'hull_bonus': 0.3})
        self.assertEqual(store.balance['station_upgrades'], {'shipyard': {'hull_bonus': 0.3}})

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


class BalanceBuildRowTests(unittest.TestCase):
    """The panel a player reads a gate off: the hull stays, the button does not (#106).

    A gate that hides its hull is indistinguishable from a bug — the player tuned the
    level, so the panel has to say which level it is waiting for, on the row itself.
    """

    def setUp(self):
        import pygame
        from render.hud import HUD
        self.addCleanup(balance.set_active, None)
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = self.gm.ds
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = self.player.energy = self.player.crew = 100000
        self.observer = next(e for e in self.st.entities.values()
                             if e.owner == 0 and e.is_ship)
        self.hud = HUD(1280, 800, self.st)
        self.hud._cur_panel = pygame.Rect(940, 90, 320, 620)
        self.hud._cur_player = self.player

    def spawn(self, kind, away=400):
        from game.core.vectors import Vec3
        return self.gm.factory.spawn_station(kind, 0, self.observer.pos + Vec3(0, 0, away))

    def draw_rows(self, yard):
        """Draw every ship row of a yard panel; returns the buttons it registered."""
        items = self.hud._shipyard_items(yard, self.ds.stations[yard.data_id])
        self.hud.buttons.clear()
        for row, sd in enumerate(items):
            self.hud._row_build_ship(sd, row * 54,
                                     {'shipyard_id': yard.id, 'ship_id': sd.id})
        return items, list(self.hud.buttons)

    def test_a_gated_hull_is_listed_and_states_the_level_it_wants(self):
        from render import hud as hud_module
        yard = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        items, buttons = self.draw_rows(yard)
        self.assertIn('imperial_cruiser', [sd.id for sd in items])
        self.assertEqual([b['payload']['ship_id'] for b in buttons
                          if b['payload']['ship_id'] == 'imperial_cruiser'], [])
        asked = []
        real_t = hud_module.i18n.t

        def recorder(text, **fields):
            asked.append((text, fields))
            return real_t(text, **fields)

        hud_module.i18n.t = recorder
        try:
            self.draw_rows(yard)
        finally:
            hud_module.i18n.t = real_t
        self.assertIn(('Refit level {level} required', {'level': 2}), asked)

    def test_the_same_row_becomes_buildable_once_the_refit_lands(self):
        """The in-test control: the gate is what withheld the button, not the fixture."""
        yard = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        _items, before = self.draw_rows(yard)
        yard.upgrade_level = 2
        _items, after = self.draw_rows(yard)
        self.assertNotIn('imperial_cruiser', [b['payload']['ship_id'] for b in before])
        self.assertIn('imperial_cruiser', [b['payload']['ship_id'] for b in after])

    def test_an_ungated_panel_is_untouched_by_the_gate_machinery(self):
        yard = self.spawn('shipyard')
        _items, buttons = self.draw_rows(yard)
        self.assertIn('imperial_cruiser', [b['payload']['ship_id'] for b in buttons])


class BalanceAiGateTests(unittest.TestCase):
    """An AI met by a gate it can pay for buys the level instead of going quiet (#106)."""

    def setUp(self):
        from game.ai.ai import AIPlayer
        self.addCleanup(balance.set_active, None)
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.ds = self.gm.ds
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = self.player.energy = self.player.crew = 100000
        self.observer = next(e for e in self.st.entities.values())
        self.ai = AIPlayer(self.st, 0)

    def spawn(self, kind, away=400):
        from game.core.vectors import Vec3
        return self.gm.factory.spawn_station(kind, 0, self.observer.pos + Vec3(0, 0, away))

    def queued(self):
        return [c for c in self.st.command_queue if c.player == 0]

    def test_the_ai_orders_the_refit_a_gated_hull_needs(self):
        yard = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        self.st.command_queue.clear()
        self.ai._queue_ship(yard, 'imperial_cruiser', 1)
        pending = self.queued()
        self.assertEqual([c.type for c in pending], ['upgrade_station'])
        self.assertEqual(pending[0].target_id, yard.id)
        self.assertFalse(any(c.type == 'build_ship' for c in self.st.command_queue))

    def test_the_refit_is_ordered_once_and_then_the_hull_is(self):
        yard = self.spawn('shipyard')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'shipyard': {'imperial_cruiser': 2}}
        self.st.command_queue.clear()
        self.ai._queue_ship(yard, 'imperial_cruiser', 1)
        self.assertEqual(len(self.queued()), 1)
        self.assertEqual(self.queued()[0].type, 'upgrade_station')
        # The level has since landed: the same order now places the hull it wanted.
        yard.upgrade_level = 2
        self.st.command_queue.clear()
        self.ai._queue_ship(yard, 'imperial_cruiser', 1)
        self.assertEqual([c.type for c in self.queued()], ['build_ship'])
        self.assertEqual(self.queued()[0].ship_id, 'imperial_cruiser')

    def test_an_ungated_order_still_places_the_hull_directly(self):
        yard = self.spawn('shipyard')
        self.st.command_queue.clear()
        self.ai._queue_ship(yard, 'imperial_corvette', 1)
        self.assertEqual([c.type for c in self.queued()], ['build_ship'])

    def test_the_ai_never_orders_a_hull_the_catalogue_refuses(self):
        """A gate it cannot lift is not a reason to spend: the order is left to the sim."""
        yard = self.spawn('mining_station')
        self.ds.rules[balance.BUILD_LEVEL_RULES_KEY] = {'mining_station': {'imperial_cruiser': 2}}
        self.st.command_queue.clear()
        self.ai._queue_ship(yard, 'imperial_cruiser', 1)
        self.assertEqual([c.type for c in self.queued()], ['build_ship'])


class LanBalanceExchangeTests(unittest.TestCase):
    """A host's tuning travels to the peer, for that match and no longer (#106).

    Two machines, one process: the host is built while the process runs the tuned overlay, the
    client is built after the overlay is back to shipped — which is exactly what the two
    players' own files would say on their own machines.
    """

    def setUp(self):
        self.addCleanup(balance.set_active, None)
        self.addCleanup(DataStore.reset)
        balance.set_active(None)
        DataStore.reset()

    def machine(self, overlay):
        """Put a process on `overlay`'s numbers, the way starting the app does."""
        balance.set_active(overlay)
        DataStore.reset()
        return DataStore.get()

    def pair(self, host_overlay, client_overlay=None, *, start=True):
        """A real-TCP host and client whose local tunings may differ."""
        from game.net.lan import LanSession, default_lan_options
        options = default_lan_options()
        options.update(map_id='skirmish01', human_count=2, ai_count=0)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.machine(host_overlay)
        host = LanSession.host(port, options)
        self.addCleanup(host.close)
        self.machine(client_overlay if client_overlay is not None else balance.defaults())
        client = LanSession.join('127.0.0.1', port)
        self.addCleanup(client.close)
        sessions = [host, client]
        self.pump(sessions, lambda: all(len(s.snapshot['players']) == 2 for s in sessions))
        if start:
            for s in sessions:
                s.set_ready(True)
            self.pump(sessions, lambda: host.snapshot['can_start'])
            host.start()
            self.pump(sessions, lambda: all(s.launch for s in sessions))
        return host, client

    def pump(self, sessions, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            for session in sessions:
                session.poll()
            if predicate():
                return
            time.sleep(.001)
        raise AssertionError([s.snapshot for s in sessions])

    TUNED = {'version': 1,
             'station_upgrades': {'shipyard': {'hull_bonus': 0.4},
                                  'mining_station': {'production_bonus': 0.3}},
             'build_levels': {'shipyard': {'imperial_cruiser': 2}}}

    def test_the_client_runs_the_hosts_numbers_without_anyone_owning_the_same_file(self):
        host, client = self.pair(self.TUNED)
        # The handshake completed and the match started: a differing tuning is adopted, not
        # refused, which is the whole point of hashing it separately from the catalogue.
        self.assertEqual(client.local_player, 1)
        self.assertIsNotNone(client.launch)
        self.assertEqual(client.launch['map_def'], host.launch['map_def'])
        self.assertEqual(client.station_balance, balance.validate(self.TUNED))
        self.assertEqual(balance.active()['station_upgrades'],
                         self.TUNED['station_upgrades'])
        # The match itself: both managers read the tuned numbers off one handshake.
        from game.core.manager import GameManager
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in (host, client)]
        for gm in managers:
            self.assertEqual(balance.station_overrides(gm.ds.rules, 'shipyard'),
                             {'hull_bonus': 0.4})
            self.assertEqual(construction.required_level(gm.ds, 'shipyard',
                                                         'imperial_cruiser'), 2)
        self.assertEqual(managers[0].ds.rules[balance.RULES_KEY],
                         managers[1].ds.rules[balance.RULES_KEY])

    def test_the_adopted_numbers_are_given_back_when_the_match_ends(self):
        host, client = self.pair(self.TUNED)
        own = client._before_adoption                 # the catalogue this peer had before the match
        self.assertIsNotNone(own)
        self.assertTrue(balance.is_default(own.balance))
        self.assertEqual(balance.station_overrides(DataStore.get().rules, 'shipyard'),
                         {'hull_bonus': 0.4})
        client.close()
        # For that match only: the peer is back on its own numbers, and on the catalogue that
        # was built from them, with nothing written to any file.
        self.assertIs(DataStore.get(), own)
        self.assertTrue(balance.is_default(balance.active()))
        self.assertTrue(balance.is_default(DataStore.get().balance))
        self.assertEqual(balance.station_overrides(own.rules, 'shipyard'), {})

    def test_a_client_already_on_those_numbers_adopts_nothing(self):
        host, client = self.pair(balance.defaults())
        self.assertIsNone(client._adopted)
        self.assertIsNone(client._before_adoption)
        store = DataStore.get()
        self.assertTrue(balance.is_default(store.balance))
        self.assertTrue(balance.is_default(client.station_balance))

    def test_a_config_the_strict_reader_refuses_stops_the_match_whole(self):
        """A half-applied overlay is a desync with a delay fuse; refuse it at the door."""
        _host, client = self.pair({'version': 1}, start=False)
        before = DataStore.get()
        for bad in ({'version': 99},
                    {'version': 1, 'station_upgrades': {'shipyard': {'hull_bonus': -5}}},
                    {'version': 1, 'station_upgrades': {'shipyard': {'no_such_bonus': 1}}},
                    {'version': 1, 'station_upgrades': {'shipyard': {'hull_bonus': 'lots'}}},
                    {'version': 1, 'build_levels': {'shipyard': {'imperial_cruiser': 9}}},
                    None):
            with self.subTest(config=bad):
                with self.assertRaises(ValueError):
                    client._adopt_balance(bad)
                self.assertIs(DataStore.get(), before)
                self.assertTrue(balance.is_default(balance.active()))
                self.assertEqual(client.station_balance, balance.defaults())

    def test_a_peer_sending_the_hostile_config_is_refused_and_never_half_applied(self):
        from game.net.lan import LanSession, default_lan_options
        options = default_lan_options()
        options.update(human_count=2, ai_count=0)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.machine(balance.defaults())
        host = LanSession.host(port, options)
        self.addCleanup(host.close)
        host._balance = {'version': 1, 'station_upgrades': {'shipyard': {'hull_bonus': -5}}}
        client = LanSession.join('127.0.0.1', port)
        self.addCleanup(client.close)
        self.pump([host, client], lambda: client.snapshot['status'] == 'error')
        self.assertIn('station balance', client.snapshot['error'])
        self.assertTrue(balance.is_default(balance.active()))
        self.assertTrue(balance.is_default(DataStore.get().balance))

    def test_what_goes_on_the_wire_is_something_the_strict_reader_accepts(self):
        """A hand-edited file on either side must not be able to refuse the other peer."""
        hand_edited = {'version': 1,
                       'station_upgrades': {'shipyard': {'hull_bonus': -1, 'nonsense': 2},
                                            'no_such_station': {'hull_bonus': 0.2}},
                       'build_levels': {'shipyard': {'imperial_cruiser': 99}}}
        wire = balance.normalize(hand_edited)
        self.assertEqual(balance.validate(wire), wire)      # never half-applied, never refused
        # What the sim cannot use is gone; a station id this build does not field is kept but
        # counted by nothing, so it cannot be reported as a change the game can see.
        self.assertNotIn('shipyard', wire['station_upgrades'])   # nothing usable survived
        self.assertEqual(wire['build_levels'], {})
        self.assertEqual(balance.tuned_summary(wire), (1, 0))
        self.assertEqual(balance.tuned_summary(wire, {'shipyard': None}), (0, 0))
        # And it is the same bytes the pair announces: a digest that is not canonical would
        # differ between two peers holding the same numbers.
        self.assertEqual(balance.digest(wire), balance.digest(json.loads(json.dumps(wire))))


class BalanceScreenTests(unittest.TestCase):
    """Settings → Game Balance → Station upgrades: the door, the editor and the file (#106).

    The screen is driven the way a player drives it — through `handle_event` on the rects it
    drew — so a row that renders but cannot be clicked, or a press that reaches no draft, fails
    here rather than in a capture.
    """

    def setUp(self):
        import pygame
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = directory.name
        self.saves = os.path.join(root, 'saves')
        os.makedirs(self.saves)
        self.path = os.path.join(self.saves, 'balance.json')
        self.scope = mock.patch.multiple(
            menus, USER_DIR=root, SAVES_DIR=self.saves,
            SETTINGS_PATH=os.path.join(self.saves, 'settings.json'),
            CAMPAIGN_PATH=os.path.join(self.saves, 'campaign.json'),
            BALANCE_PATH=self.path)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.addCleanup(balance.set_active, None)
        self.addCleanup(DataStore.reset)
        pygame.display.init()
        self.addCleanup(pygame.display.quit)
        self.menu = menus.MenuStack(1280, 800)
        self.addCleanup(self.menu.close)

    # ------------------------------------------------------------------ the door
    def test_the_game_balance_page_names_what_is_tuned_and_opens_the_editor(self):
        self.menu.screen = 'settings'
        self.menu.settings_page = 4
        self.menu.buttons = []
        self.menu.render(0)
        texts = self.menu.settings_rendered_text
        self.assertIn('Game Balance · Page 5/5', texts)
        self.assertIn('Every station uses the shipped balance.', texts)
        door = next(b for b in self.menu.buttons if b['action'] == 'goto_balance')
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                  pos=door['rect'].center))
        self.assertEqual(self.menu.screen, 'balance')
        self.menu.buttons = []
        self.menu.render(0)
        self.assertIn('Game Balance', self.menu.balance_rendered_text)

    def test_the_editor_returns_to_the_page_it_was_opened_from(self):
        self.menu.screen = 'balance'
        self.menu.buttons = []
        self.menu.render(0)
        back = next(b for b in self.menu.buttons if b['action'] == 'balance_back')
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                  pos=back['rect'].center))
        self.assertEqual((self.menu.screen, self.menu.settings_page), ('settings', 4))

    # ------------------------------------------------------------------ the rows
    def test_the_page_tabs_reach_their_own_page_from_either_side(self):
        """A tab *names* its page; a handler that steps the payload strands the other one.

        The two tabs are the only absolute page control in the menus — every other page
        button carries ±1 — so adding the payload made "Per-level gains" (page 0) a no-op
        once "Build levels" was open: a screen the player could see but not leave.
        """
        self.menu.screen = 'balance'
        self.menu.balance_page = 0
        for target, body_action in ((1, 'balance_gate_step'), (0, 'balance_step')):
            with self.subTest(target=target):
                self.menu.buttons = []
                self.menu.render(0)
                tab = next(b for b in self.menu.buttons
                           if b['action'] == 'balance_page' and b['payload'] == target)
                self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                          pos=tab['rect'].center))
                self.assertEqual(self.menu.balance_page, target)
                # And the body the tab names is the body that draws: a page the player
                # switched to but that still shows the other page's rows is the same bug
                # wearing a different face.
                self.menu.buttons = []
                self.menu.render(0)
                self.assertTrue([b for b in self.menu.buttons if b['action'] == body_action])

    def test_the_screen_offers_exactly_the_rows_the_station_uses(self):
        """One source of truth: a row the sim would not read must not be offered."""
        self.menu.screen = 'balance'
        self.menu.balance_faction = 'imperial'
        for station_id in balance.faction_station_types(self.menu.skirmish_store, 'imperial'):
            with self.subTest(station=station_id):
                self.menu.balance_station = station_id
                self.menu.balance_page = 0
                self.menu.buttons = []
                self.menu.render(0)
                offered = [b['payload']['key'] for b in self.menu.buttons
                           if b['action'] == 'balance_step']
                self.assertEqual(set(offered), set(balance.bonus_rows(self.menu.skirmish_store,
                                                                     station_id)))
                self.menu.balance_page = 1
                self.menu.buttons = []
                self.menu.render(0)
                hulls = [b['payload']['ship_id'] for b in self.menu.buttons
                         if b['action'] == 'balance_gate_step']
                self.assertEqual(set(hulls), set(balance.editable_ships(
                    self.menu.skirmish_store, station_id, 'imperial')))

    def test_the_faction_combo_lists_that_factions_stations(self):
        self.menu.screen = 'balance'
        self.menu.balance_faction = 'imperial'
        self.menu.buttons = []
        self.menu.render(0)
        self.assertEqual([b['payload'] for b in self.menu.buttons
                          if b['action'] == 'balance_station'],
                         list(balance.faction_station_types(self.menu.skirmish_store, 'imperial')))
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                  pos=next(b for b in self.menu.buttons
                                                           if b['action'] == 'balance_faction'
                                                           )['rect'].center))
        self.menu.buttons = []
        self.menu.render(0)
        self.assertEqual([b['payload'] for b in self.menu.buttons
                          if b['action'] == 'balance_station'],
                         list(balance.faction_station_types(self.menu.skirmish_store, 'rebel')))
        self.assertIn(self.menu.balance_station,
                      balance.faction_station_types(self.menu.skirmish_store, 'rebel'))

    # -------------------------------------------------------------- the presses
    def step(self, action, payload):
        """Press the stepper the screen drew for `payload`, after drawing it."""
        self.menu.buttons = []
        self.menu.render(0)
        button = next(b for b in self.menu.buttons
                      if b['action'] == action and all(b['payload'][k] == v
                                                       for k, v in payload.items()))
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                  pos=button['rect'].center))

    def test_a_press_edits_the_draft_writes_the_file_and_reaches_the_next_match(self):
        self.menu.screen = 'balance'
        self.menu.balance_station = 'shipyard'
        self.menu.balance_page = 0
        shipped = upgrades.DEFAULTS['hull_bonus']
        self.step('balance_step', {'key': 'hull_bonus', 'delta': 1})
        self.assertAlmostEqual(
            self.menu.balance_draft['station_upgrades']['shipyard']['hull_bonus'],
            shipped + 0.01, places=9)
        self.assertFalse(os.path.exists(self.path))      # not until the frame writes it
        self.menu.apply_pending()
        with open(self.path) as f:
            self.assertAlmostEqual(json.load(f)['station_upgrades']['shipyard']['hull_bonus'],
                                   shipped + 0.01, places=9)
        # The same press reaches a catalogue built afterwards, without a restart: what the
        # next match reads is what the screen wrote.
        DataStore.reset()
        store = DataStore()
        self.addCleanup(DataStore.reset)
        self.assertEqual(store.rules[balance.RULES_KEY],
                         {'shipyard': {'hull_bonus': round(shipped + 0.01, 4)}})
        self.menu.buttons = []
        self.menu.render(0)
        self.assertIn('MODIFIED', self.menu.balance_rendered_text)

    def test_a_row_stepped_back_to_the_shipped_number_stops_being_modified(self):
        self.menu.screen = 'balance'
        self.menu.balance_station = 'mining_station'
        self.menu.balance_page = 0
        self.step('balance_step', {'key': 'production_bonus', 'delta': 1})
        self.assertEqual(self.menu.balance_draft['station_upgrades'],
                         {'mining_station': {'production_bonus': 0.16}})
        self.step('balance_step', {'key': 'production_bonus', 'delta': -1})
        self.assertTrue(balance.is_default(self.menu.balance_draft))
        self.menu.buttons = []
        self.menu.render(0)
        self.assertNotIn('MODIFIED', self.menu.balance_rendered_text)

    def test_the_stepper_cannot_reach_a_value_the_strict_reader_refuses(self):
        """Every value a stepper can land on has to be a value the file may carry."""
        self.menu.screen = 'balance'
        self.menu.balance_station = 'shipyard'
        self.menu.balance_page = 0
        for _ in range(40):
            self.step('balance_step', {'key': 'hull_bonus', 'delta': -1})
        self.assertEqual(self.menu.balance_draft['station_upgrades']['shipyard']['hull_bonus'], 0.0)
        for _ in range(balance.MAX_COUNT_GAIN + 20):
            self.step('balance_step', {'key': 'volley_shots_per_level', 'delta': 1})
        self.assertEqual(self.menu.balance_draft['station_upgrades']['shipyard']
                         ['volley_shots_per_level'], balance.MAX_COUNT_GAIN)
        # Nothing the screen produced may be refused: a refusal would leave the draft
        # unwritten and the notice would say so.
        self.menu.apply_pending()
        self.assertNotEqual(self.menu.balance_notice, 'This tuning could not be saved.')
        with open(self.path) as f:
            self.assertEqual(json.load(f), self.menu.balance_draft)

    # ------------------------------------------------------------------- the gates
    def test_a_gate_the_screen_sets_is_the_gate_the_simulation_enforces(self):
        self.menu.screen = 'balance'
        self.menu.balance_station = 'shipyard'
        self.menu.balance_page = 1
        self.step('balance_gate_step', {'station': 'shipyard', 'ship_id': 'imperial_cruiser',
                                        'delta': 1})
        self.assertEqual(self.menu.balance_draft['build_levels'],
                         {'shipyard': {'imperial_cruiser': 2}})
        self.menu.apply_pending()
        DataStore.reset()
        store = DataStore()
        self.assertEqual(construction.required_level(store, 'shipyard', 'imperial_cruiser'), 2)
        game = make_game(ai=False)
        observer = next(e for e in game.state.entities.values()
                        if e.owner == 0 and e.is_ship)
        from game.core.vectors import Vec3
        yard = game.factory.spawn_station('shipyard', 0, observer.pos + Vec3(0, 0, 400))
        self.assertFalse(game.construction.station_can_build_ship(yard, 'imperial_cruiser'))
        # And a hull that was not gated is untouched.
        self.assertTrue(game.construction.station_can_build_ship(yard, 'imperial_corvette'))

    def test_the_gate_page_offers_only_hulls_the_station_could_build(self):
        """A gate on a hull the sim refuses anyway would be a row that means nothing."""
        for faction in self.menu.balance_factions():
            for station_id in balance.faction_station_types(self.menu.skirmish_store, faction):
                with self.subTest(faction=faction, station=station_id):
                    for ship_id in balance.editable_ships(self.menu.skirmish_store, station_id,
                                                          faction):
                        self.assertTrue(construction.type_can_build_ship(
                            self.menu.skirmish_store, station_id, faction, ship_id))

    def test_stepping_a_gate_back_to_the_shipped_level_removes_it(self):
        self.menu.screen = 'balance'
        self.menu.balance_station = 'shipyard'
        self.menu.balance_page = 1
        self.step('balance_gate_step', {'station': 'shipyard', 'ship_id': 'imperial_cruiser',
                                        'delta': 1})
        self.step('balance_gate_step', {'station': 'shipyard', 'ship_id': 'imperial_cruiser',
                                        'delta': -1})
        self.assertTrue(balance.is_default(self.menu.balance_draft))
        self.menu.buttons = []
        self.menu.render(0)
        self.assertIn('as shipped', self.menu.balance_rendered_text)

    # ------------------------------------------------------------------- the resets
    def test_reset_this_station_leaves_the_other_stations_alone(self):
        self.menu.screen = 'balance'
        self.menu.balance_draft = balance.set_gain(
            balance.set_gain(balance.defaults(), 'shipyard', 'hull_bonus', 0.5),
            'mining_station', 'production_bonus', 0.4)
        self.menu.balance_draft = balance.set_build_level(self.menu.balance_draft, 'shipyard',
                                                          'imperial_cruiser', 3)
        self.menu.balance_station = 'shipyard'
        self.step('balance_reset_station', {})
        self.assertEqual(self.menu.balance_draft['station_upgrades'],
                         {'mining_station': {'production_bonus': 0.4}})
        self.assertEqual(self.menu.balance_draft['build_levels'], {})
        self.menu.apply_pending()
        with open(self.path) as f:
            self.assertEqual(json.load(f)['station_upgrades'],
                             {'mining_station': {'production_bonus': 0.4}})

    def test_reset_all_tuning_removes_the_file_and_returns_the_shipped_numbers(self):
        self.menu.screen = 'balance'
        self.menu.balance_draft = balance.set_gain(balance.defaults(), 'shipyard',
                                                   'hull_bonus', 0.5)
        self.menu._dirty_balance = True
        self.menu.apply_pending()
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(balance.active()['station_upgrades'], {'shipyard': {'hull_bonus': 0.5}})
        self.menu.balance_station = 'shipyard'
        self.step('balance_reset_all', {})
        self.assertFalse(os.path.exists(self.path))
        self.assertTrue(balance.is_default(balance.active()))
        self.menu.buttons = []
        self.menu.render(0)
        self.assertIn('Every station uses the shipped balance again.', self.menu.balance_rendered_text)

    def test_a_tuned_station_survives_a_re_entry_and_a_new_menu(self):
        """The draft is the file: a menu built after a save starts from the saved numbers."""
        self.menu.screen = 'balance'
        self.menu.balance_station = 'trade_station'
        self.menu.balance_page = 0
        self.step('balance_step', {'key': 'convoy_cargo_bonus', 'delta': 1})
        self.step('balance_step', {'key': 'convoy_cargo_bonus', 'delta': 1})
        self.menu.apply_pending()
        reopened = menus.MenuStack(1280, 800)
        self.addCleanup(reopened.close)
        reopened.screen = 'balance'
        self.assertEqual(reopened.balance_draft['station_upgrades'],
                         {'trade_station': {'convoy_cargo_bonus': 0.17}})
        reopened.buttons = []
        reopened.render(0)
        self.assertIn('Retuned station types: 1 · Gated hulls: 0', reopened.balance_rendered_text)
        reopened.balance_station = 'trade_station'
        reopened.buttons = []
        reopened.render(0)
        self.assertIn('MODIFIED', reopened.balance_rendered_text)
        self.assertIn('+17% per level', reopened.balance_rendered_text)
