"""Regressions for capture dependents and combat-destroyed boarding craft."""
import json
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3


def precise(st):
    return json.loads(json.dumps(st.to_dict(precise=True)))


class TestBoardingCleanup(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.source = self.gm.factory.spawn_ship('imperial_cruiser', 0, Vec3())
        self.carrier = self.gm.factory.spawn_ship('imperial_cruiser', 1, Vec3(500, 0, 0))
        self.carrier.crew = 0
        self.carrier.shields = {q: 0.0 for q in self.carrier.shields}

    def launch(self):
        self.st.queue_command(PlayerCommand('board', 0, unit_ids=(self.source.id,),
                                           target_id=self.carrier.id))
        self.gm.commands.consume()
        return self.st.entity(self.source.boarding_party_id)

    def assert_precise_restore(self):
        self.gm.visibility.update()
        snapshot = precise(self.st)
        restored = GameManager(GameState.from_dict(snapshot))
        self.assertEqual(precise(restored.state), snapshot)
        for _ in range(12):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(precise(restored.state), precise(self.st))
        return restored

    def test_combat_destruction_clears_source_party_before_restore(self):
        craft = self.launch()
        self.assertIsNotNone(craft)
        craft_id = craft.id
        crew_after_launch = self.source.crew
        self.st.damage_queue.append(dict(target=craft, damage=1000,
                                         shield_mult=1, armor_mult=1,
                                         system_mult=1, attacker_id=1))
        self.gm.damage.update(0)
        self.assertTrue(self.source.alive)
        self.assertNotIn(craft_id, self.st.entities)
        self.assertIsNone(self.source.boarding_party_id)
        self.assertEqual(self.source.crew, crew_after_launch)
        restored = self.assert_precise_restore()
        self.assertIsNone(restored.state.entity(self.source.id).boarding_party_id)
        self.assertNotIn(craft_id, restored.state.entities)
        self.assertIsNotNone(self.launch())

    def test_healthy_bomber_reassigns_invalid_hangar(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                self.setUp()
                for entity in self.st.entities.values():
                    if entity.owner == 1:
                        entity.crew = 0
                bomber = self.gm.factory.spawn_ship('imperial_tie_bomber_squadron', 1, Vec3(600, 0, 0))
                bomber.hangar_id = self.source.id
                if replacement:
                    self.carrier.crew = 10
                self.gm.squadrons._reinforce_and_repair(bomber, .1)
                self.assertEqual(bomber.hangar_id, self.carrier.id if replacement else None)
                self.assertEqual(bomber.hull, bomber.max_hull)
                self.assertEqual(bomber.fighter_count, bomber.max_fighters)

    def test_bomber_evades_only_to_owned_operational_hangar(self):
        for case in ('hostile', 'derelict'):
            with self.subTest(case=case):
                self.setUp()
                bomber = self.gm.factory.spawn_ship('imperial_tie_bomber_squadron', 1, Vec3(600, 0, 0))
                self.gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3(650, 0, 0))
                bomber.hangar_id = self.carrier.id
                self.carrier.owner = 0 if case == 'hostile' else 1
                self.carrier.crew = 10 if case == 'hostile' else 0
                self.st.grid.rebuild(self.st.entities)
                self.gm.squadrons._squadron_behavior(bomber)
                self.assertFalse(bomber.order_type == 'follow' and
                                 bomber.order_target_id == self.carrier.id)

    def test_capture_detaches_old_owner_carrier_dependents_before_restore(self):
        bomber = self.gm.factory.spawn_ship('imperial_tie_bomber_squadron', 1, Vec3(600, 0, 0))
        bomber.hangar_id = bomber.launched_from = self.carrier.id
        bomber.order_type = 'follow'
        bomber.order_target_id = self.carrier.id
        unrelated = self.gm.factory.spawn_ship('imperial_tie_bomber_squadron', 1, Vec3(700, 0, 0))
        unrelated.hangar_id = unrelated.launched_from = unrelated.id
        unrelated.order_type = 'move'
        unrelated.order_target_pos = Vec3(800, 0, 0)
        craft = self.launch()
        craft.pos = self.carrier.pos.copy()
        self.gm.boarding.update(6)
        self.assertEqual(self.carrier.owner, 0)
        self.assertIsNone(bomber.hangar_id)
        self.assertIsNone(bomber.launched_from)
        self.assertEqual(bomber.order_type, 'idle')
        self.assertIsNone(bomber.order_target_id)
        self.assertEqual(unrelated.hangar_id, unrelated.id)
        self.assertEqual(unrelated.order_type, 'move')
        restored = self.assert_precise_restore()
        self.assertNotEqual(restored.state.entity(bomber.id).hangar_id, self.carrier.id)
        self.assertNotEqual(restored.state.entity(bomber.id).order_target_id, self.carrier.id)
