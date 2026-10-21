"""Compare the Python fog overlay against the native one.

Each side is rendered twice, with and without the mask, so the overlay is measured against that
renderer's own clear colour rather than an assumed one. Two things are compared:

* **opaque footprint** - the pixels the mask actually darkens. The two renderers are looking at the
  same world through the same mask, so these should coincide; any difference is a projection or
  quad-placement difference, and it is reported as an IoU rather than smoothed away.
* **the state inside that footprint** - 1 = charted, 2 = unexplored, matched by distance to the colour
  that state produces over that renderer's background (alpha scales all channels together, so a
  brightness test would confuse an exposure difference with a state difference).

The fog-free region cannot be separated from the area outside the quad on either side - both are the
background - so it is not claimed as an agreement measure.

Run: PYTHONPATH=. .venv/bin/python tools/render/compare_fog_frames.py \
       --python-on PY-ON.png --python-off PY-OFF.png --native-on NAT-ON.png --native-off NAT-OFF.png
"""
from __future__ import annotations

import argparse
import json

import numpy as np
from PIL import Image

# render/fog.py's two opaque states (0..1) and the alpha of the charted one.
CHARTED = np.array([12, 22, 38], dtype=np.float32) / 255.0
UNEXPLORED = np.array([3, 6, 13], dtype=np.float32) / 255.0
CHARTED_ALPHA = 155.0 / 255.0
OPAQUE_TOLERANCE = 0.02          # summed |difference| that counts as "the mask changed this pixel"


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0


def opaque(picture: np.ndarray, background: np.ndarray) -> np.ndarray:
    return np.abs(picture - background).sum(axis=2) > OPAQUE_TOLERANCE


def state_labels(picture: np.ndarray, background: np.ndarray,
                 mask: np.ndarray, tolerance: float = 0.10) -> np.ndarray:
    """1 = charted, 2 = unexplored, 0 = neither (background or an unrecognised colour)."""
    charted = CHARTED * CHARTED_ALPHA + background * (1.0 - CHARTED_ALPHA)
    unexplored = UNEXPLORED
    to_charted = np.abs(picture - charted).sum(axis=2)
    to_unexplored = np.abs(picture - unexplored).sum(axis=2)
    labels = np.where(to_charted <= to_unexplored, 1, 2)
    closest = np.minimum(to_charted, to_unexplored)
    return np.where(mask & (closest <= tolerance), labels, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-on', required=True)
    parser.add_argument('--python-off', required=True)
    parser.add_argument('--native-on', required=True)
    parser.add_argument('--native-off', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()

    py_on, py_off = load(args.python_on), load(args.python_off)
    na_on, na_off = load(args.native_on), load(args.native_off)
    if py_on.shape != na_on.shape:
        raise SystemExit(f'frame sizes differ: {py_on.shape} vs {na_on.shape}')

    py_bg, na_bg = py_off[2, 2], na_off[2, 2]
    py_opaque = opaque(py_on, py_bg)
    na_opaque = opaque(na_on, na_bg)
    # The native window's top rows carry its debug text, which is not fog.
    rows = slice(100, py_on.shape[0])
    py_opaque[:100, :] = False
    na_opaque[:100, :] = False

    py_labels = state_labels(py_on, py_bg, py_opaque)
    na_labels = state_labels(na_on, na_bg, na_opaque)

    union = py_opaque | na_opaque
    inter = py_opaque & na_opaque
    both = inter & (py_labels > 0) & (na_labels > 0)
    agreement = float((py_labels[both] == na_labels[both]).mean()) if both.any() else None

    def census(mask: np.ndarray) -> dict:
        total = int(mask.sum())
        charted = int((py_labels[mask] == 1).sum()) if mask is py_opaque \
            else int((na_labels[mask] == 1).sum())
        return {'opaque_pixels': total, 'charted_pixels': charted,
                'unexplored_pixels': total - charted}

    report = {
        'python': census(py_opaque),
        'native': census(na_opaque),
        'footprint': {'union': int(union.sum()), 'intersection': int(inter.sum()),
                      'iou': round(int(inter.sum()) / int(union.sum()), 4) if union.any() else None,
                      'only_python': int((py_opaque & ~na_opaque).sum()),
                      'only_native': int((na_opaque & ~py_opaque).sum())},
        'state_agreement': {'agreement': round(agreement, 4) if agreement is not None else None,
                            'compared_pixels': int(both.sum()),
                            'disagreeing_pixels': int((py_labels[both] != na_labels[both]).sum())
                            if both.any() else 0},
        'background': {'python': [round(float(v), 4) for v in py_bg],
                       'native': [round(float(v), 4) for v in na_bg]},
        'note': 'the two renderers clear to different colours, so every comparison is made against '
                'each side\'s own background; the native window\'s top 100 rows are excluded '
                'because they carry debug text',
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            handle.write(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
