# STAR ARMADA — S09 acceptance plan: broad suite, measurable cost, packages, platforms

## 1. Status and authority

S09 is the engineering gate after S08's merge. **It is not accepted.** This document fixes
what has to be measured, what has been measured so far, and which parts of it the owner has
to decide rather than the implementer. It authorizes no default switch, no tag, no release and
no platform waiver.

The roadmap (§S09) and `HANDOVER-S09.md` name the eight S09 requirements. Four of them are
engineering work an implementer can run (freeze the candidate, protect the machine, run the
complete suite, build and inspect exact-candidate packages). Three are owner decisions
(performance targets/resolution, platform evidence or an explicit waiver, hardware deferral).
One — native graphics on required platforms — needs hardware this machine is not.

## 2. Frozen candidate

| Field | Value |
|---|---|
| Head | `5980890c47f973b50fc677a962242e893e96f001` |
| Tree | `b28b48ab07abe0c4b5040f4696ffaf14d7e6ef12` |
| `origin/main` tree | `b28b48ab07abe0c4b5040f4696ffaf14d7e6ef12` (identical) |
| Branch | `accept/s09-integrated-candidate` |
| Isolated checkout | `~/.hermes/cache/scratch/star-armada-s09` |
| Catalogue digest | `b06c178cc6d59c64807fa53f32b57a4db82cf6efbcaf4791b34efe350f0808c3` over 231 `assets/` JSON files |
| Renderer | `render/renderer.py` `9aff34140aa3d458eec358a2d87e64d4d4277c924ca198d507e4d29983350f3c` |
| Version | `0.15.1` |

The candidate **is** main's tree: S09 adds evidence and an acceptance instrument, no product,
renderer, asset or test byte. That is deliberate — an acceptance receipt has to bind to the
thing being accepted. Machine-readable identity, including per-file pins, is in
`artifacts/s09/CANDIDATE.json`.

Catalogue state on the candidate: 119 registry bindings, of which 103 are authored and
approved, 12 `authoring_pending` and 4 `keep_procedural_proposed` under
`s07-s06-coverage-exception-2026-10-19`. `validate-models --all` is **1034/1034 checks, zero
failures and zero warnings**; `sync_runtime_metadata --check` reads **112 files** with no mesh
write; `reconcile_model_coverage --check` reports `CHECK_OK`.

## 3. Protecting the owner's machine and data

Every broad run happened in the isolated checkout under a **native descendant-inherited write
barrier** (`sandbox-exec`) denying writes to the live playing checkout
(`~/Downloads/Project/STAR-ARMADA`) and to `~/Library/Application Support/STAR ARMADA`, with a
canary sentinel and an independent before/after inventory of both.

- The barrier's own self-test passed: 14 canary checks, `success: true`, `native_sandbox: true`,
  `changed_sources: []`. Its three `audit_violations` are the deliberate denials the self-test
  exercises, not suite writes.
- The per-module sweep recorded an **identical** user-data inventory before and after
  (`gates/userdata-before.txt` vs `gates/userdata-after.txt`) and an unchanged canary.
- No user save, replay, setting or installed pack was created, modified or deleted. Genuine
  files the owner creates while playing are not treated as pollution.

## 4. Instrument choice and what each one measured

One process cannot give attributable verdicts here: `tests/test_weapon_sfx.py` does
`os.environ.setdefault("SDL_VIDEODRIVER", "dummy")` at import, process-wide, so every later GL
module in the same process runs headless. The S07 gate already recorded that as an invalid
instrument (18 errors plus one 28-minute non-completion). Both instruments were therefore run:

| Instrument | Scope | Result | Verdict |
|---|---|---|---|
| Per-module gate, one process per module, real driver, inside the barrier | 210 modules | **2,281 tests, 208 modules pass, 2 fail**, 1,893 s | Attributable instrument |
| Single process, whole tree, inside the launcher | 2,238 tests | 6 failures, 6 errors, 9 skips, 1,213 s | **Not** usable: 10 of 12 non-ok results are launcher defects (§5.2) |
| Unprotected control over every non-ok id, same bytes | 14 tests | 12 pass, 1 failure + 1 error | Classification control |

The per-module gate is `tools/acceptance/run_suite_per_module.py`, derived from the S07 working
copy: it declares the `import game.core` prelude, records `timeout`/`no_summary` as such, and
runs the two pytest-authored modules (`test_classic_screens`, `test_menu_movie`) under pytest
and `test_classic_replays_gl` as its own `main()` script — no module is counted as a pass for
yielding zero tests.

## 5. Failure classification

### 5.1 Two real failures, both pre-existing on the candidate

