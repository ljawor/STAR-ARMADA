"""Core simulation tests: setup, economy, movement, combat, subsystems."""
import unittest

from helpers import make_game, run_for
from game.core.vectors import Vec3
from game.core.commands import MoveCommand, AttackCommand
from game.data.store import DataStore


class TestSetup(unittest.TestCase):
    def test_map_loads(self):
        gm = make_game()
        st = gm.state
        self.assertEqual(len(st.players), 2)
        self.assertGreater(len(st.entities), 20)
        planets = [e for e in st.entities.values() if e.is_planet]
        self.assertEqual(len(planets), 15)   # 8 planets + 5 asteroid fields + 2 gas giants
        kinds = [e.data_id for e in planets]
        self.assertIn("asteroid_field", kinds)
        self.assertIn("temperate", kinds)

    def test_start_units(self):
        gm = make_game(ai=False)
        st = gm.state
        for pid in (0, 1):
            mine = [e for e in st.entities.values() if e.alive and e.owner == pid]
            kinds = [e.data_id for e in mine]
            self.assertIn("command_station", kinds)
            self.assertIn("imperial_constructor", kinds)
            self.assertIn("imperial_tie_squadron", kinds)
            self.assertIn("imperial_corvette", kinds)

    def test_command_capacity(self):
        gm = make_game()
        p0 = gm.state.players[0]
        # base 10 + command station 20
        self.assertEqual(p0.command_capacity, 30)


class TestEconomy(unittest.TestCase):
    def test_passive_income(self):
        gm = make_game(ai=False)
        p0 = gm.state.players[0]
        c0 = p0.credits
        run_for(gm, 10)
        self.assertGreater(p0.credits, c0)

    def test_mining_income(self):
        gm = make_game(ai=False)
        st = gm.state
        # place a mining station via construction system at the home asteroid field
        builder = next(e for e in st.entities.values()
                       if e.alive and e.owner == 0 and e.is_construction)
        ast = next(e for e in st.entities.values() if e.data_id == "asteroid_field"
                   and e.pos.x < 0)
        ok = gm.construction.start_station(builder.id, "mining_station", ast.pos.copy(), 0)
        self.assertTrue(ok)
        run_for(gm, 25)   # build 20s + a bit
        station = next((e for e in st.entities.values()
                        if e.is_station and e.data_id == "mining_station"), None)
        self.assertIsNotNone(station)
        m0 = st.players[0].materials
        run_for(gm, 10)
        self.assertGreater(st.players[0].materials, m0 + 15)


class TestMovement(unittest.TestCase):
    def test_move_order(self):
        gm = make_game(ai=False)
        st = gm.state
        ship = next(e for e in st.entities.values()
                    if e.alive and e.owner == 0 and e.is_ship and not e.is_construction
                    and not e.is_squadron)
        start = ship.pos.copy()
        target = Vec3(start.x, 0, start.z + 3000)
        st.queue_command(MoveCommand(0, [ship.id], target))
        run_for(gm, 40)
        self.assertLess(ship.pos.dist(target), 500)
        self.assertGreater(ship.pos.dist(start), 1500)

    def test_separation_no_overlap(self):
        gm = make_game(ai=False)
        st = gm.state
        ships = [e for e in st.entities.values() if e.alive and e.is_ship]
        a, b = ships[0], ships[1]
        a.pos.set(Vec3(0, 0, 0))
        b.pos.set(Vec3(5, 0, 0))
        run_for(gm, 2)
        self.assertGreater(a.pos.dist(b.pos), a.radius * 0.5 + b.radius * 0.5)


