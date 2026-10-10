"""Authoritative construction ownership, through real TCP and direct APIs."""
from copy import deepcopy
import time
import unittest

from helpers import make_game
from test_lan import free_port, pump
from game.core.commands import BuildStationCommand, ColonizeCommand
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.net.lan import precise_checksum


def actors(gm):
    st = gm.state
    builders = []
    colonizers = []
    for owner in (0, 1):
        builder = next(e for e in st.entities.values()
                       if e.owner == owner and e.is_construction
                       and 'research_station' in gm.ds.ships[e.data_id].can_build_stations)
        builder.pos = Vec3(-5000 + owner * 10000, 0, -9000)
        builders.append(builder)
        colonizers.append(gm.factory.spawn_ship(
            'imperial_colonizer', owner, Vec3(-4000 + owner * 8000, 0, -9000)))
        for resource in ('credits', 'materials', 'energy', 'crew'):
            setattr(st.players[owner], resource, 100000)
    planet = st.entities[8]
    assert planet.is_planet and planet.colonized_by is None
    return builders, colonizers, planet


def protected(gm, units):
    return deepcopy(([((e.pos.x, e.pos.y, e.pos.z), e.order_type,
                       (e.order_target_pos.x, e.order_target_pos.y, e.order_target_pos.z)
                       if e.order_target_pos else None,
                       e.order_target_id, e.build_queue) for e in units],
                     [(p.credits, p.materials, p.energy, p.crew)
                      for p in gm.state.players.values()], gm.state.stats))


class LanOwnershipTests(unittest.TestCase):
    def setup_match(self, allied):
        from game.net.lan import LanSession, default_lan_options
        options = default_lan_options()
        options.update(human_count=2, ai_count=0, cooperative=allied)
        host = LanSession.host(free_port(), options)
        self.addCleanup(host.close)
        client = LanSession.join('127.0.0.1', host.port)
        self.addCleanup(client.close)
        sessions = [host, client]
        pump(sessions, lambda: all(len(s.snapshot['players']) == 2 for s in sessions))
        for s in sessions:
            s.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        host.start()
        pump(sessions, lambda: all(s.launch is not None for s in sessions))
        launches = [s.launch for s in sessions]
        assert all(launch is not None for launch in launches)
        managers = [GameManager.start_skirmish(launch['map_def']) for launch in launches]
        control = GameManager.start_skirmish(launches[0]['map_def'])
        for gm in managers + [control]:
            if allied:
                for p in gm.state.players.values():
                    p.team = 0
            actors(gm)
        for s, gm in zip(sessions, managers):
            gm.state._net_session = s
        self.assertEqual(precise_checksum(managers[0]), precise_checksum(managers[1]))
        return sessions, managers, control

    def advance(self, sessions, managers, ticks=None):
        if ticks is None:
            from game.net.lan import INPUT_DELAY
            ticks = INPUT_DELAY + 3
        for _ in range(ticks):
            stepped = set()
            deadline = time.monotonic() + 3
            while len(stepped) < len(sessions) and time.monotonic() < deadline:
                for i, (s, gm) in enumerate(zip(sessions, managers)):
                    if i not in stepped and s.advance(gm, 1/30):
                        stepped.add(i)
                time.sleep(.0001)
            self.assertEqual(len(stepped), len(sessions), [s.snapshot for s in sessions])
            self.assertEqual(precise_checksum(managers[0]), precise_checksum(managers[1]))

    def test_real_tcp_rejects_enemy_and_allied_constructor(self):
        for allied in (False, True):
            with self.subTest(allied=allied):
                sessions, managers, control = self.setup_match(allied)
                builder = next(e for e in managers[1].state.entities.values()
                               if e.owner == 0 and e.is_construction
                               and 'research_station' in managers[1].ds.ships[e.data_id].can_build_stations)
                site = builder.pos + Vec3(600, 0, 0)
                self.assertTrue(managers[1].construction.check_site('research_station', site, builder)[0])
                managers[1].state.queue_command(BuildStationCommand(1, builder.id, 'research_station', site))
                self.advance(sessions, managers)
                for _ in range(managers[0].state.tick):
                    control.step(1/30)
                for gm in managers:
                    self.assertEqual(protected(gm, [gm.state.entities[builder.id]]),
                                     protected(control, [control.state.entities[builder.id]]))
                for s in sessions:
                    s.close()

    def test_real_tcp_rejects_enemy_and_allied_colonizer(self):
        for allied in (False, True):
            for nearby in (False, True):
                with self.subTest(allied=allied, nearby=nearby):
                    sessions, managers, control = self.setup_match(allied)
                    colonizer = next(e for e in managers[1].state.entities.values()
                                     if e.owner == 0 and e.data_id == 'imperial_colonizer')
                    planet = managers[1].state.entities[8]
                    if nearby:
                        for gm in managers + [control]:
                            gm.state.entities[colonizer.id].pos = planet.pos + Vec3(planet.radius + 300, 0, 0)
                    managers[1].state.queue_command(ColonizeCommand(1, [colonizer.id], planet.id))
                    self.advance(sessions, managers)
                    for _ in range(managers[0].state.tick):
                        control.step(1/30)
                    for gm in managers:
                        self.assertEqual(protected(gm, [gm.state.entities[colonizer.id]]),
                                         protected(control, [control.state.entities[colonizer.id]]))
                        self.assertIsNone(gm.state.entities[planet.id].colonized_by)
                    for s in sessions:
                        s.close()


    def test_real_tcp_own_station_and_colonization_complete(self):
        import math
        sessions, managers, _ = self.setup_match(False)
        gm = managers[1]
        builder = next(e for e in gm.state.entities.values()
                       if e.owner == 1 and e.is_construction
                       and 'research_station' in gm.ds.ships[e.data_id].can_build_stations)
        colonizer = next(e for e in gm.state.entities.values()
                         if e.owner == 1 and e.data_id == 'imperial_colonizer')
        planet = gm.state.entities[8]
        for manager in managers:
            manager.state.entities[colonizer.id].pos = planet.pos + Vec3(planet.radius + 300, 0, 0)
        before = gm.state.players[1].credits
        site = builder.pos + Vec3(600, 0, 0)
        gm.state.queue_command(BuildStationCommand(1, builder.id, 'research_station', site))
        gm.state.queue_command(ColonizeCommand(1, [colonizer.id], planet.id))
        self.advance(sessions, managers)
        self.assertLess(gm.state.players[1].credits, before)
        self.assertEqual(builder.build_queue[0]['kind'], 'station')
        self.assertEqual(colonizer.build_queue[0]['status'], 'paid')
        ticks = math.ceil((max(gm.ds.stations['research_station'].build_time, 15) + 1) * 30)
        self.advance(sessions, managers, ticks)
        for manager in managers:
            self.assertEqual(manager.state.entities[planet.id].colonized_by, 1)
            self.assertNotIn(colonizer.id, manager.state.entities)
            self.assertTrue(any(e.owner == 1 and e.data_id == 'research_station'
                                and e.pos.dist(site) < 1 for e in manager.state.entities.values()))


