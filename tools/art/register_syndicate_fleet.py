#!/usr/bin/env python3
"""Put the reworked Rim Syndicate meshes into the core catalogue, ready to play.

The owner runs ``main.py`` from his own tree, so the rework has to be a core asset,
not a pack, and not something a helper script switches on: after this runs, a plain
launch of the game draws the new meshes and nothing else has to be enabled.

Approval is *not* claimed here. Each manifest records
``approval.status = pending`` with the review evidence, and
only ``--approve`` (run after the owner confirms what he saw in the game) writes a
decision, an accepted status and the packaged receipts the loader verifies.

    python3 tools/art/register_syndicate_fleet.py            # review state
    python3 tools/art/register_syndicate_fleet.py --approve  # after the owner says yes
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'art' / 'blender' / 'syndicate_fleet' / 'runtime'
REVIEW_ID = 'syndicate-fleet-rework-2026-10-23-review'
DECISION_ID = 'syndicate-fleet-rework-2026-10-23'
BATCH = 'syndicate-fleet-rework'
STEMS = ('corvette', 'frigate', 'cruiser', 'convoy', 'colonizer', 'constructor', 'fighter',
         'command_station', 'defense_platform', 'energy_relay', 'fighter_platform',
         'mining_station', 'repair_dock', 'research_station', 'sensor_station', 'shipyard',
         'trade_station', 'attack_satellite', 'defense_satellite', 'planet_extractor',
         'planet_pulsar_cannon', 'planet_shield_generator', 'planet_trade_hub')
OWNER_WORDS = ('Migrade the rest of the statiosn and ship of the syndicate. Every change land on '
               'a branch. The brahc will be a PR. The chanhges you are doing must be approved by '
               'me by running main.py. After I see it in the game I will confirm and you will '
               'merge. (2026-10-23, verbatim)')


def revision(asset, mesh_sha):
    return hashlib.sha256(f'{asset}\nmesh:{mesh_sha}'.encode()).hexdigest()


def rel(path):
    return path.relative_to(ROOT).as_posix()


def manifest_for(asset):
    for path in sorted((ROOT / 'assets/models/manifests').glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('asset') == asset:
            return path, data
    raise FileNotFoundError(asset)


def evidence(stem):
    return [f'artifacts/syndicate-fleet/review/{stem}-quarter.jpg',
            f'artifacts/syndicate-fleet/review/{stem}-profile.jpg',
            f'artifacts/syndicate-fleet/review/{stem}-bow.jpg']


def envelope_decision(stem):
    registry = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))
    rows = registry['bindings'] if isinstance(registry, dict) else registry
    for row in rows:
        if row.get('binding') == 'syndicate:' + stem:
            return row['envelope_decision']
    raise KeyError(stem)


def append_decision(entry):
    """Append one entry to the policy log as text.

    Re-serialising the whole document reformats unrelated entries, so the diff would
    bury a fifteen-line decision under hundreds of whitespace changes.
    """
    path = ROOT / 'art/manifests/pipeline_policy.json'
    text = path.read_text(encoding='utf-8')
    marker = '"id": "' + entry['id'] + '"'
    if marker in text:
        return
    body = json.dumps(entry, indent=2, ensure_ascii=False)
    body = '\n'.join('  ' + line for line in body.splitlines())
    tail = '\n  ]\n}\n'
    if not text.endswith(tail):
        raise ValueError('unexpected policy log tail')
    path.write_text(text[: -len(tail)] + ',\n' + body + tail, encoding='utf-8')


def payload_for(stem):
    """The freshest mesh for a stem: a pending rebuild, else what is registered.

    The build staging directory is gitignored, so a tree that only rebuilt one family
    still has the other meshes as the registered copies.
    """
    for path in (PACK / 'assets/models' / f'syndicate_{stem}.mesh.json',
                 ROOT / 'assets/models' / f'syndicate_{stem}.mesh.json'):
        if path.exists():
            return json.loads(path.read_bytes())
    raise FileNotFoundError(stem)


def register():
    hashes = {}
    for stem in STEMS:
        asset = f'core:syndicate/{stem}'
        target = ROOT / 'assets/models' / f'syndicate_{stem}.mesh.json'
        payload = payload_for(stem)
        # The loader compares the contract payload's identity with the manifest asset,
        # so the prototype id has to become the core id before the bytes are hashed.
        payload['asset'] = asset
        raw = (json.dumps(payload, indent=2) + '\n').encode()
        target.write_bytes(raw)
        mesh_sha = hashlib.sha256(raw).hexdigest()
        rev = revision(asset, mesh_sha)

        manifest_path, manifest = manifest_for(asset)
        manifest['revision'] = rev
        manifest['files'] = {'mesh': {'path': rel(target), 'sha256': mesh_sha, 'bytes': len(raw)}}
        manifest['bounds'] = {'min': payload['bounds'][0], 'max': payload['bounds'][1]}
        manifest['roles'] = sorted(payload['batches'])
        manifest['budgets'] = {'triangles': payload['triangle_count'], 'draw_calls': 6,
                               'texture_bytes': 0}
        manifest['provenance'] = {
            'author': 'Lukasz Jawor',
            'tool': 'Blender',
            'tool_version': '5.0.1',
            'license': 'original',
            'source': f'art/blender/syndicate_fleet/{stem}.blend',
            'notes': 'Rim Syndicate rework in the industrial language the Marauder/Leviathan '
                     'batch established. Authored by tools/art/build_syndicate_fleet.py. '
                     'Containment only inside the approved binding envelope: length, camera '
                     'framing and collision radii are unchanged.',
        }
        # The loader checks approval.decision_id against the binding's envelope
        # decision, so it must name the decision that approved the (unchanged)
        # envelope, not this review. The review request itself lives in
        # art/manifests/pipeline.json and the decision log.
        manifest['approval'] = {'status': 'pending',
                                'decision_id': envelope_decision(stem),
                                'reviewed_evidence': evidence(stem)}
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        for path in (ROOT / 'art/blender/syndicate_fleet' / f'{stem}.blend', target,
                     manifest_path):
            hashes[rel(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        print('CORE', asset, payload['triangle_count'], rev[:16])

    pipeline_path = ROOT / 'art/manifests/pipeline.json'
    pipeline = json.loads(pipeline_path.read_text(encoding='utf-8'))
    pipeline.setdefault('review_batches', {})[BATCH] = {
        'state': 'owner_review_pending',
        'requested_on': '2026-10-23',
        'bindings': sorted('syndicate:' + stem for stem in STEMS),
        'note': 'Registered into core so a plain main.py launch draws the rework. '
                'Approval is pending the owner seeing it in the game.',
    }
    pipeline_path.write_text(json.dumps(pipeline, indent=2) + '\n', encoding='utf-8')

    append_decision({
        'id': REVIEW_ID,
        'date': '2026-10-23',
        'owner_words': OWNER_WORDS,
        'scope': 'All 23 pre-existing Rim Syndicate bindings re-authored; meshes and '
                 'manifests committed to core, approval pending the owner playing them.',
        'not_claimed': ['owner approval', 'merge', 'release or tag',
                        'any change to gameplay data, envelope or collision radius'],
    })
    (ROOT / 'art/manifests' / f'{BATCH}-source-hashes.json').write_text(
        json.dumps(dict(sorted(hashes.items())), indent=2) + '\n', encoding='utf-8')
    refresh_native_catalogue()
    print('REGISTER_OK', len(STEMS), 'hashes', len(hashes))


def refresh_native_catalogue():
    """Rebuild the shipped mesh catalogue the native window loads.

    The window verifies every mesh against the SHA256 in this file, so a mesh rework
    that does not refresh it stops the native renderer with 'mesh SHA256 mismatch' on
    the first frame - the game then leaves the match with no legacy fallback.
    """
    import subprocess
    import sys
    result = subprocess.run([sys.executable, 'tools/render/dump_snapshot.py',
                             '--fixture', 'four-player-combat-v1', '--catalogue',
                             '--out', 'assets/cpp/catalogue.snap'],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit('catalogue refresh failed: '
                         + (result.stderr or result.stdout).strip()[-400:])
    print('CATALOGUE', result.stdout.strip()[:120])


def approve():
    receipts_path = ROOT / 'assets/models/approval-receipts.json'
    receipts = json.loads(receipts_path.read_text(encoding='utf-8'))
    for stem in STEMS:
        asset = f'core:syndicate/{stem}'
        manifest_path, manifest = manifest_for(asset)
        approval = manifest['approval']
        if approval.get('status') == 'approved':
            continue
        approval.update(status='approved', decided_by='owner',
                        decided_on='2026-10-23', reviewed_revision=manifest['revision'])
        approval.pop('note', None)
        manifest['approval'] = approval
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        receipts['receipts'][asset] = {
            'manifest_sha256': hashlib.sha256(canonical).hexdigest(),
            'reviewed_revision': manifest['revision'],
            'decision_id': approval['decision_id'],
            'review_id': DECISION_ID,
            'evidence_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                for path in approval['reviewed_evidence']},
        }
        print('APPROVED', asset, manifest['revision'][:16])
    receipts['receipts'] = dict(sorted(receipts['receipts'].items()))
    receipts_path.write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8')
    pipeline_path = ROOT / 'art/manifests/pipeline.json'
    pipeline = json.loads(pipeline_path.read_text(encoding='utf-8'))
    if BATCH in pipeline.get('review_batches', {}):
        entry = pipeline['review_batches'].pop(BATCH)
        pipeline.setdefault('batches', {})[BATCH] = entry['bindings']
        pipeline_path.write_text(json.dumps(pipeline, indent=2) + '\n', encoding='utf-8')
    print('APPROVE_OK', DECISION_ID)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approve', action='store_true',
                        help='record the owner decision after he confirms in the game')
    args = parser.parse_args()
    approve() if args.approve else register()


if __name__ == '__main__':
    main()
