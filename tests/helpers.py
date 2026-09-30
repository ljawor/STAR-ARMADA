"""Shared test fixtures: headless GameManager instances."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.core.manager import GameManager  # noqa: E402
from game.data.store import DataStore  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_game(ticks_setup: bool = True, ai: bool = True) -> GameManager:
    DataStore.reset()
    with open(os.path.join(ROOT, "assets/data/maps/skirmish01.json")) as f:
        map_def = json.load(f)
    if not ai:
        map_def["players"][1]["is_ai"] = False
    return GameManager.start_skirmish(map_def)


def run_for(gm: GameManager, seconds: float, dt: float = 1 / 30) -> None:
    steps = int(seconds / dt)
    for _ in range(steps):
        gm.step(dt)


def order_build(gm: GameManager, builder, kind: str, pos, player: int = 0) -> bool:
    """Order a station build from a builder already AT the site.

    A station may only be sited within `economy.station_build_range` of the
    builder, so a constructor has to travel to a distant site before the build
    is accepted (the AI does this itself — see AIPlayer._pending_site). Tests
    that care about construction mechanics rather than pathing put the builder
    on site first; the range rule itself is covered by
    tests/test_planet_economy.py and tests/test_construction_range.py.
    """
    from game.core.vectors import Vec3
    builder.pos = pos.copy() if isinstance(pos, Vec3) else Vec3(*pos)
    builder.order_type = "idle"
    builder.order_target_pos = None
    return gm.construction.start_station(builder.id, kind, pos, player)