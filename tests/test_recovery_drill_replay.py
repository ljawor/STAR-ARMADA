"""Production strict replay boundary for #80; controlled, not human playthroughs."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.net.replay import MatchRecording, PlaybackSession, load_replay, validate_replay
from test_recovery_drill import captured_drill, precise


def fresh_drill():
    DataStore.reset()
    ds = DataStore.get()
    definition = next(m for m in ds.campaign['missions'] if m['id'] == 'm00_recovery_drill')
    return GameManager.start_mission(ds.maps[definition['map']], definition)


class RecoveryDrillReplayTests(unittest.TestCase):
    def roundtrip(self, gm, ticks):
        initial = precise(gm.state)
        recording = MatchRecording(gm, mode='campaign')
        snapshots = []
        try:
            for _ in range(ticks):
                gm.step(1 / 30)
                snapshots.append(precise(gm.state))
            # Each production entry point must independently accept this snapshot.
            data = validate_replay(recording.to_dict())
            direct = PlaybackSession(data)
            self.assertEqual(precise(direct.gm.state), initial)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'campaign.json'
                recording.save(path)
                loaded = load_replay(path)
                playback = PlaybackSession(loaded)
                self.assertEqual(precise(playback.gm.state), initial)
                for snapshot in snapshots:
                    self.assertTrue(playback.step())
                    self.assertEqual(precise(playback.gm.state), snapshot)
                    self.assertTrue(direct.step())
                    self.assertEqual(precise(direct.gm.state), snapshot)
                self.assertTrue(playback.ended)
                self.assertFalse(playback.step())
        finally:
            recording.close()

    def test_fresh_drill_validate_save_load_playback(self):
        self.roundtrip(fresh_drill(), 3)

    def test_mid_recovery_validate_save_load_playback_through_completion(self):
        gm, target = captured_drill()
        base = next(e for e in gm.player_entities(0) if e.data_id == 'command_station')
        target.pos = Vec3(base.pos.x, 0, base.pos.z + 400)
        target.vel = Vec3()
        gm.visibility.update()
        for _ in range(30):
            gm.step(1 / 30)
        self.assertLess(target.crew, target.max_crew)
        self.assertFalse(gm.mission.completed)
        self.assertEqual(gm.mission.objectives[0]['captured_id'], target.id)
        self.roundtrip(gm, 300)
        self.assertTrue(gm.mission.completed)
        self.assertEqual(gm.mission.objectives[1]['recovered_id'], target.id)

    def test_legacy_capture_progress_validate_save_load_playback(self):
        # Historical event-count objectives lack the new full-complement definition.
        gm, target = captured_drill()
        for objective in (gm.mission.mission['objectives'][1], gm.mission.objectives[1]):
            objective.pop('full_complement')
            objective.pop('captured_objective')
            objective['method'] = 'crew_delivered'
        self.assertEqual(gm.mission.objectives[0]['captured_id'], target.id)
        self.roundtrip(gm, 3)

    def test_new_fields_remain_typed_bounded_and_definition_bound(self):
        good = MatchRecording(fresh_drill(), mode='campaign').to_dict()
        # A valid control makes rejection tests non-vacuous.
        validate_replay(good)
        mutations = [
            ('full_complement', 1, 1, 'definition'),
            ('captured_objective', 1, 1, 'definition'),
            ('captured_objective', 'missing', 1, 'definition'),
            ('captured_objective', 'recover', 1, 'definition'),
            ('captured_objective', 'missing', 1, 'progress'),
            ('full_complement', False, 1, 'progress'),
            ('unknown_field', True, 1, 'progress'),
        ]
        for field in ('captured_id', 'recovered_id'):
            for value in (True, '1', 1.5, -1, 100000001, 10 ** 100):
                for location in ('definition', 'progress'):
                    mutations.append((field, value, 0 if field == 'captured_id' else 1, location))
        for field, value, index, location in mutations:
            with self.subTest(field=field, value=value, location=location):
                bad = deepcopy(good)
                mission = bad['initial_state']['mission_state']
                rows = mission['definition']['objectives'] if location == 'definition' else mission['objectives']
                rows[index][field] = value
                with self.assertRaises(ValueError):
                    validate_replay(bad)
                with self.assertRaises(ValueError):
                    PlaybackSession(bad)

    def test_supported_legacy_projection_keeps_capture_progress_without_new_fields(self):
        gm, target = captured_drill()
        for objective in (gm.mission.mission['objectives'][1], gm.mission.objectives[1]):
            objective.pop('full_complement')
            objective.pop('captured_objective')
            objective['method'] = 'crew_delivered'
        recording = MatchRecording(gm, mode='campaign')
        try:
            gm.step(1 / 30)
            data = recording.to_dict()
        finally:
            recording.close()
        data['initial_state'].pop('runtime_state')
        loaded = validate_replay(data)
        self.assertIn('future', loaded['compatibility_warning'].lower())
        playback = PlaybackSession(loaded)
        self.assertEqual(playback.gm.mission.objectives[0]['captured_id'], target.id)
        self.assertTrue(playback.step())
        self.assertTrue(playback.ended)

    def test_progress_identifier_bounds_accept_zero_and_maximum(self):
        from game.net.replay_validation import validate_mission
        gm = fresh_drill()
        for value in (0, 100000000):
            saved = deepcopy(gm.mission.to_dict())
            saved['objectives'][0]['captured_id'] = value
            saved['objectives'][1]['recovered_id'] = value
            validate_mission(saved, gm.ds)


if __name__ == '__main__':
    unittest.main()
