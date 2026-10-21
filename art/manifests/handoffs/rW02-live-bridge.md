# Handoff: W02 live frame bridge (producer half)

Status: **implemented and measured on `render/cpp-w02-bridge`; not merged, not active in the game.**
Owner words: "start W02" — recorded as `render-w02-live-bridge-2026-10-21` in
`art/manifests/pipeline_policy.json`. That wording authorizes implementation on a branch. It does
not approve a merge, a launch-path change, a default renderer switch, a speed claim or a release.

## 1. What this step actually proves

The Python producer can turn a running `GameState` into wire bytes inside the migration plan's
1.0 ms serialization budget, and it does so without touching simulation state.

| | Value | Source |
|---|---|---|
| Producer total, shipped frame (638 visible instances) | 0.501 ms | `artifacts/cpp-renderer/w02/producer-receipt.json` |
| Producer total, worst case (638 + 1,400 synthetic transients) | 0.712 ms | same |
| Producer total, all-visible diagnostic (752 instances) | 0.774 ms | same |
| Same encode if `state.can_see` is recomputed per entity | 45.34 ms | same |
| Payload size, worst case | 116,232 B | same |
| `state_sha256` before/after the run | unchanged (`8179f6f0…`) | same |

The 1.0 ms figure is a **producer cost**, not latency and not a frame rate. See
`docs/RENDER_BRIDGE_W02.md` for the layout, the ring, and the two traps that the numbers exist to
prevent (per-entity visibility queries; record-tuple building in the hot path).

## 2. What landed on the branch

- `render_bridge/packed.py` — v2 packed frame profile: 48-byte header, 68-byte instance records,
  52-byte transient records, content-hashed binding/kind tables, fail-closed decoder.
- `render_bridge/ring.py` — single-producer memory-mapped ring, 64-byte header, seqlock slot tags
  validated **before and after** the payload copy, drop-oldest, oversized frames refused before
  they can damage a good slot.
- `render_bridge/collect.py` — read-only gather with per-collector memoization of
  `(kind, data_id, faction) -> (binding, scale)`, plus `collect_into()` which packs straight into
  the caller's buffer with no intermediate records.
- `tools/render/measure_bridge.py` — the receipt generator; refuses to write a receipt if the
  simulation hash moved.
- `tests/test_render_packed.py` (9), `tests/test_render_ring.py` (6) — round-trip, every rejection
  path, both-path equivalence, and a threaded writer/reader that caught a real torn read.
- `render_cpp/include/frame_v2.hpp` — the consumer's decode half: header-only, GPU-free decoder and
  ring reader with the same validation order as the Python decoder, plus non-finite rejection.
- `render_cpp/tests/test_frame_v2.cpp` + `render_cpp/tests/fixtures/` — decodes frames authored by
  `tools/render/write_frame_fixtures.py` (`--check` for drift); `ctest` target `frame_v2`.
- `docs/RENDER_BRIDGE_W02.md`, ledger update, and this handoff.

Two defects were found by writing these tests rather than by reading the code: `latest()`
re-read the published counter inside the read attempt (so the newest frame could silently read as
overwritten — fixed on both sides with one header snapshot per attempt), and a patch dropped an
`push_back` that the count assertion caught immediately. The sabotage matrix in
`docs/RENDER_BRIDGE_W02.md` §6 records which removals the tests catch and which one they do not.

