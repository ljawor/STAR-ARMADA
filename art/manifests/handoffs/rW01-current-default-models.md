# W01 correction: use the current shipped model selection

Status: native/CPU checks passed; owner picture/camera review remains open; no merge or activation.
PR #146, branch `render/cpp-w01-viewer`.
Code and native captures: `2bf5ed5f78908a0e6e68dc01f0a55cdfa4f6c208`.

## 1. Owner finding and root cause

Owner: "OK. You used for thsi simulation an old version of the imperial command center and a old version of the  vigil fregat. It is important that we use the new object for this. Is this possible?"

The initial exporter enabled `model_preview` but omitted `DEFAULT_SETTINGS.visual_packs`, then selected files from the core manifest table. The base catalogue was valid and current in Git, but was **not the effective current default model selection**. The newer Vigil and Command Center already existed in the repository's shipped visual packs. Earlier W01 claims about current visual-selection parity were wrong; the core-only pictures/timings remain historical, not representative of shipped defaults. This is not an appearance approval.

## 2. Correction

- Read the application's actual defaults with stdlib AST, without importing menu/window code or touching saved preferences. Activate all **13** default packs through the existing resolver and require all to be accepted; reject failed defaults rather than silently draw old core replacements.
- Export effective selected manifest paths and hashes, including `prototype:imperial/vigil` for `imperial:corvette` and `prototype:imperial/command_station`. Vigil is registered as a corvette; no gameplay class/data changes were made.
- New frame paths are repository-relative under `assets/` and `visual_packs/`, with an explicit metadata root label; use `--assets .`. Historical core-only frames still use their old `--assets assets` root. Native canonical containment/hash checks remain active; no source mesh was copied, re-exported or edited.
- Add support for the existing `star-armada/mesh-export`, major 1 payloads used by the new objects. Preserve legacy schema 1 support. Reject unknown contract/major and mismatched selected manifest identity; preserve every face and normal.
- Launcher regenerates the corrected snapshot and uses the repository root. The corrected viewer was reopened and its process/snapshot selection checked.

## 3. Executed checks and evidence

Directory: `artifacts/cpp-renderer/w01/current-models/`.
Start with `review-sheet.png` and `receipt.json`; `SHA256SUMS.json` pins this corrective subset. Parent-directory original receipts are historical at their original commits and are not regenerated to conceal the omission.

- Regression RED: selected default pack list was empty instead of 13. GREEN: all 6 focused protocol/exporter tests pass, checking selected pack file hashes, the two named manifest identities, missing-default refusal and unchanged precise state hash.
- Native RED: the old loader rejected modern mesh files because they have `contract/contract_major`, not legacy `schema`. Retained direct-run refusal and focused test failure. GREEN: both native CTest targets pass under prebuilt and rebuilt source dependency routes; unsupported contract/major and wrong identity negative controls remain rejecting.
- Five bounded actual-Metal runs passed: capture-free fleet timing, fleet picture, Command Center close-up, Vigil close-up and complete selected catalogue. Pictures were inspected; PNG recompression preserves pixels.
- **638 detected instances including 600 combat ships**; **103 selected unique meshes** upload/submit; **394,928** catalogue triangles; **3,084,356 triangles per fleet pass**. Counts and selected source hashes are in the receipt; original approved mesh bytes are untouched.
- Same precise source state before/after extraction: `8179f6f09697f42783037c71577ee04172995ee8ac06bbf88884d285f9a897da`.
- Corrected-selection timing, 1280×800, requested MSAA4, shadows on, 60 warmup + 240 measured frames: wall median **6.111416 ms**, GPU timer median **14.902541 ms**. Raw asynchronous wall/GPU samples are different instruments: do not add them, treat wall throughput as completed-GPU latency, or claim a full-game FPS/speedup. Earlier core-only 8.74/3.89 ms numbers do not describe these models.

No full suite, native Windows, live streaming, new artwork, material approval, default switch, merge/tag/release or W02 work was performed. Current defaults are reproduced, not arbitrary saved/user-installed pack selection. Shading remains the same prototype treatment. Next gate is the owner's review of these **correct objects** and camera feel.
