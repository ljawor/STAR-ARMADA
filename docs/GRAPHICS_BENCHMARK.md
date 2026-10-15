# STAR ARMADA — Graphics benchmark baseline

## 1. Status and purpose

M0 tooling and initial Mac measurements for `GRAPHICS_UPGRADE_PLAN.md`, collected
2026-10-15 against parent commit `4a6a54e48338f87d10dd505c60afc49de3a21852`
plus the benchmark additions in this PR. No new renderer/look implementation.
**Sections 2–6 describe the original over-capacity stress workloads. Section 7
adds separate stock-rule fleet workloads. Neither is final gameplay acceptance.**
No frame-rate/resolution target has been approved. Windows graphics, packaged
runtime, physical mixed-platform LAN and whole-tree integration remain pending.

## 2. Original versioned stress fixture recipes

Use `--fixture` with one of:

- `four-player-distributed-v1`: player-0 economy/fleet overview, normal local fog.
- `four-player-combat-v1`: established interleaved four-way melee; all 600 combat
  hull centres detected and analytically in the viewport at the measured end.
- `four-player-close-v1`: distributed world, fixed flagship view. Current capture
  shows a modest-size central hull and neighbouring ships, **not an isolated
  material close-up**. A dedicated capital/escort/station art-inspection capture
  is still required at M3. Do not use this capture to claim that gate is met.

Every initial world has 600 combat ships, 40 ordinary stations, 16 extra trade
stations, 64 transports, 8 colonized planets and 32 attached satellites: 760
engine entities. Planets are entities, not an additional hidden map-only count.
Command station counts within the ten ordinary stations: a fixture assumption.

Per-player combat mix: 60 Imperial corvettes, 40 frigates, 30 cruisers,
16 battleships, 4 supercapitals. All four human slots use Imperial, hostile
teams, distinct player colours, stock statistics, no researched upgrades,
strategic AI, build queues or gameplay-rule overrides. This is a versioned
benchmark assumption, not owner approval of this class/faction distribution.
The stock fleet consumes **906 CMD versus 78 capacity per player**. Existing
hulls are set up directly; no conclusion about buildability is valid. Do not
change capacity/balance as part of a graphics benchmark.

Ordinary station mix per player: command, two mining, shipyard, research,
defense, sensor, fighter platform, repair dock and energy relay. Each player
has one temperate and one industrial colony; each has two defense and two
attack satellites. Four trade stations each start four real routed convoys at
staggered progress toward the nearest own trade market.

The 70-tick runs retain all 64 transports. An additional 100-tick distributed
simulation delivered 16 convoys and retained 48; income/traffic and orbital
movement also have focused tests. No refill suppresses stock deliveries/deaths.
All five hull classes and all four owners fired in each successive 100-tick
window of the focused 300-tick combat test. In the recorded 70-tick combat run,
all four owners/all five classes fired, with 1,780 visible shots total.

## 3. Native Mac measurement configuration

Apple M4, model Mac16,3, 24 GiB RAM; macOS/Cocoa; GL `2.1 Metal - 90.5`,
pygame-ce 2.5.8 / SDL 2.32.10. Shader enabled, actual 4x MSAA, requested and
reported swap interval 0. Requested window, observed SDL drawable and GL
viewport all 1280x800. No diagnostic pass skips or no-cull override.

Three sequential fresh-process full runs per fixture, 10 warmup +60 measured
ticks, fixed 1/30 second simulation step. Final capture-adjacent frame/swap is
excluded, leaving 59 frame/swap samples in each trial. All other stages have
60. Table entries are **medians of the three per-trial summaries** (not pooled
samples); raw reports retain every duration and per-sample inventory/activity.

| Scene | Sim mean ms | Camera mean ms | World mean ms | HUD mean ms | Frame mean ms | LAN checksum mean ms | Frame p95 ms | Frame p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| distributed | 70.54 | 12.19 | 234.99 | 103.50 | 421.74 | 27.40 | 444.16 | 450.14 |
| combat | 219.41 | 12.08 | 259.19 | 51.36 | 544.31 | 30.40 | 766.39 | 773.83 |
| close | 70.27 | 12.33 | 235.35 | 104.17 | 423.18 | 27.38 | 447.60 | 451.07 |

