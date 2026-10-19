# Handover prompt — STAR ARMADA, S06 complete, S10/S11 landing is the only open item

Paste this as the first message of a new chat (or point the new chat at this file and say "continue here").

---

## What you are picking up

The S06 model migration is **complete as batch work** and nothing has been landed. Eleven of eleven Imperial
rows are authored, eight of them carry the owner's appearance approval, every earlier faction's rows were
approved in B1–B5, and the branch's CI is green. The single remaining item is a decision the owner has not
made: **the S10/S11 landing/registration decision** — moving approved revisions from `pending` records into
`art/manifests/pipeline.json` and the runtime registry.

Read these first, in this order:
1. `art/manifests/handoffs/S06-B6-IMPERIAL-SHIPS.md` — the batch's scope and what it settled.
2. `art/manifests/approvals.json` — the decision log. Ten appearance decisions, 73 specimens, each bound by
   hash to the blend, the mesh, the seed, the shared helper, the wrapper and (where a picture was made) the
   evidence harness. Read the `correction` blocks: three of them record honest repairs.
3. `art/manifests/pipeline_policy.json` — the standing decisions, including `s06-small-prop-class-2026-10-17`,
   `s06-imperial-convoy-parity-2026-10-18` and `s06-large-evidence-accepted-2026-10-17`.
4. `docs/BLENDER_MODEL_MIGRATION_ROADMAP.md` (in the `star-armada-docs` worktree, PR #128) — the ledger.

## Where the work is

- Code worktree: `/Users/lukaszjawor/.hermes/cache/scratch/star-armada-s06`, branch
  `feat/s06-next-model-batch`, **draft PR #127**. Head at handover: `5cc3a25` (remote-verified).
- Docs worktree: `/Users/lukaszjawor/.hermes/cache/scratch/star-armada-docs`, branch
  `docs/s06-ledger-catchup`, **draft PR #128**.
- The owner's live checkout is untouched; all work has been in these scratch worktrees.
- Environment: `.venv/bin/python`; tests with `PYTHONPATH=tests`; GL runs with `env -u SDL_VIDEODRIVER`;
  Blender at `/Applications/Blender.app/Contents/MacOS/Blender`.

## The two open items

1. **S10/S11 landing decision (owner's, blocks production).** Nothing is registered: every approved row's
   registry entry still reads `procedural_legacy` (or `authoring_pending`), no manifest exists for any
   pending row, and `art/manifests/pipeline.json` does not name them. Landing means writing manifests,
   flipping registry status, adding pipeline entries and a release — in that order, with the owner's word.
2. **An intermittent in the LAN suite (optional).** `test_lan_launch_recovery` →
   `test_lost_or_partial_start_recovers_original_slots_before_tick_zero` (`humans=4, partial=True`) fails
   at `assertFalse(session.advance(manager, 600.0))` roughly 1 in 30 standalone and 1 in 4 in-suite, 0 in 12
   against a pristine `origin/main`. Not caused by this branch; same shape as the barrier bug fixed in
   `eacee7c`. Evidence: `artifacts/ci-local/`.

## Verify the state before you touch anything

```bash
cd /Users/lukaszjawor/.hermes/cache/scratch/star-armada-s06
env -u SDL_VIDEODRIVER PYTHONPATH=tests .venv/bin/python -m unittest \
  test_alliance_blender_b6_imperial_ships test_imperial_convoy_gate test_s06_appearance_records \
  test_faction_visuals test_lan_production_reconnect test_alliance_blender_b5_asteroid \
  test_alliance_blender_b4_hardware test_alliance_blender_b3c_stations test_s06_placement_repairs \
  test_alliance_blender_b3b_stations test_alliance_blender_b3_stations test_alliance_blender_b2_squadron \
  test_alliance_blender_b1_combat test_alliance_blender_cruiser test_alliance_blender_trio \
  test_alliance_blender_battleship test_asset_contract test_model_pipeline test_generic_model_preview \
  test_model_context_lifecycle            # 342 tests, OK at 5cc3a25
PYTHONPATH=tests .venv/bin/python tools/art/validate-models --all --no-contract   # 33/33
PYTHONPATH=tests .venv/bin/python tools/art/write_pending_sidecars.py --check     # 0 stale
.venv/bin/python tools/art/gen_export_wrappers.py --check                          # 0 written
.venv/bin/python tools/ci_local.py                        # local stand-in for the CI job
PYTHONPATH=tests .venv/bin/python tools/art/probe_b6_servability.py imperial:convoy   # SERVING_OK
```

## The rules this work is held to — do not relearn them

- **Appearance approval is not landing.** A decision records that the owner looked at a picture and said
  yes. It keeps `owner_decision` null, `activation` false, the registry row `procedural_legacy`, and adds
  only an `appearance_decision` key. Never infer authorization from anything else.
- **Nothing gets approved without a picture.** Every approval in the log followed a legacy-vs-authored
  review sheet from the real application. Numbers, serving proofs and green tests are not approval.
- **A batch sheet and its decision name the same rows.** A sheet cannot honestly name two sets, which is
  why the B6 batch carries one decision covering all eight approved rows rather than one per picture.
- **A pending row carries a mesh and no manifest.** A manifest is the landing artifact; writing one early
  turns five shared guards red, and they are right. Reviewers are shown a candidate by patching selection
  in a preview session, never by registering anything.
- **Never edit `tools/art/alliance_common.py`,** not even one line: every approval record names it as
  `source`. Put per-row behaviour in the row's own seed or its generated wrapper.
- **A change to a generated file must be byte-identical for every file outside the change.** Approval
  records hash the generated wrapper they name. `gen_export_wrappers.py --check` must print `0 written`.
- **Take approval pins at commit time, not write time.** A decision that pins a shared file the batch
  keeps editing goes stale every time a row lands. Three corrections exist because of this.
- **Read CI the moment a head fails**; GitHub purges job logs within hours. A job with an empty step list
  and a failure conclusion is a billing block, not a test result.
- **Never weaken a guard to make it pass.** If a guard fails on geometry, change the geometry. The guard is
  the specification: several of them caught real defects, including a regression the convoy seam landed.
- **Work in the scratch worktree, never the owner's live checkout**, and never commit to `main` — deliver
  through the draft PRs.

## How the owner works

Terse messages, often with a screenshot: "left one is better", "picture approved", "option 1", "continue".
Treat them as intent, diagnose from the image, and when a one-word message could mean two opposite things
("passed" meant the CI result *or* the prop clearing the bar), put it back as an explicit choice rather
than guessing — that is exactly what happened for the B5 asteroid prop. He approves on pictures, one row
at a time, and expects the record to say what he was shown and what he said, verbatim.