class DirectOwnershipTests(unittest.TestCase):
    def test_station_rejects_wrong_owner_missing_dead_and_wrong_kind(self):
        for invalid in ('enemy', 'ally', 'missing', 'dead', 'wrong_kind'):
            with self.subTest(invalid=invalid):
                gm = make_game(ai=False)
                builders, _, _ = actors(gm)
                builder = builders[0]
                player = 1 if invalid in ('enemy', 'ally') else 0
                if invalid == 'ally':
                    for p in gm.state.players.values():
                        p.team = 0
                if invalid == 'dead':
                    builder.alive = False
                if invalid == 'wrong_kind':
                    builder.is_construction = False
                before = protected(gm, [builder])
                self.assertFalse(gm.construction.start_station(
                    -999 if invalid == 'missing' else builder.id, 'research_station',
                    builder.pos + Vec3(600, 0, 0), player))
                self.assertEqual(protected(gm, [builder]), before)

    def test_colonize_rejects_wrong_owner_missing_dead_and_wrong_kind(self):
        for invalid in ('enemy', 'ally', 'missing', 'dead', 'wrong_kind',
                        'missing_planet', 'dead_planet', 'wrong_planet_kind'):
            for nearby in (False, True):
                with self.subTest(invalid=invalid, nearby=nearby):
                    gm = make_game(ai=False)
                    builders, colonizers, planet = actors(gm)
                    colonizer = colonizers[0]
                    player = 1 if invalid in ('enemy', 'ally') else 0
                    if nearby:
                        colonizer.pos = planet.pos + Vec3(planet.radius + 300, 0, 0)
                    if invalid == 'ally':
                        for p in gm.state.players.values():
                            p.team = 0
                    if invalid == 'dead':
                        colonizer.alive = False
                    if invalid == 'wrong_kind':
                        colonizer.data_id = builders[0].data_id
                    if invalid == 'dead_planet':
                        planet.alive = False
                    if invalid == 'wrong_planet_kind':
                        planet.is_planet = False
                    before = protected(gm, [colonizer])
                    self.assertFalse(gm.construction.start_colonize(
                        -999 if invalid == 'missing' else colonizer.id,
                        -999 if invalid == 'missing_planet' else planet.id, player))
                    self.assertEqual(protected(gm, [colonizer]), before)
                    self.assertIsNone(planet.colonized_by)

    def test_own_colonizer_can_travel_without_control_fee(self):
        from game.systems.colonies import colony_rules
        gm = make_game(ai=False)
        _, colonizers, planet = actors(gm)
        colonizer = colonizers[0]
        before = protected(gm, [colonizer])[1]
        self.assertTrue(gm.construction.start_colonize(colonizer.id, planet.id, 0))
        self.assertIsNone(colonizer.order_target_id)
        self.assertEqual(colonizer.order_type, 'move')
        self.assertEqual(colonizer.build_queue[0]['planet_id'], planet.id)
        self.assertEqual(colonizer.build_queue[0]['status'], 'traveling')
        approach = colonizer.order_target_pos
        self.assertIsNotNone(approach)
        self.assertGreater(approach.dist(planet.pos), planet.radius + colonizer.radius)
        self.assertLess(approach.dist(planet.pos), planet.radius + colony_rules()['approach_range'])
        self.assertEqual(protected(gm, [colonizer])[1], before)

    def test_station_rejects_nonship_constructor_without_mutations(self):
        gm = make_game(ai=False)
        builders, _, _ = actors(gm)
        builder = builders[0]
        builder.is_ship = False
        before = protected(gm, [builder])
        self.assertFalse(gm.construction.start_station(
            builder.id, 'research_station', builder.pos + Vec3(600, 0, 0), 0))
        self.assertEqual(protected(gm, [builder]), before)

    def test_colonize_rejects_nonship_colonizer_without_mutations(self):
        gm = make_game(ai=False)
        _, colonizers, planet = actors(gm)
        colonizer = colonizers[0]
        colonizer.is_ship = False
        before = protected(gm, [colonizer])
        self.assertFalse(gm.construction.start_colonize(colonizer.id, planet.id, 0))
        self.assertEqual(protected(gm, [colonizer]), before)


if __name__ == '__main__':
    unittest.main()
