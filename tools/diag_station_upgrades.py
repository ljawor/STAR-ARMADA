"""Acceptance probe for the station refit panel added in #77.

Renders the station panel in each state the feature has — as-built, mid-ladder,
refit pending, and at the cap, where the panel must offer no button — plus a
planet-built hull for contrast, saves the HUD overlay as PNGs for visual
inspection, and checks the geometry the tests assert: the refit control sits
inside its panel and no two controls overlap.

Usage: python tools/diag_station_upgrades.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from game.core.vectors import Vec3  # noqa: E402
from game.systems import upgrades  # noqa: E402
from helpers import make_game  # noqa: E402
from render.camera import Camera  # noqa: E402
from render.hud import HUD  # noqa: E402
from render.input import InputController  # noqa: E402


def fund(player, amount=100000):
    player.credits = player.materials = player.energy = player.crew = amount


def world():
    gm = make_game(ai=False)
    state = gm.state
    fund(state.players[0])
    observer = next(e for e in state.entities.values() if e.owner == 0 and e.is_ship)
    yard = gm.factory.spawn_station('shipyard', 0, observer.pos + Vec3(0, 0, 400))
    platform = gm.factory.spawn_station('defense_platform', 0, observer.pos + Vec3(0, 0, 900))
    mine = gm.factory.spawn_station('mining_station', 0, observer.pos + Vec3(0, 0, 1400))
    planet = next(e for e in state.entities.values() if e.data_id == 'temperate')
    planet.colonized_by = 0
    from game.systems.planet_buildings import start_building
    start_building(gm.construction, planet.id, 'planet_extractor', 0)
    for _ in range(1, 5000):
        gm.step(1 / 30)
        if any(e.data_id == 'planet_extractor' for e in state.entities.values()):
            break
    extractor = next(e for e in state.entities.values() if e.data_id == 'planet_extractor')
    return gm, yard, platform, mine, extractor


def cases(gm, yard, platform, mine):
    # as built: the button and its price
    yield 'as_built', yard, 1, 0
    # mid ladder: the accumulated effects line
    platform.upgrade_level = 3
    yield 'mid_ladder', platform, 1, 0
    # refit pending: the timer and the cancel row, and no second purchase
    gm.construction.start_upgrade(yard.id, 0)
    yield 'refit_pending', yard, 0, 1
    gm.construction.cancel_build(yard.id, 0, 0)
    # at the cap: the level line and its effects, and no button left to press
    mine.upgrade_level = 5
    yield 'at_cap', mine, 0, 0


def measure(hud, label, out_dir, expect_refit, expect_cancel):
    panel = hud.blocked_rects[0] if hud.blocked_rects else None
    refit = [b for b in hud.buttons if b['kind'] == 'upgrade_station']
    cancels = [b for b in hud.buttons if b['kind'] == 'cancel_build']
    rects = [pygame.Rect(b['rect']) for b in refit + cancels]
    report = {
        'panel': label,
        'panel_rect': list(panel) if panel else None,
        'refit_buttons': [{'rect': list(b['rect']), 'payload': dict(b['payload'])}
                          for b in refit],
        'cancel_buttons': [{'rect': list(b['rect']), 'payload': dict(b['payload'])}
                           for b in cancels],
        'checks': {
            'expected_refit_button': bool(refit) == bool(expect_refit),
            'expected_cancel_row': bool(cancels) == bool(expect_cancel),
            'all_inside_panel': all(panel is None or panel.contains(r) for r in rects),
            'no_overlap': not any(a.colliderect(b) for i, a in enumerate(rects)
                                  for b in rects[i + 1:]),
        },
    }
    path = os.path.join(out_dir, f'refit_{label}.png')
    pygame.image.save(hud.overlay, path)
    report['png'] = path
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=os.path.expanduser('~/.hermes/cache/scratch/refit77'))
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    gm, yard, platform, mine, extractor = world()
    rows = []
    for size in ((1280, 800), (1024, 768)):
        hud = HUD(*size, gm.state)
        ctrl = InputController(gm.state, Camera(*size), hud,
                               SimpleNamespace(flash=lambda *_: None))
        for label, station, refit, cancel in cases(gm, yard, platform, mine):
            ctrl.selection = {station.id}
            hud.buttons.clear(); hud.blocked_rects.clear(); hud.scroll_rects.clear()
            hud._right_panel(ctrl.selection, 0)
            rows.append(measure(hud, f'{label}_{size[0]}x{size[1]}', args.out, refit, cancel))
        # planet-built hardware must get no refit block at all
        ctrl.selection = {extractor.id}
        hud.buttons.clear(); hud.blocked_rects.clear(); hud.scroll_rects.clear()
        hud._right_panel(ctrl.selection, 0)
        rows.append(measure(hud, f'planet_built_{size[0]}x{size[1]}', args.out, 0, 0))

    print(json.dumps({
        'ladder': {kind: {'L2 cost': upgrades.upgrade_cost(_stub(kind)),
                          'L2 seconds': upgrades.upgrade_time(_stub(kind))}
                   for kind in ('shipyard', 'defense_platform', 'trade_station')},
        'panels': rows}, indent=1))
    bad = [r for r in rows if not all(r['checks'].values())]
    print('OK: every refit control sits inside its panel, none overlap, and only '
          'yard stations offer one' if not bad
          else f'FAIL: {len(bad)} panel(s) failed a geometry check')
    return 1 if bad else 0


def _stub(kind):
    """A level-1 stand-in for the ladder printout (no live entity needed)."""
    gm = make_game(ai=False)
    observer = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
    return gm.factory.spawn_station(kind, 0, observer.pos + Vec3(0, 0, 400))


if __name__ == '__main__':
    sys.exit(main())
