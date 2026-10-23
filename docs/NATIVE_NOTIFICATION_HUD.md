# Native INCOMING and lower-centre messages

## Scope and layout contract

The remaining notification slice is the bottom-left `INCOMING` event log and the lower-centre transient `flash_msg` banner. Reuse the existing native vector/text transport and renderer; ordinary `main.py` activates it through the existing `HUD.native_panels` lifecycle. Do not add another viewer or presentation setting.

User corrections take precedence over the initial general shrink request:

- INCOMING has the **same left edge and width as the approved compact left panel**: logical x=10, width=240. Its previous width was 420; exact column alignment overrides a literal 25% width reduction.
- INCOMING height is approximately 75% of its previous `34 + 18*row_count`; its bottom stays at H−14. Preserve latest-nine ordering, existing colours and owner-only event filtering.
- The lower-centre flash background is approximately 75% of its previous measured width and height, centred at the existing `(W//2,H−60)` anchor. Preserve message contents, warning colour, replacement and expiration timing. Preserve the measured geometry even for oversized strings; viewport clipping handles overflow just as in the legacy path, rather than clamping the source width before scaling.
- Keep already-approved upper/left/right/minimap geometry unchanged. Retain Python gameplay, event generation, translations, visibility and command validation.

## Implementation boundary

Capture the two complete notification scopes before pygame rasterization, using the existing `hud-vector.ring` snapshot. The legacy control must remain available solely for paired acceptance comparisons. Surface clips and blocked input bounds must follow the same transformations as native geometry; expired/empty modules disappear from complete snapshots.

`Sink` gains explicit source/target Y anchors with existing defaults unchanged. A `center` text-fit mode means shrink within the bounds and centre the **measured native ink**, not a padded pygame font surface; existing `shrink` and `clip` behavior stays unchanged. The strict producer/decoder accepts this additional bounded fit value.

The incoming event glyphs `△`, `✦` and `◉` need real native shapes because the authenticated bundled alphabet atlas does not contain them; destruction `✕` is already native. Preserve the literal event strings, single translucent coverage, clipping and the existing CPU/mesh budgets.

Residual mission, floating world annotations, drag/placement/targeting and outcome overlays are outside this slice.

## Acceptance

Require RED→GREEN CPU tests for exact column alignment and compact bounds, centre-fit text, native glyph shapes, no rasterization in migrated scopes, latest-nine filtering, local-player privacy, replacement/expiry, empty clears, unchanged gameplay checksums and EN/PL/DE/RU strings. Then rebuild the production native targets and run CTest, existing HUD regressions and actual-main before/after readbacks at small and large drawable sizes.

The actual-main helper must use an empty unique output, isolated persistent paths, real production loop/presentation and real input. Write a passing receipt only after cleanup and protected-file verification. Check for an owner game before any GPU/GL launch; never stop it automatically.

The helper only accepts a **shipped resolution preset** (`render/display_settings.py`
`RESOLUTIONS`), read from that source with `ast` so the CLI never imports the game:
the production window silently replaces any other requested size with desktop-derived
`auto`, so a `1024x640` request used to render a full frame and then fail
`wrong production output resolution`. It is now refused before any output directory is
created. Use `1280x720` as the small case and `2560x1440` as the large one.

Handover requires the rebuilt candidate in the owner's ordinary checkout and independently reviewed code. Owner visual approval remains separate from merge authorization.
