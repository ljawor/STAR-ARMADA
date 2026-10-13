"""Cancel queued construction (#94) and cost-derived surface build times (#95).

#94 reported that a paid build could not be stopped. Queue items are now
cancelled by a serialized `cancel_build` command that pops one item and pays
back half its catalogue cost through the existing `refund()` helper; a colony
planet's paid surface/satellite queue cancels the same way, which also releases
the site or orbit reservation the item held.

#95 required every surface building's time to follow the resources it consumes.
Times are derived from the catalogue cost at
`planet_buildings.resource_units_per_second`, and the catalogue's own
`build_time` must mirror that number: the store refuses a catalogue that
disagrees, so the HUD (which prints the catalogue number) cannot advertise a
time the simulation does not use.
"""
import json
import unittest
from types import SimpleNamespace

import pygame

from helpers import make_game, run_until
from game.core.commands import COMMAND_TYPES, CancelBuildCommand, PlayerCommand
from game.core.vectors import Vec3
from game.systems.planet_buildings import (BUILDING_TYPES, building_slots,
                                           building_time, start_building)

DT = 1 / 30


def resources(player):
    return (player.credits, player.materials, player.energy, player.crew)


def temperate(state):
    return next(e for e in state.entities.values() if e.data_id == 'temperate')


class CancelShipBuildTests(unittest.TestCase):
    """#94 through the construction system, the command seam and a restore."""
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = 100000
        self.player.energy = self.player.crew = 100000
        self.yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(6000, 0, 6000))
        self.cs = self.gm.construction

    def queue(self, *ship_ids):
        for ship_id in ship_ids:
            self.assertEqual(self.cs.start_ship(self.yard.id, ship_id, 0, 1), 1)
        return [item['item'] for item in self.yard.build_queue]

    def test_cancelling_one_queued_ship_refunds_half_of_that_ships_cost(self):
        self.assertEqual(self.queue('imperial_corvette', 'imperial_cruiser',
                                    'imperial_corvette'),
                         ['imperial_corvette', 'imperial_cruiser', 'imperial_corvette'])
        cost = self.gm.factory.ship_build_cost('imperial_cruiser')
        before = resources(self.player)
        self.assertTrue(self.cs.cancel_build(self.yard.id, 0, 1))
        after = resources(self.player)
        # the middle item went, the survivors kept their order
        self.assertEqual([i['item'] for i in self.yard.build_queue],
                         ['imperial_corvette', 'imperial_corvette'])
        # refund is the cancelled unit's own catalogue cost at 50%
        self.assertAlmostEqual(after[0] - before[0], cost['credits'] * 0.5)
        self.assertAlmostEqual(after[1] - before[1], cost['materials'] * 0.5)
        self.assertAlmostEqual(after[2] - before[2], cost['energy'] * 0.5)
        self.assertAlmostEqual(after[3] - before[3], cost['crew'] * 0.5)

    def test_the_cancelled_ship_is_never_delivered_and_its_cmd_returns(self):
        self.queue('imperial_corvette', 'imperial_corvette')
        delivered = lambda: [e for e in self.st.entities.values()
                             if e.alive and e.is_ship and e.owner == 0
                             and e.data_id == 'imperial_corvette']
        before_ids = {e.id for e in delivered()}
        used_before = self.player.command_used(self.st.entities)
        self.assertTrue(self.cs.cancel_build(self.yard.id, 0, 0))
        # paid queues reserve CMD; dropping the item releases its reservation
        self.assertLess(self.player.command_used(self.st.entities), used_before)
        run_until(self.gm, lambda: len(delivered()) > len(before_ids))
        self.assertEqual(len(delivered()), len(before_ids) + 1)

    def test_rejected_requests_change_nothing_and_pay_nothing_back(self):
        self.queue('imperial_corvette', 'imperial_corvette')
        before = resources(self.player)
        queue_before = [dict(i) for i in self.yard.build_queue]
        self.assertFalse(self.cs.cancel_build(self.yard.id, 1, 0))   # not the owner
        self.assertFalse(self.cs.cancel_build(self.yard.id, 0, 2))   # past the end
        self.assertFalse(self.cs.cancel_build(self.yard.id, 0, -1))  # negative index
        self.assertFalse(self.cs.cancel_build(99999991, 0, 0))       # no such builder
        self.assertEqual(resources(self.player), before)
        self.assertEqual([dict(i) for i in self.yard.build_queue], queue_before)

    def test_a_colonisation_order_is_not_paid_work_and_stays(self):
        planet = temperate(self.st)
        colonizer = self.gm.factory.spawn_ship(
            'imperial_colonizer', 0, planet.pos + Vec3(0, 0, planet.radius + 300))
        self.assertTrue(self.cs.start_colonize(colonizer.id, planet.id, 0))
        self.assertEqual([w['kind'] for w in colonizer.build_queue], ['colonize'])
        before = resources(self.player)
        self.assertFalse(self.cs.cancel_build(colonizer.id, 0, 0))
        self.assertEqual([w['kind'] for w in colonizer.build_queue], ['colonize'])
        self.assertEqual(resources(self.player), before)

    def test_the_command_reaches_the_queue_through_the_serialized_seam(self):
        self.queue('imperial_corvette', 'imperial_corvette', 'imperial_corvette')
        command = CancelBuildCommand(0, self.yard.id, 2)
        self.assertIn('cancel_build', COMMAND_TYPES)
        self.assertEqual(command, PlayerCommand.from_dict(command.to_dict()))
        self.st.queue_command(command)
        self.gm.step(DT)
        self.assertEqual([i['item'] for i in self.yard.build_queue],
                         ['imperial_corvette', 'imperial_corvette'])

    def test_a_cancel_never_supersedes_the_units_it_names(self):
        """Only a new order supersedes old work — cancelling is not a new order.

        A cancel that names a unit on its way through the dispatcher must leave
        that unit's standing orders alone; the dispatcher's supersede sweep is
        for new intent, and a colony ship's colonisation order is the case that
        would silently disappear.
        """
        planet = temperate(self.st)
        colonizer = self.gm.factory.spawn_ship(
            'imperial_colonizer', 0, planet.pos + Vec3(0, 0, planet.radius + 300))
        self.assertTrue(self.cs.start_colonize(colonizer.id, planet.id, 0))
        self.queue('imperial_corvette')
        self.st.queue_command(PlayerCommand('cancel_build', 0, target_id=self.yard.id,
                                            name='0', unit_ids=(colonizer.id,)))
        self.gm.step(DT)
        self.assertEqual(self.yard.build_queue, [])
        self.assertEqual([w['kind'] for w in colonizer.build_queue], ['colonize'])

    def test_the_cancelled_queue_survives_a_precise_snapshot_round_trip(self):
        from game.core.manager import GameManager
        from game.core.state import GameState

        def snapshot(gm):
            return json.loads(json.dumps(gm.state.to_dict(precise=True)))

        self.queue('imperial_corvette', 'imperial_cruiser', 'imperial_corvette')
        self.assertTrue(self.cs.cancel_build(self.yard.id, 0, 1))
        restored = GameManager(GameState.from_dict(snapshot(self.gm)))
        self.assertEqual(snapshot(self.gm), snapshot(restored))
        for _ in range(12):
            self.gm.step(DT)
            restored.step(DT)
            self.assertEqual(snapshot(self.gm), snapshot(restored))


