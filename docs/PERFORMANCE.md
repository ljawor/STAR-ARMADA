# Performance benchmark — issues #59 and #54

This is a measurement tool, not a claim that Windows performance is accepted.
Windows measurements were taken on the reporter's own laptop and are recorded
below; the gates that remain open are listed in the acceptance matrix at the end.
The GPU already renders the world through OpenGL; issue #59's proposed GPU
rewrite is a hypothesis, not evidence of the bottleneck. No simulation work
has been moved to a GPU and no entities, effects, meshes or visual passes are
removed by this change.

## Windows commands (executed on the reporter's laptop)

These commands were run on the reporter's own Windows laptop; the measurements are in
"Measured Windows result" below. Use the published **v0.11.0** build, not an older
released executable. Keep the laptop plugged in, record the Windows power mode and note
which GPU Windows selects — the GPU is a per-application Windows setting, so "the same
GPU for every comparison" has to be verified in the report's `graphics.gpu` field rather
than assumed. Keep unrelated CPU/GPU-heavy programs closed.

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

## Measured Windows result (native laptop)

Measured on the reporter's own machine: Acer Nitro ANV15-52, Intel Core i9-13900H,
32 GB, Windows 11 10.0.26300, internal 1536×864 display, AC connected, **Balanced**
power plan, 1280×800 with actual 4× MSAA. Two implementations were measured in fresh
subprocesses, three trials per workload: a source checkout at `da417ce` and the
downloaded **v0.11.0** Windows ZIP (sha256 `d576e16e…`, matching the published digest).
Values are the median of each trial's median, in ms.

### As shipped: the OpenGL context lands on the integrated GPU

| workload / stage | source (py 3.14.7) | packaged v0.11.0 (py 3.11.9) | macOS M4 candidate |
|---|---:|---:|---:|
| 200 ships, sim-only | 11.314 | 12.083 | 7.035 |
| 500 ships, sim-only | 36.052 | 40.141 | 24.268 |
| 200 ships, full: sim | 11.546 | 12.276 | — |
| 200 ships, full: world | 96.869 | 91.167 | — |
| 200 ships, full: hud | 7.192 | 7.245 | — |
| 200 ships, full: synchronized frame | 119.050 | 113.575 | — |
| 500 ships, full: sim | 36.746 | 40.863 | 25.736 |
| 500 ships, full: camera | 3.882 | 4.168 | — |
| 500 ships, full: world | 218.987 | 209.978 | 90.824 |
| 500 ships, full: hud | 9.303 | 9.642 | 6.399 |
| 500 ships, full: swap | 0.208 | 0.200 | — |
| 500 ships, full: synchronized frame | 269.943 | 267.178 | 125.711 |
| 500 ships, full, `--vsync 1` frame | 272.182 | 266.871 | — |

Both `python.exe` and `STAR ARMADA.exe` created their OpenGL context on the **Intel
Iris Xe** (driver 32.0.101.6874); no per-app graphics preference was set, and the
NVIDIA RTX 5060 Laptop GPU stayed idle. Relative to the macOS candidate column, the
500-corvette fixture costs about 1.65× the simulation time, 2.31× the world stage and
2.13× the synchronized frame. Rendering is the dominant cost on this platform too:
world is 78.6% (packaged) and 81.1% (source) of the as-shipped synchronized frame at
500 ships.

### Alternating integrated/discrete-GPU A/B

The GPU is selectable per application, so the two settings were interleaved inside one
session (order reversed every trial) with a per-app `High performance` preference
flipped before each child; `GL_RENDERER` confirmed the requested GPU in all 12
full-mode trials.

| workload / stage | Iris Xe iGPU ms | RTX 5060 dGPU ms | change |
|---|---:|---:|---:|
| 500 ships, sim-only (control) | 34.176 | 34.263 | +0.3% |
| 200 ships, full: world | 102.606 | 74.496 | −27.4% |
| 200 ships, full: synchronized frame | 124.305 | 97.740 | −21.4% |
| 500 ships, full: world | 241.787 | 170.818 | −29.4% |
| 500 ships, full: hud | 10.016 | 17.025 | +70.0% |
| 500 ships, full: swap | 0.150 | 0.596 | +297.3% |
| 500 ships, full: synchronized frame | 294.047 | 235.512 | −19.9% |

