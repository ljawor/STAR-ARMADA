"""#105: natural host/client controls, real TCP, paid birth and exact replay."""
import math
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import pygame

from game.core.vectors import Vec3
from game.net.lan import precise_checksum
from game.net.replay import MatchRecording, PlaybackSession
from game.systems.construction import buildable_ship_ids
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from test_lan_human_safety import setup_pair, run_ticks, init_fixture_fonts
from test_lan_main import factories


class CollectionLanAcceptance(unittest.TestCase):
    def test_both_origins_set_build_clear_paid_once_and_replay_every_tick(self):
        init_fixture_fonts(self)
        for origin in (0, 1):
            with self.subTest(origin=origin):
                sessions, managers = setup_pair(self)
                for manager in managers:
                    yard = manager.factory.spawn_station('shipyard', origin, Vec3(6000, 0, 6000))
                    player = manager.state.players[origin]
                    player.credits = player.materials = player.energy = player.crew = 100000
                yard_id = yard.id
                gm = managers[origin]
                yard = gm.state.entity(yard_id)
                hud = HUD(1280, 800, gm.state)
                ctrl = InputController(gm.state, Camera(1280, 800), hud, SimpleNamespace(flash=Mock()))
                ctrl.local_player = origin
                ctrl.selection = {yard_id}
                ns = factories()
                ns.update(pygame=pygame, state=gm.state, gm=gm, net_session=sessions[origin],
                          inputc=ctrl, flash=Mock())
                recording = MatchRecording(managers[0], mode='lan', local_player=origin)
                self.addCleanup(recording.close)
                initial_ids = set(gm.state.entities)
                hashes = []

                def click(pos, button=1):
                    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                        ns['handle_game_input'](pygame.event.Event(kind, button=button, pos=pos))
                    self.assertEqual(ns['mode'], 'game')
                    self.assertIs(ns['net_session'], sessions[origin])

                def advance(target):
                    while managers[0].state.tick < target:
                        run_ticks(self, sessions, managers, managers[0].state.tick + 1)
                        hashes.append(precise_checksum(managers[0]))

                with patch.object(ctrl.camera, 'screen_to_world', return_value=Vec3(7500, 0, 6500)):
                    click((600, 350), 3)
                self.assertIsNone(yard.collection_point)
                advance(7)
                self.assertEqual(yard.collection_point, Vec3(7500, 0, 6500))
                candidates = [sid for sid in buildable_ship_ids(gm.ds, 'shipyard', gm.state.players[origin].faction)
                              if gm.construction.station_can_build_ship(yard, sid)
                              and not gm.ds.ships[sid].is_squadron]
                ship_id = min(candidates, key=lambda sid: gm.ds.ships[sid].build_time)
                items = hud._shipyard_items(yard, gm.ds.stations['shipyard'])
                hud.scroll['ships'] = next(i for i, item in enumerate(items) if item.id == ship_id)
                hud._right_panel(ctrl.selection, origin)
                row = next(b for b in hud.buttons if b['kind'] == 'build_ship'
                           and b['payload']['ship_id'] == ship_id)
                click(row['rect'].center)
                advance(14)
                self.assertEqual(len(yard.build_queue), 1)
                advance(30 + math.ceil(gm.ds.ships[ship_id].build_time * 30))
                born = [gm.state.entities[i] for i in set(gm.state.entities) - initial_ids]
                self.assertEqual(len(born), 1)
                ship = born[0]
                self.assertEqual(ship.data_id, ship_id)
                self.assertEqual(ship.order_type, 'move')
                self.assertEqual(ship.order_target_pos, Vec3(7500, 0, 6500))
                hud.buttons.clear()
                hud.blocked_rects.clear()
                hud.scroll_rects.clear()
                hud._right_panel(ctrl.selection, origin)
                clear = next(b for b in hud.buttons if b['kind'] == 'collection_clear')
                click(clear['rect'].center)
                advance(gm.state.tick + 7)
                self.assertIsNone(yard.collection_point)
                self.assertEqual(ship.order_target_pos, Vec3(7500, 0, 6500))
                data = recording.to_dict()
                self.assertEqual([entry['cmd']['type'] for entry in data['commands']],
                                 ['collection_point', 'build_ship', 'collection_point'])
                self.assertEqual(data['commands'][0]['tick'], 3)
                self.assertEqual(sum(entry['cmd']['type'] == 'build_ship' for entry in data['commands']), 1)
                playback = PlaybackSession(data)
                for expected in hashes:
                    self.assertTrue(playback.step())
                    self.assertEqual(precise_checksum(playback.gm), expected)
                self.assertTrue(playback.ended)
                recording.close()
                for session in sessions:
                    session.close()
