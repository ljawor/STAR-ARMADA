# LAN reconnect: experimental same-host live integration

## Status and scope

**Implemented in this source, enabled by the LAN menus, not production-ready or
released.** The user authorized an experimental merge despite known blockers,
not stable release approval. The implementation targets same-host, same-build,
same-content trusted-LAN skirmishes with 2–4 humans **after every participant has
received the canonical launch**. Initial launch-packet loss is not recovered.

`LanSession` remains opt-in for programmatic callers: pass `recovery=True` to
`host`/`join`, or call `enable_recovery()` before any handshake bytes are sent.
Every human must opt in; mixed opt-in is rejected. `render/menus.py` opts in before
polling. Unexpected socket EOF retries only the original host address. A live
host process and its original session/listener must survive; there is no host
migration, saved-multiplayer-session load or process-restart recovery. Delivered
shutdown/abort, protocol errors, desync and grace expiry remain terminal.

TCP bearer credentials are plaintext. Use only a trusted isolated LAN; this is
not Internet-facing authentication or an availability guarantee. Returning to
the Join menu starts a new connection rather than restoring a lost slot.

## Implemented backend and application handoff

`game/net/live_recovery.py` drives distributed freeze, bounded released-frame
**drain, never rollback**, and target-tick input reconciliation. Ordinary
`advance(gm, dt)` remains paused; `recovery_step(gm)` explicitly advances at most
one already-released fixed tick. The host selects the maximum reported tick,
requires skew within the delayed pipeline, sends authoritative drain proof, and
requires precise graph agreement before capturing a snapshot. Normal ticks keep
bounded input/frame history, not per-tick graph snapshots.

The live journal identifies a batch by original authenticated slot + target tick;
it is **not** the standalone `PendingInputs` sequence ledger. Unsealed local
drafts, sealed-but-unsent batches, accepted-unspent batches and already-executed
actions are reconciled separately. Conflicting accepted retries, spent entries,
gaps and invalid future frontiers are rejected. The bundle reconstructs pending
inputs, sealed checksums, released frames and peer counters without changing
original paid-command execution ticks.

Original slot-bound private credentials, staged next credentials and all-peer
install ACKs guard resume. Credential rotation commits only after all ACKs;
continuing sockets and the original host listener are retained. Chunked drain
proof, input reports and snapshot bundles use existing frame/buffer caps and
backpressure. One absolute **60-second** deadline begins at first interruption
and covers retries, transfer, graph reconstruction and application installation;
additional interruptions and heartbeats do not extend it.

The caller takes `take_restored_manager()`, prepares the replacement application
graph, then calls `acknowledge_install(manager)`. `main.py` validates the drained
tick/hash and rebuilds camera, renderer, HUD and input references; transfers audio
event ownership without reopening the mixer; transfers the existing recorder;
retains valid selection/groups/follow target; clears accumulator debt; and ACKs
only after rebinding. Partial renderer-constructor failure still leaks resources
(see blockers); successful-path handoff is not exception-safety proof.

The Clean Classic recovery overlay reports missing peers, remaining grace and
actual phase/barrier progress. It blocks world orders, clears pending gestures,
allows camera movement/zoom, and offers **Escape / Cancel reconnect and leave
match**. It does not invent transfer percentages when none are available.

## Snapshot and transfer foundations

`game/net/reconnect.py` supplies the shared graph codec and chunk transport:

- `capture_snapshot(manager)` / `restore_snapshot(bytes)` preserve full-precision
  dataclass fields, typed dictionary keys, sets/tuples, queued commands, AI and
  future-affecting system state, including command-capacity timers and campaign
  script progress without following cyclic manager references. Mission-bearing
  managers are rejected: LAN currently launches skirmishes only.
- A restored manager's systems share its one restored state. Constructor-time
  normalization/queue clearing precedes snapshot installation. Spatial/query
  caches rebuild lazily; event subscribers, visual effects, floating text and
  transient recorder/network pointers are not transported. No pickle, arbitrary
  dynamic imports, float rounding or save-dictionary substitution is used.
- Envelopes require exact version/protocol/content/tick/precise checksum. Core
  dataclass runtime types and annotated nested fields, entity/player/fleet/
  projectile dictionaries, queued PlayerCommands, SubsystemState/Vec3, AI roster
  and required system attributes are checked before installing decoded fields.
  An equivalent dictionary is not accepted as a typed runtime object merely
  because it produces the same canonical checksum.
- Malformed shapes, unhashable keys/elements, nonfinite numbers and recursion/
  encoding errors become controlled ValueErrors. Payloads are capped at **8 MiB**,
  logical decode depth at **64**, and aggregate decoded nodes at **250,000**.
  The byte-bounded JSON document is allocated before logical decode budgets run.
- `ChunkSender` / `ChunkReceiver` use SHA-256 integrity, contiguous **32 KiB raw
  chunks**, one queued frame per pump and existing **64 KiB IO** backpressure.
  Whole bundles must fit the cap; general frame/buffer limits are not raised.
  Interrupted transfers restart with a new receiver, not partial continuation.
- `RecoveryBarrier` and `PendingInputs` remain standalone caller-proven quiet-
  barrier policy primitives, not the production live coordinator/journal.
  `RecoveryBarrier` binds session/slot/generation/build/content and enforces the
  first absolute grace and authenticated all-peer ACKs. Its caller supplies
  connection identity. `PendingInputs` requires outstanding sequences exactly
  `spent+1 .. next-1`, rejects gaps/duplicates/conflicts/spent retries, and keeps
  its ledger distinct from already-committed graph commands.

