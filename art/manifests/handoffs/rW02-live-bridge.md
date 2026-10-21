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
- `docs/RENDER_BRIDGE_W02.md`, ledger update, and this handoff.

## 3. Commands actually run

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_render_packed test_render_ring -v   # 15 tests OK
.venv/bin/python tools/render/measure_bridge.py --out artifacts/cpp-renderer/w02/producer-receipt.json
```

The ring test was repeated five times after the seqlock repair (`OK` each time). No full suite, no
native rendering and no C++ build was run for this step.

## 4. Known gaps and traps for the next chat

- **Nothing consumes these frames yet.** The C++ side must decode, interpolate and draw them; the
  ≤ 2-frame latency gate, dropped-frame counts and fps at 200/400/600 ships are all unmeasured.
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

## 5. Next executable step

Give the viewer a consumer: read the ring, validate the v2 header, decode instances and transients,
interpolate between the two newest frames, and record latency plus dropped frames. Then run the
equal-workload scene before any speed statement is made. Do not merge, switch the default renderer,
or claim W02 done on the producer receipt alone.
