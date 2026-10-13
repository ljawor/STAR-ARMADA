# Player-facing replays (Phase 8)

## Record and browse

Skirmishes, campaign missions, loaded singleplayer games and LAN matches record
human commands automatically. The game writes one replay when a match ends,
you leave, quickload replaces it, or the application exits normally. A replay
starts at the initial state of that particular session, not necessarily tick 0.
An interrupted process/crash is not guaranteed to save a recording.

Choose **REPLAYS** from the main menu. Six files appear per page, newest first;
**PREVIOUS**, **NEXT** and **REFRESH** browse the directory. Each row shows its
UTC timestamp and source (**recorded** or fallback **file time**). Recording
creation time takes precedence over file names and modification times, so renamed
or copied current recordings retain their chronological position. Equal timestamps
use filename as a deterministic tie-breaker. Legacy, malformed or unreadable
metadata falls back to the file modification time.

Click a row to **select** it, not to play it. Selection shows mode, duration,
game/format versions and compatibility warnings, or a clear playback error.
**PLAY SELECTED** is the separate launch action; unplayable files remain selectable
and deletable. Failed launch or simulation continuation returns to a usable browser.
**DELETE SELECTED** and **DELETE ALL REPLAYS** require an explicit destructive
mouse click on a separate confirmation screen. **Enter**, **Esc** and **Cancel**
all cancel without deleting. Delete-all includes every direct regular `.json`
file at confirmation time, including corrupt/incompatible files and files beyond
both browser limits. It does not recurse or delete other file types, directories
or symlinks. Successful/failed deletions are counted and reported; paging clamps
after removal and selection clears. Successful writes and write failures remain
reported in the main-menu footer.

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
The browser examines at most 4,096 directory entries and retains the newest
1,000 replays within that scanned subset, with an explicit limit notice. It reads
at most 64 KiB per candidate and 64 complete top-level JSON fields for timestamp
metadata, retaining only small scalar header values. A complete timestamp before
a corrupt or oversized payload can still be used. Browsing/painting does not
reconstruct recordings; only explicit selection and playback invoke the existing
bounded replay loader. Metadata beyond the prefix budget is unavailable and uses
file time. Above 4,096 entries, enumeration is partial (not a global-newest claim);
archive files and refresh to browse another batch. Delete-all is a separate
streaming directory operation with no browse cap.

Deletion rejects outside paths and removes only direct regular `.json` children.
The POSIX backend retains its pinned `O_DIRECTORY | O_NOFOLLOW` directory-FD path
and directory-relative `stat`/`unlink`; both the user directory and replay child
must be real directories. Unsupported handle APIs fail closed, never falling back
to an unchecked path-based delete. Browsing and bounded metadata are unchanged.

The Windows backend uses stdlib `ctypes` and native handles (Windows 8+). It opens
the real local drive root, then **each ancestor component** relative to the already
checked parent with `NtCreateFile`, `OBJ_DONT_REPARSE` and
`FILE_OPEN_REPARSE_POINT`. Reparse points (including junctions, symlinks, volume
mount points and cloud placeholders) and non-directory ancestors are rejected.
Directory handles deny write/delete sharing and remain owned until cleanup, so
renaming/replacing a pinned directory cannot redirect the operation. Child files
are opened relative to the pinned replay directory, reject reparse/non-disk/
directory objects, and are marked for deletion with `SetFileInformationByHandle`
**on that same checked handle**. No child pathname is resolved again for deletion.
Delete-all enumerates that directory handle in bounded 64 KiB batches with no
browser cap; it skips non-JSON/reparse/directory entries and rechecks each opened
candidate. All acquired handles are closed on success and failure; cleanup attempts
every handle even when a close fails, preserving the original operation error.

Only ordinary absolute local drive paths are supported on Windows. UNC/network,
device/extended namespace, mapped/SUBST roots, alternate data streams and ambiguous
component names fail closed. Read-only files, conflicting open handles, permissions
or unavailable native APIs produce visible failures, not forced deletion or changed
file attributes. Neither platform's delete-all is transactional: new files may
appear during enumeration, and partial failures are reported, not rolled back.

