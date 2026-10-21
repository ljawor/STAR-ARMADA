"""A/B sheet: the same building drawn by the Python renderer and by the native window.

The two cameras do not agree - the window's projection passes degrees where `bx::mtxProj` wants
radians, so its vertical field of view is ~88 degrees against the renderer's 55 - which means the
building is framed larger in one than the other. That rules out a pixel-for-pixel overlay and it is
why the parity claim for this slice rests on `compare_hardware_geometry.py` (7,500 vertices, zero
mismatches) instead. This sheet is for the eye: same silhouette, same roles, same lights.

Run: PYTHONPATH=. .venv/bin/python tools/render/hardware_ab.py --python A.png --native B.png --out C.png
"""
from __future__ import annotations

import argparse

from PIL import Image, ImageDraw


def crop(path: str, box: tuple) -> Image.Image:
    image = Image.open(path).convert('RGB')
    left, top, right, bottom = box
    return image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))


def label(image: Image.Image, text: str) -> Image.Image:
    strip = Image.new('RGB', (image.width, 22), (12, 14, 18))
    ImageDraw.Draw(strip).text((6, 6), text, fill=(210, 216, 224))
    out = Image.new('RGB', (image.width, image.height + 22), (12, 14, 18))
    out.paste(strip, (0, 0))
    out.paste(image, (0, 22))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--native', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--size', type=int, default=320, help='side of each square crop')
    parser.add_argument('--python-box', default='523,279,744,448',
                        help='the building in the Python frame, left,top,right,bottom')
    parser.add_argument('--native-box', default='520,270,760,450')
    args = parser.parse_args()

    panels = [
        label(crop(args.python, tuple(int(v) for v in args.python_box.split(',')))
              .resize((args.size, args.size), Image.LANCZOS), 'python renderer (55 deg vfov)'),
        label(crop(args.native, tuple(int(v) for v in args.native_box.split(',')))
              .resize((args.size, args.size), Image.LANCZOS), 'native window (88 deg vfov)'),
    ]
    sheet = Image.new('RGB', (args.size * 2, args.size + 22), (12, 14, 18))
    for index, panel in enumerate(panels):
        sheet.paste(panel, (index * args.size, 0))
    sheet.save(args.out)
    print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
