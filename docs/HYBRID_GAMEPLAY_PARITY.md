# STAR ARMADA — Hybrid gameplay parity audit and repair

## 1. Scope and reference

The owner reported three regressions after switching `main.py` to the hybrid renderer:
starting a match in another window, W02 development text, and a non-working right-drag
3D camera. This change keeps Python gameplay and the C++/bgfx renderer. It does **not**
replace the simulation, change asset selection, merge a release, or declare complete parity.

Reference: `ed0e615797cc0cd71021a745c68421c91b7f1929`. The comparison follows the legacy
and C++ branches of that revision's `main.py`, `InputController`, `LiveSession` and native
viewer. Source symbols below are more durable than line numbers from the initial audit.
Pre-existing working-tree camera-delta and debug-default edits were preserved and tested.

## 2. Requested regressions

| Behavior | Legacy Python path | Previous hybrid path | This repair |
|---|---|---|---|
| Window continuity | Menu and match share a pygame window | `cpp_window.spawn` starts a separate native window; menu is iconified | **Still open.** Return-to-menu now restores the original window without recreating its GL context. This is not a same-window fix. |
| W02 development text | No native developer banner | Native viewer enables diagnostic text by default | Default off; `--debug-overlay` opt-in, `--no-overlay` retained. Native viewer rebuilt locally. |
| Right-drag 3D orbit | Mouse relative deltas drive camera yaw and pitch | Ring conversion emits zero relative movement; viewer also handles its own camera shortcuts | Pointer history reconstructed in HUD coordinates; native shortcut processing disabled while Python owns input. Real SDL→ring→Python probe verifies yaw 45→5°, pitch 55→37°. |
| Escape behavior | Cancel operation/panel first, double-Escape returns to menu | Native viewer exits immediately | Native forwards Escape without exiting; Python applies the original policy. |

## 3. Additional application parity repairs

| Area | Previous hybrid gap | Repair and evidence boundary |
|---|---|---|
| HUD input/render state | Native publisher creates a second HUD | `LiveSession(..., hud=hud)` uses the controller's actual HUD: hitboxes, fleet panel, placement, scrolling and mission references stay shared. CPU/wire tests plus actual-main smoke. |
| Application-level shortcuts | Native input goes straight to the controller | `dispatch_game_event` handles local and native events identically; restores F5/F9, F1, replay pause/speed, recovery gating and `HumanCommandRejected` routing. CPU natural-event dispatch tests; not a full manual campaign/replay playthrough. |
| Input timing | Ring polled during drawing, after update | Polled before controller/simulation update. Mode/state replacement stops old-frame processing. |
| Save/load/recovery lifecycle | Publisher and input remain bound to the old graph | Start/load/replay/leave/committed recovery reset and rebind transport, HUD, controller and camera. Each session uses fresh ring paths; close readers, reap native process, close writers, clean temporary directory. CPU tests. |
| Autosave | Native rendering returns via `continue` before common autosave tail | Both renderers reach the existing autosave logic. CPU test exercises real loop branch. |
| Campaign objectives | The native HUD lacks the application's mission reference | Shared HUD receives `manager.mission` on start/load and recovery. Existing campaign restoration tests pass. |
| Help/tutorial/cinematics | Separate Python presentation surfaces are not uploaded | Composite their transparent surfaces through the overlay ring; full frame on layer addition/removal prevents stale pixels. Empty presentations do not force full uploads. CPU/wire tests; full mission visual playthrough not accepted. |
| Reconnection presentation | Native draw bypasses recovery overlay | Overlay composed above HUD, with application-level input gating. CPU tests; no physical mixed-machine LAN acceptance. |
| Placement/target cursor | Reads mouse position in hidden pygame window | Cache bridged pointer position in `InputController`; tutorial wheel handling also uses event coordinates. CPU tests. |
| Pointer discontinuity | Old sample survives resize/focus transition | Clear relative-pointer history at focus loss/resize. CPU test. |
| Return to menu | Iconified menu can remain hidden | Restore/show/focus the existing display window after native teardown; do not call `set_mode` just to restore it. CPU lifecycle test. |

## 4. Confirmed remaining gaps — not fixed by this PR

1. **A genuinely shared window.** SDL's Cocoa external-window property accepts an in-process
   Objective-C object, not a pointer usable by another process. The existing viewer is an
   executable with a blocking lifecycle, not a library API. A genuine solution needs an
   in-process C++ renderer interface (initialize/frame/shutdown), main-thread/event ownership,
   build/package changes, and safe GL-menu↔Metal-world presentation on the original window.
   Hiding a second window or forwarding a process-local pointer is not a solution. Windows
   has not been validated as an external-HWND shortcut either.
2. **World construction/tactical feedback.** Native drawing still lacks the legacy placement
   ghost, paid construction sites, surface-slot pads and station collection-point links.
   Fixing bridged cursor coordinates does not implement those native draw passes.
3. **Asteroid fields.** The migration still deliberately omits their native world geometry.
4. **Hidden-information filtering.** Instance visibility is forwarded, but the existing
   effect/projectile, planetary ownership-ring and colony shield-dome paths do not consistently
   apply the legacy point/effect/known-planet predicates. Fog appearance alone does not prove
   equivalent disclosure. This is a separate known correctness gap, not accepted parity.
5. **Fullscreen, independent resizing/focus and camera collision-safe projection** need a
   dedicated native/host-window lifecycle matrix. Matching HUD coordinates and restoring the
   menu do not establish that matrix.

Recommended next work: true in-process window hosting as a bounded architectural increment;
restore missing construction/knowledge-filtered world passes separately. Preserve native rendering.

## 5. Verification and limits

The final focused real-driver union passed **356 Python tests**, including the bridge codecs,
shared HUD, overlays, input, main routing/lifecycle, campaign/skirmish and deterministic-math
checks. All **12 native CTest checks** passed. The native SDL input smoke records 140 frames,
no unmapped/skipped input batches, and the expected Python camera orbit; Escape does not kill
its viewer. Initial failed tests and negative controls are retained in the local receipts.

The 100-corvette simulation fixture, 3 warmup + 30 measured ticks, has identical baseline and
candidate initial/final hashes. This is a bounded determinism check, not full simulation or
performance acceptance. No gameplay system or approved model bytes changed.

Actual `main.py --skirmish` was exercised with isolated settings, campaign, balance, saves and
replays, and the real Metal viewer; injected SDL right-drag reaches the production main dispatch
and camera, and the publisher uses the same HUD as the controller. This is an actual-driver
integration smoke, **not** a physical mouse test, a full-match playthrough or a benchmark.

Durable evidence lives under `artifacts/hybrid-gameplay/`. CI status belongs to the PR's current
head; local success is not a claim that GitHub CI, Windows gameplay, packages, mixed-platform
LAN or the whole repository suite passed. No merge, tag or release is authorized here.
