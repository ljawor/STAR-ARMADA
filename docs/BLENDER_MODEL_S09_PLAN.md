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

`GRAPHICS_UPGRADE_PLAN.md` recorded those numbers as **proposed, expressly not agreed**. On
2026-10-19 the owner adopted them as S09's measurement reference
(`s09-performance-target-2026-10-19` in `art/manifests/pipeline_policy.json`): **60 FPS /
16.67 ms in normal gameplay and at least 30 FPS / 33.33 ms in the supported heavy battle**, at
1280×800 on this M4, with no quality, MSAA, fog or workload reduction permitted to reach them.

### 6.1 Measured against that reference

`tools/acceptance/measure_catalogue_cost.py` configures the real selection seam and then calls the
real benchmark CLI, so the same instrument measured both selections: three serial fresh processes
per fixture and selection, 10 warmup + 60 measured ticks, requested and actual MSAA 4, 1280×800,
vsync 0, shader on. Medians of the three per-trial means, in ms; synchronized diagnostic frame
cost, **not** interactive FPS.

| Fixture | Entities | Frames, legacy | Frames, authored catalogue | Ratio | Sim | World | Camera |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stock distributed | 212 | 41.97 | 188.22 | 4.48× | unchanged | 9.95× | 10.92× |
| Stock combat | 212 | 56.87 | 292.73 | 5.15× | unchanged | 8.88× | 10.52× |
| Stress distributed | 760 | 113.07 | 705.09 | 6.24× | unchanged | 12.7× | 15.64× |
| Stress combat | 760 | 353.25 | 2,034.36 | 5.76× | unchanged | 14.33× | 15.57× |

Full per-stage medians, p95/p99 and hashes: `artifacts/s09/PERFORMANCE.json`.

Three results matter more than the frame numbers:

1. **The adopted reference is not met by either selection.** Legacy is 2.5-21× over 16.67 ms
   depending on scene; the authored catalogue is 11-122× over. Normal gameplay at 60 FPS is not
   reachable at this scale on this machine today, with or without the Blender catalogue.
2. **The catalogue's own cost is render-side and roughly 5-6×.** Simulation (20.79 → 20.29 ms),
   HUD (5.38 → 5.06 ms) and LAN checksum (9.17 → 8.84 ms) are unchanged on stock combat; the world
   stage goes 27.65 → 245.03 ms and the camera stage 1.60 → 16.64 ms. The camera growth and the
   world growth are separate suspects: denser triangle payload for display-list replay, and
   per-entity bounds work over authored meshes. Both are hypotheses recorded as such, not
   conclusions.
3. **Determinism is preserved.** Initial and final `state_sha256` values and LAN precise checksums
   are identical between the two selections on all four fixtures and stable across all three
   trials. The catalogue is a view.

This is an S09 **result and a blocker**, not an authorization: no renderer change, quality
reduction or fixture edit may be made to reach the reference. The 93.19 / 109.01 ms figures in
`GRAPHICS_BENCHMARK.md` §7 are the pre-#113 baseline; today's legacy measures 41.97 / 56.87 ms,
consistent with the post-optimization 38.84 / 51.22 ms in `GRAPHICS_DRAW_SCOPE_REUSE.md` §3.

## 7. Packaging gate

An S09 package must be built from this exact candidate and inspected, not merely produced:
runtime assets, manifests and hashes present inside the frozen product; `sys._MEIPASS` lookup
working; read-only bundle behaviour; an external writable mod root; no `art/blender/` sources or
`tools/art` authoring tools inside the bundle; and smoke runs without Blender or a source
checkout on a clean install and over a copied existing-user-data profile.

### 7.1 Measured — the gate fails

