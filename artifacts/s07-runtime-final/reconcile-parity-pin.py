"""Reconcile B5's broad implementation pin to the final S07 renderer bytes.

The first run of this tool (written to parity-pin-reconciliation.json) reconciled
B5 to the two-method authored-parity repair. The motion/ownership repair then moved
two further methods, so this version reconciles the pin to the four-method delta,
retains both earlier correction blocks unchanged, and records the supersession
rather than overwriting the record that documented the earlier two methods.

It asserts the changed-method set, proves the protected methods are AST-identical
to both the published checkpoint and B5's own approved baseline, cross-checks the
pin it is replacing against the capture set rendered under it, and re-proves every
other approved path against the published checkpoint.
"""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = 's06-b5-environment-2026-10-17'
SUPERSEDED = 's07_authored_parity_pin_correction'
BLOCK = 's07_motion_ownership_pin_correction'
EXPECTED_CHANGED = ['_draw_ship', '_draw_ship_role_batch', '_draw_ships', '_draw_station']
PROTECTED = ['_draw_asteroid_field', '_asteroid_prop_lists', '_emit_detail_mesh',
             '_draw_construction_sites']
PARITY_EVIDENCE = 'artifacts/s07-runtime-final/native-parity-attempt1/report.json'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def git_bytes(*args):
    # Approved sources include .blend binaries; never decode them as text.
    return subprocess.check_output(['git', *args], cwd=ROOT)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_path(path):
    return sha_bytes((ROOT / path).read_bytes())


def methods(source):
    return {n.name: ast.dump(n, include_attributes=False)
            for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}


