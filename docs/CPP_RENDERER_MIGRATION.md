# STAR ARMADA — C++ renderer, Python simulation: migration plan

Status: **W00 merged into `main` and approved; W01 viewer complete, owner-reviewed, landing.**
Proposal base: `main` @ `bd22879` (2026-10-20). Implementation base: `b2ff85a`.
The owner authorized W00 + W01 on 2026-10-21 and approved the offline v1 format; merge, release and
default activation remain separate decisions.
Proposal base: `main` @ `bd22879` (2026-10-20). Implementation base: `b2ff85a`.
The owner authorized W00 + W01 on 2026-10-21; merge, release and default activation remain separate.

Execution correction: W00 v1 freezes only an **offline JSON file profile**, not W02 live SoA/shared memory.
See `docs/RENDER_PROTOCOL.md`; W01 is mesh-only and cannot establish full-game FPS or world parity.
Authority: this document proposes a renderer migration. It authorizes no merge to a
default, no release, no tag and no change to gameplay, assets or simulation.

This plan replaces the "one year, one codebase" engine rewrite with the cheapest route that
fixes the measured bottleneck: **keep the Python simulation, LAN stack, tools, tests and
approved asset catalogue exactly where they are, and replace only the drawing.**

## 1. Purpose, authority and the five owner constraints

### 1.1 What this is

The renderer becomes a separate native program that receives a snapshot of the world and a
2D draw list from the running Python game, and draws it with a modern GPU pipeline
(SDL3 + bgfx: Metal on macOS, Direct3D 12 on Windows). The simulation, commands, checksums,
saves, replays, LAN session handling, menus logic, HUD layout and localization stay in
Python, untouched.

### 1.2 The five owner constraints, each bound to a mechanism

These are the lessons from the Blender catalogue roadmap, written as executable policy
rather than good intentions. Each one names the section that enforces it.

| # | Constraint (owner's words, condensed) | Mechanism in this plan | Enforced by |
|---|---|---|---|
| 1 | Too much testing | Per-workstream test budget: at most 3 tests, one capture. Full suite twice in the whole plan. | §8 |
| 2 | Must see progress in the game; can move and rotate | W01 is a runnable window on your real fleet at ~2 weeks; every workstream ends with a command you launch and a picture | §6, §9 |
| 3 | Steps split into branches, clear what is merged | One workstream = one branch = one PR. A merge table states exactly what lands in `trunk` at each step, and `main` stays playable and legacy-default throughout | §7.1, §7.2 |
| 4 | Split work so context windows stay short | Workstream sizing rules, owned-file lists, read-lists, and hard stop triggers | §7.3 |
| 5 | Every workstream ends with a progress + handover update | Handover record + ledger row in the same PR, or the PR is not mergeable | §9, §10 |

### 1.3 Decision rights

| Decision | Who | When |
|---|---|---|
| Continue past W02 (live link) | owner, on a picture and a number | after W02 |
| Continue past W05 (in-game switch behind a flag) | owner, on a playable build | after W05 |
| Make the C++ renderer the default | owner, explicit, one line | W07 only |
| Delete the legacy renderer | owner, separate later decision | after W07 + one release |
| Any performance target used as an acceptance gate | owner | before W06 |
| Gameplay, balance, asset, approval-record changes | **out of scope entirely** | — |

## 2. Measured baseline this plan rests on

Read from `docs/PERFORMANCE.md` (24-trial macOS comparison, 72-trial Windows session) and
the 500-ship fixture. These are synchronized measurements (`glFinish` per stage), so they are
an upper bound on real gameplay cost, not a frame-rate claim.

| Stage, 500 corvettes | macOS M4 | Windows i9 + RTX 5060 (dGPU selected) |
|---|---:|---:|
| simulation (`GameManager.step`) | 25.736 ms | 34.263 ms |
| world draw | 90.824 ms | 170.818 ms |
| HUD (surface compose + upload + GL) | 6.399 ms | 17.025 ms |
| swap | 0.2 ms | 0.6 ms |
| synchronized frame | 125.711 ms | 235.512 ms |

Simulation scales at ≈N^1.42 (mac) / ≈N^1.41 (win) between the measured 200- and 500-ship
points, so at the 4-player fleet of 600 combat ships it costs **≈33 ms (mac) / ≈44 ms (win)**
before anything is drawn.

