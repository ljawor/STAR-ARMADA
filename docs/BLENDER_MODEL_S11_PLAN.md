# S11 — switch the game default to the Blender catalogue

**Status:** delivered on `feat/s11-default-authored`, engine `0.16.0`, decision record
`s11-default-switch-2026-10-19`. This document is the receipt for the switch; the roadmap carries
the milestone ledger entry.

## 1. What the switch changes

Three product changes, no geometry, material or catalogue revision:

| Change | File | Why |
|---|---|---|
| Shipped default is the approved catalogue | `render/menus.py` `DEFAULT_SETTINGS['model_preview'] = True` | S11's purpose; legacy stays as the rollback control |
| `model_preview_explicit` marker + migration in `load_settings` | `render/menus.py` | A pre-switch file's `model_preview: false` was a default, not a decision; only an explicit choice pins legacy |
| Catalogue completeness in diagnostics | `render/asset_selection.py`, `render/asset_registry.py` | A damaged catalogue must read as incomplete instead of looking finished with some objects silently procedural |
| `AssetResolver.coverage(full=False)` is structural | `render/asset_registry.py` | Manifest/revision/payload-presence check (manifest, revision, payload presence, size and sha256) costs 45 ms; the full payload parse costs 1,151 ms and belongs in acceptance tooling, not in startup |

Supporting, non-render changes:

- `tools/art/build_release_asset_lock.py` writes and verifies `art/manifests/release-asset-lock.json`
  (S10): every required binding, its manifest and payload hashes, revision, approval decision and
  material profile. `--check` fails the build on drift.
- `tests/test_s11_default_switch.py` binds the four promises: default, migration, completeness,
  rollback rehearsal.
- `game/__init__.py` version `0.15.1` → `0.16.0`.

Deliberately **not** changed: the settings row's label and note, so the language packs stay
byte-identical; the legacy renderer; any mesh, manifest, approval or lock pin; any test assertion
that was not about the default itself.

## 2. Verification

### 2.1 The three install scenarios (frozen macOS package, isolated `HOME`)

Built from this branch with PyInstaller 6.22.3 / Python 3.11.16: **422 files, 139.6 MB**, 103
manifests, **103/103 payload hashes verified inside the bundle**, three schemas, no `tools/`,
`tests/`, handoffs or `.blend` inside.

| Scenario | Settings on disk | Exit | Renderer actually used |
|---|---|---|---|
| Fresh install | none | 0 | authored |
| Upgrade from a pre-switch file | `model_preview: false`, no marker | 0 | authored (migration) |
| Explicit legacy choice | `model_preview: false`, marker `true` | 0 | legacy |

Pixel evidence (`artifacts/s11/smoke-*.png`, 1280×800, identical camera and 30 s tick):

| Pair | Pixels differing > 8/255 |
|---|---|
| fresh vs upgraded | **0.014 %** |
| fresh vs legacy | **2.774 %** |
| upgraded vs legacy | **2.776 %** |

The upgrade path is pixel-identical to a fresh install, and both differ from the legacy control by
~200× the noise floor. The fresh frame shows the plated authored station modules; the legacy frame
shows the ring-and-gantry procedure.

### 2.2 Automated gates

- `validate-models --all`: 1034/1034 checks, 0 failures, 0 warnings.
- `sync_runtime_metadata --check`: 112 files, no mesh writes.
- `build_release_asset_lock.py --check`: `LOCK_OK 103 bindings`, 21,126,346 payload bytes.
- Focused union (`test_s11_default_switch`, `test_asset_selection`): 24 tests, OK.

The full-suite verdict and its classification are recorded in §2.3 when the run completes; the
per-module instrument remains the attributable one for this repository.

## 3. Rollback — rehearsed, not theoretical

1. Settings → Readability & help → the model row, off. Or set
   `{"model_preview": false, "model_preview_explicit": true}` in `saves/settings.json`.
2. Restart. The next session constructs no resolver and draws procedural geometry.
3. Saves, replays, balance files and installed packs are untouched: selection is presentation-only
   and is excluded from gameplay-mod compatibility hashes and simulation state.

`RollbackRehearsalTests.test_returning_to_legacy_needs_only_the_selector` performs steps 1–2 in
process and asserts both directions. The frozen legacy run in §2.1 is the packaged version of the
same rehearsal.

## 4. Accepted exceptions recorded with this milestone

- **Performance reference unmet.** Authored catalogue medians at 1280×800 / 4× MSAA: 188.22 ms
  (stock distributed), 292.73 ms (stock combat) against a 16.67 ms 60 FPS budget; legacy itself is
  2.5–3.4× over that budget on the same scenes. The owner accepted the switch with the reference
  recorded as unmet and split measurement/optimisation into a separate engagement
  (`s11-default-switch-2026-10-19`, `carried_forward`). Nothing here claims 60/30 FPS.
- **Windows platform scope.** No native Windows graphics or package smoke exists in this milestone;
  `s09-platform-waiver-2026-10-19` covers exactly those two items and nothing else.
- **Cosmetic label debt.** The settings row still reads "Blender model preview (next session)" and
  its note still says the preview is opt-in. Correcting the text means a language-pack revision
  across every registered language, which S11 forbids mixing with the switch; it is a follow-up.
- **Two pre-existing test-fixture defects** (`test_gl_lifecycle`'s AST fixture, `test_crew_recovery_ui`
  convoy parity) remain failures on `main` before this branch and are not regressions.
- **Two pristine-checkout controls were never run** (blocked without consent) and stay recorded as
  unrun evidence gaps, not passes.

## 5. Out of scope for this milestone

Performance measurement and optimisation (separate engagement), native Windows evidence, deletion
of the legacy renderer, and any tag or release — those need their own authorization.
