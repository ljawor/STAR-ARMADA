"""Exact nonzero-tick continuation through real strategic AI cadence."""
import json
import unittest
from game.core.manager import GameManager
from game.core.state import GameState
from game.net.replay import MatchRecording, PlaybackSession
from test_replay_workflow import game, precise


class FutureStateTests(unittest.TestCase):
    def test_nonzero_recording_and_save_continue_exactly(self):
        for start in (37, 150, 300):
            with self.subTest(start=start):
                gm = game()
                for _ in range(start):
                    gm.step(1/30)
                rec = MatchRecording(gm)
                saved = json.loads(json.dumps(gm.state.to_dict(precise=True)))
                restored = GameManager(state=GameState.from_dict(saved))
                expected = []
                for _ in range(360):
                    gm.step(1/30)
                    restored.step(1/30)
                    expected.append(precise(gm.state))
                    self.assertEqual(precise(restored.state), expected[-1], f'save tick {gm.state.tick}')
                rec.close()
                playback = PlaybackSession(rec.to_dict())
                for snapshot in expected:
                    playback.step()
                    self.assertEqual(precise(playback.gm.state), snapshot, f'replay tick {snapshot["tick"]}')

    def test_runtime_rally_preserves_supported_coordinate_types(self):
        from game.core.world import Fleet
        from game.core.vectors import Vec3
        from game.net.reconnect import _encode, _decode
        for rally in ([1.25, 2., 3.], (1.25, 2., 3.)):
            with self.subTest(rally=rally):
                fleet = Fleet(1, 0, 'rally', rally_point=rally)
                loaded = _decode(_encode(fleet))
                self.assertEqual(type(loaded.rally_point), type(rally))
                self.assertEqual(loaded.rally_point, rally)
        # Vec3 is valid for entity destinations, not iterable Fleet rallies.
        for rally in ([1., 2.], [1., 2., 3., 4.], [1., True, 3.], {'x': 1}, Vec3()):
            with self.subTest(invalid=rally), self.assertRaises(ValueError):
                _decode(_encode(Fleet(1, 0, 'rally', rally_point=rally)))

    def test_save_repairs_only_nonfinite_jump_intent_but_replay_rejects_it(self):
        from copy import deepcopy
        from game.core.vectors import Vec3
        from game.net.reconnect import _decode, _encode
        from game.net.replay import validate_replay
        for bad_field in ('target', 'charge'):
            with self.subTest(field=bad_field):
                gm = game()
                for _ in range(37):
                    gm.step(1/30)
                ship = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
                ship.jump_charge = float('nan') if bad_field == 'charge' else .1
                ship.jump_target = Vec3(float('nan') if bad_field == 'target' else 100., 0., 0.)
                original = ship.pos.copy()
                rec = MatchRecording(gm).to_dict()
                saved = deepcopy(rec['initial_state'])
                restored = GameManager(GameState.from_dict(saved))
                loaded = restored.state.entities[ship.id]
                self.assertEqual(loaded.pos, original)
                self.assertEqual(loaded.jump_charge, 0.)
                self.assertIsNone(loaded.jump_target)
                self.assertEqual(loaded.order_type, 'idle')
                self.assertEqual(set(restored.ai.ais), set(gm.ai.ais))
                self.assertEqual(restored.trading._timer, gm.trading._timer)
                with self.assertRaises(ValueError):
                    validate_replay(rec)
                # Canonical-only corruption must not be hidden by the projection.
                bad = deepcopy(rec)
                for entity in bad['initial_state']['entities'].values():
                    entity.pop('jump_target', None)
                    entity['jump_charge'] = 0.
                with self.assertRaises(ValueError):
                    validate_replay(bad)
                # Save repair is not a catch/drop fallback for unrelated fields.
                malformed = deepcopy(saved)
                runtime = malformed['runtime_state']['state']
                for key, value in runtime[1]:
                    if key == ['scalar', 'entities']:
                        value[1][0][1][2]['hull'] = ['scalar', 'bad']
                with self.assertRaises(ValueError):
                    GameManager(GameState.from_dict(malformed))

    def test_finite_invalid_jump_save_is_cancelled_but_replay_is_rejected(self):
        from game.core.vectors import Vec3
        from game.net.replay import validate_replay
        gm = game()
        ship = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        ship.jump_charge = .1
        ship.jump_target = Vec3(gm.state.map_info.bounds, 0, 0)
        original = ship.pos.copy()
        rec = MatchRecording(gm).to_dict()
        restored = GameManager(GameState.from_dict(rec['initial_state']))
        restored._update_jumps(1.)
        loaded = restored.state.entities[ship.id]
        self.assertEqual(loaded.pos, original)
        self.assertEqual(loaded.jump_charge, 0.)
        self.assertIsNone(loaded.jump_target)
        with self.assertRaises(ValueError):
            validate_replay(rec)

    def test_legacy_save_and_replay_without_future_state_have_safe_fallback(self):
        from game.net.replay import ReplayRecorder, validate_replay
        gm = game()
        for _ in range(37):
            gm.step(1/30)
        legacy = json.loads(json.dumps(gm.state.to_dict(precise=True)))
        legacy.pop('runtime_state')
        restored = GameManager(state=GameState.from_dict(legacy))
        self.assertEqual(restored.ai.ais, {})
        restored.step(1/30)
        # A loaded old save can be saved/recorded in the new format again.
        rec = MatchRecording(restored)
        restored.step(1/30)
        PlaybackSession(rec.to_dict())
        old_replay = ReplayRecorder(gm.state).to_dict()
        old_replay['initial_state'].pop('runtime_state')
        self.assertIn('future', validate_replay(old_replay)['compatibility_warning'])

    def test_midcampaign_capture_and_delivery_continue_past_strategic_cadence(self):
        from game.core.commands import PlayerCommand
        from game.core.vectors import Vec3
        from game.data.store import DataStore
        ds = DataStore.get()
        definition = ds.campaign['missions'][0]
        gm = GameManager.start_mission(ds.maps[definition['map']], definition)
        gm.step(1/30)
        st = gm.state
        transport = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_crew_transport')
        cruiser = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_cruiser')
        target = next(e for e in gm.player_entities(1) if e.data_id == 'syndicate_corvette')
        frigate = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_frigate')
        st.queue_command(PlayerCommand('crew_load', 0, unit_ids=(transport.id,)))
        for _ in range(120):
            gm.step(1/30)
        self.assertGreater(transport.crew_cargo, 0)
        st.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=frigate.id))
        for _ in range(180):
            gm.step(1/30)
        # Match the labelled controlled HUD fixture, not a natural playthrough:
        # cruiser is repositioned in range and its guns disabled before capture.
        cruiser.pos = Vec3(target.pos.x, 0, target.pos.z - 200)
        cruiser.systems['weapons'].hp = 0
        gm.visibility.update()
        st.queue_command(PlayerCommand('board', 0, unit_ids=(cruiser.id,), target_id=target.id))
        gm.step(1/30)
        self.assertIsNotNone(cruiser.boarding_party_id)

        def continuation(stage):
            # Deliberately exercise ordinary F5-style saves too. The canonical
            # future graph is exact even when the compatibility projection rounds.
            restored = GameManager(GameState.from_dict(json.loads(json.dumps(st.to_dict()))))
            self.assertEqual(precise(restored.state), precise(st))
            rec = MatchRecording(gm, mode='campaign')
            snapshots = []
            for _ in range(420):
                gm.step(1/30)
                restored.step(1/30)
                snapshots.append(precise(st))
                self.assertEqual(precise(restored.state), snapshots[-1], f'{stage} restore tick {st.tick}')
            rec.close()
            playback = PlaybackSession(rec.to_dict())
            for snapshot in snapshots:
                self.assertTrue(playback.step())
                self.assertEqual(precise(playback.gm.state), snapshot, f'{stage} replay tick {snapshot["tick"]}')
            self.assertEqual(playback.gm.state.tick, st.tick)

        continuation('capture')
        self.assertEqual(target.owner, 0)
        self.assertTrue(gm.mission.objectives[0]['done'])
        transport.pos = Vec3(frigate.pos.x, 0, frigate.pos.z + 100)
        gm.visibility.update()
        st.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=frigate.id))
        continuation('delivery')
        self.assertTrue(gm.mission.completed)
        self.assertGreaterEqual(frigate.crew, 4)
        self.assertEqual(st.tick, 1142)


if __name__ == '__main__':
    unittest.main()