Projection for this plan (renderer estimate is ±40 %, the simulation figure is measured):
world stage drops from 90.8 → **5–9 ms** (mac) and 170.8 → **8–13 ms** (win); the frame lands
at **38–42 ms (24–26 fps)** and **52–57 ms (17–19 fps)** at 600 ships, versus 8–11 fps and
5–6 fps today. 60 fps steady is reached at **≈230–370 ships (mac)** and **≈160–300 (win)**.

**Therefore:** this migration removes the renderer from the critical path and buys a 3–4×
frame-time improvement plus modern materials, shadows and lighting. It does **not** reach
60 fps at 600 ships on its own: after W05 the simulation is the bottleneck. Accelerating the
simulation (numpy/typed arrays or a compiled extension, 150–250 h) is deliberately **outside
this plan** and is listed as future workstream W08 in §10 so it is not lost.

## 3. Architecture

### 3.1 Process model

```
┌─────────────────────────────┐        snapshot (world)        ┌──────────────────────────┐
│  Python game process        │ ───── 30–60 Hz, shm ring ─────▶ │  armada_render (C++)     │
│  simulation, LAN, menus,    │                                 │  SDL3 window + bgfx      │
│  HUD layout, input mapping  │ ◀──── input events, 1 kHz ───── │  Metal / D3D12           │
│  (authoritative, unchanged) │                                 │  no game state, ever     │
└─────────────────────────────┘        draw list (2D UI)       └──────────────────────────┘
```

- The renderer is a **subprocess**, not an embedded module: the GIL is never shared, a
  renderer crash cannot corrupt a match, and the two halves keep independent crash handling.
  Revision to embedding (pybind11) only if W02 measures pipe latency above budget.
- Python writes into a **double-buffered shared-memory ring** (8 frames). If the renderer
  stalls, Python overwrites the oldest slot and continues; a slow renderer costs dropped
  frames, never a stalled simulation.
- The renderer **never writes** simulation state. Its only outbound data is an input event
  queue, which Python feeds into the existing `render/input.py` mapping — so menu navigation
  and command issuance keep their current code and their current tests.
- The camera lives in the renderer and is mirrored back to Python once per second so that
  fog-of-war and picking queries (which read camera state today) keep working. During W01–W02
  this mirror is unused; from W04 it is authoritative in the renderer and published to Python.

### 3.2 What the renderer owns, and what it must never own

| Owns | Never owns |
|---|---|
| GPU device, swapchain, shaders, mesh upload, instance buffers | entity state, commands, RNG, tick order |
| camera transform, culling, LOD selection, shadow pass | damage, visibility, fog *decisions* (it draws the fog raster Python computes) |
| 2D draw-list execution (quads, glyphs, clips) | menu layout, HUD composition, text, localization |
| input *capture* (key/mouse events, focus, DPI) | input *mapping* to menu actions or player commands |

This split is what keeps the migration at ~500–900 h instead of 650–1,120 h: the 5,643 LOC
of hand-written UI in `render/menus.py`, `render/hud.py`, `render/classic_screens.py`,
`render/input.py` and `render/i18n.py` is **not ported** — it already produces an
immediate-mode draw list, so Python keeps deciding layout and emits quads and glyph runs
instead of GL calls.

### 3.3 Asset handling — no re-export, no re-approval

The 103 approved runtime meshes in `assets/models/*.json` are already flat triangle lists
with per-face material roles (`batches`, `[nx,ny,nz,i0,i1,i2]` rows, JSON). The C++ asset
loader reads **those same files**. Consequences, which are the main reason this plan is
cheap:

- No Blender re-export, no GLB/FBX conversion, no `pipeline.json` / `approvals.json` /
  contract-example churn, no new owner appearance approvals.
- Material roles (`hull`, `paint`, `glow`, …) come from the same payload, so the C++ shader
  path consumes `render/fleet_materials.py`'s role vocabulary rather than inventing one.
- The approved-envelope and hash records stay valid because the bytes never move.

## 4. Protocols

Two streams, both versioned, both with a magic word and a CRC so a mismatched pair fails
loudly instead of drawing garbage.

### 4.1 World snapshot (Python → C++)

Per frame: `magic, version, tick, frame_index, byte_length, crc32`, then

- camera: eye, target, up, fov, near/far, viewport, MSAA sample count
- lights: directional (direction, colour, intensity), ambient, two point lights for effects
- fog: 8-bit raster (`render/fog.py` already computes it) + world rect
- instances: SoA arrays — `entity_id, binding_id, matrix3x4, tint_rgba, flags (LOD tier, selected,
  damaged, opacity), hp_frac, shield_frac, effect_state`
