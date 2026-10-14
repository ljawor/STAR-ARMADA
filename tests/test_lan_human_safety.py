"""Human LAN intent, exercised through production TCP and input seams."""
import unittest
from game.core.commands import PlayerCommand
from game.net.lan import _commands, precise_checksum
import test_lan
from test_lan import pump
from test_lan_main import factories
from game.core.manager import GameManager
from game.core.commands import StopCommand
from game.core.vectors import Vec3
from types import SimpleNamespace
from unittest.mock import Mock
import time
import pygame


def init_fixture_fonts(case):
    # Existing menus own their initialized subsystem and cached font objects.
    if not pygame.font.get_init():
        pygame.font.init()
        def close_owned_fonts():
            from render import clean_classic
            clean_classic.font.cache_clear()
            pygame.font.quit()
        case.addCleanup(close_owned_fonts)


def setup_pair(case):
    sessions = test_lan.SimulationTests().sessions()
    for session in sessions:
        case.addCleanup(session.close)
    managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
    for session, manager in zip(sessions, managers):
        manager.state._net_session = session
    return sessions, managers


def run_ticks(case, sessions, managers, target):
    # Hold each peer at the same tick: prove EVERY continuation hash, not just
    # final state or a lucky intersection of asynchronously observed ticks.
    for tick in range(managers[0].state.tick + 1, target + 1):
        deadline = time.monotonic() + 10
        while min(g.state.tick for g in managers) < tick:
            for session, manager in zip(sessions, managers):
                if manager.state.tick < tick:
                    session.advance(manager, 1/30)
                case.assertEqual(session.snapshot['status'], 'running', session.snapshot['error'])
            case.assertLess(time.monotonic(), deadline)
        case.assertEqual(precise_checksum(managers[0]), precise_checksum(managers[1]), tick)


class LocalRejectionTests(unittest.TestCase):
    def test_natural_stop_257_rejected_nonfatally_on_both_origins(self):
        from render.input import InputController
        from render.camera import Camera
        from render.hud import HUD
        init_fixture_fonts(self)
        for origin in (0, 1):
            sessions, managers = setup_pair(self)
            ids = None
            for manager in managers:
                ids = [manager.factory.spawn_ship('imperial_corvette', origin,
                       Vec3(i*200, 0, 0)).id for i in range(257)]
            session, gm = sessions[origin], managers[origin]
            ns = factories()
            ns.update(pygame=pygame, state=gm.state, gm=gm, net_session=session, flash=Mock())
            ctrl = InputController(gm.state, Camera(800,600), HUD(800,600,gm.state), SimpleNamespace(flash=Mock()))
            ctrl.local_player = origin
            ns['inputc'] = ctrl
            # Accepted intent survives the rejected next order.
            session.submit(StopCommand(origin, ids[:255]), 0)
            session.submit(StopCommand(origin, ids[:256]), 0)
            saved = list(session._pending)
            ctrl.selection = set(ids)
            ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0, unicode=''))
            self.assertEqual(ns['mode'], 'game')
            self.assertIs(ns['net_session'], session)
            self.assertEqual(session._pending, saved)
            ns['flash'].assert_called_once()
            self.assertIn('256', ns['flash'].call_args.args[0])
            run_ticks(self, sessions, managers, 7)

    def test_65th_order_rejected_atomically_through_main(self):
        for origin in (0, 1):
            sessions, managers = setup_pair(self)
            session, gm = sessions[origin], managers[origin]
            from game.net.replay import MatchRecording
            recording = MatchRecording(managers[0], mode='lan')
            self.addCleanup(recording.close)
            for _ in range(64):
                session.submit(StopCommand(origin, ()), 0)
            saved = list(session._pending)
            ns = factories()
            ns.update(state=gm.state, net_session=session, flash=Mock(),
                inputc=SimpleNamespace(handle_event=lambda ev: gm.state.queue_command(StopCommand(origin, ()))))
            ns['handle_game_input'](object())
            self.assertEqual(ns['mode'], 'game')
            self.assertEqual(session._pending, saved)
            self.assertEqual(gm.state.command_queue, [])
            ns['flash'].assert_called_once()
            self.assertIn('64', ns['flash'].call_args.args[0])
            run_ticks(self, sessions, managers, 7)
            self.assertEqual(len(recording.to_dict()['commands']), 64)
            self.assertEqual({row['tick'] for row in recording.to_dict()['commands']}, {3})

    def test_malformed_crew_schema_is_fatal_through_real_tcp(self):
        for kind in ('board', 'crew_load', 'crew_deliver', 'crew_cancel'):
            valid = PlayerCommand(kind, 1, unit_ids=(12,),
                target_id=13 if kind in ('board', 'crew_deliver') else None).to_dict()
            malformed = [dict(valid, unit_ids=[]), dict(valid, name='private payload')]
            if kind in ('board', 'crew_deliver'):
                missing_target = dict(valid)
                del missing_target['target_id']
                malformed.append(missing_target)
            for recipient in (0, 1):
                for command in malformed:
                    with self.subTest(kind=kind, recipient=recipient, command=command):
                        sessions, managers = setup_pair(self)
                        sessions[1-recipient]._peers[0].send(dict(
                            type='input' if recipient == 0 else 'frame', tick=0,
                            checksum=precise_checksum(managers[1-recipient]), commands=[command]))
                        pump(sessions, lambda: sessions[recipient].snapshot['status'] == 'error')
                        snapshot = sessions[recipient].snapshot
                        self.assertEqual(snapshot['failure_phase'], 'transport')
                        self.assertRegex(snapshot['error'], r'^(Invalid|Missing required)')
                        self.assertEqual(managers[recipient].state.tick, 0)
                        self.assertEqual(managers[recipient].state.command_queue, [])
                        for session in sessions:
                            session.close()

    def test_peer_oversized_input_remains_fatal(self):
        sessions, managers = setup_pair(self)
        sessions[1]._peers[0].send(dict(type='input', tick=0, checksum=precise_checksum(managers[1]),
            commands=[StopCommand(1, range(1,258)).to_dict()]))
        pump(sessions, lambda: sessions[0].snapshot['status'] == 'error')
        self.assertIn('Invalid unit ids', sessions[0].snapshot['error'])



