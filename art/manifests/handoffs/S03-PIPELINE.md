# Handoff: S03 — build a durable authoring pipeline

Status: **implementation complete, evidence filled — waiting on the owner's D5 review and on S02's
contract (PR #117) reaching `main`.** The policies and the definition of done were frozen first
(`s03-pipeline-policy-2026-10-16`, `art/manifests/pipeline_policy.json`); this file now carries the
receipts for what was actually run, including what could not be run here.

Branches: acceptance in `docs/s03-acceptance` (#118, merged as `fd08ac7`); implementation in
`feat/s03-authoring-pipeline` off `fd08ac7`.

Prerequisites:

- **S02's contract.** `tools/art/validate_contract.py` and `art/schemas/*` arrive with PR #117. If
  that has not merged when S03 starts, branch from it or wait — D2 requires `validate-models` to *be*
  that validator, not a second implementation.
- **S00/S01 are merged**: the three approved sources (`art/blender/alliance_*.blend`), their build
  scripts (`tools/art/build_alliance_*.py`, `alliance_common.py`) and the runtime exports
  (`assets/models/alliance_*.mesh.json`) are on `main` since `c5b78eb`, with hashes recorded in
  `art/manifests/approved-trio-source-hashes.json`.
- Blender **5.0.1** on the authoring machine. Today the build is invoked as
  `/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python
  tools/art/build_alliance_battleship.py`, one script per asset, from the repository root.

## What exists now (the gap S03 closes)

| Today | Why it is not a pipeline |
|---|---|
| three one-off exporter scripts | no single entry point; no batch mode; no validation-only mode; the Blender path is hardcoded to macOS |
| activation of the trio is hardcoded in the renderer | S04's job, but it means an export change is not visible in any registry |
| `artifacts/alliance_blender_trio/evidence/workflow.py` | a one-off harness that hardcodes the live checkout path and uses macOS-only `sandbox-exec`; useful as a record, not as tooling |
| no source-authority declaration | an exporter could overwrite hand-edited `.blend` work without anyone noticing |
| no toolchain or provenance record per asset | a rebuild on another machine is unverifiable |
| no storage decision | the first large texture would land under an undeclared policy |

## Policies in force (owner-adopted, verbatim wording in `pipeline_policy.json`)

1. **Storage:** ordinary Git; declared LFS threshold 5 MiB per file; adopt LFS only when crossed, and
   adopt it atomically (attributes + build fetching + fresh-clone check).
2. **Source authority:** blend-authoritative by default for silhouette work (export-only path, never
   overwrite hand edits); script-authoritative for repeated/modular pieces and for the approved trio.
3. **Platform:** rebuild and validate from a fresh clone on macOS **and** Windows — no
   `/Applications/Blender.app`, no `sandbox-exec`, no absolute home directories. Authoring stays macOS.

## Definition of done — receipts

All runs below are from `feat/s03-authoring-pipeline`, Blender **5.0.1**, macOS, working in a scratch
worktree. Every command is reproducible as written.

| Id | Evidence | Result |
|---|---|---|
| D1 | `python3 tools/art/build-model --batch approved-trio`, `--asset rebel:battleship`, `python3 tools/art/export-model --batch approved-trio`, `python3 tools/art/validate-models --all` / `--asset rebel:battleship` — three commands, one asset, a batch, validation-only | exit 0 each; per-asset triangle counts and hashes printed. Failure paths: no selection → `E_NO_SELECTION` exit **2**; unknown binding → `E_UNKNOWN_BINDING` exit 1; `--blender /nope/blender` → `E_NO_BLENDER` exit 1; `--blender /bin/echo` → `E_BLENDER_VERSION` exit 1; a fake `Blender 9.9.9` → `E_BLENDER_MISMATCH` exit **2** and no build. The user-data directory was hashed before and after a full rebuild: 6 files, **byte-identical**, nothing written |
| D2 | `validate-models` delegates to `tools/art/validate_contract.py` (D2 requires it to *be* that validator) | With #117's branch merged in: `validate-models: satisfied - 34/34 checks, 0 failures, 0 warnings` (exit 0) and `validate_contract.py` itself `contract satisfied: 33 checks, 25 negative controls, 0 skipped`. On this branch (before #117 reaches `main`) it **fails** with `E_NO_CONTRACT_VALIDATOR` rather than passing on its own checks — that is the intended behaviour, and the merge with #117 is clean |
| D3 | Fresh clone, plain `python3` 3.11.8, no venv, no local state: `git clone --branch feat/s03-authoring-pipeline . /tmp/sa-fresh` then `build-model --batch approved-trio` | All three exports byte-identical to the approved record: `57a5496c…`, `045d1383…`, `67d4db64…`. A second build run on the working tree reproduces the same three hashes. The only thing a rebuild dirties is `art/manifests/provenance/*` (its `recorded` timestamp) |
| D4 | `art/manifests/provenance/{rebel-battleship,rebel-frigate,rebel-shipyard}.json`, written by the commands and committed | Blender 5.0.1 and the pin, exporter path + hash, source `.blend` hash matching the approved record, runtime hash/bytes/triangles, coordinate policy, host, and the action taken (`build` vs `export`) with notes |
| D5 | `git diff --name-only origin/main -- assets/` plus the owner's capture set | Machine half: **empty** — after every build, export and validate run above, all three `.mesh.json` and all three `.blend` hashes still equal the approved record. Owner half: outstanding, see below |
| D6 | `validate-models` tree hygiene and packaging checks; branch inventory | No `.blend1`/autosave/temp file under `art/blender` or `assets/models`; `star_armada.spec` bundles `assets` only — no `art/`, no `tools/`, no `.blend`. `tests/test_model_pipeline.py` asserts the pipeline imports no `game`/`render` code and references no user-data path |

### What is *not* verified here, and must not be claimed

- **Windows rebuild.** The pipeline is structurally platform-neutral (pathlib, `subprocess` with a
  list, no `sandbox-exec`, no application path in code, Blender found by flag/env/PATH/registry) and
  its tests run inside the existing Windows CI job. But no rebuild has been executed on Windows, and
  no Windows Blender has been used. D3's Windows half stays open until Filip's machine or CI does it.
- **D2 end to end** depends on PR #117 reaching `main`; it was proven against that branch, not on
  `main`.
- **The `.blend` files are not byte-reproducible** between runs (Blender's own binary output). The
  runtime export is, which is what the pipeline verifies and what the appearance gate rests on.

## Commands to be written (names are the roadmap's proposal, not existing tools)

```
# one asset
python3 tools/art/build-model --asset rebel_battleship
python3 tools/art/export-model --asset rebel_battleship
python3 tools/art/validate-models --asset rebel_battleship

# batch, then validation only (no Blender needed)
python3 tools/art/build-model --batch approved-trio
python3 tools/art/validate-models --all
```

Expected shape: `--help`-documented, nonzero exit on any failure, no writes under the user-data
directory, and Blender located by an explicit `--blender` argument or an environment variable rather
than a hardcoded application path. Ordinary gameplay tests must not require Blender.

## Fresh-clone acceptance (to be run on both machines)

```
git clone <remote> /tmp/sa-fresh && cd /tmp/sa-fresh
# macOS and Windows: no prior state, no .venv copied from the live tree
python3 tools/art/validate-models --all          # validator only, no Blender
python3 tools/art/build-model --batch approved-trio   # requires Blender 5.0.1
sha256sum assets/models/alliance_*.mesh.json     # vs art/manifests/approved-trio-source-hashes.json
```

## Failed attempts and corrections

None yet — implementation has not started. Keep the ones that happen here rather than deleting them;
a superseded approach that is not recorded gets re-attempted by the next chat.

## Open issues / blockers

- PR #117 (the S02 contract and validator) is open for the owner's review. D2 depends on it.
- Making the harnesses Windows-clean is real work: `sandbox-exec` has no Windows equivalent, so the
  user-data write barrier needs a cross-platform mechanism (or must not be required for a plain
  rebuild + validate run).
- The packaged build's `sys._MEIPASS` asset discovery is still unverified; if `assets/` layout moves
  under section 4, S09's frozen-build check has to be re-run rather than assumed.

## Next step after S03

S04 — implement the registry, resolver and explicit preview/default boundary that S02 specifies, which
is what finally replaces the hardcoded trio activation. S05 then re-validates the trio's approved
appearance on that generic path. No catalogue batch, no activation and no production default switch
before S06/S11 respectively.
