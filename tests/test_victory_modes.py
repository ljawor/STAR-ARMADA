"""Victory condition tests (spec §46): annihilation baseline + new modes."""
import json
import os
import unittest

from helpers import make_game, run_for, ROOT
from game.data.store import DataStore


def _patch_victory(gm, victory_cfg):
    """Override rules.victory for the running game."""
    gm.ds.rules.setdefault("sim", {})["victory"] = victory_cfg


class TestAnnihilation(unittest.TestCase):
    def test_default_mode_ends_game(self):
        gm = make_game(ai=False)
        # kill both command stations of team 1 -> team 0 wins
        st = gm.state
        for e in list(st.entities.values()):
            if e.alive and e.is_station and e.owner == 1 and \
                    gm.ds.stations.get(e.data_id) and \
                    gm.ds.stations.get(e.data_id).command_capacity >= 15:
                st.damage_queue.append({
                    "attacker_id": 0, "attacker_entity": None, "target": e,
                    "damage": 10**9, "shield_mult": 1.0, "armor_mult": 1.0,
                    "system_mult": 1.0, "weapon": None,
                    "impact_pos": e.pos.copy(),
                })
        run_for(gm, 3)
        self.assertTrue(st.game_over)
        self.assertEqual(st.game_over_reason, "annihilation")
        self.assertEqual(st.winner, 0)


class TestPlanetMajority(unittest.TestCase):
    def test_majority_triggers(self):
        gm = make_game(ai=False)
        st = gm.state
        _patch_victory(gm, {"modes": ["planet_majority"],
                            "planet_majority": {"fraction": 0.5,
                                                "min_colonized": 3}})
        planets = [e for e in st.entities.values() if e.is_planet
                   and e.data_id != "asteroid_field"]
        self.assertGreaterEqual(len(planets), 3)
        for e in planets[:3]:
            e.colonized_by = 0
        run_for(gm, 2)
        self.assertTrue(st.game_over)
        self.assertEqual(st.game_over_reason, "planet_majority")
        self.assertEqual(st.winner, 0)

    def test_below_min_colonized_does_not_trigger(self):
        gm = make_game(ai=False)
        st = gm.state
        _patch_victory(gm, {"modes": ["planet_majority"],
                            "planet_majority": {"fraction": 0.5,
                                                "min_colonized": 20}})
        for e in st.entities.values():
            if e.is_planet and e.data_id != "asteroid_field":
                e.colonized_by = 0
        run_for(gm, 2)
        self.assertFalse(st.game_over)


class TestEconomic(unittest.TestCase):
    def test_credits_and_planets_trigger(self):
        gm = make_game(ai=False)
        st = gm.state
        _patch_victory(gm, {"modes": ["economic"],
                            "economic": {"credits": 100, "planets": 1}})
        p0 = st.players[0]
        p0.credits = 150
        planet = next(e for e in st.entities.values()
                      if e.is_planet and e.data_id != "asteroid_field")
        planet.colonized_by = 0
        run_for(gm, 2)
        self.assertTrue(st.game_over)
        self.assertEqual(st.game_over_reason, "economic")
        self.assertEqual(st.winner, 0)


class TestTimed(unittest.TestCase):
    def test_timeout_picks_leader(self):
        gm = make_game(ai=False)
        st = gm.state
        _patch_victory(gm, {"modes": ["timed"],
                            "timed": {"time_limit": 5.0}})
        # break symmetry: player 0 colonizes one extra planet (+3 score)
        planet = next(e for e in st.entities.values()
                      if e.is_planet and e.data_id != "asteroid_field")
        planet.colonized_by = 0
        run_for(gm, 7)
        self.assertTrue(st.game_over)
        self.assertEqual(st.game_over_reason, "timed")
        self.assertEqual(st.winner, 0)

    def test_tie_yields_no_winner(self):
        gm = make_game(ai=False)
        st = gm.state
        _patch_victory(gm, {"modes": ["timed"],
                            "timed": {"time_limit": 5.0}})
        # equalize scores: colonize one planet each (start is symmetric)
        planets = [e for e in st.entities.values()
                   if e.is_planet and e.data_id != "asteroid_field"]
        planets[0].colonized_by = 0
        planets[1].colonized_by = 1
        run_for(gm, 7)
        self.assertTrue(st.game_over)
        self.assertEqual(st.game_over_reason, "timed")
        self.assertIsNone(st.winner)


if __name__ == "__main__":
    unittest.main()