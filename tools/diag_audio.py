"""Render every voice to a WAV + a spectrogram montage for real inspection.

The probe measures numbers; this produces the actual audio so the result can be
checked by ear and by eye (spectrograms), not just asserted.

Usage: SDL_AUDIODRIVER=dummy PYTHONPATH=. ./.venv/bin/python tools/diag_audio.py
"""
from __future__ import annotations

import os
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np                                            # noqa: E402
import pygame                                                 # noqa: E402

pygame.init()

OUT = os.path.join(ROOT, "saves")
os.makedirs(OUT, exist_ok=True)


class _Events:
    def subscribe(self, *a, **k):
        pass


class _State:
    time = 0.0
    events = _Events()


def write_wav(path, mono, rate):
    st = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(st.tobytes())


def spectrogram(x, rate, nfft=1024, hop=256):
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    frames = 1 + (len(x) - nfft) // hop
    win = np.hanning(nfft)
    S = np.zeros((nfft // 2 + 1, frames))
    for i in range(frames):
        seg = x[i * hop:i * hop + nfft] * win
        S[:, i] = np.abs(np.fft.rfft(seg))
    S = 20 * np.log10(S + 1e-6)
    S -= S.max()
    return np.clip(S, -60, 0)


def to_montage(items, path, cell_w=300, cell_h=64, cols=4):
    """Grid of labelled spectrograms: time on x, frequency on y per cell."""
    import pygame
    pygame.font.init()
    font = pygame.font.SysFont("menlo,consolas,monaco", 11)
    rows = (len(items) + cols - 1) // cols
    label_h = 14
    W = cols * cell_w
    H = rows * (cell_h + label_h)
    out = pygame.Surface((W, H))
    out.fill((18, 18, 22))
    for i, (name, spec) in enumerate(items):
        # spec is (freq, time) with LOW frequencies first -> flip to draw
        # low frequencies at the BOTTOM of the cell
        img = spec[::-1, :]
        fh, tw = img.shape
        a = ((img + 60) / 60.0 * 255).astype(np.uint8)
        small = pygame.Surface((tw, fh))
        rgb = np.repeat(a[:, :, None], 3, axis=2)
        pygame.surfarray.blit_array(small, np.transpose(rgb, (1, 0, 2)))
        # stretch to a uniform cell (time -> x, frequency -> y)
        small = pygame.transform.scale(small, (cell_w - 8, cell_h - 4))
        cx = (i % cols) * cell_w
        cy = (i // cols) * (cell_h + label_h)
        out.blit(small, (cx + 4, cy + label_h))
        out.blit(font.render(name, True, (235, 235, 245)), (cx + 4, cy + 1))
    pygame.image.save(out, path)


def main():
    from render.audio import Audio
    a = Audio(_State())
    if not a.available:
        print("mixer unavailable"); return 1
    rate = a.rate
    print(f"rate={rate}  voices={len(a.sounds)}")

    order = ["laser", "laser_pd", "turbolaser", "turbolaser_heavy", "ion",
             "missile", "torpedo", "kinetic", "plasma", "beam",
             "impact_shield", "impact_hull", "explosion", "big_explosion",
             "jump", "build", "research", "alert", "mission_complete",
             "mission_failed", "convoy", "raid", "ability", "warning", "ui"]
    items = []
    for name in order:
        snd = a.sounds.get(name)
        if snd is None:
            continue
        arr = pygame.sndarray.array(snd).astype(np.float64) / 32768.0
        mono = arr.mean(axis=1) if arr.ndim > 1 else arr
        write_wav(os.path.join(OUT, f"sfx_{name}.wav"), mono, rate)
        spec = spectrogram(mono, rate)
        # pad every spectrogram to the same time width so cells compare
        target = 400
        if spec.shape[1] < target:
            spec = np.pad(spec, ((0, 0), (0, target - spec.shape[1])))
        items.append((name, spec))
        x = mono
        n = min(2048, len(x))
        sp = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
        f = np.fft.rfftfreq(n, 1.0 / rate)
        cen = float((f * sp).sum() / (sp.sum() + 1e-12))
        print(f"  {name:18s} {snd.get_length():5.2f}s  centroid {cen:7.0f}Hz  "
              f"peak {np.max(np.abs(x)):.2f}")

    png = os.path.join(OUT, "sfx_spectrograms.png")
    to_montage(items, png)
    print(f"\nwrote {len(items)} WAVs + {png}")
    print(f"grid order (left->right, top->bottom): {', '.join(n for n, _ in items)}")
    print("AUDIO_DIAG_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