Native API contracts are based on the official Microsoft documentation for
[NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[OBJECT_ATTRIBUTES / OBJ_DONT_REPARSE](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes),
[GetFileInformationByHandleEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex),
[FILE_FULL_DIR_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_full_dir_info),
[SetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle),
[FILE_DISPOSITION_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_disposition_info)
and [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew),
with the [Python ctypes reference](https://docs.python.org/3/library/ctypes.html)
for typed calling conventions, structure alignment and Windows error capture.

Writes validate their output and atomically replace the destination using a
same-directory temporary file. A size/recording cap or disk error prevents
saving that replay but never stops the live match. No promise is made for
untrusted files that defeat all semantic validation; these are local data files,
not an executable script/plugin format.

## Verification

Focused regression command:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_replay_library test_replay_deletion_windows test_replay_workflow test_replay_typed_validation test_review_campaign_replay -v
```

The tests compare JSON-normalized `to_dict(precise=True)` at **every** replayed
tick, not the coarse network checksum: AI skirmish continuation, an initial
pending command, actual main factories, two real local TCP LAN peers, and
partial campaign/script restore through staged objectives and reinforcements.
They cover compatibility/size/shape failures, immutable input, pause/speed/end,
bounded paging, atomic save failure, and the actual main-loop error and
campaign-result branches. Existing legacy replay and main/LAN interfaces remain
regression-tested separately.

### Mandatory native Windows deletion gate (currently pending)

Portable policy/ABI/dispatch tests are **not native syscall acceptance**. The
`NativeWindowsDeletionTests` class uses actual temporary files, actual directory
junctions (no symlink privilege required), native selected/delete-all operations,
4,101 replay fixtures, read-only failure reporting, pinned directory/child rename
attempts and post-failure renames to detect leaked handles. File-symlink coverage
also runs when Windows grants symlink privileges; lack of that privilege is the
only optional native skip. Junction, deletion, containment and cleanup cases must
all pass, not skip. No destructive test uses a player's replay directory.

Run on a real Windows runner/host from the candidate checkout (PowerShell; Python
3.11+). This command **fails on non-Windows**, unlike a suite which can pass by
skipping every native test:

```powershell
$env:PYTHONPATH = 'tests'
python -c "import os, unittest; assert os.name == 'nt', 'Native Windows deletion gate requires Windows'; suite = unittest.defaultTestLoader.loadTestsFromName('test_replay_deletion_windows.NativeWindowsDeletionTests'); expected = suite.countTestCases(); result = unittest.TextTestRunner(verbosity=2).run(suite); optional = 'test_file_symlink_is_never_deleted_or_followed'; raise SystemExit(0 if result.wasSuccessful() and result.testsRun == expected and all(test._testMethodName == optional for test, reason in result.skipped) else 1)"
```

Then run the focused regression modules above using Windows `python`, with
`PYTHONPATH=tests`, `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` if headless.
Keep the full native log, Python/Windows versions and exact candidate revision.
**Shipping gate remains open until those results exist.** The implementation was
developed on macOS; its Windows-only tests are skipped there. The `Windows signal`
workflow now runs the mandatory native gate and portable replay-library tests in
addition to LAN tests. A failure or required native skip blocks that workflow;
only the privileged file-symlink test may skip. Read the exact candidate's CI log,
not an earlier green LAN-only workflow, before declaring Windows acceptance.

Real SDL/OpenGL diagnostic (requires a real window server; no SDL dummy video):

```sh
PYTHONPATH=. .venv/bin/python tools/diag_replay_workflow.py --out <new-output-directory>
```

It drives the actual main/menu loop with SDL events, records a live skirmish,
browses all 16 fixtures over three pages, exercises invalid-file UX and playback
controls, checks text bounds/overlaps and GL errors, verifies no gameplay action
buttons remain (view-only panel controls are allowed), and captures the real
framebuffer at 1024×768 and 1280×800. It captures selected/delete-all confirmations,
proves Enter/Esc cancel, deletes a corrupt selected fixture, then deletes over
4,096 temporary replay fixtures while preserving an outside file/symlink.
All destructive checks use the isolated output-directory user root, never the
checkout's real replay library.
The output directory must be new to keep the fixture-count checks non-vacuous.
This is local macOS automation evidence, **not cross-platform interactive or
multi-machine LAN acceptance**. Windows/frozen-package and human interactive
acceptance still require their own runs.
