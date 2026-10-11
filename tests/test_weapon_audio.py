"""Issue #44: assert real SDL postmix output, not merely a busy channel."""
import os
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from unittest.mock import Mock, patch
import unittest
import numpy as np
import pygame

from tools.diag_weapon_audio import MixerCapture, combat_fixture


class TestMixerCapture(unittest.TestCase):
    def tearDown(self):
        pygame.mixer.quit()

    def test_capture_rejects_non_s16_stereo_mixer(self):
        pygame.mixer.quit()
        pygame.mixer.init(frequency=44100, size=-8, channels=1, allowedchanges=0)
        with self.assertRaisesRegex(RuntimeError, 'signed 16-bit stereo'):
            MixerCapture()

    def test_capture_waits_for_callback_frames(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, allowedchanges=0)
        with MixerCapture() as capture:
            self.assertTrue(callable(getattr(capture, 'wait_frames', None)),
                            'capture needs bounded callback readiness, not blind sleeps')
            capture.wait_frames(1024)
        self.assertGreaterEqual(len(capture.pcm()), 1024)


class TestProductionWeaponAudio(unittest.TestCase):
    def test_quiet_staging_preserves_source_bank_and_reuses_cached_sound(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            original = audio.sounds['laser']
            original_pcm = pygame.sndarray.array(original)
            for _ in range(25):
                audio.play('laser', .3, shooter.pos)
            self.assertEqual(len(audio._quiet_sounds), 1)
            self.assertEqual(original.get_volume(), 1.)
            np.testing.assert_array_equal(pygame.sndarray.array(original), original_pcm)
            self.assertTrue(all(voice[3] is audio._quiet_sounds[original]
                                for voice in audio._active_voices.values()))
            self.assertFalse(any(pygame.mixer.Channel(i).get_busy() for i in (0, 1, 2)))
        finally:
            audio.cleanup()

    def test_night_bank_quiet_playback_stays_within_intended_peak_budget(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            audio.apply_settings({'audio_dynamic_range': 'night', 'audio_mono': True})
            with MixerCapture() as capture:
                audio.play('laser', .3, shooter.pos)
                capture.wait_frames(int(audio.rate * .18))
            pcm = capture.pcm()
            self.assertGreater(np.count_nonzero(pcm), 0)
            np.testing.assert_array_equal(pcm[:, 0], pcm[:, 1])
            source_peak = np.max(np.abs(pygame.sndarray.array(audio.night_sounds['laser']).astype(np.int32)))
            gain = max(audio.mix_gains('laser', .3, shooter.pos))
            self.assertLessEqual(int(np.max(np.abs(pcm.astype(np.int32)))),
                                 int(np.ceil(source_peak * gain)) + 1)
        finally:
            audio.cleanup()

    def test_live_settings_keep_quiet_voice_gain_stage_without_restart(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            audio.play('big_explosion', .3, shooter.pos)
            channel = pygame.mixer.Channel(3)
            sound = channel.get_sound()
            with MixerCapture() as progress:
                progress.wait_frames(int(audio.rate * .03))
            with MixerCapture() as capture:
                audio.apply_settings({'sfx_volume': .7, 'audio_mono': True})
                capture.wait_frames(int(audio.rate * .12))
            self.assertIs(channel.get_sound(), sound, 'settings must not restart a transient')
            self.assertGreater(np.count_nonzero(capture.pcm()), 0,
                               'live settings rounded the staged quiet voice back to silence')
        finally:
            audio.cleanup()

    def test_live_volume_reduction_keeps_initially_louder_transient_audible(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            # Previously unstaged at .8 SFX, then both stereo bytes became zero.
            audio._spatial = lambda pos: (1., .8)
            audio.play('big_explosion', .3, shooter.pos)
            channel = pygame.mixer.Channel(3)
            sound = channel.get_sound()
            self.assertGreater(min(audio.mix_gains('big_explosion', .3, shooter.pos)), 1 / 255)
            with MixerCapture() as progress:
                progress.wait_frames(int(audio.rate * .03))
            with MixerCapture() as capture:
                tracked_channel = Mock(wraps=channel)
                with patch('pygame.mixer.Channel', return_value=tracked_channel):
                    audio.apply_settings({'sfx_volume': .1})
                tracked_channel.play.assert_not_called()
                tracked_channel.stop.assert_not_called()
                capture.wait_frames(int(audio.rate * .12))
            self.assertIs(channel.get_sound(), sound, 'settings must retain playing PCM')
            self.assertTrue(channel.get_busy())
            gains = audio.mix_gains('big_explosion', .3, shooter.pos)
            np.testing.assert_allclose(gains, (.001176, .0021))
            pcm = capture.pcm()
            for side in (0, 1):
                self.assertGreater(np.count_nonzero(pcm[:, side]), 0,
                                   'volume reduction silenced a still-playing transient')
        finally:
            audio.cleanup()

    def test_cleanup_releases_bounded_detached_pcm_cache(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            for profile in ('standard', 'night'):
                audio.apply_settings({'audio_dynamic_range': profile})
                for name in audio.sounds:
                    audio.play(name, 1.)
            self.assertGreater(len(audio._quiet_sounds), 0)
            self.assertLessEqual(len(audio._quiet_sounds), 2 * len(audio.sounds))
        finally:
            audio.cleanup()
        self.assertFalse(audio._quiet_sounds, 'cleanup retains detached PCM buffers')
        self.assertFalse(audio._active_voices, 'cleanup retains playing-sound references')

    def test_stereo_boundary_gains_preserve_each_side_and_peak_budget(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        try:
            audio.apply_settings({'sfx_volume': 1.})
            for left, right in ((.0038, .00405), (.00405, .0038), (.0038, .0039)):
                with self.subTest(gains=(left, right)):
                    pygame.mixer.stop()
                    pan = (1. - min(left, right) / max(left, right)) / .55
                    audio._spatial = lambda pos: (max(left, right) / .07,
                                                 pan if right > left else -pan)
                    np.testing.assert_allclose(audio.mix_gains('laser', 1.), (left, right))
                    with MixerCapture() as capture:
                        audio.play('laser', 1.)
                        capture.wait_frames(int(audio.rate * .15))
                    pcm = capture.pcm().astype(np.int32)
                    source_peak = int(np.max(np.abs(pygame.sndarray.array(audio.sounds['laser']).astype(np.int32))))
                    for side, gain in enumerate((left, right)):
                        self.assertGreater(np.count_nonzero(pcm[:, side]), 0)
                        self.assertLessEqual(int(np.max(np.abs(pcm[:, side]))),
                                             int(np.ceil(source_peak * gain)) + 1)
        finally:
            audio.cleanup()

    def test_all_battle_voices_stage_safely_at_maximum_gain(self):
        gm, shooter, target, audio = combat_fixture('imperial_corvette')
        reserved = {'warning': 1, 'alert': 1, 'mission_complete': 2, 'mission_failed': 2}
        try:
            audio.set_camera(None)
            audio.apply_settings({'sfx_volume': 1.})
            for name, source in audio.sounds.items():
                pygame.mixer.stop()
                audio.play(name, 1.)
                slot = reserved.get(name, 3)
                playing = pygame.mixer.Channel(slot).get_sound()
                if name in reserved:
                    self.assertIs(playing, source)
                else:
                    self.assertAlmostEqual(max(audio.mix_gains(name, 1.)), .07)
                    self.assertEqual(playing.get_volume(), .125)
                    self.assertLess(max(audio.mix_gains(name, 1.)) / playing.get_volume(), 1.)
                    self.assertEqual(source.get_volume(), 1.)
                    self.assertEqual(playing.get_raw(), source.get_raw())
        finally:
            audio.cleanup()

    def test_ship_and_fighter_shots_remain_nonzero_at_tactical_zoom(self):
        for ship_id in ('imperial_tie_squadron', 'imperial_corvette'):
            with self.subTest(ship=ship_id):
                gm, shooter, target, audio = combat_fixture(ship_id)
                events = []
                gm.state.events.subscribe('weapon_fired', lambda ev: events.append(ev.data))
                try:
                    with MixerCapture() as capture:
                        gm.step(1 / 30)
                        capture.wait_frames(int(audio.rate * .18))
                    self.assertTrue(any(ev['attacker_id'] == shooter.id for ev in events))
                    self.assertTrue(audio._active_voices, 'event must reach playback allocation')
                    name, volume, point, sound = next(iter(audio._active_voices.values()))
                    gains = audio.mix_gains(name, volume, point)
                    self.assertGreater(max(gains), .0005, 'not deliberately distance-culled')
                    self.assertLess(max(gains), 1 / 255, 'fixture must expose SDL panning rounding')
                    pcm = capture.pcm()
                    self.assertGreater(len(pcm), 0, 'SDL callback must actually execute')
                    self.assertGreater(np.count_nonzero(pcm), 0,
                                       'firing reached a busy channel but SDL output was silent')
                    source_peak = int(np.max(np.abs(pygame.sndarray.array(sound).astype(np.int32))))
                    self.assertLessEqual(int(np.max(np.abs(pcm.astype(np.int32)))),
                                         int(np.ceil(source_peak * max(gains))) + 1,
                                         'gain staging must not boost the intended mix budget')
                finally:
                    audio.cleanup()


if __name__ == '__main__':
    unittest.main()
