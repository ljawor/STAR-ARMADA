"""Capture actual SDL_mixer postmix PCM for production factory firing events.

This is a mixer-output diagnostic, NOT a microphone/device-output recording or
human listening acceptance. Use --driver coreaudio for a native macOS run.
"""
from __future__ import annotations

import argparse
import ctypes
import threading
import json
import os
from pathlib import Path
import sys
import wave

import numpy as np
import pygame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class MixerCapture:
    """Hook pygame's bundled SDL_mixer; validate format before decoding PCM."""
    def __init__(self):
        init = pygame.mixer.get_init()
        if init is None or init[1:] != (-16, 2):
            raise RuntimeError('Postmix capture requires signed 16-bit stereo mixer')
        self.rate = init[0]
        directory = Path(pygame.__file__).parent
        candidates = list((directory / '.dylibs').glob('*SDL2_mixer*'))
        candidates += list(directory.glob('*SDL2_mixer*.dll'))
        for folder in ('pygame_ce.libs', 'pygame.libs'):
            candidates += list((directory.parent / folder).glob('*SDL2_mixer*'))
        # An arbitrary system library may be a second, unopened mixer instance.
        if not candidates:
            raise RuntimeError('Cannot locate pygame bundled SDL_mixer for postmix capture')
        self.library = ctypes.CDLL(str(candidates[0]))
        self.library.Mix_QuerySpec.argtypes = [ctypes.POINTER(ctypes.c_int),
                                             ctypes.POINTER(ctypes.c_ushort),
                                             ctypes.POINTER(ctypes.c_int)]
        self.library.Mix_QuerySpec.restype = ctypes.c_int
        rate, fmt, channels = ctypes.c_int(), ctypes.c_ushort(), ctypes.c_int()
        opened = self.library.Mix_QuerySpec(ctypes.byref(rate), ctypes.byref(fmt),
                                           ctypes.byref(channels))
        expected_format = 0x8010 if sys.byteorder == 'little' else 0x9010
        if not opened or (rate.value, fmt.value, channels.value) != (self.rate, expected_format, 2):
            raise RuntimeError('Bundled SDL_mixer does not match pygame signed 16-bit stereo mixer')
        self.blocks = []
        self.frames = 0
        self.condition = threading.Condition()
        self.callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
        self.callback = self.callback_type(self._capture)
        self.library.Mix_SetPostMix.argtypes = [self.callback_type, ctypes.c_void_p]
        self.library.Mix_SetPostMix.restype = None

    def _capture(self, _, stream, size):
        with self.condition:
            self.blocks.append(ctypes.string_at(stream, size))
            self.frames += size // 4
            self.condition.notify_all()

    def __enter__(self):
        self.library.Mix_SetPostMix(self.callback, None)
        try:
            self.wait_frames(1)  # Prove this is the live mixer before firing.
        except BaseException:
            self.__exit__()
            raise
        with self.condition:
            self.blocks.clear()
            self.frames = 0
        return self

    def __exit__(self, *args):
        self.library.Mix_SetPostMix(self.callback_type(), None)

    def wait_frames(self, frames, timeout=2.):
        """Wait for an absolute captured-frame count, with a bounded deadline."""
        with self.condition:
            if not self.condition.wait_for(lambda: self.frames >= frames, timeout):
                raise RuntimeError(f'SDL postmix callback timeout: {self.frames}/{frames} frames')

    def pcm(self):
        with self.condition:
            return np.frombuffer(b''.join(self.blocks), dtype=np.int16).reshape(-1, 2).copy()


def combat_fixture(ship_id, distance=6000.):
    """Controlled placement; real factory, visibility, weapons and bus unchanged."""
    from game.core.manager import GameManager
    from game.core.vectors import Vec3
    from render.camera import Camera
    from render.audio import Audio
    definition = json.loads((ROOT / 'assets/data/maps/skirmish01.json').read_text())
    for player in definition['players']:
        player['is_ai'] = False
    gm = GameManager.start_skirmish(definition)
    shooter = gm.factory.spawn_ship(ship_id, 0, Vec3(0, 0, 0))
    target = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(0, 0, 400))
    shooter.current_target = target.id
    shooter.order_type = 'hold'
    camera = Camera(960, 640)
    camera.distance = distance
    audio = Audio(gm.state)
    if not audio.available:
        raise RuntimeError('SDL audio initialization failed')
    audio.set_camera(camera)
    return gm, shooter, target, audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--driver', default='dummy')
    parser.add_argument('--baseline', action='store_true', help='Load committed HEAD audio in memory')
    args = parser.parse_args()
    os.environ['SDL_AUDIODRIVER'] = args.driver
    if args.baseline:
        import subprocess
        import render.audio
        exec(compile(subprocess.check_output(['git', 'show', 'HEAD:render/audio.py'], cwd=ROOT),
                     'HEAD:render/audio.py', 'exec'), render.audio.__dict__)
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for ship_id in ('imperial_tie_squadron', 'imperial_corvette'):
        gm, shooter, target, audio = combat_fixture(ship_id)
        events = []
        gm.state.events.subscribe('weapon_fired', lambda ev: events.append(dict(ev.data)))
        try:
            with MixerCapture() as capture:
                # Actual manager tick produces the firing event, not a fabricated publish.
                gm.step(1 / 30)
                capture.wait_frames(int(audio.rate * .25))
            pcm = capture.pcm()
            shot_events = [ev for ev in events if ev['attacker_id'] == shooter.id]
            if not shot_events:
                raise AssertionError('Factory craft did not produce weapon_fired')
            voice = next(iter(audio._active_voices.values()), None)
            gains = audio.mix_gains(voice[0], voice[1], voice[2]) if voice else (0., 0.)
            entry = dict(ship=ship_id, kind=shooter.kind, shots=len(shot_events),
                         weapon=shot_events[0]['weapon'], intended_gains=gains,
                         legacy_panning_bytes=[int(g * 255) for g in gains],
                         sound_gain=voice[3].get_volume() if voice else 1.,
                         staged_panning_bytes=[int(g / voice[3].get_volume() * 255) for g in gains]
                             if voice else [0, 0],
                         frames=len(pcm), nonzero_samples=int(np.count_nonzero(pcm)),
                         peak=int(np.max(np.abs(pcm.astype(np.int32)))) if pcm.size else 0,
                         mixer=pygame.mixer.get_init(), driver=args.driver)
            results.append(entry)
            with wave.open(str(args.out / (ship_id + '.wav')), 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(audio.rate)
                wav.writeframes(pcm.tobytes())
        finally:
            audio.cleanup()
    report = dict(baseline=args.baseline, results=results,
                  device_output_recorded=False, human_listening_verified=False)
    (args.out / 'weapon_audio_metrics.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not all(entry['nonzero_samples'] > 0 for entry in results):
        raise SystemExit('WEAPON_AUDIO_FAIL: production firing produced silent SDL postmix')
    print('WEAPON_AUDIO_OK: production ship and squadron shots reached SDL postmix')


if __name__ == '__main__':
    main()
