# W05 slice 4 — the fog raster

Status: **landed on `render/cpp-w05-parity` (PR #150).**

## What crosses, and what does not

The fog is not a per-pixel effect in the Python renderer. `render/fog.py::FogMask` classifies **one
texel per visibility cell** into three states — the team's sensors reach it (alpha 0), seen before but
not now (alpha 155, charted), never seen (alpha 255, unexplored) — and draws the result as a single
quad lying on the ecliptic. The classification is authoritative state: sensor sources, their effective
radii, and every allied player's explored-cell set.

So the **finished mask** crosses, not its inputs. Carrying the inputs instead would be worse on every
axis: the explored-cell set alone is thousands of cells, and re-deriving the radii in the window would
be a second opinion about what the player can see — exactly what W05 forbids.

`render_bridge/fogmap.py` (`ARMFOG01`): 28-byte header `<8sHHffII>` — magic, version, cells, metres
per cell, map bounds, generation, crc32 — then `cells × cells × 4` bytes of RGBA, row 0 at the −z
edge, the same order `pygame.image.tobytes` produces and the quad's texcoords expect. A 72-cell mask
over the 36 km skirmish map is **20,764 bytes**. Every check is refuse-whole: a half-decoded mask
would reveal ground the player has never seen, which is a state leak rather than a cosmetic slip.

The window (`render_cpp/include/fogmap.hpp`, `shaders/vs_fog.sc` / `fs_fog.sc`) samples the texture on
one quad, alpha-blended, **depth test off** — in the Python pass the mask is a picture of what the
player knows, not geometry in the world, so it covers unexplored space and the ships inside it.

## What was republished, and when

The mask is published only when the classification changes (`FogMask.surface` returns the same object
while its key holds). In the live fixture that turns out to be *most frames* — sensors ride on hulls,
so hull motion changes visibility — and it costs **2.03 ms median / 2.26 ms worst** to rasterise and
encode, at 20 KB per publication. That is the simulation's own answer being rasterised, not the
window doing visibility work.

## Evidence

The live mask moves with the fleet, so two captures a few ticks apart are not the same mask: comparing
them would measure the simulation, not the transport. The parity frame therefore uses a **fixed,
synthetic** pattern (`tools/render/fog_pattern.py`): a clear third, a charted third, an unexplored
third, and one deliberately see-through cell in the middle of the unexplored block, so a transposed or
mirrored upload shows up as a picture that is wrong rather than a number that is off. Both frames are
labelled synthetic in the artifact report.

Both sides were rendered twice — with and without the overlay — so each is measured against its own
clear colour (Python clears to black, the native window to a dark blue), and the two opaque states are
told apart by distance to the colour that state produces over that background, not by brightness.

| measure | result |
| --- | --- |
| state labels (charted / unexplored) | **1.0000 agreement over 773,326 compared pixels, 0 disagreeing** |
| overlay footprint IoU | **0.9972** (793,503 native vs 791,260 python opaque pixels) |
| boundary columns along the centre row | **identical**: 0–155 clear, 156–639 charted, 640 the single see-through cell, 641–1123 charted, 1124–1279 unexplored |

Frames: `artifacts/cpp-renderer/w05/fog-python-pattern.png`,
`fog-native-pattern.png`, the numbers in `fog-parity.json`, and a live frame with the mask over the
melee in `fog-live.png`.

## A real bug this slice found in the shared ring

The fog slot was sized exactly to the blob (`header + pixels + 20`). The first publish was refused —
then, sized to the nominal capacity, the mask failed its own crc: the ring writes its completing tag
into each slot's **last 8 bytes**, so capacity is `slot_bytes − 28`, not `slot_bytes − 20`. Every
existing producer leaves slack, which is why it had never bitten. Fixed in `render_bridge/ring.py` and
`render_cpp/include/frame_v2.hpp` (`SLOT_TRAILER` / `kSlotTrailer`), with a regression test that
publishes a frame of exactly `payload_bytes` and reads its last byte back
(`tests/test_render_ring.py`), and the C++ capacity assertion in `test_frame_v2`.

## Not carried

* The minimap's own fog (a different surface, W06).
* Fog for effects and shots is unaffected: the producer already hands the window per-frame visibility
  answers; this slice is the overlay only.

## An open question this slice could not settle

The fog overlay lands on **identical pixels at the same camera distance** (11000, the Python figure).
That is at odds with the planets slice, where equal framing needed ~1.36× the distance and the source
comment at `viewer.cpp:1246` records `bx::mtxProj` receiving degrees where it wants radians. Both are
measured; they cannot both be explained by a single global projection error, so the projection needs its
own audit before any framing or benchmark number is quoted. The fog result stands on its own: the mask
lands where the mask should.
