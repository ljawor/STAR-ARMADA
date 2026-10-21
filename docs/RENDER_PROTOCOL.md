# Render protocol — W00/W01 offline file profile v1

Scope: an opt-in **offline tool**, not a gameplay renderer switch. Python exports
one file; the native SDL3/bgfx viewer reads it. No simulation, asset, approval,
save/replay, LAN, gameplay defaults or legacy renderer behaviour changes.

This profile deliberately uses JSON, not the proposed packed SoA/shared-memory
format. It does **not** freeze the W02 live transport, ring layout, input protocol,
UI parity, or a ≤1 ms serialization claim. Those require separate design and
measurement. The migration plan's broader proposed wire layout is not implemented
by this profile. W00's 600 instances and UI500 are synthetic transport controls,
not evidence of a running 600-ship battle or rendered HUD.

## 1. Envelope (both kinds)

Exactly one frame per file. Header is 32 bytes, little endian, packed without
alignment padding. Python's normative layout is `struct.Struct('<8sHHIQII')`.

| Offset | Size | Type | Meaning |
|---|---:|---|---|
| 0 | 8 | bytes | magic `b'ARMADAS\0'` (hex `41 52 4d 41 44 41 53 00`) |
| 8 | 2 | u16 | version = 1 |
| 10 | 2 | u16 | kind: 1 world, 2 UI |
| 12 | 4 | u32 | simulation tick; never wall-clock time |
| 16 | 8 | u64 | render frame index (offline exporter starts at 0) |
| 24 | 4 | u32 | payload byte length, excluding header |
| 28 | 4 | u32 | standard zlib/IEEE CRC32 of payload bytes only |

The payload limit is **64 MiB = 67,108,864 bytes**, inclusive; it is not a target
frame size. Check the header and declared length before allocating/parsing the
payload. Exact file length must be `32 + payload_length`: truncation and trailing
bytes (including a second frame) are errors. CRC is integrity, not authentication.

Payload bytes are canonical UTF-8 JSON produced by:

```python
json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
```

`ensure_ascii` retains Python's default `True` (non-ASCII characters are escaped).
Root must be an object, keys strings, numbers finite. No BOM, insignificant
whitespace, duplicate keys, NaN or Infinity. The Python decoder requires
byte-identical canonical re-encoding, including Python JSON number formatting.
Do not rewrite the payload in a different JSON library before checking its CRC.
No compression, pointer values or native struct layouts occur in the payload.

Reference API (`render_bridge.protocol`): `encode(payload, kind=1, tick=0,
frame_index=0) -> bytes`; `decode(bytes) -> Frame(kind, tick, frame_index, payload)`.
Envelope decoding checks framing/canonical JSON, **not** world semantic validity;
a world consumer must additionally validate schema, required fields, vector
lengths, finite transforms, entity/binding uniqueness, hashes and safe asset paths.

Unknown magic/version/kind, CRC failure, invalid JSON or invalid length raise
`ProtocolError` in Python. A native consumer rejects them with exit **3**, without
partially drawing the file. Unknown future versions are never guessed. Device
failure exit **4** belongs to the native viewer/later lifecycle, not this codec.
No live fallback or subprocess recovery is implemented here. A future incompatible
wire format needs an explicitly agreed version/profile, not a silent reinterpretation.

## 2. World payload (`kind=1`, `schema=1`)

Required top-level fields:

- `schema`: integer 1.
- `fixture`: versioned source fixture name (normally `four-player-combat-v1`).
- `state_sha256`: lower-case 64-hex SHA256 from `game.benchmark.state_hash(state)`;
  this hashes the **full precise** `state.to_dict(precise=True)` as canonical JSON,
  not a rounded display state or a narrower replay checksum.
- `camera`: `{target:[x,y,z], distance, yaw, pitch, fov}`. Angles and vertical FOV
  are **degrees**. Target/distance use simulation world units.
- `instances`: objects `{entity_id:int, binding:string, position:[x,y,z],
  yaw:number, scale:number, tint:[r,g,b,a], category:string}`. Entity yaw is
  **radians**, rotation about +Y, zero forward +Z; positive yaw turns +Z toward
  +X. Uniform scale, then yaw rotation, then world translation. Y is up.
  Tint channels are normalized linear coefficients in [0,1]. IDs are real entity
  IDs except in explicitly labelled transport/catalogue inspection fixtures.
- `assets`: one entry per used binding, sorted by binding:
  `{binding:string, path:string, sha256:string, vertex_count:int,
  triangle_count:int}`. Path is relative to the viewer's **assets directory**,
  e.g. `models/imperial_corvette.mesh.json`, never `assets/models/...` relative to
  that directory. Resolve beneath that root; refuse absolute paths, `..`, and
  symlink escapes. SHA256 covers the unchanged mesh file bytes. Counts come from
  `vertices` and the sum of `batches` rows, cross-checked against `triangle_count`.
- `metadata`: inventory, assumptions, visibility mode, explicit omissions,
  checksum provenance, scale policy and offline profile label.

No lights, FOV-dependent inflated hull sizes, effects, fog raster, UI composition,
planet surfaces or live camera events are silently inferred as game parity.
Viewer lighting is a viewing convention, not simulation state.

### Extraction and visibility

