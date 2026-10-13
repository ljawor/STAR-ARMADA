"""Acceptance probe for the language packs (#93).

Renders the menu screens in English, German and Polish and the in-game station panel in
each language, and checks the things a translation can plausibly break:

* **geometry is language-independent** — every button rect on a screen is identical in all
  three packs, so a longer German label can never move a control;
* **nothing is silently truncated** — a translated label must not end in the ellipsis the
  canvas draws when a string does not fit where English fits;
* **every string the HUD asks to translate exists in the catalogue** — a recorded lookup
  wrapper proves the drawing edges are actually being exercised (a screen that drew
  English because nobody called `t()` would otherwise pass every other check).

Usage: python tools/diag_i18n.py [--out DIR]
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame  # noqa: E402

from render import hud as hud_module  # noqa: E402
from render import i18n, menus  # noqa: E402
from render.camera import Camera  # noqa: E402
from render.hud import HUD  # noqa: E402
from render.input import InputController  # noqa: E402
from game.core.vectors import Vec3  # noqa: E402
from helpers import make_game  # noqa: E402
from types import SimpleNamespace  # noqa: E402

SIZE = (1280, 800)

#: A resource bill has no catalogue entry: it is assembled from live numbers at the call
#: site. Anything else the UI asks to translate must be a catalogue key.
RUNTIME_BILL = re.compile(r'^[\d.,]+ (cr|mt|EN|crew|cmd)\b')


def catalogue_keys() -> set[str]:
    with open(os.path.join(i18n.LANG_DIR, 'en.json'), encoding='utf-8') as handle:
        data = json.load(handle)
    return set(data) | set(data.pop('names', {}) or {})


def screens(menu, code):
    """Every menu screen a player can be on, as (name, rendered_text, button rects)."""
    out = []
    for name, setup in (
        ('main', dict(screen='main')),
        ('settings_page0', dict(screen='settings', settings_page=0)),
        ('settings_language', dict(screen='settings', settings_page=3)),
        ('campaign', dict(screen='campaign', campaign_page=0)),
    ):
        for key, value in setup.items():
            setattr(menu, key, value)
        menu.buttons = []
        menu.render(0)
        prefix = 'settings' if name.startswith('settings') else name
        texts = list(getattr(menu, f'{prefix}_rendered_text', []))
        rects = sorted(tuple(b['rect']) for b in menu.buttons)
        png = os.path.join(OUT, f'menu_{name}_{code}.png')
        pygame.image.save(menu._surface, png)
        out.append({'screen': name, 'language': code, 'texts': texts, 'rects': rects,
                    'png': png})
    return out


def station_panel(code):
    """The station action panel (refit block included) with the pack active."""
    i18n.set_language(code)
    gm = make_game(ai=False)
    player = gm.state.players[0]
    player.credits = player.materials = player.energy = player.crew = 100000
    observer = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
    yard = gm.factory.spawn_station('shipyard', 0, observer.pos + Vec3(0, 0, 400))
    hud = HUD(*SIZE, gm.state)
    ctrl = InputController(gm.state, Camera(*SIZE), hud, SimpleNamespace(flash=lambda *_: None))
    ctrl.selection = {yard.id}
    hud.buttons.clear(); hud.blocked_rects.clear(); hud.scroll_rects.clear()
    requested: list[str] = []
    real_t = i18n.t

    @functools.wraps(real_t)
    def recorder(text, **fields):
        requested.append(text)
        return real_t(text, **fields)

    hud_module.i18n.t = recorder
    try:
        hud._right_panel(ctrl.selection, 0)
    finally:
        hud_module.i18n.t = real_t
    png = os.path.join(OUT, f'hud_station_{code}.png')
    pygame.image.save(hud.overlay, png)
    return {'language': code, 'requested': requested, 'png': png,
            'panel_rect': list(hud.blocked_rects[0]) if hud.blocked_rects else None}


def main() -> int:
    # Fixture isolation: the probe must never read or write the player's real settings.
    scratch = tempfile.TemporaryDirectory()
    saves = os.path.join(scratch.name, 'saves')
    os.makedirs(saves, exist_ok=True)
    for name, value in (('USER_DIR', scratch.name), ('SAVES_DIR', saves),
                        ('SETTINGS_PATH', os.path.join(saves, 'settings.json')),
                        ('CAMPAIGN_PATH', os.path.join(saves, 'campaign.json'))):
        setattr(menus, name, value)

    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=os.path.expanduser('~/.hermes/cache/scratch/i18n93'))
    args = parser.parse_args()
    global OUT
    OUT = args.out
    os.makedirs(OUT, exist_ok=True)

    pygame.display.init()
    keys = catalogue_keys()
    report: dict = {'screens': [], 'panels': [], 'checks': {}, 'coverage': i18n.coverage()}
    failures: list[str] = []

    menu = menus.MenuStack(*SIZE)
    for code, _label in i18n.LANGUAGES:
        menu.close()
        menu = menus.MenuStack(*SIZE)
        # The settings dict is the source of truth: `MenuStack.__init__` applies the
        # language from it, so a probe that only called `set_language` would be reset.
        menu.settings['language'] = code
        i18n.set_language(code)
        report['screens'].extend(screens(menu, code))
        report['panels'].append(station_panel(code))
    menu.close()

    by_screen: dict[str, list[dict]] = {}
    for row in report['screens']:
        by_screen.setdefault(row['screen'], []).append(row)
    for name, rows in by_screen.items():
        rects = {tuple(r['rects']) for r in rows}
        if len(rects) != 1:
            failures.append(f'{name}: button geometry differs between languages')
        english = next(r for r in rows if r['language'] == 'en')
        for row in rows:
            if row['language'] == 'en':
                continue
            extra_truncation = [t for t in row['texts']
                                if t.endswith('…') and t not in english['texts']]
            if extra_truncation:
                failures.append(f"{name}/{row['language']}: truncated by translation: "
                                f"{extra_truncation[:3]}")
            if not english['texts']:
                # The main menu draws through pygame, not the classic canvas: no text is
                # recorded, so compare the rendered pixels instead.
                if open(row['png'], 'rb').read() == open(english['png'], 'rb').read():
                    failures.append(f"{name}/{row['language']}: rendered identically to English")
            elif row['texts'] == english['texts']:
                failures.append(f"{name}/{row['language']}: drew the English strings")

    runtime_bills = set()
    for panel in report['panels']:
        unknown = []
        for text in panel['requested']:
            if text in keys or '{' in text:
                continue
            if RUNTIME_BILL.search(text):
                # A resource bill assembled at the call site ("1,050 cr · 1,200 mt").
                # Its units are still English; that is the one tracked follow-up, and
                # the count is reported rather than waved away.
                runtime_bills.add(text)
                continue
            unknown.append(text)
        if unknown:
            failures.append(f"hud/{panel['language']}: asked to translate strings that "
                            f"are not in the catalogue: {sorted(set(unknown))[:5]}")
        if panel['language'] != 'en' and not panel['requested']:
            failures.append(f"hud/{panel['language']}: the panel drew without a lookup")
    report['runtime_bills'] = sorted(runtime_bills)

    report['checks'] = {
        'runtime_bills_still_english': len(report['runtime_bills']),
        'catalogue_strings': len(keys),
        'geometry_identical': not any('geometry' in f for f in failures),
        'no_new_truncation': not any('truncated' in f for f in failures),
        'hud_lookups_are_catalogue_keys': not any('catalogue' in f for f in failures),
        'failures': failures,
    }
    print(json.dumps(report['coverage'], indent=1))
    for row in report['panels']:
        print(f"{row['language']}: {len(row['requested'])} HUD lookups, png={row['png']}")
    for row in report['screens']:
        if row['screen'] == 'settings_language':
            print(f"{row['language']} language row drew: "
                  f"{[t for t in row['texts'] if t.endswith('›')]}")
    print('OK: geometry, truncation and lookup coverage all hold' if not failures
          else 'FAIL: ' + '; '.join(failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
