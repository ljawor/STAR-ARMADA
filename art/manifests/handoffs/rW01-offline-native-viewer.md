# Handoff: W01 offline native fleet viewer

Status: **engineering review-ready; owner camera/appearance gate open; not merged**.
PR: **#146**, base PR #145 (`docs/cpp-renderer-w00-spec`).
Branch: `render/cpp-w01-viewer`.
Implementation base: `b2ff85ab622cd535aaf0525adb362a700e4b6f63`.
W00 dependency head: `f5844a83936b52a64635cd4c664bce19d5197187`.
Final native/exporter code and capture revision: `7bf11d2204b3aca6c82e58943ab71f26613ea5d2`.
The evidence/docs commit follows this code revision; its exact pushed head is available from PR #146 and `git ls-remote origin refs/heads/render/cpp-w01-viewer`, avoiding a self-referential commit pin.

## 1. Authority and scope

Owner: "ok let's start this. Let's try to work on W00 + W01."
Execution record: `render-protocol-v1` in `art/manifests/pipeline_policy.json`.
This is permission to implement the bounded offline slice, not to merge, release, switch defaults, start W02 or approve changed appearance. W00's owner protocol review is still open; its executable offline v1 profile is the development prerequisite, not a frozen live-wire contract.

Owned files: `render_cpp/`, `tools/render/dump_snapshot.py`, `tests/test_render_snapshot.py`, this handoff, the migration ledger and `artifacts/cpp-renderer/w01/`.
No `game/`, `render/`, `assets/`, approved model/registry/appearance records, simulation/LAN, save/replay code, normal launch or renderer preference changed.

## 2. What actually works

- Python exports the unchanged real `four-player-combat-v1` stress fixture with player-0 detection: **638 mesh instances = 600 combat ships + 38 other entities**, 18 meshes. Two visible planets are explicitly omitted. This is prebuilt stress infrastructure, not proof of stock buildability.
- Standalone SDL3/bgfx viewer uses actual **Metal** on this Mac, with no silent OpenGL fallback. Existing mesh bytes and every face/material role are retained; instances are batched by mesh.
- Local orbit, wheel zoom, WASD pan, hull/station presets, diagnostic overlay and PNG capture. SDL-event probes exercised orbit/zoom/preset; camera pan/bounds have CPU checks. Natural keyboard/focus/camera feel remains owner-facing.
- Source-dependency build and prebuilt-dependency build both compiled and passed CTest. Source configuration reused the exact pinned dependency sources already downloaded; it was not a fresh network-only clone.
- The launcher exported the real fixture and ran the native viewer successfully. `render_cpp/README.md` contains source build and bounded run commands.

Local runnable worktree:
`/Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01`

```sh
open /Users/lukaszjawor/.hermes/cache/scratch/star-armada-cpp-w01/render_cpp/launch.command
```

Drag to orbit; wheel to zoom; WASD to pan; `1` overview, `2` supercapital, `3` station; Shift+S PNG; Escape quits. Do not confuse this frozen scene with a running match.

## 3. Evidence and measured result

Durable directory: `artifacts/cpp-renderer/w01/`.
`acceptance.json` pins the code, source files, every transported runtime mesh and lossless capture pixels; `SHA256SUMS.json` pins the evidence set. `review-sheet.png` compares overview references and native close-ups; full-resolution PNGs are included.

Final code, 1280×800, requested MSAA4, all mesh roles, 2048-square directional shadows, 60 warmup + **240 measured frames**, no overlay/readback in timing run:

| Offline mesh-only measurement | Median | p95 | p99 |
|---|---:|---:|---:|
| Wall frame loop | 8.736083 ms | 11.223917 ms | 12.439416 ms |
| bgfx GPU timer | 3.893125 ms | 4.307875 ms | 4.795250 ms |

Fleet submits **1,560,792 triangles per pass**. There are 37 reported draw submissions (18 mesh groups × shadow/colour plus the touched view). The catalogue diagnostic loaded/uploaded/submitted **103 unique meshes, 342,376 triangles**, not a per-model visual acceptance. Native actual MSAA sample count has not been independently queried; the report labels it requested.

Non-background pixels: fleet 11,919; capital view 33,172; station 66,997; catalogue grid 4,045. These prove nonempty captures, not quality. Shadow on/off changes **5,431 pixels** above two RGB levels at the identical capital camera. Exported captures were inspected and losslessly compressed without changing RGBA pixels.