These are synchronized diagnostic costs, **not interactive FPS**. Full mode
uses `glFinish` stage boundaries and excludes ordinary input/audio/network/AI.
Separate LAN canonical checksum cost is outside frame/sim stages and says
nothing about socket/barrier/input-delay cost. Frame timing also excludes the
per-sample reporting inventory/visibility/driver queries; sim includes read-only
activity callbacks. `activity_total` includes warmup events; per-sample activity
and timing exclude warmup. Do not sum stage summaries into a claimed live frame
rate. Short runs characterize this starting interval, not sustained battle tails.

Acceptance runs must leave `STAR_ARMADA_DATA` unset and record a SHA256 catalogue
manifest; `GameManager` permits data overrides, so a fixture ID alone is not a
cross-machine asset-identity guarantee. The Mac environment had no override;
the evidence archive includes the repository catalogue/source manifest. Retain
that input identity check on Windows and future baselines.

The workload has no demonstrated room for additional expensive rendering.
Simulation, world and HUD all need measurement-led work for this scale; the
legacy corvette diagnosis must not be generalized to this mixed fleet. The
separate close view still has substantial world cost despite few projected
centres: investigate actual pass/culling cost instead of assuming visibility
metadata is a draw-call census. Keep simulation optimizations separate and
checksum-identical; do not change the tick/pacing to conceal cost.

## 4. Reproduce on Mac and Windows

Create the report directory first. Never pass `--units` for these fixtures.
Warmup +frames must be <=300 ticks (10 simulated seconds), below stock convoy
spawn timing. Longer/sustained workloads require a new reviewed fixture contract.

Mac, from repository root:

```sh
mkdir -p benchmark-reports
SDL_VIDEODRIVER=cocoa .venv/bin/python main.py --benchmark --fixture four-player-combat-v1 --mode full --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --lan-checksum --output benchmark-reports/combat.json --screenshot benchmark-reports/combat.png
```

Windows PowerShell, from repository root:

```powershell
New-Item -ItemType Directory -Force benchmark-reports | Out-Null
.\.venv\Scripts\python.exe main.py --benchmark --fixture four-player-combat-v1 --mode full --frames 60 --warmup 10 --width 1280 --height 800 --vsync 0 --msaa 4 --lan-checksum --output benchmark-reports/combat.json --screenshot benchmark-reports/combat.png
```

Replace the fixture ID for other views. For simulation parity use the same
frames/warmup with `--mode sim`, omit screenshot, and retain `--lan-checksum`.
Use the environment's venv executable **without resolving its symlink**; resolving
to the base interpreter can lose site-packages. One repeat attempt did exactly
that and produced a retained `ModuleNotFoundError: No module named 'pygame'`
error report; it is excluded, not converted into timing evidence.

The legacy default remains `corvette-combat-v1`; its `--units`/state-hash contract
is pinned by tests. Do not use the old `tools/benchmark_compare.py` optimization
comparator for new fixture IDs against a baseline which lacks them.

## 5. Verification and visual inspection

- Parent reran 34 tests: `test_graphics_benchmark`,
  `test_performance.BenchmarkContractTests`, `test_detmath`: all passed.
- Parent reran 33 tests with Cocoa: `test_performance`, `test_fog_render`,
  `test_gl_lifecycle`: all passed. Whole-tree suite **not run** for this milestone.
- Compileall and whitespace checks passed. Static added-source security scan
  found no secret literals, unsafe shell/eval/exec/pickle patterns.
- Precise initial/final simulation hashes and final LAN checksum matched each
  fixture's sim/full runs and all three full trials. These checks establish
  renderer read-only state for these inputs, not every gameplay path.
- Actual screenshots inspected: upright HUD, subjects present, visible player
  cues, two colonies in distributed overview. Combat is an intentionally dense,
  unnaturally orderly interleaved fixture; overlapping shield shells and markers
  dominate and obscure hardware. It is not a cinematic composition or final
  readability approval. Close view is not an isolated material inspection.
- No claim of pixel-identical moving animation or cross-driver rasterization.
  No Windows GL execution, package test or real mixed-machine LAN performed.

## 6. Evidence retention and next gates

Raw reports, three first-trial screenshots, source SHA256 manifests and summary
are archived as `star-armada-graphics-m0.zip` for delivery alongside this change.
The archive excludes user saves/settings and unrelated prototype artifacts.
The measured code/source manifest distinguishes mutable working-tree additions
from the parent SHA; tests and benchmark state hashes are retained in evidence.