class GameplayAcceptanceTests(unittest.TestCase):
    def test_natural_crew_l_delivery_cancel_paid_once_and_replayed(self):
        from game.net.replay import MatchRecording, PlaybackSession
        from render.input import InputController
        from render.camera import Camera
        from render.hud import HUD
        init_fixture_fonts(self)
        for origin in (0, 1):
            sessions, managers = setup_pair(self)
            for gm in managers:
                gm.factory.spawn_station('command_station', origin, Vec3())
                t = gm.factory.spawn_ship('imperial_crew_transport', origin, Vec3(0,0,300))
                target = gm.factory.spawn_ship('imperial_frigate', origin, Vec3(1200,0,300))
                target.crew -= 20
                target.order_type = 'hold'
            tid, target_id = t.id, target.id
            gm = managers[origin]
            st, p = gm.state, gm.state.players[origin]
            operating = st.entity(tid).crew
            initial_pool, initial_credits = p.crew, p.credits
            recording = MatchRecording(managers[0], mode='lan')
            self.addCleanup(recording.close)
            ctrl = InputController(st, Camera(800,600), HUD(800,600,st), SimpleNamespace(flash=Mock()))
            ctrl.local_player = origin
            ctrl.selection = {tid}
            ns = factories()
            ns.update(pygame=pygame, state=st, gm=gm, net_session=sessions[origin], inputc=ctrl, flash=Mock())
            ns['handle_game_input'](pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l, mod=0, unicode=''))
            self.assertEqual(ns['mode'], 'game')
            run_ticks(self, sessions, managers, 40)
            loaded = st.entity(tid).crew_cargo
            self.assertGreater(loaded, 0)
            pool_spent = initial_pool + p.income_frame['crew'] * 40/30 - p.crew
            self.assertAlmostEqual(pool_spent, loaded)
            self.assertAlmostEqual(initial_credits + p.income_frame['credits'] * 40/30 - p.credits, 2*loaded)
            # Cancel preserves paid passengers and prevents further purchases.
            st.queue_command(PlayerCommand('crew_cancel', origin, unit_ids=(tid,)))
            run_ticks(self, sessions, managers, 47)
            cancelled_cargo = st.entity(tid).crew_cargo
            self.assertEqual(st.entity(tid).crew_mission, {})
            pool, credits = p.crew, p.credits
            st.queue_command(PlayerCommand('crew_deliver', origin, unit_ids=(tid,), target_id=target_id))
            run_ticks(self, sessions, managers, 720)
            self.assertEqual(st.entity(tid).crew_cargo, 0)
            self.assertEqual(st.entity(target_id).crew, st.entity(target_id).max_crew - 20 + cancelled_cargo)
            self.assertEqual(st.entity(tid).crew, operating)
            self.assertAlmostEqual(p.crew, pool + p.income_frame['crew'] * (720-47)/30)
            self.assertAlmostEqual(p.credits, credits + p.income_frame['credits'] * (720-47)/30)
            data = recording.to_dict()
            self.assertEqual([e['cmd']['type'] for e in data['commands']], ['crew_load', 'crew_cancel', 'crew_deliver'])
            self.assertEqual([e['tick'] for e in data['commands']], [3, 43, 50])
            playback = PlaybackSession(data)
            while playback.step():
                pass
            self.assertEqual(precise_checksum(playback.gm), precise_checksum(managers[0]))

    def test_board_capture_and_source_ownership_both_origins_replay_once(self):
        from game.net.replay import MatchRecording, PlaybackSession
        for origin in (0, 1):
            sessions, managers = setup_pair(self)
            for gm in managers:
                source = gm.factory.spawn_ship('imperial_cruiser', origin, Vec3(0,0,0))
                if 'weapons' in source.systems:
                    source.systems['weapons'].hp = 0
                target = gm.factory.spawn_ship('imperial_frigate', 1-origin, Vec3(500,0,0))
                target.crew = 0
                target.shields = {key: 0. for key in target.shields}
                gm.visibility.update()
            sid, target_id = source.id, target.id
            st = managers[origin].state
            total = st.entity(sid).crew
            recording = MatchRecording(managers[0], mode='lan')
            self.addCleanup(recording.close)
            st.queue_command(PlayerCommand('board', origin, unit_ids=(sid,sid), target_id=target_id))
            run_ticks(self, sessions, managers, 240)
            self.assertEqual(st.entity(target_id).owner, origin)
            self.assertEqual(st.entity(sid).crew + st.entity(target_id).crew + sum(
                e.crew for e in st.entities.values() if e.boarding), total)
            self.assertEqual(len(recording.to_dict()['commands']), 1)
            playback = PlaybackSession(recording.to_dict())
            while playback.step():
                pass
            self.assertEqual(precise_checksum(playback.gm), precise_checksum(managers[0]))

    def test_foreign_source_and_allied_target_are_gameplay_noops(self):
        for kind in ('board', 'crew_load', 'crew_deliver', 'crew_cancel'):
            sessions, managers = setup_pair(self)
            for gm in managers:
                gm.factory.spawn_station('command_station', 1, Vec3())
                t = gm.factory.spawn_ship('imperial_crew_transport', 1, Vec3(0,0,100))
                t.crew_cargo = 4
                t.crew_mission = dict(phase='load', owner=1, target=None, progress=0.)
                target = gm.factory.spawn_ship('imperial_frigate', 0, Vec3(100,0,100))
                target.crew -= 20
            # Authenticated player zero cannot order player one's ship.
            managers[0].state.queue_command(PlayerCommand(kind, 0, unit_ids=(t.id,),
                target_id=target.id if kind in ('board','crew_deliver') else None))
            run_ticks(self, sessions, managers, 7)
            self.assertEqual(managers[0].state.entity(t.id).crew_mission['phase'], 'load')
            self.assertEqual(managers[0].state.entity(target.id).crew, target.crew)
        for kind in ('board', 'crew_deliver'):
            sessions, managers = setup_pair(self)
            for gm in managers:
                gm.state.players[1].team = gm.state.players[0].team
                source = gm.factory.spawn_ship('imperial_cruiser' if kind == 'board' else 'imperial_crew_transport', 0, Vec3())
                if 'weapons' in source.systems:
                    source.systems['weapons'].hp = 0
                source.crew_cargo = 4
                target = gm.factory.spawn_ship('imperial_frigate', 1, Vec3(100,0,0))
                target.crew = 0
                target.shields = {key: 0. for key in target.shields}
                gm.visibility.update()
            managers[0].state.queue_command(PlayerCommand(kind, 0, unit_ids=(source.id,), target_id=target.id))
            run_ticks(self, sessions, managers, 7)
            self.assertIsNone(managers[0].state.entity(source.id).boarding_party_id)
            self.assertEqual(managers[0].state.entity(source.id).crew_cargo, 4)
            self.assertEqual(managers[0].state.entity(source.id).crew_mission, {})


