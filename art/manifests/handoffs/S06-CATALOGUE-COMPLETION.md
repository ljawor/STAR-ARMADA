# S06 catalogue completion — B7/B8/B9 authoring checkpoint

## 1. Authority and scope

Owner: `Agree execute 1 , 2 and 3`; current increment: `please continue part2. Anything pending from my end for this?`.
Execution decision: `s06-catalogue-completion-execution-2026-10-18` in `pipeline_policy.json`.
This increment stops before S07 integration/registration. Appearance approval, merge, release and default activation are separate gates.

## 2. Exact working context

- Repository: `ljawor/STAR-ARMADA`.
- Worktree: `/Users/lukaszjawor/.hermes/cache/scratch/star-armada-catalogue-completion`.
- Branch: `feat/s06-catalogue-completion`; base: `dc16a88c52cdc72d7f9cb81675969cc6e3d8786c` (PR #129).
- Initial complete authoring/capture code: `8182d5a616f11ddc7083f31d92ba0c2ab36cddf7`.
- B7 centred camera implementation: `eb1b5be` (resolve through Git for full SHA).
- Publication head must be read from Git/PR, not embedded recursively in this file.
- Local `.venv` is an untracked/ignored convenience link to the live checkout. Never stage it.
- Earlier reconciliation and planning PR #129 is complete; do not re-run the planning assignment.

## 3. Delivered and verified

- B6 sidecars reproduce through their real batch command. Corrected explicit seed selection and stale provenance; approved source/exporter/runtime files and approval records unchanged.
- B7: ten Imperial orbital stations.
- B8: eight existing Confederacy/Syndicate combat hulls.
- B9: eight faction constructor/colonizer hulls plus the shared construction scaffold.
- All 27 editable Blender masters and runtime meshes exist. Blender 5.0.1 built each source. Every mesh was exported twice with identical runtime bytes and unchanged master hashes.
- All 27 payloads pass the production immutable loader at their exact declared envelopes, with all six populated roles.
- 26 ships/stations have real production-renderer close, rear, tactical and common-scale paired still evidence. No motion acceptance claimed.
- Review candidates are patched only in the diagnostic process; no manifests, registry entries, runtime pipeline selections, rendering/gameplay changes or activation were introduced. The later owner response adds appearance records only.
- All earlier approval pins continue to pass. After owner approval, reconciliation reports 102 unique approved assets (99 S06 specimens plus the trio), four shared candidates and one pending appearance (scaffold). S06 is still open.

Machine receipt: `artifacts/s06-completion/COMPLETION-REVIEW.json`. It pins runtime meshes, capture-code commits, renderer blobs, per-row metrics and the two export-reproduction receipts.

## 4. Honest remaining gates

- **Owner appearance review recorded:** owner replied `approved` to the B7/B8/B9 grids at review head `e9d78bcf684c2128b2e76af30f3e61cd3e952083`. Three revision-bound decisions cover exactly 26 pictured rows (10/8/8); B9 is partial and the scaffold remains unapproved.
- **Scaffold:** authored/exported/loader-validated, but requires the separate S07 scaffold selection seam for honest in-game review. It is excluded explicitly; do not claim 27 reviewed models.
- **Three planned Syndicate hulls:** no gameplay data exists for them. They remain separate data/model work; no statistics or production eligibility were invented.
- S07 integration and S08/S09 compatibility/platform/performance/package acceptance have not been performed here.
- Production rendering stays legacy. Nothing merged or released.

## 5. Failed attempts retained

- Initial authoring union: 11 subprocess errors from the absent worktree `.venv`; rerun passed after creating the local link. Both raw outputs retained.
- Initial Confederacy battleship export: float32 upper-bound overshoot. Seed fitting now rounds inward; wrapper and loader bounds were not relaxed. RED/GREEN and failed export retained.
- B9 seed arguments originally omitted `--asset`; review found it. Sheet, assertion and generated sidecars corrected, with RED retained.
- B7 first still captures cropped the fighter-platform mast. Second captures use the same paired camera, centred on the station's actual positive-Y envelope with extra clearance. Both attempts retained; appearance grid uses attempt 2.
- First framing-test run failed because its arbitrary length was not the fixture's footprint and a fake harness lacked the real view helpers. Corrected fixtures pass; the original result remains in `station-framing-green.txt` despite that historical filename.
- Raw unittest logs retain their original trailing whitespace. Do not rewrite failed evidence to make whitespace checks green.

## 6. Reproduction and handoff

From this worktree, using the live interpreter or local `.venv`:

```bash
python3 tools/art/gen_export_wrappers.py --check
python3 tools/art/write_pending_sidecars.py --check
python3 tools/art/reconcile_model_coverage.py --check
PYTHONPATH=tests .venv/bin/python -m unittest test_completion_payloads test_completion_review test_model_coverage_reconciliation test_s06_appearance_records test_b6_sidecar_reproduction test_blender_b7_imperial_stations test_blender_b8_remaining_combat test_blender_b9_construction test_completion_wrapper_generation -v
.venv/bin/python tools/art/validate-models --all
```

`validate-models --all` covers registered pipeline assets, **not** all pending models; `test_completion_payloads` is the pending geometry check. The full authoring union is retained under `artifacts/s06-completion/authoring-union-with-venv.txt`.

Export-only wrappers are `tools/art/export_<identifier>.py`; they open the master and never save it. Initial seeds refuse an existing master unless deliberately passed `--replace-seed`; do not reseed masters just to reproduce exports.

Review commands require a fresh output directory, real SDL/OpenGL, and no concurrent heavy graphics job:

```bash
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_completion_review.py --spec art/manifests/pending/S06-BATCH-B7-IMPERIAL-STATIONS.json --out <fresh-directory>
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_completion_review.py --spec art/manifests/pending/S06-BATCH-B8-REMAINING-COMBAT.json --out <fresh-directory>
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_completion_review.py --spec art/manifests/pending/S06-BATCH-B9-CONSTRUCTION.json --out <fresh-directory>
```

The three `B*-appearance-grid.jpg` images and full-size paired contact sheets bind the owner's `approved` response to exactly 26 current source/runtime revisions. The unpictured scaffold remains pending; no tests imply approval, activation or landing. B9 sidecars use explicit per-row status so the sheet's partial decision cannot leak to the scaffold.
