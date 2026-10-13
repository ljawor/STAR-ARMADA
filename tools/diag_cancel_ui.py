"""Acceptance probe for the cancel affordance added in #94.

Renders the two panels that carry the new control — a station's ship-production
queue and a colony's paid surface-slot grid — at both supported resolutions,
saves the HUD overlay as a PNG for visual inspection, and checks the geometry
the tests assert: every cancel button lies inside its panel, no two of them
overlap (a click must be unambiguous), and the count matches what is queued.

Usage: python tools/diag_cancel_ui.py [--out DIR]
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
from game.systems.planet_buildings import building_time, start_building  # noqa: E402
from helpers import make_game  # noqa: E402
from render.camera import Camera  # noqa: E402
from render.hud import HUD  # noqa: E402
from render.input import InputController  # noqa: E402

QUEUE = (('imperial_corvette', 2), ('imperial_cruiser', 1))


def build_world(gm):
    state = gm.state
    player = state.players[0]
    player.credits = player.materials = player.energy = player.crew = 100000
    observer = next(e for e in state.entities.values() if e.owner == 0 and e.is_ship)
    yard = gm.factory.spawn_station('shipyard', 0, observer.pos + Vec3(0, 0, 200))
    for ship_id, count in QUEUE:
        gm.construction.start_ship(yard.id, ship_id, 0, count)
    planet = next(e for e in state.entities.values() if e.data_id == 'temperate')
    planet.colonized_by = 0
    observer.pos = planet.pos.copy()
    start_building(gm.construction, planet.id, 'planet_pulsar_cannon', 0)
    start_building(gm.construction, planet.id, 'planet_extractor', 0)
    return yard, planet


def measure(hud, label, out_dir, expected):
    rows = [b for b in hud.buttons if b['kind'] == 'cancel_build']
    panel = hud.blocked_rects[0] if hud.blocked_rects else None
    report = {'panel': label, 'panel_rect': list(panel) if panel else None,
              'expected_controls': expected, 'buttons': [], 'checks': {}}
    for index, button in enumerate(rows):
        rect = pygame.Rect(button['rect'])
        report['buttons'].append({'index': index, 'rect': list(rect),
                                  'payload': dict(button['payload']),
                                  'inside_panel': bool(panel is None or panel.contains(rect))})
    rects = [pygame.Rect(b['rect']) for b in report['buttons']]
    report['checks'] = {
        'count_matches_queue': len(rows) == expected,
        'all_inside_panel': all(b['inside_panel'] for b in report['buttons']),
        'no_overlap': not any(a.colliderect(b) for i, a in enumerate(rects)
                              for b in rects[i + 1:]),
    }
    path = os.path.join(out_dir, f'cancel_ui_{label}.png')
    pygame.image.save(hud.overlay, path)
    report['png'] = path
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=os.path.expanduser('~/.hermes/cache/scratch/cancel94'))
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    queued = sum(count for _, count in QUEUE)
    reports = []
    for size in ((1280, 800), (1024, 768)):
        gm = make_game(ai=False)
        yard, planet = build_world(gm)
        hud = HUD(*size, gm.state)
        ctrl = InputController(gm.state, Camera(*size), hud,
                               SimpleNamespace(flash=lambda *_: None))
        for label, selection, page, expected in (
                (f'station_{size[0]}x{size[1]}', {yard.id}, None, queued),
                (f'colony_{size[0]}x{size[1]}', {planet.id}, 'surface', 2)):
            if page is not None:
                hud.planet_page = page
            ctrl.selection = selection
            hud.buttons.clear(); hud.blocked_rects.clear(); hud.scroll_rects.clear()
            hud._right_panel(selection, 0)
            reports.append(measure(hud, label, args.out, expected))

    print(json.dumps({
        'derived_times': {k: building_time(k) for k in
                          ('planet_extractor', 'planet_trade_hub',
                           'planet_shield_generator', 'planet_pulsar_cannon')},
        'panels': reports}, indent=1))
    bad = [r for r in reports if not all(r['checks'].values())]
    print('OK: cancel controls sit inside their panel, do not overlap, and match the queue'
          if not bad else f'FAIL: {len(bad)} panel(s) failed a geometry check')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
