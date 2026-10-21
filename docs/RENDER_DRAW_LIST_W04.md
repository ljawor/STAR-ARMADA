# W04 — the input return path (design and evidence)

Status: **implemented, verified locally**. No tag, no release, no default-renderer change.

W03 carried the picture out of Python. W04 carries the player *in*: the C++ window records what the
pointer and the keyboard did, publishes it on a ring, and the Python simulation feeds those events
to the very controller that a native pygame window feeds today.

## 1. The rule this package must not break

Every command stays in Python. The window has no simulation authority, no prediction, no
optimistic selection: it records events. `InputController.handle_event` still turns events into
PlayerCommands, and the simulation still validates them. If the window and the game disagree, the
game is right by construction.

## 2. Wire format

`render_bridge/input.py` (Python) and `render_cpp/include/input_ring.hpp` (C++) implement the same
format, and both are tested against the same fixture file.

```
batch header, 20 bytes:  8s magic 'ARMINP01' | u16 version | u16 count | u32 reserved | u32 crc32
record, 16 bytes:        u8 kind | u8 button/modifiers | u16 code | i32 x | i32 y | u32 extra
```

* `kind`: motion, button down/up, wheel, key down/up, focus lost, resize, quit.
* `code`: printable keys carry **their ASCII value**; everything else is one of the shared
  `KEYCODE_*` / `kCode*` constants. SDL keycodes never cross the bridge — a window that mapped them
  itself would drift the first time SDL renumbers a scancode, and the symptom would be "that key
  does nothing", not a format error.
* `extra`: for resize, `(width << 16) | height`.
* The CRC covers the records; a malformed batch is refused whole, never half-applied.

Transport is the same single-producer ring as W02 (`render_bridge/ring.py` layout), written by the
window this time. Drop-oldest applies: input that a stalled consumer never read is gone, and
`RingInput.report()['batches_skipped']` says how much.

## 3. What the window does

`armada_viewer --input-ring input.bin [--input-slots 48]`:

1. Creates the ring, then publishes one **resize** batch carrying the window size, so the consumer
   maps pointer pixels without assuming a size.
2. Records every SDL event it polls, and publishes one batch per frame.
3. Reports `input.{batches,events,published,unmapped_keys,coordinates,window}` in its JSON report.

`--input-exercise` pushes a scripted click/key sequence through the real SDL pump (labelled
`synthetic` in the report) so the return path can be replayed end to end without a human.

## 4. What the game does

`render/input_bridge.py::RingInput` reads batches and calls `controller.handle_event` with the
pygame event objects the game already handles, then `controller.update()` in the producer loop
(`tools/render/stream_ring.py --input-ring …`). Two conversions are explicit:

* **Coordinates** — HUD surface is a fixed W×H; the window can be any pixel size, so pointer
  positions are scaled onto the surface. A click must select the same ship at 1280×800 and at
  2560×1600.
* **Sampling** — `poll()` drains what has been published since the last call, oldest first.
  `limit=1` gives frame-accurate held-key behaviour for a consumer that keeps up; draining
  everything means a click is never lost but a press and its release can land in one tick.

## 5. Evidence

| What | Result | Where |
| --- | --- | --- |
| Native encoder == Python encoder, byte for byte | 14 events, **244 bytes identical**, 8 malformed frames refused | `render_cpp/tests/test_input.cpp`, `tools/render/write_input_fixtures.py` |
| Python codec + ring reader | 22 tests (round trip, 7 refusals, pygame mapping, no replay/reorder) | `tests/test_render_input.py` |
| Bridge drives the real controller and real state | 10 tests against a live `GameManager` skirmish: space follows the selection, released key stops the yaw, pointer scaled 2× onto the surface, late attach replays nothing, 4 of 12 batches reported as overwritten | `tests/test_input_bridge.py` |
| Native bytes drive the real controller | 9 events → follow id 18, yaw 45→43 while held, wheel distance 3000→3409, click changes the selection | `tools/render/replay_input_ring.py`, `artifacts/cpp-renderer/w04/input-replay.json` |
| Live: producer + window together | attached after 1.66 s, **7 of 9 scripted events delivered**, 5 batches, 0 skipped, 0 unmapped; the controller answered "select a unit to follow" because the fixture seeds no selection — the decision is the game's | `render_cpp/live.command --input-exercise`, `artifacts/cpp-renderer/w04/live-producer.json` |
| C++ suite | 5/5 (`scene`, `camera`, `overlay`, `input`, `frame_v2`) | `ctest` in `render_cpp/build-w02` |

## 6. Limits, stated rather than glossed

* **No frame-rate claim.** Nothing here is an equal-workload benchmark.
* **The live producer is slow in this fixture**: `--fixture four-player-combat-v1` steps at a
  142 ms median (≈2.4 Hz), so the window publishes far more input batches than the game reads. The
  bridge drains everything each tick and reports what it skipped; a click made during a slow tick is
  still applied late, and held-key camera motion degrades because press and release can arrive in
  the same tick. Fixing that properly needs event timestamps and a replayed key state across ticks
  — W05 territory, not silently patched here.
* **The window still owns its own shortcuts** (Esc quit, S screenshot, F/H toggles) and publishes
  those keys too. A real session will need the game to decide which keys the window may keep.
* **Menus are not bridged.** A click reaches the HUD hit-test path, but no menu frame has been
  exercised.
* **Nothing verified on Windows/D3D12.** The ring writer in `input_ring.hpp` is POSIX
  (`mmap`/`flock`).
* **CI is disabled** by owner instruction; all of the above is local evidence.

## 7. Files

* `render_bridge/input.py` — batch codec, `Event`, `pygame` mapping, `InputReader`.
* `render_cpp/include/input_ring.hpp` — native codec and single-producer ring writer.
* `render_cpp/src/viewer.cpp` — `--input-ring`, `--input-slots`, `--input-exercise`, SDL→wire key and
  modifier mapping, per-frame publishing, `input` block in the report.
* `render/input_bridge.py` — `RingInput` (coordinate scaling, sampling, counters).
* `render/input.py` — one change: the wheel handler now takes the event's position instead of
  asking the local window for the pointer, which a bridged controller cannot do.
* `tools/render/stream_ring.py` — `--input-ring`; attaches when the window's ring appears, drains it,
  runs `InputController.update`, and reports the counters.
* `tools/render/write_input_fixtures.py`, `render_cpp/tests/test_input.cpp` — cross-language fixture
  parity.
* `tools/render/replay_input_ring.py` — native ring → real controller receipt.
* `render_cpp/live.command` — passes both rings; stops the producer with a signal it can report on.