## 3. Commands actually run

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_render_packed test_render_ring -v   # 15 tests OK
.venv/bin/python tools/render/measure_bridge.py --out artifacts/cpp-renderer/w02/producer-receipt.json
.venv/bin/python tools/render/write_frame_fixtures.py --check                           # FIXTURES_OK
cmake -S render_cpp -B render_cpp/build-w02 ...   # same bgfx prebuilt pins as W01
cmake --build render_cpp/build-w02 --target test_frame_v2 test_scene test_camera
ctest --test-dir render_cpp/build-w02                                                 # 3/3 passed
```

The ring test was repeated five times after the seqlock repair (`OK` each time). No full suite, no
native rendering and no C++ build was run for this step.

## 4. Known gaps and traps for the next chat

- **Nothing draws these frames yet.** The decode half exists and is tested; there is no draw path,
  no interpolation and no camera mirror, so the ≤ 2-frame latency gate, dropped-frame counts and fps
  at 200/400/600 ships are all unmeasured.
- **The post-copy tag re-validation has no deterministic control.** Its removal is not caught by the
  native concurrent test at a realistic publish rate; the Python threaded test caught it when the
  producer ran unthrottled. Keep both tests, and do not read the native one as covering that guard.
- **`build-w02` is a local build directory** configured against the W01 bgfx prebuilt pins; it is not
  part of the branch.
- **Equal-workload benchmark still missing.** Fog, HUD and planets are absent from every number
  here; the migration plan's owner gate ("owner sees a live battle") is untouched.
- **Who supplies the visibility set is a design decision, not a detail.** The gather needs the set
  the renderer already computed. If W03 replaces HUD/menu drawing, the set must still come from
  one place per frame, or the producer silently reverts to the 45 ms path.
- **Effects are the ceiling, not a sample.** The worst case uses the simulation's own caps (1,200
  effects, 200 projectiles) with synthetic records.
- **`Windows signal` is still disabled** by the owner, so this step has local evidence only.
- A frame that exceeds the ring slot capacity is refused by the writer. If a future frame profile
  grows, size the ring deliberately — a refused publish is a dropped picture, not a corrupt one.

## 5. Live draw path (landed with this step)

- `render_cpp/src/viewer.cpp` gained `--ring`, `--tables`, `--seconds`; the snapshot still supplies
  the mesh catalogue and camera, instances come from the ring, drawn by the reviewed W01 path.
- Pose is recovered as `(position, yaw, scale)` and interpolated as an angle and a scalar
  (`pose_from_matrix`, `lerp_angle`, `write_instance`), covered by `test_pose` in `ctest frame_v2`,
  including the degenerate-scale refusal. Writing the matrix element-wise shrinks a turning hull.
- Producer: `tools/render/stream_ring.py` steps a real `GameManager` and publishes every tick.
- Receipt: `artifacts/cpp-renderer/w02/live/live-receipt.json` (+ `detection.png`, producer and viewer
  JSON, `gather-receipt.json`, `motion.json`). Player-visible stream: 1434 frames drawn, 54 adopted,
  0 dropped, decode 0.716 ms median, frames behind median 0 / p95 0 / p99 1 (gate <= 2 met).
- Producer cost is now inside the 1.0 ms budget on real combat frames: 0.964 ms median for 736
  instances + 1,426 transients, after replacing the transient generator with a direct pack loop
  (2.6x, interleaved A/B). `tools/render/measure_gather.py` is the bench and the regression tool.
- Player visibility is supplied per frame (`visible_ids`, `effect_allow`, `projectile_allow`);
  computing it in the legacy predicates costs 105 ms/frame and belongs to the renderer, not the
  bridge. The stream still runs at 3.0 Hz because the Python tick costs 179 ms.
- Defect found by the new health test: every instance carried hp = 0 and the disabled flag, because
  the reader asked for `hp`/`max_hp` while `Entity` stores `hull`/`max_hull`.
- `Ring.create` now takes an exclusive lock and refuses a second producer. It was added because a
  second producer silently truncated the header during this work and produced phantom drop counts.

## 6. Next executable step

The bridge is wired; what remains is the part that makes a number mean something: the equal-workload
scene (fog, HUD, planets, transients drawn) at 200/400/600 ships, and handing the producer the
renderer's player-visibility set instead of `all_visible`. Then the owner's live-battle check. Do not
merge, switch the default renderer, or call W02 done on this receipt alone.
