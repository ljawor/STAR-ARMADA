"""Compare a pre-final capture set against the final-byte capture set.

Purpose: the earlier captures were made with renderer 7d05d28b (two-method repair).
The final renderer is 9aff3414 (four methods). `_draw_ships` only phases motion when a
visible ship is authored AND moving, so stationary single-entity captures should be
byte-identical; `_draw_station` changed the authored station path, so station-class
rows are expected to differ. This measures which captures moved instead of asserting
it, and reports per-binding counts rather than a single total.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
import numpy as np


def changed(a, b):
    x = np.asarray(Image.open(a).convert('RGB'), dtype=np.int16)
    y = np.asarray(Image.open(b).convert('RGB'), dtype=np.int16)
    if x.shape != y.shape:
        return None
    return int(np.any(np.abs(x - y) > 3, axis=2).sum())


def row_key(row):
    return row.get('key') or row.get('binding') or f"{row.get('faction')}-{row.get('mode')}"


def captures_of(report_row, root):
    """Accept both row shapes: a captures dict, or one capture plus a sibling -disabled file."""
    if 'captures' in report_row:
        return report_row['captures']
    if 'capture' in report_row:
        caps = {'capture': report_row['capture']}
        stem = Path(report_row['capture']['file']).stem
        disabled = stem + '-disabled.png'
        if (root / disabled).exists():
            caps['disabled'] = {'file': disabled,
                                'sha256': hashlib.sha256((root / disabled).read_bytes()).hexdigest(),
                                'state_sha256': None}
        return caps
    return {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--old', type=Path, required=True)
    p.add_argument('--new', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    # Some earlier reports predate the renderer_sha256 field. The old bytes may be
    # declared from independent evidence; the new side must carry its own hash.
    p.add_argument('--old-renderer', default=None)
    a = p.parse_args()
    old_report = json.loads((a.old / 'report.json').read_text())
    new_report = json.loads((a.new / 'report.json').read_text())
    assert new_report.get('status') == 'passed', new_report.get('status')
    rows = []
    for new_row in new_report['rows']:
        key = row_key(new_row)
        old_row = next((r for r in old_report['rows'] if row_key(r) == key), None)
        row = {'key': key, 'binding': new_row.get('binding', key),
               'category': new_row.get('category', 'unspecified'),
               'old_revision': (old_row or {}).get('revision'),
               'new_revision': new_row.get('revision'),
               'captures': {}}
        if old_row and old_row.get('revision') and new_row.get('revision'):
            assert old_row['revision'] == new_row['revision'], (
                key, 'revision moved between capture sets')
        for label, new_cap in captures_of(new_row, a.new).items():
            old_cap = captures_of(old_row, a.old).get(label) if old_row else None
            if old_cap is None:
                row['captures'][label] = {'status': 'no_counterpart'}
                continue
            count = changed(a.old / old_cap['file'], a.new / new_cap['file'])
            row['captures'][label] = {
                'old_sha256': old_cap['sha256'],
                'new_sha256': new_cap['sha256'],
                'old_state_sha256': old_cap['state_sha256'],
                'new_state_sha256': new_cap['state_sha256'],
                'byte_identical': old_cap['sha256'] == new_cap['sha256'],
                'changed_pixels_gt3': count,
            }
        rows.append(row)

    identical = [r['binding'] for r in rows
                 if all(c.get('byte_identical') for c in r['captures'].values())]
    moved = [r['binding'] for r in rows if r['binding'] not in identical]
    by_category = {}
    for r in rows:
        entry = by_category.setdefault(r['category'], {'bindings': 0, 'moved': 0})
        entry['bindings'] += 1
        entry['moved'] += r['binding'] not in identical
    states_preserved = all(
        c['old_state_sha256'] == c['new_state_sha256']
        for r in rows for c in r['captures'].values()
        if c.get('old_state_sha256') is not None and c.get('new_state_sha256') is not None)
    old_renderer = old_report.get('renderer_sha256') or a.old_renderer
    new_renderer = new_report.get('renderer_sha256')
    assert new_renderer, 'the new capture set must record the renderer bytes that produced it'
    assert old_renderer, 'declare --old-renderer: the old report has no renderer hash'
    assert old_renderer != new_renderer, (
        'both capture sets used the same renderer bytes: this compares nothing')
    summary = {
        'old_renderer_sha256': old_renderer,
        'old_renderer_sha256_source': ('report' if old_report.get('renderer_sha256')
                                       else 'declared_on_command_line'),
        'new_renderer_sha256': new_renderer,
        'old_harness_sha256': old_report.get('harness_sha256'),
        'new_harness_sha256': new_report.get('harness_sha256'),
        'bindings_compared': len(rows),
        'captures_compared': sum(len(r['captures']) for r in rows),
        'byte_identical_bindings': len(identical),
        'moved_bindings': moved,
        'by_category': by_category,
        'per_frame_state_sha256_preserved': states_preserved,
        'note': ('A capture that moved is not a defect by itself: _draw_station changed the '
                 'authored station path. Station-class movement is expected; identical '
                 'station captures would mean the new method never took effect.'),
    }
    a.out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=2) + '\n')
    print(json.dumps(summary, indent=1))
    assert states_preserved, 'a capture changed the simulation state'


if __name__ == '__main__':
    main()
