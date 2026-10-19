#!/usr/bin/env python3
"""Build or verify `art/manifests/release-asset-lock.json` (S10 of the Blender migration).

The lock is the release's answer to one question: *which exact bytes is the shipped
default catalogue made of?* For every required (`status: core`) registry binding it
records the manifest, the mesh payload, both hashes, the approval decision and the
material profile, and it refuses to write a lock whose pins do not match the files on
disk. `--check` regenerates in memory and compares against the committed copy, so CI
can fail on drift without rewriting anything.

    python tools/art/build_release_asset_lock.py            # write
    python tools/art/build_release_asset_lock.py --check    # verify only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'art/manifests/release-asset-lock.json'
CONTRACT = 'star-armada/release-asset-lock'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        raise SystemExit(f'lock path escapes the repository: {path}')


def build() -> dict:
    sys.path.insert(0, str(ROOT))
    from game import __version__

    registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
    manifests = {}
    for path in sorted((ROOT / 'assets/models/manifests').glob('*.json')):
        data = json.loads(path.read_text())
        manifests[data['asset']] = (path, data)

    rows, total_bytes, problems = [], 0, []
    for row in sorted(registry['bindings'], key=lambda item: item['binding']):
        if row.get('status') != 'core':
            continue
        binding, asset = row['binding'], row['manifest']
        if asset not in manifests:
            problems.append(f'{binding}: manifest {asset} is not present')
            continue
        manifest_path, manifest = manifests[asset]
        files = {}
        for role, entry in sorted(manifest.get('files', {}).items()):
            target = ROOT / entry['path']
            if not target.is_file():
                problems.append(f'{binding}: {role} payload missing: {entry["path"]}')
                continue
            actual, size = _sha256(target), target.stat().st_size
            if actual != entry['sha256']:
                problems.append(f'{binding}: {role} hash mismatch for {entry["path"]}')
            if size != entry.get('bytes', size):
                problems.append(f'{binding}: {role} byte count differs for {entry["path"]}')
            total_bytes += size
            files[role] = {'path': entry['path'], 'sha256': actual, 'bytes': size}
        approval = manifest.get('approval', {})
        rows.append({
            'binding': binding,
            'asset': asset,
            'revision': manifest['revision'],
            'manifest': {'path': _relative(manifest_path),
                         'sha256': _sha256(manifest_path),
                         'bytes': manifest_path.stat().st_size},
            'files': files,
            'material_profile': manifest.get('requires', {}).get('material_profile'),
            'min_engine': manifest.get('requires', {}).get('min_engine'),
            'approval': {'decision_id': approval.get('decision_id'),
                         'approved_by': approval.get('approved_by'),
                         'approved_on': approval.get('approved_on')},
            'envelope_decision': row.get('envelope_decision'),
        })

    if problems:
        for problem in problems:
            print(f'FAIL {problem}', file=sys.stderr)
        raise SystemExit(f'refusing to write a lock with {len(problems)} problem(s)')

    return {
        'contract': CONTRACT,
        'contract_major': 1,
        'engine_version': __version__,
        'purpose': ('The exact catalogue a shipped default selection resolves to. '
                    'Rollback is a settings change, not a lock change.'),
        'counts': {'core_bindings': len(rows), 'payload_bytes': total_bytes},
        'bindings': rows,
    }


def render(lock: dict) -> str:
    return json.dumps(lock, indent=1, sort_keys=True) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='verify the committed lock instead of writing it')
    args = parser.parse_args(argv)

    text = render(build())
    if args.check:
        if not LOCK.is_file():
            print('FAIL release-asset-lock.json is missing', file=sys.stderr)
            return 1
        current = LOCK.read_text()
        if current != text:
            print('FAIL release-asset-lock.json is stale; re-run without --check',
                  file=sys.stderr)
            return 1
        print(f'LOCK_OK {len(json.loads(text)["bindings"])} bindings')
        return 0
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(text)
    lock = json.loads(text)
    print(f'wrote {_relative(LOCK)}: {lock["counts"]["core_bindings"]} bindings, '
          f'{lock["counts"]["payload_bytes"]} payload bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