class CancelCommandValidationTests(unittest.TestCase):
    """The LAN layer carries its own command whitelist and field rules."""
    def setUp(self):
        self.gm = make_game(ai=False)
        self.yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(6000, 0, 6000))

    def test_lan_whitelists_cancel_build_and_bounds_the_queue_index(self):
        from game.net.lan import COMMAND_TYPES as LAN_TYPES
        from game.net.lan import _commands
        self.assertIn('cancel_build', LAN_TYPES)
        _commands([CancelBuildCommand(0, self.yard.id, 3).to_dict()], 0)
        for command in (PlayerCommand('cancel_build', 0, target_id=self.yard.id),
                        PlayerCommand('cancel_build', 0, target_id=self.yard.id, name=''),
                        PlayerCommand('cancel_build', 0, target_id=self.yard.id, name='x'),
                        PlayerCommand('cancel_build', 0, target_id=self.yard.id, name='100'),
                        PlayerCommand('cancel_build', 0, target_id=self.yard.id, name='-1'),
                        PlayerCommand('cancel_build', 0, name='0')):
            with self.subTest(command=command.to_dict()), self.assertRaises(ValueError):
                _commands([command.to_dict()], 0)
        with self.assertRaises(ValueError):     # a peer may only command its own slot
            _commands([CancelBuildCommand(0, self.yard.id, 0).to_dict()], 1)


