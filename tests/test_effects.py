"""Effects tests: kill/hit effects must carry the data the renderer needs.

The explosion was reported "still too simple" and the impact as "a flat white
disc". Both root causes were in the SIM layer (what gets spawned), so they are
testable headlessly — no GL context needed.

  - hull_hit was spawned with NO colour, so the renderer's default (1,1,1)
    under ADDITIVE blending saturated into a solid white disc
  - explosion carried no per-blast variation, so every kill looked identical
"""
import unittest

from helpers import make_game, run_for
from game.core.vectors import Vec3


def _first_effect(st, kind):
    for fx in st.effects:
        if fx["kind"] == kind:
            return fx
    return None


class TestHitEffectData(unittest.TestCase):
    def _damage(self, gm, target, dmg, impact):
        """Push damage through the REAL damage queue."""
        st = gm.state
        st.damage_queue.append({
            "target": target, "damage": dmg, "shield_mult": 1.0,
            "armor_mult": 1.0, "system_mult": 1.0,
            "attacker_entity": None, "attacker_id": -1,
            "weapon": None, "impact_pos": impact,
        })
        gm.damage.update(1 / 30)

    def test_hull_hit_spawns_with_a_colour(self):
        """A colourless hull_hit defaulted to (1,1,1) -> a flat white disc."""
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.is_ship and e.owner == 0)
        ship.shields = {k: 0.0 for k in ship.shields}   # force a hull hit
        self._damage(gm, ship, 5.0, ship.pos + Vec3(0.0, 0.0, 12.0))
        fx = _first_effect(st, "hull_hit")
        self.assertIsNotNone(fx, "no hull_hit effect was spawned")
        assert fx is not None
        self.assertIn("color", fx, "hull_hit has no colour -> renders white")
        r, g, b = fx["color"][:3]
        # the bug was an ALL-channel white; a warm spark may legitimately have
        # r=1.0, so assert on the property that actually mattered: not white
        self.assertFalse(r > 0.97 and g > 0.97 and b > 0.97,
                         f"hull_hit colour {fx['color']} is saturated white")
        self.assertGreater(r, g, "impact should be warm (r > g > b)")
        self.assertGreater(g, b)

    def test_explosion_carries_size_and_seed(self):
        """size drives the blast scale; seed varies its shape per kill."""
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.is_ship and e.owner == 0)
        self._damage(gm, ship, 99999.0, ship.pos + Vec3(0.0, 0.0, 8.0))
        self.assertFalse(ship.alive, "ship should have been destroyed")
        fx = _first_effect(st, "explosion")
        self.assertIsNotNone(fx, "no explosion effect was spawned")
        assert fx is not None
        self.assertIn("size", fx)
        self.assertGreater(fx["size"], 0.0)
        self.assertIn("seed", fx, "no seed -> every blast looks identical")

    def test_explosion_seed_is_deterministic(self):
        """Same seed state -> same blast seed (replay/lockstep safety).

        The seed comes from state.rng(), which is derived from the sim seed and
        tick. Pulling it from the RENDERER's rng (or wall clock) would break
        bit-exact replays.
        """
        def seeds():
            gm = make_game(ai=False)
            st = gm.state
            ship = next(e for e in st.entities.values()
                        if e.alive and e.is_ship and e.owner == 0)
            st.damage_queue.append({
                "target": ship, "damage": 99999.0, "shield_mult": 1.0,
                "armor_mult": 1.0, "system_mult": 1.0,
                "attacker_entity": None, "attacker_id": -1,
                "weapon": None, "impact_pos": ship.pos + Vec3(0.0, 0.0, 8.0),
            })
            gm.damage.update(1 / 30)
            fx = _first_effect(st, "explosion")
            assert fx is not None
            return fx["seed"]

        self.assertEqual(seeds(), seeds(),
                         "explosion seed is not reproducible")

    def test_seed_varies_between_kills(self):
        """Different kills at different ticks must not look identical."""
        gm = make_game(ai=False)
        st = gm.state
        ships = [e for e in st.entities.values()
                 if e.alive and e.is_ship and e.owner == 0][:2]
        self.assertGreaterEqual(len(ships), 2)
        for s in ships:
            st.damage_queue.append({
                "target": s, "damage": 99999.0, "shield_mult": 1.0,
                "armor_mult": 1.0, "system_mult": 1.0,
                "attacker_entity": None, "attacker_id": -1,
                "weapon": None, "impact_pos": s.pos + Vec3(0.0, 0.0, 8.0),
            })
            gm.damage.update(1 / 30)
            run_for(gm, 0.5)          # advance the tick so rng() differs
        blast_seeds = [f["seed"] for f in st.effects if f["kind"] == "explosion"]
        self.assertEqual(len(blast_seeds), 2)
        self.assertNotEqual(blast_seeds[0], blast_seeds[1],
                            "both kills got the same seed")


if __name__ == "__main__":
    unittest.main()
