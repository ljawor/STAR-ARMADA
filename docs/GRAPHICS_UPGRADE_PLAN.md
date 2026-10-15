# In-tree graphics upgrade plan

Steps to improve STAR ARMADA's graphics and its frame cost **inside this repo**,
on the existing compatibility OpenGL context (`2.1 Metal`, GLSL `1.20`). No engine
switch. This is the working plan for the graphics work; `docs/MODERN_GRAPHICS.md`
records the pass already shipped, `docs/PERFORMANCE.md` records the benchmark
work, and `docs/UNREAL_PORT.md` is the (rejected for now) engine-port study.

Every number below is measured on this project's own benchmark and capture tools,
not estimated. Where a number is a microbenchmark rather than a whole-stage
measurement, it says so.

## Scope and non-negotiables

Do:

- Raise visual quality and/or cut frame cost in the view layer only.
- Keep using the compatibility context and the existing GLSL `1.20` pipeline
  until a step below explicitly says otherwise.
- Make every change measurable against the shipped renderer, and reversible
  behind a switch until it is accepted.

Do not:

- **Touch the simulation.** The tick is 6 ms at 150 units and 25 ms at 500, and it
  must stay CPU doubles on `detmath` for per-turn checksums, replay digests and
  LAN lockstep. GPU utilisation is free in the view; in the tick it costs the
  guarantees. No engine math or engine containers on the tick path.
- **Switch engines.** Measured 2026-10-15: an engine port is 4–6 months to parity
  for this game, with determinism as the load-bearing risk and only 22 shipped
  data files (all JSON, no meshes/textures/audio) to migrate. See
  `docs/UNREAL_PORT.md`.
- **Lower MSAA to fund anything.** 4× MSAA costs 0.2–1.2 ms here; dropping it buys
  about 1%.
- **Chase fill-rate tricks.** The world pass costs the same at 1280×800 and
  2560×1440, so it is not fill-bound.
- Commit to `main`, or leave `main` dirty. One branch, one PR per step
  (`gh` CLI, account `ljawor`).

## Measured starting point

Whole-frame breakdown, `main.py --benchmark --mode full --frames 60 --warmup 10
--vsync 0 --msaa 4`, M4 iMac, macOS 26.6, pygame-ce 2.5.8:

| Scene | sim ms | world ms | hud ms | frame ms | fps |
|---|---:|---:|---:|---:|---:|
| 1280×800, 150 units | 6.35 | 30.36 | 4.77 | 43.19 | 23.2 |
| 1280×800, 500 units | 25.04 | 82.83 | 6.53 | 118.41 | 8.4 |
| 2560×1440, 150 units | 6.00 | 28.64 | 9.66 | 45.73 | 21.9 |

What that says:

- **The world pass is the cost and it scales with entity count, not pixels**:
  0.15–0.20 ms per ship, identical at 1440p. It is dominated by per-draw CPU
  overhead, which is why Step 1 is batching.
- **The HUD is the one genuinely resolution-bound cost**: 4.77 → 9.66 ms (2×) for
  3.6× the pixels. That is Step 2.
- The post-processing chain does not exist in the game yet (Step 4).

## Step 1 — Batch the hull and station draws (instancing)

**Goal.** Remove the per-draw CPU overhead from the world pass.

**Change.** Draw each (material role, hull shape) pair with one
`glDrawElementsInstanced`, instead of one display-list call per entity. Reuse
`render.fleet_materials.HULL` verbatim; replace only the vertex shader. Instance
transform + colour travel as divisor-1 attributes, uploaded once per frame.

**Already prototyped and measured.** `render/fleet_batch.py` (444 lines,
untracked) plus `render/renderer.py` (+33/−4) in the prototype tree
`~/Downloads/Project/STAR-ARMADA-TEST`:

| units | | world ms | frame ms | fps | role draws/frame |
|---|---|---:|---:|---:|---|
| 150 | off | 28.79 | 40.77 | 24.5 | ~356 per-entity |
| 150 | on | **27.13** | **39.05** | **25.6** | 2.6 instanced |
| 500 | off | 81.87 | 116.86 | 8.6 | ~1206 per-entity |
| 500 | on | **76.19** | **110.78** | **9.0** | 8.4 instanced |

World pass −5.8% / −6.9%; frame −4.2% / −5.2%. 1,206 per-entity draws collapse to
8.4. `state_sha256` is identical with the batch on and off in every run.