class CancelPlanetWorkTests(unittest.TestCase):
    """A colony planet holds its own paid surface/satellite queue."""
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = 100000
        self.player.energy = self.player.crew = 100000
        self.planet = temperate(self.st)
        self.planet.colonized_by = 0
        self.cs = self.gm.construction

    def test_cancelling_a_paid_surface_build_refunds_half_and_frees_its_slot(self):
        self.assertTrue(start_building(self.cs, self.planet.id, 'planet_pulsar_cannon', 0))
        item = self.planet.build_queue[0]
        self.assertEqual(item['kind'], 'planet_building')
        self.assertIn(item['slot'], building_slots(self.st, self.planet))
        cost = self.gm.factory.station_build_cost('planet_pulsar_cannon')
        before = resources(self.player)
        self.assertTrue(self.cs.cancel_build(self.planet.id, 0, 0))
        self.assertEqual(self.planet.build_queue, [])
        self.assertNotIn(item['slot'], building_slots(self.st, self.planet))
        after = resources(self.player)
        self.assertAlmostEqual(after[0] - before[0], cost['credits'] * 0.5)
        self.assertAlmostEqual(after[1] - before[1], cost['materials'] * 0.5)
        # the released site is genuinely buildable again
        self.assertTrue(start_building(self.cs, self.planet.id, 'planet_extractor', 0))
        self.assertEqual(self.planet.build_queue[0]['slot'], item['slot'])

    def test_cancelling_a_paid_satellite_frees_its_orbit_slot(self):
        self.assertTrue(self.cs.start_satellite(self.planet.id, 'defense_satellite', 0))
        item = self.planet.build_queue[0]
        self.assertEqual(item['kind'], 'satellite')
        self.assertIn(item['slot'], self.cs.satellite_slots(self.planet))
        cost = self.gm.factory.station_build_cost('defense_satellite')
        before = resources(self.player)
        self.assertTrue(self.cs.cancel_build(self.planet.id, 0, 0))
        self.assertEqual(self.planet.build_queue, [])
        self.assertNotIn(item['slot'], self.cs.satellite_slots(self.planet))
        self.assertAlmostEqual(resources(self.player)[0] - before[0],
                               cost['credits'] * 0.5)

    def test_another_player_cannot_cancel_your_colony_work(self):
        self.assertTrue(start_building(self.cs, self.planet.id, 'planet_extractor', 0))
        before = resources(self.player)
        self.assertFalse(self.cs.cancel_build(self.planet.id, 1, 0))
        self.assertEqual(len(self.planet.build_queue), 1)
        self.assertEqual(resources(self.player), before)


class SurfaceBuildTimeTests(unittest.TestCase):
    """#95: time follows the resource bill, and the catalogue mirrors it."""
    def setUp(self):
        self.gm = make_game(ai=False)
        self.ds = self.gm.ds

    def units(self, kind):
        sd = self.ds.stations[kind]
        return float(sd.cost_credits + sd.cost_materials + sd.cost_energy)

    def test_every_surface_building_time_is_its_cost_over_the_rule_rate(self):
        rate = float(self.ds.rules['planet_buildings']['resource_units_per_second'])
        for kind in BUILDING_TYPES:
            with self.subTest(kind=kind):
                self.assertAlmostEqual(building_time(kind, self.ds), self.units(kind) / rate)
                # the number the HUD prints is the number the sim uses
                self.assertAlmostEqual(float(self.ds.stations[kind].build_time),
                                       self.units(kind) / rate)
        # equal cost, equal time: the extractor and the trade hub both bill 1,600
        self.assertEqual(self.units('planet_extractor'), self.units('planet_trade_hub'))
        self.assertAlmostEqual(building_time('planet_extractor', self.ds),
                               building_time('planet_trade_hub', self.ds))

    def test_a_dearer_building_takes_strictly_longer(self):
        times = {kind: building_time(kind, self.ds) for kind in BUILDING_TYPES}
        self.assertLess(times['planet_extractor'], times['planet_shield_generator'])
        self.assertLess(times['planet_shield_generator'], times['planet_pulsar_cannon'])
        # the order of build times follows the bill, not a hand-set per-type number
        by_cost = sorted(BUILDING_TYPES, key=lambda k: (self.units(k), k))
        self.assertEqual(sorted(BUILDING_TYPES, key=lambda k: (times[k], k)), by_cost)

    def test_the_store_refuses_a_catalogue_time_that_ignores_cost(self):
        sd = self.ds.stations['planet_pulsar_cannon']
        original = sd.build_time
        sd.build_time = 24          # the flat number every type used to share
        try:
            with self.assertRaises(ValueError):
                self.ds._validate()
        finally:
            sd.build_time = original
        self.ds._validate()         # honest data validates again

    def test_the_rate_rule_is_validated(self):
        cfg = self.ds.rules['planet_buildings']
        original = dict(cfg)
        try:
            for bad in (0, -80, 'fast', True, None):
                cfg['resource_units_per_second'] = bad
                with self.subTest(rate=bad), self.assertRaises(ValueError):
                    self.ds._validate()
                cfg['resource_units_per_second'] = original['resource_units_per_second']
        finally:
            self.ds.rules['planet_buildings'] = original
        self.ds._validate()

    def test_retuning_the_rate_moves_the_time_without_touching_code(self):
        half = building_time('planet_pulsar_cannon', self.ds,
                             {'slot_cap': 6, 'resource_units_per_second': 160})
        self.assertAlmostEqual(half, building_time('planet_pulsar_cannon', self.ds) / 2)

    def test_the_simulation_queues_the_derived_time_and_takes_it(self):
        planet = temperate(self.gm.state)
        planet.colonized_by = 0
        player = self.gm.state.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        self.assertTrue(start_building(self.gm.construction, planet.id,
                                       'planet_pulsar_cannon', 0))
        item = planet.build_queue[0]
        want = building_time('planet_pulsar_cannon', self.ds)
        self.assertAlmostEqual(item['total'], want)
        self.assertAlmostEqual(item['time_left'], want)
        elapsed = run_until(self.gm, lambda: not planet.build_queue)
        self.assertAlmostEqual(elapsed, want, delta=2 * DT)
        self.assertTrue(any(e.data_id == 'planet_pulsar_cannon'
                            for e in self.gm.state.entities.values()))


