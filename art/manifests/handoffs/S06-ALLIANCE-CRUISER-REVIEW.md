# S06 B1 — Liberty Cruiser review checkpoint

## State and authority

Branch: `feat/s06-next-model-batch`. Source/capture base: S05 merge `f873a3344553c6ec5a806b7e7ff7a843a8c321ea`. Roadmap follow-up #126 merged as `bd4709f858ae73c39cf11e33b1c6fb01a38dadfb`; its only delta is the roadmap. Read the published PR for the exact checkpoint head, not a scratch checkout or a self-referential embedded HEAD.

Owner requested: **“Merge and upatte the progress on BLENDER_MODEL_MIGRATION_ROADMAP.md and continue with S06”**. S05 and its roadmap update are merged. The first new B1 specimen is the Liberty Cruiser (`ship:rebel:cruiser` / `rebel_cruiser`), an engineering prioritization inside the previously approved B1 order. No new appearance approval is inferred from permission to continue.

**Pending owner appearance approval, not S06 completion, production integration, merge or release authorization.** The editable `.blend` is authoritative. `tools/art/build_alliance_cruiser.py` is initial seeding only; normal export is `tools/art/export_alliance_cruiser.py`, which opens the existing master and does not save it. Pending metadata lives in `art/manifests/pending/S06-ALLIANCE-CRUISER.json` and is explicitly not an approved manifest/hash receipt.

The approved pipeline requires owner-approved hashes. Therefore this pending specimen is deliberately absent from `pipeline.json`, `approvals.json`, the runtime registry and bundled approval receipts. `build-model --asset rebel:cruiser` is not yet supported. Do not register a purported approved hash to make that command green. After explicit approval, bind the reviewed source/runtime revision and export-only workflow atomically through the existing contract.

## Artifacts and verification

- Editable master, original seed, export-only tool, runtime mesh, focused tests and review-only capture harness are preserved together.
- Runtime: 6,264 triangles, 3,492 vertices, 409,447 bytes. SHA-256 `38b4e9f92040e67ffc1655910de39c24de4156397a94c76c34f94738a383ba84`.
- Four focused geometry/source/emitter/corruption tests passed independently in the parent invocation.
- Parent independently exported twice using resolved Blender 5.0.1: both match runtime bytes; master hash unchanged. Commands and outputs: `artifacts/s06_alliance_cruiser_review/parent-run/reproducibility.json` and `export-{1,2}.txt`.
- Parent independently ran the full GL review harness. All eight frozen PNGs match worker captures byte-for-byte; all frozen repeats have zero changed pixels. Four individual engine ablations measure 212/222/245/239 pixels, exact restoration. All 150 paired simulation samples match. Actual 1280×800, 4MSAA, production shaders, normal fog; no gameplay/data/collision change.
- The first parent command was refused before rendering because an explicit `SDL_VIDEODRIVER` is prohibited by the preserved capture isolation helper. The corrected command unsets it and uses the normal native driver; both outputs retained. No quality or safety gate relaxed.
- Parent receipts are under `parent-run/`; full independent frames/videos remain in scratch `s06-cruiser-parent-review02`. The selected published images/videos are the worker final set, byte-identical for the checked frozen frames.
- `final/review-sheet.png` contains close/rear/tactical/common-scale before/after views. `final/paired-motion.mp4` is 5 seconds, 150 frames at 30fps. Parent inspected the full-size close candidate and review sheet: tapered layered armor, low bridge and separated machinery nacelles read clearly; the existing planet/background band remains visible in both variants and is not an asset fix.

Run from repository root:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_cruiser -v
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_alliance_cruiser_review.py --out /ABSOLUTE/FRESH/SCRATCH/DIRECTORY
```

The harness validates through the production geometry loader, injects only the pending cruiser in-process for review, restores the production resolver, and records that production selects no cruiser before/after. It does not forge approvals or change shipped selection.

## Remaining gate

Show the sheet and paired movie and ask the owner whether this specific Liberty Cruiser revision is approved or needs changes. Do not author the remaining corvette/carrier to evade that gate. If approved, record the owner's exact words bound to reviewed hashes and implement approved pipeline/registry metadata; retain merge/default activation as separate authority. If changes are requested, revise only this specimen and reproduce evidence. Other B1 bindings and B2–B5 remain incomplete.

No native Windows graphics/package acceptance, full suite, broad performance or S11 authorization is claimed. The S05 historical capture limitation stays in its own handoff. Existing approved trio files and gameplay remain unchanged.

## Corrected review recipe and safeguards

The initial independent review failed on inherited recipe metadata: recorded focus-fire/selection had not been executed. Corrected `fixed-review/capture/metrics.json` truthfully declares empty explicit command schedule and empty selection. Use the corrected sheet/movie in that directory. All 23 PNGs match prior captures; original failure/outputs remain preserved. Eleven focused tests pass after master-output alias safeguards and non-vacuous emitter geometry tests; corrected exporter independently reproduced identical bytes twice. No mesh/master appearance change. Source pin record is current; original pins remain in `fix-review.json`.

Parent reconciled the branch by fast-forward to roadmap merge `bd4709f` (only the document changed). Final focused invocation passed **59 tests**, pipeline **34/34**, runtime metadata **9 files reproduced**. The pipeline still covers the approved trio only; the pending cruiser has its own geometry/export/review tests, not invented approval coverage.