| Test | Cause | Status |
|---|---|---|
| `test_gl_lifecycle.MainLifecycleTests.test_start_game_closes_old_views_before_replacement` | `AttributeError: 'SimpleNamespace' object has no attribute 'ds'` — S08 commit `e82345f` added `data_store=gm.ds` to `main.start_game`; the AST-extracted fixture (last touched in `df78eb7`, #111) builds a fake game namespace with `state` and `mission` but no `ds` | Real defect, introduced by the S08 merge and missed because S08's gate ran 18 selected modules and never ran the whole suite |
| `test_crew_recovery_ui.RecoveryUITests.test_faction_transports_have_small_known_solid_visuals` | `'imperial:convoy' != 'box'` — the guard still expects the legacy box fallback for the Imperial crew transport, contradicting `s06-imperial-convoy-parity-2026-10-18` | Real defect, already recorded as pre-existing in `artifacts/s07-runtime-final/pre-existing-failures.json` |

Both reproduce in a fresh process on a real driver and in the unprotected control on the same
bytes. Neither is caused by S09's evidence additions.

### 5.2 Ten results that were defects in my instrument, not the tree

| IDs | Mechanism |
|---|---|
| `test_asset_contract` (setUpClass, 4 tests), `test_b6_sidecar_reproduction…test_b6_sidecars_reproduce_from_the_real_batch_check` | The launcher rewraps every child started with `sys.executable` into itself; that re-entry imports pygame, whose greeting lands on the child's stdout, so the tool's JSON no longer starts at column 1 |
| `test_s07_binding_routes…test_cli_is_read_only_and_runs_without_pythonpath` | The same rewrite injects `sys.path` into a child whose contract is to run without `PYTHONPATH` |
| `test_s08_pack_safety` (snapshot-after-corruption, symlink loops) | The barrier's `Path.resolve()` on the write target raises on the deliberately looping symlinks the fixtures create |
| `test_ship_material_passes` (4 tests) | `setUp` reports "Could not allocate fleet shader" only when the whole tree runs in one process; the module passes in a fresh process under the same barrier |

All ten pass unprotected on the same bytes. A protected single-process run therefore cannot be
cited as the S09 suite verdict; the per-module sweep is.

### 5.3 Skips

Nine, all with a recorded reason: seven require the native Windows kernel
(`test_replay_deletion_windows`), one is a fixture with shields already fitted
(`test_jump_travel`), and one — `test_frozen_paths…test_every_folder_a_dev_run_writes_into_the_repo_is_ignored`
— skipped because a linked worktree has `.git` as a file. **That last one is outstanding, not a
pass**: it has to be run in a real checkout.

## 6. Performance: measured baseline, unagreed target

The repository's measured Mac baseline (Apple M4, Cocoa, real 1280×800 drawable, actual 4× MSAA,
synchronized diagnostic frame cost, **not** interactive FPS) is:

| Workload | Frame mean | Frame p95 | Source |
|---|---:|---:|---|
| Stock distributed (212 entities) | 93.19 ms | 101.56 ms | `GRAPHICS_BENCHMARK.md` §7 |
| Stock combat (52 combat hulls) | 109.01 ms | 117.26 ms | `GRAPHICS_BENCHMARK.md` §7 |
| Stress distributed (760 entities) | 421.74 ms | 444.16 ms | `GRAPHICS_BENCHMARK.md` §3 |
| Stress combat | 544.31 ms | 766.39 ms | `GRAPHICS_BENCHMARK.md` §3 |

`GRAPHICS_UPGRADE_PLAN.md` records **proposed, expressly not agreed** discussion targets: 60 FPS
(16.67 ms) in normal gameplay and at least 30 FPS (33.33 ms) in the supported heavy battle. The
measured stock scenes miss those by roughly 5-7×. S09 must not adopt them as approved, and must
not start an open-ended optimization detour to chase them.

**Owner decision required:** the target resolution and the frame budget S09 is measured against,
on named hardware. Until that answer exists, no performance *acceptance* can be claimed; only
measurement can be reported.

## 7. Packaging gate

An S09 package must be built from this exact candidate and inspected, not merely produced:
runtime assets, manifests and hashes present inside the frozen product; `sys._MEIPASS` lookup
working; read-only bundle behaviour; an external writable mod root; no `art/blender/` sources or
`tools/art` authoring tools inside the bundle; and smoke runs without Blender or a source
checkout on a clean install and over a copied existing-user-data profile. `star_armada.spec`
bundles `assets` only, which is the right shape, but **no S09 package exists yet** and the
workflow's manual package job is skipped, not passed.

## 8. Platform gate

Native Windows graphics, the Windows half of the S03 pipeline (D3: a fresh-clone rebuild with
repeated byte-stable approved exports), and native Windows package smoke remain unproven. Hosted
Windows LAN CI is a different, narrower check. Filip's laptop and physical mixed-machine play
stay deferred unless the owner reauthorizes that hardware. A missing platform result is a
blocker or an explicitly attributable owner waiver — never an inferred pass.

## 9. Exit criteria

S09 can be accepted only when all of the following are true and bound to this candidate or its
successor:

1. Suite verdict from an attributable instrument, with every non-ok result classified against an
   executed control, and every instrument defect named rather than counted (§4, §5).
2. Owner-agreed targets and resolution, with measured cost against them and quality unchanged.
3. Exact-candidate Mac and Windows packages inspected inside the bundle and smoke-run in clean
   and existing-user-data scenarios.
4. Native graphics evidence on the required platforms, or an explicit owner waiver naming what is
   waived.
5. Outstanding blockers listed with who owns them: the two recorded test failures, the
   `test_frozen_paths` checkout re-run, D3's Windows half, packaging, native Windows graphics.

## 10. Open owner decisions

- **D-S09-1 — performance target.** Which resolution and frame budget should S09 be measured
  against, on which hardware? Options: adopt the proposed 60/30 FPS discussion targets; set a
  scene-specific budget from the measured baseline (e.g. hold stock scenes at today's cost and
  require no regression); or defer numerical acceptance and report measurement only.
- **D-S09-2 — platform evidence.** Windows graphics and package acceptance is unproven and this
  machine cannot produce it. Options: authorize the work when Windows hardware is available;
  record an explicit time-boxed waiver covering native Windows graphics/package acceptance only;
  or hold S09 open as blocked on that evidence.

Both are recorded here as questions, not as answers. No part of this document is an approval.
