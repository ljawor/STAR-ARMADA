"""Language packs (#93): player-facing text, loaded at the render edges.

A pack is a flat JSON map from the **English string** (the msgid, exactly as it is
written in the source) to its translation, plus an optional ``names`` section for
data-driven names — ships, stations, factions, tech, weapons — which are keyed by the
English display name so that translating a name needs no code change and a mod's own
name still passes through untouched.

Only presentation code imports this module: the simulation never reads a pack, so a
language cannot change `state_sha256`, a replay or a lockstep peer. The English pack
is the catalogue — its keys are every string the UI can draw, extracted by
``tools/lang_coverage.py`` — and a pack missing a key falls back to English rather
than to a blank label.

Lookups happen at the drawing edges (``SetupCanvas.text``/``.button``,
``HUD._label``, ``menu._button``/``._title``), so a screen is translated without
touching a single call site. Strings assembled at runtime (``f"Page {n}/3"``) cannot
be matched by msgid; those call sites ask for the pattern explicitly with
``t('Page {n}/{total}', n=..., total=...)``.
"""
from __future__ import annotations

import json
import os
from typing import Any

#: Language codes shipped in `assets/data/lang/`. The first entry is the default and
#: the catalogue of every string the UI can draw; every other pack may be partial.
LANGUAGES = (('en', 'English'), ('de', 'Deutsch'), ('pl', 'Polski'), ('ru', 'Русский'))

DEFAULT_LANGUAGE = 'en'

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(_ROOT, 'assets', 'data', 'lang')

#: Active pack: msgid -> translation, plus the resolved language code.
_language = DEFAULT_LANGUAGE
_pack: dict[str, str] = {}
_names: dict[str, str] = {}
_loaded: dict[str, dict | None] = {}


def pack_path(code: str) -> str:
    return os.path.join(LANG_DIR, f'{code}.json')


def available() -> list[tuple[str, str]]:
    """(code, native label) for every shipped pack, in display order."""
    return [entry for entry in LANGUAGES if os.path.exists(pack_path(entry[0]))]


def load_pack(code: str) -> dict | None:
    """The parsed pack for `code`, or None when it is missing or malformed."""
    if code in _loaded:
        return _loaded[code]
    data: dict | None = None
    try:
        with open(pack_path(code), encoding='utf-8') as handle:
            parsed = json.load(handle)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, ValueError, UnicodeDecodeError):
        data = None
    _loaded[code] = data
    return data


def _strings(data: dict | None) -> tuple[dict[str, str], dict[str, str]]:
    """Split a pack into its flat msgid map and its `names` map, dropping junk."""
    if not isinstance(data, dict):
        return {}, {}
    strings = {key: value for key, value in data.items()
               if key != 'names' and isinstance(key, str) and isinstance(value, str)
               and value.strip()}
    names = data.get('names')
    names = ({key: value for key, value in names.items()
              if isinstance(key, str) and isinstance(value, str) and value.strip()}
             if isinstance(names, dict) else {})
    return strings, names


def set_language(code: str) -> str:
    """Activate a pack by code; an unknown or unreadable code falls back to English.

    Returns the code that is actually active, so a caller can persist the fallback
    rather than a language the build does not ship.
    """
    global _language, _pack, _names
    resolved = code if code in {entry[0] for entry in LANGUAGES} else DEFAULT_LANGUAGE
    strings, names = _strings(load_pack(resolved))
    if resolved != DEFAULT_LANGUAGE and not strings:
        # A shipped-but-empty pack is a bug; English is still better than raw keys.
        resolved = DEFAULT_LANGUAGE
        strings, names = _strings(load_pack(DEFAULT_LANGUAGE))
    _language = resolved
    _pack = strings
    _names = names
    return resolved


def language() -> str:
    return _language


def label(code: str) -> str:
    """Native name of a language code, for the settings row."""
    for entry_code, entry_label in LANGUAGES:
        if entry_code == code:
            return entry_label
    return code


def cycle(code: str, step: int = 1) -> str:
    """The next shipped code after `code`, so a settings row can be stepped through.

    Cycles through the *shipped* packs (a code with no file behind it is skipped), and
    an unknown code starts at the first entry rather than raising.
    """
    codes = [entry[0] for entry in available()]
    if not codes:
        return DEFAULT_LANGUAGE
    if code not in codes:
        return codes[0]
    return codes[(codes.index(code) + step) % len(codes)]


def apply_from_settings(settings: dict | None) -> str:
    """Activate the language a settings dict carries and write back the resolved code.

    Called once per entry point (`MenuStack.__init__`) so a saved preference is live
    before the first frame is drawn, and a settings file naming a language this build
    does not ship is corrected in place instead of being kept as a lie.
    """
    code = settings.get('language') if isinstance(settings, dict) else None
    resolved = set_language(code if isinstance(code, str) else DEFAULT_LANGUAGE)
    if isinstance(settings, dict) and settings.get('language') != resolved:
        settings['language'] = resolved
    return resolved


def t(text: Any, **fields: Any) -> Any:
    """Translate a player-facing string; unknown strings pass through unchanged.

    `text` is normally the English literal written at the call site. With keyword
    fields the string is treated as a `str.format` template after lookup, so a
    dynamically built label can be translated as one unit
    (`t('Page {n}/{total}', n=2, total=3)`). Non-strings are returned untouched so a
    drawing helper can call this unconditionally.
    """
    if not isinstance(text, str) or not text:
        return text
    out = _pack.get(text) or _names.get(text) or text
    if fields:
        try:
            return out.format(**fields)
        except (KeyError, IndexError, ValueError):
            return out
    return out


def name(text: Any) -> Any:
    """Translate a data-driven name (ship, station, faction, tech, weapon, planet).

    Data names also live in the flat map, so this is `t()` with the emphasis that a
    name is *never* left half-translated: a modded id whose English name is unknown
    passes through as authored.
    """
    return t(text)


def coverage(root: str | None = None) -> dict[str, Any]:
    """Per-pack translation state against the English catalogue.

    Returns the missing and extra msgids per pack so the numbers in a pull request
    are generated rather than claimed, and so a stale key (a UI string that has been
    reworded since it was translated) is visible instead of silently dead.
    """
    root = LANG_DIR if root is None else root
    catalog = _strings(load_pack(DEFAULT_LANGUAGE))[0]
    report: dict[str, Any] = {'catalog': len(catalog), 'packs': {}}
    for code, _label in LANGUAGES:
        if code == DEFAULT_LANGUAGE:
            continue
        strings, names = _strings(load_pack(code))
        missing = sorted(key for key in catalog if key not in strings and key not in names)
        extra = sorted(key for key in strings if key not in catalog)
        report['packs'][code] = {
            'translated': len(strings) + len(names) - len(extra),
            'missing': len(missing),
            'extra': len(extra),
            'missing_sample': missing[:20],
            'extra_sample': extra[:20],
        }
    return report


set_language(DEFAULT_LANGUAGE)
