"""Mission objective tests: hold_point + escort_convoy (spec §28)."""
import unittest

from helpers import make_game, run_for
from game.core.vectors import Vec3


def _mission(gm, objectives):
    """Attach an objective list to the live MissionSystem."""
    gm.mission.mission = {"objectives": objectives}
    gm.mission.objectives = [dict(o, done=False) for o in objectives]


class TestHoldPoint(unittest.TestCase):
    def test_hold_completes_after_duration(self):
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.is_ship and e.owner == 0)
        ship.pos = Vec3(500, 0, 500)     # inside the point
        _mission(gm, [{"type": "hold_point", "pos": [500, 0, 500],
                       "radius": 800, "count": 1, "duration": 2.0,
                       "text": "Hold the beacon"}])
        run_for(gm, 3.0)
        self.assertTrue(gm.mission.objectives[0]["done"])
        self.assertTrue(gm.mission.completed)

    def test_hold_requires_presence(self):
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.is_ship and e.owner == 0)
        ship.pos = Vec3(-50000, 0, 0)    # far away
        _mission(gm, [{"type": "hold_point", "pos": [500, 0, 500],
                       "radius": 800, "count": 1, "duration": 2.0,
                       "text": "Hold the beacon"}])
        run_for(gm, 3.0)
        self.assertFalse(gm.mission.objectives[0]["done"])
        self.assertFalse(gm.mission.completed)

    def test_hold_drains_when_left(self):
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.is_ship and e.owner == 0)
        ship.pos = Vec3(500, 0, 500)
        _mission(gm, [{"type": "hold_point", "pos": [500, 0, 500],
                       "radius": 800, "count": 1, "duration": 2.0,
                       "text": "Hold the beacon"}])
        run_for(gm, 1.0)                 # 1s held
        ship.pos = Vec3(-50000, 0, 0)    # leave
        run_for(gm, 1.0)                 # drains ~2s worth
        run_for(gm, 2.0)                 # away the whole time
        self.assertFalse(gm.mission.objectives[0]["done"])


class TestEscort(unittest.TestCase):
    def test_convoy_arrival_completes(self):
        gm = make_game(ai=False)
        st = gm.state
        _mission(gm, [{"type": "escort_convoy", "text": "Escort the convoy"}])
        from test_trading import _two_traders, _advance_until
        source, destination = _two_traders(gm)
        gm.trading.cfg.update(spawn_interval=0.5)
        arrived = []
        st.events.subscribe("convoy_arrived", lambda e: arrived.append(dict(e.data)))
        _advance_until(self, gm, lambda: gm.mission.objectives[0]["done"])
        self.assertTrue(arrived, "escort must complete through a real delivery")
        self.assertEqual(arrived[0]["convoy_owner"], 0)
        self.assertIn(arrived[0]["dest"], (source.id, destination.id))
        self.assertTrue(gm.mission.completed)
        self.assertTrue(gm.mission.objectives[0]["done"])

    def test_convoy_destroyed_fails_mission(self):
        gm = make_game(ai=False)
        st = gm.state
        _mission(gm, [{"type": "escort_convoy", "text": "Escort the convoy"}])
        from test_trading import _two_traders
        _two_traders(gm, distance=6000.0)
        gm.trading.cfg.update(spawn_interval=0.5)  # route cannot arrive before raid
        run_for(gm, 1.0)
        c = next(e for e in st.entities.values()
                 if e.alive and e.data_id == "trade_convoy" and e.owner == 0)
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": c,
            "damage": 10**9, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 1.0, "weapon": None, "impact_pos": c.pos.copy(),
        })
        run_for(gm, 0.2)
        self.assertTrue(gm.mission.failed)


if __name__ == "__main__":
    unittest.main()