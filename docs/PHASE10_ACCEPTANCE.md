# Phase 10 — presentation acceptance

## Approved scope

This increment targets audio mix, short skippable in-engine campaign intros/outros,
and bounded tutorial/accessibility/UX improvements. Presentation stays outside the
deterministic simulation. Cinematics must not interrupt live LAN or replay playback.
It does not authorize a version bump, merge, tag or published release.

Native Windows hardware is unavailable for this increment. Windows gameplay and
mixed-platform LAN remain **OPEN** regardless of local tests or archive integrity.
A local frozen macOS candidate is not a verified published release artifact.

## Verification matrix

Executed October 11, 2026 on the feature branch. Results are controlled automated
acceptance unless explicitly described otherwise; native human checklist items below
remain unchecked.

| Gate | Status | Executed evidence / remaining gate |
|---|---|---|
| Audio routing, priority, mono and mix settings | PASS — controlled/native mixer | 50 focused audio tests; real producers/180 combat ticks; CoreAudio PCM and live controls; unclipped offline comparisons |
| Subjective audio quality | OPEN | Human listening to standard/night comparisons and real gameplay |
| Campaign intro/outro lifecycle | PASS — production loop | Real Cocoa main-loop frames; all skip gestures, disabled/reduced motion, camera restore, no catch-up, success/failure once and menu return |
| Simulation invariance during presentation | PASS — controlled | Exact JSON-normalized precise dictionaries across frames/input; audio callbacks compare lossless raw fields, queues and timers |
| Settings/help/hints layout | PASS — native Cocoa GL | 44 UX framebuffer captures at 1024×768/1280×800; emitted glyph/control bounds, all pages, GL state and alpha comparison; actual main F1 dispatch/cancellation/occlusion |
| Settings persistence and malformed values | PASS | Persisted round-trip, nonfinite/huge numeric and invalid boolean/profile fallback tests; dummy-video headless portability |
| Tutorial usability | OPEN | Natural-navigation human recovery-drill playthrough; no fixture repositioning |
| macOS source gameplay | PASS — diagnostic/smoke | Native SDL/GL diagnostics and 30-second source `SMOKE_OK`; not a full campaign playthrough |
| Local frozen macOS candidate | PASS — local smoke | Fresh PyInstaller app; five changed modules match source bytecode; stale 0.6.0 control rejected; read-only checksum-verified DMG `SMOKE_OK`; isolated writable user data/replay output |
| Full regression suite and independent review | PASS | Final stable run: 905 tests, 380.245s, exit zero. Independent source re-review approved 78 audio/presentation plus 43 LAN/jump/support tests; shutdown-fixture review approved six lifecycle tests |
| Native Windows gameplay | OPEN — no machine available | Native executable and interactive checklist below |
| Mixed-platform LAN | OPEN — no Windows machine available | Separate Mac/Windows peers, gameplay and aligned continuation |

## Executed evidence and reproduction

