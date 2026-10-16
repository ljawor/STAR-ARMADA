# The model authoring pipeline

Three commands, one implementation (`model_pipeline.py`), for macOS, Windows and Linux. They
build, export and validate the catalogue's Blender assets without ever touching the player's
saved data and without hardcoding a Blender install.

```
python3 tools/art/build-model     --asset rebel:battleship
python3 tools/art/build-model     --batch approved-trio
python3 tools/art/export-model    --asset rebel:battleship
python3 tools/art/validate-models --all
```

`build-model`, `export-model` and `validate-models` are those three commands by name; they forward
to `model_pipeline.py`, so the three cannot drift apart. Ordinary gameplay tests never need Blender
— only `build-model` and `export-model` do.

Read the policy they implement first: `art/manifests/pipeline_policy.json`
(decision `s03-pipeline-policy-2026-10-16`) and the acceptance table in
`art/manifests/handoffs/S03-PIPELINE.md`.

## The registry

`art/manifests/pipeline.json` says, per asset: the binding, which authority owns the source
(`script` = rebuilt from code, `blend` = the `.blend` is the master), the exporter, the runtime
export, the recorded triangle count, the material roles, and **which record holds the approved
bytes**. Approved hashes are never copied into this file — they are read from the record it names,
so the two cannot drift apart.

## What each command guarantees

| Command | Guarantee |
|---|---|
| `build-model` | Regenerates a *script-authoritative* asset from code, then verifies the runtime export against the approved bytes. A rebuild that changes what the owner approved **fails** instead of landing quietly. A regenerated `.blend` whose runtime bytes are unchanged is restored from Git, so an approved binary is never left modified for no reason. |
| `export-model` | Produces the runtime export **without touching the declared source**. A script-authoritative asset is exported inside a throwaway copy of the tree; a blend-authoritative asset's export script is refused unless it genuinely opens the source and never saves it. |
| `validate-models` | The S02 contract validator (`validate_contract.py`) plus the build-side checks: registry shape and path safety, approved runtime *and* source hashes, payload sanity (triangle count versus batch rows, envelope, material roles), provenance freshness, tree hygiene (no autosaves or temporary files under the source roots) and packaging (editable sources and tools stay out of the frozen build). If the contract validator is missing it fails: it is not a second opinion. |

Every command writes `art/manifests/provenance/<binding>.json`: the toolchain, the source and
runtime hashes, the exporter hash, the coordinate policy, the host and — for `export-model` — the
note that nothing in the repository's source was written. Commit it with the change.

## Blender

Discovery order, never a path hardcoded in code:

1. `--blender /path/to/blender`
2. `$STAR_ARMADA_BLENDER`
3. `blender` on `PATH`
4. the per-platform candidates in `art/manifests/pipeline.json` (add your install there)

The pinned version is `5.0.1`. A different version is refused unless you pass
`--allow-blender-mismatch`, and the version actually used is recorded in the provenance.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | satisfied |
| 1 | failed — a real problem (missing file, hash mismatch, contract failure) |
| 2 | refused — the request contradicts the policy (e.g. `build-model` on a blend-authoritative asset, or an export script that saves its source) |

## Notes

- `validate-models --no-contract` runs the build-side checks only and says so in a warning. Local
  iteration only: it is not acceptance evidence.
- `validate-models --allow-source-drift` downgrades a stale approved `.blend` hash to a warning.
- No command writes user data, and none of this imports the game or the renderer: it runs Blender
  and hashes files. `tests/test_model_pipeline.py` enforces both.
- The exported `.blend` files are Blender's own binary output and are **not** byte-reproducible
  between runs; the runtime export is. That is why the pipeline verifies the runtime bytes and
  treats the source as a rebuildable artifact.
