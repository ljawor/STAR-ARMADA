"""Export bounded production-voice WAV comparisons, optionally play on device.

PYTHONPATH=. .venv/bin/python tools/diag_audio_mix.py --out <scratch-directory>
Add --device to open the native device and play standard/night/mono comparisons.
Offline float sums are NOT SDL output capture; device playback is NOT human
listening acceptance. No simulation runs or changes in this diagnostic.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--device', action='store_true')
    args = parser.parse_args()
    scratch = (Path.home() / '.hermes/cache/scratch').resolve()
    out = args.out.expanduser().resolve()
    if not out.is_relative_to(scratch):
        parser.error('--out must be within Hermes scratch')
    out.mkdir(parents=True, exist_ok=True)
    if args.device:
        # Require native playback; never silently downgrade this gate to dummy.
        os.environ['SDL_AUDIODRIVER'] = 'coreaudio' if sys.platform == 'darwin' else (
            'directsound' if sys.platform == 'win32' else 'alsa')
    else:
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np
    import pygame
    from render.audio import Audio

    state = SimpleNamespace(time=0., entities={}, events=SimpleNamespace(
        subscribe=lambda *_: None))
    audio = Audio(state, settings={'sfx_volume': 1., 'music_volume': 1.})
    report = {'device_requested': args.device, 'device_playback_verified': False,
              'human_listening_accepted': False,
              'driver_requested': os.environ['SDL_AUDIODRIVER'],
              'offline_method': 'float sum of production PCM and mix_gains; eight bounded '
                                'battle slots, isolated warning/mission slots, ambient loop; '
                                'not SDL output capture'}
    if not audio.available:
        report['error'] = 'native mixer unavailable' if args.device else 'dummy mixer unavailable'
        (out / 'audio_mix_metrics.json').write_text(json.dumps(report, indent=2))
        print('AUDIO_MIX_FAIL', report['error'])
        return 1
    try:
        rate = audio.rate
        report['rate'] = rate
        report['mixer_init'] = pygame.mixer.get_init()
        audio.start_ambient()
        ambient = pygame.sndarray.array(audio.ambient_channel.get_sound()).astype(float) / 32768.
        report['ambient_envelope'] = {
            'peak': float(np.max(np.abs(ambient))),
            'loop_seam_delta': float(np.max(np.abs(ambient[0] - ambient[-1]))),
            'max_sample_step': float(np.max(np.abs(np.diff(ambient, axis=0))))}
        assert report['ambient_envelope']['loop_seam_delta'] == 0.
        assert report['ambient_envelope']['max_sample_step'] < .01
        audio.play('big_explosion', 1.)
        assert pygame.mixer.Channel(3).get_busy()
        audio.apply_settings({'sfx_volume': 0., 'music_volume': .5})
        assert not any(pygame.mixer.Channel(i).get_busy() for i in range(1, 11))
        assert audio.ambient_channel.get_busy()
        assert abs(audio.ambient_channel.get_volume() - .25) < .01
        audio.apply_settings({'sfx_volume': 1., 'music_volume': 0.})
        assert audio.ambient_channel.get_volume() == 0.
        audio.play('warning', 1.)
        audio.toggle_mute()
        audio.apply_settings({'sfx_volume': 1., 'music_volume': 1.})
        assert not any(pygame.mixer.Channel(i).get_busy() for i in range(11))
        assert audio.ambient_channel.get_volume() == 0.
        audio.toggle_mute()
        assert audio.ambient_channel.get_busy()
        assert abs(audio.ambient_channel.get_volume() - .5) < .01
        audio.apply_settings({'audio_dynamic_range': 'night', 'audio_mono': True})
        audio.play('big_explosion', 1.)
        playing = pygame.mixer.Channel(3).get_sound()
        assert playing is audio._quiet_sounds[audio.night_sounds['big_explosion']]
        np.testing.assert_array_equal(pygame.sndarray.array(playing),
                                      pygame.sndarray.array(audio.night_sounds['big_explosion']))
        assert audio.mix_gains('big_explosion', 1.)[0] == audio.mix_gains('big_explosion', 1.)[1]
        report['live_control_probe_passed'] = True
        pygame.mixer.stop()
        peak = max(float(np.max(np.abs(pygame.sndarray.array(sound).astype(float)))) / 32768.
                   for sound in audio.sounds.values())
        report['coherent_peak_bound'] = peak * (8 * .07 + .18 + .22) + .5 * float(np.max(np.abs(ambient)))
        assert report['coherent_peak_bound'] < .9

        def render(profile, mono):
            audio.apply_settings({'sfx_volume': 1., 'music_volume': 1.,
                                  'audio_dynamic_range': profile, 'audio_mono': mono})
            n = rate * 5
            tracks = np.zeros((11, n, 2), dtype=np.float64)
            tracks[0] = np.tile(ambient, (math.ceil(n / len(ambient)), 1))[:n] * .5
            ends = [0] * 11
            cursor = 0
            events = [(0., 'big_explosion', 1., 0.) for _ in range(8)]
            events += [(0., 'warning', 1., 0.), (0., 'mission_complete', 1., 0.)]
            events += [(float(t), 'laser_heavy', .42, math.sin(t * 2.))
                       for t in np.arange(.4, 3.8, .09)]
            events += [(1.8, 'big_explosion', .85, -.8),
                       (2.2, 'warning', .5, 0.), (3.5, 'mission_failed', .8, 0.)]
            for when, name, volume, pan in sorted(events, key=lambda e: e[0]):
                begin = int(when * rate)
                if name.startswith('mission_'):
                    slot = 2
                elif name in ('warning', 'alert'):
                    slot = 1
                else:
                    free = [i for i in range(3, 11) if ends[i] <= begin]
                    if free:
                        slot = free[0]
                    else:
                        slot = 3 + cursor
                        cursor = (cursor + 1) % 8
                audio._spatial = lambda pos, pan=pan: (1., pan)
                gains = audio.mix_gains(name, volume)
                bank = audio.night_sounds if profile == 'night' else audio.sounds
                pcm = pygame.sndarray.array(bank[name]).astype(float) / 32768.
                end = min(n, begin + len(pcm))
                tracks[slot, begin:] = 0.  # replacement truncates only that slot
                tracks[slot, begin:end] = pcm[:end - begin] * np.asarray(gains)
                ends[slot] = end
            return tracks.sum(axis=0)

        wavs = {'standard_stereo': render('standard', False),
                'night_stereo': render('night', False),
                'night_mono': render('night', True),
                'explosion_standard': pygame.sndarray.array(audio.sounds['big_explosion']).astype(float) / 32768.,
                'explosion_night': pygame.sndarray.array(audio.night_sounds['big_explosion']).astype(float) / 32768.}
        metrics = {}
        for name, pcm in wavs.items():
            peak = float(np.max(np.abs(pcm)))
            rms = float(np.sqrt(np.mean(pcm ** 2)))
            metrics[name] = {'peak': peak, 'rms': rms,
                             'headroom_db': -20. * math.log10(max(peak, 1e-12)),
                             'crest_db': 20. * math.log10(max(peak, 1e-12) / max(rms, 1e-12)),
                             'clipped_samples': int(np.sum(np.abs(pcm) >= 1.)),
                             'max_left_right_delta': float(np.max(np.abs(pcm[:, 0] - pcm[:, 1])))}
            assert peak < .9 and metrics[name]['clipped_samples'] == 0
            with wave.open(str(out / (name + '.wav')), 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes(np.ascontiguousarray(pcm * 32767, dtype='<i2').tobytes())
        assert metrics['night_mono']['max_left_right_delta'] == 0.
        assert metrics['explosion_night']['crest_db'] < metrics['explosion_standard']['crest_db']
        report['wav_metrics'] = metrics
        if args.device:
            from pygame._sdl2.audio import get_audio_device_names
            report['output_devices'] = list(get_audio_device_names(False))
            # Exercise actual allocator/priority protection on the native mixer.
            audio.ambient_channel = None  # the offline setup stopped its loop
            audio.start_ambient()
            audio.play('warning', 1.)
            audio.play('mission_complete', 1.)
            for _ in range(100):
                audio.play('big_explosion', 1.)
            assert pygame.mixer.Channel(0).get_busy()
            assert pygame.mixer.Channel(1).get_sound() is audio.night_sounds['warning']
            assert pygame.mixer.Channel(2).get_sound() is audio.night_sounds['mission_complete']
            report['native_priority_saturation_passed'] = True
            pygame.mixer.stop()
            played = []
            for name in ('standard_stereo', 'night_stereo', 'night_mono'):
                sound = pygame.mixer.Sound(str(out / (name + '.wav')))
                channel = pygame.mixer.Channel(11)
                channel.set_volume(.75)
                channel.play(sound)
                assert channel.get_busy()
                deadline = pygame.time.get_ticks() + 7000
                while channel.get_busy() and pygame.time.get_ticks() < deadline:
                    pygame.time.wait(20)
                assert not channel.get_busy(), 'device playback did not finish'
                played.append(name)
            report['played_wavs'] = played
            report['device_playback_verified'] = True
        (out / 'audio_mix_metrics.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        print('AUDIO_MIX_OK', out)
        return 0
    finally:
        audio.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