Before art rollout: agree target resolution/frame budget; profile the mixed
scenes; approve actual-renderer capital/escort/station slice with better framing.
Native Windows/active-GPU measurements and sustained live LAN remain hard gates.
The approved separate stock-rule fleet workload is documented below.

## 7. Separate stock-rule fleet workloads

The owner approved keeping the original 150-combat-ships-per-player recipes as
**stress workloads** and adding separate stock-rule fleet workloads without
changing balance. Existing stress IDs and precise state contracts are retained.

New IDs: `four-player-stock-distributed-v1` and
`four-player-stock-combat-v1`. Each player has **8 corvettes, 4 frigates and
1 cruiser** (Imperial, 13 combat ships); the infrastructure/colonies/satellites/
transport quotas from section 2 are unchanged. Global initial inventory:
**52 combat ships, 40 ordinary stations, 16 trade stations, 64 transports,
8 planets and 32 satellites**, totaling **212 engine entities**.

Command use is **40 fleet +26 infrastructure =66/78 per player**, leaving 12.
Tests check use <=capacity every tick through both 300-tick scenarios. A real
construction test removes the prebuilt combat hulls and successfully queues the
entire fleet via `ConstructionSystem.start_ship` using the existing level-one
shipyards, empty research and unchanged 10,000/resource starting grant. No tech,
refit, capacity or balance override is involved. This proves fleet affordability,
queue reservations and faction/type/level eligibility at the supplied economy.

**Buildability limit:** this remains direct starting-state construction, not a
replayed organic build history. Mine/relay terrain siting, infrastructure
construction, colonization and resource gathering are not proved by the fleet
queue test. The `stock` metadata class means the fleet meets stock command and
shipyard constraints with the supplied infrastructure; it does not certify every
prebuilt station site or historical economic progression. The smaller mix is a
versioned tooling choice, not a replacement for the approved stress scale.

### Native Mac baseline

Same M4/GL/1280x800/actual 4x MSAA configuration and method as section 3:
three serial fresh-process full runs, 10 warmup +60 measured ticks. Values are
medians of the three per-trial summaries; **not interactive FPS**.

| Scene | Sim mean ms | Camera mean ms | World mean ms | HUD mean ms | Frame mean ms | LAN checksum mean ms | Frame p95 ms | Frame p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Stock distributed | 28.23 | 9.59 | 40.25 | 13.14 | 93.19 | 9.29 | 101.56 | 105.07 |
| Stock combat | 29.79 | 9.97 | 55.59 | 12.03 | 109.01 | 9.74 | 117.26 | 118.49 |

These results describe different inputs than the stress baseline, **not an
optimization gain**. The stock-rule fleet scenes also exceed the proposed (not
agreed) frame budgets. Profile their simulation, camera/world, HUD and checksum
work before funding additional rendering; no renderer or simulation optimization
is part of this change.

The 70-tick combat sample records 128 visible shots from all four owners and all
three ship classes. Both 70-tick views retain the initial transports; longer
focused tests verify actual deliveries, orbital movement and income. All three
full repetitions match their sim control's precise initial/final hashes and
final LAN checksum. Stock/stress distinction and per-sample/final command budgets
are in JSON; `units` now reports actual initial combat hull count.

Parent reran **39 focused tests** (`test_graphics_benchmark`,
`test_performance.BenchmarkContractTests`, `test_detmath`), all passed; compile
and whitespace/security checks also passed. Legacy and original stress golden
hashes are pinned. No full integration suite or native Windows GL run is claimed.

Both actual captures were inspected: upright HUD shows 66/78; distributed view
shows the local economy/colonies and only its 13 combat hulls; combat has 52
detected/projected centres in a small central block with substantial empty space.
Shield/marker overlap and rectangular fog boundaries remain visible. The existing
fixed camera deliberately remains comparable, but this is not an art close-up,
a natural battle formation or final graphics/readability approval.

Use the commands in section 4 with the new fixture IDs and distinct output names.
No `--units` for either stock ID. The separate `star-armada-graphics-stock-m0.zip`
evidence contains raw reports/captures and source/catalogue fingerprints.
Native Windows graphics, sustained LAN, frame-budget agreement and the visual
slice remain separate gates.
