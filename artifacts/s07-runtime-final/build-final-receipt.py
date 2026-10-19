"""Assemble S07-FINAL-RECEIPT.json from the evidence on disk, not from memory.

Every cited path must exist; every hash is computed here; the overall status is derived from
the criteria rather than asserted. A criterion whose evidence is missing fails loudly instead
of being quietly omitted.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'artifacts/s07-runtime-final'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rel = lambda p: str(Path(p).resolve().relative_to(ROOT))

RENDERER = 'render/renderer.py'
RENDERER_PIN = '9aff34140aa3d458eec358a2d87e64d4d4277c924ca198d507e4d29983350f3c'
CANDIDATE_COMMIT = '56906ea7c73c219fbdc91c68176104b23d0f7712'


def need(path):
    p = Path(path)
    assert p.exists(), f'cited evidence is missing: {path}'
    return {'path': rel(p), 'sha256': sha(p)}


def criterion(cid, wp, requirement, status, commands, exit_codes, evidence,
              controls, limitations, blocking=None, note=None):
    for e in evidence:
        need(ROOT / e)
    row = {
        'id': cid, 'wp': wp, 'requirement_ref': requirement, 'applicability': 'in_scope',
        'status': status, 'commands': commands, 'exit_codes': exit_codes,
        'evidence_paths_and_hashes': [need(ROOT / e) for e in evidence],
        'negative_controls': controls, 'limitations': limitations,
        'blocking_decision_id': blocking,
    }
    if note:
        row['note'] = note
    return row


def suite_gate():
    """The suite gate is per-module, and this reads its receipt rather than a single log.

    A single process cannot serve: tests/test_weapon_sfx.py sets SDL_VIDEODRIVER=dummy at import,
    process-wide, after which GL modules error or hang. The gate recorded here runs one process per
    module with the real driver, plus declared fallbacks (a prelude for a pre-existing circular
    import, pytest for pytest-style modules, script execution for the one module with no test cases).
    """
    path = ART / 'suite-per-module.json'
    gate = json.loads(path.read_text())
    assert gate['modules'] > 190, f'unexpected module count: {gate["modules"]}'
    assert gate['tests_ran'] > 2200, f'unexpected test count: {gate["tests_ran"]}'
    assert 'prelude' in gate and 'pytest_fallback' in gate, 'the gate must declare its fallbacks'
    not_passing = [row['module'] for row in gate['not_passing']]
    classified = json.loads((ART / 'pre-existing-failures.json').read_text())
    known = set(classified['pre_existing']) | set(classified['import_order'])
    unexplained = [module for module in not_passing if module not in known]
    assert not unexplained, f'failing modules with no recorded classification: {unexplained}'
    return {
        'method': gate['method'],
        'prelude': gate['prelude'],
        'pytest_fallback': gate['pytest_fallback'],
        'modules': gate['modules'],
        'tests_ran': gate['tests_ran'],
        'tally': gate['tally'],
        'wall_seconds': gate['wall_seconds'],
        'not_passing_modules': not_passing,
        'in_scope_failures': [m for m in not_passing
                              if classified['pre_existing'].get(m, {}).get('classification') != 'pre_existing'],
        'pre_existing_failures': [
            {'module': module,
             'test': row['test'],
             'base_commit_result': row['base_commit']['counts'],
             'final_tree_result': row['final_tree']['counts'],
             'contradicted_decision': row['contradicted_decision'],
             'handling': row['handling']}
            for module, row in classified['pre_existing'].items()
            if module in not_passing
        ],
        'single_process_run_is_not_a_gate': classified['invalid_gate']['why'],
    }


suite = suite_gate()
pipeline = json.loads((ROOT / 'art/manifests/pipeline.json').read_text())
renderer_sha = sha(ROOT / RENDERER)
assert renderer_sha == RENDERER_PIN, ('renderer moved since the evidence was produced',
                                      renderer_sha, RENDERER_PIN)
review = json.loads((ART / 'INDEPENDENT-MOTION-REVIEW.json').read_text())
assert review['renderer_sha256'] == renderer_sha

bindings = [{'binding': a['binding'], 'runtime': a['runtime'],
             'mesh_sha256': sha(ROOT / a['runtime']),
             'revision_binding': (a.get('approval') or {}).get('decision_id')}
            for a in pipeline['assets']]

criteria = [
    criterion('C1', 'S07-step1', 'B5 runtime pin names the final renderer bytes',
              'pass',
              ['.venv/bin/python artifacts/s07-runtime-final/reconcile-parity-pin.py'],
              [0],
              ['artifacts/s07-runtime-final/parity-pin-reconciliation-v2.json',
               'artifacts/s07-runtime-final/reconcile-parity-pin-v2.log',
               'art/manifests/approvals.json',
               'art/manifests/approved-s06-source-hashes.json'],
              ['the extended script asserts exactly four changed methods and fails if the set moves',
               'protected-method equality is proven against two baselines, so a moved method cannot pass',
               'the retained earlier correction block is compared byte-for-byte except superseded_by'],
              ['the correction record started from an uncommitted intermediate approvals.json; those bytes are now published so the recorded hash is recomputable']),
    criterion('C2', 'S07-step2', 'native catalogue captured on the final renderer',
              'pass',
              ['env -u SDL_VIDEODRIVER -u STAR_ARMADA_FIXED_MATERIALS .venv/bin/python artifacts/s07-runtime-final/run-bounded.py --seconds 1500 --log artifacts/s07-runtime-final/native-catalogue-final.log -- .venv/bin/python artifacts/s07-runtime-final/native-catalogue.py'],
              [0],
              ['artifacts/s07-runtime-final/native-catalogue-final/report.json',
               'artifacts/s07-runtime-final/native-catalogue-final.log'],
              ['the harness asserts every unspawnable row is the documented render-only scaffold, so it cannot silently skip a row',
               'a first attempt crashed on data_id=None and is retained as a failed attempt rather than deleted'],
              ['captures are native-driver frames, not packaged-build or Windows evidence']),
    criterion('C3', 'S07-step2', 'native representative matrix captured on the final renderer with protected inputs unchanged',
              'pass',
              ['env -u SDL_VIDEODRIVER -u STAR_ARMADA_FIXED_MATERIALS .venv/bin/python artifacts/s07-runtime-final/run-bounded.py --seconds 1800 --log artifacts/s07-runtime-final/native-matrix-final.log -- .venv/bin/python artifacts/s07-runtime-final/native-matrix.py'],
              [0],
              ['artifacts/s07-runtime-final/native-matrix-final/report.json',
               'artifacts/s07-runtime-final/native-matrix-final.log'],
              ['the report records renderer_sha256 and the run asserts it in-loop, so acceptance cannot silently run on changed bytes',
               'protected_changed must be empty across 327 pinned inputs'],
              ['a first matrix run predates the renderer-hash field and its captures are not bound to bytes']),
    criterion('C4', 'S07-step2', 'construction and scaffold rows captured on the final renderer',
              'pass',
              ['env -u SDL_VIDEODRIVER -u STAR_ARMADA_FIXED_MATERIALS .venv/bin/python artifacts/s07-runtime-final/run-bounded.py --seconds 1300 --log artifacts/s07-runtime-final/native-construction-final.log -- .venv/bin/python artifacts/s07-runtime-final/native-construction.py'],
              [0],
              ['artifacts/s07-runtime-final/native-construction-final/report.json',
               'artifacts/s07-runtime-final/native-construction-final.log'],
              ['scaffold revision is asserted unchanged at 12959d25'],
              ['construction captures cover queue/prop state, not gameplay construction timing']),
    criterion('C5', 'S07-step2', 'final-byte captures do not drift from the pre-repair sets',
              'pass',
              ['.venv/bin/python artifacts/s07-runtime-final/compare-captures.py --old <pre> --new <final> --out <json> (catalogue, matrix, construction)'],
              [0, 0, 0],
              ['artifacts/s07-runtime-final/catalogue-final-vs-prefinal.json',
               'artifacts/s07-runtime-final/matrix-final-vs-prefinal.json',
               'artifacts/s07-runtime-final/construction-final-vs-prefinal.json'],
              ['the comparator refuses two capture sets produced by the same renderer bytes, so it cannot pass by comparing nothing',
               'state hashes are checked where both reports carry them'],
              ['byte-identity is expected here, and the reason is structural: the two changed draw methods on the uncached path have no production call site, and the one live change is authored LOD suppression, which draws sub-pixel geometry. Identity is therefore not evidence that the changed code is exercised — the motion-transition harness is what exercises it.']),
    criterion('C6', 'S07-step3', 'candidate menu movie rebuilt and independently read back at the final bytes',
              'pass',
              ['.venv/bin/python tools/build_menu_movie.py --model-preview --output-dir artifacts/s07-runtime-final/candidate-movie-final --asset artifacts/s07-runtime-final/candidate-movie-final/review/candidate.zip',
               '.venv/bin/python artifacts/s07-runtime-final/verify-final-movie.py'],
              [0, 0],
              ['artifacts/s07-runtime-final/candidate-movie-final/render-report.json',
               'artifacts/s07-runtime-final/candidate-movie-final-readback.json',
               'artifacts/s07-runtime-final/candidate-movie-final-vs-prefinal.json'],
              ['the verifier refuses a candidate baked by different renderer bytes than the review it is pointed at (proven by an old-candidate control)',
               'the shipped battle.zip is asserted byte-equal to the committed blob'],
              ['offline presentation fixture, not gameplay or packaged-build acceptance']),
    criterion('C7', 'S07-step4', 'independent review of the four-method delta',
              'pass',
              ['delegate_task leaf reviewer, disjoint from the implementer, bound to renderer sha256 9aff3414'],
              [0],
              ['artifacts/s07-runtime-final/INDEPENDENT-MOTION-REVIEW.json'],
              ['the review measured the renderer hash before and after and re-derived the AST diff itself',
               'its findings were checked rather than accepted: the record-consistency finding reproduced exactly (the published hash matched no committed state)'],
              ['no native GL or pixel execution by the reviewer',
               'one review finding about mixed-fleet legacy trail state is recorded as unmeasured, not as pass'],
              note='overall pass_with_findings, no blocking findings; two record findings fixed in place, one coverage finding left open and labelled'),
    criterion('C8', 'S07-step1/5', 'registration and approval guards migrated to the scaffold authority without weakening',
              'pass',
              ['env -u SDL_VIDEODRIVER -u STAR_ARMADA_FIXED_MATERIALS PYTHONPATH=tests .venv/bin/python -m unittest '
               'test_s07_approval_preservation test_s07_registration test_s07_scaffold_registration '
               'test_s06_appearance_records test_s07_motion_order test_s07_material_parity '
               'test_s07_authored_lod_parity test_s07_capture_transition test_s07_construction_runtime '
               'test_s07_hidden_contact_acceptance test_s07_binding_routes test_s07_lod_environment '
               'test_s07_selected_geometry_matrix'],
              [0],
              ['artifacts/s07-runtime-final/guard-family-final.log',
               'artifacts/s07-runtime-final/suite-per-module.json',
               'tests/s07_registration_assertions.py',
               'tests/test_s06_appearance_records.py'],
              ['the scaffold is excluded only after proving its own appearance decision and its separate execution authority',
               'two negative controls withdraw that authority and must be refused by the guard',
               'the command names all thirteen modules, so the result is reproducible from the receipt'],
              ['103 tests across the named guard modules, and every module also appears in the per-module gate',
               'an earlier union run recorded 269 tests in a single process but logged no module names, so that figure is superseded rather than cited']),
    criterion('C9', 'S07-step5', 'generated metadata, wrappers and sidecars reproduce',
              'pass',
              ['.venv/bin/python tools/art/sync_runtime_metadata.py --check',
               '.venv/bin/python tools/art/gen_export_wrappers.py --check',
               '.venv/bin/python tools/art/write_pending_sidecars.py --check'],
              [0, 0, 0],
              ['art/manifests/pipeline.json'],
              ['each tool reports its own exit status; no text matching over generated files'],
              ['reproducibility on this checkout, not on a fresh clone with autocrlf']),
    criterion('C10', 'S07-step5', 'model contract validation satisfied for the whole catalogue',
              'pass',
              ['.venv/bin/python tools/art/validate-models --all'],
              [0],
              ['art/manifests/pipeline.json'],
              ['a missing contract validator is a failure, not a skip'],
              ['build-side and contract checks only; not packaging']),
    criterion('C11', 'S07-step5', 'menu movie tests and simulation determinism',
              'pass',
              ['.venv/bin/python -m pytest -q -rs tests/test_menu_movie.py',
               'PYTHONPATH=tests .venv/bin/python -m unittest test_detmath'],
              [0, 0],
              ['artifacts/s07-runtime-final/suite-per-module.json'],
              ['the two skips are read and named rather than inferred; the skipped 360-frame bake was run separately as C6',
               'both counts are read from the gate receipt, where test_menu_movie records 31 passed and 2 skipped'],
              ['the skipped tests themselves were not executed under pytest']),
    criterion('C12', 'S07-step5', 'suite green on the final tree apart from recorded pre-existing failures',
              'pass_with_recorded_pre_existing_failure' if not suite['in_scope_failures'] else 'fail',
              ['.venv/bin/python artifacts/s07-runtime-final/run-suite-per-module.py',
               '.venv/bin/python artifacts/s07-runtime-final/record-pre-existing-failures.py'],
              [1, 0],
              ['artifacts/s07-runtime-final/suite-per-module.json',
               'artifacts/s07-runtime-final/pre-existing-failures.json',
               'artifacts/s07-runtime-final/gl-modules-separate-processes.json'],
              ['this receipt refuses to build while any failing module has no recorded classification',
               'every pre-existing classification was produced by re-running the same test command against a pristine extraction of the base commit, not by assertion',
               'the three modules that fail only under cold import are resolved by a declared prelude, and the unflattering isolation-only numbers are retained beside the resolved ones'],
              [f"{suite['modules']} modules, {suite['tests_ran']} tests, {suite['wall_seconds']:.0f}s wall",
               'the single-process run is recorded as not a valid gate: SDL_VIDEODRIVER=dummy is set process-wide at import, producing 18 GL errors and one test that did not complete in ~28 minutes; it was abandoned at 1910/2206',
               'the exit code 1 is expected and is the recorded pre-existing failure, not a crash'],
              note=(f"in-scope failures: {suite['in_scope_failures'] or 'none'}; pre-existing: "
                    + ', '.join(f"{f['module']} ({f['base_commit_result']['failures']} failure on the base commit)"
                                for f in suite['pre_existing_failures']))),
    criterion('C13', 'S07-step1', 'simulation state preserved across every capture and comparison',
              'pass',
              ['.venv/bin/python artifacts/s07-runtime-final/compare-captures.py (state hash assertions)'],
              [0],
              ['artifacts/s07-runtime-final/catalogue-final-vs-prefinal.json',
               'artifacts/s07-runtime-final/matrix-final-vs-prefinal.json'],
              ['the comparator fails when a capture changed the state hash'],
              ['state hashes are asserted where both reports carry them']),
    criterion('C14', 'S07-step4', 'owner decision on the only player-facing consequence of the delta',
              'pass',
              ['.venv/bin/python tools/art/validate-models --all (decision log parses)'],
              [0],
              ['art/manifests/pipeline_policy.json'],
              ['the decision records the owner words verbatim and binds to the reviewed renderer hash'],
              ['accepts a cost, authorizes no further performance or visual change']),
]

deferred = [
    {'gate': 'macOS packaging / DMG build and smoke', 'status': 'not_run',
     'reason': 'packaging is a separate owner gate and was not authorized in S07'},
    {'gate': 'Windows native graphics and packaged-build acceptance', 'status': 'not_run',
     'reason': 'no Windows host in this workstream; S09 owns platform acceptance'},
    {'gate': 'interactive performance / FPS targets', 'status': 'not_run',
     'reason': 'S08 owns performance; this receipt accepts a draw-cost change but measures no frame rate'},
    {'gate': 'S08/S09 compatibility and platform gates', 'status': 'not_run',
     'reason': 'explicitly outside S07 closure'},
    {'gate': 'merge, default activation, release', 'status': 'blocked_owner_decision',
     'reason': 'each is a separate owner gate; PR #131 stays draft'},
]

retained_failures = []
for path, note in [
    ('artifacts/s07-runtime-final/native-catalogue-final-attempt1-crash.log',
     'catalogue harness crashed on a row with data_id=None before the scaffold was explicitly excluded'),
    ('artifacts/s07-runtime-final/native-matrix-attempt1.txt',
     'first matrix run produced captures not bound to renderer bytes; the harness was given a renderer hash and re-run'),
    ('artifacts/s07-runtime-final/reconcile-parity-pin-v1-failure.log',
     'reconciliation asserted four protected methods equal B5 and correctly caught _draw_construction_sites'),
    ('artifacts/s07-runtime-final/full-suite-final-opaque-aborted.log',
     'first full-suite attempt emitted one character per test, so a stall was indistinguishable from '
     'slowness; abandoned at 1910/2206 after the log froze for over five minutes'),
    ('artifacts/s07-runtime-final/full-suite-bounded.log',
     'second full-suite attempt was bounded and instrumented, but hung in a GL test because a module '
     'import had set SDL_VIDEODRIVER=dummy process-wide; abandoned at 1910/2206 after a 1688s stall'),
    ('artifacts/s07-runtime-final/suite-per-module-isolation-only.json',
     'first per-module sweep counted three pytest-style modules as passing while they contributed zero '
     'tests, and blamed three modules for a pre-existing circular import; kept as the unflattering '
     'first attempt, superseded by suite-per-module.json'),
]:
    if (ROOT / path).exists():
        retained_failures.append({'evidence': need(ROOT / path), 'note': note})
retained_failures.append({
    'evidence': need(ART / 'candidate-movie-final-vs-prefinal.json'),
    'note': ('the pre-repair candidate movie is byte-identical to the final one across 360 frames; that is a '
             'consequence of the uncached draw path having no production call site, and it is recorded as a '
             'limitation of what the movie gate proves, not as evidence the changed code was exercised'),
})

preservation = {
    'renderer_protected_methods_ast_equal_to_published_checkpoint': True,
    'renderer_pin_names_the_bytes_measured_here': renderer_sha == RENDERER_PIN,
    'approved_paths_byte_equal_to_published_checkpoint': 'asserted per path by reconcile-parity-pin.py',
    'earlier_correction_blocks_retained': ['s07_renderer_pin_correction',
                                           's07_authored_parity_pin_correction (superseded_by pointer only)'],
    'shipped_movie_unchanged': True,
    'simulation_state_unchanged': True,
    'approved_geometry_or_source_modified': False,
    'tolerance_or_acceptance_criterion_relaxed': False,
}

blocking = [c['id'] for c in criteria if c['status'] in ('fail', 'unproven')]
overall = 'pass' if not blocking else 'fail'

receipt = {
    'schema': 1,
    'candidate_commit': CANDIDATE_COMMIT,
    'candidate_state': ('published HEAD plus an uncommitted working-tree increment; the renderer bytes this '
                        'receipt is bound to are the working-tree bytes, hashed above'),
    'renderer_sha256': renderer_sha,
    'scope': ('S07 opt-in catalogue closure: motion/ownership repair of four renderer methods, the pin record, '
              'native runtime evidence at the final bytes, the candidate movie, one independent review, and the '
              'owner decision accepting the only player-facing consequence'),
    'authority_decision_ids': ['s07-opt-in-continuation-2026-10-18',
                               's07-scaffold-registration-2026-10-19',
                               's07-authored-lod-cost-2026-10-19'],
    'candidate_binding_count': len(bindings),
    'candidate_bindings': bindings,
    'criteria': criteria,
    'preservation': preservation,
    'retained_failed_attempts': retained_failures,
    'deferred_gates': deferred,
    'suite_gate': suite,
    'pre_existing_failures': suite['pre_existing_failures'],
    'criteria_not_passing': blocking,
    'overall_status': overall,
    'what_this_receipt_does_not_prove': [
        'that the phased-motion branch or _draw_station run in the shipped runtime: neither has a production call site, so the repair is latent there',
        'any frame-rate, interactive or Windows behaviour',
        'packaged-build or default-activation behaviour',
        'that the changed code path is exercised by the capture evidence; the motion-transition harness exercises it, the stationary sets cannot',
        'a green suite in a single process: that configuration is broken in this environment by a module that sets SDL_VIDEODRIVER=dummy at import, and the gate here is per module instead',
    ],
}

out = ART / 'S07-FINAL-RECEIPT.json'
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'overall_status': overall, 'criteria': len(criteria),
                  'bindings': len(bindings), 'not_passing': blocking,
                  'suite': suite, 'receipt': rel(out), 'receipt_sha256': sha(out)}, indent=1))
