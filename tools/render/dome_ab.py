"""Stitch the colony-dome reference and the native frame into one A/B sheet.

Run: PYTHONPATH=. .venv/bin/python tools/render/dome_ab.py --python-full F --native-full F         --python-pulse F --native-pulse F --out FILE
"""
from __future__ import annotations

import argparse

from PIL import Image, ImageDraw

CROP = (280, 60, 1000, 780)           # the shell, without the frame's empty margins


def sheet(paths: list[str], labels: list[str], columns: int) -> Image.Image:
    crops = [Image.open(path).convert("RGB").crop(CROP) for path in paths]
    width, height = crops[0].size
    sheet = Image.new("RGB", (width * columns, height * 2), (8, 10, 16))
    draw = ImageDraw.Draw(sheet)
    for index, (crop, label) in enumerate(zip(crops, labels)):
        column, row = index % columns, index // columns
        sheet.paste(crop, (column * width, row * height))
        draw.text((column * width + 12, row * height + 10), label, fill=(150, 210, 255))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-full", required=True)
    parser.add_argument("--native-full", required=True)
    parser.add_argument("--python-pulse", required=True)
    parser.add_argument("--native-pulse", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    sheet([args.python_full, args.native_full, args.python_pulse, args.native_pulse],
          ["python  full field", "window  full field",
           "python  after a hit", "window  after a hit"], 2).save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
