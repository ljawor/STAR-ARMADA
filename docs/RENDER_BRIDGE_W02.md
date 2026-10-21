# W02 — Live frame bridge: wire profile and transport

Status: **implementation landed on `render/cpp-w02-bridge`; not merged, not active in the game.**
Owner instruction for this step: "start W02". No production launch path, default renderer
selection, merge or performance claim is authorized by that instruction.

This document defines what the Python side writes when a *running* match streams frames to the
out-of-process C++ viewer, and what it costs. The offline `.snap` file profile approved in W00
(`docs/RENDER_PROTOCOL.md`) is unchanged and remains the file format for offline captures; the live
profile is a separate, separately-versioned payload and header (section 2).

## 1. Why the payload is not the offline JSON

W00's canonical JSON payload was measured on a real frame before any live design was chosen
(`w02_encode_spike.py`, receipt in `artifacts/cpp-renderer/w02/`). One frame of the
`four-player-combat-v1` fixture with 2,000 synthetic transient records encoded to:

| Profile | Bytes | Median | p95 | Against the 1.0 ms budget |
|---|---|---|---|---|
| W00 canonical JSON | 534 KB | 7.95 ms | 9.70 ms | fails, 8x over |
| Packed structure of arrays | 123 KB | 0.58 ms | 0.73 ms | passes |

Decomposition of the JSON cost: 20,000 transient numbers ≈ 5.7 ms, of which ≈ 5.4 ms is float
decimal text alone; the 7,656 instance matrix floats ≈ 1.5 ms. No amount of tuning in the encoder
removes that, so the live profile is packed and JSON stays an offline, human-inspectable format.

## 2. Frame layout (v2 packed, kind 1)

The live frame does **not** reuse the W00 32-byte envelope. A streaming frame has to carry its own
record counts and the identity of the string tables it was packed against, and folding those into
W00's reserved bytes would have made the approved offline header mean two different things. The v2
header is its own versioned structure; `render_bridge/protocol.py` and the offline `.snap` bytes it
produces are untouched, and a consumer distinguishes the two by magic and version before it parses
anything else. The cost of that choice is one extra envelope parser in the C++ reader, which is
cheaper than an ambiguous header.

Frame header, 48 bytes, `struct.Struct('<8sHHIQIIIIII')`, little-endian:

| Offset | Field | Meaning |
|---|---|---|
| 0 | `magic` 8s | `b'ARMADAF2'` |
| 8 | `version` u16 | 2 |
| 10 | `kind` u16 | 1 = world |
| 12 | `tick` u32 | simulation tick the frame was gathered from |
| 16 | `frame_index` u64 | producer frame counter |
| 24 | `instances` u32 | instance record count |
| 28 | `effects` u32 | transient record count |
| 32 | `table_crc32` u32 | identity of the binding/kind tables this frame indexes |
| 36 | `flags` u32 | frame-level flags |
| 40 | `length` u32 | payload bytes following the header |
| 44 | `crc32` u32 | zlib CRC32 of the payload |

A consumer validates, in this order: magic/version/kind, record counts against its ceilings
(4,096 instances, 8,192 transients), the table identity against the tables it holds, `length`
against the counts, exact total length (trailing bytes are refused), and the payload CRC. Only
then does it decode a record.

Instance record, 68 bytes, `struct.Struct('<IHH4B12f2f')`:

| Offset | Field | Meaning |
|---|---|---|
| 0 | `entity_id` u32 | simulation entity id, stable across frames |
| 4 | `binding_id` u16 | index into the session's binding table |
| 6 | `flags` u16 | bit 0 selected, bit 1 damaged, bit 2 disabled |
| 8 | `tint` 4x u8 | per-owner colour |
| 12 | `matrix` 12x f32 | column-major 3x4: rotation about Y by `yaw`, uniform `scale`, translation `pos` |
| 60 | `hp` f32 | fraction |
| 64 | `shield` f32 | fraction |

Transient record, 52 bytes, `struct.Struct('<BBH3f3f3fff4B')`: `cls` u8 (2 = effect, 3 =
projectile), `is_beam` u8, `kind_id` u16, position 3f, velocity 3f, `end_position` 3f (the beam
endpoint), life f32, size f32, colour 4x u8. Effects and projectiles share one stride and one
array so the consumer walks a single list; `cls` is what separates them, which is why the gather
step stamps it rather than leaving it to the renderer.

