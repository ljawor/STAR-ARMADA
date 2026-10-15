# LAN reconnect: experimental same-host live integration

## Status and scope

**Experimental same-host recovery, enabled by the LAN menus.** The v0.15.0 source
increment repairs the admission, initial-launch delivery and constructor-cleanup
defects documented during the earlier experimental merge. The owner authorized
those fixes and release v0.15.0; final protected integration, native source CI and
downloaded-package gates passed. This is not physical mixed-machine acceptance.
The scope is same-host, same-build, same-content trusted-LAN skirmishes with 2–4
humans, including a ready original client losing the initial canonical launch.

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
only after rebinding. Renderer construction now owns its rollback, including
shader programs and display lists allocated before a constructor returns. Real-GL
fault regressions verify resource release, preservation of the original error,
and survival of the active renderer; successful handoff alone is not that proof.

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

## v0.15.0 hardening and historical failures

- **Admission:** authenticated humans and a bounded four-socket unauthenticated
  pool are counted separately. New arrivals displace the oldest incomplete
  admission when that pool is full. An absolute accept-time authentication
  deadline is checked before parsing; partial bytes cannot renew it. Real-TCP
  regressions cover 2/3/4-human original-slot recovery and partial-byte expiry.
  This bounded pool is not protection against a sustained connection flood.
- **Initial launch:** a ready lobby client with original credentials can retry
  after EOF before receiving `start`. Authenticated original-slot recovery at
  tick zero re-delivers the validated canonical launch; an existing graph is not
  rebuilt. Host initial-flush EOF enters recovery. The initial checksum barrier
  still waits for every human graph. Lost/partial-start tests cover 2/3/4 humans,
  and a spawned client-process test verifies slot identity and the tick-8 hash.
- **Constructor rollback:** post-allocation failures release candidate programs,
  shaders and display lists, continue independent cleanup after an error, and
  preserve the original constructor exception. Fourteen real-context tests cover
  these paths and normal idempotent close.
- **Shutdown fixture:** the AST fixture now supplies production's initialized
  `recovery_overlay` local and verifies overlay cleanup before views/pygame quit;
  it does not suppress the exception or weaken shutdown assertions.

- **Prelaunch lobby and skew:** host-detected EOF before `start()` retains original
  slot credentials and revision-bound consent without inventing a graph. Authenticated
  all-peer lobby/credential receipt gates resume; lost ready/unready writes are
  reconciled. Both signs of released startup skew are covered for 2/3/4 humans;
  identical launch re-delivery never rebuilds an already advanced graph. Paid
  tick-3 commands remain once-only in control/peer traces and actual playback.

The earlier PR #107 integration run remains historical **FAIL**: 1,478 tests had
2 shutdown-fixture errors and 8 skips; repository autosaves/campaign changed and
a replay appeared despite its old Python audit reporting no violations. Those
results are not retroactively relabeled. New acceptance uses all five temporary
persistence paths (including balance), a native macOS descendant write sandbox,
an independent Python audit and before/after hashes. Anonymous pipe/socket FDs
are distinguished from filesystem FDs so the spawn test remains executable.
Final whole-tree and package evidence must be read separately.

**Remaining limits:** physical mixed Mac/Windows recovery, attribution of the
original crash, silent-blackhole recovery, trusted signing and frozen Windows
interactive GL/audio/input remain unproven. Silent blackholes can hit global
lockstep timeout before peer-loss recovery; EOF tests do not establish otherwise.
Plaintext bearer credentials require a trusted isolated LAN.

## Verification evidence and limits

Fresh **v0.15.0** acceptance passed the full **1,618-test** protected suite (zero
failures/errors, 8 existing skips), with native sandbox, zero audit violations and
unchanged source/user-data inventories. Independent final network review and native
Windows source CI passed, including admission/launch regressions. Both downloaded
packages passed hashes/integrity and tagged code/data inspection; read-only frozen
macOS smoke and both benchmark modes passed. Durable local evidence is in
`dist/release-v0.15.0/`. These checks do not close native frozen Windows interactive,
physical mixed-machine or silent-blackhole acceptance. The older evidence below is
historical and retains its original failures.

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
- That historical integration remains **FAIL** for its shutdown and persistence
  gates. Fresh v0.15.0 integration is recorded separately, not inferred from it.

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
