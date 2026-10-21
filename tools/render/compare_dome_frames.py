"""Compare a colony dome as Python draws it with the same dome drawn by the native window.

The shell is a rim: most of its area is nearly transparent and the limb carries the light, so a
single number cannot describe it. This measures the frame's own background, the rim's radius and
centre, the mean colour on the limb and the mean colour over the whole shell area, and prints the
two sides side by side. Both sides must be captured from the same scene
(`tools/render/dome_scene.py`); the window's projection is a separate defect, so a matched radius
means the framing was chosen correctly, not that the renderers were corrected.

Run: PYTHONPATH=. .venv/bin/python tools/render/compare_dome_frames.py \
        --python full=FILE --python pulse=FILE --native full=FILE --native flash=FILE [--out J]
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from PIL import Image


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float64) / 255.0


def describe(frame: np.ndarray, threshold: float = 0.004) -> dict:
    """Rim radius, limb colour and shell-area colour, measured on a radial profile.

    Both sides draw the dome over an empty frame - Python over black, the window over its own sky -
    so the background is the median of the top strip. The radius is read off the profile rather
    than off a bounding box: a bbox follows the faintest and the brightest stray pixel, and the
    window's frame carries a small status mark in its bottom rows.
    """
    height, width = frame.shape[:2]
    edge = 20
    background = np.median(frame[:6].reshape(-1, 3), axis=0)
    delta = frame - background
    energy = delta.max(axis=2)
    yy, xx = np.mgrid[0:height, 0:width]
    centre = (width / 2.0, height / 2.0)
    # Centre from the shell's own mass, restricted to the frame without its bottom strip.
    inner = energy[:height - edge]
    centre = (float(np.nonzero(inner)[1].mean()) if inner.any() else centre[0], centre[1])
    r = np.hypot(xx - centre[0], yy - centre[1]).astype(int)
    profile = np.bincount(r.ravel(), weights=energy.ravel(), minlength=int(r.max()) + 2)
    counts = np.bincount(r.ravel(), minlength=int(r.max()) + 2)
    radial = profile / np.maximum(counts, 1)
    peak_r = int(np.argmax(radial))
    peak = float(radial[peak_r])
    above = np.nonzero(radial > threshold)[0]
    mask = energy > threshold
    mask[height - edge:] = False
    radius = float(above.max()) if above.size else 0.0
    limb = mask & (np.abs(r - peak_r) <= 3)
    body = mask & (r < peak_r - 20)
    def mean(patch: np.ndarray, sel: np.ndarray) -> list:
        return [round(float(v), 4) for v in patch[sel].mean(axis=0)] if sel.any() else [0.0] * 3
    return {
        'background': [round(float(v), 4) for v in background],
        'pixels': int(mask.sum()),
        'centre': [round(centre[0], 1), round(centre[1], 1)],
        'radius': round(radius, 2),
        'rim_radius': peak_r,
        'rim_energy': round(peak, 5),
        'limb_mean_rgb': mean(delta, limb),
        'limb_pixels': int(limb.sum()),
        'body_mean_rgb': mean(delta, body),
        'peak_rgb': [round(float(v), 4) for v in delta[mask].max(axis=0)] if mask.any() else [0.0] * 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', action='append', default=[], metavar='LABEL=FILE')
    parser.add_argument('--native', action='append', default=[], metavar='LABEL=FILE')
    parser.add_argument('--out')
    args = parser.parse_args()

    result: dict = {}
    for label, path in (item.split('=', 1) for item in args.python):
        result.setdefault(label, {})['python'] = describe(load(path))
    for label, path in (item.split('=', 1) for item in args.native):
        result.setdefault(label, {})['native'] = describe(load(path))

    for label, sides in result.items():
        print(f'--- {label}')
        for side, values in sides.items():
            if not values.get('pixels'):
                print(f'  {side:7s} nothing drawn')
                continue
            print(f"  {side:7s} centre {values['centre']} radius {values['radius']:7.2f} "
                  f"px {values['pixels']:6d} limb {values['limb_mean_rgb']} "
                  f"body {values['body_mean_rgb']} peak {values['peak_rgb']}")
        if len(sides) == 2 and all(s.get('pixels') for s in sides.values()):
            a, b = sides['python'], sides['native']
            radius_ratio = b['radius'] / a['radius'] if a['radius'] else 0.0
            print(f"  ratio   radius {radius_ratio:.4f}  "
                  f"area {b['pixels'] / max(1, a['pixels']):.4f}  "
                  f"limb b/r {b['limb_mean_rgb'][2] / max(1e-6, a['limb_mean_rgb'][2]):.4f}  "
                  f"limb g/r {b['limb_mean_rgb'][1] / max(1e-6, a['limb_mean_rgb'][1]):.4f}")
            result[label]['radius_ratio'] = round(radius_ratio, 4)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
        print('written', args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