**Honest ceiling.** The microbenchmark's 7.9× is a per-*call* figure (36 µs/entity
per-entity list vs 1.51 ms instanced for 500 hulls) and does not transfer: the
vertex and fragment work is unchanged, so batching returns only the call overhead
it removed. Do not justify further work on the 7.9×.

**Acceptance.** World stage −10% or better at 150 units, frame −5% or better,
`state_sha256` unchanged, full suite green (see *Verification*), and the parity
step below satisfied.

**Files.** `render/fleet_batch.py` (new), `render/renderer.py` (`_batcher()`,
batch-first role loop with per-entity fallback, `batch.close` in `close()`).

**Risk.** Instanced draws are present in the shipping context via
`ARB_instanced_arrays` / `ARB_draw_instanced` / `glVertexAttribDivisor`, but must
be **runtime-detected**: a Windows compatibility context is a different driver.
Fallback is per-role back to the display lists, and the reason must be logged.

## Step 2 — Make the emissive plates stop fighting the plating (do this first, it blocks Step 1)

**Symptom.** With the batch on, the frame is no longer pixel-identical to the
shipped renderer: 0.98% of pixels in a single-frigate close-up, 0.59% at the
command centre, 0.26% in a 40-ship melee, 0.25% at a station battle, all at
1920×1200, measured with a control run (same path twice) that is **0 differing
pixels**. Role isolation: `cool` byte-identical, `base`/`dark` differ by ≤31/255
on about ten pixels, but `trim`/`lit` differ structurally — the differing pixels
are exactly the `lit` emissive colour `(255,204,133)` filling an entire plating
face.

**Cause (proven, not guessed).** The emissive plates in `render/fleet_geometry.py`
are authored **flush with the hull/trim plating** — a coincidence within 5e-5
units. Both surfaces meet a pixel ray at the same distance, so the last bit of
the interpolated depth decides the winner, and the display list and the instanced
draw round that bit differently. Ray-casting the real mesh against the real camera
(`tools/probe_plate_depth.py`) showed it; the coincident partner is `trim`.

Two consequences worth keeping in view: the same co-planarity is a **flicker risk
on another GPU** (the Windows LAN peer) even without the batch, and an inset on
the emissive side alone does **not** fix it — a 0.05-unit inset changed nothing,
because the flipping depth belongs to the plating.

**Change.** Decide the winner **in the shared geometry**, so it is a property of
the model rather than of the arithmetic: separate the surfaces by a
depth-quantum-safe margin at mesh-build time (`finish()` in
`render/fleet_geometry.py` is the single choke point for every ship and station
mesh), or make the emissive panel deliberately proud of the plating. Either way
the emitters become *intentionally* visible on every path and every GPU.

**Acceptance.** Emissive plates visible in a deliberate, named way; the frigate
parity captures either pixel-identical or differing only by the intended reveal;
`state_sha256` unchanged (this is view-only geometry); the mesh-count and
plane-count assertions in the geometry tests still pass.

**Order.** Land this **with or before** Step 1. Shipping a batch that changes which
surface wins a depth tie by accident is not acceptable, and landing the geometry
fix first means Step 1 can be verified as pixel-exact.

## Step 3 — Cache the HUD as a texture with dirty-rect upload

**Goal.** Reclaim the only cost that grows with resolution: 4.77 ms at 1280×800
and 9.66 ms at 2560×1440, on a 2× Retina drawable (a 1280×800 window is a
2560×1600 framebuffer).

**Change.** Build the HUD surface as now, but upload only the rectangles that
changed since the last frame instead of the full surface, and skip the upload
entirely on frames where nothing changed. Panel scrolls, floating texts and
selection readouts are the per-frame offenders; a static top bar is not.

**Acceptance.** HUD stage at 1440p within ~10% of its 1280×800 cost, HUD pixels
unchanged (the existing HUD diagnostic already compares real GL pixels against
the alpha composite of the pygame surface — reuse it), no regression in the
keyboard/HUD event tests.

**Risk.** Partial uploads can tear if the dirty rectangles are tracked wrong; the
fallback is a full upload whenever the tracked region set is uncertain.

## Step 4 — Post-processing as an optional presentation pass

**Goal.** Add the filmic pass (bloom, tonemap, vignette, grain) as a *switchable*
presentation step, not a replacement for anything.