Tables (binding names, kind names) are not repeated per frame. `render_bridge/packed.py` serializes
them once per session behind a content hash (`ARMTBL2`), and a consumer refuses any frame whose
`table_crc32` it does not hold. A stable frame is therefore ~43 KB for 638 visible instances
instead of ~100 strings per frame, and the string tables are validated once rather than per
frame.

## 3. Transport: one writer, many readers, drop-oldest

`render_bridge/ring.py` maps a file of fixed slots:

```
header, 64 B:  magic b'ARMADAR1' | u16 version | u16 slots | u32 slot_bytes | u64 published
slot:          u64 begin tag | u32 length | payload | u64 end tag
```

- The writer never blocks on the reader. If the consumer is behind, the oldest slot is reused —
  the picture degrades, the simulation never does.
- Every slot is a seqlock: the writer stamps `2n+1` before copying and `2n+2` after. A reader
  validates both tags **before and after** copying the payload. The second check is the one that
  matters: checking only before the copy lets the writer begin re-using the slot mid-copy, and a
  reader then returns a byte mix of two frames. The ring's threaded test observed exactly that
  before the second check was added, which is why the check exists rather than being defensive
  padding.
- A frame whose length exceeds the slot capacity is refused before anything is written, so a
  mis-sized ring cannot corrupt a good frame that is already in place.
- A reader takes **one** header snapshot per attempt and validates the slot against it. Re-reading
  the published counter inside the attempt looks harmless and is not: a producer that advanced by a
  whole ring between the two reads makes the newest frame look overwritten, and the reader then
  presents an older picture with no error anywhere. The native test found this while it was being
  written (it reported "observed no frames" against a healthy producer), and both readers now hold
  the snapshot fixed for the duration of one read.

## 4. Measured producer cost

`tools/render/measure_bridge.py` re-measures this from a real fixture. Numbers below are from
`artifacts/cpp-renderer/w02/producer-receipt.json` (macOS, Python 3.11.16, host load average 2.77
at the start of the run). "encode" is gather-from-`GameState` + pack + CRC; "publish" is the ring copy.

| Visibility mode | Frame | Instances | Transients | Bytes | Encode | Publish | Total | 1.0 ms gate |
|---|---|---|---|---|---|---|---|---|
| all-visible | shipped | 752 | 0 | 51,184 | 0.552 | 0.001 | **0.553** | pass |
| all-visible | worst case | 752 | 1,400 | 123,984 | 0.772 | 0.002 | **0.774** | pass |
| detection, set supplied | shipped | 638 | 0 | 43,432 | 0.500 | 0.001 | **0.501** | pass |
| detection, set supplied | worst case | 638 | 1,400 | 116,232 | 0.710 | 0.002 | **0.712** | pass |
| detection, recomputed | shipped | 638 | 0 | 43,432 | 45.338 | 0.001 | **45.339** | fail |
| detection, recomputed | worst case | 638 | 1,400 | 116,232 | 46.115 | 0.002 | **46.117** | fail |

Two facts this table is meant to make impossible to forget:

1. **The live writer must be handed the visibility set.** Asking `state.can_see` once per entity
   per frame costs ~45 ms — 60x the whole budget — because each call runs a sensor/detection
   query. The renderer already computes which entities a player can see in order to draw them, so
   the bridge takes that set (`FrameCollector(visible_ids=...)`) instead of recomputing it. A
   writer that forgets this is not "slightly slow", it is 45x over budget.
2. **Record tuples are not the production path.** Building a validated record tuple per entity and
   then packing it measured 2.98 ms/frame. `FrameCollector.collect_into` packs straight into the
   ring buffer with positional `struct.pack_into` calls, pre-resolves the per-owner tint once, and
   leaves validation to the consumer, which must validate anyway. The validating builders
   (`instance_record`, `effect_record`, `pack_frame`/`unpack_frame`) remain the API for tools and
   tests, and the test suite asserts the two paths agree field-for-field.

An earlier version of the same path measured **136 ms/frame** because `asset_registry.resolve`
re-read and re-validated a manifest document per entity, including four `pathlib.resolve()` calls.
The per-collector memoization of `(kind, data_id, faction) -> (binding, scale)` is what removed
it; the offline exporter's behaviour and bytes are untouched by that cache.

