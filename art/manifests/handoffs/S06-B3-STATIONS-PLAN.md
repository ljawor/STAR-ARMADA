# Handoff: S06 B3 — stations (30 authorable bindings, plus an imperial blocker)

Status: **scoped, not started.** This batch is the next executable step after B2. Nothing here is authored,
reviewed or approved; no station mesh, master or sidecar exists yet.

Base commit / branch: whatever head PR #127 carries when this batch starts (read it from GitHub, not from
this file). The scope below was read out of live code at `cae5104a057317832d05782311f25d7c96caecf0` by
`PYTHONPATH=tests .venv/bin/python tools/art/probe_b3_scope.py`.

## The seam already exists

`render/faction_stations.py:station_mesh(faction, data_id)` asks
`render.asset_selection.mesh_for(f'{faction}:{data_id}')` **before** falling back to its own procedural
layout, so each authored station binds exactly like a squadron did in B2 — `<faction>:<kind>`, no renderer
change, no new dispatch. Its three canonical families each carry ten bespoke functional layouts in
radius-50 space (scaled ×0.8 on the way out), which is the legacy envelope to author inside.

`render/fleet_geometry.station_mesh(data_id, faction)` dispatches imperial stations **straight** to
`_station_mesh(did)` with no `mesh_for` call. Authoring an imperial station therefore needs a renderer
change, so those ten are an owner/renderer decision — the same shape as the shared `wedge`/`box` imperial
ship shapes, not an asset in this batch.

## Envelope table (legacy extents, measured — author inside these)

`length` is the legacy drawn length at the binding's own class ratio; a station authored inside its
envelope keeps it, exactly as B1/B2 did.

| Binding | radius | length | legacy tri | envelope lo | envelope hi |
|---|---|---|---|---|---|
| `rebel:command_station` | 130 | 124.601 | 2,112 | `[-48.0, -6.8, -29.6]` | `[48.0, 26.48, 29.6]` |
| `rebel:shipyard` | 110 | 170.135 | 6,080 | `[-56.0, -19.6, -44.8]` | `[56.0, 39.04, 50.758]` |
| `rebel:research_station` | 85 | 133.144 | 3,504 | `[-40.0, -9.6, -25.6]` | `[40.0, 39.28, 35.901]` |
| `rebel:defense_platform` | 60 | 129.578 | 4,560 | `[-45.92, -4.8, -44.32]` | `[45.92, 11.166, 44.32]` |
| `rebel:mining_station` | 70 | 108.192 | 2,416 | `[-44.8, -15.6, -26.0]` | `[44.8, 10.12, 22.8294]` |
| `rebel:sensor_station` | 45 | 115.685 | 3,344 | `[-46.4, -12.8, -24.8]` | `[46.4, 30.48, 16.24]` |
| `rebel:trade_station` | 65 | 118.704 | 4,512 | `[-44.0, -5.948, -38.736]` | `[44.0, 6.12, 39.36]` |
| `rebel:fighter_platform` | 75 | 125.304 | 2,464 | `[-48.0, -9.2, -39.2]` | `[48.0, 6.92, 39.2]` |
| `rebel:repair_dock` | 70 | 119.995 | 3,104 | `[-38.4, -12.8, -33.6]` | `[38.4, 23.6, 39.6]` |
| `rebel:energy_relay` | 55 | 117.862 | 2,208 | `[-50.4, -8.4078, -29.36]` | `[50.4, 13.2078, 20.9846]` |
| `confederacy:command_station` | 130 | 181.411 | 1,616 | `[-53.8231, -6.0, -38.4]` | `[53.8231, 41.6, 60.0]` |
| `confederacy:shipyard` | 110 | 194.662 | 1,136 | `[-62.04, -5.6, -45.0564]` | `[62.04, 41.6, 62.4]` |
| `confederacy:research_station` | 85 | 143.010 | 1,296 | `[-46.3156, -12.4, -33.48]` | `[46.3156, 13.88, 52.68]` |
| `confederacy:defense_platform` | 60 | 153.550 | 1,984 | `[-50.2043, -8.4, -31.2764]` | `[50.2043, 16.544, 55.68]` |
| `confederacy:mining_station` | 70 | 126.205 | 2,032 | `[-40.6686, -31.44, -29.36]` | `[40.6686, 11.08, 46.96]` |
| `confederacy:sensor_station` | 45 | 126.419 | 1,200 | `[-36.1913, -14.0, -28.2851]` | `[36.1913, 38.4, 34.8]` |
| `confederacy:trade_station` | 65 | 132.221 | 4,032 | `[-43.7668, -6.552, -46.0532]` | `[43.7668, 18.28, 46.0532]` |
| `confederacy:fighter_platform` | 75 | 113.755 | 3,904 | `[-42.4021, -8.8, -36.4]` | `[42.4021, 11.88, 36.0]` |
| `confederacy:repair_dock` | 70 | 120.561 | 2,496 | `[-40.1472, -14.8, -36.4]` | `[40.1472, 26.4, 36.4]` |
| `confederacy:energy_relay` | 55 | 139.550 | 976 | `[-41.4372, -16.0, -25.7713]` | `[41.4372, 31.6, 46.4]` |
| `syndicate:command_station` | 130 | 153.163 | 1,120 | `[-52.1606, -15.2, -53.6606]` | `[48.0, 45.6, 38.4883]` |
| `syndicate:shipyard` | 110 | 162.806 | 1,248 | `[-52.1606, -18.9928, -53.6606]` | `[46.9468, 45.6, 48.4056]` |
| `syndicate:research_station` | 85 | 123.622 | 2,336 | `[-40.0, -7.2, -27.572]` | `[36.4, 37.68, 32.8]` |
| `syndicate:defense_platform` | 60 | 110.354 | 1,408 | `[-45.9679, -10.8, -28.5448]` | `[30.3691, 22.1, 28.0475]` |
| `syndicate:mining_station` | 70 | 142.597 | 1,696 | `[-33.9322, -32.4, -25.0848]` | `[42.4, 39.6, 41.4431]` |
| `syndicate:sensor_station` | 45 | 118.442 | 1,248 | `[-47.2, -17.6, -31.137]` | `[26.3565, 43.857, 21.1423]` |
| `syndicate:trade_station` | 65 | 143.954 | 2,048 | `[-52.3122, -8.8, -48.6483]` | `[45.2571, 24.5, 46.5606]` |
| `syndicate:fighter_platform` | 75 | 118.601 | 1,312 | `[-39.6, -15.2, -39.2]` | `[32.1135, 30.8, 39.2]` |
| `syndicate:repair_dock` | 70 | 130.100 | 1,120 | `[-37.4318, -16.8, -38.931]` | `[39.7528, 34.8, 37.9495]` |
| `syndicate:energy_relay` | 55 | 134.957 | 2,144 | `[-47.5594, -11.2, -46.5402]` | `[46.5284, 23.36, 34.4011]` |

