# Handoff: S03 — build a durable authoring pipeline

Status: **acceptance frozen, implementation not started.** The policies and the definition of done are
agreed (`s03-pipeline-policy-2026-10-16`, `art/manifests/pipeline_policy.json`); every evidence slot
below is still empty and must be filled with real output before S03 can be called complete. Do not mark
this step done because the plan exists.

Branch / base: `docs/s03-acceptance` off `main` `dfda83f2e67931873296e9d49acc4e62a2e63bcd`
(`dfda83f`). The step itself should be implemented on a fresh branch off the then-current `main`.

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

## Definition of done — evidence slots (fill with real output)

| Id | Evidence to fill | Checked by |
|---|---|---|
| D1 | transcript of `build-model` / `export-model` / `validate-models` for one asset, for a batch, and validation-only; plus one deliberate-failure run each, showing the nonzero exit and no user-data write | machine |
| D2 | the command `validate-models` runs, and its output on the trio — it must invoke the S02 validator | machine |
| D3 | `sha256` of `assets/models/alliance_{battleship,frigate,shipyard}.mesh.json` before/after a rebuild in a **fresh clone**, and after a second export run; must equal the recorded approved hashes | machine |
| D4 | per-asset provenance record: Blender version, exporter version, source/runtime hashes, declared authority, coordinate/scale policy | machine + skim |
| D5 | `git diff --name-only origin/main -- assets/` (must be empty) plus the before/after in-game capture set — same silhouettes, worklights, aft emitters | **owner** |
| D6 | branch inventory showing no `.blend1`/autosave/temp renders/raw capture runs, and the packaging file list showing sources and tools excluded | machine |

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
