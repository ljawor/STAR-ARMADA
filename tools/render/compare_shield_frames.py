"""Compare the native shield shells against the Python reference frame.

Both frames are the same four bubbles at the same camera. The shells are additive and faint by
design (a 0.001 interior wash and an 0.18 rim), and the native frame also carries the fleet, so the
comparison works on COLOURED blobs: the shells carry hue, the hulls are grey and the HUD text is
excluded by a row band. Each frame is labelled into connected coloured regions, blobs are matched
left to right, and each pair is compared on centroid, radius and rim colour.

Every number here is a measurement of two PNGs, not of intent.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0


def background(pixels):
    """Each renderer's own clear colour, taken from the frame's border.

    The two renderers do not share a clear colour (the window clears to a dark blue), so every
    measurement is expressed as a delta from that frame's own background. Comparing absolute
    brightness would confuse exposure with signal.
    """
    border = np.concatenate([pixels[:8].reshape(-1, 3), pixels[-8:].reshape(-1, 3),
                             pixels[:, :8].reshape(-1, 3), pixels[:, -8:].reshape(-1, 3)])
    return np.median(border, axis=0)


def signal(pixels, bg, threshold=0.006):
    """Where this frame carries light the shells added, measured against its own background."""
    delta = pixels - bg
    return (delta.max(axis=2) > threshold) & (delta.min(axis=2) > -0.02)


def label_blobs(mask, min_pixels=400):
    """Connected components of a boolean mask, 4-connected, without pulling in scipy.

    Small blobs are dropped: the native frame also contains hulls, each of which adds a few dozen
    lit pixels above the background, while a shell is thousands.
    """
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    blobs = []
    for y0 in range(height):
        for x0 in range(width):
            if not mask[y0, x0] or seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            pixels = []
            while stack:
                y, x = stack.pop()
                pixels.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(pixels) >= min_pixels:
                ys = np.array([p[0] for p in pixels])
                xs = np.array([p[1] for p in pixels])
                blobs.append({'pixels': pixels, 'rows': ys, 'cols': xs})
    blobs.sort(key=lambda b: float(b['cols'].mean()))
    return blobs


def describe(pixels, blob, colour):
    rows, cols = blob['rows'], blob['cols']
    # radius as the equivalent-area circle
    radius = float(np.sqrt(len(rows) / np.pi))
    patch = colour[rows, cols]
    bg = background(colour)
    patch = np.clip(patch - bg, 0.0, None)     # light the shells added, over their own background
    lum = patch.max(axis=1)
    rim = patch[lum >= np.percentile(lum, 90)] if lum.size else patch
    return {
        'centre': [round(float(cols.mean()), 1), round(float(rows.mean()), 1)],
        'radius_px': round(radius, 1),
        'coloured_pixels': int(len(rows)),
        'energy': round(float(lum.sum()), 3),
        'mean_rgb': [round(float(v), 5) for v in patch.mean(axis=0)],
        'rim_rgb': [round(float(v), 5) for v in rim.mean(axis=0)] if rim.size else [0, 0, 0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--native', required=True)
    parser.add_argument('--out')
    parser.add_argument('--band', type=int, nargs=2, default=[180, 700],
                        help='rows to consider, so HUD text is excluded from both frames')
    args = parser.parse_args()

    py = load(args.python)
    native = load(args.native)
    if py.shape != native.shape:
        raise SystemExit(f'size mismatch: {py.shape} vs {native.shape}')
    band = slice(args.band[0], args.band[1])

    py_bg, native_bg = background(py), background(native)
    py_blobs = label_blobs(signal(py[band], py_bg))
    native_blobs = label_blobs(signal(native[band], native_bg))

    report = {'band': args.band, 'python_blobs': [], 'native_blobs': [], 'pairs': [],
              'background': {'python': [round(float(v), 5) for v in py_bg],
                             'native': [round(float(v), 5) for v in native_bg]}}
    py_described = [describe(py[band], b, py[band]) for b in py_blobs]
    native_described = [describe(native[band], b, native[band]) for b in native_blobs]
    report['python_blobs'] = py_described
    report['native_blobs'] = native_described

    # The native frame also contains hulls, each a small blob of its own, so a pair is the native
    # blob closest to the Python blob's centroid - not the next one in x order.
    used = set()
    for index, py_blob in enumerate(py_described):
        best, best_distance = None, None
        for candidate_index, candidate in enumerate(native_described):
            if candidate_index in used:
                continue
            distance = ((candidate['centre'][0] - py_blob['centre'][0]) ** 2 +
                        (candidate['centre'][1] - py_blob['centre'][1]) ** 2) ** 0.5
            if best_distance is None or distance < best_distance:
                best, best_distance = candidate_index, distance
        if best is None:
            continue
        used.add(best)
        native_blob = native_described[best]
        report['pairs'].append({
            'index': index,
            'match_distance_px': round(best_distance, 2),
            'python': py_blob,
            'native': native_blob,
            'radius_ratio': (round(native_blob['radius_px'] / py_blob['radius_px'], 3)
                             if py_blob['radius_px'] else 0.0),
            'centre_offset_px': [round(native_blob['centre'][0] - py_blob['centre'][0], 1),
                                 round(native_blob['centre'][1] - py_blob['centre'][1], 1)],
            'energy_ratio': (round(native_blob['energy'] / py_blob['energy'], 3)
                             if py_blob['energy'] else 0.0),
            'rim_hue_match': [round(native_blob['rim_rgb'][c] / py_blob['rim_rgb'][c], 3)
                              if py_blob['rim_rgb'][c] else 0.0 for c in range(3)],
        })
    report['blob_count'] = {'python': len(py_described), 'native': len(native_described)}
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
