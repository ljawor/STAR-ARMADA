#!/usr/bin/env python3
"""Write the review-only pending sidecars for a batch straight off disk.

Every hash, byte count and count is read from the file it describes: a hand-typed
sha256 in a pending record is a stale record the moment the asset is rebuilt, and the
sidecar is what a later reader trusts when deciding whether the reviewed bytes are the
bytes on the branch.

    python3 tools/art/write_pending_sidecars.py                 # every pending batch
    python3 tools/art/write_pending_sidecars.py --batch s06-b1-alliance-combat --check
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / 'art/manifests/pending'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return dict(path=str(path.relative_to(ROOT)), sha256=digest(path), bytes=path.stat().st_size)


def sidecar_for(batch, asset):
    mesh_path = ROOT / asset['mesh']
    payload = json.loads(mesh_path.read_text(encoding='utf-8'))
    # A batch that authors several meshes from one seed declares it (and the argument that
    # selects this asset) instead of carrying a per-identifier builder.
    seed = ROOT / asset['seed'] if 'seed' in asset else ROOT / 'tools/art' / f"build_{asset['identifier']}.py"
    exporter = ROOT / 'tools/art' / f"export_{asset['identifier']}.py"
    evidence = batch.get('evidence', {}).get(asset['binding'], {})
    return {
        'schema': 1,
        'status': batch['status'],
        'purpose': 'Review-only authoring sidecar. Not an approved runtime manifest, '
                   'approval receipt, or selectable pipeline entry.',
        'batch': batch['batch'],
        'binding': asset['binding'],
        'canonical_binding': f"ship:{asset['binding']}",
        'gameplay_entity': asset['gameplay_entity'],
        'class': asset['class'],
        'authority': payload['features']['authority'],
        'source': record(ROOT / f"art/blender/{asset['identifier']}.blend"),
        'initial_seed': dict(record(seed), selects=asset.get('seed_arg')),
        'export_script': record(exporter),
        'runtime': dict(record(mesh_path), triangles=payload['triangle_count'],
                        vertices=len(payload['vertices']), roles=sorted(payload['batches'])),
        'envelope': asset['envelope'],
        'bounds': payload['bounds'],
        'authoring': payload.get('authoring'),
        'blender_pin': '5.0.1',
        'owner_decision': None,
        'activation': False,
        'future_pipeline_registration':
            'After explicit appearance approval only. Export-only script is normal workflow; '
            'the seed must not overwrite the master. Do not use this sidecar as approval.',
        'evidence': evidence.get('sheet'),
        'motion': evidence.get('motion'),
    }


def sidecar_record(batch, asset):
    """`sidecar_for`, plus the appearance decision when the batch sheet declares one.

    The key is added only for a batch that carries one, so every earlier batch's sidecar stays
    byte-for-byte what it was: these records are what a later reader trusts, and a mechanical
    re-emission of twenty-two of them would be a change nobody asked for. An appearance
    decision is not a landing decision - `owner_decision` still records that, and `activation`
    stays false until a landing is authorized and executed - so the two stay separate fields.
    """
    record = sidecar_for(batch, asset)
    # A partial batch declares each row explicitly; never inherit its decision onto
    # an unpictured row (the B9 scaffold is still awaiting a review seam).
    if batch['status'] == 'partially_appearance_approved_pending_landing':
        record['status'] = asset['status']
        decision = asset.get('appearance_decision')
        approved = record['status'] == 'appearance_approved_pending_landing'
        if approved != bool(decision):
            raise ValueError('partial batch row status/decision mismatch: ' + asset['binding'])
    else:
        decision = batch.get('appearance_decision')
    if decision:
        record['appearance_decision'] = decision
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', default=None)
    parser.add_argument('--check', action='store_true',
                        help='report drift instead of writing (exit 1 when stale)')
    parser.add_argument('--out-dir', type=Path, default=None)
    args = parser.parse_args()

    specs = sorted(PENDING.glob('S06-BATCH-*.json'))
    if args.batch:
        specs = [p for p in specs if json.loads(p.read_text())['batch'] == args.batch]
        if not specs:
            raise SystemExit(f'no pending batch spec matches {args.batch}')
    stale = 0
    for spec_path in specs:
        batch = json.loads(spec_path.read_text(encoding='utf-8'))
        for asset in batch['assets']:
            text = json.dumps(sidecar_record(batch, asset), indent=2, sort_keys=False) + '\n'
            name = 'S06-' + asset['identifier'].upper().replace('_', '-') + '.json'
            out = (args.out_dir or PENDING) / name
            if args.check:
                current = out.read_text(encoding='utf-8') if out.exists() else ''
                if current != text:
                    print(f'STALE {out.relative_to(ROOT)}')
                    stale += 1
            else:
                out.write_text(text, encoding='utf-8')
                print(f'wrote {out.relative_to(ROOT)}')
    if args.check:
        print(f'{stale} stale sidecar(s)')
        return 1 if stale else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
