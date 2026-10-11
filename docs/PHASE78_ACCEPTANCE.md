# Phase 7/8 source acceptance — October 11, 2026

This report records PR #39 source verification for v0.8.0. Package publication,
downloaded artifact checks and frozen smoke results are recorded separately in
the GitHub release notes. Windows/mixed-platform interactive acceptance is not implied.

## Implemented

- Persisted deterministic campaign tick/time/event/objective triggers, once-only
  reinforcements, stages, capture and personnel-delivery objectives.
- Recovery drill plus the original ten missions, paged at both supported diagnostic
  sizes; schema-versioned stable unlock IDs and explicit legacy migration.
- Automatic accepted-human-command recording for skirmish/campaign/load/LAN,
  replay browser, bounded validation and read-only playback with pause/speed/end.
- Canonical future AI/system state in saves/replays, including mid-match strategy,
  pending construction and system timers; exact continuation, not coarse hashes.
- Same-host reconnect **foundation only**: typed snapshots, authenticated barriers,
  gapless input journals, bounded transfer. Production LAN disconnect remains terminal.

## Final executed gates

- Whole-tree suite: **861 tests passed in 368.219 seconds**.
  Log: `~/.hermes/cache/scratch/star-armada-phase78-acceptance-final.log`.
  Existing unclosed-file ResourceWarnings in audio/persistence tests remain non-failing.
- Compile checks and `git diff --check` passed.
- Real Cocoa SDL/OpenGL replay diagnostic: `DIAG_REPLAY_OK`, 1024×768 and 1280×800.
  Evidence: `~/.hermes/cache/scratch/phase78-delivery-replays/`.
- Campaign diagnostic: `DIAG_CAMPAIGN_PHASE7_UI_AND_CONTROLLED_CONTINUATION_OK`
  at both sizes. Exact mission roster/briefings, contained objective text, accepted
  boarding/capture and personnel delivery; capture/delivery restore checks passed.
  Evidence: `~/.hermes/cache/scratch/phase78-delivery-campaign/`.
  Controlled fixture repositions cruiser/transport and disables cruiser fire;
  this is not a natural-navigation human campaign playthrough.
- Reconnect diagnostic: `LAN_RECONNECT_FOUNDATION_OK`, 2/3/4 humans over real TCP,
  externally quiesced graphs and 60 aligned continuation ticks per scenario.
  Evidence: `~/.hermes/cache/scratch/phase78-delivery-reconnect.log`.
  It does not establish live production reconnect.
- Production two-process LAN pacing: `DIAG_LAN_OK`, 180 ticks and 181 matching
  precise hashes in each mode. Quantized 33/33/34 ms: 29.60/29.26 ticks/sec;
  SDL Clock: 28.47/28.50 ticks/sec. Both exceed the 27 ticks/sec gate.
  Evidence: `~/.hermes/cache/scratch/phase78-lan-final-{quantized,clock}.log`.

## Regression and migration boundaries

The earlier 857-test run failed (3 failures, 6 errors); it is superseded, not counted
as acceptance. Fixes retain list/tuple fleet rally coordinates, save-only numerical
invalid-jump repair and strict untrusted replay rejection. Legacy test payloads
explicitly omit runtime state; private colony queue fixtures use actual schema.
Queued-input UI comparisons exclude intended input in both serialized projections.

Historical old saves/replays without runtime state rebuild fresh AI/timers and cannot
recover unrecorded strategy. Old v2 duration remains known; its browser warning is
future-state unavailable, not duration unknown. V1 content/duration are unverified.

## Still open

- Production reconnect: distributed freeze/rollback, acknowledged-input reconciliation,
  reserved authenticated slots and atomic manager/UI/audio/recorder handoff.
- Natural-navigation full campaign playthrough, combat-wave balance and cinematic polish.
- Native Windows, mixed-platform/multi-machine LAN and frozen-package interactive tests.
- Faction parity/full-match balance, eight-player expansion and other later roadmap scope.

Independent integration re-review passed: 85 focused tests and 44 additional probes,
including 160 exact restored-state comparisons across AI cadence. Together with the
whole-tree suite and final diagnostics, this completes the source pre-commit gate.
These results do not authorize merging or releasing.
