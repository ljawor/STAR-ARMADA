"""Coalition elimination for raw skirmish/LAN maps; legacy campaign saves."""
import json
import unittest

import helpers
from game.core.manager import GameManager
from game.core.state import GameState, MapInfo


def map_def():
    return {"id": "coalitions", "players": [
        {"slot": pid, "team": team, "is_ai": pid == 2,
         "start": [pid * 5000 - 5000, 0, 0],
         "start_units": {"constructor": 1}}
        for pid, team in ((2, 1), (0, 1), (1, 2))]}


class AllianceVictoryTests(unittest.TestCase):
    def test_enemy_constructor_prevents_win_until_every_enemy_unit_is_dead(self):
        gm = GameManager.start_skirmish(map_def())
        gm.victory.update(2)
        self.assertFalse(gm.state.game_over)
        for e in gm.state.entities.values():
            if e.owner == 1:
                e.alive = False
        gm.victory.update(2)
        self.assertTrue(gm.state.game_over)
        self.assertEqual(gm.state.winner, 0)
        self.assertEqual(gm.state.game_over_reason, "elimination")

    def test_restored_round_keeps_coalition_elimination_outcome(self):
        gm = GameManager.start_skirmish(map_def())
        for e in gm.state.entities.values():
            if e.owner == 0:
                e.alive = False
        restored = GameManager(GameState.from_dict(json.loads(json.dumps(
            gm.state.to_dict(precise=True)))))
        for manager in (gm, restored):
            manager.victory.update(2)
            self.assertFalse(manager.state.game_over)
            for e in manager.state.entities.values():
                if e.owner == 1:
                    e.alive = False
            manager.victory.update(2)
            self.assertEqual(manager.state.winner, 0)
            self.assertEqual(manager.state.game_over_reason, "elimination")

    def test_command_station_destruction_does_not_end_real_skirmish_ticks(self):
        gm = helpers.make_game(ai=False)
        for e in list(gm.state.entities.values()):
            if e.owner == 1 and e.data_id == "command_station":
                gm.state.damage_queue.append({
                    "attacker_id": 0, "attacker_entity": None, "target": e,
                    "damage": 10 ** 9, "shield_mult": 1, "armor_mult": 1,
                    "system_mult": 1, "weapon": None, "impact_pos": e.pos.copy()})
        helpers.run_for(gm, 3)
        self.assertFalse(gm.state.game_over)
        self.assertTrue(any(e.alive and e.owner == 1 and e.is_ship
                            for e in gm.state.entities.values()))

    def test_fallen_human_wins_with_surviving_ally_and_sorted_representative(self):
        gm = GameManager.start_skirmish(map_def())
        for e in gm.state.entities.values():
            if e.owner in (0, 1):
                e.alive = False
        gm.victory.update(2)
        self.assertTrue(gm.state.game_over)
        self.assertEqual(gm.state.winner, 0)  # not first-inserted/live AI 2
        self.assertIn(2, gm.state.allied_player_ids(gm.state.winner))

    def test_all_units_gone_draw_ignores_stale_capacity_and_nonunits(self):
        from game.core.entity import Entity
        gm = GameManager.start_skirmish(map_def())
        for e in gm.state.entities.values():
            e.alive = False
        for p in gm.state.players.values():
            p.command_capacity = 100
        for eid, kind, owner in ((100, "planet", 1), (101, "debris", 1),
                                 (102, "projectile", 1), (103, "ship", -1)):
            gm.state.add_entity(Entity(eid, kind, owner, "test",
                                      is_planet=kind == "planet", is_ship=kind == "ship"))
        gm.victory.update(2)
        self.assertTrue(gm.state.game_over)
        self.assertIsNone(gm.state.winner)

    def test_each_enemy_unit_type_prevents_elimination(self):
        from game.core.entity import Entity
        for kind, data_id in (("ship", "imperial_constructor"), ("ship", "trade_convoy"),
                              ("ship", "fighter"), ("squadron", "imperial_tie_squadron"),
                              ("station", "mining_station"), ("station", "command_station")):
            with self.subTest(data_id=data_id):
                gm = GameManager.start_skirmish(map_def())
                for e in gm.state.entities.values():
                    if e.owner == 1:
                        e.alive = False
                remaining = Entity(100, kind, 1, data_id, is_ship=kind == "ship",
                                   is_station=kind == "station", is_squadron=kind == "squadron")
                gm.state.add_entity(remaining)
                gm.victory.update(2)
                self.assertFalse(gm.state.game_over)
                remaining.alive = False
                gm.victory.update(2)
                self.assertEqual(gm.state.winner, 0)

    def test_team_zero_allied_but_missing_negative_teams_solo(self):
        for team, finishes in ((0, True), (None, False), (-1, False)):
            with self.subTest(team=team):
                gm = GameManager.start_skirmish(map_def())
                gm.state.players[0].team = team
                gm.state.players[2].team = team
                for e in gm.state.entities.values():
                    if e.owner == 1:
                        e.alive = False
                gm.victory.update(2)
                self.assertEqual(gm.state.game_over, finishes)

    def test_elimination_ignores_economic_timed_and_planet_majority(self):
        gm = GameManager.start_skirmish(map_def())
        gm.ds.rules["sim"]["victory"] = {
            "modes": ["economic", "timed", "planet_majority"],
            "economic": {"credits": 0, "planets": 0},
            "timed": {"time_limit": 0},
            "planet_majority": {"fraction": 0, "min_colonized": 0}}
        gm.victory.update(2)
        self.assertFalse(gm.state.game_over)

    def test_precise_checksum_includes_victory_mode(self):
        from game.net.lan import precise_checksum
        gm = GameManager.start_skirmish(map_def())
        elimination = precise_checksum(gm)
        gm.state.map_info.victory_mode = "command"
        self.assertNotEqual(precise_checksum(gm), elimination)

    def test_legacy_command_victory_keeps_scripted_semantics(self):
        gm = GameManager.start_mission(map_def(), {"id": "legacy"})
        for p in gm.state.players.values():
            p.command_capacity = 0
        gm.state.players[0].command_capacity = 15
        gm.victory.update(2)
        self.assertTrue(gm.state.game_over)
        self.assertEqual(gm.state.winner, 2)  # preserve legacy insertion-order representative
        self.assertEqual(gm.state.game_over_reason, "annihilation")

    def test_hud_allied_representative_is_victory_not_false_defeat(self):
        from unittest.mock import Mock
        from render.hud import HUD, GOOD
        gm = GameManager.start_skirmish(map_def())
        st = gm.state
        st.game_over = True
        st.winner = 2  # AI represents the local player's coalition.
        hud = HUD(1280, 800, st)
        real_font = hud.font_title
        hud.font_title = Mock(wraps=real_font)
        hud._top_bar(0, False)
        text, antialias, color = hud.font_title.render.call_args.args
        self.assertTrue(text.startswith("VICTORY"))
        self.assertEqual(color, GOOD)

    def test_hud_enemy_win_is_defeat_and_all_gone_is_draw(self):
        from unittest.mock import Mock
        from render.hud import HUD, BAD, TXT_DIM
        gm = GameManager.start_skirmish(map_def())
        hud = HUD(1280, 800, gm.state)
        hud.font_title = Mock(wraps=hud.font_title)
        gm.state.game_over = True
        for winner, title, color in ((1, "DEFEAT", BAD), (None, "DRAW", TXT_DIM)):
            with self.subTest(winner=winner):
                gm.state.winner = winner
                hud._top_bar(0, False)
                args = hud.font_title.render.call_args.args
                self.assertTrue(args[0].startswith(title), args[0])
                self.assertEqual(args[2], color)

    def test_raw_skirmish_persists_elimination_and_old_save_defaults_command(self):
        gm = GameManager.start_skirmish(map_def())
        self.assertEqual(gm.state.map_info.victory_mode, "elimination")
        saved = json.loads(json.dumps(gm.state.to_dict(precise=True)))
        self.assertEqual(saved["map_info"]["victory_mode"], "elimination")
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(restored.state.map_info.victory_mode, "elimination")
        self.assertEqual(restored.state.allied_player_ids(0), [0, 2])
        self.assertEqual(restored.state.to_dict(precise=True), gm.state.to_dict(precise=True))
        # Emulate an actual old file, not a projection edit of a new exact save.
        saved.pop("runtime_state")
        del saved["map_info"]["victory_mode"]
        self.assertEqual(GameManager(GameState.from_dict(saved)).state.map_info.victory_mode,
                         "command")
        self.assertEqual(MapInfo().victory_mode, "command")
        self.assertEqual(GameManager.start_mission(map_def(), {"id": "legacy"}).state.map_info.victory_mode,
                         "command")
        self.assertEqual(GameManager.start_skirmish(map_def(), mission_def={"id": "legacy"}).state.map_info.victory_mode,
                         "command")


if __name__ == "__main__":
    unittest.main()
