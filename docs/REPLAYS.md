# Player-facing replays (Phase 8)

## Record and browse

Skirmishes, campaign missions, loaded singleplayer games and LAN matches record
human commands automatically. The game writes one replay when a match ends,
you leave, quickload replaces it, or the application exits normally. A replay
starts at the initial state of that particular session, not necessarily tick 0.
An interrupted process/crash is not guaranteed to save a recording.

Choose **REPLAYS** from the main menu. Six files appear per page; **PREVIOUS**,
**NEXT** and **REFRESH** browse the directory. Rows include mode, duration, game
version and replay format. Invalid files show an error, and failed launch or
simulation continuation returns to a usable browser instead of killing the app.
Successful writes and write failures are reported in the main-menu footer.

Files live under `USER_DIR/replays`, alongside the existing user-data root:
source checkouts use the project directory; frozen macOS apps use
`~/Library/Application Support/STAR ARMADA/replays`. Frozen Windows/Linux
builds use the same platform user-data root as settings. No recording writes
inside a frozen application bundle. File names are unique `match-<uuid>.json`.

## Watch

- **P**: pause/resume.
- **[ / ]**: cycle speed through 0.25×, 0.5×, 1×, 2× and 4×.
- **Esc**: return to the replay browser.
- Camera pan/rotation/zoom, selection and follow are inspection-only.
- Gameplay keys, orders, production, abilities and save/load cannot enqueue
  commands. Production/ability action panels are suppressed during playback.
- The final recorded tick is held with an **ENDED** indicator. Silent time after
  the last command is included; duration is never inferred from that command
  for current recordings.
- Playback never overwrites its input file, records a new match, autosaves,
  quicksaves, or unlocks campaign progress.

## Format and compatibility

The player-facing writer uses JSON format `star-armada-replay`, **version 2**.
It includes a full-precision initial state, ordered accepted human commands,
`end_tick`, `duration_seconds`, fixed `tick_rate` (30), `game_version`,
`content_digest`, mode, map, seed, viewpoint, mod identifiers and creation time.
The content digest covers the effective data-store catalogue/rules/maps/campaign
including mod overrides. The same game version and effective content are
required; missing/changed content is rejected rather than silently replayed.
Replays do not embed mod files.

Current snapshots also include a versioned JSON-only runtime graph preserving
future-affecting AI construction/strategy state, queued work and mutable system timers.
Visible and canonical representations must agree before playback is approved.
Old saves/replays without this runtime state rebuild fresh AI brains and reset those
timers; the browser warns **future-state unavailable** for old v2 recordings. Their
duration remains known, but exact mid-match continuation cannot be guaranteed.
Historical state that was never recorded cannot be recovered by the loader.

V2 command ticks mean **the state tick immediately before `GameManager.step`**.
The recorder observes the manager seam, not input submission. This includes
LAN commands only once they have entered an accepted shared frame. Unaccepted
pending network input is not recorded. AI commands are deterministic outputs
and are not reinjected. Commands already pending in the initial snapshot are
restored exactly once and excluded from the new command log.

The old `ReplayRecorder` / `ReplayPlayer` infrastructure remains available for
existing callers. **V1** files with a restorable state and valid ordered human
commands may be opened with an explicit legacy warning. Their original content
and duration cannot be authenticated: playback stops after the last recorded
command (or immediately for a commandless file). V1 initial pending queues are
rejected as ambiguous rather than risk double execution. Legacy files are not
upgraded or rewritten in place, and legacy compatibility is not a determinism
guarantee for recordings from an older simulation build.

## Bounds and failures

Input is JSON only. Validation precedes simulation construction and bounds:
16 MiB files, 100,000 recorded commands, six hours of absolute 30 Hz tick IDs,
32 nested levels, 750,000 values, 10,000 entities and 16 players/mod IDs.
Nonfinite coordinates/numbers, unsupported versions/rates, bad command shapes,
AI injection, out-of-duration commands and incompatible content are rejected.
The browser examines at most 4,096 directory entries / 1,000 replay files, tells
you when it reaches the cap, and loads metadata only for the visible page.
Archive older files outside the directory and refresh to browse another batch.

Writes validate their output and atomically replace the destination using a
same-directory temporary file. A size/recording cap or disk error prevents
saving that replay but never stops the live match. No promise is made for
untrusted files that defeat all semantic validation; these are local data files,
not an executable script/plugin format.

## Verification

Focused regression command:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_replay_workflow -v
```

The tests compare JSON-normalized `to_dict(precise=True)` at **every** replayed
tick, not the coarse network checksum: AI skirmish continuation, an initial
pending command, actual main factories, two real local TCP LAN peers, and
partial campaign/script restore through staged objectives and reinforcements.
They cover compatibility/size/shape failures, immutable input, pause/speed/end,
bounded paging, atomic save failure, and the actual main-loop error and
campaign-result branches. Existing legacy replay and main/LAN interfaces remain
regression-tested separately.

Real SDL/OpenGL diagnostic (requires a real window server; no SDL dummy video):

```sh
PYTHONPATH=. .venv/bin/python tools/diag_replay_workflow.py --out <new-output-directory>
```

It drives the actual main/menu loop with SDL events, records a live skirmish,
browses all 16 fixtures over three pages, exercises invalid-file UX and playback
controls, checks text bounds/overlaps and GL errors, verifies no gameplay action
buttons remain, and captures the real framebuffer at 1024×768 and 1280×800.
The output directory must be new to keep the fixture-count checks non-vacuous.
This is local macOS automation evidence, **not cross-platform interactive or
multi-machine LAN acceptance**. Windows/frozen-package and human interactive
acceptance still require their own runs.