`python-reference.png/json` uses the current production world renderer with the same frozen source fixture and overview camera, but includes its normal world passes and gameplay readability inflation. Native uses canonical hull sizes and omits fog, shields, markers, planets and background. **This is not matched quality or an apples-to-apples timing comparison; no speedup ratio follows.** Visually, native shading is still basic; no graphics improvement or owner appearance acceptance is asserted.

State before/after export and source reference:
`8179f6f09697f42783037c71577ee04172995ee8ac06bbf88884d285f9a897da`.
Catalogue layout is artificial; this hash identifies its unchanged source fixture, not the invented grid transforms.

## 4. Checks, failed attempts and review repairs

- **20 focused Python tests passed:** 3 W00 protocol + 3 new W01 exporter + 14 existing detmath. Command: `SDL_VIDEODRIVER=cocoa PYTHONPATH=tests <game-venv-python> -m unittest test_render_protocol test_render_snapshot test_detmath -v`.
- **2 native CTest targets passed**, `scene` and `camera`. Scene reports protocol, mesh correctness and containment/reference groups; camera covers orbit/zoom/pan bounds. This is not a full-game suite.
- Seven final-byte native runs plus launcher passed, bounded by an independently canary-tested process-group watchdog; receipts retain PIDs, exit codes, elapsed time, timeout and termination.
- Initial shader compile rejected a varying referenced inside a helper; pass the varying explicitly. The pinned bgfx API rejected the old `Init.resolution/platformData` and obsolete instancing capability bit; use `Init.swapChain`, explicit native backend/fallback policy and per-draw buffer availability. C++20 is required by the selected bx headers.
- Source-route build initially failed because `bx/math.h` was not propagated by bgfx's private dependency. Explicit direct `bx` linkage repaired it; full source-route build then passed in 7.644 s incrementally after the dependency build. Original failed build receipt remains.
- Native duplicate-ID and duplicate-key checks were added after recorded RED controls; both CTest targets passed afterward.
- Independent static review identified kind confusion, short-capture false success and device failure/lifetime/handle handling. Scoped cleanup and required handle checks were already present in the first published native revision. Remaining defects reproduced: world-shaped UI packet incorrectly accepted (0 instead of 3), one-frame capture returned 0 with no file, missing shader returned 1 instead of 4. Final CLI controls all pass with **3 / valid PNG / 4**. Logs retain RED, one intermediate compile typo, and GREEN.
- Ordinary failure exits unwind acquired native resources. Fatal bgfx callbacks log and terminate exit 4 without throwing across a driver thread; actual device-loss/recovery is not tested or implemented.
- ASan from the initial loader probe failed during macOS sanitizer initialization before executing tests. The worker reported ordinary/UBSan loader probes passing; the parent repeated ordinary loader checks. Do not describe ASan as green.

The implementation is 1,810 source/test/build-definition/shader lines (plus launcher/docs) and adds three Python methods plus native behavior groups: this **exceeds the proposal's LOC/test-count sizing rules**. No exception approval or compliance is inferred. Work remains draft; these are bounded prototype checks, not a precedent for full-suite-per-step or a second broad harness.

## 5. Dependency pins and unproven gates

- bgfx.cmake `b07783852a1cb0636a07f51a92d5366974579245`
- bgfx `d8d6acd94b64e01da3c4d1bc869df2dc2a8eb1ba`
- bx `234f2fba71909d95175daf865bb9f3aa5cd3c047`
- bimg `c37d64e57457487e6f4f2332d5ac4f025b70b8d7`
- SDL3 **3.4.14**, AppleClang **16.0.0.16000026**, CMake **3.25.1**.
- nlohmann/json `65ee68451d8eb2b5f3a30b410476ab83deb3289b`; PicoSHA2 `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29`.

Not proven: full-game parity or FPS; 200/400-ship timings; actual D3D12/Windows graphics; fresh-machine/package launch; natural input/focus acceptance; full PBR/material parity or better graphics; per-asset approval transfer; real device loss; W02 streaming/serialization/recovery; HUD, picking, fog, effects or menus. GitHub's Windows Python/LAN workflow is separate and cannot validate this native renderer. The initial code-head run `39551650938` was deliberately cancelled while pending before the evidence-head push, avoiding two own runs on the account; pre/post receipts are retained, and this is not a pass. Read PR #146 checks at its final head separately. No full integration suite was run at this isolated tool milestone.

## 6. Next gate — owner flies the offline viewer

Open the launcher and judge camera feel and the explicitly incomplete picture. W01 is not complete until that review; do not infer approval from a test pass or this preservation draft. If accepted, agree the W02 live-wire/camera-authority scope next. If rejected, record the specific appearance/input issue and repair only that bounded offline slice. No live integration, merge/tag/release or default switch follows automatically.
