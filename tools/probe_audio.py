"""Audio probe: measure what is wrong with the SFX, before and after.

The mixer is opened with SDL_AUDIODRIVER=dummy and the Sounds are created the
normal way, so this runs headlessly. Everything below is measured from the
actual sample buffers pygame will play — not from the synthesis parameters.

Metrics, and why each one is here:

  duration vs intended   pygame reports the played length; if the mixer runs at
                         a different rate than the buffers were synthesized at,
                         every sound plays FAST and HIGH. This was a live bug:
                         RATE=22050 but the mixer opened at 44100, so every
                         sound played at 2x pitch in half its time.
  spectral centroid      brightness (Hz). A "laser" should be bright, an
                         "explosion" should be dark; if they are all similar the
                         voices are not differentiated.
  spectral flatness      ~0 = tonal, ~1 = hiss. White noise with no filtering
                         scores near 1 and reads as static, not as a weapon.
  crest / onset click    a discontinuity at the start is an audible tick.
  peak / rms             headroom and whether the sound is actually audible.
  low-band energy        <150 Hz share — explosions need sub-bass to have body.

Usage: SDL_AUDIODRIVER=dummy PYTHONPATH=. ./.venv/bin/python tools/probe_audio.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np                                   # noqa: E402
import pygame                                        # noqa: E402

pygame.init()


class _FakeEvents:
    def subscribe(self, *a, **k):
        pass


class _FakeState:
    time = 0.0
    events = _FakeEvents()


def _decode(snd):
    """Played samples as float arrays, resampled to the MIXER's real rate.

    get_raw() returns the buffer AT THE MIXER'S RATE, so anything computed from
    it is what is actually heard.
    """
    arr = pygame.sndarray.array(snd).astype(np.float64) / 32768.0
    rate = pygame.mixer.get_init()[0]
    return arr, rate


def _mono(arr):
    return arr.mean(axis=1) if arr.ndim > 1 else arr


def _spectrum(x, rate, nperseg=2048):
    """Simplified periodogram: Hann window, averaged over frames."""
    n = min(nperseg, len(x))
    if n < 64:
        return np.zeros(2), np.zeros(2)
    hop = max(1, n // 2)
    frames = [x[i:i + n] for i in range(0, len(x) - n + 1, hop)]
    if not frames:
        frames = [x[:n]]
    win = np.hanning(n)
    acc = np.zeros(n // 2 + 1)
    for f in frames:
        sp = np.abs(np.fft.rfft(f * win)) ** 2
        acc += sp
    acc /= len(frames)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    return freqs, acc


def metrics(snd, intended_dur=None):
    arr, rate = _decode(snd)
    x = _mono(arr)
    if len(x) < 8 or np.max(np.abs(x)) < 1e-9:
        return None
    freqs, psd = _spectrum(x, rate)
    total = psd.sum() + 1e-12
    centroid = float((freqs * psd).sum() / total)
    p = psd / total
    flatness = float(np.exp(np.mean(np.log(p + 1e-12))) / (np.mean(p) + 1e-12))
    low = float(psd[freqs < 150.0].sum() / total)
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    # onset click: first-sample discontinuity relative to the body's scale
    onset = float(abs(x[0]) / (peak + 1e-12))
    length = float(snd.get_length())
    ratio = (length / intended_dur) if intended_dur else None
    return {"dur": length, "ratio": ratio, "centroid": centroid,
            "flatness": flatness, "low": low, "peak": peak, "rms": rms,
            "onset": onset, "rate": rate, "samples": len(x)}


def main():
    from render.audio import Audio, RATE
    a = Audio(_FakeState())
    if not a.available:
        print("mixer unavailable"); return 1
    mixer_rate = pygame.mixer.get_init()[0]
    print(f"synth RATE={RATE}  mixer rate={mixer_rate}", end="")
    print("   <-- MISMATCH: every sound plays fast and high"
          if mixer_rate != RATE else "   (match)")

    # intended durations, read from the synthesis table
    intended = {
        "laser": 0.07, "laser_heavy": 0.13, "impact": 0.09,
        "explosion": 0.65, "big_explosion": 1.3, "jump": 1.4,
        "build": 0.16, "ui": 0.045, "alert": 0.30,
    }
    print(f"\n{'sound':16s} {'got s':>7} {'want s':>7} {'ratio':>6} "
          f"{'centroid':>9} {'flat':>6} {'low<150':>8} {'peak':>6} {'onset':>6}")
    fails = []
    for name in sorted(a.sounds):
        m = metrics(a.sounds[name], intended.get(name))
        if m is None:
            print(f"{name:16s}  SILENT")
            fails.append(f"{name} is silent")
            continue
        r = f"{m['ratio']:.2f}" if m["ratio"] else "  -  "
        print(f"{name:16s} {m['dur']:7.3f} "
              f"{intended.get(name, float('nan')):7.3f} {r:>6} "
              f"{m['centroid']:9.0f} {m['flatness']:6.3f} "
              f"{m['low'] * 100:7.1f}% {m['peak']:6.3f} {m['onset']:6.3f}")

    print("\n--- verdicts ---")
    # 1. pitch/duration: the headline bug
    if mixer_rate != RATE:
        fails.append(f"mixer rate {mixer_rate} != synth rate {RATE}: every SFX "
                     f"plays at {mixer_rate / RATE:.0f}x pitch in "
                     f"{RATE / mixer_rate:.2f}x the time")
    # 2. voices must be spectrally distinct
    cs = {n: metrics(a.sounds[n])["centroid"] for n in a.sounds
          if metrics(a.sounds[n])}
    if cs.get("laser") and cs.get("explosion"):
        if cs["laser"] < cs["explosion"] * 1.5:
            fails.append(f"laser centroid {cs['laser']:.0f}Hz is not clearly "
                         f"brighter than explosion {cs['explosion']:.0f}Hz")
    # 3. noise must be filtered, not hiss
    for n in ("impact", "explosion", "big_explosion"):
        m = metrics(a.sounds[n])
        if m and m["flatness"] > 0.55:
            fails.append(f"{n} spectral flatness {m['flatness']:.2f} is "
                         f"hiss-like (unfiltered white noise)")
    # 4. explosions need sub-bass
    for n in ("explosion", "big_explosion"):
        m = metrics(a.sounds[n])
        if m and m["low"] < 0.05:
            fails.append(f"{n} has only {m['low'] * 100:.1f}% energy below "
                         f"150Hz — no body")
    # 5. no onset clicks
    for n, m in ((n, metrics(a.sounds[n])) for n in a.sounds):
        if m and m["onset"] > 0.35:
            fails.append(f"{n} starts at {m['onset']:.2f} of peak — onset click")
    # 6. audible
    for n, m in ((n, metrics(a.sounds[n])) for n in a.sounds):
        if m and m["peak"] < 0.05:
            fails.append(f"{n} peak {m['peak']:.3f} is near-inaudible")

    if fails:
        print(f"AUDIO_PROBE_FAIL ({len(fails)} issues)")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("AUDIO_PROBE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