`tools/render/dump_snapshot.py` calls `game.graphics_benchmark.make_fixture`, never
the game loop, and verifies full precise checksum **before and after all render-only
extraction**, including catalogue mode. No simulation or selection settings are
persisted. The tool does configure process-local render selection/cache state.

Use real approved binding resolution: `asset_selection.configure({'model_preview':
True}, asset_root=ROOT)` and `asset_selection.ship_binding(ds, data_id,
owner_faction)` (including trade convoys). The `asset_root` argument is misleading:
current `AssetResolver` expects the **repository root containing assets/**; passing
`ROOT/'assets'` incorrectly searches `assets/assets/models/...`. Snapshot paths,
by contrast, are intentionally relative to `ROOT/'assets'`. Station bindings use
registered `imperial:` + entity `data_id` for these all-Imperial fixtures.

Every alive detected non-planet entity is exported; missing/unresolved approved
meshes cause an explicit error rather than silent omission. `assets/models/registry.json`
and its referenced manifests select mesh paths; the real resolver validates the
mesh contract. No guessed filename dispatch or procedural replacement is used.
Ships use canonical `ship_size(...).scale`, **not** the gameplay zoom readability
multiplier; stations and satellites use `radius/50`. Satellite placement is the
real fixture entity position; planet-surface parity remains W05.

Default visibility is ordinary `state.can_see(0, entity_id)`, labelled
`player0-detection`, **not** all-map/omniscient or camera-frustum filtering. Explicit
`--all-visible` means `omniscient-diagnostic`. Metadata distinguishes source-world
`inventory` from `exported_inventory`, lists visible omitted planet IDs, and says
planet rendering is deferred to W05. The unchanged source includes 600 combat
ships plus infrastructure/convoys; it is not truncated to 600 instances.

`--units` is only a count assertion on the chosen versioned fixture (600 for the
default stress fixture, 52 for stock). It never modifies its recipe.

### Catalogue inspection (optional)

`--catalogue` uses all 103 core registry bindings / 103 unique runtime mesh paths,
resolves and validates every mesh, and writes an artificial grid with synthetic
IDs, raw authored scale 1 and an inspection camera. It is labelled
`catalogue-inspection-not-gameplay`, fixture
`approved-runtime-catalogue-inspection-v1`. Its checksum identifies the unchanged
**source** game fixture; it is not a checksum of synthetic inspection transforms
and does not prove gameplay appearance, camera fit or native rendering acceptance.

## 3. UI transport fixture (`kind=2`, `schema=1`)

Root fields: `schema`, `fixture`, `viewport:[width,height]`, `commands`, `metadata`.
The synthetic UI500 fixture has 500 `quad` commands in list order, each with
`op`, `rect:[x,y,w,h]`, `uv_rect:[u0,v0,u1,v1]`, `rgba:[r,g,b,a]`, `texture_id`,
`clip_rect:[x,y,w,h]`, `layer`. Coordinates are top-left-origin logical pixels,
+X right and +Y down; layers are integers. No actual texture/atlas is shipped or
implied by texture ID 0. W03 must specify resource tables, glyph runs, DPI,
blending and clipping semantics before claiming UI parity. The offline world
viewer need not execute UI kind 2; it must not mistake it for kind 1.

## 4. Frozen transport controls

Under `tests/fixtures/render_protocol/`:

| File | Contents |
|---|---|
| `empty.world.snap` | zero instances, synthetic empty world |
| `synthetic600.world.snap` | 600 synthetic transport instances, unresolved transport binding, no mesh dependencies |
| `ui500.snap` | 500 synthetic quad commands |
| `checksums.json` | exact file byte lengths and SHA256 hashes |

All three explicitly set `metadata.synthetic_transport_fixture=true`. Zero-filled
`state_sha256` in the synthetic world files is a **sentinel**, never a real game
checksum. The unresolved binding is intentional: these are codec controls, not
native asset-rendering input. Obtain useful viewer input using the real dumper.

The focused budgets are three W00 tests (roundtrip, rejection, frozen fixtures)
and three W01 tests (real read-only extraction, CLI visibility, catalogue closure).
No heavy benchmark, screenshot, full-suite sweep, or ≤1 ms assertion is made.

## 5. Camera authority correction for later live phases

W01's offline viewer may orbit/pan/zoom locally because it never issues game
commands. For live phases Python must own the authoritative camera, **or** input
must carry the exact frame-indexed camera/viewport snapshot used for that event,
with matching Python picking/fog queries. A once-per-second camera mirror is
**not** sufficient for picking and must not be implemented as authority. Renderer
input capture does not acquire simulation-command authority.

## 6. Commands (from repository root)

```sh
python tools/render/dump_snapshot.py --units 600 --out "$TMPDIR/w01-real.snap"
python tools/render/dump_snapshot.py --all-visible --out "$TMPDIR/w01-omniscient.snap"
python tools/render/dump_snapshot.py --catalogue --out "$TMPDIR/w01-catalogue.snap"
PYTHONPATH=tests python -m unittest test_render_protocol test_render_snapshot -v
```

Use the project's existing Python environment. SDL3/bgfx dependencies and native
build instructions belong to `render_cpp/`; this exporter does not import GL,
open a window, change renderer defaults, or attest native acceptance.
