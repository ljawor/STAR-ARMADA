#!/usr/bin/env python3
"""Render the per-asset export wrappers for the S06 pending batch from one template.

The S03 pipeline refuses an exporter that does not itself open the declared source
(`E_EXPORT_NOT_FROM_SOURCE`), so every asset needs its own wrapper rather than a shared
import. Writing ten near-identical files by hand is how one of them silently drifts; they
are rendered from `tools/art/templates/export_wrapper.tmpl` here, and `--check` proves the
tree still matches that template (it is run by the B1/B2 guard tests).

    python3 tools/art/gen_export_wrappers.py --check
    python3 tools/art/gen_export_wrappers.py            # write missing / mismatched
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / 'tools/art/templates/export_wrapper.tmpl'
FIRST_LINE = '#!/usr/bin/env python3'
SLOTS = ('@@IDENTIFIER@@', '@@LABEL@@', '@@ENVELOPE@@', '@@MIN_LENGTH@@', '@@MAX_TRIANGLES@@',
         '@@MAX_VERTICES@@', '@@MAX_BYTES@@')

# Master label, envelope (the binding's legacy procedural extent), minimum authored Z span,
# and this asset's own export caps - each tighter than the runtime loader's 12,000 triangle
# / 10,000 vertex / 2,000,000 byte ceiling.
ASSETS = {
    'alliance_corvette': ('Blockade Runner', ((-21.9, 21.9), (-6.0, 15.3), (-46.46, 45.0)), 91.4, 8000, 6000, 1_200_000),
    'alliance_carrier': ('Independence-class Fleet Carrier', ((-146.51, 146.51), (-30.5, 57.0), (-204.8, 190.0)), 394.0, 11888, 9450, 2_000_000),
    'alliance_interceptor': ('Falcon interceptor', ((-12.0, 12.0), (-3.0, 8.471), (-19.77, 18.0)), 37.7, 5000, 3500, 500_000),
    'alliance_bomber': ('Bulwark bomber', ((-16.0, 16.0), (-6.8, 6.55), (-25.37, 23.0)), 48.3, 5000, 3500, 500_000),
    'legion_vulture': ('Vulture drone', ((-12.831, 12.831), (-3.0, 7.6), (-15.07, 19.4)), 34.4, 5000, 3500, 500_000),
    'legion_hyena': ('Hyena strike craft', ((-17.531, 17.531), (-7.0, 13.0), (-21.65, 26.12)), 47.7, 5000, 3500, 500_000),
    'syndicate_jackal': ('Jackal raider', ((-7.892, 8.45), (-4.024, 12.0), (-17.258, 24.5)), 41.7, 5000, 3500, 500_000),
    'alliance_convoy': ('Colony transport', ((-31.0, 31.0), (-9.0, 16.0), (-72.698, 59.5)), 132.1, 10000, 7000, 1_500_000),
    'legion_convoy': ('Legion hauler', ((-36.5, 36.5), (-7.0, 29.5), (-65.698, 57.6)), 123.2, 10000, 7000, 1_500_000),
    'syndicate_convoy': ('Syndicate bulk hauler', ((-27.786, 42.267), (-9.0, 36.5), (-76.912, 62.04)), 138.9, 10000, 7000, 1_500_000),
}


def template():
    """The template body, without its own header comment block."""
    text = TEMPLATE_PATH.read_text(encoding='utf-8')
    start = text.index(FIRST_LINE)
    return text[start:]


def render(identifier):
    label, envelope, min_length, max_triangles, max_vertices, max_bytes = ASSETS[identifier]
    text = template()
    for token, value in (('@@IDENTIFIER@@', identifier), ('@@LABEL@@', label),
                         ('@@ENVELOPE@@', repr(envelope)), ('@@MIN_LENGTH@@', repr(min_length)),
                         ('@@MAX_TRIANGLES@@', repr(max_triangles)), ('@@MAX_VERTICES@@', repr(max_vertices)),
                         ('@@MAX_BYTES@@', '{:,}'.format(max_bytes).replace(',', '_'))):
        assert token in text, token
        text = text.replace(token, value)
    for slot in SLOTS:
        assert slot not in text, slot
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report drift and exit 1')
    args = parser.parse_args()
    stale, written = [], []
    for identifier in ASSETS:
        path = ROOT / f'tools/art/export_{identifier}.py'
        wanted = render(identifier)
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current == wanted:
            continue
        stale.append(identifier)
        if not args.check:
            path.write_text(wanted, encoding='utf-8', newline='\n')
            written.append(identifier)
    for identifier in stale:
        print(('DRIFT ' if args.check else 'WROTE ') + identifier)
    if args.check and stale:
        return 1
    print(f'{len(ASSETS) - len(stale)} up to date, {len(written)} written')
    return 0


if __name__ == '__main__':
    sys.exit(main())
