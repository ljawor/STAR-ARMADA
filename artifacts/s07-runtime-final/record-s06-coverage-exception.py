"""Record the S06 coverage exception that S07's own stop criteria require.

`docs/BLENDER_MODEL_S07_PLAN.md` §7: "S07 can close only after required S06 coverage is complete or
explicitly excepted." Coverage is not complete: the registry carries rows that are not authored and
rows that are proposed to stay procedural. This writes the exception, enumerated from the registry
itself so the list cannot drift from the data it describes, plus the policy decision that authorizes
it.

Provenance is kept explicit: the owner authorized recording the exception; the row list is derived
from `assets/models/registry.json`, not typed by hand; the wording of the exception text is the
implementer's draft under that authorization. The owner's own words are quoted verbatim and are not
presented as approval of any appearance.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'art/manifests/pipeline_policy.json'
REGISTRY = ROOT / 'assets/models/registry.json'
PIPELINE = ROOT / 'art/manifests/pipeline.json'
OUT = ROOT / 'art/manifests/reviews/S07-S06-COVERAGE-EXCEPTION.json'

DECISION_ID = 's07-s06-coverage-exception-2026-10-19'
BASE_COMMIT = '56906ea7c73c219fbdc91c68176104b23d0f7712'
OWNER_WORDING = "OK let's do it : 1st a) than b) than merging rest."   # verbatim, 2026-10-19

REASONS = {
    'authoring_pending': (
        'not yet authored: the binding remains procedural in the shipped runtime and is absent from '
        'the opt-in registry, so no preview or default path can select it; authoring continues in S06 '
        'after S07 closes'),
    'keep_procedural_proposed': (
        'proposed to remain procedural: an environment backdrop whose generation is the shipped '
        'behaviour and for which no authored replacement is planned; the proposal status is retained '
        'and is not an appearance approval'),
}
CLASS_MEANING = {
    'authoring_pending': 'deferred authoring, tracked for a later S06 batch',
    'keep_procedural_proposed': 'proposed to remain procedural for the foreseeable catalogue',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


registry = json.loads(REGISTRY.read_text())
bindings = registry['bindings']
pipeline = json.loads(PIPELINE.read_text())['assets']

core = [b for b in bindings if b.get('status') == 'core']
rows = [b for b in bindings if b.get('status') != 'core']
by_status = {}
for row in rows:
    by_status.setdefault(row['status'], []).append(row)

# the enumerated exception must be exactly the registry's non-core rows, by class
assert set(by_status) == set(REASONS), f'unexpected status classes: {sorted(by_status)}'
assert len(rows) == sum(len(v) for v in by_status.values())

approved_assets = [a for a in pipeline if (a.get('approval') or {}).get('decision_id')]
assert len(approved_assets) == len(pipeline), 'a registered asset has no approval decision'
assert set(a['binding'] for a in approved_assets) == set(b['binding'] for b in core), (
    'registry core rows and approved pipeline assets disagree')
decision_ids = sorted({(a.get('approval') or {}).get('decision_id') for a in approved_assets})

record = {
    'schema': 1,
    'id': DECISION_ID,
    'date': '2026-10-19',
    'requirement': ('docs/BLENDER_MODEL_S07_PLAN.md §7 — S07 can close only after required S06 '
                    'coverage is complete or explicitly excepted'),
    'classification': 'explicit_exception',
    'counts': {
        'registry_bindings': len(bindings),
        'registered_and_approved': len(core),
        'excepted': len(rows),
        'by_class': {status: len(items) for status, items in by_status.items()},
    },
    'registered_and_approved': {
        'bindings': len(core),
        'approval_decision_ids': decision_ids,
        'note': 'every registered asset carries an explicit approval decision; nothing is approved here',
    },
    'excepted_bindings': [
        {
            'binding': item['binding'],
            'registry_status': status,
            'class_meaning': CLASS_MEANING[status],
            'category': item.get('category'),
            'manifest': item.get('manifest'),
            'reason': REASONS[status],
        }
        for status, items in sorted(by_status.items())
        for item in sorted(items, key=lambda b: b['binding'])
    ],
    'not_approved_by_this_record': [
        'any appearance, model revision or approval for the excepted bindings',
        'a default switch: the shipped default stays legacy',
        'merge, release or packaging authorization, which remain separate owner gates',
    ],
    'owner_authorization': {
        'basis': 'owner instruction in chat, 2026-10-19',
        'owner_wording': OWNER_WORDING,
        'scope_defined_by': ('implementer enumeration derived from assets/models/registry.json status; '
                             'the owner authorized recording the exception, not inventing its rows'),
        'wording_source': ('implementer draft under that authorization; the enumerated rows are '
                           'machine-derived from the registry, and this text is not attributed to the owner'),
    },
    'binding_evidence': {
        'base_commit': BASE_COMMIT,
        'registry_path': 'assets/models/registry.json',
        'registry_sha256': sha(REGISTRY),
        'pipeline_path': 'art/manifests/pipeline.json',
        'pipeline_sha256': sha(PIPELINE),
    },
    'enforcement': ('build-final-receipt.py refuses to build unless this record enumerates exactly the '
                    'registry non-core rows, class for class, so the exception cannot silently absorb a '
                    'new unauthored row or drop one'),
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(record, indent=2) + '\n')

policy = json.loads(POLICY.read_text())
log = policy['decision_log']
assert not any(entry.get('id') == DECISION_ID for entry in log), 'decision already recorded'
log.append({
    'id': DECISION_ID,
    'date': '2026-10-19',
    'owner': 'owner (Lukasz Jawor)',
    'decision': 'accepted-s06-coverage-exception',
    'owner_wording': OWNER_WORDING,
    'question_answered': (
        'S07 can close only once S06 coverage is complete or explicitly excepted. Sixteen registry '
        'bindings are not authored: twelve authoring_pending rows and four keep_procedural_proposed '
        'rows. Are those sixteen excepted from S07 coverage so S07 can close?'),
    'how_recorded': (
        'Put to the owner as the second of three actions ("1st a) then b) then merging rest"); the '
        'enumerated rows and their classes are derived from assets/models/registry.json at the moment '
        'of recording and are listed in art/manifests/reviews/S07-S06-COVERAGE-EXCEPTION.json, not '
        'paraphrased here'),
    'scope': {
        'excepted': len(rows),
        'by_class': {status: len(items) for status, items in by_status.items()},
        'registered_and_approved_untouched': len(core),
    },
    'does_not_authorize': ['any appearance approval', 'a default switch', 'merge, release or packaging'],
    'evidence': 'art/manifests/reviews/S07-S06-COVERAGE-EXCEPTION.json',
    'bound_to': {'registry_sha256': sha(REGISTRY), 'base_commit': BASE_COMMIT},
})
POLICY.write_text(json.dumps(policy, indent=2) + '\n')

print('wrote', OUT.relative_to(ROOT))
print('registered and approved:', len(core), '| excepted:', len(rows),
      {k: len(v) for k, v in by_status.items()})
print('policy decisions:', len(log), '| policy bytes:', POLICY.stat().st_size)
for row in record['excepted_bindings']:
    print(f"  {row['registry_status']:<24} {row['binding']}")
