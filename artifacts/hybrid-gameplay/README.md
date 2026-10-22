# Hybrid gameplay repair evidence

## 1. Revision and scope

Code and visual-probe revision: `89565ae1b2fbf0130e7b2bc09aac2d46e78ab3d7`.
Baseline: `ed0e615797cc0cd71021a745c68421c91b7f1929`.
Later evidence-only commits do not change these reviewed/rendered code bytes.

The native renderer stays enabled. **Same-window hosting is not fixed**; see
`docs/HYBRID_GAMEPLAY_PARITY.md` for the comparison and remaining native world/visibility gaps.
No merge, package, release, Windows gameplay, whole-suite or performance acceptance is implied.

## 2. Machine results

- `tests/final-python-union-latest.{json,log}`: 356 tests, zero failures/errors, real Cocoa driver.
  Includes actual application recovery probes and paid replay continuation tests, but is not a
  physical mixed-machine LAN playthrough. The JSON records the exact module invocation.
- `tests/final-native-ctest.{json,log}`: 12/12 C++ tests.
- `tests/simulation-parity.json`: the 100-corvette, 3+30-tick initial and final state hashes
  equal the actual archived baseline. Timings in the raw reports are not a renderer speedup.
- `native/controls.json`: actual SDL pump→native ring→Python controller; yaw 45→5°, pitch 55→37°;
  140 native frames, zero unmapped/skipped batches. Escape is delivered without exiting the viewer.
- `native/{before,after}-verification.json`: actual isolated `main.py --skirmish` plus Metal,
  the real shared HUD, adopted frame/HUD/camera reports, and code SHA-256 pins verified against
  the committed blobs. The deliberately time-bounded viewer subsequently exits and the game
  exercises ordinary fallback before quitting. User persistence is redirected to a disposable root.
- `native/capture-report.json`: camera poses, raw image and native binary hashes; 7.94% of the
  measured world region changes after right-drag. The identical-image negative control is rejected.
  The sheet is **before/after a drag**, not a screenshot comparison against the unfixed program.
- `native/debug-*.png`: same offline native fixture with default versus opt-in developer text;
  6,570 upper-left pixels differ at a >20/255 channel threshold. This is a debug-policy control,
  not a gameplay or performance comparison. Both and the actual-game sheet were inspected.

## 3. Failed attempts and independent review

Keep the initial failed tests under `negative-controls/`; the committed old input bridge fails
the yaw assertion, and the old native shortcut path modifies its camera despite an input owner.
The review-driven pointer, cinematic restoration and unequal-HUD-size regressions are retained.
`review/initial.json` and `second.json` preserve the genuine findings; `final.json` is the
independent passing re-review after both repair cycles. Test-only `exec` compiles AST-selected
trusted repository source; it is not user-provided evaluation.

Other development attempts remain in local scratch receipts. In particular, an early mixed
recovery run used the dummy driver and failed GL setup, and a later AST-fixture rewrite first
omitted `running` and assumed a return value. Those harness errors were corrected rather than
classified as product defects. Final real-driver coverage passes. Native probe development also
corrected a report-key typo before its behavioral RED run.

## 4. Reproduce the actual-driver probes

Build the viewer first using the repository's pinned dependencies/build instructions. Run one
probe at a time on a graphical desktop and give it an outer process-group deadline.

```sh
.venv/bin/python tools/render/verify_live_controls.py --out <scratch>/controls
.venv/bin/python tools/render/verify_main_runtime.py --out <scratch>/before
.venv/bin/python tools/render/verify_main_runtime.py --orbit --out <scratch>/after
ctest --test-dir render_cpp/build-w02 --output-on-failure
```

The tools have internal deadlines/normal teardown; retain an external deadline as protection
against native hangs. To reproduce debug-policy captures, launch the same offline snapshot with
`--frames 40 --warmup 0 --screenshot <path>` once with no debug flag and once with
`--debug-overlay`. `--no-overlay` remains an explicit compatible opt-out.
