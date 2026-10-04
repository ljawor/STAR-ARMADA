"""Pure ship-rank panel contract tests (no SDL or GL initialization)."""
import unittest
from types import SimpleNamespace

from render import hud


class ShipRankPanelTests(unittest.TestCase):
    def setUp(self):
        self.ship = SimpleNamespace(data_id="corvette", is_ship=True,
                                    is_squadron=False, xp=180.0)
        self.store = SimpleNamespace(
            ships={"corvette": SimpleNamespace(veteran_xp=150)},
            rules={"experience": {"levels": [0, 120, 320, 700, 1400]}})
        # Explicit proposed simulation contract; balance is not implemented here.
        self.experience = SimpleNamespace(
            rank_for=lambda e: 2, max_rank=lambda e: 5,
            attack_multiplier=lambda e: 1.05,
            defense_multiplier=lambda e: .95)

    def panel(self):
        helper = getattr(hud, "ship_rank_panel_data", None)
        self.assertTrue(callable(helper), "pure ship_rank_panel_data helper is missing")
        return helper(self.ship, self.store, self.experience)

    def test_promoted_ship_reports_next_scaled_threshold_and_shared_power(self):
        data = self.panel()
        self.assertEqual(data["rank_text"], "RANK 2/5")
        self.assertEqual(data["xp_text"], "XP 180 / 480 · NEXT RANK")
        self.assertEqual(data["attack_text"], "ATTACK +5.0%")
        self.assertEqual(data["defense_text"], "DAMAGE REDUCTION 5.0%")
    def test_maximum_rank_reports_max_instead_of_indexing_next_threshold(self):
        self.experience.rank_for = lambda e: 5
        self.ship.xp = 9999
        data = self.panel()
        self.assertEqual(data["rank_text"], "RANK 5/5")
        self.assertEqual(data["xp_text"], "MAX RANK · XP 9,999")

    def test_station_and_dataless_convoy_have_no_ship_rank_panel(self):
        self.ship.is_ship = False
        self.assertIsNone(self.panel())
        self.ship.is_ship = True
        self.ship.data_id = "trade_convoy"
        self.assertIsNone(self.panel())

    def test_squadron_uses_the_same_rank_readouts(self):
        self.ship.is_ship = False
        self.ship.is_squadron = True
        self.assertEqual(self.panel()["rank_text"], "RANK 2/5")

    def test_panel_read_does_not_mutate_xp_or_configuration(self):
        before = vars(self.ship).copy()
        self.panel()
        self.assertEqual(vars(self.ship), before)
        self.assertEqual(self.store.rules["experience"]["levels"],
                         [0, 120, 320, 700, 1400])
    def test_real_simulation_api_matches_rank_panel_at_every_promotion(self):
        from helpers import make_game
        from game.systems.experience import rank_info
        game = make_game(ai=False)
        store = hud.DataStore.get()
        for ship in game.state.entities.values():
            if ship.data_id not in store.ships:
                continue
            for threshold in store.rules["experience"]["levels"]:
                ship.xp = threshold * store.ships[ship.data_id].veteran_xp / 100
                info = rank_info(ship)
                data = hud.ship_rank_panel_data(ship)
                self.assertEqual(data["rank_text"],
                                 f"RANK {info['rank']}/{info['max_rank']}")
                self.assertEqual(data["defense_text"],
                                 f"DAMAGE REDUCTION {info['defense_bonus'] * 100:.1f}%")

    def test_injected_experience_without_rank_info_uses_default_thresholds(self):
        for rules in ({"experience": {}}, {}):
            with self.subTest(rules=rules):
                self.store.rules = rules
                self.assertEqual(self.panel()["xp_text"],
                                 "XP 180 / 480 · NEXT RANK")
                self.assertEqual(self.store.rules, rules)

    def test_valid_omitted_experience_rules_use_shared_rank_defaults(self):
        from copy import deepcopy
        from unittest.mock import patch
        from helpers import make_game
        from game.systems.experience import rank_info
        game = make_game(ai=False)
        store = hud.DataStore.get()
        ship = next(e for e in game.state.entities.values()
                    if e.is_ship and e.data_id in store.ships)
        for omitted in ("levels", "experience"):
            with self.subTest(omitted=omitted):
                rules = deepcopy(store.rules)
                if omitted == "levels":
                    del rules["experience"]["levels"]
                else:
                    del rules["experience"]
                before = deepcopy(rules)
                with patch.object(store, "rules", rules):
                    store._validate()
                    ship.xp = 120 * store.ships[ship.data_id].veteran_xp / 100
                    info = rank_info(ship)
                    self.assertLess(info["rank"], info["max_rank"])
                    data = hud.ship_rank_panel_data(ship)
                    self.assertEqual(data["rank_text"],
                                     f"RANK {info['rank']}/{info['max_rank']}")
                    self.assertEqual(data["xp_text"],
                                     f"XP {ship.xp:,.0f} / {info['next_threshold']:,.0f} · NEXT RANK")
                    self.assertEqual(rules, before)

    def test_catalogue_ship_abilities_fit_with_rank_and_jump_rows(self):
        from helpers import make_game
        from game.core.vectors import Vec3
        game = make_game(ai=False)
        view = hud.HUD(1280, 800, game.state)
        for ship_id in hud.DataStore.get().ships:
            ship = game.factory.spawn_ship(ship_id, 0, Vec3())
            ship.jump_target = ship.pos.copy()
            view.buttons.clear()
            view.blocked_rects.clear()
            view._left_panel({ship.id}, 0)
            panel = view.blocked_rects[0]
            for button in view.buttons:
                self.assertTrue(panel.contains(button["rect"]), ship_id)

    def test_selected_ship_paints_rank_xp_and_power_without_bar_overlap(self):
        import pygame
        from unittest.mock import patch
        from helpers import make_game
        game = make_game(ai=False)
        ship = next(e for e in game.state.entities.values()
                    if e.owner == 0 and e.is_ship and not e.is_construction)
        ship.jump_target = ship.pos.copy()
        view = hud.HUD(1280, 800, game.state)
        labels, bars = [], []
        original_label, original_bar = view._label, view._bar

        def label(x, y, text, color=hud.TXT, font=None):
            font = font or view.font
            labels.append((text, pygame.Rect(x, y, *font.size(str(text)))))
            original_label(x, y, text, color, font)

        def bar(x, y, w, h, *args):
            bars.append(pygame.Rect(x, y, w, h))
            original_bar(x, y, w, h, *args)

        view._label, view._bar = label, bar
        model = hud.ship_rank_panel_data
        with patch.object(hud, "ship_rank_panel_data",
                          side_effect=lambda e, ds=None: model(e, ds, self.experience)):
            view._left_panel({ship.id}, 0)
        rank_labels = [(s, r) for s, r in labels
                       if s.startswith(("RANK", "XP", "ATTACK", "DAMAGE REDUCTION"))]
        self.assertEqual(len(rank_labels), 4, labels)
        panel = view.blocked_rects[0]
        for text, rect in rank_labels:
            self.assertTrue(panel.contains(rect), text)
            self.assertFalse(any(rect.colliderect(b) for b in bars), text)
        for button in view.buttons:
            self.assertTrue(panel.contains(button["rect"]))


if __name__ == "__main__":
    unittest.main()
