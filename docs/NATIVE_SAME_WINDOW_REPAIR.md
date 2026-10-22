# Native original-window, sky and station repair — local verification

## State

Local follow-up to the bounded hybrid repair in draft PR #158. This file and
`artifacts/native-host-repair/` describe the current working-tree revision, not a
merged release. `source-sha256.json` pins the tested source files. Independent
review rejected this revision (see `review-rejected.json` in the evidence folder).
The owner requested a draft checkpoint to preserve the work; this is explicitly
not a merge-ready or independently approved revision. The older
`artifacts/hybrid-gameplay/review/final.json` does **not** approve these changes.

## What changed

* Default native gameplay uses a shared C++/bgfx library with a windowless worker.
  Python retains its original pygame/OpenGL window and event loop. A native
  offscreen framebuffer is read back to CPU memory and uploaded to that existing
  GL window. This preserves native scene rendering, but is **not zero-copy**.
  `STAR_ARMADA_CPP_EXTERNAL=1` retains the separate viewer for diagnostics only.
* Stars use soft, small discs, camera rotation without translation, and a
  far-depth depth-tested pass without depth writes. Opaque scene objects occlude
  them regardless of submission sorting.
* Paid station sites are published as progressively growing scaffold geometry.
  Completed stations use their faction-correct mesh binding, dynamically
  transported independently of the startup snapshot catalogue. The dynamic-mesh
  flag is separate from the planet/surface-frame flag.
* Original-window pointer coordinates are mapped once to the native logical HUD.
  Right-drag and HUD clicks use the same shared application dispatcher.
* RecoveryOverlay.draw now returns its rendered surface. Its previous None
  return caused native HUD composition to fail and silently fall back to legacy
  during reconnection; the new regression reproduces that exact error first.

## Executed evidence

* 362 targeted Python tests passed. This includes actual host and joined
  application TCP recovery, two physical-coordinate paid build clicks,
  reconnection presentation without native fallback, and replay checksums.
  It is **not** the repository-wide per-module acceptance run.
* 13 native CTest checks passed, including the deterministic starfield test.
* Opaque black planet probe: **0 foreground star pixels** across 69,557 interior
  pixels, with 21 candidate sky pixels behind the planet. The pre-fix probe
  observed 348 foreground pixels.
* Actual paid queue native fixture: early/half/completed renders succeeded;
  each stage reports no missing meshes and no mesh decode failures. The queue
  is deliberately time-advanced; this is not a natural-duration playthrough or
  acceptance of every station/faction/site condition.
* Existing-window fixture retains the same underlying Cocoa window address and
  proves its original GL context remains usable after native teardown.
* Actual main.py probe performs match → menu → second match with the identical
  native window address and blocks any external armada_viewer launch. Local
  right-drag changes yaw 45 → 9.5 degrees and pitch 55 → 38.98 degrees. F5 writes
  an isolated quicksave. Captures show first match, returned menu and re-entry.
* Added-line static security scan found no matches in the checked patterns.
  This is a scan, **not** independent code-review approval.

## Reproduction (macOS source checkout)

```sh
cmake -S render_cpp -B render_cpp/build-w02
cmake --build render_cpp/build-w02 --target armada_viewer armada_embedded test_starfield -j 4
ctest --test-dir render_cpp/build-w02 --output-on-failure
SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy .venv/bin/python tools/render/verify_embedded_main.py --out "$TMPDIR/native-main-proof"
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/render/verify_star_occlusion.py --out "$TMPDIR/star-proof"
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/render/verify_station_lifecycle.py --out "$TMPDIR/station-proof"
```

Run native/GL probes sequentially under an external process-group deadline. The
retained tests/*.json receipts record commands, exit codes and timeout status.

## Still not accepted

* Independent review rejected this ABI/thread/readback change: unbounded cleanup
  join after timeout, process-fatal bgfx callback, omitted library packaging,
  and unsafe concurrent frame/close calls. The fix attempt was interrupted.
* Frozen packaging and Windows/D3D runtime. The existing packaging specification
  does not yet include the new shared library; the existing release workflow
  also lacks native compilation. A source-checkout proof is not shipping proof.
* Representative interactive performance and transfer latency. An empty-world
  fixture is not a full-game FPS result; embedded bgfx draw-call samples are
  currently zero after readback-frame advancement and must not support a
  performance claim.
* Full campaign/cinematic, resize/fullscreen, all faction/station lifecycle,
  mixed-machine LAN and fault-injection acceptance.
* Remaining renderer parity gaps (placement ghosts, surface pads, collection
  links, asteroid representation and some effects/knowledge filtering).
* Final art direction: these repairs are **not Homeworld2-level visual quality**.
  The station captures establish visibility and construction feedback, not an
  approved materials/lighting/silhouette upgrade.

Nothing in this record authorizes a merge, tag or release.
