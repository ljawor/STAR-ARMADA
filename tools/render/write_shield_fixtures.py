"""Write a shield-shell fixture through the real bridge encoder.

The fixture exists so the C++ side can be exercised without a running simulation, and so a capture
can be compared against a Python reference of the same shell. It holds three bubbles at different
strengths - full, half and nearly spent - plus one station, because those are the four things that
can go wrong: the hue ramp, the fade alpha, the station radius factor and the readability floor.
"""
from __future__ import annotations

import argparse
import os
import sys

from render import emissive_batch
from render_bridge import emissive, ring


class Shell:
    """The subset of a unit that `emissive_batch.shields` reads."""

    def __init__(self, uid, pos, radius, fraction, capacity=400.0, station=False):
        self.id = uid
        self.pos = pos
        self.radius = radius
        self.is_station = station
        self.is_ship = not station
        self.is_squadron = False
        self.is_planet = False
        self.planet_building_slot = None
        self.alive = True
        self.shields = {q: capacity * fraction for q in emissive_batch.QUADRANTS}
        self._max = {q: capacity for q in emissive_batch.QUADRANTS}

    def max_shield_total(self):
        return sum(self._max.values())


def units():
    return [
        # Lifted well above the ecliptic so a capture holds the bubbles and no hulls: a hull in the
        # window would be brighter than the rim and make the measurement meaningless.
        Shell(1, _vec(-1400.0, 6000.0, 0.0), 60.0, 1.00),
        Shell(2, _vec(0.0, 6000.0, 0.0), 60.0, 0.50),
        Shell(3, _vec(1400.0, 6000.0, 0.0), 60.0, 0.06),
        Shell(4, _vec(2800.0, 6000.0, 0.0), 220.0, 0.75, station=True),
    ]


def _vec(x, y, z):
    import types
    return types.SimpleNamespace(x=x, y=y, z=z)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='render_cpp/tests/fixtures/shield')
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    records = emissive_batch.shields(units(), lambda u: u.radius)
    blob = emissive.encode(records)
    path = os.path.join(args.out, 'shields.bin')
    with open(path, 'wb') as handle:
        handle.write(blob)
    print(f'{path}: {len(records)} shells, {len(blob)} bytes')
    # The viewer reads a ring, the C++ test reads the bare blob; both are written from one encode so
    # they cannot drift.
    ring_path = os.path.join(args.out, 'shields.ring')
    with ring.Ring.create(ring_path, slots=4, slot_bytes=max(1024, len(blob) + 64)) as out:
        out.publish(blob)
    print(f'{ring_path}: one published batch')
    for record in records:
        print(f"  id-less record centre={record['a']} radius={record['radius']:.3f} "
              f"fraction={record['width']:.3f} colour={record['colour']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
