"""Focused real-simulation acceptance tests for built-in skirmish maps."""
from collections import Counter
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import unittest

from game.core.manager import GameManager
from game.ai.ai import AIPlayer
from game.core.vectors import Vec3
from game.data.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
STARTERS = Counter(command_station=1, shipyard=1, imperial_constructor=1,
                   imperial_tie_squadron=2, imperial_corvette=2)


class SkirmishMapsTests(unittest.TestCase):
    def check_map(self, map_id, capacity):
        ds = DataStore()
        self.assertIn(map_id, ds.maps, 'Missing playable skirmish map')
        m = ds.maps[map_id]
        self.assertEqual(len(m['players']), capacity)
        self.assertEqual(m.get('max_players'), capacity)
        self.assertGreater(len(m['description']), 80)
        self.assertEqual([p['slot'] for p in m['players']], list(range(capacity)))
        self.assertEqual([p['team'] for p in m['players']], list(range(capacity)))
        self.assertEqual([p['is_ai'] for p in m['players']], [False] + [True] * (capacity - 1))
        gm = GameManager.start_skirmish(m)
        st = gm.state
        self.assertEqual(set(st.players), set(range(capacity)))
        neutral_ids = [v['id'] for key in ('asteroid_fields', 'gas_giants', 'planets')
                       for v in m.get(key, [])]
        self.assertEqual(len(neutral_ids), len(set(neutral_ids)))
        bodies = [e for e in st.entities.values() if e.is_planet and e.data_id != 'asteroid_field']
        miners = [e for e in st.entities.values() if e.data_id == 'asteroid_field']
        colonies = [e for e in bodies if e.data_id not in ('barren', 'gas_giant')]
        mine_distances, colony_distances = [], []
        resources = []
        for pid, player in st.players.items():
            units = gm.player_entities(pid)
            self.assertEqual(Counter(e.data_id for e in units), STARTERS)
            resources.append((player.credits, player.materials, player.energy, player.crew))
            self.assertTrue(all(math.isfinite(v) and v > 0 for v in resources[-1]))
            for e in units:
                # Jump/navigation treats bounds as full width; include hull footprint.
                self.assertLessEqual(abs(e.pos.x) + e.radius, m['bounds'] / 2)
                self.assertLessEqual(abs(e.pos.z) + e.radius, m['bounds'] / 2)
                for body in bodies:
                    self.assertGreaterEqual(e.pos.dist(body.pos), body.radius + e.radius + 120,
                                            (map_id, pid, e.data_id, body.name_override))
                for other in units:
                    if e.id != other.id and other.is_station:
                        self.assertGreaterEqual(e.pos.dist(other.pos), e.radius + other.radius + 40)
            home = next(e for e in units if e.data_id == 'command_station')
            builder = next(e for e in units if e.is_construction)
            mine = min(miners, key=lambda e: home.pos.dist(e.pos))
            colony = min(colonies, key=lambda e: home.pos.dist(e.pos))
            mine_distances.append(home.pos.dist(mine.pos))
            colony_distances.append(home.pos.dist(colony.pos))
            self.assertLess(mine_distances[-1], 6500)
            self.assertLess(colony_distances[-1], 7500)
            brain = AIPlayer(st, pid)
            site = brain._find_asteroid_site(home)
            self.assertIsNotNone(site)
            self.assertTrue(gm.construction.check_site('mining_station', site, builder)[0])
            # Every possible AI half-radius mining sample is legal, not only this seed.
            for angle in range(24):
                a = angle * math.tau / 24
                site = Vec3(mine.pos.x + math.sin(a) * mine.radius / 2, 0,
                            mine.pos.z + math.cos(a) * mine.radius / 2)
                self.assertTrue(gm.construction.check_site('mining_station', site, builder)[0])
                self.assertLessEqual(abs(site.x) + 100, m['bounds'] / 2)
                self.assertLessEqual(abs(site.z) + 100, m['bounds'] / 2)
            for kind in ('trade_station', 'research_station', 'shipyard'):
                site = brain._find_station_site(kind, 900, home, builder)
                self.assertIsNotNone(site, (map_id, pid, kind))
                self.assertTrue(gm.construction.check_site(kind, site, builder)[0])
            # Enemies begin entirely outside live sensors; their sensor circles are disjoint.
            for other in st.players:
                if other != pid:
                    self.assertFalse(any(st.can_see(pid, e.id) for e in gm.player_entities(other)))
                    for e in units:
                        for enemy in gm.player_entities(other):
                            self.assertGreater(e.pos.dist(enemy.pos), e.sensor_range + enemy.sensor_range)
            if map_id != 'skirmish01':
                # Direct early mining travel has no gravity-well obstruction.
                delta = mine.pos - builder.pos
                for body in bodies:
                    fraction = max(0, min(1, (body.pos - builder.pos).dot(delta) / delta.length_sq()))
                    closest = builder.pos + delta * fraction
                    self.assertGreater(closest.dist(body.pos), body.radius + builder.radius + 120)
        self.assertEqual(len(set(resources)), 1)
        self.assertLess(max(mine_distances) - min(mine_distances), 2)
        if map_id != 'skirmish01':
            # Kotarri's trade/barren near-base worlds are intentionally legacy-asymmetric.
            self.assertLess(max(colony_distances) - min(colony_distances), 2)
        if map_id != 'skirmish01':
            self.assertGreaterEqual(m['bounds'], 30000)
            for e in st.entities.values():
                self.assertLessEqual(abs(e.pos.x) + e.radius, m['bounds'] / 2)
                self.assertLessEqual(abs(e.pos.z) + e.radius, m['bounds'] / 2)
            for a, b in combinations([e for e in st.entities.values() if e.is_planet], 2):
                self.assertGreater(a.pos.dist(b.pos), a.radius + b.radius)
        initial = json.dumps(st.to_dict(precise=True), sort_keys=True)
        duplicate = GameManager.start_skirmish(DataStore().maps[map_id])
        self.assertEqual(initial, json.dumps(duplicate.state.to_dict(precise=True), sort_keys=True))
        for _ in range(90):
            gm.step(1 / 30)
            duplicate.step(1 / 30)
        self.assertEqual(st.tick, 90)
        self.assertFalse(st.game_over)
        self.assertEqual(json.dumps(st.to_dict(precise=True), sort_keys=True),
                         json.dumps(duplicate.state.to_dict(precise=True), sort_keys=True))
        for pid in range(1, capacity):
            self.assertIn(pid, gm.ai.ais)
            self.assertGreater(gm.ai.ais[pid]._count_stations('mining_station'), 0)

    def test_sector_duel_preserves_legacy_gameplay(self):
        m = json.loads((ROOT / 'assets/data/maps/skirmish01.json').read_text())
        for key in ('name', 'description', 'max_players'):
            m.pop(key, None)
        # Captured from the original fixture before adding public UI metadata.
        self.assertEqual(hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest(),
                         'd0e4219286b2dbe653fc7824ed5727d4ea2b4921699070e37eef671259b1b25f')

    def test_sector_duel_capacity_load_spawns(self):
        self.check_map('skirmish01', 2)

    def test_nebula_frontier_capacity_load_spawns(self):
        self.check_map('skirmish04', 4)

    def test_crossroads_capacity_load_spawns(self):
        self.check_map('skirmish03', 4)

    def test_trinary_reach_capacity_load_spawns(self):
        self.check_map('skirmish02', 3)


if __name__ == '__main__':
    unittest.main()