- projectiles and transient effects: `position, velocity, kind, life, size, colour`
- environment: planets (centre, radius, rotation, surface texture id), satellites, orbit rings,
  nebula sprites, background panorama id
- `state_sha256` of the tick this snapshot describes — so any screenshot can be tied to a
  simulation state

Budget: ≤ 1.0 ms to serialize 600 entities + 2,000 effects on the Python side, measured by
W02's own receipt. If exceeded, the fix is preallocated arrays and struct packing, not a
redesign — but the number is a gate, not a hope.

### 4.2 2D draw list (Python → C++, unchanged layout logic)

The existing HUD/menu code already emits draw commands. In this plan it emits them into a
list instead of calling GL: `quad(x,y,w,h, uv_rect, rgba, texture_id, clip_rect, layer)` and
`glyph_run(font_id, size, x, y, glyph_ids[], advances[], rgba, clip_rect, layer)`.
The C++ side executes the list in order against a font atlas built from the same TTF files,
so text stays pixel-comparable and localization keeps working through the existing
`render/i18n.py` catalogue and language packs (including the CJK/Cyrillic glyph coverage the
language tests already pin).

### 4.3 Transport and failure behaviour

| Case | Behaviour |
|---|---|
| magic/version mismatch | renderer exits `3`; Python logs `E_RENDERER_PROTOCOL` and continues **headless-legacy** for that launch |
| renderer crash (segfault, device loss) | Python notices the pipe close, falls back to the legacy renderer for the rest of the session, writes a diagnostic; a match in progress is not lost |
| renderer slower than budget | ring buffer drops oldest slots; Python never blocks; a counter is exposed in the overlay |
| device loss / TDR (Windows) | renderer re-initialises bgfx once, then exits `4`; same fallback path |

## 5. Invariants — what must not move

1. **Determinism.** `state_sha256` and `initial_state_sha256` are identical with the C++
   renderer on and off, for the same inputs. The renderer is read-only; this is structurally
   true (§3.2) and is asserted anyway by one test (§8.2) and one receipt per workstream.
2. **Assets.** No file under `assets/models/` changes. Registry, pipeline, contract examples
   and approval records are untouched by every workstream in this plan.
3. **Simulation, balance, saves, replays, LAN.** No behaviour change; the renderer is local
   and is never part of lockstep or checksum exchange.
4. **Legacy renderer stays.** It is the fallback, the rollback and the A/B control until an
   explicit later decision removes it.
5. **Language packs.** Text is still produced by `render/i18n.py`; no new string catalogue is
   introduced. The glyph atlas must cover every language pack's repertoire (checked in W03).

## 6. Workstreams and dependency gates

One workstream = one branch = one PR = **one chat session**. Hours are engineering estimates
(±40 %), not commitments.

| W | Workstream | Hours | Depends on | Branch | Gate |
|---|---|---:|---|---|---|
| W00 | Protocol spec, wire format fixtures, decision record | 6–10 | this plan | `docs/cpp-renderer-w00-spec` | spec reviewed; no code |
| W01 | **Offline viewer**: snapshot dump + bgfx window, orbit/pan/zoom on the real fleet | 30–50 | W00 | `render/cpp-w01-viewer` | **owner looks at a picture and flies the camera** |
| W02 | **Live link**: running match streams into the viewer at 30 Hz; latency + fps receipt | 40–70 | W01 | `render/cpp-w02-bridge` | 1 ms serialization budget met; owner sees live battle |
| W03 | HUD transport, design A (carry the composed surface; text stays SDL_ttf). **Landed**: slice 1 dirty-rect upload in the legacy HUD (`hud.render()` 2.193 → 1.407 ms median, 1,024,000 → 55,016 pixels/frame, GPU-readback identical); slice 2 `ARMOVL01` overlay ring, keyframes, native decode + fullscreen unblended/alpha-blended pass, presented-pixel parity **800/800 rows, 0 differing pixels** (`docs/RENDER_DRAW_LIST_W03.md`, `artifacts/cpp-renderer/w03/`). Menus are still Python-only and paint through the same surface if they are sent | — | W01 | `render/cpp-w03-drawlist` | presented-pixel parity; language packs unaffected because the raster stays SDL_ttf |
| W04 | Input return path: events from C++ into the existing mapper. **Implemented** (slice 1): `ARMINP01` batch codec + native ring writer, `--input-ring` capture in the window, `RingInput` feeding the production `InputController`, `stream_ring --input-ring` and `live.command` wired. Encoders byte-identical on a shared fixture (14 events, 244 B), 10 bridge tests against a live `GameManager` skirmish, native ring replayed through the real controller, live run delivered 7 of 9 scripted events with 0 skipped. Authority stays with the Python command validators; menus not yet bridged (`docs/RENDER_DRAW_LIST_W04.md`, `artifacts/cpp-renderer/w04/`) | 30–50 | W03 | `render/cpp-w04-input` | click/keys drive real commands; menu path still to exercise |
| W05 | World parity: stations, planets, satellites, orbits, fog, markers, effects, LOD; `--renderer cpp` flag | 150–260 | W02, W03, W04 | `render/cpp-w05-parity` | **owner plays a skirmish in the new window**; determinism test green. Slice 1 (planets) landed: textures carried once per planet, native sphere shading ported from `fleet_materials.py::PLANET`, same-fixture reference frame; slices 2–6 open |
| W06 | Packaging: mac `.app` + notarize, windows `.exe`, both binaries in `star_armada.spec`/CI | 80–140 | W05 | `render/cpp-w06-package` | frozen packages launch and play on both platforms |
| W07 | Polish, measured improvement receipt, default switch (**owner gate**) | 60–110 | W06 | `render/cpp-w07-default` | owner authorizes the switch in one line |

