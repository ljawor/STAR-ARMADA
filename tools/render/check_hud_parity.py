"""Prove the C++ window presents the HUD Python composed, pixels and all.

The viewer decodes the overlay ring, patches a texture and captures that texture offscreen with
blending off (``--hud-dump``). This replays the same ring in Python, applies the same patches, and
compares the result with the dump byte for byte, row for row.

What it proves: the native decoder plus ``updateTexture2D`` patch path produces the surface the
Python producer published. What it does not prove: that the picture is drawn over the 3D scene at
the right size (that is the screenshot's job) or anything about frame rate.

    PYTHONPATH=.:tests .venv/bin/python tools/render/check_hud_parity.py \
        --ring hud.bin --dump hud.png --report viewer.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zlib
from pathlib import Path

from render_bridge import overlay, ring


def replay(ring_path: Path, sequence: int):
    """Apply published overlay frames in order, exactly as the window does."""
    reader = ring.Ring.open(ring_path, writable=False)
    surface = None
    applied = 0
    keyframes = 0
    size = (0, 0)
    try:
        published = reader.published
        # The window a window could still have read: the ring only holds the newest `slots`
        # frames, and the producer may have moved far past the reported sequence by now.
        first = max(0, sequence + 1 - reader.slots)
        for seq in range(first, min(published, sequence + 1)):
            payload = reader.read(seq)
            if payload is None:
                continue
            frame = overlay.decode(payload[1])
            width, height = frame['width'], frame['height']
            if surface is None:
                if not frame['full']:
                    # The window also refuses patches before a keyframe.
                    continue
                surface = bytearray(width * height * 4)
                size = (width, height)
            if frame['full']:
                surface[:] = frame['payload']
            else:
                payload_bytes = frame['payload']
                offset = 0
                for x, y, w, h in frame['rects']:
                    for row in range(h):
                        start = ((y + row) * width + x) * 4
                        surface[start:start + w * 4] = payload_bytes[offset:offset + w * 4]
                        offset += w * 4
            applied += 1
            keyframes += 1 if frame['full'] else 0
        info = {'published': published, 'applied': applied, 'keyframes': keyframes,
                'width': size[0], 'height': size[1]}
    finally:
        reader.close()
    return surface, info


def dump_rgb(path: Path):
    """The dump is a PNG of the texture; read it back without trusting our own writer."""
    import pygame

    image = pygame.image.load(str(path))
    width, height = image.get_size()
    raw = pygame.image.tobytes(image, 'RGB')
    return width, height, raw


def compare(surface, width: int, height: int, rgb: bytes):
    """Compare RGB channels; the dump PNG carries no alpha, so alpha stays out of the comparison."""
    rows = 0
    differing_pixels = 0
    first = None
    for y in range(height):
        row_surface = surface[y * width * 4:(y + 1) * width * 4]
        row_dump = rgb[y * width * 3:(y + 1) * width * 3]
        if row_surface[0::4] == row_dump[0::3] and row_surface[1::4] == row_dump[1::3] \
                and row_surface[2::4] == row_dump[2::3]:
            rows += 1
            continue
        for x in range(width):
            a = row_surface[x * 4:x * 4 + 3]
            b = row_dump[x * 3:x * 3 + 3]
            if a != b:
                differing_pixels += 1
                if first is None:
                    first = {'x': x, 'y': y, 'surface': list(a), 'dump': list(b)}
    return {'identical_rows': rows, 'rows': height, 'differing_pixels': differing_pixels,
            'first_difference': first}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ring', type=Path, required=True)
    parser.add_argument('--dump', type=Path, required=True)
    parser.add_argument('--report', type=Path, help='viewer report; its hud.applied_sequence is replayed')
    parser.add_argument('--sequence', type=int, help='override the reported sequence')
    parser.add_argument('--window', type=int, default=2,
                        help='frames of capture latency to tolerate on each side (default 2)')
    parser.add_argument('--json', type=Path, help='write the result here')
    args = parser.parse_args(argv)

    sequence = args.sequence
    if sequence is None:
        if args.report is None:
            raise SystemExit('pass --report (viewer) or --sequence')
        view = json.loads(args.report.read_text())
        hud = view['hud']
        if hud['decode_failures']:
            raise SystemExit(f"window reported {hud['decode_failures']} decode failures")
        # The screenshot is of the frame it was requested on; the window keeps applying HUD
        # frames until it exits, so the later applied_sequence describes a different picture.
        sequence = int(hud.get('screenshot_sequence') or hud['applied_sequence'])

    surface, info = replay(args.ring, sequence)
    if surface is None:
        raise SystemExit('no keyframe in the replayed range: the window would show nothing')
    width, height, rgb = dump_rgb(args.dump)
    result = {
        'ring': str(args.ring),
        'dump': str(args.dump),
        'sequence': sequence,
        'replay': info,
        'surface_sha256': hashlib.sha256(surface).hexdigest(),
        'dump_crc32': zlib.crc32(rgb) & 0xFFFFFFFF,
        'surface_rgb_crc32': zlib.crc32(bytes(surface[i] for i in range(len(surface))
                                             if i % 4 != 3)) & 0xFFFFFFFF,
    }
    if (width, height) != (info['width'], info['height']):
        raise SystemExit(f'dump is {width}x{height}; the ring carries {info["width"]}x'
                         f'{info["height"]} frames')
    # bgfx delivers a capture a frame or two after the request, so allow a small window and
    # report exactly which sequence the presented picture belongs to.
    candidates = {}
    for offset in range(-args.window, args.window + 1):
        seq = sequence + offset
        if seq < 0:
            continue
        candidate_surface, _ = replay(args.ring, seq)
        if candidate_surface is None:
            continue
        candidates[seq] = compare(candidate_surface, width, height, rgb)['differing_pixels']
    best = min(candidates, key=lambda s: (candidates[s], abs(s - sequence))) if candidates else sequence
    surface, info = replay(args.ring, best)
    result['sequence'] = best
    result['replay'] = info
    result['surface_sha256'] = hashlib.sha256(surface).hexdigest()
    result['surface_rgb_crc32'] = zlib.crc32(bytes(surface[i] for i in range(len(surface))
                                                 if i % 4 != 3)) & 0xFFFFFFFF
    result['window'] = {'searched': sorted(candidates), 'differing_pixels': candidates,
                        'best_sequence': best, 'offset': best - sequence}
    result['comparison'] = compare(surface, width, height, rgb)
    result['identical'] = result['comparison']['differing_pixels'] == 0
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return 0 if result['identical'] else 1


if __name__ == '__main__':
    sys.exit(main())
