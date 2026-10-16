# S04 — generic opt-in preview evidence

Status: **review-ready, published as draft PR #124; independent review passed after one fix cycle**.
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
The fresh clone at `45e4ed3b731fde6c376fdb894088a248abc774e9` passed **184/184 with no skips**;
`fresh-clone-focused-tests.txt` and `fresh-clone-verification.json` retain that separate receipt.
Do not reinterpret either run as native package evidence. Exact module order is in the handoff.

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

Independent review initially found extreme-integer overflow, unbounded version conversion and an
optional-facade fallback regression. Separate-context RED→GREEN fixes passed parent reruns and scoped
independent re-review. Both verdicts and the fix receipt are retained; the initial failure is not erased.

## Preservation and deferred gates

No changes to approved `.blend`, exporter or `.mesh.json` bytes. The live checkout is untouched.
All work and acceptance output live in the isolated S04 worktree/scratch snapshots. The original
inventory checker remains red for baseline provenance drift and is not silently repaired here.

Public gameplay-mod dependency discovery, hostile-update/peer/save/replay acceptance belong to S08.
Only explicit validated additive fixtures are admitted by this S04 API; the ordinary application
safely rejects additions when it has no dependency map. S09 owns full-suite/native/package acceptance.

## CI integration repair and final fresh-clone receipt

Windows runs `38952034998` and `38952529212` exposed an S04 catalogue reproducibility defect.
The second also failed LAN recovery (tick 6 != 8); two immutable baseline and two immutable candidate
local repetitions passed. This is **not reproduced locally**, not proven pre-existing. No deadline
or assertion was relaxed. Both Windows logs and classifications are retained.

All four language packs now reproducibly include the six preview strings (366 UI keys, 96 names),
through authored translations and UTF-8/LF writers. The real settings pack-count row is localized.
A real autocrlf checkout then exposed conversion of hash-pinned mesh JSON and its approval evidence.
Scoped `-text` attributes now **disable conversion**, preserving committed runtime, authoring, schema
and evidence bytes; no approved mesh, Blender or exporter content changed. The intermediate failures
and RED controls are retained. This is not a broad LF normalization or a changed approval hash.

Final code: `19d63f7d677cd2cdb5b5fd60e4a9e95c810c63d5`. A fresh clone with `core.autocrlf=true` passes
**195 focused tests, no failures/errors/skips**, nine-file metadata reproduction and pipeline 34/34.
Unprotected render source really contains CRLF in that clone; language catalogues remain LF and
all eleven approved source/runtime hashes match baseline. Capture source hashes match this commit;
eight views still have zero preview differences and equal simulation hashes.
See `final-fresh-clone-tests.txt` and `final-fresh-clone-verification.json` in the evidence directory.
The final focused command extends the original module list with `test_language_tools`.
Independent review passed the language repair; parent additionally verified the byte-preserving
attribute follow-up in the real clone. Native Windows CI must pass the next pushed head; this local
checkout is not native Windows rendering/package acceptance. No full suite or S11 authorization.
