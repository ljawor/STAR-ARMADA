"""Issue #91: laser and photon voices, held to the owner's reference recordings.

The owner supplied a recorded laser shot and a recorded photon gun. Neither is
shipped — every voice in render/audio.py is synthesised — so "it should sound
like this" can only be checked as numbers. tools/sfx_character.py measures a
recording and a voice with the SAME function (weight = spectral centroid, crack
= 95 % magnitude rolloff, tail = how long it stays above -20 dB), and the bands in
tools/diag_weapon_sfx.py are what these tests pin.

The one place a synthesised voice legitimately differs: the recordings swell to
their peak after 70-150 ms, while a game voice is punched in ~3 ms. That is
deliberate (fire feedback at RTS rates) and is why the tests pin weight, crack
and length rather than the transient's shape.
"""
import os
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest

import numpy as np

from tools.diag_weapon_sfx import BANDS, RELATIONS
from tools.sfx_character import REFERENCE_TARGETS, bank_voices, character


class TestWeaponSfxAgainstTheReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pygame
        cls.voices = bank_voices(sorted(BANDS))
        init = pygame.mixer.get_init()
        cls.rate = init[0] if init else 44100
        cls.measured = {name: character(mono, cls.rate)
                        for name, mono in cls.voices.items()}

    def test_every_voice_sits_in_the_band_the_references_define(self):
        for name, bands in sorted(BANDS.items()):
            for key, (low, high) in sorted(bands.items()):
                with self.subTest(voice=name, metric=key):
                    value = self.measured[name][key]
                    self.assertIsNotNone(value)
                    self.assertGreaterEqual(value, low)
                    self.assertLessEqual(value, high)

    def test_the_relationships_that_keep_the_voices_apart_hold(self):
        for label, (key, a, op, factor, key2, b) in RELATIONS:
            with self.subTest(relation=label):
                va, vb = self.measured[a][key], self.measured[b][key2]
                if op == '>':
                    self.assertGreater(va, vb * factor, f'{a}.{key}={va} vs {b}.{key2}={vb}')
                else:
                    self.assertLess(va, vb * factor, f'{a}.{key}={va} vs {b}.{key2}={vb}')

    def test_the_laser_matches_the_recorded_laser(self):
        """Weight within 60 % and length within 30 % of the reference recording."""
        ref, laser = REFERENCE_TARGETS['laser'], self.measured['laser']
        for key, tolerance in (('all_centroid', .6), ('all_roll95', .6), ('tail_ms', .3)):
            with self.subTest(metric=key):
                self.assertLess(abs(laser[key] - ref[key]) / ref[key], tolerance,
                                f'laser {key}={laser[key]} vs reference {ref[key]}')

    def test_the_photon_voice_matches_the_recorded_photon_gun(self):
        ref, heavy = REFERENCE_TARGETS['photon'], self.measured['turbolaser']
        for key, tolerance in (('all_centroid', .6), ('all_roll95', .25), ('tail_ms', .25)):
            with self.subTest(metric=key):
                self.assertLess(abs(heavy[key] - ref[key]) / ref[key], tolerance,
                                f'turbolaser {key}={heavy[key]} vs reference {ref[key]}')

    def test_the_laser_no_longer_reads_as_a_bare_chirp(self):
        """The pre-#91 voice was an 85 ms chirp: centroid >5 kHz, rolloff ~18 kHz.

        A laser bolt is a hit: its weight has to sit in the low mids, and its top
        end has to be quiet enough that the crack does not become the sound.
        """
        laser = self.measured['laser']
        self.assertLess(laser['all_centroid'], 2000, 'laser has no weight left')
        self.assertLess(laser['all_roll95'], 4500, 'laser is a hiss again')
        self.assertGreater(laser['tail_ms'], 100, 'laser must not be a click')
        self.assertLess(laser['dur_ms'], 350, 'a laser bolt must not linger')

    def test_no_voice_is_silent_or_clipped(self):
        """Every voice is peak-normalised to 0.85 by _to_sound().

        The sample peak is what catches a clipped voice: an envelope peak over a
        4 ms window cannot see a 3 ms transient driven past full scale.
        """
        for name, mono in sorted(self.voices.items()):
            with self.subTest(voice=name):
                c = self.measured[name]
                self.assertGreater(c['dur_ms'], 100)
                self.assertGreater(c['peak_dbfs'], -14)
                self.assertLess(c['peak_dbfs'], -1)
                self.assertLessEqual(float(np.max(np.abs(mono))), 0.86,
                                     'voice was normalised past full scale')

    def test_no_two_voices_are_the_same_shot_relabelled(self):
        """A weapon has to be identifiable by ear; 10 % is the floor for that."""
        names = sorted(self.measured)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                with self.subTest(pair=(a, b)):
                    deltas = [abs(self.measured[a][key] - self.measured[b][key])
                              / self.measured[b][key]
                              for key in ('all_centroid', 'all_roll95', 'tail_ms')]
                    self.assertGreater(max(deltas), 0.10,
                                       f'{a} and {b} measure as the same shot')


if __name__ == '__main__':
    unittest.main()
