"""Measure the character of a weapon voice — attack, tail, brightness, timbre.

Issue #91: the owner supplied two reference recordings (a laser and a photon
gun). They are NOT shipped with the game — ``render/audio.py`` synthesises every
voice — so "our laser sounds like the reference" has to be a measurement, not an
opinion. This module measures a recorded shot and a synthesised voice with the
SAME function, so the comparison is apples to apples:

* ``character()``      — one shot: attack, time to peak, tail, peak level and the
                         spectral centroid / 95 % rolloff of the onset and the body.
* ``shots()``          — split a recording into individual shots (the photon
                         reference holds 141 of them).
* ``character_of_shots()`` — median and 10th/90th percentiles across the shots.
* ``bank_voices()``    — build the game's real sound bank headless as mono arrays.
* ``spectrogram_png()``— a spectrogram, drawn with pygame (no matplotlib here).

Usage::

    python tools/sfx_character.py --voices laser,turbolaser,plasma
    python tools/sfx_character.py --reference path/to/ref.wav
    python tools/sfx_character.py --reference ref.wav --spectrogram out.png
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Reference files are external to the repo (never shipped); these numbers were
#: taken from them with ``character_of_shots`` below and are what the synthesised
#: voices are held to. Note both recordings SWELL to their peak (laser 68 ms,
#: photon 147 ms in), which is why their ring-out window is not darker than their
#: whole shot; a game voice is punched at 3 ms instead, deliberately.
REFERENCE_TARGETS = {
    "laser": dict(all_centroid=1279, all_roll95=3589, body_centroid=1101,
                  body_roll95=2788, tail_ms=136.8, peak_dbfs=-8.1),
    "photon": dict(all_centroid=1033, all_roll95=7280, body_centroid=859,
                   body_roll95=6344, tail_ms=358.9, peak_dbfs=-11.3),
}

DB_FLOOR = -80.0


# ------------------------------------------------------------------ measurement
def envelope(x, rate, win_ms: float = 4.0) -> np.ndarray:
    """Smoothed amplitude envelope (RMS over a short sliding window)."""
    win = max(8, int(rate * win_ms / 1000.0))
    x = np.asarray(x, dtype=np.float64)
    return np.sqrt(np.convolve(x * x, np.ones(win) / win, 'same'))


def _spectrum(x, rate, start_ms, end_ms):
    i0 = max(0, int(start_ms * rate / 1000.0))
    i1 = min(len(x), int(end_ms * rate / 1000.0))
    if i1 - i0 < 32:
        return None
    seg = x[i0:i1] * np.hanning(i1 - i0)
    sp = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1.0 / rate)
    total = float(sp.sum()) + 1e-12
    centroid = float((sp * fr).sum() / total)
    roll95 = float(fr[min(int(np.searchsorted(np.cumsum(sp) / total, 0.95)), len(fr) - 1)])
    return centroid, roll95


def character(mono, rate) -> dict:
    """Character of a single shot. All times in ms, all brightness in Hz."""
    x = np.asarray(mono, dtype=np.float64)
    env = envelope(x, rate)
    peak = float(env.max()) if len(env) else 0.0
    if peak < 1e-9:
        return dict(dur_ms=round(len(x) / rate * 1000, 1), peak_dbfs=DB_FLOOR,
                    attack_ms=0.0, to_peak_ms=0.0, tail_ms=0.0, onset_centroid=None,
                    onset_roll95=None, body_centroid=None, body_roll95=None)
    pk = int(env.argmax())
    above = np.flatnonzero(env > 0.1 * peak)
    attack = float((env > 0.9 * peak).argmax() - above[0]) / rate * 1000.0
    onset = _spectrum(x, rate, pk / rate * 1000.0, pk / rate * 1000.0 + 10.0)
    body = _spectrum(x, rate, 30.0, 120.0)
    whole = _spectrum(x, rate, 0.0, len(x) / rate * 1000.0)
    out = dict(dur_ms=round(len(x) / rate * 1000, 1),
               peak_dbfs=round(20 * np.log10(peak), 1),
               attack_ms=round(attack, 1),
               to_peak_ms=round(pk / rate * 1000.0, 1),
               tail_ms=round(float(above[-1]) / rate * 1000.0, 1))
    for key, val in (("onset", onset), ("body", body), ("all", whole)):
        out[f'{key}_centroid'] = int(val[0]) if val else None
        out[f'{key}_roll95'] = int(val[1]) if val else None
    return out


def shots(mono, rate, floor_db: float = -45.0, min_ms: float = 120.0):
    """Split a recording into single shots: runs above ``floor_db``."""
    x = np.asarray(mono, dtype=np.float64)
    env = envelope(x, rate, win_ms=5.0)
    on = env > 10 ** (floor_db / 20.0)
    edges = np.flatnonzero(np.diff(on.astype(np.int8)))
    spans = [(a, b) for a, b in zip(edges[::2], edges[1::2])
             if (b - a) / rate * 1000.0 >= min_ms]
    return [(a / rate, b / rate) for a, b in spans]


def character_of_shots(mono, rate, **kw) -> dict:
    """Median/p10/p90 of ``character()`` across every shot in a recording."""
    x = np.asarray(mono, dtype=np.float64)
    rows = []
    for start, end in shots(x, rate, **kw):
        i0 = max(0, int(start * rate) - int(rate * 0.01))
        i1 = min(len(x), int(end * rate) + int(rate * 0.02))
        rows.append(character(x[i0:i1], rate))
    out = {"shots": len(rows)}
    keys = [k for k in (rows[0] if rows else {}) if k != 'dur_ms']
    for key in keys:
        vals = np.array([r[key] for r in rows if r[key] is not None], dtype=float)
        if not len(vals):
            out[key] = None
            continue
        out[key] = round(float(np.median(vals)), 1)
        out[f"{key}_p10"] = round(float(np.percentile(vals, 10)), 1)
        out[f"{key}_p90"] = round(float(np.percentile(vals, 90)), 1)
    return out


# ------------------------------------------------------------------ file input
def load_wav(path) -> tuple[int, np.ndarray]:
    import wave
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
        width = w.getsampwidth()
        channels = w.getnchannels()
    if width != 2:
        raise ValueError(f'{path}: expected 16-bit PCM, got {width * 8}-bit')
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return rate, x


# ------------------------------------------------------------------ game voices
def sound_mono(sound) -> np.ndarray:
    """The mono signal inside a pygame Sound (voices are built mono, stored L/R)."""
    import pygame
    arr = pygame.sndarray.array(sound)
    if arr.ndim > 1:
        arr = arr[:, 0]
    return arr.astype(np.float64) / (32768.0 if arr.dtype == np.int16 else 1.0)


def bank_voices(names=None, rate: int | None = None) -> dict:
    """Build the real sound bank headless and hand back mono arrays per voice."""
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    import pygame
    from render.audio import RATE, Audio
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=rate or RATE, size=-16, channels=2)
    engine = Audio.__new__(Audio)           # _build() only needs rate + sounds
    engine.rate = pygame.mixer.get_init()[0]
    engine.sounds = {}
    engine._build()
    out = {name: sound_mono(snd) for name, snd in engine.sounds.items()}
    if names:
        missing = [n for n in names if n not in out]
        if missing:
            raise KeyError(f'unknown voice(s): {", ".join(missing)}')
        out = {n: out[n] for n in names}
    return out


# -------------------------------------------------------------------- pictures
def _colormap(z):
    """Dark-magma-ish ramp without matplotlib."""
    stops = np.array([[0.02, 0.01, 0.06], [0.35, 0.05, 0.30],
                      [0.75, 0.18, 0.28], [0.97, 0.55, 0.18], [1.0, 0.98, 0.75]])
    pos = np.linspace(0.0, 1.0, len(stops))
    z = np.clip(z, 0.0, 1.0)
    out = np.empty(z.shape + (3,))
    for ch in range(3):
        out[..., ch] = np.interp(z, pos, stops[:, ch])
    return (out * 255).astype(np.uint8)


def spectrogram_png(mono, rate, path, title: str = '', nfft: int = 1024,
                    floor_db: float = -70.0, gain: float = 1.35,
                    height: int = 300, width: int = 720) -> Path:
    """Write a spectrogram PNG via pygame (log-frequency, so bass is visible).

    The hop is derived from a target width instead of being fixed: a 300 ms voice
    with a fixed hop renders 51 px wide and nothing can be read off it.
    """
    import pygame
    x = np.asarray(mono, dtype=np.float64)
    win = np.hanning(nfft)
    hop = max(1, int((max(1, len(x) - nfft)) / max(1, width)))
    frames = [x[i:i + nfft] * win for i in range(0, max(1, len(x) - nfft + 1), hop)]
    if not frames:
        frames = [np.zeros(nfft)]
    spec = np.array([np.abs(np.fft.rfft(f)) for f in frames]).T   # bins x frames
    fmin, fmax = 40.0, min(rate / 2.0, 16000.0)
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    edges = np.geomspace(fmin, fmax, height + 1)
    rows = [spec[max(0, int(np.searchsorted(freqs, lo))):
                 max(1, int(np.searchsorted(freqs, hi)))] for lo, hi in
            zip(edges[:-1], edges[1:])]
    img = np.array([r.mean(axis=0) if len(r) else np.zeros(len(frames)) for r in rows])
    db = 20 * np.log10(img + 1e-9)
    db = np.clip((db - floor_db) / -floor_db * gain, 0.0, 1.0)
    rgb = _colormap(db)[::-1]                                     # low freq at bottom
    cols = rgb.shape[1]
    surf = pygame.Surface((cols, height))
    pygame.surfarray.blit_array(surf, np.transpose(rgb, (1, 0, 2)))
    pygame.font.init()
    font = pygame.font.Font(None, 20)
    for hz in (200, 1000, 4000):
        row = int(height - (math.log(hz / fmin) / math.log(fmax / fmin)) * height)
        if 0 <= row < height:
            pygame.draw.line(surf, (90, 90, 90), (0, row), (cols, row))
            surf.blit(font.render(f'{hz} Hz', True, (200, 200, 200)), (3, max(0, row - 18)))
    total_ms = len(x) / rate * 1000.0
    if title:
        surf.blit(font.render(f'{title}   {total_ms:.0f} ms', True, (255, 255, 255)), (6, 4))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(path))
    return path


# ------------------------------------------------------------------------- CLI
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reference', type=Path, action='append', default=[],
                        help='recorded WAV to measure (repeatable)')
    parser.add_argument('--voices', default='laser,turbolaser,plasma',
                        help='comma-separated voice names, or "all"')
    parser.add_argument('--spectrogram', type=Path, default=None,
                        help='write a reference-vs-voice spectrogram PNG here')
    parser.add_argument('--json', type=Path, default=None)
    args = parser.parse_args()

    table, payload = [], {}
    for ref in args.reference:
        rate, mono = load_wav(ref)
        row = character_of_shots(mono, rate)
        payload[ref.name] = row
        table.append((ref.name, row))
        if args.spectrogram:
            spectrogram_png(mono, rate, args.spectrogram.with_name(
                f'{args.spectrogram.stem}_{ref.stem[:24]}.png'), title=ref.name)

    want = None if args.voices == 'all' else [n.strip() for n in args.voices.split(',') if n.strip()]
    voices = bank_voices(want)
    voice_rate = pygame_rate()
    for name, mono in voices.items():
        row = character(mono, voice_rate)
        payload[name] = row
        table.append((name, row))
        if args.spectrogram:
            spectrogram_png(mono, voice_rate, args.spectrogram.with_name(
                f'{args.spectrogram.stem}_{name}.png'), title=name)

    keys = ('dur_ms', 'attack_ms', 'to_peak_ms', 'tail_ms', 'peak_dbfs',
            'onset_centroid', 'onset_roll95', 'body_centroid', 'body_roll95')
    head = f'{"voice":22s}' + ''.join(f'{k.split("_")[0][:4]:>8s}' for k in keys)
    print(head)
    for name, row in table:
        cells = ''.join(f'{row.get(k) if row.get(k) is not None else "-":>8}'
                        for k in keys)
        print(f'{name[:22]:22s}{cells}')
    print('\ntargets from the references (issue #91):')
    for name, tgt in REFERENCE_TARGETS.items():
        print(f'  {name:8s} onset {tgt["onset_centroid"]:>5} Hz / roll95 '
              f'{tgt["onset_roll95"]:>5} Hz   body {tgt["body_centroid"]:>5} Hz / '
              f'roll95 {tgt["body_roll95"]:>5} Hz   tail {tgt["tail_ms"]:>4} ms')
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f'\nwrote {args.json}')
    return 0


def pygame_rate() -> int:
    import pygame
    init = pygame.mixer.get_init()
    return init[0] if init else 44100


if __name__ == '__main__':
    raise SystemExit(main())
