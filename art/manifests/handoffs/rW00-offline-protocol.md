# Handoff: W00 offline protocol
Status: review-ready; not merged; owner spec review remains open.

## 1. Authority and source
Base: `b2ff85ab622cd535aaf0525adb362a700e4b6f63`, branch `docs/cpp-renderer-w00-spec`.
Owner words: "ok let's start this. Let's try to work on W00 + W01."
Recorded as `render-protocol-v1` in `art/manifests/pipeline_policy.json`.
This authorizes implementation, not merge/release/default activation or blanket protocol approval.
The exact pushed head and PR are recorded in the PR/remote receipt; this file cannot pin its own commit.

## 2. What landed on the branch
- `docs/RENDER_PROTOCOL.md`: 32-byte LE versioned envelope, canonical bounded JSON offline profile.
- `render_bridge/protocol.py`: reference file codec; no process/window/shared-memory bridge.
- Three frozen binary transport controls and `checksums.json`; explicit synthetic labels.
- Three behavioral test methods: roundtrip, malformed input, fixture identity.
- Append-only policy execution record and migration-ledger update.

## 3. Commands actually run
```sh
PYTHONPATH=tests /Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python -m unittest test_render_protocol test_render_snapshot -v
```
Parent verification: 6 tests passed in 6.644 s (3 protocol plus 3 W01 exporter tests).
W01 exporter/tests exist locally but are deliberately **not in the W00 commit**; W00's own
clean checkout command is `PYTHONPATH=tests python -m unittest test_render_protocol -v`.
Failing-first logs are retained in local scratch `w00-red-*.log`; the committed tests exercise
bad magic/version/kind, length/trailing bytes, CRC, nonfinite/canonical JSON and input ranges.
No full suite or native rendering was run for W00; no performance claim follows.

## 4. Scope corrections and known gaps
- Offline JSON is a deliberate bounded slice, not the live packed-array/shared-memory specification.
- W02 must design and measure transport, synchronization, lifecycle and the 1 ms serialization gate.
- UI500 is a transport control, not a functioning HUD renderer or texture/atlas contract.
- Camera picking must use coherent frame-indexed authority, not a 1 Hz mirror.
- A small reference codec was added in W00 so protocol bytes are executable, not prose-only.
- The W01 source exporter and snapshot/mesh consumer have separate validation responsibilities.
- No game/render/assets/main/default behavior changes; approval records and model hashes unchanged.

## 5. Next executable step
W01: compile the native SDL3/bgfx viewer, load the real exported fleet and all 103 runtime
meshes, exercise camera controls, render/inspect a PNG, retain offline-only timings, and publish
its own PR/handoff. Do not restart catalogue migration or broaden into W02/gameplay integration.