The implementation is on `feature/phase10-presentation`, based on released v0.8.0.
The candidate still reports 0.8.0: this is deliberately not a new version or release.

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_audio test_audio_mix test_cinematics test_presentation_ux test_presentation_main -q
PYTHONPATH=. .venv/bin/python tools/diag_audio_mix.py --out "$TMPDIR/phase10-audio" --device
PYTHONPATH=. .venv/bin/python tools/diag_presentation_ux.py --out "$TMPDIR/presentation-ux"
PYTHONPATH=. .venv/bin/python tools/diag_cinematics.py "$TMPDIR/phase10-cinematics"
.venv/bin/python main.py --smoke
```

Local retained evidence is under the configured Hermes scratch directory:

- `phase10-audio-audit-tests.log`, `phase10-audio-audit-producers.json`;
  `phase10-audio-audit-{native,offline}/audio_mix_metrics.json` and five WAVs each.
  Native mixer: 44,100 Hz, signed 16-bit stereo. Coherent channel peak bound
  **0.87630**; standard/night comparison peaks **0.59888/0.49327**, no clipped
  samples; mono left/right difference zero. Ambient seam zero; maximum adjacent
  PCM step **0.002716**. These are buffer/mixer checks, not recorded sound or
  human quality approval.
- `presentation-ux/report.json`: 44 captures, actual glyph/control bounds and
  page reachability, exact state preservation and zero GL errors. GL compositing
  agrees with the SDL reference within two RGB levels. Fixtures cover real drill
  selection types but use controlled objectives/positions/cargo.
- `phase10-cinematics/report.json`, `phase10-cinematics.log`: real production
  SDL event/tick/draw loop, 182/180 caption rectangles at 1024×768/1280×800,
  zero GL errors, intro/outro camera/time invariance, skip/disabled/reduced-motion,
  success/failure/menu/progress and F1 modal dispatch/occlusion checks.
- `phase10-source-smoke.log`: 30-second rendered source `SMOKE_OK`.
- `phase10-full-suite.log`: final serialized 905-test `OK`, after correcting
  the hint-intercepted pointer release and extending the old shutdown AST fixture
  to verify presentation cleanup before quit. The first full run exposed the
  fixture's missing namespace entry; assertions were strengthened, not suppressed.
  Existing unclosed-file ResourceWarnings in `test_audio.py` and
  `test_persistence.py` remain; no test failure/error remains.
- `tutorial-pointer-{right-red,right-green,left-red,green,focused}.log` records
  strict correction evidence with real InputController. Final independent review
  reproduced both bugs against an in-memory pre-fix control and approved the fix;
  real SDL hint-release probes also pass at both resolutions.
- `phase10-frozen-bytecode.json`: all five changed production modules exactly
  match structural source bytecode; `phase10-frozen-control.json` rejects the
  old local 0.6.0 bundle, including its absent presentation modules.
- `STAR-ARMADA-phase10-local-candidate.dmg`: checksum verification passed;
  read-only launch exits zero with `SMOKE_OK` in `phase10-frozen-smoke.log`.
  Screenshot and replay were freshly written under the isolated test HOME's
  `Library/Application Support/STAR ARMADA`, not the mounted app. Ad-hoc signed
  arm64 candidate; no notarization, Windows candidate or published download implied.
  This smoke is a skirmish, not frozen campaign/help interactive acceptance.

## Native interactive checklist

Run on the exact candidate/package being accepted; record build SHA, version, OS,
GPU, resolution, audio device, settings and outcome. Keep unchecked entries open.

- [ ] Launch from installed/extracted package without source checkout or Python.
- [ ] Settings persist outside the application; restart retains every new option.
- [ ] Check standard/night mix at modest volume, music/SFX zero, mono and critical
      alerts during a dense battle. No bursts, stuck loops, missing alerts or crashes.
- [ ] Launch the recovery drill naturally; read intro, skip by keyboard and mouse,
      then verify selection/camera/orders work without a queued accidental order.
- [ ] Repeat with cinematics disabled and reduced motion enabled; check no camera
      pan/fade in reduced-motion presentation and no simulation advance in intro.
- [ ] Complete/fail a campaign mission; verify outcome text, one outro only, correct
      stable-ID unlock behavior and return to menu. Save/load and replay remain valid.
- [ ] Open/close F1 help, visit all help/settings pages, toggle hints and high contrast.
      Read captions/help at both 1024×768 and 1280×800; verify no inaccessible controls.
- [ ] Tutorial: board a naturally reached detected shields-down target, repair life
      support separately from recruitment, then load/deliver crew using real controls.
- [ ] Resize/fullscreen, focus loss/recovery, quit from menu/game/presentation;
      no stuck held keys, stale texture references or teardown failures.
- [ ] Mac/Windows LAN: two real machines, matching build/content, cold host/join,
      readiness, ordinary orders and sustained combat. No campaign presentation or
      local pause introduced. Disconnect remains terminal until reconnect is delivered.

## Limits

Targeted help/caption readability is not whole-game UI scaling, a screen reader,
complete keyboard-only gameplay, general colorblind certification or a completed
campaign balance/playthrough gate. Reduced motion applies to this presentation
increment, not a promise to remove every combat flash/effect. Offline WAV metrics
are not an acoustic capture or subjective listening approval.
The cinematic compositor is verified under the production renderer's conventional
GL state. Adversarial nondefault cinematic shader/texture/unpack-state isolation
remains a nonblocking hardening suggestion, not a passed diagnostic gate.
