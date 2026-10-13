"""Build `assets/data/lang/{de,pl}.json` from the authored maps in `tools/lang_sources/`.

The German and Polish packs are generated, never hand-edited, and this script refuses to
write anything unless every pack carries *exactly* the catalogue: a missing key would ship
as a silent English fallback, and a key that is not in the catalogue would sit in the pack
forever, unreachable. Both are build errors.

    python tools/build_lang_packs.py

Run `tools/lang_coverage.py --write` first when UI strings changed: that refreshes
`assets/data/lang/en.json`, the catalogue this script checks against.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT, 'assets', 'data', 'lang')
SOURCES = os.path.join(ROOT, 'tools', 'lang_sources')


def load_source(code: str):
    """Import `tools/lang_sources/<code>.py` by path — it is deliberately not a package."""
    path = os.path.join(SOURCES, f'{code}.py')
    spec = importlib.util.spec_from_file_location(f'lang_source_{code}', path)
    if spec is None or spec.loader is None:                 # pragma: no cover - misuse
        raise SystemExit(f'cannot import pack source {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, code.upper()), getattr(module, f'{code.upper()}_NAMES')


def main() -> int:
    with open(os.path.join(LANG_DIR, 'en.json'), encoding='utf-8') as handle:
        en = json.load(handle)
    en_names = en.pop('names')
    en_strings = set(en)

    loaded = {}
    problems = 0
    for code in ('de', 'pl'):
        strings, names = load_source(code)
        loaded[code] = (strings, names)
        missing = sorted(en_strings - set(strings))
        extra = sorted(set(strings) - en_strings)
        missing_names = sorted(set(en_names) - set(names))
        extra_names = sorted(set(names) - set(en_names))
        if missing:
            problems += 1
            print(f'{code}: {len(missing)} catalogue keys untranslated:')
            for key in missing:
                print(f'    {key!r}')
        if extra:
            problems += 1
            print(f'{code}: {len(extra)} keys not in the catalogue: {extra}')
        if missing_names:
            problems += 1
            print(f'{code}: {len(missing_names)} names untranslated: {missing_names}')
        if extra_names:
            problems += 1
            print(f'{code}: {len(extra_names)} names not in the catalogue: {extra_names}')

    if problems:
        print('refusing to write packs: fix the keys above and re-run')
        return 1

    for code, (strings, names) in loaded.items():
        out = {key: strings[key] for key in sorted(en_strings)}
        out['names'] = {key: names[key] for key in sorted(en_names)}
        path = os.path.join(LANG_DIR, f'{code}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(out, handle, ensure_ascii=False, indent=1)
            handle.write('\n')
        print(f'wrote {path}: {len(out) - 1} strings, {len(out["names"])} names')
    return 0


if __name__ == '__main__':
    sys.exit(main())
