"""Phase 10 production mixer probes; dummy is explicit, never device proof."""
import os
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
import pygame
import numpy as np
from test_audio import _State, _Ev
from render.audio import Audio


class TestAudioMix(unittest.TestCase):
    def setUp(self):
        self.state = _State()
        self.audio = Audio(self.state)
        self.assertTrue(self.audio.available)

    def tearDown(self):
        self.audio.cleanup()

    def test_live_entity_vec3_positions_use_camera_attenuation_and_pan(self):
        from game.core.vectors import Vec3
        from render.camera import Camera
        a = self.audio
        a.set_camera(Camera(960, 640))
        for coordinates in ((2000., 0., 0.), (-2000., 0., 0.), (99999., 0., 0.)):
            with self.subTest(coordinates=coordinates):
                self.assertEqual(a._spatial(Vec3(*coordinates)), a._spatial(coordinates))
        self.assertEqual(a._spatial(Vec3(99999., 0., 0.)), (0., 0.))

    def test_live_nonzero_volume_and_mono_refresh_active_voice_gains(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        a = self.audio
        a._spatial = lambda pos: (1., .8)
        a.play('big_explosion', 1., [1, 0, 0])
        actual = pygame.mixer.Channel
        changed = {}
        def channel(index):
            real = actual(index)
            def set_volume(*values):
                changed[index] = values
                real.set_volume(*values)
            return SimpleNamespace(get_busy=real.get_busy, get_sound=real.get_sound,
                                   stop=real.stop, set_volume=set_volume)
        with patch('render.audio.pygame.mixer.Channel', side_effect=channel):
            a.apply_settings({'sfx_volume': .25, 'audio_mono': True})
        self.assertIn(3, changed, 'a live nonzero edit left old gains playing')
        self.assertEqual(changed[3], a.mix_gains('big_explosion', 1., [1, 0, 0]))
        self.assertIs(actual(3).get_sound(), a.sounds['big_explosion'])

    def test_live_dynamic_range_change_discards_old_transients(self):
        a = self.audio
        a.start_ambient()
        ambient = a.ambient_channel.get_sound()
        a.play('big_explosion', 1.)
        a.apply_settings({'audio_dynamic_range': 'night'})
        self.assertFalse(pygame.mixer.Channel(3).get_busy())
        self.assertIs(a.ambient_channel.get_sound(), ambient)
        a.play('big_explosion', 1.)
        self.assertIs(pygame.mixer.Channel(3).get_sound(), a.night_sounds['big_explosion'])

    def test_build_completion_cannot_suppress_own_research_completion(self):
        a = self.audio
        seen = []
        a.play = lambda name, volume=.5, pos=None: seen.append(name)
        a._ev_build(_Ev(entity_id=1, ship='imperial_corvette', owner=0))
        a._ev_research(_Ev(player=0, tech='a_real_tech'))
        self.assertEqual(seen, ['build', 'research'])

    def test_ambient_loop_has_click_free_start_tail_and_seam(self):
        a = self.audio
        a.start_ambient()
        pcm = pygame.sndarray.array(a.ambient_channel.get_sound()).astype(float) / 32768.
        self.assertLessEqual(float(np.max(np.abs(pcm))), .16)
        self.assertEqual(float(np.max(np.abs(pcm[0]))), 0.)
        self.assertEqual(float(np.max(np.abs(pcm[-1]))), 0.)
        self.assertLess(float(np.max(np.abs(np.diff(pcm, axis=0)))), .01)

    def test_own_economic_notifications_are_not_camera_attenuated(self):
        from types import SimpleNamespace
        from game.core.vectors import Vec3
        a = self.audio
        self.state.entities[1] = SimpleNamespace(owner=0, pos=Vec3(99999, 0, 0))
        a._spatial = lambda pos: (0., 0.) if pos is not None else (1., 0.)
        a._ev_convoy(_Ev(entity_id=1, owner=0, convoy_owner=0, dest=2, cargo=150.))
        self.assertTrue(pygame.mixer.Channel(3).get_busy())
        a._ev_raid(_Ev(entity_id=1, looter=1, convoy_owner=0, loot=75., cargo=150.))
        self.assertTrue(pygame.mixer.Channel(4).get_busy())

    def test_unusable_world_position_does_not_crash_playback(self):
        a = self.audio
        a.play('big_explosion', 1., object())
        a.apply_settings({'sfx_volume': .5})
        self.assertTrue(pygame.mixer.Channel(3).get_busy())

    def test_live_zero_sfx_stops_existing_effects_but_keeps_ambient(self):
        a = self.audio
        a.start_ambient()
        a.play('big_explosion', 1.)
        a.play('warning', 1.)
        self.assertTrue(pygame.mixer.Channel(1).get_busy())
        a.apply_settings({'sfx_volume': 0., 'music_volume': .5})
        self.assertFalse(any(pygame.mixer.Channel(i).get_busy() for i in range(1, 32)))
        self.assertTrue(pygame.mixer.Channel(0).get_busy())
        a.play('mission_complete', 1.)
        self.assertFalse(pygame.mixer.Channel(2).get_busy())

    def test_private_alerts_are_own_only_and_hidden_combat_cannot_throttle_visible(self):
        from types import SimpleNamespace
        a, st = self.audio, self.state
        st.entities = {1: SimpleNamespace(owner=0, pos=[99999, 0, 0]),
                       2: SimpleNamespace(owner=1, pos=[0, 0, 0]),
                       3: SimpleNamespace(owner=1, pos=[0, 0, 0])}
        st.can_see = lambda viewer, eid: eid != 2
        st.is_position_visible = lambda viewer, pos: False
        seen = []
        a.play = lambda name, volume=.5, pos=None: seen.append((name, pos))
        a._ev_critical(_Ev(entity_id=2, owner=1))
        a._ev_critical(_Ev(entity_id=3, owner=1))
        a._ev_critical(_Ev(entity_id=1, owner=0))
        self.assertEqual(seen, [('warning', None)], 'own alerts must bypass off-screen attenuation')
        seen.clear()
        a._ev_fire(_Ev(attacker_id=2, owner=1, weapon='turbolaser'))
        a._ev_fire(_Ev(attacker_id=3, owner=1, weapon='turbolaser'))
        self.assertEqual([n for n, _ in seen], ['turbolaser'])
        seen.clear()
        for handler, payload in [(a._ev_build, dict(entity_id=3, owner=1)),
                                 (a._ev_station, dict(entity_id=3, owner=1)),
                                 (a._ev_research, dict(player=1)),
                                 (a._ev_level, dict(entity_id=3)),
                                 (a._ev_convoy, dict(owner=1, convoy_owner=1)),
                                 (a._ev_raid, dict(convoy_owner=1, looter=2))]:
            handler(_Ev(**payload))
        self.assertEqual(seen, [])
        for handler, payload in [(a._ev_hit, dict(target_id=2, target_owner=1)),
                                 (a._ev_explosion, dict(entity_id=2, owner=1, pos=[0, 0, 0])),
                                 (a._ev_jump, dict(entity_id=2, owner=1)),
                                 (a._ev_ability, dict(entity_id=2))]:
            handler(_Ev(**payload))
        self.assertEqual(seen, [])
        self.assertEqual(st.time, 0.)
        self.assertEqual(st.entities[2].owner, 1)

    def test_alerts_and_ambient_survive_saturated_fire_pool_with_headroom(self):
        a = self.audio
        a.apply_settings({'sfx_volume': 1., 'music_volume': 1.})
        a.start_ambient()
        ambient = a.ambient_channel.get_sound()
        a.play('warning', 1.)
        a.play('mission_complete', 1.)
        for _ in range(100):
            a.play('big_explosion', 1.)
        self.assertIs(pygame.mixer.Channel(0).get_sound(), ambient)
        self.assertIs(pygame.mixer.Channel(1).get_sound(), a.sounds['warning'])
        self.assertIs(pygame.mixer.Channel(2).get_sound(), a.sounds['mission_complete'])
        self.assertEqual(sum(pygame.mixer.Channel(i).get_busy() for i in range(3, 32)), 8)
        bound = 0.
        for i in range(11):
            sound = pygame.mixer.Channel(i).get_sound()
            peak = np.max(np.abs(pygame.sndarray.array(sound).astype(float))) / 32768
            gain = .5 if i == 0 else max(a.mix_gains(
                'warning' if i == 1 else 'mission_complete' if i == 2 else 'big_explosion', 1.))
            bound += peak * gain
        self.assertLess(bound, .9, 'even coherent full-volume voices need headroom')
        a.toggle_mute()
        a.toggle_mute()
        ambient = a.ambient_channel.get_sound()
        for _ in range(100):
            a.play('laser', 1.)
        self.assertIs(pygame.mixer.Channel(0).get_sound(), ambient)

    def test_night_and_mono_change_actual_playback(self):
        a = self.audio
        a._spatial = lambda pos: (1., .8)
        a.play('big_explosion', 1.)
        standard = next(pygame.mixer.Channel(i) for i in range(32)
                        if pygame.mixer.Channel(i).get_busy())
        original = pygame.sndarray.array(standard.get_sound()).astype(float) / 32768
        pygame.mixer.stop()
        a.apply_settings({'audio_dynamic_range': 'night', 'audio_mono': True})
        a.play('big_explosion', 1.)
        night = next(pygame.mixer.Channel(i) for i in range(32)
                     if pygame.mixer.Channel(i).get_busy())
        pcm = pygame.sndarray.array(night.get_sound()).astype(float) / 32768
        self.assertLess(np.max(np.abs(pcm)), np.max(np.abs(original)) * .8)
        self.assertLess(np.max(np.abs(pcm)) / np.sqrt(np.mean(pcm ** 2)),
                        np.max(np.abs(original)) / np.sqrt(np.mean(original ** 2)))
        # Shared production gain function, used by the channel and WAV diagnostic.
        left, right = a.mix_gains('big_explosion', 1., [1, 0, 0])
        self.assertEqual(left, right)
        self.assertGreater(left, 0.)
        a.apply_settings({'audio_mono': False})
        left, right = a.mix_gains('big_explosion', 1., [1, 0, 0])
        self.assertLess(left, right)

    def test_settings_are_sane_and_muted_music_stays_zero(self):
        a = self.audio
        for value, expected in [(float('nan'), .8), (float('inf'), .8),
                                (-4, 0.), (9, 1.), ('bad', .8)]:
            a.apply_settings({'sfx_volume': value, 'music_volume': 0,
                              'audio_dynamic_range': 'invalid', 'audio_mono': 'false'})
            self.assertEqual(a.settings['sfx_volume'], expected)
            self.assertEqual(a.settings['audio_dynamic_range'], 'standard')
            self.assertIs(a.settings['audio_mono'], False)
        a.start_ambient()
        self.assertEqual(a.ambient_channel.get_volume(), 0.)
        a.toggle_mute()
        a.apply_settings({'music_volume': 1})
        self.assertEqual(pygame.mixer.get_num_channels(), 32)
        a.toggle_mute()
        a.apply_settings({'music_volume': 0})
        self.assertEqual(a.ambient_channel.get_volume(), 0.)


class TestAudioProducerAudit(unittest.TestCase):
    """Controlled fixtures exercise unchanged producers, not natural playthroughs."""
    def setUp(self):
        import copy
        from helpers import make_game
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.observed = []
        self.played = []
        subscribe = self.st.events.subscribe
        from game.core.runtime_snapshot import _names
        def snapshot():
            # The save codec rejects transient WeaponData in mid-tick damage
            # queues; compare full-precision raw state instead (no codec loss).
            values = {name: getattr(self.st, name) for name in _names()}
            values.update(effects=self.st.effects, floating_texts=self.st.floating_texts,
                          timers=(self.gm.trading._timer, self.gm.squadrons._tactical_timer,
                                  self.gm.victory._timer))
            return copy.deepcopy(values)
        def audited_subscribe(name, callback):
            def audit(event):
                before = snapshot()
                callback(event)
                self.assertEqual(before, snapshot(), 'audio mutated sim during ' + name)
                self.observed.append((name, copy.deepcopy(event.data)))
            subscribe(name, audit)
        from unittest.mock import patch
        with patch.object(self.st.events, 'subscribe', side_effect=audited_subscribe):
            self.audio = Audio(self.st, local_player=1)
        self.assertTrue(self.audio.available)
        production_play = self.audio.play
        def recorded_play(name, volume=.5, pos=None):
            self.played.append(name)
            production_play(name, volume, pos)
        self.audio.play = recorded_play

    def tearDown(self):
        self.audio.cleanup()

    def test_real_construction_research_arrival_and_raid_payloads(self):
        from game.core.vectors import Vec3
        gm, st, a = self.gm, self.st, self.audio
        for owner in (0, 1):
            self.played.clear()
            a._last.clear()
            builder = next(e for e in st.entities.values() if e.owner == owner and e.is_station)
            gm.construction._complete(builder, {'kind': 'ship', 'item': 'imperial_corvette'})
            self.assertEqual(self.played, ['build'] if owner == 1 else [])
            a._last.clear()
            self.played.clear()
            gm.construction._complete(builder, {'kind': 'station', 'item': 'research_station',
                                               'pos': [-5000 + owner * 10000, 0, -7000]})
            self.assertEqual(self.played, ['build'] if owner == 1 else [])
            station = next(e for e in reversed(list(st.entities.values()))
                           if e.owner == owner and e.data_id == 'research_station')
            tech = gm.research.available_techs(owner)[0]
            self.assertTrue(gm.research.start_research(owner, station.id, tech))
            st.players[owner].researching[tech]['time_left'] = 0.
            self.played.clear()
            gm.research.update(1 / 30)
            self.assertEqual(self.played, ['research'] if owner == 1 else [])
            src = gm.factory.spawn_station('trade_station', owner, Vec3(-5000 + owner * 10000, 0, 7000))
            dest = gm.factory.spawn_station('trade_station', owner, src.pos + Vec3(1000, 0, 0))
            convoy = gm.trading._make_convoy(src, dest, 150., 250.)
            convoy.pos.set(dest.pos)
            self.played.clear()
            a._last.clear()
            gm.trading.update(0.)
            self.assertEqual(self.played, ['convoy'] if owner == 1 else [])
            # Actual nested TradingSystem raid event carries looter + convoy_owner,
            # not owner or player. Player 1 must hear both raider and victim roles.
            convoy = gm.trading._make_convoy(src, dest, 150., 250.)
            self.played.clear()
            a._last.clear()
            gm.damage._kill(convoy, None, 1 - owner)
            self.assertIn('raid', self.played)
        names = {name for name, _ in self.observed}
        self.assertTrue({'ship_built', 'station_built', 'research_complete',
                         'convoy_arrived', 'convoy_raided', 'unit_destroyed'} <= names)

    def test_real_critical_level_ability_jump_and_allied_victory(self):
        from game.core.vectors import Vec3
        gm, st, a = self.gm, self.st, self.audio
        own = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 0))
        own.hull = own.max_hull * .05
        gm.damage._hull_threshold_effects(own)
        self.assertIn('warning', self.played)
        own.xp = 1e6
        gm.damage._update_level(own)
        self.assertIn('ui', self.played)
        own.hull = own.max_hull
        own.energy = own.max_energy
        self.assertTrue(gm.abilities.activate(own, 'emergency_shield_recharge'))
        self.assertIn('ability', self.played)
        own.jump_charge = .00001
        own.jump_target = Vec3(1000, 0, 1000)
        gm.step(1 / 30)
        self.assertIn('jump', self.played)
        self.assertTrue({'unit_critical', 'unit_leveled', 'ability_used', 'jump_complete'}
                        <= {name for name, _ in self.observed})
        st.players[0].team = st.players[1].team
        self.played.clear()
        a._last.clear()
        st.events.publish('game_over', winner=0)
        self.assertEqual(self.played, ['mission_complete'])

    def test_real_hidden_then_detected_combat_and_dead_position_boundary(self):
        from game.core.events import GameEvent
        from game.core.vectors import Vec3
        gm, st, a = self.gm, self.st, self.audio
        hidden = gm.factory.spawn_ship('imperial_corvette', 0, Vec3(-8000, 0, 8000))
        self.assertFalse(st.can_see(1, hidden.id))
        # Playback of captured production-shaped events cannot disclose hidden fire.
        st.events.publish('weapon_fired', attacker_id=hidden.id, owner=0,
                          weapon='turbolaser', heavy=True)
        self.assertEqual(self.played, [])
        observer = gm.factory.spawn_ship('imperial_frigate', 1, Vec3(-8000, 0, 8200))
        self.assertTrue(st.can_see(1, hidden.id))
        st.events.publish('weapon_fired', attacker_id=hidden.id, owner=0,
                          weapon='turbolaser', heavy=True)
        self.assertEqual(self.played, ['turbolaser'])
        # Real manager ticks invoke actual weapon/projectile publishers.
        self.played.clear()
        for _ in range(180):
            gm.step(1 / 30)
        self.assertTrue(any(name.startswith('impact') for name in self.played))
        self.assertTrue({'weapon_fired', 'projectile_hit'} <= {name for name, _ in self.observed})
        # A foreign environmental death has no local killer knowledge: CURRENT
        # sensors, rather than explored history or stale alive=False metadata.
        visible = gm.factory.spawn_ship('imperial_corvette', 0, observer.pos + Vec3(200, 0, 0))
        pos = visible.pos.to_dict()
        self.played.clear()
        a._last.clear()
        gm.damage._kill(visible, None, -1)
        self.assertIn('explosion', self.played)
        event = GameEvent('unit_destroyed', {'entity_id': visible.id, 'owner': 0,
                            'killer_owner': -1, 'pos': pos, 'data_id': visible.data_id})
        for entity in st.entities.values():
            if entity.owner == 1:
                entity.pos.set(Vec3(11000, 0, -11000))
        self.assertFalse(st.is_position_visible(1, Vec3.from_dict(pos)))
        self.played.clear()
        a._last.clear()
        a._ev_explosion(event)
        self.assertEqual(self.played, [])


