"""Station collection points (#105), through the queued human command seam."""
import unittest
from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.vectors import Vec3


class CollectionBase(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.yard = self.gm.factory.spawn_station('shipyard', 0, Vec3(6000, 0, 6000))

    def point(self, pos=(7000, 120, 7000), player=0, target=None):
        self.st.queue_command(PlayerCommand('collection_point', player,
                              target_id=self.yard.id if target is None else target,
                              target_pos=pos))
        self.gm.step(1 / 30)

class CollectionCommands(CollectionBase):
    def test_paid_fighter_platform_completion_departs_for_point(self):
        from game.core.commands import BuildShipCommand
        from game.systems.construction import buildable_ship_ids
        from helpers import run_until
        platform = self.gm.factory.spawn_station('fighter_platform', 0, Vec3(6000, 0, 6500))
        player = self.st.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        fighter = next(sid for sid in buildable_ship_ids(self.gm.ds, 'fighter_platform', player.faction)
                       if self.gm.construction.station_can_build_ship(platform, sid))
        self.point((7500, 0, 6500), target=platform.id)
        before = set(self.st.entities)
        self.st.queue_command(BuildShipCommand(0, platform.id, fighter))
        self.gm.step(1 / 30)
        self.assertEqual(len(platform.build_queue), 1)
        self.assertLess(player.credits, 100000)
        run_until(self.gm, lambda: bool(set(self.st.entities) - before), limit_seconds=60)
        squad = self.st.entities[(set(self.st.entities) - before).pop()]
        distance = squad.pos.dist(Vec3(7500, 0, 6500))
        for _ in range(15):
            self.gm.step(1 / 30)
        self.assertTrue(squad.is_squadron)
        self.assertEqual(squad.order_type, 'move')
        self.assertEqual(squad.order_target_pos, Vec3(7500, 0, 6500))
        self.assertLess(squad.pos.dist(squad.order_target_pos), distance)

    def test_collection_edit_does_not_supersede_standing_orders(self):
        self.yard.order_type = 'hold'
        self.yard.build_queue = [{'kind': 'colonize', 'time_left': 100}]
        self.st.queue_command(PlayerCommand('collection_point', 0, target_id=self.yard.id,
                              unit_ids=(self.yard.id,), target_pos=(1, 2, 3)))
        self.gm.commands.consume()
        self.assertEqual(self.yard.order_type, 'hold')
        self.assertEqual(self.yard.build_queue, [{'kind': 'colonize', 'time_left': 100}])

    def test_paid_completion_samples_latest_point_and_leaves_existing_hulls_alone(self):
        from game.core.commands import BuildShipCommand
        from helpers import run_until
        player = self.st.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        self.point((7000, 0, 7000))
        before = set(self.st.entities)
        self.st.queue_command(BuildShipCommand(0, self.yard.id, 'imperial_corvette'))
        self.gm.step(1 / 30)
        self.assertEqual(len(self.yard.build_queue), 1)
        self.assertLess(player.credits, 100000)
        self.point((7800, 0, 6000))
        run_until(self.gm, lambda: bool(set(self.st.entities) - before), limit_seconds=30)
        ship = self.st.entities[(set(self.st.entities) - before).pop()]
        self.assertEqual(ship.order_target_pos, Vec3(7800, 0, 6000))
        self.point(None)
        self.assertEqual(ship.order_target_pos, Vec3(7800, 0, 6000))

    def test_reinforcement_does_not_cancel_fighter_collection_movement(self):
        fighter_id = next(k for k, v in self.gm.ds.ships.items()
                          if v.is_squadron and v.faction == self.st.players[0].faction)
        squad = self.gm.factory.spawn_ship(fighter_id, 0, self.yard.pos)
        squad.hangar_id = self.yard.id
        squad.fighter_count = squad.max_fighters - 0.001
        squad.order_type = 'move'
        squad.order_target_pos = Vec3(7500, 0, 6000)
        self.gm.squadrons.update(1)
        self.assertEqual(squad.fighter_count, squad.max_fighters)
        self.assertEqual(squad.order_type, 'move')
        self.assertEqual(squad.order_target_pos, Vec3(7500, 0, 6000))

    def test_set_is_queued_and_clear_preserves_paid_work(self):
        self.st.queue_command(PlayerCommand('collection_point', 0,
                             target_id=self.yard.id, target_pos=(7000, 120, 7000)))
        self.assertIsNone(getattr(self.yard, 'collection_point', None))
        self.gm.step(1 / 30)
        self.assertEqual(self.yard.collection_point, Vec3(7000, 120, 7000))
        self.yard.build_queue.append({'kind': 'ship', 'item': 'imperial_corvette', 'time_left': 100})
        self.point(None)
        self.assertIsNone(self.yard.collection_point)
        self.assertEqual(len(self.yard.build_queue), 1)

    def test_completion_moves_new_hull_without_teleporting(self):
        self.point()
        self.yard.build_queue.append({'kind': 'ship', 'item': 'imperial_corvette', 'time_left': 0})
        before = set(self.st.entities)
        self.gm.step(1 / 30)
        ship = self.st.entities[(set(self.st.entities) - before).pop()]
        self.assertEqual(ship.order_type, 'move')
        self.assertEqual(ship.order_target_pos, self.yard.collection_point)
        self.assertIsNot(ship.order_target_pos, self.yard.collection_point)
        self.assertLess(ship.pos.dist(self.yard.pos), self.yard.radius + 300)
        distance = ship.pos.dist(ship.order_target_pos)
        for _ in range(150):
            self.gm.step(1 / 30)
        self.assertLess(ship.pos.dist(ship.order_target_pos), distance)

    def test_fighter_completion_keeps_move_after_tactical_update(self):
        self.point()
        fighter_id = next(k for k, v in self.gm.ds.ships.items()
                          if v.is_squadron and v.faction == self.st.players[0].faction)
        self.yard.build_queue.append({'kind': 'ship', 'item': fighter_id, 'time_left': 0})
        before = set(self.st.entities)
        self.gm.step(1 / 30)
        squad = self.st.entities[(set(self.st.entities) - before).pop()]
        for _ in range(15):
            self.gm.step(1 / 30)
        self.assertEqual(squad.order_type, 'move')
        self.assertEqual(squad.order_target_pos, self.yard.collection_point)

    def test_foreign_ineligible_and_invalid_orders_leave_point_unchanged(self):
        self.point()
        for pos in [(float('nan'), 0, 0), (float('inf'), 0, 0), (True, 0, 0),
                    (1e10, 0, 0), (10 ** 400, 0, 0), (1, 2), 'bad']:
            self.point(pos)
            self.assertEqual(self.yard.collection_point, Vec3(7000, 120, 7000))
        self.point((1, 2, 3), player=1)
        self.assertEqual(self.yard.collection_point, Vec3(7000, 120, 7000))
        for kind in ('mining_station', 'defense_satellite'):
            station = self.gm.factory.spawn_station(kind, 0, Vec3(9000, 0, 9000))
            self.point((1, 2, 3), target=station.id)
            self.assertIsNone(station.collection_point)

    def test_no_point_preserves_idle_default(self):
        self.yard.build_queue.append({'kind': 'ship', 'item': 'imperial_corvette', 'time_left': 0})
        before = set(self.st.entities)
        self.gm.step(1 / 30)
        ship = self.st.entities[(set(self.st.entities) - before).pop()]
        self.assertEqual(ship.order_type, 'idle')
        self.assertIsNone(ship.order_target_pos)

    def test_save_projection_runtime_and_lan_snapshot_keep_point(self):
        import json
        from game.core.state import GameState
        from game.core.manager import GameManager
        from game.net.lan import precise_checksum
        from game.net.reconnect import capture_snapshot, restore_snapshot
        self.point((7000.123456789, 120, 7000))
        saved = json.loads(json.dumps(self.st.to_dict(precise=True)))
        self.assertEqual(saved['entities'][str(self.yard.id)]['collection_point'],
                         [7000.123456789, 120, 7000])
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(precise_checksum(restored), precise_checksum(self.gm))
        peer = restore_snapshot(capture_snapshot(self.gm))
        self.assertEqual(precise_checksum(peer), precise_checksum(self.gm))
        saved.pop('runtime_state')
        self.assertEqual(GameState.from_dict(saved).entity(self.yard.id).collection_point,
                         self.yard.collection_point)

    def test_wire_set_clear_and_spurious_fields(self):
        from game.core.commands import CollectionPointCommand
        from game.net.lan import _commands
        for point in (Vec3(1, 2, 3), None):
            command = CollectionPointCommand(0, self.yard.id, point)
            _commands([command.to_dict()], 0)
            self.assertEqual(PlayerCommand.from_dict(command.to_dict()), command)
        for changes in ({'target_id': None}, {'unit_ids': [self.yard.id]}, {'name': 'bad'},
                        {'target_pos': [float('nan'), 0, 0]}, {'target_pos': [10 ** 400, 0, 0]}, {'player': 1}):
            payload = CollectionPointCommand(0, self.yard.id, Vec3(1, 2, 3)).to_dict()
            payload.update(changes)
            with self.assertRaises(ValueError):
                _commands([payload], 0)

    def test_digest_detects_point_without_changing_unset_legacy_digest(self):
        from game.net.replay import state_checksum
        before = state_checksum(self.st)
        # Independently measured with the pre-#105 HEAD checksum implementation.
        self.assertEqual(before, '8758ea70dbe5b52ef3ca287fe33c509aa5ccf6d86f697ff41e270c31204325a6')
        self.assertNotIn('collection_point', self.st.to_dict()['entities'][self.yard.id])
        self.yard.collection_point = Vec3(1, 2, 3)
        self.assertNotEqual(state_checksum(self.st), before)
        self.yard.collection_point = None
        self.assertEqual(state_checksum(self.st), before)

    def test_restored_pending_birth_continues_identically(self):
        import json
        from game.core.state import GameState
        from game.core.manager import GameManager
        from game.net.lan import precise_checksum
        from game.net.reconnect import capture_snapshot, restore_snapshot
        from game.core.commands import BuildShipCommand
        self.point()
        player = self.st.players[0]
        player.credits = player.materials = player.energy = player.crew = 100000
        self.st.queue_command(BuildShipCommand(0, self.yard.id, 'imperial_corvette'))
        self.gm.step(1 / 30)
        self.assertEqual(len(self.yard.build_queue), 1)
        self.yard.build_queue[0]['time_left'] = 0.0
        peers = [GameManager(GameState.from_dict(json.loads(json.dumps(self.st.to_dict(precise=True))))),
                 restore_snapshot(capture_snapshot(self.gm))]
        for _ in range(30):
            self.gm.step(1 / 30)
            for peer in peers:
                peer.step(1 / 30)
                self.assertEqual(precise_checksum(peer), precise_checksum(self.gm))

    def test_nonoperational_and_boarded_station_cannot_edit_point(self):
        self.point()
        for changes in ({'alive': False}, {'crew': 0}, {'boarding': {'active': True}}):
            from unittest.mock import patch
            with patch.multiple(self.yard, **changes):
                self.st.queue_command(PlayerCommand('collection_point', 0, target_id=self.yard.id,
                                                   target_pos=(1, 2, 3)))
                self.gm.commands.consume()
            self.assertEqual(self.yard.collection_point, Vec3(7000, 120, 7000))

    def test_old_save_runtime_migrates_missing_point_only(self):
        from game.core.runtime_snapshot import capture_runtime, migrate_saved_runtime, decode_runtime
        from test_station_upgrades import strip_field
        graph = capture_runtime(self.gm)
        strip_field(graph, 'collection_point')
        state, _, _ = decode_runtime(migrate_saved_runtime(graph), self.gm)
        self.assertIsNone(state['entities'][self.yard.id].collection_point)

    def test_old_replay_runtime_is_not_silently_migrated(self):
        from game.net.replay import MatchRecording, validate_replay
        from test_station_upgrades import strip_field
        recording = MatchRecording(self.gm)
        self.addCleanup(recording.close)
        data = recording.to_dict()
        strip_field(data['initial_state']['runtime_state'], 'collection_point')
        with self.assertRaises(ValueError):
            validate_replay(data)

    def test_snapshot_and_replay_projection_reject_out_of_policy_point(self):
        from game.net.reconnect import _encode, _decode
        from game.net.replay_validation import validate_state
        self.yard.collection_point = Vec3(1e10, 0, 0)
        with self.assertRaises(ValueError):
            _decode(_encode(self.yard))
        with self.assertRaises(ValueError):
            validate_state(self.st.to_dict(precise=True))

    def test_replay_requires_collection_target_and_rejects_extra_fields(self):
        from game.net.replay import MatchRecording, validate_replay
        recording = MatchRecording(self.gm)
        self.addCleanup(recording.close)
        self.point()
        for changes in ({'target_id': None}, {'name': 'unrelated'}):
            data = recording.to_dict()
            data['commands'][0]['cmd'].update(changes)
            with self.assertRaises(ValueError):
                validate_replay(data)


class CollectionControls(CollectionBase):
    def setUp(self):
        super().setUp()
        import pygame
        font_owned = not pygame.font.get_init()
        if font_owned:
            from render import clean_classic
            self.addCleanup(pygame.font.quit)
            self.addCleanup(clean_classic.font.cache_clear)
        from types import SimpleNamespace
        from render.camera import Camera
        from render.hud import HUD
        from render.input import InputController
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, Camera(1280, 800), self.hud,
                                    SimpleNamespace(flash=lambda *_: None))
        self.ctrl.selection = {self.yard.id}

    def click(self, pos, button):
        import pygame
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.ctrl.handle_event(pygame.event.Event(kind, button=button, pos=pos))

    def test_ground_right_click_sets_station_point_and_clear_button_queues(self):
        from unittest.mock import patch
        from game.core.commands import CollectionPointCommand
        with patch.object(self.ctrl.camera, 'screen_to_world', return_value=Vec3(7000, 0, 7000)):
            self.click((600, 350), 3)
        self.assertEqual(self.st.command_queue,
                         [CollectionPointCommand(0, self.yard.id, Vec3(7000, 0, 7000))])
        self.assertIsNone(self.yard.collection_point)
        self.gm.step(1 / 30)
        self.hud._right_panel(self.ctrl.selection, 0)
        rows = [b for b in self.hud.buttons if b['kind'] == 'collection_clear']
        self.assertEqual(len(rows), 1)
        self.click(rows[0]['rect'].center, 1)
        self.assertEqual(self.st.command_queue, [CollectionPointCommand(0, self.yard.id)])
        self.gm.step(1 / 30)
        self.assertIsNone(self.yard.collection_point)

    def test_stale_clear_button_and_foreign_selection_are_inert(self):
        from unittest.mock import patch
        self.point()
        self.hud._right_panel(self.ctrl.selection, 0)
        rows = [b for b in self.hud.buttons if b['kind'] == 'collection_clear']
        self.assertEqual(len(rows), 1)
        self.ctrl.selection.clear()
        self.click(rows[0]['rect'].center, 1)
        self.assertEqual(self.st.command_queue, [])
        self.yard.owner = 1
        self.ctrl.selection = {self.yard.id}
        with patch.object(self.ctrl.camera, 'screen_to_world', return_value=Vec3(1, 2, 3)):
            self.click((600, 350), 3)
        self.assertFalse(any(c.type == 'collection_point' for c in self.st.command_queue))

    def test_minimap_right_click_does_not_project_through_to_ground(self):
        from unittest.mock import patch
        self.hud._minimap(self.ctrl.selection, 0)
        with patch.object(self.ctrl.camera, 'screen_to_world', return_value=Vec3(1, 2, 3)) as project:
            self.click(self.hud.minimap_rect.center, 3)
        self.assertEqual(self.st.command_queue, [])
        project.assert_not_called()

    def test_mixed_ground_selection_sets_only_station_and_keeps_mobile_attack_move(self):
        from unittest.mock import patch
        ship = self.gm.factory.spawn_ship('imperial_corvette', 0, Vec3(6000, 0, 6200))
        mine = self.gm.factory.spawn_station('mining_station', 0, Vec3(6000, 0, 6300))
        self.ctrl.selection = {self.yard.id, ship.id, mine.id}
        with patch.object(self.ctrl.camera, 'screen_to_world', return_value=Vec3(7000, 0, 7000)):
            self.click((600, 350), 3)
        self.assertEqual([c.type for c in self.st.command_queue], ['collection_point', 'attack_move'])
        self.assertEqual(self.st.command_queue[0].target_id, self.yard.id)
        self.assertEqual(self.st.command_queue[1].unit_ids, (ship.id,))

    def test_fixture_cleanups_preserve_borrowed_cached_menu_font(self):
        from render import clean_classic
        shared = clean_classic.font(16)
        fixture = CollectionControls('test_stale_clear_button_and_foreign_selection_are_inert')
        fixture.setUp()
        fixture.doCleanups()
        self.assertIs(clean_classic.font(16), shared)
        self.assertGreater(shared.render('still live', True, (255, 255, 255)).get_width(), 0)