class TestCombat(unittest.TestCase):
    def _fight_setup(self):
        gm = make_game(ai=False)
        st = gm.state
        return gm, st

    def test_ships_fight_and_die(self):
        gm, st = self._fight_setup()
        # spawn two enemy frigates near each other
        fr0 = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(-500, 0, 0))
        fr1 = gm.factory.spawn_ship("imperial_frigate", 1, Vec3(500, 0, 0))
        st.queue_command(AttackCommand(0, [fr0.id], fr1.id))
        st.queue_command(AttackCommand(1, [fr1.id], fr0.id))
        dead_seen = False
        for _ in range(60 * 90):     # up to 90 sim-seconds
            gm.step(1 / 30)
            if not fr0.alive or not fr1.alive:
                dead_seen = True
                break
        self.assertTrue(dead_seen, "no ship died in 90s of mutual attack")

    def test_shields_absorb_then_hull(self):
        gm, st = self._fight_setup()
        fr0 = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(0, 0, 0))
        self.assertEqual(fr0.total_shield(), fr0.max_shield_quad * 4)
        # directional shields: ship faces +z, so a hit from +x drains the LEFT (port) quad
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": fr0,
            "damage": 100, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 0.5, "weapon": None, "impact_pos": Vec3(100, 0, 0),
        })
        gm.step(1 / 30)
        self.assertEqual(fr0.shields["left"], fr0.max_shield_quad - 100)
        self.assertEqual(fr0.shields["front"], fr0.max_shield_quad)
        self.assertEqual(fr0.hull, fr0.max_hull)
        # big hit: left quad breaks, hull takes remainder
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": fr0,
            "damage": 5000, "shield_mult": 1.0, "armor_mult": 1.0,
            "system_mult": 0.5, "weapon": None, "impact_pos": Vec3(100, 0, 0),
        })
        gm.step(1 / 30)
        self.assertEqual(fr0.shields["left"], 0)
        self.assertLess(fr0.hull, fr0.max_hull)

    def test_subsystem_damage_slows_ship(self):
        gm, st = self._fight_setup()
        fr = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(0, 0, 0))
        sub = fr.systems["engines"]
        sub.hp = 0
        from game.systems.stats import effective_speed
        from game.systems.stats import effective_speed as es
        spd = es(st, fr)
        sd = DataStore.get().resolve_ship("imperial_frigate")
        self.assertLess(spd, sd.speed * 0.4)

    def test_squadron_losses_reduce_count(self):
        gm, st = self._fight_setup()
        sq = gm.factory.spawn_ship("imperial_tie_squadron", 0, Vec3(0, 0, 0))
        self.assertEqual(sq.fighter_count, 6)
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": sq,
            "damage": sq.max_hull * 0.5, "shield_mult": 0, "armor_mult": 1.0,
            "system_mult": 0.5, "weapon": None, "impact_pos": Vec3(5, 0, 0),
        })
        gm.step(1 / 30)
        self.assertLess(sq.hull, sq.max_hull)
        # kill it fully
        sq.hull = 1
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": None, "target": sq,
            "damage": 100, "shield_mult": 0, "armor_mult": 1.0,
            "system_mult": 0.5, "weapon": None, "impact_pos": Vec3(5, 0, 0),
        })
        gm.step(1 / 30)
        self.assertFalse(sq.alive)

    def test_xp_and_levels(self):
        gm, st = self._fight_setup()
        fr = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(0, 0, 0))
        fr.xp = 0
        st.damage_queue.append({
            "attacker_id": 1, "attacker_entity": fr, "target": None, "damage": 0,
        })
        # direct kill credit
        victim = gm.factory.spawn_ship("imperial_tie_squadron", 1, Vec3(100, 0, 0))
        gm.damage._kill(victim, fr, 0)
        self.assertGreater(fr.xp, 0)
        self.assertEqual(fr.level, 1)   # small kill = below first threshold


class TestAbilities(unittest.TestCase):
    def _fight_setup(self):
        gm = make_game(ai=False)
        st = gm.state
        return gm, st

    def test_overdrive_and_cooldown(self):
        gm, st = self._fight_setup()
        cv = gm.factory.spawn_ship("imperial_corvette", 0, Vec3(0, 0, 0))
        ok = gm.abilities.activate(cv, "engine_overdrive")
        self.assertTrue(ok)
        self.assertGreater(cv.ability_active.get("engine_overdrive", 0), 0)
        self.assertGreater(cv.ability_cooldowns.get("engine_overdrive", 0), 0)
        # second activation blocked by cooldown
        cv2 = gm.factory.spawn_ship("imperial_corvette", 0, Vec3(50, 0, 0))
        self.assertTrue(gm.abilities.activate(cv2, "engine_overdrive"))
        cv2.ability_cooldowns["engine_overdrive"] = 10
        cv2.ability_active.clear()
        self.assertFalse(gm.abilities.activate(cv2, "engine_overdrive"))

    def test_emp_burst(self):
        gm, st = self._fight_setup()
        caster = gm.factory.spawn_ship("imperial_cruiser", 0, Vec3(0, 0, 0))
        victim = gm.factory.spawn_ship("imperial_corvette", 1, Vec3(200, 0, 0))
        sys_hp_before = victim.systems["engines"].hp
        ok = gm.abilities.activate(caster, "emp_burst")
        self.assertTrue(ok)
        gm.step(1 / 30)
        self.assertLess(victim.systems["engines"].hp, sys_hp_before)
        self.assertLess(victim.total_shield(), victim.max_shield_quad * 4)


class TestSaveLoad(unittest.TestCase):
    def test_roundtrip(self):
        gm = make_game(ai=False)
        st = gm.state
        run_for(gm, 3)
        # damage a ship first
        ship = next(e for e in st.entities.values() if e.is_ship and e.owner == 0)
        ship.hull *= 0.6
        data = st.to_dict()
        st2 = type(st).from_dict(data)
        self.assertEqual(len(st2.entities), len(st.entities))
        self.assertAlmostEqual(st2.players[0].credits, st.players[0].credits, places=1)
        ship2 = st2.entities[ship.id]
        self.assertAlmostEqual(ship2.hull, ship.hull, places=1)
        # systems survive
        self.assertIn("engines", ship2.systems)
        # continue stepping the restored state
        gm2 = type(gm)(state=st2)
        run_for(gm2, 1)
        self.assertEqual(len(st2.entities), len(st.entities))


if __name__ == "__main__":
    unittest.main()