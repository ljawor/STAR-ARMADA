# LAN reconnect: tested foundation, not a shipped reconnect flow

## Status and scope

`game/net/reconnect.py` supplies opt-in primitives for **same-host, same-build,
same-content LAN skirmishes**. They are deliberately **not enabled in
`LanSession` or `main.py`**. A production joined-peer disconnect, loading timeout,
protocol error, or desync still terminates the match. There is no host migration,
new reconnect button, automatic reconnect, or promise of process-restart recovery.

This is the narrow foundation permitted by the implementation request. Do not
mark LAN reconnect complete based on its diagnostic. The diagnostic externally
quiesces simulations at one canonical tick; it does not discover that barrier in
an interrupted production lockstep session.

## Delivered APIs

- `capture_snapshot(manager) -> bytes` and `restore_snapshot(bytes) -> GameManager`:
  full-precision dataclass fields, integer/tuple dictionary keys, sets and tuples,
  queued commands, all AI instance variables excluding `state`/`ds`, trading,
  squadron, victory and mission state, plus command-capacity timer. The new
  campaign-script object's triggers/progress are explicitly represented rather
  than following its cyclic manager references. Mission-bearing managers are
  rejected: LAN currently launches skirmishes only.
- Restoring constructs a **new** manager with all systems pointing to its **same
  restored state**. Constructor-time visibility/queue resets happen before the
  snapshot fields are installed. Spatial/query caches are rebuilt/lazy; events,
  visual effects, floating text and transient recorder/network pointers are not
  transported. No pickle, dynamically imported wire types, float rounding or
  `GameState.to_dict()` substitution is used. Unsupported future field types
  fail closed. Maintain this schema and checksum together when new mutable
  simulation-system state is introduced.
- Snapshot envelopes require exact game version, protocol, content hash, tick
  and `precise_checksum`. Snapshot size is bounded to **8 MiB**. These are
  authenticated-host data, not a general-purpose hostile save-file sandbox.
- `RecoveryBarrier(humans, content)`: host policy for a **caller-proven already
  quiesced** barrier. `credentials(slot)` returns a random session ID and
  per-slot bearer token, each generated from 32 random bytes, plus credential
  generation/build/protocol. `interrupt(slot, tick=..., digest=..., now=...)`
  starts one absolute **60-second** grace. Further disconnects, authentication,
  loading, heartbeats and polling do not extend it. Pass monotonic transport
  time to `poll`, `authenticate`, `acknowledge`, and `finish`.
- `authenticate(slot, **credentials, content=..., now=...)` checks exact session,
  slot token, credential generation, build, protocol and content. Invalid
  outsider requests raise `ValueError` without killing continuing participants.
  Acknowledgements from authenticated participants must match epoch, canonical
  tick and the digest of the **snapshot + pending-input bundle**. A mismatch is
  terminal. `finish(now=...)` succeeds only after all humans acknowledge and
  before grace expires; it rotates tokens. `abort()` and `host_lost()` are
  terminal. Keep credentials private to the corresponding slot, out of lobby
  snapshots, reports, logs and replay files. Current LAN TCP is unencrypted:
  bearer authentication is for trusted LANs, not protection from network sniffing.
- `PendingInputs(humans, barrier_tick=...)`: bounded authoritative input journal.
  One batch per slot per strictly increasing target tick, at most 64 commands,
  target within the current barrier plus twice the production input delay.
  Assign a per-slot `sequence` **before** transmission. `accept` is idempotent
  only for an identical outstanding retry, rejects changed/skipped/spent
  sequences, and detaches submitted mutable data. `for_tick` returns slot-ordered
  commands. Call `commit_through(executed_tick)` only after execution; spent
  watermarks survive `export()`/`restore()`. The ledger is separate from the
  state's already-committed command queue.
- `ChunkSender(bundle_bytes)` / `ChunkReceiver(expected_digest)`: SHA-256-verified,
  contiguous transfer with **32 KiB raw chunks**, one frame queued per `pump(peer)`
  and backpressure at the existing 64 KiB IO budget. Uses existing `_Peer` framing
  and its frame/buffer limits; no oversized snapshot frame or unbounded enqueue
  loop. The complete transmitted bundle must also fit 8 MiB; the diagnostic's
  base64 snapshot packaging reduces the usable raw-snapshot budget. Reject an
  oversized final bundle instead of silently raising transport limits. Restart
  an interrupted transfer with a new receiver/transfer ID; no
  partial-transfer continuation is promised. The recovery coordinator's absolute
  grace must continue running through all chunk transfer and graph loading.

