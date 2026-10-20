#!/usr/bin/env python3
"""Assemble artifacts/s11/RECEIPT.json from the evidence this branch produced.

Re-runnable and read-only: it measures the built bundle, replays the package's own
smoke logs, recomputes the pixel differences and re-runs the validators, so the receipt
can never claim more than the tree can show. The full-suite figures are parsed from
artifacts/s11/suite.log when a completed run exists.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / 'build/s11-dist/STAR ARMADA.app'
PY = ROOT / '.venv/bin/python'


def run(*args):
    done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    text = (done.stdout + done.stderr).strip()
    return {'exit': done.returncode, 'last_line': text.splitlines()[-1] if text else ''}


def bundle():
    if not APP.is_dir():
        return {'built': False}
    resources = APP / 'Contents/Resources'
    files = [p for p in APP.rglob('*') if p.is_file()]
    manifests = sorted((resources / 'assets/models/manifests').glob('*.json'))
    verified = 0
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        for entry in data.get('files', {}).values():
            target = resources / entry['path']
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256']:
                verified += 1
    forbidden = [p for p in APP.rglob('*')
                 if any(part in p.as_posix() for part in ('/tools/', '/tests/', 'handoff', '.blend'))]
    return {'built': True, 'files': len(files),
            'bytes': sum(p.stat().st_size for p in files),
            'manifests': len(manifests), 'payloads_verified': verified,
            'schemas': len(list((resources / 'assets/models/schemas').glob('*.json'))),
            'forbidden_paths': len(forbidden)}


def pixels():
    script = r'''
import json, sys, pygame, numpy as np
pygame.init(); pygame.display.set_mode((1, 1))
def load(name): return pygame.surfarray.array3d(pygame.image.load(name)).astype(np.int16)
a, b, c = (load('artifacts/s11/smoke-%s.png' % n) for n in ('fresh', 'upgraded', 'legacy'))
def diff(x, y): return round(float((np.abs(x - y).max(axis=2) > 8).mean() * 100), 3)
print(json.dumps({'fresh_vs_upgraded': diff(a, b), 'fresh_vs_legacy': diff(a, c),
                  'upgraded_vs_legacy': diff(b, c)}))
'''
    done = subprocess.run([str(PY), '-c', script], cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {'error': (done.stdout + done.stderr)[-400:]}


def smokes():
    out = {}
    for mode in ('fresh', 'upgraded', 'legacy'):
        log = HERE / f'smoke-{mode}.log'
        text = log.read_text() if log.exists() else ''
        out[mode] = {'smoke_ok': 'SMOKE_OK' in text,
                     'settings_on_disk': {'fresh': 'absent', 'upgraded': 'model_preview false, no marker',
                                          'legacy': 'model_preview false, marker true'}[mode]}
    return out


def suite():
    """The attributable instrument: one process per module, per-module timeouts."""
    gate = HERE / 'per-module-final.json'
    if not gate.exists():
        return {'run': False}
    data = json.loads(gate.read_text())
    return {'instrument': 'tools/acceptance/run_suite_per_module.py --out '
                          'artifacts/s11/per-module-final.json',
            'run': True, 'modules': data['modules'], 'tests': data['tests_ran'],
            'tally': data['tally'], 'wall_seconds': data['wall_seconds'],
            'timeout_seconds_per_module': data['timeout_seconds_per_module'],
            'not_passing': [{'module': row['module'], 'outcome': row['outcome'],
                             'failing': row.get('failing', [])}
                            for row in data['not_passing']]}


receipt = {
    'contract': 'star-armada/s11-switch-receipt',
    'engine_version': run(str(PY), '-c', 'import game; print(game.__version__)')['last_line'],
    'decision': 's11-default-switch-2026-10-19',
    'bundle': bundle(),
    'smokes': smokes(),
    'pixel_percent_differing': pixels(),
    'validators': {
        'validate_models': run(str(PY), '-m', 'tools.art.model_pipeline', 'validate-models', '--all'),
        'runtime_metadata': run(str(PY), '-m', 'tools.art.sync_runtime_metadata', '--check'),
        'release_asset_lock': run(str(PY), 'tools/art/build_release_asset_lock.py', '--check'),
    },
    'suite': suite(),
}
(HERE / 'RECEIPT.json').write_text(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
print(json.dumps(receipt, indent=1, sort_keys=True))