class TestAudioMixDiagnostic(unittest.TestCase):
    def test_offline_exports_measured_comparison_wavs(self):
        import json
        import subprocess
        import sys
        import tempfile
        import wave
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        diag = root / 'tools/diag_audio_mix.py'
        self.assertTrue(diag.exists(), 'offline mix diagnostic is not implemented')
        scratch = Path.home() / '.hermes/cache/scratch'
        with tempfile.TemporaryDirectory(prefix='audio-mix-test-', dir=scratch) as out:
            result = subprocess.run([sys.executable, str(diag), '--out', out],
                                    cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(out) / 'audio_mix_metrics.json').read_text())
            self.assertFalse(report['device_playback_verified'])
            self.assertTrue(report['live_control_probe_passed'])
            self.assertEqual(report['ambient_envelope']['loop_seam_delta'], 0.)
            self.assertLess(report['ambient_envelope']['max_sample_step'], .01)
            self.assertLess(report['coherent_peak_bound'], .9)
            self.assertEqual(set(report['wav_metrics']), {'standard_stereo', 'night_stereo',
                             'night_mono', 'explosion_standard', 'explosion_night'})
            for name, metric in report['wav_metrics'].items():
                self.assertLess(metric['peak'], .9)
                self.assertEqual(metric['clipped_samples'], 0)
                with wave.open(str(Path(out) / (name + '.wav'))) as wav:
                    self.assertEqual(wav.getnchannels(), 2)
                    self.assertEqual(wav.getframerate(), report['rate'])
                    self.assertGreater(wav.getnframes(), 1000)
            self.assertEqual(report['wav_metrics']['night_mono']['max_left_right_delta'], 0.)
            self.assertLess(report['wav_metrics']['explosion_night']['crest_db'],
                            report['wav_metrics']['explosion_standard']['crest_db'])


if __name__ == '__main__':
    unittest.main()
