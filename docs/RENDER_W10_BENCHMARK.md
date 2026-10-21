# W10: the same workload on both sides

Every earlier number measured one side. W05's publish figures excluded drawing; the window's frame
times excluded simulation and HUD composition. Neither is a frame rate, and neither could tell anyone
whether the new renderer costs more than the old one.

`tools/render/bench_equal_workload.py` builds `four-player-combat-v1`, trims it to N ships (stations,
planets, HUD and fog kept), publishes N frames through the real `LiveSession`, and then draws the
resulting rings through the real window. Both sides see the same content at 1280x800.

    PYTHONPATH=. .venv/bin/python tools/render/bench_equal_workload.py --sizes 200,400,600 --frames 45

Medians of 45 samples, this machine, 2026-10-21 (`artifacts/cpp-renderer/w10/bench.json`):

| ships | cue vertices | producer frame | producer HUD | emit | fog | window wall | window GPU |
|---|---|---|---|---|---|---|---|
| 200 | 21,888 | 0.12 ms | 4.22 ms | 0.57 ms | 0.19 ms | 2.82 ms | 2.10 ms |
| 400 | 37,088 | 0.14 ms | 5.80 ms | 0.84 ms | 0.21 ms | 0.89 ms | 2.23 ms |
| 600 | 52,288 | 0.18 ms | 7.99 ms | 1.15 ms | 0.27 ms | 1.79 ms | 1.99 ms |

p95 at 600 ships: HUD 8.73 ms, window wall 6.64 ms.

## What this says

**The HUD is the cost, on both paths.** Composing it costs 4.2 ms at 200 ships and 8.0 ms at 600 -
it is the same `render/hud.py` the legacy renderer calls, so a legacy match pays it too. This is the
cost Design A keeps in Python on purpose, and the reason the owner's fallback ("if we later discover
that we have big costs on the hud we can still run a migration project for this part separately")
still has something to migrate.

**The bridge itself is cheap.** The world crossing costs 0.12-0.18 ms; emissive 0.57-1.15 ms; fog
0.19-0.27 ms. At 600 ships the bridge adds roughly **1.6 ms** on top of a HUD both renderers pay.

**The window is not the bottleneck.** 1.99 ms of GPU time and 1.79 ms median wall at 600 ships, with
39 draw calls. The 2.82 ms wall at 200 ships is first-frame shader/pipeline setup leaking into the
median of 45 samples, not a cost that grows with content - the mean (2.99 ms) and the 600-ship median
(1.79 ms) show it does not.

## What this does not say

- **Not a frame rate.** The simulation is not stepped and no audio runs; the fixture state is static.
  These are draw-and-cross costs per frame on fixed content.
- `submitted_triangles_per_pass` (**394,928**) is the shipped mesh catalogue the window always loads,
  not the ring content; it does not vary with ships and is not a workload measure.
- 88 instances is what the camera sees of the trimmed fixture at the window's default pose; the
  per-ship costs above scale with the *published* set (cue and shield counts), which is what the game
  pays for regardless of what is on screen.
- Local machine, one run each. No claim is made about Windows or about a 60 FPS target.