class FontLifecycleTests(unittest.TestCase):
    def test_human_fixtures_preserve_shared_menu_fonts(self):
        from render import clean_classic
        pygame.font.init()
        cached = clean_classic.font(24)
        for case in (LocalRejectionTests('test_natural_stop_257_rejected_nonfatally_on_both_origins'),
                     GameplayAcceptanceTests('test_natural_crew_l_delivery_cancel_paid_once_and_replayed')):
            with self.subTest(fixture=case.id()):
                case.debug()  # Actual fixture, including its registered cleanups.
                self.assertTrue(pygame.font.get_init(), 'fixture quit shared menu fonts')
                self.assertIs(clean_classic.font(24), cached)
                self.assertGreater(cached.render('Menu after LAN', True, (255, 255, 255)).get_width(), 0)


class HumanSchemaTests(unittest.TestCase):
    def test_player_crew_and_boarding_schema(self):
        for kind in ('board', 'crew_load', 'crew_deliver', 'crew_cancel'):
            with self.subTest(kind=kind):
                data = PlayerCommand(kind, 1, unit_ids=(12,),
                    target_id=13 if kind in ('board', 'crew_deliver') else None).to_dict()
                self.assertEqual(_commands([data], 1), [data])
                with self.assertRaises(ValueError):
                    _commands([data], 0)
                for field in ('name', 'target_pos', 'ability_id'):
                    with self.assertRaises(ValueError):
                        _commands([dict(data, **{field: [0, 0, 0] if field == 'target_pos' else 'x'})], 1)
                without_units = dict(data, unit_ids=[])
                with self.assertRaises(ValueError):
                    _commands([without_units], 1)
                if kind in ('board', 'crew_deliver'):
                    del data['target_id']
                    with self.assertRaises(ValueError):
                        _commands([data], 1)
        with self.assertRaises(ValueError):
            _commands([PlayerCommand('crew_recover', 1, unit_ids=(12,), target_id=13).to_dict()], 1)