**Timeline at ~25 h/week:** W01 (visible, camera-driven viewer) **≈ 1.5–2 weeks**; playable game
in the new window (W05) **≈ 3–4 months**; parity + packaging + switch (W07) **≈ 6–9 months**.
Total **516–850 h**. Compare: Unity rewrite 2,280–4,000 h, Godot 2,520–4,430 h, C++ full
rewrite 2,790–4,790 h.

### 6.1 Per-workstream definitions

Each lists: goal, owned files, the command that must work, and what the owner checks.

#### W00 — Protocol spec and wire fixtures

- Write `docs/RENDER_PROTOCOL.md`: both stream layouts, endianness, alignment, versioning,
  failure codes, budget. Freeze it as a policy decision in `art/manifests/pipeline_policy.json`
  with id `render-protocol-v1`.
- Commit three binary fixtures (600-entity world, HUD-heavy draw list, empty frame) under
  `tests/fixtures/render_protocol/` plus a checksum file — these are the round-trip control for
  W02 onward.
- Owned: `docs/RENDER_PROTOCOL.md`, `art/manifests/pipeline_policy.json` (append only),
  `tests/fixtures/render_protocol/*`.
- Owner checks: nothing visual. This step's review is *negative*: no game, render or asset
  file changed.

#### W01 — Offline viewer (the first thing you can look at and fly)

- `tools/render/dump_snapshot.py` — builds a 600-ship world with the existing benchmark
  fixture, writes one snapshot file. Reuses `--benchmark`'s scene construction; does not run
  the game loop.
- `render_cpp/` — CMake + SDL3 3.4.x + bgfx (pinned commit, Metal on mac / D3D12 on win),
  JSON mesh loader for `assets/models/*.json`, PBR-ish hull shader, one directional light,
  one shadow cascade, instanced draw of the whole fleet, simple HUD text overlay
  (fps, ships, draw calls).
- Command: `python3 tools/render/dump_snapshot.py --units 600 --out render_cpp/build/fleet.snap` then
  `render_cpp/build/armada_viewer --snapshot render_cpp/build/fleet.snap --assets assets`.
  macOS shortcut: `open render_cpp/launch.command`; build prerequisites are in `render_cpp/README.md`.
- Controls: drag to orbit, wheel to zoom, WASD to pan, `1`–`3` for camera presets,
  Shift+S to save a PNG, `f` to toggle fps overlay.
- Owner checks: the picture (does the fleet read better than the legacy renderer?) and the
  camera feel. **This is the "see progress, move and rotate" gate.**

