# Native notification HUD evidence

Candidate branch: `feat/native-notification-hud`, based on merged PR184 at `8348a4b622a3b19dfb5e2ee82030528df99c9037`.

## Current state

Implemented in the owner's ordinary checkout and rebuilt in `render_cpp/build-w02`. No feature merge or owner visual approval yet. Both Python and C++ independent reviews passed, including the actual-ink repair. C++ rereview additionally passed 2,142 sanitized centering cases and byte-exact compatibility checks against HEAD (1,296 cases) and the pre-repair implementation (1,728 cases); see `cpp-review-final.json`. `final-readiness-pins.json` identifies the final rebuilt/tested source and binaries; earlier `readiness-pins.json` describes the superseded first handover.

INCOMING is x=10,width=240 logical pixels, matching both column edges of the approved left panel. Height is .75 of legacy and bottom stays H−14. The lower-centre transient message uses .75 edge-rounded legacy measured dimensions around its existing centre. Oversized text retains legacy overflow clipping, rather than changing its measured width. Native text centres actual ink, including symbols and whitespace handling.

## Final execution

- 294 Python tests and 9,934 subtests passed (`final-python.log`); 88 existing pygame deprecation warnings.
- Production native build succeeded and 15/15 CTest tests passed.
- Two real main-loop cases: 1280×800 and 2560×1440; EN/DE/PL/RU, local-owner/latest-nine event filtering, exact alignment/scaling, replacement, natural expiry, stale removal, actual input blocking/freed-world input and application overlay coverage.
- Four native pipeline cases: both resolutions with ordinary dual-ring and vector-only configurations, 834 assertions total.
- Thirty authentic main-loop framebuffer PNGs retained in `acceptance-final/`; final English large and Russian small captures visually inspected. Presentation fixtures publish completion events through the real EventBus; they are not claimed as gameplay construction-command completion.
- Paused presentation checksums match; protected files/settings are unchanged; cleanup passed. External process-group watchdog verified using an intentionally blocked negative control.

`acceptance-final/acceptance.json` records all nine supervisor stages (watchdog, build, CTest, six graphics/main cases). `final-acceptance-manifest.json` hashes every produced evidence file. Every actual-main PNG/model/method JSON is retained; pipeline PNGs are represented by hashes only. `acceptance/` and `acceptance-manifest.json` preserve the earlier pre-centering-repair run, not final production acceptance.

## Review/repair history

- `python-review-initial.json`: failed missing direct-helper owner-game guard and pre-scale flash width clamp.
- `python-review-final.json`: independent approval after both precise fixes.
- `cpp-review-initial.json`: glyphs/budgets/compatibility passed, actual-ink centering failed on icons/trailing spaces.
- `cpu/`: retained implementation RED/GREEN, UBSan and byte-compatibility receipts. Final center-only repair preserved 112 shrink/clip cases byte-for-byte.

No ASan, Windows/frozen delivery, release/tag, whole-game FPS acceptance or gameplay changes are claimed. No owner process was stopped. All evidence logs must be explicitly staged despite the repository-wide `*.log` ignore when publishing this branch.

## Harness repair after the acceptance run

`--width 1024 --height 640` used to render a complete production frame and then fail
`wrong production output resolution`, because the window silently replaces any request
that is not a shipped preset with desktop-derived `auto`. The helper now reads
`render/display_settings.py`'s `RESOLUTIONS` tuple with `ast` (so the CLI still imports
nothing from the game) and refuses an unshipped size before creating the output
directory. Two CPU tests pin that, and the real captures were re-run on the repaired
harness at 2560×1440, 1280×800 and 1280×720 — receipts in `harness-repair.json`. Only the
harness and its test moved; every production source and both binaries still match
`final-readiness-pins.json`.