The CPU-only control is unchanged between the two GPU settings, so the render-stage
differences are a GPU effect and not session drift. The discrete GPU renders the world
27–29% faster and takes 20–21% off the synchronized frame, but the HUD and the swap
stage get markedly more expensive — consistent with a render-offload path that copies
each frame back to the display GPU. World remains the largest stage on both settings.
For a player on this hardware the actionable step is Windows **Settings → System →
Display → Graphics → add `STAR ARMADA.exe` → High performance**; this document does not
claim the game can select the GPU for the user.

### Reproducibility and caveats on Windows

- 72 benchmark trials were run in three sessions (30 as-shipped, 24 with the discrete GPU
  enabled, 18 interleaved A/B). Every trial executed 70 ticks with no early game over,
  showed combat activity in all 60 measured samples, and produced identical full-precision
  initial/final state hashes (`2c81e4fd…` → `880b3b59…` at 500 ships); the frozen Windows
  package reproduces the source build's simulation exactly.
- Real-GL framebuffers are **not bit-exact on every trial**: two variants were captured
  and differ by 3 pixels out of 1,024,000, each by one LSB, in the world pass. The two
  GPUs hash differently from each other, as expected for different rasterizers. Precise
  simulation state never differed.
- `--vsync 1` produced no measurable pacing difference (272.2 vs 269.9 ms at 500 ships)
  and `reported_swap_interval` is `null`, as this document already warns for Windows
  loaders; no driver pacing was observable.
- World is 79–81% of the synchronized frame at 500 ships in the as-shipped sessions
  (73–82% across all six measured configurations) — the largest remaining stage on
  Windows too.
- The packaged build runs Python 3.11.9 and its sim-only medians are 6.8% (200 ships) to
  11.3% (500 ships) above the dev venv's Python 3.14.7 under the same conditions; that is
  an interpreter difference between the packaged toolchain and this checkout, not a
  packaging defect.
- Cross-session drift was up to ~10% on CPU-only stages (source 500-ship sim-only medians
  38.2 / 36.1 / 34.2 ms in three separate clean sessions) and ~10% on GPU stages, which is
  why the GPU comparison above is interleaved in one session.
- An earlier measurement batch was discarded: while the machine was busy it produced a
  2–6× spread and one differing framebuffer hash. Only trials with machine-wide CPU busy
  ≤ 0.45 and no heavy concurrent GPU process were kept (observed busy: 0.08–0.24).
- Full mode is synchronized (`glFinish`) CPU/driver/completed-GPU time, not gameplay
  FPS. The packaged executable reports `Windows-10-10.0.26300` because Python 3.11's
  `platform` module does not label Windows 11; the source run on Python 3.14.7 reports
  `Windows-11-10.0.26300`. Same operating system.

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
| Native Windows packaged function and GPU/driver measurements | PASS — reporter's laptop, 72 trials: source `da417ce` + downloaded v0.11.0 package, both benchmark modes, real GL, GPU/driver/MSAA recorded; see "Measured Windows result" |
| Windows GPU selection and offload cost | MEASURED — OpenGL defaults to the integrated Iris Xe; the discrete RTX 5060 cuts the world stage 27–29% and the synchronized frame 20–21% but adds HUD/swap cost; interactive feel not yet accepted |
| Windows interactive large-fleet acceptance | **OPEN — Filip**, after measurements and play testing |

Neither issue is automatically closed. The user authorized merge and v0.11.0
publication after the Windows acceptance limitation was disclosed. Native Windows
measurements are now recorded above; the frozen package runs and reports on Windows.
Interactive Windows gameplay/feel, Windows signing and security-policy acceptance,
native listening and mixed-platform LAN acceptance remain open. Refs #59, #54.