Historical core-only W01 execution receipt (2026-10-21, PR **#146**, code `7bf11d2204b3aca6c82e58943ab71f26613ea5d2`):
source-built Metal viewer/launcher runs; 638 detected mesh instances include 600 combat ships;
103-mesh catalogue GPU upload/submission closure passes. At 1280×800, 240 measured offline
mesh-only frames: wall median **8.736083 ms**, GPU median **3.893125 ms**. These are not full-game
FPS or a matched-quality speedup. Native shading remains basic; no visual improvement is claimed.
Natural camera/appearance review and native Windows remain open. Source/test size exceeded the
proposal's sizing rules; no exception approval is inferred. See
`art/manifests/handoffs/rW01-offline-native-viewer.md` and `artifacts/cpp-renderer/w01/acceptance.json`.
The source code is published; the owner gate, merge/release/default activation and W02 are not.

Owner-caught model-selection correction: the initial exporter omitted the shipped
Imperial visual packs. Code `2bf5ed5f78908a0e6e68dc01f0a55cdfa4f6c208` uses all 13
actual default packs, including current Vigil and Command Center, and accepts their
versioned mesh contract. Corrected Metal captures/103-mesh closure and 6 Python +
2 native target checks pass; old core-only timings/pictures above are historical.
Corrective handoff: `art/manifests/handoffs/rW01-current-default-models.md`.
No new artwork, default activation or W02 work is authorized by this correction.

#### W02 — Live link

- Python: `render_bridge/` (writer thread, ring buffer, lifecycle, fallback), `--renderer cpp`
  accepted but **not default**; the legacy renderer stays the default.
- C++: ring-buffer reader, frame interpolation, camera mirror out.
- Command: `python3 main.py --skirmish --renderer cpp --observer` (a second window shows the
  live match).
- Receipt: serialization ms, end-to-end latency, dropped-frame count, fps at 200/400/600 ships.
- Owner checks: the live battle looks right and the camera responds; the numbers.
- Gate: if serialization > 1.0 ms or latency > 2 frames, stop and fix before W03.

#### W03 — Draw-list executor

- Python: replace `gl*` calls in `render/hud.py`, `render/menus.py`, `render/classic_screens.py`
  with draw-list emission (a shim, one call site per primitive). Layout code unchanged.
- C++: quad batcher, SDF or bitmap atlas from the same TTFs, clip rects, layer ordering.
- Command: same as W02, now with the real HUD and menus drawn by the renderer.
- Owner checks: side-by-side captures legacy vs C++ for main menu, skirmish setup, settings
  (all pages), library, replay browser, HUD with a mixed selection and a long refit effect.
- Gate: every visible string present; all four language packs render non-tofu (§8.2 test 4).

#### W04 — Input return path

- C++: key/mouse/scroll/focus events into the queue with timestamps and DPI scale.
- Python: `render/input.py` consumes them via one adapter; mapping code unchanged.
- Owner checks: click through setup, issue an order, open settings, Escape behaviour,
  alt-tab and window resize.

#### W05 — World parity behind a flag

- Port the remaining draw paths: stations (both entry points), planets and satellites, orbit
  rings, nebula/background, markers, hit effects, shields, jump points, collection rings, fog,
  selection rings, LOD tiers, damage/ownership cues.
- Command: `python3 main.py --renderer cpp` for a full match, menus included.
- Owner checks: **plays a skirmish** in the new window, compares against legacy, judges both
  the look and the feel.
- Machine gate: determinism test green (`--renderer cpp` vs legacy, same seed/replay, identical
  `state_sha256`); no asset, registry or approval file in the diff.

#### W06 — Packaging

- mac: `.app` bundle containing both binaries, hardened runtime, notarization, `hdiutil verify`.
- win: `.exe` + renderer DLL/exe, signed or explicitly waived (owner decision).
- Update `star_armada.spec` and CI; frozen smoke on both platforms.
- Owner checks: install and launch from the package, not the repo.

#### W07 — Polish, receipt, switch

- VFX/material polish funded by W06's headroom; a measured before/after receipt at 200/400/600
  ships on both machines.
- The default switch is a one-line change **and an owner decision**, recorded in
  `pipeline_policy.json` with the owner's words and the reviewed revision.
- Legacy stays shipped and selectable for at least one release.

## 7. Branch, merge and context protocol

### 7.1 One workstream, one branch, one PR

- Branch name: `render/cpp-w<NN>-<slug>` (docs steps use `docs/…`).
- PR title: `feat(render): W<NN> <what lands>`.
- Merge: `gh pr merge <n> --squash --delete-branch --match-head-commit <full-40-sha>` after the
  WP's gate is met. Never merge a head that moved after review.
- Never `git add -A` in this repo (unfrozen runs write `saves/`, `replays/`, `diagnostics/`
  into the tree). Stage explicit paths only.

### 7.2 What actually lands in `main`, workstream by workstream

| After | `main` gains | `main` does **not** gain |
|---|---|---|
| W00 | the protocol document + fixtures + decision id | any binary, any render change |
| W01 | `render_cpp/` sources, CMake, `tools/render/dump_snapshot.py`, receipts | anything the game loads — the viewer is a tool |
| W02 | bridge module, `--renderer cpp --observer` flag **off by default** | no change to normal launch |
| W03 | draw-list shim in the three UI modules, behind the flag | legacy path untouched when flag is off |
| W04 | input adapter, behind the flag | default input path unchanged |
| W05 | full world parity behind `--renderer cpp` | **default is still legacy** |
| W06 | packaging scripts, both binaries in the package | no default change |
| W07 | default = `cpp`, legacy selectable | no legacy deletion, no tag, no release (separate) |

`main` is runnable and legacy-default at every merge point. No workstream may merge while
the previous one is red on its own gate.

### 7.3 Context budget — how each workstream stays small

Rule: **one workstream fits one chat session**, which means:

- ≤ 4 owned files (or ≤ 2 files + one new directory), ≤ ~800 changed lines.
- Each workstream's brief names the **read-list** (documents and files only) so an agent never
  has to discover the tree: e.g. W03 reads `docs/RENDER_PROTOCOL.md` §4.2, `render/hud.py`
  (draw calls only — grep for `gl`, do not read the 1,693 lines), `render/clean_classic.py`,
  the W02 handover. **No workstream requires reading `render/renderer.py` in full** (4,021
  lines); the world-parity work in W05 is split by *draw path*, one path per sub-branch.
- W05 is the one heavy workstream; it is split into three sub-branches (W05a stations +
  planet hardware, W05b ships/markers/effects, W05c fog/orbits/background), each with its own
  PR and its own capture, so no single session owns the whole parity surface.
- Hard stop triggers — stop, write the handover as `blocked`, and hand back:
  - the same defect survives two fix attempts;
  - the session needs more than ~4 files' worth of new context;
  - a gate needs a number you cannot measure in this session;
  - any change would touch `game/`, `assets/` or approval records (out of scope by §1.3).
- No concurrent heavy jobs: one GL capture, one suite run or one renderer build at a time.
  Two agents must never own `render_cpp/CMakeLists.txt` or the protocol structs simultaneously.

## 8. Testing budget and evidence policy

The previous roadmap's cost was dominated by acceptance machinery: a 210-module, 2,281-test
sweep per milestone, per-module sharding, sabotage matrices per PR. This plan budgets tests
explicitly and spends them where a defect would be expensive.

### 8.1 Budget per workstream

| Item | Limit |
|---|---|
| New automated tests | **≤ 3**, one of which must be behavioural (drives the real code path) |
| Capture receipts | 1 PNG + 1 small JSON per workstream, in `artifacts/cpp-renderer/w<NN>/` |
| Full-suite runs | **twice in the entire plan**: at W05 (parity) and W07 (acceptance) |
| Contract/registry validators | once, at W05, to prove no asset byte moved |
| Runtime of a workstream's own checks | ≤ 5 min |

### 8.2 The five tests that must exist (and no others without a new justification)

1. **Protocol round-trip** (`tests/test_render_protocol.py`): encode → decode a 600-entity
   snapshot and a 500-command draw list; assert byte-identical re-encode, CRC rejection of a
   flipped byte, and exit code `3` on a version bump. Written in W00/W02.
2. **Determinism with the renderer on** (`tests/test_renderer_determinism.py`): run the same
   seed/replay twice, once with the bridge writing snapshots and once headless; assert
   identical `state_sha256` per tick. Written in W05.
3. **Asset load parity** (`tests/test_render_assets.py`): every one of the 103 approved meshes
   loads in the C++ loader; triangle and vertex counts match the JSON payload. Written in W01.
4. **Glyph coverage** (`tests/test_render_glyphs.py`): for each of the four language packs,
   every character used by the menus is present in the atlas with distinct bitmaps. Written
   in W03 — this is the successor to the existing tofu test, not a duplicate of it.
5. **Capture assertions are not tests**: a capture is a receipt with a JSON of measured values
   (frame ms, changed pixels, subject-in-frame) that the owner looks at.

### 8.3 What is explicitly forbidden here

- Running the full suite per PR "to be safe". Two runs, at the two gates, on a machine with
  nothing else running.
- Building a second test harness for the renderer beyond the round-trip fixture.
- Sabotage matrices, per-module sharding, or re-deriving the existing 2,278-test verdict per
  workstream.
- Treating a green CI as render acceptance. CI covers the Python side; the renderer's
  acceptance is a picture plus a measured number.

## 9. Handover protocol

Every workstream ends with **two** artifacts in its own PR, or the PR cannot merge:

1. `art/manifests/handoffs/r<W>-<slug>.md`, from this template;
2. a ledger row update in §10 of this document (status, date, PR, head sha, one-line verdict).

```markdown
# Handoff: W<NN> <slug>
Status: not-started | in-progress | blocked | review-ready | complete
Base commit / branch / exact pushed head (40 chars):
PR number:
Prerequisites verified (previous gate's receipt path):
Owned files (and files touched outside the list, with reason):
Protocol version / bgfx commit / SDL3 version / toolchain:
What changed visibly (and the command that shows it):
Measured numbers (stage ms at 200/400/600, latency, dropped frames, draw calls):
Determinism check (state_sha256 comparison, or why it does not apply yet):
Tests added (names + counts) and commands actually run:
Captures: repository-relative paths in artifacts/cpp-renderer/w<NN>/
Owner decision required (or "none"):
Known gaps / things this workstream did NOT prove:
Next executable step and its gate:
```

Rules that make the handover useful rather than decorative:

- The handover is written **from a fresh read of the tree** (`git rev-parse HEAD`, branch,
  `git status --short`, `shasum` of the files it names) — never from the previous summary.
- If the session stops mid-work, the handover says `in-progress` or `blocked`, names the exact
  unfinished item and leaves the branch pushed. A half-built workstream is never presented as
  a result.
- Numbers in the handover are pasted from the receipt files, not retyped from memory.

## 10. Progress ledger and next task

| W | Status | Next action / blocking condition |
|---|---|---|
| W00 | **Merged into `main` and approved** | 2026-10-21, PR #145, code `f5844a8` → `4283715`, squashed to `main` as `3dc9279`. Offline protocol/reference codec + three controls; 3 focused tests pass. Owner approved v1 as the offline file profile (`render-protocol-v1-owner-approval-2026-10-21`). W02's live transport is defined separately in `docs/RENDER_BRIDGE_W02.md` (v2 packed profile, not the offline envelope). See `art/manifests/handoffs/rW00-offline-protocol.md`. |
| W01 | **Owner-reviewed; lands with this PR** | 2026-10-21, PR #146, renderer code `fdf1b2a`: all 13 shipped visual packs resolved; newer Vigil/Command Center and 103 selected meshes render on Metal. Owner accepted the appearance and the camera movement/zoom ("Looks good for me. The movement and zomming work really fast."). Old core-only evidence is historical. Handoff `rW01-current-default-models.md`. |
| W02 | **In progress: producer, decode and live draw path measured** | 2026-10-21, branch `render/cpp-w02-bridge`, PR open. v2 packed frame + mmap ring + read-only gather; `render_cpp/include/frame_v2.hpp` decodes committed Python-authored frames and refuses every corrupted variant; `armada_viewer --ring` draws ring frames with angle-and-scale interpolation (`tools/render/stream_ring.py` produces them from a stepping `GameManager`). End-to-end (`artifacts/cpp-renderer/w02/live/live-receipt.json`): a player-visible frame (638 of 752 hulls) decodes in 0.716 ms median with **frames behind at draw ≤ 1 (gate ≤ 2 met)**, 0 dropped of 54 adopted, 1434 frames drawn; 27 Python tests + `ctest` 3/3. Producer cost on a combat frame is **0.964 ms median** (736 instances + 1,426 transients) after replacing the transient generator with a direct pack loop — 2.6x faster than the 2.6 ms it measured, and inside the 1.0 ms budget. Two limits stated plainly: the stream runs at 3.0 Hz because a 752-hull Python tick costs 179 ms, not because of the bridge; and computing player visibility costs 105 ms/frame in the legacy predicates, which the C++ path must not inherit. Still open: equal-workload fps (fog, HUD, planets), player-visibility filtering in the live path, Windows, and the owner's live-battle check. |
| W03 | **Landed**: design A — dirty-rect upload in the legacy HUD, `ARMOVL01` overlay ring with keyframes, native decoder + UI pass, presented-pixel parity 0 differing pixels | Depends on W01; W02 landed (`463d431`) |
| W04 | In progress: input return path | Depends on W03 |
| W05 | Not started | a/b/c sub-branches; owner plays a skirmish here |
| W06 | Not started | Depends on W05 + owner's packaging decision on Windows signing |
| W07 | Not started, **not authorized** | Owner's explicit one-line switch, after W06 and its receipt |
| W08 (future, out of scope) | Not planned | Simulation acceleration (150–250 h) — the only route to 60 fps at 600 ships |

**Current next gate: the W02 consumer and its latency receipt.** The serialization half is measured
(`docs/RENDER_BRIDGE_W02.md` §4): 0.712 ms worst case against the ≤ 1.0 ms gate, on the condition
that the writer is handed the renderer's visibility set. What is *not* proven is everything the
gate actually names — the C++ consumer decoding and interpolating these frames, end-to-end latency
≤ 2 frames, dropped-frame counts, and fps at 200/400/600 ships on an **equal-workload** scene (fog,
HUD, planets). No speed claim may be made from the mesh-only loop or from a producer-only
number. The `Windows signal` workflow is disabled by the owner's hand as of 2026-10-21, so W02's
evidence has to be local until it is re-enabled.

## 11. Risk register

| Risk | Likelihood | Mitigation | Detected by |
|---|---|---|---|
| Serialization eats the win | medium | Budget 1.0 ms/frame; preallocated SoA buffers; W02 gate stops before UI work | W02 receipt |
| Two-runtime packaging breaks one platform | medium | W06 is its own workstream; frozen smoke test; legacy path always present | W06 gate |
| Font/glyph mismatch vs legacy UI | medium | Same TTFs, same advance widths fed from Python; per-pack glyph test | test 4, W03 captures |
| Subprocess feel: input lag, focus, resize | medium | W04 dedicated to it; events timestamped; camera in renderer | W04 owner play |
| Draw-list ordering bugs (HUD under world, clipping) | high | Layer + clip rect are protocol fields, not renderer guesswork; side-by-side captures per screen | W03 owner review |
| Silent divergence in world parity (a path never ported) | high | Parity checklist per draw path in W05a/b/c; a "missing binding" debug overlay that paints unported entities magenta | W05 captures |
| bgfx/device loss on Windows laptop | medium | One re-init, then exit `4` and fall back | W02/W06 smoke |
| Determinism drift sneaking in | low | Renderer cannot write state; camera mirror is one-way; test 2 | test 2 |
| Scope creep into UI port or sim rewrite | high | §3.2 ownership table; stop triggers in §7.3 | handover review |
| Renderer work displaces the art/performance stream | medium | This plan is opt-in and flag-gated; `main` stays legacy-default until W07 | ledger |

## 12. Open owner decisions (do not answer these yourself)

1. **Performance reference.** Is the acceptance target "60 fps at 600 ships" (which requires
   W08 simulation work) or "the best frame time this renderer can produce at 600 ships",
   measured against 8.8 fps today? The plan measures both, and does not pick.
2. **HUD fidelity bar.** Must the new HUD be pixel-comparable to Clean Classic, or is
   "same layout, same strings, same hitboxes, small rendering differences" acceptable?
3. **Windows packaging.** Signing, notarization-equivalent and native Windows graphics evidence
   were waived once (`s09-platform-waiver-2026-10-19`). Is the waiver renewed for W06, or does
   this plan own a Windows machine's evidence?
4. **Legacy lifetime.** Keep the legacy renderer selectable for one release, or until the next
   engine version? (Recommendation: one release, then a separate deletion decision.)
5. **W07 timing.** The switch is the owner's one-line gate; the plan does not schedule it.

## 13. What this plan does not claim

- **Not** 60 fps at the 4-player fleet. Measured projection is 24–26 fps (mac) and 17–19 fps
  (win) at 600 ships; 60 fps is reached near 230–370 / 160–300 ships. The remainder is
  simulation cost (W08, out of scope).
- **Not** an engine switch. No Unity, Godot or Unreal, no scene graph, no editor, no C# or
  GDScript rewrite, no simulation port.
- **Not** an art change. Every approved mesh, hash, envelope and approval record stays byte-
  identical; the visual difference comes from lighting, shading and post, not new geometry.
- **Not** a packaging, Windows-native or release claim until W06 runs.
- **Not** proven on Filip's machine. All projections use the published Windows measurement;
  W02 and W06 must produce native Windows numbers before any Windows performance sentence is
  written without a caveat.
- **Not** a commitment to the hour ranges. They are engineering estimates at ±40 %, from the
  measured baseline in §2 and the ownership split in §3.2.