## Why production integration is intentionally blocked

Production `LanSession` pipelines input/checksum frames three ticks ahead. On
socket loss, host and continuing clients need not be at the same simulation tick.
Its `_pending`, `_sealed`, `_inputs`, `_frames`, `_checksums` and each peer's
`next_tick` are transport state, not recoverable from a `GameState` save. A local
submission may have left `_pending` but not reached the host; another copy may be
accepted or already spent. The current wire input protocol has no persistent
per-submission ID or acknowledged execution watermark. Simply reconnecting a
socket, resetting its turn counters, or replacing one graph silently loses or
repeats inputs. Taking a snapshot while other peers still advance is not a
canonical all-peer pause.

### Required backend work before enabling recovery

1. Add explicit wire-versioned pause/freeze messages and canonical barrier
   selection for **all** humans, including continuing connections. Journal
   committed frames and graph snapshots sufficiently to reconcile bounded
   pipeline skew. Either drain to a proven common barrier with all necessary
   inputs, or roll all graphs back consistently. Never let the live tick driver
   keep stepping one graph after recovery begins.
2. Assign stable input batch IDs at submission/sealing and retain local
   unconfirmed submissions through socket replacement. Reconcile each peer's
   pending/sealed/in-flight inputs against authoritative accepted and spent
   watermarks before finalizing the bundle. Retain original target ticks; do not
   blindly merge journal entries into `GameState.command_queue`.
3. Integrate resume-token issuance into the slot's original authenticated
   handshake, keep disconnected slots reserved, keep the same host listener,
   reject outsiders/stale generations before sending a snapshot, and bind every
   received acknowledgement to that connection's authenticated slot. Do not trust
   a client-supplied acknowledgement slot number as connection identity.
4. Separate **recoverable transport interruption** from fatal protocol/desync
   errors and explicit terminal close/abort. Preserve lobby port-probe handling
   and cold-launch absolute loading deadlines. Host loss is always terminal.
5. Reset/rebuild delayed frame/checksum/sequence pipelines from the authoritative
   bundle, validate every restored graph, then broadcast a single all-peer resume
   epoch. Check the original absolute grace at every phase. Do not start a fresh
   loading deadline or extend it on heartbeats. Start grace at the **first
   detected transport interruption**, not at a later snapshot/quiescence stage;
   pass that original detection time to the foundation policy and check current
   monotonic time before any later phase.

### Required `main.py` / UI seam (no changes delivered here)

The eventual integrated session needs an explicit recovering status, detached
recovery progress (missing slots, time remaining, loading/hash-ack phase), an
abort action, and an atomic restored-manager handoff. Existing
`session.advance(gm, dt)` must return `False` throughout recovery with no
simulation catch-up debt. On handoff, rebind **gm, state, renderer, HUD, input,
audio/event subscriptions, camera/viewer callbacks, recorder/network pointers**
and selection references; clear old accumulator debt. Do not add reconnect UI
that calls these standalone primitives without the backend steps above.

There is deliberately no production `LanSession.resume()`/`reconnect()` API yet.
The tested `restore_snapshot` return value is a seam for future integration,
not an automatically installed game graph.

## Validation fixes and remaining trust boundaries

The detached decoded graph is validated **before any snapshot fields are installed**:
exact core dataclass runtime types and annotated field types, typed entity/player/
fleet/projectile dictionaries with matching IDs, queued `PlayerCommand`s, nested
`SubsystemState`/`Vec3`, discovery snapshots, exploration cells, and typed cooldown/
color/member containers. A dict with identical fields is not a typed object, even
if `precise_checksum` cannot distinguish them. Required AI attributes, ownership,
brain roster (empty before the first tick, complete afterwards), timers, attack
fleet ID and pending-site `(station_kind, Vec3)` entries are checked. Required
system attribute keys/types and fixed config/script/progress dictionary shapes
are checked against a newly constructed empty manager before installation.

