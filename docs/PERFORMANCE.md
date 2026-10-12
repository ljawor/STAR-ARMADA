# Performance benchmark — issues #59 and #54

This is a measurement tool, not a claim that Windows performance is accepted.
The GPU already renders the world through OpenGL; issue #59's proposed GPU
rewrite is a hypothesis, not evidence of the bottleneck. No simulation work
has been moved to a GPU and no entities, effects, meshes or visual passes are
removed by this change.

## Filip: run on the Windows laptop

Use the published **v0.11.0** build, not an older released executable.
Keep the laptop plugged in, record the Windows power mode, and close unrelated
CPU/GPU-heavy programs. Use the same settings and GPU for every comparison.
A native Windows machine is required for Windows performance acceptance.

From a source checkout, in PowerShell at the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --benchmark --mode sim --units 500 --frames 60 --warmup 10 --output "$HOME\Desktop\armada-sim-500.json"
.\.venv\Scripts\python.exe main.py --benchmark --mode full --units 500 --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --output "$HOME\Desktop\armada-full-500.json" --screenshot "$HOME\Desktop\armada-full-500.png"
```

For the published v0.11.0 Windows ZIP, run from the extracted game
folder (it does not need Python, git or the source tree):

```powershell
Start-Process -FilePath '.\STAR ARMADA.exe' -ArgumentList '--benchmark --mode sim --units 500 --frames 60 --warmup 10 --output armada-sim-500.json' -Wait
Start-Process -FilePath '.\STAR ARMADA.exe' -ArgumentList '--benchmark --mode full --units 500 --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --output armada-full-500.json --screenshot armada-full-500.png' -Wait
```

The GUI executable has no console: read the JSON files in that writable folder.
Repeat full mode with `--units 200`, and repeat each measurement three times
with separate output filenames. Then repeat full mode with `--vsync 1` to
isolate driver/display pacing. Keep requested MSAA/resolution identical; the
JSON includes the actual GL sample count, viewport, GPU and driver. If a
requested context is unavailable, `status: error` is diagnostic evidence, not
a valid performance result. Do not disable Windows security policy to accept
this work. Send JSON, PNG, laptop/GPU model, power mode and the tested build/PR
revision; user-specific filesystem paths are not included in normal reports.

macOS/source equivalent:

```sh
.venv/bin/python main.py --benchmark --mode sim --units 500 --frames 60 --warmup 10 --output /path/to/armada-sim-500.json
.venv/bin/python main.py --benchmark --mode full --units 500 --frames 60 --warmup 10 --vsync 0 --msaa 4 --output /path/to/armada-full-500.json
```

The output directory must already exist and be writable. Closing the benchmark
window cancels the run and produces an error report rather than partial
success. Normal game settings/saves, audio and menu initialization are bypassed.

## What the JSON measures

Schema version 1 uses the seeded `corvette-combat-v1` fixture: alternating
factory-built Imperial corvettes holding in two dense opposing rows, plus one
remote command station per side. The stations prevent annihilation from turning
later steps into no-ops. Every frame executes exactly one 1/30-second manager
tick, independent of wall-clock speed. Warmup frames execute but are excluded
from timing samples. Actual ticks, initial/final live counts, per-sample entity,
projectile and effect counts, and full-precision initial/final state hashes are
included. This controlled synthetic stress scene excludes AI, input, menus,
cinematics and audio; it is not a complete human-match benchmark.

Full mode creates a real SDL OpenGL window and preserves all world/HUD passes:

| Stage | Included work |
|---|---|
| `sim` | Real complete `GameManager.step`, not just movement |
| `camera` | Production `Camera.apply`, geometry refresh and GL matrices |
| `world` | Production renderer, including its additional camera apply |
| `hud` | Floating text projection, Surface composition, upload and GL draw |
| `swap` | `pygame.display.flip`, including any driver/vsync wait |
| `frame` | Those stages plus loop overhead, excluding final evidence readback |

Timers use `perf_counter_ns`. `glFinish` after camera/world/HUD makes GPU/driver
completion attributable to the stage that submitted it. These are synchronized
CPU + driver + GPU durations, **not pure GPU timer-query measurements**, and
are not ordinary gameplay FPS: synchronization removes normal CPU/GPU overlap.
No artificial frame cap or sleep is used. `mean_ms`, `median_ms`, nearest-rank
`p95_ms`, maximum, sample count and all raw samples are retained. Screenshots
are captured from the back buffer before swap and vertically corrected.

Requested vsync is separate from the reported SDL swap interval. The latter
may be `null` where pygame's linked SDL symbol cannot be resolved, particularly
with Windows loaders; never assume that a requested setting was honored.
Driver control-panel overrides can still change pacing. The legacy pygame
`GL_SWAP_CONTROL` constant aliases another GL attribute and is not used.

## Measured macOS result

A completed 24-trial comparison used three alternating baseline/candidate trials
for 200 and 500 corvettes in both sim-only and full modes, 30 measured ticks
plus five warmup ticks. Baseline: `470e467`. Machine: Apple M4, macOS 26.6.2,
Python 3.11.16, pygame-ce 2.5.8, Cocoa, OpenGL 2.1 Metal, 1280×800, actual 4×
MSAA and SDL-reported swap interval 0. Values below are the median of each
trial's median. Run the comparison without concurrent tests or heavy jobs:

```sh
.venv/bin/python tools/benchmark_compare.py --output-dir /path/to/evidence
```

| Workload / stage | Baseline ms | Candidate ms | Reduction |
|---|---:|---:|---:|
| 200 ships, sim-only tick | 8.545 | 7.035 | 17.7% |
| 500 ships, sim-only tick | 39.674 | 24.268 | 38.8% |
| 500 ships, full-mode simulation | 40.924 | 25.736 | 37.1% |
| 500 ships, full-mode HUD | 8.793 | 6.399 | 27.2% |
| 500 ships, synchronized full frame | 150.392 | 125.711 | 16.4% |

All 24 runs executed 35 ticks with active combat during the measured interval;
initial and final precise simulation hashes matched across baseline/candidate
and modes. Final real-GL framebuffer hashes matched across every corresponding
full-mode trial. This is controlled stress-scene evidence, not normal gameplay
FPS or Windows performance acceptance. Rendering remains the largest measured
stage (500 ships: world 94.538 → 90.824 ms); this PR does not claim it is solved.

The changes address measured CPU work: reject farther target candidates before
expensive live visibility checks, prune separation neighbors in fine bins while
preserving authoritative coarse-grid order and sequential pushes, and bulk-write
the exact fog raster instead of querying/writing every texel in Python. No
rendering passes, ships, effects or gameplay interactions are dropped.
Instrumented profiling is separate from timing: in the 500-ship, ten-tick
control, target validation calls fell from 234,084 to 115,186 (see generated
profile JSON; this is not a universal bound).

## Scope and acceptance matrix

| Gate | Status / required evidence |
|---|---|
| CPU bottleneck reproduced on current main | Measured 500-unit combat; detailed report below |
| Nearest-target semantics and visibility | PASS — focused tie/hidden-target tests and live manager differentials |
| Separation semantics and pruning | PASS — mixed-radius sequential-push and every-tick manager differentials |
| Fog raster output and live alliance invalidation | PASS — exact RGBA/live-sensor boundary tests and matching real framebuffer |
| Full precise dictionaries unchanged | PASS — every-tick manager differential + sim/full baseline/candidate hashes |
| Local baseline/candidate per-stage measurement | PASS — 24 fresh-process trials, see results above |
| Real Cocoa SDL/GL world/HUD/swap | PASS — exact final framebuffer hashes match baseline |
| Source CLI + malformed/cancelled report behavior | PASS — focused contract tests and actual sim CLI invocation |
| Native macOS frozen entry point | PASS — downloaded v0.11.0 read-only smoke plus sim/full benchmarks |
| Stable whole-tree regression suite | PASS — 1,009 tests, serialized final-tree run (446.235 s) |
| Independent review | PASS — no blocking security or logic findings; source review only |
| Native Windows packaged function and GPU/driver measurements | **OPEN — Filip's laptop** |
| Windows interactive large-fleet acceptance | **OPEN — Filip**, after measurements and play testing |

Neither issue is automatically closed. The user authorized merge and v0.11.0
publication after the Windows acceptance limitation was disclosed. Native
Windows performance, gameplay and signing/policy acceptance remain open.
Refs #59, #54.
