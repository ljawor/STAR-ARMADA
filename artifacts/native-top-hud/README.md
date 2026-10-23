# Native top-HUD acceptance evidence

## What this candidate changes

Ordinary `main.py` starts the native upper HUD automatically: CR / MT / EN / CRW /
CMD, income rates, clock, pause and FPS are measured and drawn by the existing
C++ renderer at the drawable resolution. Python retains all simulation,
authoritative values, command handling and translation. Russian is retained.
The remaining HUD modules and approved faction assets are not migrated here.

## Retained visual evidence

- `actual-main-top-comparison.png`: before above, native after below, at 2560×1440.
- `actual-main-before.png` / `actual-main-after.png`: same paused ordinary match,
  camera and simulation checksum. The control disables only the native slice.
- `actual-main-running.png`: resumed ordinary game.
- `actual-main-paused-{de,pl,ru}.png`: actual game language captures.
- `actual-main-metrics.json`: default activation, actual unmodified loop body,
  real SDL pause/resume and top-bar input occlusion. The hidden Cocoa/GL window
  uses the production embedded library, not a replacement renderer.
- `native-resolution-matrix.json`: native GPU pixel assertions at 1280×800,
  1920×1080, 2560×1440 and 3840×2160. This diagnostic's backdrop is the offline
  catalogue; it is not evidence of a running match. Per-resolution language
  image hashes are retained; those diagnostic PNGs are regenerable, not bundled.

## Executed local gates

- Full native build succeeded; CTest **14/14 passed**.
- Focused Python union **172 passed / 1,587 subtests passed**. This is not the
  repository-wide long acceptance suite. Existing `pygame.image.tostring`
  deprecation warnings remain in `render_bridge/planets.py`.
- C++ layout: nine sizes × normal / large / maximum-length values; bounds,
  non-overlap, palette, inactive geometry, distinct multilingual glyph masks,
  pinned-font corruption and strict bounded JSON cases.
- UBSan passed. ASan is **blocked** by macOS runtime initialization failure,
  not reported as a pass.
- GPU controls: glyph colour/coverage counts; native-only versus identical
  inactive-native control; resumed strip identical to a clean reference captured
  before pause/FPS were drawn; repeated-state identity; malformed model preserves
  last good frame; inactive model clears; opaque app layer covers the entire bar.
- Ordinary-main capture confirms default activation before its legacy override,
  paused before/after checksum equality, top click blocking and successful resume.
  Real settings/campaign/balance files are hash-checked unchanged by the tool.

## Review history

Initial failed reviews are preserved, not overwritten:

- `integration-review-initial.json`: constructor-failure mode/handle leak.
  Corrected with deferred activation and exception-safe ring cleanup; regression
  tests include original exception identity and both previous presentation modes.
- `cpu-review-initial.json`: raw NUL could terminate JSON parsing before invalid
  trailing bytes. Corrected by rejecting any raw NUL before parsing; permanent
  tests include NUL, NUL+junk and NUL+0xFF, leading/interior NUL and escaped NUL.
- Final independent receipts are separate `*-review-final.json` files. They must
  both pass before this candidate is published for owner review.

`evidence-sha256.json` seals retained captures, receipts and the tested production
sources, shaders/font and local build products. Local build hashes identify this
Mac's rebuilt deliverable, not a frozen release or a portable binary guarantee.

No Windows/frozen-app delivery, whole-game frame-rate target, broader HUD
migration, owner visual approval, merge or release is claimed by these artifacts.
See `docs/NATIVE_TOP_HUD.md` for protocol and reproducible commands.