## 5. What is read-only, and what is proven

- The producer only reads `GameState`. `measure_bridge.py` computes `state_sha256` before and
  after a full measurement run and refuses to write a receipt if it moved; the run above reported
  `8179f6f0…` unchanged.
- Proven here: the payload round-trips through the consumer-side decoder; corrupted payloads,
  foreign table hashes, out-of-table binding ids, trailing bytes, truncated frames and non-finite
  input are all rejected with `FrameError`; the ring hands back whole frames under a concurrent
  reader; both encoding paths agree.
- **Not proven in this section**: the consumer side. It is measured in §7 (decode, interpolation,
  draw path, frames-behind, drops) — but on a producer-only window, so still not proven anywhere:
  fps at 200/400/600 ships, the equal-workload scenario (fog, HUD, planets, transients drawn against
  the real HUD), player-visibility filtering in the live path, and Filip's Windows laptop. The
  migration plan's "owner sees a live battle" gate is untouched.

## 6. Native consumer (decode half)

`render_cpp/include/frame_v2.hpp` is the C++ side of the same contract: a header-only, GPU-free
decoder plus the ring reader. It validates in the same order as the Python decoder (magic, version,
kind, record ceilings, table identity, length against counts, exact total length, CRC) and then adds
what a renderer needs and Python's decoder also checks — every matrix element, status and transient
number must be finite, because a CRC-valid frame can still carry a NaN if the producer was fed one.

It decodes **bytes this producer wrote**, not frames it made up: the fixtures in
`render_cpp/tests/fixtures/` are authored by `tools/render/write_frame_fixtures.py` (with a
`--check` mode for drift) and committed, so the two languages are compared against one artifact.
`ctest` runs it as `frame_v2` beside the existing `scene` and `camera` tests.

The decoder's checks are shown to be load-bearing rather than merely present. Removing each one in
turn from a scratch copy of the header and re-running the test:

| Sabotage | Result |
|---|---|
| Drop the payload CRC comparison | caught: "accepted a frame it should refuse" (3/3 runs) |
| Drop the table-identity comparison | caught (3/3 runs) |
| Drop the matrix finiteness check | caught (3/3 runs) |
| Drop the post-copy tag re-validation | **not caught** (3/3 runs passed) |

The last row is reported as not caught, not as a pass: at a realistic publish rate (2 ms between
frames) a reader's copy window is microseconds and no writer can cycle a slot inside it, so the
concurrent C++ test cannot falsify that guard. The same removal *was* caught by the Python threaded
test, which ran the producer unthrottled. The guard stays because the window it closes is real; the
honest statement is that its control is the Python test, and the C++ side covers the deterministic
torn-slot case (a slot whose completing tag is missing) instead.

## 7. The live draw path

`render_cpp/src/viewer.cpp` gained a live mode rather than a second program, so the frames being
timed are drawn by the same code path that already passed W01 review:

```
armada_viewer --snapshot live.snap --assets . --ring live.bin [--seconds 8]
```

The snapshot still supplies the mesh catalogue (bindings, scales, camera); instances come from the
ring. Per frame the viewer reads the newest complete frame, decodes it, and writes interpolated
instance records into the same `Group` buffers the offline path uses. Pose is recovered from the wire
matrix as `(position, yaw, scale)` — `yaw = atan2(col2.x, col0.x)`, `scale = col1.y` — and
interpolated as an angle and a scalar, not element by element, because interpolating matrix entries
shrinks a turning hull toward the chord between two rotations. `pose_from_matrix`, `lerp_angle` and
`write_instance` are covered by `test_pose` in the native suite, including the degenerate-scale
refusal and the `+pi -> -pi` short-way case.

The producer side is `tools/render/stream_ring.py`: a real `GameManager`, stepped at 1/60 s, gathered
and published every tick, paced to `--hz` when the simulation can keep up.

Measured once, end to end, `artifacts/cpp-renderer/w02/live/live-receipt.json` (macOS, Metal,
1280x800, MSAA 4, 2048 shadow map, `four-player-combat-v1`, 752 instances):

