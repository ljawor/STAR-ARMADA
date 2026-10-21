# W03 — Draw-list executor: premise check and measured design

Status: **started 2026-10-21**. Branch `render/cpp-w03-drawlist`, base `main` @ `463d431` (W02
merged). This document exists because the plan's premise — *replace the `gl*` calls in the UI
modules with draw-list emission and re-rasterize text from an atlas in C++* — does not match what
the code does today. The numbers below decide which design W03 should implement.

## 1. What the UI code actually does

Measured, not assumed:

| Module | Lines | `gl*` calls | How it paints |
|---|---:|---:|---|
| `render/hud.py` | 1693 | 43 | Draws into one `pygame.Surface` (`self.overlay`, `hud.py:140`), then `_upload()` (`hud.py:1644`) converts the whole surface with `pygame.image.tostring` and calls `glTexImage2D`; `draw_gl()` draws one fullscreen ortho quad |
| `render/menus.py` | 1371 | 49 | Same shape: layout and text into a surface, one textured quad |
| `render/classic_screens.py` | 375 | **0** | Pure surface painting via `render/clean_classic.py`, which uses `pygame.font.SysFont('helvetica,arial', …)` and `surface.blit` |

Two facts follow, and both matter for the estimate:

1. **`classic_screens.py` has no GL code to replace.** The plan lists it as a shim target; it is
   already surface-only. Its work is transport, not primitives.
2. **Text is not drawn by GL at all.** Every label in the HUD and menus is rasterized by SDL_ttf into
   the shared surface. There is no per-glyph GL path to port, and no atlas to reproduce — the
   four-language-pack tofu risk (§8.2 test 4) comes from *re-implementing* glyph rasterization in
   C++, which this design would simply not do.

## 2. What the current upload costs

`tools/render/measure_overlay.py`, 240 frames, 1280×800 RGBA (1.024 MP, 4,096,000 B/frame),
`glFinish` after each transfer, on the same host as the W02 receipts (macOS, Apple Silicon, Metal):

| Path | median | p95 |
|---|---:|---:|
| `pygame.image.tostring` only | 0.575 ms | 0.589 ms |
| tostring + `glTexImage2D` (what `_upload` does today) | **0.951 ms** | 0.982 ms |
| tostring + `glTexSubImage2D` into an allocated texture | 1.319 ms | 1.353 ms |
| one 320×180 dirty rect, tostring + `glTexSubImage2D` | **0.061 ms** | 0.068 ms |

Receipt: `artifacts/cpp-renderer/w03/overlay-upload.json`. Synthetic by construction — the surface
content is drawn by the bench, not by a match, so this measures transfer cost and nothing else. The
timings are pessimistic in one way (a real frame overlaps the transfer with the world pass) and
optimistic in another (no window resize, no GPU contention).

The useful reading: the HUD's per-frame upload costs about as much as the entire W02 producer budget,
and it is proportional to uploaded area. A full-screen HUD that animates everywhere will not reach
0.061 ms, but a HUD whose animated parts are a few panels will.

## 3. Candidate designs

**A — Overlay transport (recommended).** Python keeps composing the surface exactly as now; the
bridge carries the overlay texture (dirty rects, RGBA, same header discipline as W02) and C++ owns
the ortho pass, the blend state and the final composite. Layout code untouched, text rasterized by
the same SDL_ttf calls, so the UI is pixel-identical by construction rather than by comparison.
Cost: a new payload kind in the bridge, dirty-rect tracking in `hud.py`/`menus.py`, C++ texture
upload + quad. Risk: bandwidth (4 MB/frame for a full surface; 230 KB for one 320×180 rect).

**B — Draw-list primitives + C++ atlas.** The plan's original design. Every `pygame.draw.*` becomes a
draw-list record, text becomes glyph quads from an atlas built from the same TTFs. Removes SDL_ttf
from the frame path and gives resolution independence. Risk: glyph coverage per language pack must be
proven against four catalogues, and the atlas must reproduce pygame's kerning and hinting to pass a
pixel comparison — which is where the 100–160 h estimate comes from.

**C — Hybrid.** Draw list for geometry (panels, bars, borders, icons), text runs as pre-rasterized
line textures cached by (string, size, colour). Most of B's control, none of B's glyph risk, but it
introduces a cache-invalidation surface that neither A nor B has.

Recommendation: **A first**, because it is the shortest path to "the C++ window shows the real HUD and
menus" and it cannot fail a pixel comparison it defines itself. B stays available as a later
optimization if the overlay bandwidth ever shows up in a frame budget.

## 4. Slice order for A

