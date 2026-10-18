# Handover — S06 coverage reconciliation; S07 is next after remaining art

## What you are picking up

**Correction of the previous handover, October 18, 2026.** Its title and assertions that
S06 was complete, eleven Imperial rows were authored, ten batch appearance decisions existed,
and only an S10/S11 landing decision remained were wrong. The previous version is retained in
Git at `4ffdc600306ecdf4f35265fca689b495e35dd3fe`; the owner's approvals are not rewritten.
This correction follows the owner's `agree. Let do this`, accepting the bounded reconciliation
and S07-planning task. It is not registration/default-switch/merge/release authorization.

Read first:
1. Project skill and roadmap sections 6 and 8 (the corrected roadmap is in draft PR #128).
2. `art/manifests/reviews/S06-COVERAGE-RECONCILIATION.md` and `.json` on this branch.
3. `docs/BLENDER_MODEL_S07_PLAN.md` — bounded prerequisites, ownership and acceptance gates.
4. `art/manifests/approvals.json`, `pipeline_policy.json`, `pipeline.json` and the runtime registry.
5. `S06-B6-IMPERIAL-SHIPS.md`, the S01 inventory/scope record, S02 contract and S03 authority policy.

The tree and revision-bound approvals win over historical ledger prose. S00–S05 are closed;
do not rerun completed model reviews while the approved bytes remain unchanged.

## Where the work is

- Implementation: `~/.hermes/cache/scratch/star-armada-s06`, `feat/s06-next-model-batch`,
  draft PR #127; audited exact head `4ffdc600306ecdf4f35265fca689b495e35dd3fe`, clean.
- Reconciliation: `~/.hermes/cache/scratch/star-armada-s07-plan`,
  `docs/s06-coverage-s07-plan`, based exactly on that implementation head. This branch owns
  coverage tool/tests/report, the S07 plan and these corrections; no assets or runtime move.
- Roadmap: `~/.hermes/cache/scratch/star-armada-docs`, `docs/s06-ledger-catchup`, draft PR #128;
  starting head `8c67396950e3a8ba3afe728656ca54beb295dde0`. Only the roadmap changes there.
- Fetch/read each PR's exact pushed head before resuming. Publication receipts live in PR bodies
  and `S06-COVERAGE-S07-PLAN.md`; do not copy a later SHA into an approval record.
- The owner's live checkout is untouched and stale. Tests: `PYTHONPATH=tests .venv/bin/python
  -m unittest ...`; no pytest. Scratch worktrees may use the owner's venv by absolute path.
  Blender is pinned to 5.0.1; no Blender or GL is needed for this audit.

## The open work

1. **Finish S06 catalogue coverage.** 73 new appearance-approved specimens across nine batch
   decisions plus the original trio = 76 unique assets. Four additional trade-convoy inventory
   identities map to those candidates but are not integration-approved by this report.
2. **27 required inventory meshes lack approved assets:** eight combat hulls (five Confederacy,
   three Syndicate), ten Imperial orbital stations, eight faction constructor/colonizer hulls
   and the shared construction scaffold. Three additional planned Syndicate hulls are outside
   the historical inventory's 120 rows and lack data/model definitions. Do not infer their stats.
3. Ten texture rows are deferred to their current pipeline and three effect/movie rows are outside
   the mesh catalogue under `s06-b5-scope-2026-10-17`. These are not authored Blender meshes.
4. **S07–S09 remain open.** S07 closes opt-in integration after S06 coverage closure; S08 validates
   mods/updates/save/replay/peer compatibility; S09 owns integrated suite/performance/packages/platforms.
   Only then do S10 asset-lock/rollback review and separately authorized S11 default activation follow.

Preview registration may be separately authorized without a release. The original trio is already
registered for preview; no new S06 specimen is registered. Existing pending guards remain intact.
The next owner decision should name a bounded remaining-art batch, not a production switch.

## Verify the state before you touch anything

```bash
python3 tools/art/reconcile_model_coverage.py --check
PYTHONPATH=tests .venv/bin/python -m unittest test_model_coverage_reconciliation test_s06_appearance_records
PYTHONPATH=tests .venv/bin/python tools/art/write_pending_sidecars.py --check
.venv/bin/python tools/art/gen_export_wrappers.py --check
PYTHONPATH=tests .venv/bin/python tools/art/validate-models --all
```

**Known blocker:** the sidecar check above currently raises `FileNotFoundError` for
`tools/art/build_imperial_corvette.py` on clean audited S06 head and this branch. B6 lacks the
per-row seed declarations consumed by the generator. It is recorded, not repaired in this task.

The coverage report checks files/approval hashes, not new in-game captures. Preserve old focused
and broad-suite receipts without claiming they ran again. PR #127 workflow `39102141681` is successful
on audited head `4ffdc60`; its manual Windows package job was skipped. A later PR needs its own check.

## The rules this work is held to

- Appearance approval, opt-in registration, merge, default switch and release are separate gates.
- Preserve all approved blend/mesh/exporter bytes and owner words. No new approval is created here.
- Use inventory category/live ship data for canonical mapping, not generated sidecar `ship:` labels.
- Imperial station and ship generic consults already exist; lack of selection is not lack of a seam.
- Never edit approval-bound shared `alliance_common.py` or wrappers merely to prepare this plan.
- Keep new models pending until revision-bound appearance approval and separately authorized registration.
- Never weaken pending-registration guards; S07 must deliberately migrate them with an authorized record.
- Scratch feature branches/PRs only; explicit staging; no stash/reset/cleanup of the owner's tree/data.
- Before push: exact intended file delta, no tracked `.venv` or symlink, approvals/hash report unchanged,
  wrappers/sidecars reproduce; after push read back exact remote head/blobs and CI.
- Retain reported LAN observations (1/30 standalone, 1/4 suite, 0/12 control). Their cause is unproven;
  the old handover's categorical "not caused by this branch" was unsupported.

## How the owner works

Keep chat summaries short. Ask one gate at a time, with an enumerated bounded scope. Ambiguous words
are not approval until clarified. Existing approved pictures need no repeat review merely because
registration is not yet done. No deferred platform waiver, art exception or gameplay stat is inferred.
