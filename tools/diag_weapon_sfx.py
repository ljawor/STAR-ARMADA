"""Acceptance probe for issue #91: do the laser/photon voices match the references?

Prints a metrics table (measured, not asserted by ear), writes a spectrogram per
voice next to the reference recording's spectrogram, and exports the voices as
WAV files so a human can listen. Exits non-zero if any voice drifts out of the
band the references define.

    python tools/diag_weapon_sfx.py --out ~/.hermes/cache/scratch/sfx91
    python tools/diag_weapon_sfx.py --out /tmp/sfx91 --reference ~/Downloads/ref.wav
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sfx_character import (REFERENCE_TARGETS, bank_voices, character,  # noqa: E402
                                 load_wav, spectrogram_png)

#: Band each voice must stay inside. Built from the reference recordings'
#: character (laser: weight ~1.3 kHz, ring-out rolloff ~2.8 kHz, 137 ms tail;
#: photon: weight ~1.0 kHz, broadband ~7.3 kHz, 359 ms tail) and widened where a
#: synthesised shot legitimately differs from a recording — a recording swells
#: to its peak over 70-150 ms, a game voice is punched in 3 ms, so its 30-120 ms
#: window (``body_``) sits brighter than the reference's. The bands therefore pin
#: weight, crack and length, which is what the ear identifies a weapon by.
BANDS = {
    # a laser bolt is a short dark thump, brighter than the photon voice is wide.
    # body_roll95 is the fizz's fingerprint: without it the ring-out goes flat.
    "laser": dict(all_centroid=(950, 1950), all_roll95=(2200, 4500),
                  body_centroid=(1000, 1900), body_roll95=(2300, 3400),
                  tail_ms=(105, 190)),
    "laser_b": dict(all_centroid=(1000, 2100), all_roll95=(2400, 4700),
                    body_centroid=(1000, 2000), body_roll95=(2400, 3600),
                    tail_ms=(95, 185)),
    "laser_c": dict(all_centroid=(850, 1750), all_roll95=(1900, 4000),
                    body_centroid=(950, 1850), body_roll95=(2100, 3200),
                    tail_ms=(110, 220)),
    # point-defense: the same gun, smaller — brighter and over sooner
    "laser_pd": dict(all_centroid=(1500, 3000), all_roll95=(4000, 9000),
                     body_centroid=(1200, 2400), body_roll95=(2600, 4000),
                     tail_ms=(65, 140)),
    "laser_heavy": dict(all_centroid=(650, 1400), all_roll95=(1150, 3000),
                         body_centroid=(850, 1700), body_roll95=(1850, 2900),
                         tail_ms=(150, 300)),
    # the photon gun: same weight, far more top end, a much longer tail
    "turbolaser": dict(all_centroid=(850, 1700), all_roll95=(5000, 10500),
                       body_centroid=(1100, 2300), body_roll95=(7000, 11000),
                       tail_ms=(250, 500)),
    "turbolaser_heavy": dict(all_centroid=(750, 1600), all_roll95=(5000, 10800),
                              body_centroid=(1050, 2200), body_roll95=(7000, 11200),
                              tail_ms=(350, 720)),
    "plasma": dict(all_centroid=(750, 1600), all_roll95=(4200, 9000),
                   body_centroid=(1100, 2300), body_roll95=(7000, 11200),
                   tail_ms=(250, 500)),
}

#: Relationships the mix depends on, so the voices stay tellable apart.
RELATIONS = (
    ("photon voices stay broadband where the laser is tight",
     ("all_roll95", "turbolaser", ">", 1.6, "all_roll95", "laser")),
    ("the photon voice is not simply a louder laser",
     ("all_centroid", "turbolaser", "<", 1.35, "all_centroid", "laser")),
    ("point-defense is brighter than the laser it defends",
     ("all_centroid", "laser_pd", ">", 1.15, "all_centroid", "laser")),
    ("point-defense is over sooner than the laser",
     ("tail_ms", "laser_pd", "<", 0.9, "tail_ms", "laser")),
    ("a heavy laser rings longer than a laser",
     ("tail_ms", "laser_heavy", ">", 1.1, "tail_ms", "laser")),
    ("a heavy turbolaser rings longer than a turbolaser",
     ("tail_ms", "turbolaser_heavy", ">", 1.1, "tail_ms", "turbolaser")),
)


def export_wav(mono, rate, path):
    st = (np.clip(np.asarray(mono, dtype=np.float64), -1.0, 1.0) * 32767.0).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(st.tobytes())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=Path('/tmp/sfx91'))
    parser.add_argument('--reference', type=Path, action='append', default=[],
                        help='recorded WAV to compare against (repeatable)')
    parser.add_argument('--no-png', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    voices = bank_voices(sorted(BANDS))
    from tools.sfx_character import pygame_rate
    rate = pygame_rate()
    measured = {name: character(mono, rate) for name, mono in voices.items()}

    print(f'{"voice":18s}{"allC":>7}{"allR95":>8}{"bodyC":>7}{"bodyR95":>8}'
          f'{"tail":>7}{"peak":>7}   verdict')
    failures = []
    for name, c in measured.items():
        bad = [f'{key}={c[key]} not in {band}' for key, band in BANDS[name].items()
               if c[key] is None or not band[0] <= c[key] <= band[1]]
        failures += [f'{name}: {b}' for b in bad]
        print(f'{name:18s}{c["all_centroid"]:>7}{c["all_roll95"]:>8}{c["body_centroid"]:>7}'
              f'{c["body_roll95"]:>8}{c["tail_ms"]:>7}{c["peak_dbfs"]:>7}   '
              f'{"ok" if not bad else "FAIL"}')
        export_wav(voices[name], rate, args.out / f'{name}.wav')
        if not args.no_png:
            spectrogram_png(voices[name], rate, args.out / f'{name}.png', title=name)

    print('\nreference recordings measured with the same function:')
    from tools.sfx_character import character_of_shots
    for ref in args.reference:
        ref_rate, mono = load_wav(ref)
        c = character_of_shots(mono, ref_rate)
        print(f'  {ref.name:28s} shots={c["shots"]:>3} allC={c["all_centroid"]:>6} '
              f'allR95={c["all_roll95"]:>6} bodyC={c["body_centroid"]:>6} '
              f'tail={c["tail_ms"]:>7}')
        if not args.no_png:
            spectrogram_png(mono, ref_rate, args.out / f'reference_{ref.stem[:20]}.png',
                            title=ref.name)
    print('\nreference character the bands were derived from (issue #91):')
    for name, tgt in REFERENCE_TARGETS.items():
        print(f'  {name:8s} allC={tgt["all_centroid"] if "all_centroid" in tgt else "-"} '
              f'allR95={tgt["all_roll95"] if "all_roll95" in tgt else "-"} '
              f'bodyC={tgt["body_centroid"]:>5} tail={tgt["tail_ms"]:>5} ms')

    for label, (key, a, op, factor, key2, b) in RELATIONS:
        va, vb = measured[a][key], measured[b][key2]
        ok = va > vb * factor if op == '>' else va < vb * factor
        print(f'{"ok  " if ok else "FAIL"} {label}: {a}.{key}={va} {op} '
              f'{factor} x {b}.{key2}={vb}')
        if not ok:
            failures.append(f'{label}: {a}.{key}={va} {op} {factor} x {vb}')

    print(f'\nwrote {len(voices)} voices to {args.out} (WAV to listen, PNG to look at)')
    if failures:
        print(f'\nFAIL: {len(failures)} check(s) failed')
        for f in failures:
            print('  -', f)
        return 1
    print('\nOK: every voice sits inside the band the reference recordings define')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