1. **Dirty-rect tracking, in the legacy renderer.** `hud.py`/`menus.py` record the rects they paint
   into and `_upload()` sends only those. Measurable today, helps the shipping renderer, and is the
   input W03 needs. Gate: identical pixels for a fixed UI state (byte compare of the surface), and
   upload cost measured before/after on a real session.
2. **Overlay payload in the bridge.** New frame kind `overlay` carrying (w, h, rect list, RGBA bytes)
   with a CRC and the same single-producer/one-snapshot rules as `ARMADAR1`. Reuse the v2 header
   conventions; do not touch the approved offline profile.
3. **C++ consumer.** Texture upload with dirty rects, ortho pass after the world pass, blend state
   matching `hud.py::draw_gl` (lit off, depth off, `SRC_ALPHA/ONE_MINUS_SRC_ALPHA`).
4. **Screens side by side.** Main menu, skirmish setup, settings (all pages), library, replay
   browser, HUD with a mixed selection and a long refit effect — captured legacy vs C++ from the same
   state, compared pixel-wise with a stated tolerance and a diff image for every failure.

Gate for W03: every visible string present, pixel difference under the stated tolerance, and the four
language packs rendering identically in both paths (trivially true for A, which must still be proven
by capture, not by argument).

## 4a. Decision and first slice (2026-10-21)

The owner chose **A**: *"OK. Your right. Let's go for A. If we later discover that we have big costs
on the hud we can still run a migration project for this part seperatly."* Recorded in
`art/manifests/pipeline_policy.json` as `render-w03-design-a-overlay-transport-2026-10-21`, scoped to
W03 with no tag, release, default-renderer or frame-rate claim attached.

Slice 1 is implemented in the legacy renderer, because it is the same work either way and it pays
off before any C++ exists:

- `render/overlay_upload.py` — `OpRecorder` records one key per paint call (every argument that
  affects its pixels) plus the rect it painted; `OverlayUploader` sends only the rects whose keys
  changed, merged into bands, with `glTexSubImage2D`. Unkeyed blits are dirty every frame.
- `render/hud.py` — the 59 `pygame.draw.*` calls, the `fill` and the 17 overlay blits go through the
  painter proxy; `_label` and the bar labels carry keys, so unchanged text is not re-sent.

Measured with `tools/render/measure_hud_frame.py` (360 frames per mode, interleaved rounds, real
skirmish state, fps label changing every frame so the dirty path cannot win by doing nothing):

| | median `hud.render()` | pixels uploaded per frame |
|---|---:|---:|
| full surface (previous behaviour) | **2.193 ms** | 1,024,000 |
| dirty rects | **1.407 ms** | 55,016 |

0.786 ms per frame saved (36 %), 95 % fewer bytes. The remaining 55 k pixels are the unkeyed
blits — minimap, fog thumbnail, floating texts — which are genuinely animated.

Correctness is checked two ways, and the second one earned its keep:

- `tests/test_overlay_upload.py` (9 tests): an unchanged paint list uploads nothing; a changed label
  dirties only its own rect; a *vanishing* op dirties the rect it painted; an unkeyed blit is dirty
  every frame; and replaying a run of partial uploads onto a blank buffer reproduces exactly the
  bytes a full upload would send, for a real HUD painted from real state.
- `tools/diag_hud_upload.py` reads the framebuffer back and compares a partially-uploaded composite
  against a forced-full one. All three scenarios (steady state, fps change, hull damage) are
  byte-identical with max channel delta 0, and a repeatability control draws the same state twice to
  prove the comparison itself is sound.

Two defects were found this way, both of which would have shipped silent corruption:

1. **The y offset was inverted.** `glTexImage2D` puts the surface's *first* row at `t = 0`, so
   `glTexSubImage2D` counts rows from that origin: `rect.y`, not `height - rect.bottom`. With the
   inverted formula every patch landed mirrored, which the framebuffer comparison showed as 227
   corrupted rows; the Python-side replay test could not see it, because it used the same formula.
   Any check that only replays the uploader's own arithmetic proves nothing about the GPU — the
   readback is the control.
2. **A disappearing op left its pixels behind.** The fps label is drawn only while `fps > 0`. When it
   stops, there is no op to compare against, so nothing dirtied its rect and the old "59 FPS" stayed
   in the texture. Regression test: `test_a_vanishing_op_uploads_the_area_it_painted`.

## 4b. Slice 2: the transport and the C++ pass (2026-10-21)

Slice 2 carries the surface across the bridge and puts it on screen in the C++ window.

