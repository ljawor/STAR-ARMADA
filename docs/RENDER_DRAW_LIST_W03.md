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

## 5. What this document does not claim

- No estimate: the 100–160 h figure in `docs/CPP_RENDERER_MIGRATION.md` was written for design B.
  Design A is materially smaller, but this document does not price it — slice 1 has to land first and
  tell us how many rects a real HUD touches per frame.
- No frame-rate claim, and no claim that the C++ window is faster at UI than the legacy one. Only the
  upload cost in §2 is measured.
- No approval to change the migration plan's W03 definition. That definition names a text atlas;
  adopting A instead is the owner's call, and this document is the evidence for it.

## 6. Open question for the owner

A or B — carry the composed surface, or port text to a C++ atlas? A is recommended on measured
grounds (§2: the upload is cheap when dirty-rected, and text is already SDL_ttf in both paths), but B
is what the plan says and it is the only one of the two that removes SDL_ttf from the C++ window.
