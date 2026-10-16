# S04 — generic opt-in preview evidence

Status: **engineering checks passing locally; independent review/publication pending**.
No merge, tag, release, new model approval or S11 authorization is implied.

## Captures

`verification.json` contains the exact recipe, cameras, display configuration, render-source hashes,
mesh hashes, repeated-frame checks and simulation digests for all three variants:

- Prototype baseline: archive of `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c`.
- Generic opt-in preview: candidate source tree (identified by the report's complete render-source hashes).
- Legacy default: same candidate tree with preview disabled; negative control.

Eight views (common-scale, three close, three rear and tactical) have **zero differing preview
channels**; every legacy view differs. Each frame repeated identically and rendering preserved the
same simulation digest: `549ae8fa52c544d00a46c2b01f35d9dcdffbecdb4b487abb52bcec23eeb2071d`.

Actual Cocoa/OpenGL on Apple M4, 1280×800, 4× MSAA, production shaders, normal fog. The three retained
full-resolution preview images and `review-sheet.png` were inspected. The sheet's upper/middle rows
are prototype/generic preview; its bottom row is legacy, not another authored proposal.

This settles S04's unchanged-specimen control at frozen frames. It does **not** close S05's full
motion/combat/owner-colour matrix or transfer any approval record, nor establish native Windows or
packaged rendering, per-feature worklight pixel measurements or performance targets.

Reproduce from the repository root using the normal venv (no Blender):

```sh
# Extract the baseline into an isolated directory first, never the live checkout.
git archive 5bddd7b67245ddff4b595bb3b477ca8ceede0a6c | tar -x -C <baseline>
.venv/bin/python artifacts/s04_generic_preview/evidence/capture.py \
  --source <baseline> --output <captures>/prototype --selection prototype
.venv/bin/python artifacts/s04_generic_preview/evidence/capture.py \
  --source <candidate> --output <captures>/preview --selection preview
.venv/bin/python artifacts/s04_generic_preview/evidence/capture.py \
  --source <candidate> --output <captures>/legacy --selection legacy
.venv/bin/python artifacts/s04_generic_preview/evidence/compare.py \
  --captures <captures> --output artifacts/s04_generic_preview
```

The capture script patches all five menu persistence paths to disposable output storage before any
consumer is constructed. It requires real GL, production materials and exactly 4× MSAA; it never
runs `main.py`, writes user saves or mutates simulation.

## Focused tests and validators

`focused-tests.txt` retains the actual 184-test run: no failures/errors, one skip. The skip is
`test_frozen_paths.TestFrozenPaths.test_every_folder_a_dev_run_writes_into_the_repo_is_ignored`,
reason `not a git checkout`: that legacy test treats a worktree's `.git` file as not a checkout.
A fresh-clone supplemental run is still required before publication; do not reinterpret this skip
as native package evidence. The exact command/module order is recorded in the handoff.

Separately executed: contract validator **36 checks / 28 negative controls / 0 skipped**;
`validate-models --all` **34/34, 0 failures/warnings**; runtime metadata synchronization check and
real-export replacement/additive fixtures pass. These validators do not run automatically in the
existing repository CI, so a future green CI result cannot substitute for them.

## Failed attempts retained

- `initial-integration-failures.txt`: six expected integration failures when the old specimen tests
  still assumed unconditional activation and mocked loader functions no longer used by the generic
  resolver. The fixtures now explicitly opt into preview and exercise real missing/corrupt files;
  no assertions were relaxed to retain unconditional production activation.
- `start-boundary-red.txt`: missing application session seam before it was implemented.
- Further observed RED slices (full output exists in the conversation, not as manufactured logs):
  missing selection module/API; lost persisted order; malformed/duplicate pack preferences accepted;
  unreachable preview row; live renderer failed to lock selection; stale CPU helpers; malformed pack
  content raised `AttributeError`; corrupt assets re-read 100 times; symlinked pack directory escaped
  the external root; GPU cache used model identity without content revision. All mapped checks now
  pass. The final GPU test also compiles the actual additive fixture in a real context.
- Resolver implementation and two review workers were interrupted by model-response timeouts.
  Their summaries were not treated as verification; parent reran tests and inspected source.

## Preservation and deferred gates

No changes to approved `.blend`, exporter or `.mesh.json` bytes. The live checkout is untouched.
All work and acceptance output live in the isolated S04 worktree/scratch snapshots. The original
inventory checker remains red for baseline provenance drift and is not silently repaired here.

Public gameplay-mod dependency discovery, hostile-update/peer/save/replay acceptance belong to S08.
Only explicit validated additive fixtures are admitted by this S04 API; the ordinary application
safely rejects additions when it has no dependency map. S09 owns full-suite/native/package acceptance.