**Measured cost, all on the existing GL 2.1 context** (16F attachments, MSAA
renderbuffer + blit resolve, MRT available — no core-profile migration needed):

| Path | 20 ships | 60 ships | 150 ships |
|---|---:|---:|---:|
| float 1280×800 | +1.54 ms | +2.15 ms | +2.55 ms |
| 8-bit + MSAA 1280×800 | +2.06 | +2.21 | +3.30 |
| 8-bit + MSAA 2560×1440 | +5.23 | +6.06 | +4.50 |

About **1.4 ms per megapixel**, flat in ship count — a fixed tax, not a scaling
one. It is therefore a net cost to the frame; take it as a look decision, not a
performance one. Take the float/`hdr` variant: cheaper *and* better than
8-bit + MSAA.

**Change.** Promote `tools/postfx_proto.py` into `render/`, wire it behind a
setting, default off until accepted.

**Acceptance.** Chain cost within 15% of the numbers above at the same scene,
zero clipped highlights inside the hull silhouette (measured float: frigate
5,225 → 0, station 1,893 → 586), and the look verified on the four showcase
cameras. Off by default must be pixel-identical to the current frame hash.

**Traps already paid for** (full detail in the `pygame-macos-development` skill,
`references/postfx-chain-and-fullscreen-quads.md`): run the chain in **linear
light** (decode → bloom → tonemap → encode) — blooming display values made the
glow a tight ring, 249 px of added light outside a hull versus **1905 px**
decoded; bloom goes **after** the tonemap; `gl_Position = gl_Vertex` in a
vertex shader is clip space, so a 0..1 quad covers only the top-right 25% and the
rest keeps the previous frame (this reads as a *duplicated subject*, not as a
coverage bug); and never sum per-pass `glFinish` timings (2.33 ms summed vs
1.54 ms real).

## Step 5 — Core-profile migration (GL 4.1 / GLSL 4.10), only if Steps 1–3 run out

**What it buys.** On this Mac a `GL 3.2` core context reaches `GL 4.1 Metal`:
GLSL `4.10` compiles, VAOs are core (no `APPLE_vertex_array_object`), a 64 KB
uniform block, and 2048 texture-array layers — which is what you want for
per-faction hull paint and panel variation without a texture per ship. Compute
and SSBO are still absent (that needs GL 4.3), so no GPU compute work is coming
either way.

Draw-cost reference from `tools/probe_gl_ceiling.py` (500 entities, ~600
triangles each):

| Path | ms | per entity |
|---|---:|---:|
| GL 2.1, per-entity `glCallList` | 18.00 | 36 µs |
| GL 2.1, one merged list | 2.27 | — |
| core, per-entity `glDrawArrays` | 2.36 | 5 µs |
| core, one `glDrawArraysInstanced` | 1.51 | — |

**Do not do this for frame cost.** Step 1 already captures the per-draw win in
the shipping context; the core profile's own benefit here is the texture-array
and uniform-buffer capability, i.e. richer per-hull variety, not speed. It touches
the whole view layer (~3.8k lines across `render/`) and a Windows compatibility
context is a different code path.

## Step 6 — Depth of the look, once the frame is cheap (optional, parallel)

With hulls instanced, ship count stops being the cost driver, so the same budget
buys a denser fleet and richer per-hull detail. Candidates, in rough order of
value per unit of risk:

- Per-faction hull paint and panel variation via texture arrays (needs Step 5).
- LOD or merged detail roles for distant ships (fewer triangles per hull; the
  world pass is per-entity, so this helps only after Step 1).
- Shadow maps / deferred shading / PBR: **out of scope** on this context and
  budget, and the reason `docs/UNREAL_PORT.md` exists as a study rather than a
  plan.

Keep adding to the measured tone-pass and material work recorded in
`docs/MODERN_GRAPHICS.md` (per-fragment highlights, roughness, edge lighting,
beveled hulls, planet detail; render-only cost 7.36 → 8.27 ms at 150 ships).

## Verification protocol (use this for every step)

Run from the repo root with a real window server.

