"""Trading tests (spec §26): convoy spawn, delivery payment, raiding loot."""
import unittest

from helpers import make_game, run_for
from game.core.vectors import Vec3
from game.data.store import DataStore


def _two_traders(gm):
    """Spawn a trade station for both players near their command stations."""
    st = gm.state
    st.next_entity_id  # noqa
    for pid, x in ((0, -6000.0), (1, 6000.0)):
        gm.factory.spawn_station("trade_station", pid, Vec3(x, 0, 0))
    return [e for e in st.entities.values()
            if e.alive and e.data_id == "trade_station"]


class TestConvoys(unittest.TestCase):
    def test_convoy_spawns(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg["spawn_interval"] = 0.5
        stations = _two_traders(gm)
        run_for(gm, 1.0)
        convoys = [e for e in st.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertGreaterEqual(len(convoys), 1)
        c = convoys[0]
        self.assertGreater(c.cargo_credits, 0)
        self.assertIsNotNone(c.convoy_dest)
        self.assertIn(c.owner, (0, 1))

    def test_convoy_arrives_and_pays(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg.update(spawn_interval=0.5)
        import game.data.store as _s
        _s.DataStore.get().rules["economy"]["trading"]["speed"] = 400.0
        stations = _two_traders(gm)
        p0 = st.players[0]
        cr0 = p0.credits
        run_for(gm, 40.0)
        paid = p0.credits > cr0
        self.assertTrue(paid, "destination owner should be paid on arrival")

    def test_raid_loots_killer(self):
        gm = make_game(ai=False)
        st = gm.state
        ts = gm.trading
        ts.cfg["spawn_interval"] = 0.5
        _two_traders(gm)
        run_for(gm, 1.0)
        convoys = [e for e in st.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertGreaterEqual(len(convoys), 1)
        c = convoys[0]
        p1 = st.players[1]
        cr1 = p1.credits
        # player 1 destroys player 0's convoy
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": c,
            "damage": 10**9, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 1.0, "weapon": None, "impact_pos": c.pos.copy(),
        })
        run_for(gm, 0.2)
        loot = c.cargo_credits * ts.cfg.get("loot_fraction", 0.5)
        self.assertGreaterEqual(p1.credits, cr1 + loot - 1.0)

    def test_no_trade_stations_no_convoys(self):
        gm = make_game(ai=False)
        run_for(gm, 2.0)
        convoys = [e for e in gm.state.entities.values()
                   if e.alive and e.data_id == "trade_convoy"]
        self.assertEqual(len(convoys), 0)


if __name__ == "__main__":
    unittest.main()