Built from this candidate with PyInstaller 6.22.3 (`star_armada.spec --noconfirm`): 422 files,
133 MB, `assets` only. Bundle closure is **complete** — 103 selectable bindings, 103 bundled
manifests, 103 mesh payloads hash-verified against their manifest pins (21 MB), all three schemas
present, and no `tools/`, `tests/`, handoffs or `.blend` inside. `artifacts/s09/package/PACKAGE.json`
and `frozen-closure.json`.

The frozen package runs with the **legacy** default: `--smoke` under an isolated `HOME` reaches
`SMOKE_OK` at t=30 s and writes a real in-game capture (`frozen-smoke-legacy.png`).

The frozen package **cannot start with the authored catalogue selected**:

```
render.asset_registry.AssetError: E_SYMLINK_ESCAPE: path: assets/models/schemas/model-manifest.schema.json
  main.py:293 start_game -> asset_selection.configure_from_settings -> asset_registry.AssetResolver.__init__ -> _safe()
[PYI-38430:ERROR] Failed to execute script 'main' due to unhandled exception
```

Cause, isolated with a read-only probe against the built bundle: PyInstaller 6 lays a macOS
`.app` out with `Contents/Frameworks` as `sys._MEIPASS` and `Contents/Frameworks/assets` as a
symlink to `../Resources/assets`. `render/menus.py:28` sets `ASSET_ROOT = sys._MEIPASS`, so the
resolver's root is `Frameworks` while every real asset lives in `Resources`; `_safe()` resolves
symlinks and refuses any path whose realpath leaves the root, so the resolver rejects its own
bundled assets. `AssetResolver(Contents/Frameworks)` raises `E_SYMLINK_ESCAPE`;
`AssetResolver(Contents/Resources)` loads 119 bindings and 103 manifests without complaint. The
shipped data is correct — the root is wrong.

This is a **pre-existing packaging defect**, not an S09 regression: the default never constructs
the resolver, which is why it has been invisible until a package was built with selection enabled.
It blocks S11 outright — a default switch would ship a macOS build that raises an unhandled
exception in `start_game` before the first frame. The fix is product code and therefore outside
this step's authorization; the shape that the probe supports is resolving `ASSET_ROOT` to the
directory owning the real assets tree when frozen, with the escaping-symlink alternative rejected
because it weakens the containment check S08 hardened. **The fix has not been applied or run.**

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
   *Status: measured (§6.1) with a recorded reference; the reference is **not met**, so this
   criterion is open, not satisfied.*
3. Exact-candidate Mac and Windows packages inspected inside the bundle and smoke-run in clean
   and existing-user-data scenarios. *Status: the Mac package builds, closes over its assets and
   smoke-runs legacy, but crashes on the authored selection (§7.1); Windows unbuilt. Open.*
4. Native graphics evidence on the required platforms, or an explicit owner waiver naming what is
   waived.
5. Outstanding blockers listed with who owns them: the two recorded test failures, the
   `test_frozen_paths` checkout re-run, D3's Windows half, packaging, native Windows graphics.

## 10. Owner decisions recorded

Both questions were put to the owner as pick-one options and answered on 2026-10-19. The records
live in `art/manifests/pipeline_policy.json`, with the selected option text kept verbatim beside
the parsed decision.

- **`s09-performance-target-2026-10-19` (D-S09-1)** — the 60 FPS / 30 FPS reference is adopted as
  S09's measurement reference at 1280×800 on this M4. The record also carries the measured context
  shown beside the option, and states that it authorizes no quality reduction, no workload edit and
  no optimization project. Consequence: the reference is not met (§6.1), and S09 reports the gap
  instead of claiming performance acceptance.
- **`s09-platform-waiver-2026-10-19` (D-S09-2)** — a scoped waiver covers **native Windows graphics
  evidence and native Windows package smoke** only. It does **not** cover the Windows half of the
  S03 pipeline (D3), the native-Windows skip rows, mixed-machine play, the Mac package, the suite or
  the performance reference. Those stay requirements or blockers.

Neither record authorizes a merge, tag, release or default switch; S10 and S11 remain unauthorized.