**Wire format** (`render_bridge/overlay.py`, decoded by `render_cpp/include/overlay.hpp`):

    header, 28 bytes: magic b'ARMOVL01', u16 version, u16 flags (bit 0 = whole surface),
                      u16 width, u16 height, u16 rect count, u16 reserved,
                      u32 payload bytes, u32 crc32(payload)
    rects:  count x 8 bytes, u16 x/y/w/h in surface coordinates
    payload: RGBA bytes of each rect in order, row major, no padding

A full frame carries zero rects and `width * height * 4` bytes. A patch frame's payload must be
exactly the sum of its rect areas, so a truncated or padded patch is refused instead of half-applied.
The native decoder validates magic, version, flags, dimensions, rect count, rect bounds, payload
length and CRC, and throws `OverlayError` naming the field it rejected.

**Keyframes, because a window can attach at any time.** Dirty rects are state deltas: a window that
starts after the producer's first frame has no base surface, so patches alone would never complete
the HUD. The producer publishes a whole surface on its first frame and then at least every
`--overlay-keyframe` seconds (default 2.0, 1.0 in the demo launcher), and the window refuses and
counts patches that arrive before it has seen a keyframe (`skipped_patches_before_keyframe`). This
bug was visible in the first live capture: only the minimap and one readout were drawn, everything
else black.

**The C++ pass.** One RGBA8 texture with point sampling (`--overlay-ring`), `updateTexture2D` per
patch, and one fullscreen quad after the world pass with depth off and straight-alpha blending, which
matches `hud.py::draw_gl`.

**Parity, measured.** `tools/render/check_hud_parity.py` replays the same ring in Python and compares
the presented picture with the replayed surface. The window is run with `--hud-only`, which draws
that one quad unblended over opaque black so the backbuffer screenshot *is* the texture's own RGB:

| check | result |
|---|---|
| identical rows | **800 / 800** |
| differing pixels | **0** of 1,024,000 |
| capture offset | **-1 frame** (`screenshot_sequence` records the sequence the capture belongs to, because the window keeps applying frames until it exits) |
| decode failures | 0 |
| patches applied in the run | 103 over 13 frames, 7 of them keyframes |

Two things had to be fixed to get there, both invisible without comparing presented pixels:

1. **`bgfx::requestScreenShot` silently does nothing for a render-target framebuffer on Metal**
   (`renderer_mtl.cpp:1824` returns when the framebuffer has no swapchain). The first dump attempt
   produced no file and the run failed with "HUD dump requested but never captured". Hence
   `--hud-only` presenting into the backbuffer, which the capture path does support.
2. **Sampling.** The HUD is presented one texel per pixel; linear filtering smeared neighbours into
   glyph edges. The texture is created with `BGFX_SAMPLER_MIN_POINT | MAG_POINT`.

**Launching it.** `render_cpp/live.command` starts the producer, waits for a complete frame, and opens
the window; Esc quits and stops the producer. It uses a fresh ring directory per run, because a
window that opens onto a half-created ring aborts with `cannot read ring payload` — the native reader
treats a short read as fatal where a live window should treat it as "no frame yet". That is still
open; the launcher avoids it rather than fixing it.

Measured live session: 986 frames drawn, 638 instances, 13 HUD frames applied, 103 patches,
0 decode failures, `hud.decode` 0.71 ms median.

## 5. What this document does not claim

- No estimate: the 100–160 h figure in `docs/CPP_RENDERER_MIGRATION.md` was written for design B.
  Design A is materially smaller, but this document does not price it — slice 1 has to land first and
  tell us how many rects a real HUD touches per frame.
- No frame-rate claim, and no claim that the C++ window is faster at UI than the legacy one. §4a
  measures `hud.render()` in this window only, with the world pass excluded; the C++ viewer has no
  HUD at all yet.
- No live-loop check: the HUD is rendered from a real skirmish state 360 times, but not inside a
  running match at 60 Hz with input, resizes and menus. Slice 2 runs the transport live but the
  window takes no input, and the producer steps the simulation as fast as it can rather than at a
  match's tick rate — the ~3 Hz stream is a transport property, not a game frame rate.
- Menus are untouched. They paint through `render/clean_classic.py` and are not per-frame, so they
  are a separate slice.
- No approval to change the migration plan's W03 definition. That definition names a text atlas;
  adopting A instead is the owner's call, and this document is the evidence for it.

## 6. Open question for the owner

A or B — carry the composed surface, or port text to a C++ atlas? A is recommended on measured
grounds (§2: the upload is cheap when dirty-rected, and text is already SDL_ttf in both paths), but B
is what the plan says and it is the only one of the two that removes SDL_ttf from the C++ window.