class CancelBuildUITests(unittest.TestCase):
    """The HUD offers the cancel affordance; input only acts on live rows."""
    def setUp(self):
        from render.camera import Camera
        from render.hud import HUD
        from render.input import InputController
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.player = self.st.players[0]
        self.player.credits = self.player.materials = 100000
        self.player.energy = self.player.crew = 100000
        self.observer = next(e for e in self.st.entities.values()
                             if e.owner == 0 and e.is_ship)
        self.yard = self.gm.factory.spawn_station(
            'shipyard', 0, self.observer.pos + Vec3(0, 0, 200))
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud,
                                    SimpleNamespace(flash=lambda *_: None))

    def draw(self):
        self.hud.buttons.clear()
        self.hud.blocked_rects.clear()
        self.hud.scroll_rects.clear()
        self.hud._right_panel(self.ctrl.selection, 0)

    def click(self, point):
        for event in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(event, button=1, pos=point))

    def cancel_rows(self):
        return [b for b in self.hud.buttons if b['kind'] == 'cancel_build']

    def test_ship_queue_rows_offer_cancel_and_clicking_one_queues_the_command(self):
        self.assertEqual(self.gm.construction.start_ship(
            self.yard.id, 'imperial_corvette', 0, 3), 3)
        self.ctrl.selection = {self.yard.id}
        self.draw()
        rows = self.cancel_rows()
        self.assertEqual([b['payload']['index'] for b in rows], [0, 1, 2])
        self.assertTrue(all(b['payload']['target_id'] == self.yard.id for b in rows))
        self.click(rows[1]['rect'].center)
        self.assertEqual(self.st.command_queue, [CancelBuildCommand(0, self.yard.id, 1)])
        self.gm.step(DT)
        self.assertEqual(len(self.yard.build_queue), 2)

    def test_a_row_left_over_from_another_selection_cannot_act(self):
        self.gm.construction.start_ship(self.yard.id, 'imperial_corvette', 0, 2)
        self.ctrl.selection = {self.yard.id}
        self.draw()
        row = self.cancel_rows()[0]
        # The row is still in this frame's button list; the selection has moved
        # on without a redraw, so the input-side ownership/selection check is
        # the only thing standing between a stale row and the queue.
        self.ctrl.selection = {self.observer.id}
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue, [])
        # the same click with the yard still selected does act
        self.ctrl.selection = {self.yard.id}
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue,
                         [CancelBuildCommand(0, self.yard.id, 0)])

    def test_a_paid_colony_slot_offers_cancel_and_respects_the_page(self):
        planet = temperate(self.st)
        planet.colonized_by = 0
        self.observer.pos = planet.pos.copy()
        self.assertTrue(start_building(self.gm.construction, planet.id,
                                       'planet_extractor', 0))
        self.ctrl.selection = {planet.id}
        self.hud.planet_page = 'surface'
        self.draw()
        row = self.cancel_rows()[0]
        self.assertEqual(row['payload'],
                         {'target_id': planet.id, 'page': 'surface', 'index': 0})
        # the orbit page shows the same cell; the surface row must stay inert
        self.hud.planet_page = 'orbit'
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue, [])
        self.hud.planet_page = 'surface'
        self.click(row['rect'].center)
        self.assertEqual(self.st.command_queue,
                         [CancelBuildCommand(0, planet.id, 0)])
