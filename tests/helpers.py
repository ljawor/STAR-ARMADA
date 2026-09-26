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