Malformed envelope/body/type-tag/collection shapes, unhashable keys/elements,
nonfinite numbers and JSON recursion/encoding errors raise controlled `ValueError`.
The existing 8 MiB byte cap remains; decoded values have a **64 logical-level depth
cap** and **250,000-node aggregate budget** across state, AI and systems (keys,
scalars and containers count). These independently bound deep recursion and
small-node object amplification; they are conservative foundation policy limits,
not a measured maximum supported match size. The JSON parser still allocates the
byte-bounded document before the logical decode budget is applied.

Restored input entries must have exactly `slot`, `sequence`, `target_tick`, and
`commands`. Each slot's outstanding sequences must cover `spent+1 .. next-1`
exactly once; empty gaps and identical duplicate entries are rejected. Normal
`accept` retries remain idempotent. The diagnostic's acknowledgement handler binds
to the **host peer-map slot** and rejects a supplied slot mismatch before policy
mutation. The policy API itself still relies on its caller to supply connection
identity; it does not authenticate sockets.

Remaining boundaries are intentional:

- Only authenticated, same-version/content, trusted-host skirmish snapshots are
  supported. Checksums are integrity/alignment checks, not authorization or a MAC;
  the host can construct a self-consistent but dishonest graph.
- Untyped payload interiors remain host-owned semantics: build/research/damage/
  boarding/crew-mission records, map geometry dictionaries, statistics, extra AI
  strategy values, and script progress collection contents are not exhaustively
  validated as gameplay schemas. Core annotations and explicitly listed nested
  types are checked, but this is **not** a hostile-save sandbox, a complete
  referential-integrity/catalogue/range validator, or proof every accepted graph
  can execute arbitrary future ticks.
- The subsequent replay/save fidelity fix restores canonical `SubsystemState`
  objects instead of dynamically synthesized stubs and preserves future-affecting
  AI/system state in a versioned runtime graph. Ordinary restored graphs can now
  share the codec; old files without runtime state retain a documented fresh-AI/
  reset-timer fallback rather than a historical exactness guarantee.
- Distributed quiescence, original handshake/connection authentication, input
  reconciliation, production recovery wiring, UI handoff, host migration and
  unencrypted-LAN bearer-token risks remain as documented above.

Only focused reconnect tests/diagnostics are run for these fixes; no full-suite,
commit or push is part of this validation change.

## Verification

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_lan_reconnect -v
PYTHONPATH=. .venv/bin/python tools/diag_lan_reconnect.py
```

RED/GREEN cycles covered missing full snapshots, authenticated all-peer policy,
absolute grace/terminal failures, credential generation/build checks, pending
input retries/spent watermarks/turn bounds and bounded real TCP transfer.

The focused diagnostic reports `LAN_RECONNECT_FOUNDATION_OK` for **2, 3 and 4
humans**. It opens actual loopback TCP connections, closes a participant socket,
detects EOF, keeps other sockets alive, reconnects to the same listener/port,
rejects an invalid token, transfers the authoritative snapshot/input bundle,
restores every peer and requires every hash acknowledgement. It compares exact
checksums at the restored tick and **every one of 60 following ticks**, with one
actual delayed human command per slot executed exactly once per graph. Two- and
three-human scenarios also preserve an active AI brain. This is a single-process
multi-graph test using real sockets, **not** independent-process live reconnect
acceptance. A second actual disconnect replays the old rotated credential and
proves rejection. Real TCP heartbeats accompany fake monotonic times through
absolute grace expiry; TCP abort and observed host EOF are terminal policy
scenarios. These remain externally driven foundation tests, not live main-loop
recovery tests. Separate unit tests cover fatal recovery-hash mismatch and loading
that cannot outlive grace. A separate chunk test transfers a payload larger than
both the production frame and send-buffer bounds.

Existing fatal protocol/disconnect and startup deadline tests remain unchanged
and pass. Existing `tools/diag_lan.py` was also exercised in two independent
processes with both 33/33/34 ms pacing and real SDL `Clock.tick(30)`: 180 ticks,
181 exact aligned hashes, nonzero human/AI inputs, and more than 27 ticks/second
for both peers in both modes. No reconnect logic is added to the ordinary
simulation hot path. Full suite, GL/menu acceptance and mixed-platform tests are
left to the parent integration gate.