All thirty currently report `mesh_for` unclaimed (`mesh_for(key) is None`), so none is registered or
selectable.

## Imperial stations (10, blocked on a renderer decision)

`imperial:command_station` r130 2,672 tri, `shipyard` r110 1,584, `research_station` r85 1,104,
`defense_platform` r60 1,584, `mining_station` r70 1,536, `sensor_station` r45 976, `trade_station` r65 2,288,
`fighter_platform` r75 864, `repair_dock` r70 816, `energy_relay` r55 928 — all drawn by
`render/fleet_geometry._station_mesh(did)` with no `mesh_for` seam. To author them, `station_mesh` needs the
same `mesh_for` consult the faction path already has. That is a one-line renderer change plus its guards, and
it must be its own decision record, not a side effect of an asset batch.

## B4 preview (satellites and planet installations, 24 bindings)

`assets/data/stations/stations.json` also holds `defense_satellite`, `attack_satellite`,
`planet_extractor`, `planet_trade_hub`, `planet_shield_generator`, `planet_pulsar_cannon` (all radius 45).
These are the same file's keys minus the station kinds — enumerate them that way rather than by hand.

## Authoring approach for B3 (mirrors B2, with the lesson already learnt)

- **One shared seed** (`tools/art/build_b3_stations.py`, `--asset <faction>:<kind>`) with the same
  before-Blender pre-flight refusal of an existing master, plus the generated export wrappers from
  `tools/art/templates/export_wrapper.tmpl`.
- **A station kit, not thirty hand-written builders:** the legacy layouts already share a vocabulary
  (radial ring, spoke arms, central spine/tower, dock cradle, gantry/frame, panel and array banks, dish and
  mast, vent blocks), and the renderer's own `_Hardware` supplies `ring` / `loft` / `plate`. Parameterise by
  faction silhouette × station function, so a functional layout reads at tactical range and the faction
  reads at close range.
- **Fit each station inside the envelope row above** and verify with `probe_master_bounds.py` before
  exporting; measure with the evaluated (bevelled) bounds, never the declared sections.
- **Stations are large and mostly convex**, so a drive-mouth-style occlusion defect is unlikely; the review
  that matters here is the **role ablation at tactical range** (accent/dark/cool) plus a close-range capture
  to prove the functional layout reads. Author every emissive part the way B2's rule requires anyway: every
  closed solid ends forward of the emitter's face.
- Acceptance for the batch: each of the thirty bindings has a master, an export-only wrapper, a pending
  sidecar regenerated by `write_pending_sidecars.py --check`, focused guards green, one shared batch contact
  sheet with per-station close/tactical captures, and evidence committed under
  `artifacts/s06_alliance_batch_review/`; no production registration, no merge, registry status stays
  `procedural_legacy`.

## Owner decisions still open before or during B3

1. **Imperial stations** — authorize the `mesh_for` seam in `fleet_geometry.station_mesh` (one line plus
   guards), or leave those ten procedural.
2. **Imperial ships** (`imperial:fighter`, `imperial:bomber`, `imperial:convoy`) — scope the shared `wedge`/`box`
   source change or leave them.
3. **`trade_convoy` envelope** for the four rows that share the crew-transport meshes.
4. **Appearance approval for the eleven S06 specimens already authored** (cruiser, B1 pair, B2's eight).
