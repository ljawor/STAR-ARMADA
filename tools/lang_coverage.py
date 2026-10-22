"""Language-pack coverage for #93: extract the UI catalogue, report what is translated.

The English pack *is* the catalogue: this tool walks the player-facing surface (the
menu screens and the in-game HUD) for the string literals those files can draw, adds
the data-driven names from the shipped catalogue, and writes them to
``assets/data/lang/en.json``. Every other pack is then measured against it, so the
translated/missing numbers are generated rather than claimed and a reworded UI string
shows up as a stale key instead of silently staying English.

Usage:
    .venv/bin/python tools/lang_coverage.py            # report only
    .venv/bin/python tools/lang_coverage.py --write     # refresh the English catalogue
    .venv/bin/python tools/lang_coverage.py --markdown  # coverage table for a PR body
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from render import i18n

LANG_DIR = os.path.join(ROOT, 'assets', 'data', 'lang')

#: The player-facing surface: menu screens, the in-game HUD and the entry point.
#: Presentation only — no simulation module may need a translation.
UI_SURFACE = (
    'render/menus.py',
    'render/clean_classic.py',
    'render/classic_screens.py',
    'render/classic_saves.py',
    'render/classic_replays.py',
    'render/save_library.py',
    'render/replay_library.py',
    'render/hud.py',
    'render/cinematics.py',
    'render/presentation.py',
    'main.py',
)

#: Literals that are never shown to a player: screen ids, keys, formats, paths, shaders.
SKIP_PREFIXES = ('gl_', 'SDL_', 'K_', 'utf-', 'ascii', 'json', 'text/', 'image/', '#')
SKIP_SUFFIXES = ('.json', '.png', '.jpg', '.glsl', '.md', '.py', '.ttf', '.wav', '.ogg')
SKIP_EXACT = {
    'utf-8', 'ascii', 'true', 'false', 'all', 'off', 'hostiles', 'standard', 'night',
    'ON', 'OFF', 'left', 'right', 'center', 'top', 'bottom', 'none', 'en', 'de', 'pl', 'ru',
    # Settings validation warning, never drawn as a player-facing label.
    'Invalid visual pack preferences; using legacy models',
    # The startup refusal of #160: printed to the console and followed by SystemExit(2) before
    # any screen exists, so it is a developer diagnostic, not a label the player can be shown.
    'the native renderer is missing: build it with\n'
    '  cmake -S render_cpp -B render_cpp/build-w02 && cmake --build render_cpp/build-w02\n'
    'there is no legacy renderer to fall back to any more (issue #160)',
    # Internal canonical handoff assertions, never presented as player-facing labels.
    'Recovery requires a detached LAN manager',
    'Recovered manager differs from the drained canonical barrier',
}

#: Strings the scanner cannot harvest, listed by hand. Both kinds would otherwise be
#: invisible to the coverage report: a template the UI assembles with `str.format` reads
#: as an f-string fragment, and a unit word ('hull') reads as an id because it is
#: lowercase. A key that is not in the catalogue can never be reported as untranslated.
EXTRA_UI_KEYS = (
    '{outcome} — {name}',
    '{label} +{percent}%',
    '{page} · Page {n}/{total}',
    '{credits} cr · {materials} mt',
    '{credits} cr · {materials} mt · {energy} EN',
    '{credits} cr · {materials} mt · {energy} EN · {time}s',
    '{crew} crew · {command} cmd · {time}s',
    'REFIT · LEVEL {level}/{max}',
    '▲ Refit to level {level}',
    '+{count} shot/mount',
    '+{count} convoy',
    'hull', 'shields', 'regen', 'damage', 'output', 'cargo',
    '▲', '▼',
    # Station tuning: format fields, lowercase unit words and the percent-bearing
    # explanation deliberately fail the conservative literal heuristic below.
    '+{count} per level', '+{percent}% per level',
    'Gated hulls: {gated}', 'Retuned station types: {tuned}',
    'The gain each refit level adds, as a share of the shipped value. 100% doubles it.',
    'as shipped', 'convoys', 'extra shots', 'level {level}',
    '{station} is back to the shipped balance.',
)


def _is_candidate(value: str) -> bool:
    if not value or len(value) < 2 or len(value) > 400:
        return False
    if value != value.strip():
        # Leading/trailing space means this is a fragment of a longer f-string
        # (" CR/HP · "), not a label a player ever sees on its own.
        return False
    if value in SKIP_EXACT or value.startswith(SKIP_PREFIXES):
        return False
    if value.endswith(SKIP_SUFFIXES):
        return False
    if not any(ch.isalpha() for ch in value):
        return False
    if '%' in value or value.startswith('$'):
        return False
    if value.isupper() and '_' in value:
        # CONSTANT_IDS and environment variables, not labels.
        return False
    if value == value.lower():
        # Lowercase-only literals are ids, keys, actions or enum values, not labels.
        return False
    if value.startswith('{') or value.endswith('}'):
        return False
    if value[-1] in '·+=/([:;,|-':
        return False
    if any(token in value for token in ('\\n', '{}', 'self.', 'os.', '->')):
        return False
    return True


def literals_in(path: str) -> set[str]:
    """Every string literal a module can draw, docstrings excluded."""
    with open(path, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if _is_candidate(node.value):
                found.add(node.value)
    return found


def data_names() -> dict[str, str]:
    """English display names of every shipped ship, station, faction, tech and weapon.

    Read from the dataclasses the game itself loads, so a name that changes in the
    data is a catalogue change here, not a translation that quietly stops applying.
    """
    # Import order matters here: `game.core.manager` pulls `game.systems`, which the
    # data store also needs; loading the store first deadlocks on the cycle.
    from game.core.manager import GameManager  # noqa: F401
    from game.data.store import DataStore
    ds = DataStore.get()
    names: dict[str, str] = {}
    for group, table in (('ships', getattr(ds, 'ships', {})),
                         ('stations', getattr(ds, 'stations', {})),
                         ('factions', getattr(ds, 'factions', {})),
                         ('tech', getattr(ds, 'techs', {})),
                         ('weapons', getattr(ds, 'weapons', {}))):
        for entry in table.values():
            value = getattr(entry, 'display_name', None)
            if isinstance(value, str) and value.strip():
                names[value] = group
    # A planet's display name is derived from its id, exactly as `unit_name` does it.
    for planet_id in ('temperate', 'desert', 'ocean', 'gas_giant', 'ice', 'barren', 'volcanic'):
        names[planet_id.replace('_', ' ').title()] = 'planets'
    return names


def catalogue() -> dict[str, str]:
    keys: dict[str, str] = {}
    for rel in UI_SURFACE:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        for value in literals_in(path):
            keys[value] = 'ui'
    # Templates the UI assembles at runtime (`t('{outcome} — {name}', …)`). They are
    # literals in the source, but they look like a f-string fragment to the scanner, so
    # they are listed here by hand — a template no pack carries is untranslated text.
    for value in EXTRA_UI_KEYS:
        keys[value] = 'ui'
    for value, group in data_names().items():
        keys.setdefault(value, group)
    return keys


def load_json(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


def report(markdown: bool = False) -> int:
    keys = catalogue()
    en_path = os.path.join(LANG_DIR, 'en.json')
    en = load_json(en_path)
    missing_from_en = sorted(key for key in keys if key not in en and key not in en.get('names', {}))
    rows = []
    total_translated = 0
    total = len(keys)
    for code, _label in i18n.LANGUAGES:
        if code == i18n.DEFAULT_LANGUAGE:
            continue
        pack = load_json(os.path.join(LANG_DIR, f'{code}.json'))
        strings = {k: v for k, v in pack.items() if k != 'names'}
        names = pack.get('names', {}) if isinstance(pack.get('names'), dict) else {}
        translated = sum(1 for key in keys
                         if isinstance(value := strings.get(key, names.get(key)), str)
                         and value.strip())
        total_translated += translated
        rows.append((code, translated, len(strings) + len(names), total - translated))
    if markdown:
        print(f'| Language | Translated | Pack entries | Missing | Coverage |')
        print('|---|---|---|---|---|')
        for code, translated, entries, missing in rows:
            pct = (100.0 * translated / total) if total else 0.0
            print(f'| {code} | {translated} | {entries} | {missing} | {pct:.1f}% |')
    else:
        en_entries = len(en) - int('names' in en) + len(en.get('names', {}))
        print(f'catalogue: {total} keys ({en_entries} in en.json, {len(missing_from_en)} not yet written)')
        for code, translated, entries, missing in rows:
            pct = (100.0 * translated / total) if total else 0.0
            print(f'  {code}: {translated}/{total} translated ({pct:.1f}%), '
                  f'{entries} pack entries, {missing} missing')
        if missing_from_en:
            print('  en.json needs refreshing for:')
            for key in missing_from_en[:15]:
                print(f'    {key!r}')
    return 0


def write_catalogue() -> int:
    """Rebuild the English catalogue from the source — never merged with the old file.

    A stale key (a UI string that has been reworded) must disappear from the
    catalogue so it shows up as *missing* in every translation instead of lingering
    as a dead entry nobody will ever draw.
    """
    keys = catalogue()
    names = {value: group for value, group in keys.items() if group != 'ui'}
    out: dict[str, object] = {key: key for key, group in sorted(keys.items()) if group == 'ui'}
    out['names'] = {key: key for key in sorted(names)}
    os.makedirs(LANG_DIR, exist_ok=True)
    with open(os.path.join(LANG_DIR, 'en.json'), 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(out, handle, ensure_ascii=False, indent=1)
        handle.write('\n')
    print(f'wrote {os.path.join(LANG_DIR, "en.json")}: '
          f'{len(out) - 1} strings, {len(out["names"])} data names')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='refresh assets/data/lang/en.json')
    parser.add_argument('--markdown', action='store_true', help='coverage table for a PR body')
    args = parser.parse_args()
    sys.exit(write_catalogue() if args.write else report(markdown=args.markdown))