def canonical(value):
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def main():
    base = git('rev-parse', 'HEAD').strip()
    old_source = git('show', base + ':render/renderer.py')
    new_source = (ROOT / 'render/renderer.py').read_text()
    old, new = methods(old_source), methods(new_source)

    changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
    assert changed == EXPECTED_CHANGED, changed
    assert all(old[k] == new[k] for k in PROTECTED)

    path = ROOT / 'art/manifests/approvals.json'
    original = path.read_bytes()
    approval = json.loads(original)
    decision = next(d for d in approval['decision_log'] if d['id'] == DECISION)
    assert len(decision['revision']['assets']) == 1

    # Both earlier corrections must come through this run unchanged.
    retained = {k: canonical(decision[k])
                for k in ('s07_renderer_pin_correction', SUPERSEDED)}

    # Locate B5's own approved renderer baseline in history by its recorded hash,
    # and prove the protected methods still match it too.
    b5_pin = decision['s07_renderer_pin_correction']['previous_renderer_sha256']
    b5_source = None
    for commit in git('rev-list', base, '--', 'render/renderer.py').split():
        blob = git('show', commit + ':render/renderer.py')
        if sha_bytes(blob.encode()) == b5_pin:
            b5_source = blob
            break
    assert b5_source is not None, 'B5 approved renderer baseline not found in history'
    b5 = methods(b5_source)
    # `_draw_construction_sites` gained the authored scaffold seam at the published
    # checkpoint (b0ca626..HEAD), under the separately recorded scaffold decisions.
    # It is therefore required to match the checkpoint, not B5. The three methods
    # B5's own record names must still be identical to B5's approved baseline.
    moved_at_checkpoint = ['_draw_construction_sites']
    assert sorted(k for k in PROTECTED if b5[k] != new[k]) == moved_at_checkpoint
    assert all(old[k] == new[k] for k in PROTECTED)
    changed_vs_b5 = sorted(k for k in b5.keys() | new.keys() if b5.get(k) != new.get(k))

    # The pin being replaced is the two-method state that produced the parity captures.
    runtime = decision['revision']['assets'][0]['runtime']
    previous = dict(runtime)
    parity = json.loads((ROOT / PARITY_EVIDENCE).read_text())
    assert previous['render/renderer.py'] == parity['renderer_sha256'], (
        previous['render/renderer.py'], parity.get('renderer_sha256'))
    assert previous['render/renderer.py'] != b5_pin
    superseded = decision[SUPERSEDED]
    assert sorted(superseded['changed_renderer_methods']) == ['_draw_ship', '_draw_ship_role_batch']
    assert sorted(superseded['changed_renderer_methods']) != changed

    # Every other approved path must still be byte-identical to the checkpoint.
    preservation = []
    for item in approval['decision_log']:
        for asset in item.get('revision', {}).get('assets', []):
            for group in ('source', 'exporter', 'runtime'):
                for relative, historical in asset.get(group, {}).items():
                    if relative == 'render/renderer.py':
                        continue
                    actual = sha_path(relative)
                    baseline = sha_bytes(git_bytes('show', base + ':' + relative))
                    assert actual == baseline, (relative, baseline, actual)
                    preservation.append({
                        'path': relative,
                        'historical_approval_pin': historical,
                        'baseline_and_current_sha256': actual,
                        'historical_pin_matches_current': historical == actual,
                        'preserved_against_published_checkpoint': True,
                        # Name the basis, because the two can differ: alliance_common.py moved at the
                        # scaffold seam after B5, so it is preserved against the checkpoint and NOT
                        # against the pin B5 recorded. A reader must not infer "approved bytes unchanged".
                        'preservation_basis': ('historical_approval_pin' if historical == actual
                                               else 'published_checkpoint_only'),
                        'not_preserved_against_historical_approval_pin': historical != actual,
                    })

    # The correction starts from an uncommitted intermediate approvals.json. Publishing those exact
    # bytes beside the record is what makes previous_approvals_sha256 recomputable; a hash that no
    # state on disk or in history can reproduce is an assertion, not evidence.
    previous_approvals_path = ('artifacts/s07-runtime-final/pre-correction/'
                               'approvals-before-motion-correction.json')
    evidence_target = ROOT / previous_approvals_path
    evidence_target.parent.mkdir(parents=True, exist_ok=True)
    evidence_target.write_bytes(original)
    assert sha_path(previous_approvals_path) == sha_bytes(original)

    correction = {
        'authority_decision_ids': ['s07-opt-in-continuation-2026-10-18',
                                   's07-scaffold-registration-2026-10-19'],
        'authority_owner_words_verbatim': ['ok continue', 'Work down the 4 points, please.'],
        'supersedes': SUPERSEDED,
        'reason': ('Engineering-only motion/ownership repair moves two further Renderer methods '
                   '(_draw_ships phased motion order, _draw_station cached role materials) on top '
                   'of the two already reconciled by the authored-parity fix. The broad B5 runtime '
                   'implementation pin follows the final bytes; this is not a new appearance '
                   'approval, asset change, tolerance amendment or acceptance-criterion waiver. '
                   'Both earlier correction blocks, the original appearance approval and every '
                   'other approved path are retained unchanged.'),
        'previous_commit': base,
        'previous_approvals_sha256': sha_bytes(original),
        'previous_approvals_evidence': {
            'path': previous_approvals_path,
            'sha256': sha_bytes(original),
            'note': ('uncommitted intermediate state this correction started from, published verbatim '
                     'so the hash is recomputable; it matches no committed revision by construction'),
        },
        'previous_runtime': previous,
        'previous_changed_renderer_methods': sorted(superseded['changed_renderer_methods']),
        'changed_renderer_methods': changed,
        'changed_methods_vs_b5_approved_baseline': changed_vs_b5,
        'protected_methods_ast_equal': {k: old[k] == new[k] for k in PROTECTED},
        'protected_methods_ast_equal_vs_b5_approved_baseline': {k: b5[k] == new[k] for k in PROTECTED},
        'protected_methods_moved_before_this_correction': {
            k: ('moved by the separately authorized scaffold seam between B5 approval '
                '(b0ca626) and the published checkpoint; unchanged since that checkpoint')
            for k in moved_at_checkpoint},
        'b5_approved_renderer_sha256': b5_pin,
        'previous_pin_evidence': {
            'path': PARITY_EVIDENCE,
            'renderer_sha256': parity['renderer_sha256'],
            'note': 'the two-method pin this correction replaces is the renderer those captures were made with',
        },
        'retained_corrections': {
            name: {'canonical_sha256': digest, 'unchanged_by_this_correction': True}
            for name, digest in retained.items()},
        'approved_revisions_preserved': preservation,
    }

    decision[BLOCK] = correction
    superseded.setdefault('superseded_by', BLOCK)
    runtime['render/renderer.py'] = sha_path('render/renderer.py')

    # The only permitted change to a retained block is the forward pointer itself.
    still_retained = {
        's07_renderer_pin_correction': decision['s07_renderer_pin_correction'],
        SUPERSEDED: {k: v for k, v in decision[SUPERSEDED].items() if k != 'superseded_by'},
    }
    assert {k: canonical(v) for k, v in still_retained.items()} == retained, 'an earlier correction moved'
    path.write_text(json.dumps(approval, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    out = ROOT / 'artifacts/s07-runtime-final/parity-pin-reconciliation-v2.json'
    out.write_text(json.dumps(correction, indent=2) + '\n', encoding='utf-8')

    print(json.dumps({
        'changed_renderer_methods': changed,
        'changed_methods_vs_b5_approved_baseline': changed_vs_b5,
        'protected_methods': PROTECTED,
        'checked_approval_path_records': len(preservation),
        'previous_renderer_sha256': previous['render/renderer.py'],
        'new_renderer_sha256': runtime['render/renderer.py'],
        'retained_corrections': sorted(retained),
    }, indent=1))


if __name__ == '__main__':
    main()
