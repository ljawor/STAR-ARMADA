"""Remote colony ownership is an observed contact even without sensor coverage."""
import json
import unittest

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3


class ColonyVisibilityTests(unittest.TestCase):
    def test_remote_settlement_and_capture_refresh_allied_last_observed_owner(self):
        for previous_owner in (None, 1):
            for settler_owner in (0, 2):
                with self.subTest(previous_owner=previous_owner, settler_owner=settler_owner):
                    gm = make_game(ai=False)
                    st = gm.state
                    st.players[0].team = 0
                    st.players[1].team = 1
                    st.players[2] = PlayerState(2, team=0)
                    # Keep opposing starting forces alive, but outside remote sensors.
                    for e in st.entities.values():
                        if not e.is_planet:
                            e.pos = Vec3(-11000 if e.owner == 0 else 11000, 0, -11000)
                    planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
                    planet.pos = Vec3(4000.123456789, 100.234567891, 4000.345678912)
                    planet.radius = 501.234567891
                    planet.colonized_by = previous_owner
                    ship = gm.factory.spawn_ship('imperial_colonizer', settler_owner,
                                                 planet.pos + Vec3(0, 0, planet.radius + 300))
                    gm.visibility.update()
                    for viewer in (0, 2):
                        self.assertEqual(st.discovered_planets[viewer][planet.id].colonized_by,
                                         previous_owner)
                    gm.ds.rules['colonies']['control_seconds'] = .1
                    st.queue_command(PlayerCommand('colonize', settler_owner,
                                     unit_ids=(ship.id,), target_id=planet.id))
                    start_tick = st.tick
                    for _ in range(12):
                        gm.step(1 / 30)
                    self.assertEqual(st.tick, start_tick + 12, 'victory froze the fixture')
                    self.assertEqual(planet.colonized_by, settler_owner)
                    self.assertNotIn(ship.id, st.entities, 'successful control must consume observer')
                    self.assertFalse(st.is_position_visible(0, planet.pos), 'other sensors cover colony')
                    for viewer in (0, 2):
                        self.assertTrue(st.can_see(viewer, planet.id))
                        self.assertEqual(st.discovered_planets[viewer][planet.id].colonized_by,
                                         settler_owner, 'remote visible ownership was not remembered')
                    # Runtime production is private even while the colony is always visible.
                    planet.build_queue = [dict(item='attack_satellite', time_left=13.25, total=22)]
                    gm.visibility.update()
                    for viewer in (0, 2):
                        self.assertEqual(st.discovered_planets[viewer][planet.id].build_queue, [])
                    # A later hidden enemy transfer must retain the last observed colony owner.
                    planet.colonized_by = 1
                    planet.name_override = 'Hidden enemy rename'
                    gm.visibility.update()
                    for viewer in (0, 2):
                        self.assertFalse(st.can_see(viewer, planet.id))
                        known = st.known_entity(viewer, planet.id)
                        assert known is not None
                        self.assertEqual(known.colonized_by, settler_owner)
                        self.assertNotEqual(known.name_override, planet.name_override)
                        self.assertEqual(known.pos, planet.pos)
                        self.assertEqual(known.radius, planet.radius)
                    saved = json.loads(json.dumps(st.to_dict(precise=True)))
                    restored = GameManager(GameState.from_dict(saved))
                    snapshot = lambda state: json.loads(json.dumps(state.to_dict(precise=True)))
                    self.assertEqual(snapshot(restored.state), saved)
                    for _ in range(3):
                        gm.step(1 / 30)
                        restored.step(1 / 30)
                        self.assertEqual(snapshot(restored.state), snapshot(st))
                        for viewer in (0, 2):
                            known = restored.state.known_entity(viewer, planet.id)
                            assert known is not None
                            self.assertEqual(known.colonized_by, settler_owner)

    def test_snapshot_updates_use_eligible_colonies_and_precomputed_sensor_sources(self):
        from unittest.mock import patch
        from game.core.entity import Entity
        from game.systems.colonies import COLONY_TYPES

        gm = make_game(ai=False)
        st = gm.state
        st.entities.clear()
        st.explored_cells.clear()
        st.discovered_planets.clear()
        st.players[0].team = 0
        st.players[1].team = 1
        st.players[2] = PlayerState(2, team=0)
        for eid, kind in enumerate(sorted(COLONY_TYPES) + ['gas_giant', 'unknown_mod'], 1):
            st.add_entity(Entity(eid, 'planet', -1, kind, is_planet=True,
                                 pos=Vec3(4000, 0, 4000), colonized_by=2))
        enemy = st.add_entity(Entity(100, 'planet', -1, 'temperate', is_planet=True,
                                    pos=Vec3(4000, 0, 4000), colonized_by=1))
        dead = st.add_entity(Entity(101, 'planet', -1, 'temperate', is_planet=True,
                                   alive=False, colonized_by=0))
        expected = {e.id for e in st.entities.values() if st.can_see(0, e.id)}
        self.assertEqual(len(expected), len(COLONY_TYPES))
        with patch.object(GameState, 'can_see', wraps=st.can_see) as queries, \
                patch.object(GameState, 'sensor_sources', wraps=st.sensor_sources) as sources:
            gm.visibility.update()
            self.assertEqual(queries.call_count, 0, 'update rescanned observers per planet')
            self.assertEqual(sources.call_count, 2, 'sources were not aggregated once per alliance')
        for viewer in (0, 2):
            self.assertEqual(set(st.discovered_planets[viewer]), expected)
            self.assertNotIn(enemy.id, st.discovered_planets[viewer])
            self.assertNotIn(dead.id, st.discovered_planets[viewer])
        self.assertEqual(st.discovered_planets[1][enemy.id].colonized_by, 1)


if __name__ == '__main__':
    unittest.main()
