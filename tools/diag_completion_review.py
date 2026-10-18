#!/usr/bin/env python3
"""Bounded, UNAPPROVED production-draw review: --spec SHEET --out FRESH_DIR.

Imperial's single-ship harness hardcodes faction='imperial' in its serving probes;
use the unchanged faction-aware Alliance batch harness for ships AND stations.
Only the in-process selected_binding predicate follows its existing mesh seam.
No registration, simulation/source edits, motion, or scaffold draw claims.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def derive_spec(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding='utf-8'))
    assert spec['schema'] == 1 and spec['assets']
    included, excluded = [], []
    for row in spec['assets']:
        if row.get('review_requires_scaffold_seam') or row.get('class') == 'scaffold':
            paths = [row['seed'], row['mesh'], f"art/blender/{row['identifier']}.blend",
                     f"tools/art/export_{row['identifier']}.py"]
            paths += [str(p.relative_to(ROOT)) for p in
                      (ROOT / 'artifacts/s06-completion').glob(f"{row['identifier']}-export-*.txt")]
            proof = {p: sha256(ROOT / p) if (ROOT / p).is_file() else None for p in paths}
            excluded.append(dict(asset=row, reason='requires S07 scaffold seam', proof=proof))
        else:
            row['label'] = row['binding'].replace(':', '-')
            included.append(row)
    assert 0 < len(included) <= 26
    assert len({a['binding'] for a in included}) == len(included)
    assert len({a['label'] for a in included}) == len(included)
    spec.update(assets=included, excluded=excluded)
    overview = dict(first_x=-4200, first_z=0, spacing=700, distance=700 * len(included),
                    yaw=90, pitch=40, close_distance_floor=150)
    overview.update(spec.get('overview_camera', {}))
    overview.update(spec.get('overview', {}))
    overview['close_distance_floor'] = spec.get('close_distance_floor', overview['close_distance_floor'])
    spec.update(overview=overview, provenance=dict(source=str(path), source_sha256=sha256(path),
                adapter='tools/diag_completion_review.py', harness='tools/diag_alliance_batch_review.py',
                harness_sha256=sha256(ROOT / 'tools/diag_alliance_batch_review.py'),
                note='In-memory camera schema defaults and binding-unique labels; sheets unchanged.'))
    return spec


def assert_unregistered(spec):
    registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
    pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text())
    bindings = {r['binding']: r for r in registry['bindings']}
    for asset in spec['assets']:
        row = bindings[asset['binding']]
        assert row['status'] in ('procedural_legacy', 'authoring_pending'), row
        assert not (ROOT / f"assets/models/manifests/{asset['identifier']}.json").exists()
        assert asset['binding'] not in {a['binding'] for a in pipeline['assets']}


@contextmanager
def selected_seam(selection, bindings):
    original = selection.selected_binding
    selection.selected_binding = lambda key: (True if key in bindings and
                                              selection.mesh_for(key) is not None else original(key))
    try:
        yield
    finally:
        selection.selected_binding = original


def load_harness():
    spec = importlib.util.spec_from_file_location('completion_batch', ROOT / 'tools/diag_alliance_batch_review.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_report(spec, report):
    for flag in ('source_preserved', 'protected_files_preserved',
                 'production_candidates_unselected_after_review'):
        assert report[flag] is True, flag
    for asset in spec['assets']:
        record = report['captures'][asset['binding']]
        for name in ('close', 'tactical'):
            assert record['comparison'][name]['changed_pixels_gt3'] > 0, (asset['binding'], name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    spec = derive_spec(args.spec)
    assert_unregistered(spec)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    derived = out / 'review-spec.json'
    derived.write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    protected = [args.spec.resolve(), ROOT / 'assets/models/registry.json', ROOT / 'art/manifests/pipeline.json']
    protected += [p for folder in ('game', 'render') for p in (ROOT / folder).rglob('*.py')]
    protected += list((ROOT / 'tools').glob('diag_*.py'))
    before = {p: sha256(p) for p in protected}
    sys.path.insert(0, str(ROOT))
    from render import asset_selection as selection
    harness, previous = load_harness(), sys.argv
    try:
        with selected_seam(selection, {a['binding'] for a in spec['assets']}):
            sys.argv = [str(ROOT / 'tools/diag_alliance_batch_review.py'), '--spec', str(derived),
                        '--out', str(out / 'render'), '--skip-motion']
            harness.main()
    finally:
        sys.argv = previous
        selection.configure({})
        assert before == {p: sha256(p) for p in protected}, 'protected source changed'
    check_report(spec, json.loads((out / 'render/metrics.json').read_text()))
    assert_unregistered(spec)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
