"""#80 controlled production-order drill; not natural navigation acceptance."""
import json
import unittest
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3
from game.data.store import DataStore


def precise(state):
    return json.loads(json.dumps(state.to_dict(precise=True)))


def captured_drill():
    DataStore.reset()
    ds = DataStore.get()
    definition = next(m for m in ds.campaign['missions'] if m['id'] == 'm00_recovery_drill')
    gm = GameManager.start_mission(ds.maps[definition['map']], definition)
    gm.step(1 / 30)
    target = next(e for e in gm.player_entities(1) if e.data_id == 'syndicate_corvette')
    cruiser = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_cruiser')
    cruiser.pos = Vec3(target.pos.x, 0, target.pos.z - 200)
    cruiser.systems['weapons'].hp = 0
    gm.visibility.update()
    gm.state.queue_command(PlayerCommand('board', 0, unit_ids=(cruiser.id,), target_id=target.id))
    gm.step(1 / 30)
    craft = gm.state.entity(cruiser.boarding_party_id)
    assert craft is not None
    craft.crew = 4  # Controlled surviving-party fixture; general boarding rules unchanged.
    for _ in range(1200):
        gm.step(1 / 30)
        if target.owner == 0:
            break
    assert target.owner == 0
    return gm, target


class RecoveryDrillTests(unittest.TestCase):
    def test_auto_recruitment_completes_same_captured_corvette_at_full_complement(self):
        gm, target = captured_drill()
        recovery = gm.mission.objectives[1]
        self.assertFalse(recovery['done'])
        base = next(e for e in gm.player_entities(0) if e.data_id == 'command_station')
        target.pos = Vec3(base.pos.x, 0, base.pos.z + 400)
        target.vel = Vec3()
        gm.visibility.update()
        events = []
        gm.state.events.subscribe('crew_delivered', lambda ev: events.append(ev))
        for _ in range(30):
            gm.step(1 / 30)
        self.assertLess(target.crew, target.max_crew)
        self.assertFalse(gm.mission.completed)
        restored = GameManager(GameState.from_dict(precise(gm.state)))
        self.assertEqual(precise(restored.state), precise(gm.state))
        for _ in range(300):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(gm.state))
        self.assertEqual(target.crew, target.max_crew)
        self.assertTrue(gm.mission.completed, 'automatic recovery must count without a delivery event')
        self.assertEqual(events, [])
        self.assertEqual(recovery['recovered_id'], target.id)

    def test_transport_partial_restore_and_wrong_hull_cannot_complete(self):
        gm, target = captured_drill()
        recovery = gm.mission.objectives[1]
        wrong = gm.factory.spawn_ship('syndicate_corvette', 0, Vec3(-6000, 0, 3000))
        gm.state.events.publish('crew_delivered', target=wrong.id, crew=wrong.max_crew)
        gm.step(1 / 30)
        self.assertFalse(recovery['done'])
        transport = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_crew_transport')
        gm.state.queue_command(PlayerCommand('crew_load', 0, unit_ids=(transport.id,)))
        for _ in range(360):
            gm.step(1 / 30)
        self.assertGreaterEqual(transport.crew_cargo, target.max_crew)
        transport.pos = Vec3(target.pos.x, 0, target.pos.z + 100)
        gm.state.queue_command(PlayerCommand('crew_deliver', 0, unit_ids=(transport.id,), target_id=target.id))
        for _ in range(30):
            gm.step(1 / 30)
            if target.crew > 1:
                break
        self.assertLess(target.crew, target.max_crew)
        self.assertFalse(recovery['done'], 'partial recovery is not 100%')
        saved = precise(gm.state)
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(precise(restored.state), saved)
        for _ in range(120):
            gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(gm.state))
        self.assertEqual(target.crew, target.max_crew)
        self.assertTrue(gm.mission.completed)
        self.assertEqual(recovery['recovered_id'], target.id)

    def test_hints_name_same_corvette_and_both_recovery_methods(self):
        from render.presentation import PresentationOverlay
        gm, target = captured_drill()
        overlay = PresentationOverlay(1024, 768)
        text = ' '.join(overlay.tutorial_paragraphs(gm.state, [target.id]))
        self.assertIn('100%', text)
        self.assertIn('captured corvette', text)
        self.assertIn('Automatic', text)
        self.assertIn('transport', text)
        self.assertNotIn('deliver 4', text)

    def test_destroyed_or_hostile_bound_hull_cannot_complete(self):
        for change in ('destroyed', 'hostile'):
            with self.subTest(change=change):
                gm, target = captured_drill()
                target.crew = target.max_crew
                if change == 'destroyed':
                    target.hull = 0
                    target.alive = False
                else:
                    target.owner = 1
                gm.step(1 / 30)
                self.assertFalse(gm.mission.completed)

    def test_invalid_full_complement_reference_and_method_are_rejected(self):
        from copy import deepcopy
        from game.systems.campaign_validation import validate_campaign
        gm, _ = captured_drill()
        for field, value in [('captured_objective', 'missing'), ('method', 'crew_delivered'),
                             ('full_complement', 1)]:
            bad = deepcopy(gm.mission.mission)
            bad['objectives'][1][field] = value
            with self.assertRaises(ValueError, msg=field):
                validate_campaign(bad, gm.ds)

    def test_already_full_on_stage_activation_counts_without_new_event(self):
        gm, target = captured_drill()
        target.crew = target.max_crew
        gm.step(1 / 30)
        self.assertTrue(gm.mission.completed)
