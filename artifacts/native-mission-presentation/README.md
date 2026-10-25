# Native mission presentation — local acceptance

Capture-producing code: `37abea989bb077faad9375afe35dc9c2fa029f72`. Native viewer/library SHA-256 and every source hash are in each resolution's `verification.json`.

## Changed

- Mission-start briefing: native vector/text card with bounded layout, type hierarchy, complete paged briefing/objectives and skip/page footer.
- Mission objectives and contextual drill hints: one native top-centre panel, one minimize/restore state. No separate orphan raster hint card.
- Existing native C++ vector consumer reused. Legacy cinematic compose remains as the explicit slice-only before-control and compatibility fallback.

## Real execution

`tools/render/capture_native_mission_game.py` runs the stock `m00_recovery_drill` through actual `main.py` production bodies/loop, SDL events and the built embedded C++ renderer. It isolates settings/campaign saves, reads the checkout's shipped visual packs, requires preview mode and all 16 accepted packs, and verifies owner persistence hashes unchanged. It is non-shipping developer tooling, not an owner-launch command.

Both 1280×800 and 2560×1440 runs cover native briefing, legacy briefing control with other native HUD slices unchanged, Enter skip, expanded objectives/hints, SDL minimize/restore, freed body hitbox, exact restored native content and unchanged paused simulation checksum. PL/DE/RU screenshots are retained. `mission-states.png` is a labelled crop of genuine small-run framebuffer pixels; uncropped frames remain alongside it.

Final run commands (fresh output directories, external deadline supervisor):

```sh
SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy .venv/bin/python tools/render/capture_native_mission_game.py --out <fresh-small>
SDL_VIDEODRIVER=cocoa SDL_AUDIODRIVER=dummy .venv/bin/python tools/render/capture_native_mission_game.py --width 2560 --height 1440 --out <fresh-large>
```

`collapse-pixels.json` independently measures actual framebuffer glyph removal and restored body pixel agreement, not just Python display-model state.

## Tests/review and limits

- Focused union: 138 passed, 1545 subtests. Covers cinematic paging, raster-forbidden native paths, mission layout/collapse, presentation, hybrid main, vector HUD, wheel/input, language tools.
- Rebuilt owner native tree; 16/16 CTests passed.
- Additional compatibility run: 31 passed, 117 subtests, one pre-existing failure in `PresentationMainTests.test_cinematic_final_frame_returns_to_menu_only_for_outro`: its old AST fixture does not supply native `CPP`. Reproduced with the committed base `main.py` before this patch (8 passed, same one failure). No full-suite pass claimed.
- An unrelated ignored Finder `.DS_Store` contamination rejected the existing alliance visual pack during preflight. Exact metadata files were quarantined with retained bytes/hashes outside the checkout; no tracked asset/validator changes. The final capture explicitly requires every shipped pack accepted.
- Independent full review and capture-provenance followup: no security/logic blockers. Nonblocking suggestions concern help-modal hint export, footer bounds, wrapper duplication and mission scroll-state reset; unchanged scope is documented in review receipts.
- Local macOS rendering only. No empirical Windows acceptance, packaged-app acceptance, full-suite or CI-green claim. Windows signal remains manually disabled at the owner's direction. Owner visual approval and merge remain pending.

Earlier core-only preflight captures are retained in scratch and are not this final evidence set.
