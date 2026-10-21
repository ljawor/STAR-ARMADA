"""Encode the colony-dome fixture through the real producer.

The records are built by `render.emissive_batch.PlanetDomes` from a two-entity state (a planet and
its surface generator), encoded with the live codec and published into a one-slot ring the viewer
drains with `--emit-ring`. Two scenes:

* `domes-full.ring`  - a full field, one pass;
* `domes-flash.ring` - the frame after a hit, where the renderer draws the same additive shell
  three times, so the producer publishes three identical records.

Run: PYTHONPATH=. .venv/bin/python tools/render/write_dome_fixtures.py --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import game.core.manager as _manager                       # noqa: E402,F401  (import order)
from render import emissive_batch                          # noqa: E402
from render_bridge import emissive as codec                # noqa: E402
from render_bridge import ring                            # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools", "render"))
import dome_scene                                          # noqa: E402


def vec(point):
    return types.SimpleNamespace(x=point[0], y=point[1], z=point[2])


class Planet:
    def __init__(self) -> None:
        self.id = 11
        self.alive = True
        self.operational = True
        self.data_id = "planet"
        self.is_planet = True
        self.is_ship = False
        self.is_squadron = False
        self.radius = dome_scene.RADIUS
        self.colonized_by = "imperial"
        self.pos = vec(dome_scene.PLANET)


class Generator:
    def __init__(self, held: float) -> None:
        self.id = 21
        self.alive = True
        self.operational = True
        self.data_id = "planet_shield_generator"
        self.planet_id = 11
        self.owner = "imperial"
        self.pos = vec(dome_scene.PLANET)
        self._capacity = 400.0
        self._held = held

    def max_shield_total(self) -> float:
        return self._capacity

    def total_shield(self) -> float:
        return self._held


class State:
    def __init__(self, *entities) -> None:
        self.entities = {e.id: e for e in entities}

    def entity(self, eid):
        return self.entities.get(eid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    planet = Planet()
    full = Generator(dome_scene.STRENGTH * 400.0)
    domes = emissive_batch.PlanetDomes()
    one_pass = domes.step(State(planet, full), 1.0 / 60.0)

    # The hit: the generator's pool drops, so the next frame pulses.
    hit = Generator(dome_scene.HIT_STRENGTH * 400.0)
    pulse = emissive_batch.PlanetDomes()
    pulse.step(State(planet, full), 1.0 / 60.0)
    three_pass = pulse.step(State(planet, hit), 1.0 / 60.0)

    written = {}
    # The viewer drains a ring, so each scene is published as one batch - the same bytes a live
    # producer would write, not a bare blob.
    for name, records in (("domes-full.ring", one_pass), ("domes-flash.ring", three_pass)):
        path = os.path.join(args.out, name)
        blob = bytes(codec.encode(records))
        with ring.Ring.create(path, slots=4, slot_bytes=max(1024, len(blob) + 64)) as out:
            out.publish(blob)
        written[name] = len(records)

    report = {
        "synthetic": True,
        "planet": list(dome_scene.PLANET),
        "planet_radius": dome_scene.RADIUS,
        "dome_radius": dome_scene.DOME_RADIUS,
        "full": {"records": len(one_pass), "colour": list(one_pass[0]["colour"]) if one_pass else None},
        "flash": {"records": len(three_pass),
                  "colour": list(three_pass[0]["colour"]) if three_pass else None},
        "rings": written,
        "note": "a colony dome crosses as the same kind-6 record a ship bubble uses; the pulse is "
                "the renderer's repeated additive pass, published as repeated records",
    }
    with open(os.path.join(args.out, "domes.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps(written, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