Trust boundary: snapshots are authenticated **trusted-host** data, not a hostile
save sandbox. Checksums are alignment/integrity checks, not authorization or a
MAC. Untyped gameplay payload interiors, map geometry, statistics and extra AI/
script values do not have exhaustive gameplay/range/referential-integrity
validation. A dishonest host can supply self-consistent state. Supported field
schemas and checksums must evolve together as mutable simulation state changes.

## Known unfixed blockers — experimental merge only

1. **Admission starvation (high):** unauthenticated incomplete-frame sockets count
   against the four-peer admission cap before authentication. Partial bytes renew
   receive-idle time without completing authentication. An independent four-human
   real-TCP probe occupied remaining capacity with two outsiders, rejected five
   valid original-slot retries, then expired grace. Reserved-slot identity does not
   guarantee reconnect availability. No absolute authentication deadline or
   unauthenticated-pool displacement is implemented.
2. **Initial start-packet loss (high):** if the host has entered running but a ready
   client loses the socket before receiving `start`, the client is still lobby and
   cannot enter recovery or construct a manager. Independent 2/3/4-human probes
   reproduce client `Disconnected` while the host waits in recovering. Existing
   startup tests wait for every launch first; they do not cover this boundary.
3. **Partial Renderer construction:** failure after GL display-list/shader program
   allocation can leak those resources because the constructor never returns the
   object to `install_recovered_manager` for cleanup. Current injected-constructor
   tests reject before partial allocation; they do not prove cleanup of that case.
4. **Integrated suite fails:** 1478 tests, 0 failures, **2 errors**, 8 existing skips.
   Both `test_gl_lifecycle.MainLifecycleTests.test_shutdown_closes_views_before_quit_and_handles_menu_only`
   subtests (`started=False/True`) raise `NameError: recovery_overlay is not defined`
   in the AST-extracted shutdown fixture. Immutable base `319250d` passes that
   unchanged test. No guard, weakened assertion or new skip was added to hide it.
5. **User-data preservation failed in that run:** three repository autosaves and
   `campaign.json` changed; `match-8897608fad5c4e888acd33627c52591d.json` appeared in
   replays. Attribution is unresolved despite an audit barrier reporting no
   violations. Application Support files did not change. Original snapshots and
   changed-file evidence are preserved; files were not restored/deleted. Do not
   claim the whole run was persistence-safe or rerun it against real user data.
6. **Acceptance gaps:** physical mixed Mac/Windows recovery and attribution of the
   original crash remain unproven. Silent network blackholes can hit global
   lockstep timeout before peer-loss recovery; EOF probes do not establish
   blackhole recovery. Native Windows headless backend CI does not prove GL
   handoff, frozen packages or interactive mixed-machine play.

No version bump is made: `game/__init__.py` remains `0.14.0`. Repository release
instructions require a feature-branch bump for a release, not every source merge;
this request authorizes neither a stable increment, tag nor publication. Exact
source commits/content, not the unchanged display version alone, identify this
experiment. No release workflow is dispatched by this PR preparation.

## Verification evidence and limits

The completed native Cocoa/real-GL integration report and raw logs live at
`~/.hermes/cache/scratch/star-armada-production-reconnect/integrated/REPORT.md`
and `report.json`; security/start-boundary reproductions are in
`~/.hermes/cache/scratch/lan-independent-review/review.json`. These are local
evidence paths, not committed CI artifacts. Read their failures, not just passes.

- Production diagnostic: all **12 real-TCP** cases (2/3/4 humans × pending,
  lost-before-accept, accepted-unspent, spent), exact control/peer continuation
  through tick 60 and paid queues once. This tight-loop diagnostic uses multiple
  managers in one process and is not an FPS or process-isolation benchmark.
- Separate independent-process recovery evidence covers all 12 cases; it does
  not substitute for physical mixed-machine tests.
- Actual host and joined app probes: unchanged application path, real GL, natural
  paid input before/after handoff, original recording and exact playback;
  31-tick future traces. Overlay measured at 640×480 and 1920×1080.
- Recovery-enabled independent-process SDL Clock pacing: 300 ticks, 301 aligned
  hashes; host 29.303 TPS, client 29.290 TPS against an explicit 27 TPS floor.
- Full integration remains **FAIL** for the shutdown and persistence gates above.
  It is not rerun during experimental-merge preparation.

Windows signal retains every prior check and adds `test_lan_reconnect` and
`test_lan_production_reconnect` to its explicit portable module list. The genuine
GL assertions in `test_lan_recovery_handoff` and `test_lan_recovery_ui` are not run
under that job's dummy video, weakened or relabeled as passing native Windows GL
acceptance. Its pre-existing shared-runner pacing floor remains 15 TPS; that is
not the native 27 TPS hardware acceptance target. Read the exact PR checks for
the final head before making any CI claim.

Focused entrypoints (run with isolated temporary persistence paths):

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_lan_reconnect test_lan_production_reconnect -v
PYTHONPATH=. .venv/bin/python tools/diag_lan_production_reconnect.py --out /absolute/scratch/new-recovery-run --ticks 60
# Real video/GL required, never dummy video:
PYTHONPATH=tests .venv/bin/python -m unittest test_lan_recovery_handoff test_lan_recovery_ui -v
```

The older `tools/diag_lan_reconnect.py` reports foundation-only acceptance for
externally quiesced same-process multi-graph TCP scenarios. Its historical passes
are not live backend, application, process-isolation or mixed-platform proof.
