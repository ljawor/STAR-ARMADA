# S06 coverage reconciliation and S07 planning handoff

## 1. Authority and owned scope

Owner: `agree. Let do this`, accepting coverage reconciliation and an S07 integration plan.
No registration, art revision, default switch, merge or release authorization.

Audited implementation base: `4ffdc600306ecdf4f35265fca689b495e35dd3fe`, draft PR #127,
`feat/s06-next-model-batch`. New stacked branch `docs/s06-coverage-s07-plan` lives at
`~/.hermes/cache/scratch/star-armada-s07-plan`; exact pushed head is in its PR metadata.
It starts at that base and owns only the reconciliation tool/test/report, S07 plan and handoffs.
The owner's live checkout and implementation worktree are not changed.

Roadmap correction is independently published in draft PR #128 on `docs/s06-ledger-catchup`,
exact head `1909426ca23e59cf2e76d827debbb0ded402b854`. That PR changes only the roadmap.
Read the exact remote head and working-tree status before resuming; never infer them from this file.

## 2. Delivered result

- `reviews/S06-COVERAGE-RECONCILIATION.{json,md}` under `art/manifests/` accounts for all
  120 historical inventory rows: 76 approved unique assets, four shared convoy candidates,
  27 missing meshes, ten deferred textures, three outside-mesh rows.
- Nine batch appearance decisions cover 73 new specimens; the original trio adds three.
  Three planned Syndicate hulls are additional data/model work outside the historical inventory.
- `docs/BLENDER_MODEL_S07_PLAN.md` names prerequisites, file/function ownership, selected
  Imperial station consumer gaps, identity/ownership/bounds/contact/LOD/menu requirements,
  commands, evidence limits and stop gates. It is planning, not implemented integration.
- Corrected `S06-TO-S10-HANDOVER.md` and `S06-B6-IMPERIAL-SHIPS.md` retain explicit correction
  history instead of perpetuating completion/seam/count claims. No approval record is rewritten.
- All approved sources, wrappers, runtime exports, policy/approval records, data and registry
  bytes remain unchanged. Full S06 is incomplete; S00–S05 remain closed.

## 3. Verification and retained problems

Executed in the reconciliation worktree:

```bash
PYTHONPATH=tests /Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python \
  -m unittest test_model_coverage_reconciliation test_s06_appearance_records -v
python3 tools/art/reconcile_model_coverage.py --check
python3 tools/art/gen_export_wrappers.py --check
/Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python tools/art/validate-models --all
```

Results: 11 tests passed; coverage CHECK_OK; wrappers 71 up to date / 0 written;
model validation satisfied 34/34, zero failures/warnings. Corruption controls exercise stale
report and wrong approval hash against a disposable copy, asserting check mode does not repair it.
Independent static review of the two new Python files passed with no blocking findings. Initial
reviewer was interrupted with no verdict; bounded retry supplied the passing verdict. Nonblocking
suggestion: add direct source/runtime byte corruption and full input-preservation snapshots.

Known baseline blocker: `write_pending_sidecars.py --check` raises `FileNotFoundError` for
`tools/art/build_imperial_corvette.py`. Reproduced on clean audited implementation and this tree;
B6 lacks per-row seed declarations. It is not repaired here. Approved hashes still pass.
No fresh Blender/GL/full-suite/performance/package/native-platform acceptance is claimed.

Prior docs CI run `39102143276` failed on `8c67396950e3a8ba3afe728656ca54beb295dde0`:
`test_lan_production_reconnect.ProductionReconnectTests.test_normal_ticks_have_bounded_history_and_never_capture_graph_snapshots`,
`[57,57,57,57] != [100,100,100,100]`. Raw failed log retained at
`~/.hermes/cache/scratch/s06-docs-pr128-initial-ci-failure.txt` (scratch, not Git). No assertion
was weakened, and no causal classification is claimed. New roadmap run `39104695868` belongs
only to `1909426`; read its final status separately. A previous green implementation head does
not establish this branch's CI or art validation. Manual package skips are not package passes.

## 4. Next bounded task and publication checks

Recommended: repair the missing-seed reproducibility blocker, then take the ten Imperial orbital
stations as the next art batch, followed by remaining combat hulls and construction. This is a
recommendation; no new design approval or data/stat specification is inferred. Preserve existing
approvals while those bytes are unchanged. Do not skip S07–S09 to reach S10/S11.

Before push: focused checks above, exact eight-file task delta against the implementation base,
no tracked `.venv`/symlink in that delta, no modified approval/runtime/source bytes. Stage explicit
paths. Read back remote head and claim-bearing blobs after push; compare the PR file list against
that delta. Roadmap stays on its separate docs-only PR. No merge/tag/release/default switch.