```sh
# the stage breakdown, on vs off, into JSON
SA_FLEET_BATCH=0 .venv/bin/python tools/bench_fleet_batch.py \
  --units 150 --frames 60 --warmup 10 --res 1280x800 \
  --label batch-off-150 --output /tmp/b150_off.json
SA_FLEET_BATCH=1 .venv/bin/python tools/bench_fleet_batch.py \
  --units 150 --frames 60 --warmup 10 --res 1280x800 \
  --label batch-on-150  --output /tmp/b150_on.json

# pixel parity across the four showcase scenes
.venv/bin/python tools/parity_fleet_batch.py --a /tmp/sa-parity/b0 --b /tmp/sa-parity/b1 \
  --tag-a b0 --tag-b b1 --out /tmp/sa-parity/diff

# the whole suite — NOTE the driver export, see the trap below
SDL_VIDEODRIVER=cocoa PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -t tests
```

Rules that keep this honest:

- **A control run is mandatory.** Run the *same* path twice and require
  pixel-identical output before attributing any cross-run delta to a change.
- **Compare failing-test name sets, not counts** — and run the two trees
  sequentially, alone. The LAN recovery tests are real sockets with injected
  clocks; a concurrent benchmark was enough to flip one.
- Compare `state_sha256` every time. If it moved, the change reached the
  simulation and the change is wrong.
- Report "pixel-identical" and "visually identical" as the different claims they
  are, with the number: 0.98% of pixels on a close-up is visible, 0.26% in a melee
  is not.

## Traps that will cost you a day if you rediscover them

- **The full suite silently disables GL testing.** `tests/test_weapon_sfx.py` does
  `os.environ.setdefault("SDL_VIDEODRIVER", "dummy")` at import time, and
  `unittest discover` imports every module before running any test. The whole
  process then runs on the dummy driver: 14 `test_renderer_constructor_cleanup`
  errors, 2 lan errors, and the audio exit probe failing on an inherited
  `SDL_AUDIODRIVER=dummy`. Since it is `setdefault`, exporting
  `SDL_VIDEODRIVER=cocoa` before the run defeats it — no test edit needed. Without
  the export, a green full-suite run says **nothing** about renderer lifetime code.
  Steps to fix properly: set the dummy driver for those modules' subprocesses only,
  or set/restore it in `setUpModule`/`tearDownModule`.
- **Depth readback is dead on this driver.** `glReadPixels(GL_DEPTH_COMPONENT)`
  returns 1.0 everywhere — with and without MSAA, and from an FBO we own with an
  explicit depth renderbuffer — while `GL_DEPTH_BITS` still reports 32. Decide
  depth questions from colour plus a geometric ray-cast, never from depth.
- **Compare parity per role and per pass.** Install the isolation monkeypatch for
  **both** shots, or unhandled roles fall back to the display list and the two
  pictures are not the same role set. Run both sides with the same skip set.
- **A probe can print a second, unrelated result after your case.** A grep for the
  wrong words matched only a later generic block and reported "identical" for
  three roles that plainly differed. Grep the case's own header line.
- Everything else already learned lives with the tools: the
  `pygame-macos-development` skill (`references/opengl-render-debugging.md`,
  `references/gl-pixel-probe-authoring.md`, `references/metal-depth-readback.md`,
  `scripts/probe_gl_ceiling.py`) and the `star-armada` skill
  (`references/view-batching-and-parity.md`, `references/running-the-suite.md`).

## Where the prototype is

- Prototype tree (**the tree with the batch changes; uncommitted**):
  `~/Downloads/Project/STAR-ARMADA-TEST`. Only `render/renderer.py` differs from
  `main` as a tracked file, plus the untracked `render/fleet_batch.py`.
  Run it with `.venv/bin/python main.py` — the batch is on by default,
  `SA_FLEET_BATCH=0` gives the old path — or
  `SA_FLEET_BATCH_ROLES=base,dark,…` to isolate one role.
- Measurements and images: `STAR-ARMADA-TEST/artifacts/fleet_batch/` (README,
  six benchmark JSONs, `look_frigate.png`, `look_melee.png`),
  `STAR-ARMADA-TEST/artifacts/showcase/` (post-FX before/after sets),
  `STAR-ARMADA-TEST/artifacts/postfx/` (chain metrics).
- Tools: `tools/probe_gl_ceiling.py`, `tools/bench_fleet_batch.py`,
  `tools/parity_fleet_batch.py`, `tools/parity_fleet_inline.py`,
  `tools/probe_plate_depth.py`, `tools/probe_depth_buffer.py`,
  `tools/probe_depth_fbo.py`, `tools/capture_showcase.py`,
  `tools/capture_fight.py`.
- The prototype is deliberately a copy: it must not be disturbed while the
  production tree stays clean.