| Side | Quantity | Value |
|---|---|---|
| Producer | published frames / rate | 152 in 50.1 s = **3.03 Hz** |
| Producer | gather + pack + publish | **1.102 ms** median, 1.381 ms p95 |
| Producer | simulation tick, same frames | **178.9 ms** median, 442.0 ms p95 |
| Producer | computing player visibility | **104.6 ms** median (renderer work, not bridge) |
| Consumer | frames drawn / instances drawn | 1434 in 12 s / **638 of 752** (player-visible) |
| Consumer | producer frames adopted / dropped | **54 / 0** |
| Consumer | decode of a 638-instance frame | **0.716 ms** median, 0.772 ms p95 |
| Consumer | frames behind at draw | median 0, p95 0, p99 1 (**gate ≤ 2: met**) |
| Consumer | wall / GPU frame | 10.18 ms / 7.84 ms median |

These numbers are the *detection* stream: the producer is handed the renderer's visibility
answers (`visible_ids` plus fog predicates for effects and shots, which are not entities and
cannot travel in an id set). The same tick measured all-visible costs the same 0.964 ms, because
this fixture's transients are all inside player 0's sensor range.

Three things this table says that are easy to misread:

1. **The 4.92 Hz is the simulation, not the bridge.** A 752-hull Python tick costs 125 ms median on
   this stress fixture. The bridge spends 2.4 ms of that 127 ms. Nothing about the stream rate is
   evidence about how fast a rendered frame is.
2. **"Frames behind" is the gate in the unit it was written in.** It counts how many producer frames
   were published between the one being drawn and the moment of drawing. Median and p95 are 0 and
   p99 is 1, i.e. the picture is at most one producer frame stale even though the viewer draws ~112
   frames a second. It is not wall-clock latency and not a frame rate.
3. **The budget is met on real frames, and it took a rewrite to get there.** The generator that
   produced transient tuples measured 2.6 ms on a combat frame (1,426 transients). Packing straight
   from the state's own dicts, caching the colour conversion by object identity, hoisting `cos/sin`
   per distinct yaw and inlining the hp/shield fractions took the same state to **0.964 ms**, an
   interleaved A/B of 2.6x. `tools/render/measure_gather.py` is the bench; it steps 300 ticks into
   the fight, measures both visibility modes and asserts the state hash afterwards.

Two defects came out of writing that bench rather than out of reading the code:

- **Every instance carried hp = 0 and the disabled flag.** `Entity` stores `hull` / `max_hull`;
  `hp` / `max_hp` exist only on subsystems, and the reader asked for those with a `getattr` default,
  so the missing attribute silently became 0. It never showed in the picture because nothing draws
  health yet. `tests/test_render_packed.InstanceHealthTest` now asserts an intact hull reports 1.0
  and that damage and disabled flags follow a hull the test sets by hand; reverting the field names
  fails both tests.
- **Computing what the player can see is not free, and the bridge must not own it.** Handing the
  gather a per-record callable cost a Python call for every transient; pre-resolved id sets
  (`effect_allow` / `projectile_allow`) dropped that. The visibility answers themselves cost 42 ms
  (entity sensors) plus 74 ms (fog predicates on 1,426 transients) per frame in the legacy
  predicates — work the renderer already pays, and work the C++ path should do against the fog mask
  instead of querying per effect.

That the picture is live, not a paused snapshot, was checked separately: two reads of the same ring
1.2 s apart differ in **96 ship positions** (max delta 4.381 units) and in transient count
(1,118 -> 1,058), with the ring's sequence advancing 12 -> 15.

The ring is single-producer and now says so: `Ring.create` takes an exclusive advisory lock and
refuses a second producer on the same path. Without it, a second producer truncated the header and
restarted the counter under the first, and a consumer reported thousands of phantom drops — which is
exactly what happened once during this work and produced the guard, not a hypothesis.

## 8. Tests

`tests/test_render_packed.py` (9 tests) and `tests/test_render_ring.py` (7 tests, one of which
drives a reader thread against a live writer and one of which starts a second producer process to
prove it is refused) run without a display or GPU; `ctest` adds
`frame_v2` (native decoder, both rejection matrices and ring reads, also GPU-free). The equivalence test builds the real fixture, encodes through both paths and
compares every field, and asserts the simulation hash is unchanged afterwards.
