# Free Systems Alliance redesign — first style specimens

## Current state

The Escort Frigate and Shipyard are built in Blender and exported as real,
strict-runtime-validated replacements. Their close/rear/tactical before/after
captures use the production native renderer and normal material roles.
These are **two style specimens, not completion of the faction redesign**.
The remaining 24 bindings are the next authoring stage, using these specimens
as the faction style reference; the original full-faction request remains active.

The requested final delivery is the **normal game launched with `main.py`**,
not an optional-viewer-only merge. No merge or release has been requested for
these new appearances yet. Normal settings and the shipped catalogue remain
unchanged during this first visual check; the existing accepted Imperium fleet
is protected.

## Style

Alliance modular/naval construction rather than Imperial spear-shaped armor:
chamfered command modules, connected service frames and mission pods, broad
stepped plating, exposed paired drives, inhabited industrial facilities and
open drydock slipways. The shipyard has two empty service lanes with connected
cranes; it is not a filled box with a dock label.

## Full coverage

`coverage.json` is derived from the live shipped catalogue and verified hashes:
26 bindings = 10 ship/logistics + 10 orbital stations + 2 satellites + 4 surface
installations. Crew transport and generated trade convoys share one existing
binding. The shared scaffold and environmental meshes are not faction-specific
and stay unchanged. No new classes, costs, balance values or unit behavior.

## First specimens

| Binding | Triangles | Export vertices |
|---|---:|---:|
| `rebel:frigate` | 9,864 | 5,480 |
| `rebel:shipyard` | 10,708 | 6,824 |

Both fit the exact existing replacement envelopes with small inward clearance,
use all six existing material roles and remain inside the current loader limits.
Editable new masters are `art/blender/alliance_redesign_{frigate,shipyard}.blend`;
old Alliance/Imperium masters, exports and approved helpers are not overwritten.

## Real native evidence

`native-specimens/before-after.png` compares the exact same entity, ownership
color, camera and shader, with an unchanged Imperial Vigil control. Individually
framed subjects are not a ship-size comparison or organic construction test.

Changed pixels (>8 RGB delta), close / rear / tactical:
- Frigate: 30,480 / 26,027 / 4,696.
- Shipyard: 77,416 / 71,033 / 10,734.
- Imperial Vigil control: 0 / 0 / 0.

`native-specimens/metrics.json` binds each rendered mesh to its actual path/hash.
`native-specimens-supervised.{json,txt}` records the successful externally bounded
capture. All retained PNGs were recompressed losslessly with decoded pixels checked.

The generic benchmark snapshot exporter assumes Imperial stations; this new
capture tool instead uses production `render_bridge.collect.station_binding`
for the specimen owner's actual faction. A regression covers the Alliance
station binding so an Imperial shipyard cannot masquerade as an Alliance review.
The shared exporter and runtime were not changed.

## Reproduce

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/art/build_alliance_redesign.py
.venv/bin/python tools/art/package_alliance_redesign.py
.venv/bin/python -m pytest -q tests/test_alliance_redesign_ship_designs.py \
  tests/test_alliance_redesign_station_designs.py \
  tests/test_alliance_redesign_specimens.py tests/test_alliance_redesign_capture.py
.venv/bin/python tools/render/verify_alliance_redesign.py --include-control \
  --out /absolute/fresh/path/native-specimens
```

The builder refuses existing new outputs unless `--replace-own` is explicitly
provided. Do not rebuild the original accepted masters. Blender is offline-only;
the eventual normal game requires no Blender installation.

## Rollout constraints

The existing optional-pack global triangle ceiling applies to the combined
Imperium + Alliance selection, not to each individual pack. Keep the accepted
Imperium geometry unchanged; allocate the remaining faction budget explicitly
before bulk authoring. Never silently raise the cap, split packs to bypass it,
or reduce accepted Imperium detail. The two current specimens fit that ceiling.
Normal-game rollout must migrate both former thirteen- and fourteen-pack shipped
settings, retain custom selections/preferences, regenerate the actual shipped
native catalogue, and verify all non-Alliance native asset rows remain identical.
