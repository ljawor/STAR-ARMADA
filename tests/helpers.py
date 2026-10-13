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


def run_until(gm: GameManager, predicate, limit_seconds: float = 600.0,
              dt: float = 1 / 30) -> float:
    """Tick until `predicate()` holds; raise if it never does within the limit.

    Tests wait on the delivered condition rather than a hardcoded number of
    seconds, so content pacing can change (surface build time is derived from
    cost — #95) without silently weakening what the test checks. Returns the
    elapsed simulated seconds.
    """
    steps = int(limit_seconds / dt)
    for step in range(steps):
        if predicate():
            return step * dt
        gm.step(dt)
    if predicate():
        return steps * dt
    raise AssertionError(f'condition not met within {limit_seconds:g}s')


def queue_detected_human_attack(gm: GameManager, player: int, unit_ids, target_id: int) -> None:
    """Submit fresh human intent through the serialized production command seam.

    Destruction fixtures call this again only AFTER combat abandons the target;
    the initial operational-target order cannot authorize finishing a derelict.
    """
    from game.core.commands import AttackCommand, PlayerCommand
    if gm.state.players[player].is_ai or not gm.state.can_see(player, target_id):
        raise AssertionError('an explicit human attack requires a currently detected target')
    command = AttackCommand(player, unit_ids, target_id)
    gm.state.queue_command(PlayerCommand.from_dict(json.loads(json.dumps(command.to_dict()))))


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